"""Exercise the installed selection hooks against original x86 code in Unicorn."""
from pathlib import Path
import json,sys,struct,os,tempfile,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'.tools'))
import pefile
from unicorn import *
from unicorn.x86_const import *
from keystone import *
M=json.loads(Path('.tools/selection-runtime.json').read_text());B=M['base'];D=M['data']
compiled=None
if len(sys.argv)>1:
 launcher=Path(sys.argv[1]).resolve();newbase=int(sys.argv[2],0) if len(sys.argv)>2 else 0x2340000
 fixture='''using System;using System.IO;using System.Reflection;using System.Collections.Generic;class Dump {static void Main(string[] a){var t=Assembly.LoadFrom(a[0]).GetType("Amagadon.SelectionRuntime",true);foreach(var e in (Dictionary<int,byte[]>)t.GetMethod("Build").Invoke(null,new object[]{int.Parse(a[2])}))File.WriteAllBytes(Path.Combine(a[1],e.Key.ToString("x8")+".bin"),e.Value);}}'''
 with tempfile.TemporaryDirectory(prefix='amagadon-selection-') as folder:
  folder=Path(folder);(folder/'Dump.cs').write_text(fixture)
  subprocess.run([str(Path(os.environ['WINDIR'])/'Microsoft.NET/Framework/v4.0.30319/csc.exe'),'/nologo','/platform:x86','/out:'+str(folder/'Dump.exe'),str(folder/'Dump.cs')],check=True)
  subprocess.run([str(folder/'Dump.exe'),str(launcher),str(folder),str(newbase)],check=True)
  compiled={int(p.stem,16):p.read_bytes() for p in folder.glob('*.bin')}
 delta=newbase-B
 for key in ('base','data','counts','lists','group_counts','groups','pending','stamp'):M[key]+=delta
 M['blocks']={k:v+delta for k,v in M['blocks'].items()}
 for h in M['hooks']:h['target']+=delta
 B=M['base'];D=M['data']
P=pefile.PE(r'C:\Users\seo\Downloads\armaggeddon\armaggeddon\Armageddon.exe')
K=Ks(KS_ARCH_X86,KS_MODE_32)
STACK,RETURN,MANAGER,UNITS,DEFS=0x400f000,0x4001000,0x3000000,0x3100000,0x3e00000
checks=0

def w(u,a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
def r(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
def asm(u,a,s):u.mem_write(a,bytes(K.asm(s,a)[0]))
def run(u,a,b,count=2000000):
 u.emu_start(a,b,count=count)
 assert u.reg_read(UC_X86_REG_EIP)==b,hex(u.reg_read(UC_X86_REG_EIP))
def call(u,name,args):
 u.reg_write(UC_X86_REG_ESP,STACK);u.mem_write(STACK,struct.pack('<'+'I'*(len(args)+1),RETURN,*args));run(u,M['blocks'][name],RETURN)
 assert u.reg_read(UC_X86_REG_ESP)==STACK+(12 if name in ('terrain_visibility','observer_visibility') else 4)

def fresh(n=65,player=1,relocated=0):
 u=Uc(UC_ARCH_X86,UC_MODE_32)
 u.mem_map(0x400000,P.OPTIONAL_HEADER.SizeOfImage)
 for s in P.sections:u.mem_write(0x400000+s.VirtualAddress,s.get_data())
 u.mem_map(0x3000000,0x1000000);u.mem_map(0x4000000,0x100000)
 u.mem_map(0x233a000,4096) if B!=0x2340000 else u.mem_map(0x233a000,4096);u.mem_map(B,M['size']);u.mem_write(B,compiled[B] if compiled else Path('.tools/selection-runtime.bin').read_bytes())
 for h in M['hooks']:
  before=bytes.fromhex(h['before']);assert bytes(u.mem_read(h['site'],len(before)))==before,hex(h['site'])
  u.mem_write(h['site'],bytes([h['opcode']])+struct.pack('<i',h['target']-h['site']-5)+b'\x90'*(len(before)-5))
  if compiled:assert bytes(u.mem_read(h['site'],len(before)))==compiled[h['site']]
 w(u,0x504a10,MANAGER);w(u,MANAGER+4,n);u.mem_write(0x4e7270,bytes([player]));u.mem_write(0x504f48,b'\4')
 u.mem_write(MANAGER+0x7218,b'\xff'*(9*64))
 for i in range(n):
  unit=UNITS+i*0x1400;w(u,MANAGER+8+i*4,unit);w(u,unit+8,DEFS)
  u.mem_write(unit+12,struct.pack('<HH',1,i));u.mem_write(unit+0x3c,bytes([player]));u.mem_write(unit+0x13b8,b'\1')
  w(u,unit+20,100+i%10*20);w(u,unit+24,100+i//10*20)
 u.mem_write(DEFS+0x23d,b'\1')
 w(u,STACK,RETURN);u.reg_write(UC_X86_REG_ESP,STACK)
 return u

def selection(u,p):
 c=r(u,M['counts']+p*4)
 return list(struct.unpack('<'+'H'*c,u.mem_read(M['lists']+p*4096,c*2)))

# Coordinate setter entry diagnostics must reproduce the original prologue exactly.
for site in (0x43f550,0x43f590):
 for enabled,frozen,multi in ((1,0,1),(0,0,1),(1,1,1),(1,0,0)):
  outcomes=[]
  for patched in (False,True):
   u=fresh(1);w(u,B+0x80000+28,enabled);w(u,B+0x80000+12,frozen);w(u,B+0x80000+20,3);w(u,0x513ed4,multi);w(u,0x503c6c,21803)
   if not patched:u.mem_write(site,bytes.fromhex('83ec10568bf1'))
   w(u,STACK,0x4423d6);w(u,STACK+4,1931);u.reg_write(UC_X86_REG_ECX,UNITS);u.reg_write(UC_X86_REG_ESI,0x12345678);u.reg_write(UC_X86_REG_EFLAGS,0x602)
   original=bytes(u.mem_read(UNITS,0x1400));run(u,site,site+6)
   outcomes.append(([u.reg_read(reg) for reg in (UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP,UC_X86_REG_ESP,UC_X86_REG_EFLAGS)],bytes(u.mem_read(STACK-20,28))))
   assert bytes(u.mem_read(UNITS,0x1400))==original
   if patched:
    t=B+0x5d5000;expected=enabled and not frozen and multi
    assert r(u,t+4)==(1 if expected else 0)
    if expected:
     o=t+4096+128
     assert r(u,o)==r(u,o+124)==1 and r(u,o+4)==21803 and r(u,o+8)==3
     assert r(u,o+12)==0 and r(u,o+16)==site and r(u,o+20)==1931 and r(u,o+96)==0x4423d6
  assert outcomes[0]==outcomes[1],(site,enabled,frozen,multi)
print('PASS position setter installed JMP: original stack/registers/flags, readonly unit state, disabled/frozen/single-player guards')

# Resource-only minimap bypass, independent of owner and visibility. Ordinary
# entities still reach the original fog query; no entity state is mutated.
for kind in (0,1,0x100,0x200,0x2ff,0x300,0x301,0x302,0x303,0x304,0x305,0x306):
 for alive in (0,1):
  u=fresh(1);u.mem_write(UNITS+12,struct.pack('<H',kind));u.mem_write(UNITS+0x13b8,bytes([alive]));u.mem_write(UNITS+0x3c,b'\x09')
  u.reg_write(UC_X86_REG_EBX,UNITS);u.reg_write(UC_X86_REG_EAX,0x12345678);u.reg_write(UC_X86_REG_ECX,0x87654321)
  u.reg_write(UC_X86_REG_EFLAGS,0x202);before=bytes(u.mem_read(UNITS,0x1400))
  reveal=alive and 0x300<=kind<=0x306
  run(u,0x4a621f,0x4a63ab if reveal else 0x4a6228)
  assert u.reg_read(UC_X86_REG_ESP)==STACK and u.reg_read(UC_X86_REG_EFLAGS)==0x202
  assert bytes(u.mem_read(UNITS,0x1400))==before
  if reveal:assert u.reg_read(UC_X86_REG_EAX)==0x12345678 and u.reg_read(UC_X86_REG_ECX)==0x87654321
  else:assert u.reg_read(UC_X86_REG_EAX)==100
print('PASS minimap resource-only visibility: all six ore types; ordinary entities unchanged; no simulation writes')

for filename in (b'wav/weapon/earth/digger.wav',b'wav\\weapon\\earth\\DIGGER.WAV',b'wav/weapon/elca/vibewave.wav',b'wav/weapon/ead/ec00.wav',b'other.wav',b'digger.wav.backup',b'SAndC/UWSelect118_0.wav'):
 for percent in (0,25,50,100):
  u=fresh(1);w(u,B+0x76108,percent);w(u,STACK+0x14,7);w(u,STACK+0x1c,127)
  w(u,0x2231f08+7*20,DEFS);u.mem_write(DEFS,filename+b'\0')
  u.reg_write(UC_X86_REG_EAX,12);u.reg_write(UC_X86_REG_EDX,34);u.reg_write(UC_X86_REG_EBX,56);u.reg_write(UC_X86_REG_EFLAGS,0x202)
  run(u,0x4bc147,0x4bc14c)
  expected=127*percent//100 if filename.replace(b'\\',b'/').lower().split(b'/')[-1] in (b'digger.wav',b'vibewave.wav',b'ec00.wav') else 127
  assert r(u,STACK-4)==expected and u.reg_read(UC_X86_REG_ESP)==STACK-4
  assert [u.reg_read(rg) for rg in (UC_X86_REG_EAX,UC_X86_REG_EDX,UC_X86_REG_EBX,UC_X86_REG_EFLAGS)]==[12,34,56,0x202]
print('PASS harvesting volume: mute/25/50/100 percent; path case/separators; unrelated sounds untouched')

# World display routing must not reveal unknown enemies. Resource-only bypass
# covers all three native draw passes and both minimap checks.
for site,visible,hidden in [(0x448e80,0x448f3d,0x449d5e),(0x449e3a,0x449ed2,0x44a027),(0x44a101,0x44a1a1,0x44a362)]:
 for kind,owner in [(0x300,9),(0x303,9),(0x306,9),(0x22a,2),(0x20f,2),(0x22a,1),(0x300,2)]:
  for sight in (0,1,2):
   u=fresh(1);u.mem_write(UNITS+12,struct.pack('<H',kind));u.mem_write(UNITS+0x3c,bytes([owner]))
   u.reg_write(UC_X86_REG_ESI,MANAGER);u.reg_write(UC_X86_REG_EBX,DEFS);u.reg_write(UC_X86_REG_EDI,DEFS);w(u,DEFS,0)
   asm(u,0x42b230,f'mov eax,{sight}; ret 8')
   resource=0x300<=kind<=0x306 and owner==9
   target=visible if resource else hidden if sight==2 and owner!=1 else site+5
   before=bytes(u.mem_read(UNITS,0x1400));run(u,site,target)
   assert u.reg_read(UC_X86_REG_ESP)==STACK+8 and bytes(u.mem_read(UNITS,0x1400))==before
for kind in (0x300,0x306,0x22a):
 u=fresh(1);u.mem_write(UNITS+12,struct.pack('<H',kind));u.mem_write(UNITS+0x3c,b'\x09');u.reg_write(UC_X86_REG_EDI,UNITS)
 asm(u,0x42b230,'mov eax,2; ret 8');run(u,0x4a6744,0x4a6749)
 assert u.reg_read(UC_X86_REG_EAX)==(0 if 0x300<=kind<=0x306 else 2)
print('PASS resource visibility: ore/hydrogen in three world passes and late minimap gate; unknown enemies hidden, own units preserved')
# Replay observer: every unit is drawn regardless of the recorded player's fog;
# a live game (mailbox state != 2) keeps hiding unseen enemies.
for site,visible,hidden in [(0x448e80,0x448f3d,0x449d5e),(0x449e3a,0x449ed2,0x44a027),(0x44a101,0x44a1a1,0x44a362)]:
 for mode in (0,2):
  for owner in (1,2):
   u=fresh(1);w(u,0x4f75ec,1024);w(u,0x233a000,mode);u.mem_write(UNITS+12,struct.pack('<H',0x22a));u.mem_write(UNITS+0x3c,bytes([owner]))
   u.reg_write(UC_X86_REG_ESI,MANAGER);u.reg_write(UC_X86_REG_EBX,DEFS);u.reg_write(UC_X86_REG_EDI,DEFS);w(u,DEFS,0)
   asm(u,0x42b230,'mov eax,2; ret 8')
   target=hidden if (mode!=2 and owner!=1) else site+5
   run(u,site,target);assert u.reg_read(UC_X86_REG_ESP)==STACK+8,(site,mode,owner)
print('PASS replay observer fog: unseen enemy units drawn during playback, still hidden in live games')

for player in (1,4,8):
 for n in (0,1,16,17,65,1700):
  u=fresh(n,player);call(u,'select',(player,13));assert selection(u,player)==list(range(n))
  assert list(u.mem_read(MANAGER+0x1a98,n))==[1]*n
  if player==1:assert r(u,0x4fa65c)==(0 if n else 0xffffffff)
  assert struct.unpack('<16i',u.mem_read(MANAGER+0x7218+player*64,64))==tuple(list(range(min(n,16)))+[-1]*(16-min(n,16)))
  checks+=1
u=fresh(90)
for i in range(90):
 unit=UNITS+i*0x1400
 u.mem_write(unit+12,struct.pack('<H',(0x12,0x113,0x21c)[i%3]))
 if i%4==0:u.mem_write(unit+0x464,b'\x2d')
 elif i%3==0:u.mem_write(unit+0x464,b'\x05')
 if i%7==0:u.mem_write(unit+0x3c,b'\2')
 if i%11==0:u.mem_write(unit+0x13b8,b'\0')
call(u,'select',(1,14));assert selection(u,1)==[i for i in range(90) if i%4 and i%7 and i%11];checks+=1
for key,mode in ((0x3c,13),(0x34,14)):
 u=fresh();u.reg_write(UC_X86_REG_ESI,key-1);u.reg_write(UC_X86_REG_ECX,1);u.reg_write(UC_X86_REG_EAX,64)
 run(u,0x453799,0x4537be);assert u.mem_read(0x52f553,1)==bytes([mode]);checks+=1
 for address,size in ((0x51a8a0,4),(0x513ec8,1),(0x5030c9,1),(0x5304dd,1),(0x507b34,4)):
  u=fresh();u.mem_write(address,b'\1'+b'\0'*(size-1));u.reg_write(UC_X86_REG_ESI,key-1);u.reg_write(UC_X86_REG_ECX,1);u.reg_write(UC_X86_REG_EAX,64)
  run(u,0x453799,0x4537a3);assert u.mem_read(0x52f553,1)!=bytes([mode]);checks+=1
# Run the actual frame hook and then wrappers, not the stand-alone batching model.
for name,handler in (('right',0x408390),('order',0x420410)):
 u=fresh();u.mem_write(0x52f553,b'\x0d');u.reg_write(UC_X86_REG_EBX,1);run(u,0x48bc82,0x48bc8b)
 assert len(selection(u,1))==65 and u.mem_read(0x52f553,1)==b'\x0d'
 packet=bytes(u.mem_read(0x52f550,64));observed=[]
 def dispatch(uc,a,s,x):
  assert bytes(uc.mem_read(0x52f550,64))==packet
  observed.extend(i for i in struct.unpack('<16i',uc.mem_read(MANAGER+0x7258,64)) if i>=0)
  uc.mem_write(0x52f550,b'\xee'*64);w(uc,0x51bc54,0)
 asm(u,handler,'ret');u.hook_add(UC_HOOK_CODE,dispatch,begin=handler,end=handler)
 call(u,name,(1,));assert observed==list(range(65)),observed
 assert bytes(u.mem_read(0x52f550,64))==packet;checks+=1
# Real native rectangle selector; substitute only sprite-bound and Win32 SetRect leaves.
u=fresh(65)
asm(u,0x43f610,'mov eax,[esp+4]; mov dword ptr [eax],-8; mov dword ptr [eax+4],-8; mov dword ptr [eax+8],8; mov dword ptr [eax+12],8; ret 8')
w(u,0x4cb254,RETURN+0x100)
asm(u,RETURN+0x100,'mov eax,[esp+4]; mov edx,[esp+8]; mov [eax],edx; mov edx,[esp+12]; mov [eax+4],edx; mov edx,[esp+16]; mov [eax+8],edx; mov edx,[esp+20]; mov [eax+12],edx; ret 20')
rect=DEFS+0x1000;u.mem_write(rect,struct.pack('<4i',50,50,400,400))
u.reg_write(UC_X86_REG_ECX,MANAGER)
u.mem_write(STACK,struct.pack('<5I',RETURN,1,1,rect,1));run(u,0x44dbd0,RETURN)
assert selection(u,1)==list(range(65)),selection(u,1)
assert u.reg_read(UC_X86_REG_ESP)==STACK+20;checks+=1
# Original group store/recall path plus complete sidecar list.
for mode in (1,0):
 u.mem_write(0x52f553,b'\3');u.mem_write(0x52f554,bytes([mode]));call(u,'group',(1,))
 if mode==1:
  w(u,M['counts']+4,0);u.mem_write(MANAGER+0x7258,b'\xff'*64)
assert selection(u,1)==list(range(65));checks+=1
# Summary is emitted after the transport cases below.
# print('PASS',checks,'installed-hook scenarios: F2/period guards, actual worker classifier, all selection flags, native rectangle >16, native control groups and frame-to-batch dispatch. Native order effects remain a separate gameplay check.')

# Real game's DirectPlay command codec, two separate peers and replay packet.
def native(u,address,args):
 u.reg_write(UC_X86_REG_ESP,STACK);u.mem_write(STACK,struct.pack('<'+'I'*(len(args)+1),RETURN,*args));run(u,address,RETURN)
for mode in (13,14):
 sender=fresh(65);sender.mem_write(0x52f553,bytes([mode]));native(sender,0x4851c0,(0x52f550,DEFS+0x2000))
 wire=bytes(sender.mem_read(DEFS+0x2000,10))
 for peer in range(3):
  receiver=fresh(65)
  if mode==14:
   for i in range(65):receiver.mem_write(UNITS+i*0x1400+12,struct.pack('<H',0x12))
  receiver.mem_write(DEFS+0x2000,wire);native(receiver,0x485280,(0,DEFS+0x2000,0x52f550))
  assert receiver.mem_read(0x52f553,1)==bytes([mode])
  recorded=bytes(receiver.mem_read(0x52f550,64))
  receiver.reg_write(UC_X86_REG_EBX,1);run(receiver,0x48bc82,0x48bc8b)
  assert selection(receiver,1)==list(range(65))
  assert bytes(receiver.mem_read(0x52f550,64))==recorded
  checks+=1
# Selection rectangle: original wire writer and original receive decoder retain
# the extended marker (4095), then the installed simulation hook reconstructs it.
u=fresh(65);w(u,M['pending'],1);u.mem_write(M['pending']+4,struct.pack('<4i',50,50,400,400))
run(u,M['blocks']['wire'],0x4079bc)
native(u,0x474120,(0x51be70,DEFS+0x2000,DEFS+0x3000))
length=struct.unpack('<H',u.mem_read(DEFS+0x3000,2))[0];wire=bytes(u.mem_read(DEFS+0x2000,length))
assert wire[:2]==bytes([0x33,16]) and length==26
u.mem_write(0x50d298,wire);w(u,0x50d294,0);u.reg_write(UC_X86_REG_EBP,0);u.reg_write(UC_X86_REG_ECX,0x33);u.reg_write(UC_X86_REG_ESP,STACK);u.mem_write(STACK+0x12,b'\0')
run(u,0x473c7a,0x47404d)
packet=bytes(u.mem_read(0x51c110,64));assert struct.unpack_from('<2H',packet,30)==(4095,0xa31)
u.mem_write(0x52f550,packet)
asm(u,0x43f610,'mov eax,[esp+4]; mov dword ptr [eax],-8; mov dword ptr [eax+4],-8; mov dword ptr [eax+8],8; mov dword ptr [eax+12],8; ret 8')
w(u,0x4cb254,RETURN+0x100)
asm(u,RETURN+0x100,'mov eax,[esp+4]; mov edx,[esp+8]; mov [eax],edx; mov edx,[esp+12]; mov [eax+4],edx; mov edx,[esp+16]; mov [eax+8],edx; mov edx,[esp+20]; mov [eax+12],edx; ret 20')
u.reg_write(UC_X86_REG_EBX,1);run(u,0x48bc82,0x48bc8b);assert selection(u,1)==list(range(65));checks+=1
# Dead units and units changing ownership cannot remain command targets.
u=fresh(65);call(u,'select',(1,13));u.mem_write(UNITS+3*0x1400+0x13b8,b'\0');w(u,MANAGER+0x7258+3*4,-1)
u.mem_write(UNITS+4*0x1400+0x3c,b'\2');u.mem_write(0x52f553,b'\xff');u.reg_write(UC_X86_REG_EBX,1)
run(u,0x48bc82,0x48bc8b);assert selection(u,1)==[i for i in range(65) if i not in (3,4)];checks+=1
# A new match must not inherit the previous match's large control groups.
w(u,0x503c6c,100);call(u,'reset',());w(u,0x503c6c,1);call(u,'reset',());assert selection(u,1)==[];checks+=1
if compiled:assert compiled[0x4d96e0]==bytes.fromhex('d65f12bfb6aa8347b154d17783ab6831')
print('PASS',checks,'installed-hook/transport scenarios. Actual x86 DirectPlay encode/decode, independent peer selection and replay packet retention; live network and native order effects are separate checks.')

# A later native input update may overwrite the immediate HUD state.
# Refresh is deferred until the render hook, and must repair that overwrite.
u=fresh(65);w(u,0x50313c,DEFS);observed=[]
asm(u,0x40f630,'ret')
commands=[]
asm(u,0x425ee0,'ret')
def command_panel(uc,a,size,data):
 sp=uc.reg_read(UC_X86_REG_ESP);commands.append((r(uc,sp+4),r(uc,sp+8)))
u.hook_add(UC_HOOK_CODE,command_panel,begin=0x425ee0,end=0x425ee0)
def panel(uc,a,size,data):observed.append(r(uc,uc.reg_read(UC_X86_REG_ESP)+4))
u.hook_add(UC_HOOK_CODE,panel,begin=0x40f630,end=0x40f630)
call(u,'select',(1,13));assert observed==[3] and commands==[(0,1)]
observed.clear();commands.clear()
u.mem_write(MANAGER+0x7498,b'\xff'*64);w(u,0x4fa65c,-1)
asm(u,0x4a8720,'ret')
u.reg_write(UC_X86_REG_ESP,STACK);run(u,M['blocks']['hud'],0x4a6038)
assert observed==[3] and commands==[(0,1)] and r(u,0x4fa65c)==0
assert bytes(u.mem_read(MANAGER+0x7498,64))==bytes(u.mem_read(MANAGER+0x7258,64))
# No repeated panel resets on subsequent draws.
u.reg_write(UC_X86_REG_ESP,STACK);run(u,M['blocks']['hud'],0x4a6038);assert observed==[3]
print('PASS deferred command HUD repairs overwritten native selection before render, exactly once')

if compiled:
 # Only terrain shading branches change; unit visibility routine is untouched.
 for address,expected in ((0x4a5274,'eb1f'),(0x4a5380,'eb19'),(0x4a52a6,'3c007450'),(0x4a53a8,'3c00744a')):
  assert compiled[address]==bytes.fromhex(expected)
 for address,target in ((0x4a52a6,0x4a52fa),(0x4a53a8,0x4a53f6)):
  for visibility in (0,1,2):
   u=fresh(0);u.mem_write(address,compiled[address]);u.reg_write(UC_X86_REG_EAX,visibility)
   run(u,address,target if visibility==0 else address+4)
 print('PASS minimap terrain: visible unchanged; explored/unexplored dimmed; only terrain render sites patched')

# Renderer-only mapping must preserve visible/explored values and map unknown
# to explored shading without writing the authoritative visibility source.
for visibility in (0,1,2):
 u=fresh(0);asm(u,0x42b230,'mov eax,'+str(visibility)+'; ret 8')
 call(u,'terrain_visibility',(15,20));assert u.reg_read(UC_X86_REG_EAX)==(1 if visibility==2 else visibility)
 assert u.reg_read(UC_X86_REG_ESP)==STACK+12
print('PASS world terrain preview: unknown -> dim fog, existing sight levels preserved; wrapper stack balanced')

# Execute the complete original viewport fog-cache builder, including the
# edge/corner helper which previously restored opaque black (40) tiles.
u=fresh(0);asm(u,0x42b230,'mov eax,2; ret 8')
u.reg_write(UC_X86_REG_ECX,UNITS);u.reg_write(UC_X86_REG_ESP,STACK)
u.mem_write(STACK,struct.pack('<3I',RETURN,0,0));run(u,0x42b4a0,RETURN)
for x in range(16):
 for y in range(25):
  offset=UNITS+0x2418a+(x+y*264)*2
  assert struct.unpack('<H',u.mem_read(offset,2))[0]==20,(x,y,bytes(u.mem_read(offset,2)))
print('PASS complete native fog-cache pipeline: 400 unexplored viewport cells retain dim terrain (20), no opaque black (40)')

for replayMode in (0,1,2):
 u=fresh(0);w(u,0x4f75ec,1024);w(u,0x233a000,replayMode);u.mem_write(0x503bcd,b'\0')
 call(u,'observer_view',());assert u.reg_read(UC_X86_REG_EAX)&255==0
 assert u.mem_read(0x503bcd,1)==b'\0'
print('PASS observer view enabled only during playback; authoritative global sight flag unchanged')

for mode,hidden in ((0,1),(1,1),(2,0),(2,1)):
 u=fresh(0);w(u,0x4f75ec,1024);w(u,0x233a000,mode);w(u,B+0x76704,hidden)
 run(u,M['blocks']['replay_hud_gate'],0x4a61af if mode==2 and hidden else 0x4a49f4)
print('PASS replay HUD toggle: playback-only hide branch; normal play and recording retain HUD')

# Render phase is never replaced by the observer visibility policy.
for phase in (0,1,2,3,4):
 u=fresh(0);w(u,0x4f75ec,1024);w(u,0x233a000,2);u.mem_write(0x503bcd,bytes([phase]));call(u,'observer_view',());assert u.reg_read(UC_X86_REG_EAX)&255==phase
u=fresh(0);w(u,0x4f75ec,1024);w(u,0x233a000,2);call(u,'observer_visibility',(20,30));assert u.reg_read(UC_X86_REG_EAX)==0
call(u,'replay_voice',(123,));assert u.reg_read(UC_X86_REG_EAX)==0
print('PASS observer regression: all five render phases preserved; display visibility bypass and voice suppression isolated to playback')

# Resource layout rollback: no resource text call sites are intercepted.
resource_sites=(0x4a58f1,0x4a5929,0x4a5989,0x4a59c1,0x4a5a5c,0x4a5a94,0x4a5bb7,0x4a5bf1)
assert not any(h['site'] in resource_sites for h in M['hooks'])
print('PASS resource rollback: original HD resource text call sites retained')

# First rendered frame centers once on a living local building; never on enemy.
u=fresh(3);w(u,UNITS+0x30,1);u.mem_write(UNITS+60,b'\x02');w(u,UNITS+0x1400+0x30,1);w(u,UNITS+0x1400+20,3200);w(u,UNITS+0x1400+24,1600);w(u,0x503c6c,5)
call(u,'resource_text',[]);assert (r(u,0x5812e8),r(u,0x5812ec))==(84,41)
w(u,0x5812e8,50);w(u,0x503c6c,10);call(u,'resource_text',[]);assert r(u,0x5812e8)==50
u.mem_write(0x504f48,b'\x02');call(u,'resource_text',[]);u.mem_write(0x504f48,b'\x04');call(u,'resource_text',[]);assert r(u,0x5812e8)==84
# Common mapping, race override, chat guard, identity fallback.
for kind,common,race,chat,expected in [(1,31,0,0,30),(0x101,31,32,0,31),(0x201,0,0,0,15),(1,31,0,1,15)]:
 u=fresh(1);u.mem_write(UNITS+12,struct.pack('<H',kind));u.mem_write(B+0x77000+15,bytes([common]));u.mem_write(B+0x77000+((kind>>8)+1)*256+15,bytes([race]));u.mem_write(0x513ec8,bytes([chat]));u.reg_write(UC_X86_REG_ESI,15);call(u,'hotkey_map',[]);assert u.reg_read(UC_X86_REG_ESI)==expected
# Resource markers override black neutral owner colour only.
for kind,owner,expected in [(0x300,9,0xf0),(0x306,9,0xf0),(0x22a,2,7),(0x300,2,7)]:
 u=fresh(1);u.mem_write(UNITS+12,struct.pack('<H',kind));u.mem_write(UNITS+60,bytes([owner]));u.reg_write(UC_X86_REG_EDI,UNITS);w(u,STACK+12,7);run(u,M['blocks']['minimap_resource_color'],0x48f230);assert r(u,STACK+12)==expected
print('PASS start camera once-per-match/local ownership; common/race hotkeys/chat guard; resource marker colours')
# BGM fallback preserves authored paths and the original cdecl argument layout.
for empty in (False,True):
 u=fresh(1);u.mem_write(0x504b68,b'\0' if empty else b'BGM\\Menu.wav\0');w(u,STACK+4,0x504b68);run(u,M['blocks']['multiplayer_music'],0x4bc350);assert r(u,STACK+4)==(B+0x76d00 if empty else 0x504b68);assert u.reg_read(UC_X86_REG_ESP)==STACK
if compiled:
 expected=b'BGM\\04-into the war.wav\0'
 assert compiled[B+0x76d00]==expected
 assert (Path(r'C:\Users\seo\Downloads\armaggeddon\armaggeddon')/expected[:-1].decode('ascii')).is_file()
print('PASS BGM fallback pointer, exact installed NUL-terminated path and existing music asset; native cdecl frame retained')

# Native command-boundary diagnostics: bounded ring, freeze, reset, and no writes
# to authoritative unit/command/RNG state. Diagnostic memory is outside replay data.
u=fresh(3);t=B+0x80000;ring=B+0x81000
w(u,t+28,1);w(u,0x513ed4,1);w(u,0x4f8a10,0xffffffff);w(u,0x503c6c,100);u.mem_write(0x581158,b'\x17');u.mem_write(0x52f210,bytes(range(256))*5+bytes(range(128)))
beforeUnits=bytes(u.mem_read(UNITS,3*0x1400));beforeCommands=bytes(u.mem_read(0x52f210,1408));beforeRng=bytes(u.mem_read(0x581158,4))
regs=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
for i,reg in enumerate(regs):u.reg_write(reg,0x11110000+i)
saved=[u.reg_read(reg) for reg in regs];u.reg_write(UC_X86_REG_EFLAGS,0x202)
call(u,'sync_trace',[]);assert [u.reg_read(reg) for reg in regs]==saved and u.reg_read(UC_X86_REG_EFLAGS)==0x202
assert r(u,t)==0x31525453 and r(u,t+4)==1 and r(u,t+20)==1
slot=ring+2048;assert r(u,slot)==r(u,slot+76)==1 and r(u,slot+4)==100 and r(u,slot+8)==23 and r(u,slot+84)==0xffffffff
assert bytes(u.mem_read(slot+128,1408))==beforeCommands
detail=B+0x281000+4096+54464
assert r(u,B+0x281000)==0x31544e55 and r(u,detail)==r(u,detail+20)==1 and r(u,detail+4)==100 and r(u,detail+12)==3
assert r(u,detail+64)==0 and r(u,detail+64+8)==r(u,UNITS+20) and r(u,detail+64+16)==r(u,UNITS+0x9c4)
assert bytes(u.mem_read(UNITS,3*0x1400))==beforeUnits and bytes(u.mem_read(0x581158,4))==beforeRng
h=r(u,slot+24);call(u,'sync_trace',[]);assert r(u,t+4)==1
w(u,0x503c6c,101);call(u,'sync_trace',[]);assert r(u,ring+4096+24)==h
w(u,UNITS+20,999);w(u,0x503c6c,102);call(u,'sync_trace',[]);assert r(u,ring+6144+24)!=h
oldOrder=r(u,ring+6144+92);w(u,UNITS+0x414,88);u.mem_write(0x51a8e4,b'\1');w(u,0x503c6c,103);call(u,'sync_trace',[]);assert r(u,t+12)==1 and r(u,t+16)==103 and r(u,t+4)==4 and r(u,ring+8192+4)==103 and r(u,ring+8192+20)==1
assert r(u,ring+8192+92)!=oldOrder
failedDetail=B+0x281000+4096+4*54464
assert r(u,failedDetail+4)==103 and r(u,failedDetail+64+20)==88
w(u,0x503c6c,200);call(u,'sync_trace',[]);assert r(u,t+4)==4
u.mem_write(0x51a8e4,b'\0');w(u,0x503c6c,1);call(u,'sync_trace',[]);assert r(u,t+20)==2 and r(u,t+4)==1 and r(u,t+12)==0
for tick in range(2,1030):w(u,0x503c6c,tick);call(u,'sync_trace',[])
assert r(u,t+4)==1029 and r(u,ring+5*2048)==1029
assert r(u,B+0x281000+4096+5*54464)==1029 and r(u,B+0x281000+4096+5*54464+8)==2
w(u,t+28,0);w(u,0x503c6c,2000);call(u,'sync_trace',[]);assert r(u,t+4)==1029
print('PASS native sync trace: frame/command/RNG/hash capture, registers/flags, same-clock deduplication, first-error freeze, new-match reset, 1024-slot wrap and diagnostics-off')
# Execute both original control-flow branches: multiplayer jumps over 454487.
# The shared barrier at 45448c must still commit multiplayer records.
for multi in (0,1):
 u=fresh(1);w(u,B+0x80000+28,1);w(u,0x513ed4,multi);w(u,0x4f8a10,0xffffffff);w(u,0x503c6c,7);u.reg_write(UC_X86_REG_EBP,1);u.reg_write(UC_X86_REG_EBX,0);u.reg_write(UC_X86_REG_EAX,1)
 asm(u,0x482cf0,'ret');asm(u,0x408300,'ret');asm(u,0x429260,'ret')
 run(u,0x45445e,0x454491);assert r(u,B+0x80004)==multi and r(u,B+0x80024)==1 and u.reg_read(UC_X86_REG_EAX)==0x22260 and u.reg_read(UC_X86_REG_ESP)==STACK
# Read CRT TLS state without invoking rand()/TLS APIs or changing the seed.
u=fresh(1);u.mem_map(0,4096);w(u,0xe10+3*4,DEFS);w(u,DEFS+20,0x12345678);w(u,0x4f8a10,3);w(u,B+0x80000+28,1);w(u,0x513ed4,1);w(u,0x503c6c,7)
call(u,'sync_trace',[]);assert r(u,B+0x81000+2048+84)==0x12345678 and r(u,DEFS+20)==0x12345678
print('PASS installed per-tick command barrier and read-only CRT TLS seed')

# New skirmish initialization: closed/open slots stay absent, computers receive
# the flag consumed by the native build-plan scheduler, local player is retained.
for local in (1,4):
 for kinds in ([3,2,0,1,2,0,0,0],[3,0,0,0,0,0,0,0]):
  u=fresh(0,local);u.mem_write(0x504f72,b'\1');u.mem_write(0x513c64,bytes(kinds));u.mem_write(0x513c80,b'\2'*8);u.mem_write(MANAGER+0x240f1,b'\1'*8)
  run(u,0x402bbe,0x402bc3)
  for p,kind in enumerate(kinds,1):
   active=1 if p==local or kind==3 else (2 if kind==2 else 0)
   ai=1 if kind==2 and p!=local else 0
   assert u.mem_read(0x513c7f+p,1)==bytes([active]);assert u.mem_read(MANAGER+0x240f0+p,1)==bytes([ai])
  # Real spawn gate must skip a former computer now set Closed.
  u.reg_write(UC_X86_REG_EBX,3);run(u,0x404d96,0x4051a8)
  # Native scheduler must enter only computer brains.
  calls=[]
  def ai_call(uc,a,size,data):
   if a==0x454ee0:
    calls.append(uc.reg_read(UC_X86_REG_EDI));sp=uc.reg_read(UC_X86_REG_ESP);uc.reg_write(UC_X86_REG_EIP,r(uc,sp));uc.reg_write(UC_X86_REG_ESP,sp+4)
  handle=u.hook_add(UC_HOOK_CODE,ai_call);run(u,0x48cc06,0x48cc5e);u.hook_del(handle)
  assert calls==[p for p,kind in enumerate(kinds,1) if kind==2 and p!=local]
# Campaign and multiplayer initialization retain original slot/AI state.
for multi,mode in ((1,1),(0,2),(1,2)):
 u=fresh(0);w(u,0x513ed4,multi);u.mem_write(0x504f72,bytes([mode]));u.mem_write(0x513c80,b'\2'*8);u.mem_write(MANAGER+0x240f1,b'\1'*8);run(u,0x402bbe,0x402bc3);assert u.mem_read(0x513c80,8)==b'\2'*8 and u.mem_read(MANAGER+0x240f1,8)==b'\1'*8
# Actual native worker classifier, both directions, all three races, option OFF.
for kind in (0x12,0x13,0x14,0x113,0x114,0x21c,0x21d,0x21e,0x15,0x11f,0x223):
 for enabled in (0,1):
  for key in (46,47):
   u=fresh(1);u.mem_write(UNITS+12,struct.pack('<H',kind));w(u,MANAGER+0x7218+64,0);w(u,B+0x77400,enabled);u.reg_write(UC_X86_REG_ESI,key);call(u,'hotkey_map',[])
   expected=key^1 if enabled and kind in (0x12,0x13,0x14,0x113,0x114,0x21c,0x21d,0x21e) else key
   assert u.reg_read(UC_X86_REG_ESI)==expected,(hex(kind),enabled,key)
print('PASS skirmish Closed spawn exclusion, native AI scheduler activation, campaign/multiplayer isolation, optional B/V swap for all three native worker types')

# Execute the original AI planner and its original order writer with controlled
# world queries. Covers production -> construction -> attack for all race plans.
archive=Path(r'C:\Users\seo\Downloads\armaggeddon\armaggeddon');hed=(archive/'Armageddon.HED').read_bytes()
with (archive/'Armageddon.MFP').open('rb') as archive_file:
 for entry in range(9):
  offset=struct.unpack_from('<I',hed,8+entry*72)[0];size=struct.unpack_from('<I',hed,8+entry*72+68)[0];archive_file.seek(offset);lines=archive_file.read(size).splitlines()
  first=list(map(int,lines[0][70:].split()));second=list(map(int,lines[1][70:].split()));worker,parent,race,action,qty=first;building=second[0]
  assert action==1 and second[3]==0
  u=fresh(0);brain=DEFS+0x2000;plan=DEFS+0x4000;player=2
  u.mem_write(MANAGER+0x25137+player,b'\1');w(u,brain+20,player);w(u,brain+24,4);w(u,brain+0xfc,plan);w(u,brain+0x28+(worker&255)*4,1)
  for i,row in enumerate([(race,1,worker,parent,qty),(race,0,building,0,0),(race,3,0,1,0),(race,4,0,0,0)]):u.mem_write(plan+i*20,struct.pack('<5I',*row))
  world={'stage':0}
  def ai_world(uc,a,size,data):
   result=None;args=0
   if a in (0x455830,0x455c90):result=0
   elif a==0x450cd0:
    requested=r(uc,uc.reg_read(UC_X86_REG_ESP)+8)&0xffff;args=8
    result=0 if world['stage']==0 else (255 if world['stage']==2 or requested==worker else 0)
   elif a==0x4552a0:result=1;args=4
   elif a==0x476ad0:result=0
   elif a in (0x451090,0x4510c0):result=0;args=8
   elif a==0x4295c0:result=1
   if result is not None:
    sp=uc.reg_read(UC_X86_REG_ESP);uc.reg_write(UC_X86_REG_EAX,result);uc.reg_write(UC_X86_REG_EIP,r(uc,sp));uc.reg_write(UC_X86_REG_ESP,sp+4+args)
  u.hook_add(UC_HOOK_CODE,ai_world)
  def planner():
   w(u,STACK,RETURN);u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ECX,brain);run(u,0x454ee0,RETURN);assert u.reg_read(UC_X86_REG_ESP)==STACK+4
  planner();assert u.mem_read(0x504dd8+player*16,1)==b'\1' and r(u,0x504ddc+player*16)==worker,(entry,worker,r(u,brain+28),bytes(u.mem_read(0x504dd8+player*16,12)).hex())
  world['stage']=1;planner();assert u.mem_read(0x504dd8+player*16,1)==b'\1' and r(u,0x504ddc+player*16)==building
  world['stage']=2;planner();assert u.mem_read(0x504dd8+player*16,1)==b'\2' and r(u,brain+28)==3
print('PASS original AI plans: all 9 Earth/Elca/EAD variants issue native production and construction orders, then advance to attack (world perception/affordability queries controlled)')
# Initialization trampoline preserves caller state except its displaced MOV EDX.
u=fresh(0);u.mem_write(0x504f72,b'\1');u.mem_write(0x513c64,b'\3\2\0\0\0\0\0\0')
regs=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
for i,reg in enumerate(regs):u.reg_write(reg,0x123400+i)
before=[u.reg_read(reg) for reg in regs];u.reg_write(UC_X86_REG_EFLAGS,0x246);run(u,0x402bbe,0x402bc3)
assert [u.reg_read(reg) for reg in regs]==before and u.reg_read(UC_X86_REG_EDX)==0x513ca0 and u.reg_read(UC_X86_REG_ESP)==STACK and u.reg_read(UC_X86_REG_EFLAGS)==0x246
# B/V remains unchanged for no selection, dead/enemy worker, chat and non-game UI.
for scenario in ('empty','dead','enemy','chat','menu'):
 u=fresh(1);u.mem_write(UNITS+12,struct.pack('<H',0x12));w(u,MANAGER+0x7218+64,0 if scenario!='empty' else -1);w(u,B+0x77400,1)
 if scenario=='dead':u.mem_write(UNITS+0x13b8,b'\0')
 if scenario=='enemy':u.mem_write(UNITS+60,b'\2')
 if scenario=='chat':u.mem_write(0x5030c9,b'\1')
 if scenario=='menu':u.mem_write(0x504f48,b'\2')
 u.reg_write(UC_X86_REG_ESI,46);call(u,'hotkey_map',[]);assert u.reg_read(UC_X86_REG_ESI)==46
print('PASS skirmish trampoline caller preservation; build-key context/ownership/dead-selection guards')

# Replay the actual construction crash path, with only surrounding world/own
# footprint queries controlled. Both reports request missing Earth definition 56.
def construction_machine(patched=True,target=0x38):
 u=fresh(173,2);actor=UNITS+172*0x1400;cat=DEFS+0x8000
 u.reg_write(UC_X86_REG_ESI,actor);u.reg_write(UC_X86_REG_EDI,0xffffffff);u.reg_write(UC_X86_REG_EBX,0)
 u.mem_write(actor+12,struct.pack('<HH',0x12,172));w(u,actor+0x414,target);w(u,actor+0xa4,3251);w(u,actor+0xf4,2276);w(u,actor+0x2c,1);u.mem_write(actor+0x464,b'\7');w(u,0x5049fc,cat)
 for i,v in enumerate((0xffffffff,0x11112222,0x33334444,0)):w(u,STACK+i*4,v)
 w(u,STACK+0x84,RETURN);w(u,STACK+0x88,0)
 if not patched:u.mem_write(0x438b51,bytes.fromhex(next(h['before'] for h in M['hooks'] if h['site']==0x438b51)))
 def surroundings(uc,a,size,data):
  sp=uc.reg_read(UC_X86_REG_ESP);pop=None
  if a==0x41f590:pop=4
  elif a==0x476ad0:pop=0
  elif a==0x43b280:pop=8
  elif a==0x43f5d0:
   output=r(uc,sp+4);uc.mem_write(output,struct.pack('<4i',0,0,16,16));uc.reg_write(UC_X86_REG_EAX,output);pop=8
  if pop is not None:uc.reg_write(UC_X86_REG_EIP,r(uc,sp));uc.reg_write(UC_X86_REG_ESP,sp+4+pop)
 u.hook_add(UC_HOOK_CODE,surroundings)
 return u,actor,cat
u,actor,cat=construction_machine(False)
try:run(u,0x438b51,RETURN)
except UcError:assert u.reg_read(UC_X86_REG_EIP)==0x40d941
else:raise AssertionError('Reported NULL footprint crash not reproduced')
u,actor,cat=construction_machine(True);w(u,0x503c6c,11433);w(u,B+0x80004,10);w(u,B+0x80014,1);packet=bytes(range(64));u.mem_write(0x52f510+2*64,packet)
run(u,0x438b51,RETURN);assert u.reg_read(UC_X86_REG_ESP)==STACK+0x8c
assert r(u,actor+0x414)==0xffffffff and r(u,actor+0x460)==0xffffffff and u.mem_read(actor+0x464,1)==b'\0'
e=B+0x78000;slot=e+256+128
assert r(u,e)==0x31444c42 and r(u,e+4)==1 and r(u,slot)==r(u,slot+120)==1
assert [r(u,slot+i) for i in (4,8,12,16,20,24,28,32,36)]==[11433,172,0x12,2,0x38,3251,2276,7,4]
assert bytes(u.mem_read(slot+48,64))==packet and r(u,B+0x8000c)==2 and r(u,B+0x80010)==11433
# Missing catalog/out-of-range definition/faction each follows native cancel.
for target,reason,missing in ((0x38,4,False),(0x38,3,True),(0xff,2,False),(0x438,1,False)):
 u,actor,cat=construction_machine(True,target)
 if missing:w(u,0x5049fc,0)
 run(u,0x438b51,RETURN);assert r(u,B+0x78000+256+128+36)==reason
# Normal construction keeps the original register/flag/stack behavior at resume.
for faction in range(4):
 normal=[]
 for patched in (False,True):
  u,actor,cat=construction_machine(patched,(faction<<8)|4);w(u,0x5049fc+faction*4,cat);w(u,cat+4+4*4,DEFS);u.reg_write(UC_X86_REG_EAX,0x12345678);u.reg_write(UC_X86_REG_EFLAGS,0x246)
  run(u,0x438b51,0x438b58);normal.append(([u.reg_read(reg) for reg in (UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP,UC_X86_REG_ESP)],u.reg_read(UC_X86_REG_EFLAGS),bytes(u.mem_read(actor,0x1400))))
  assert r(u,B+0x78004)==0
 assert normal[0]==normal[1]
print('PASS paired crash replay: original NULL fault at 40d941 reproduced; invalid construction cancelled with exact context/packet and trace freeze; valid construction unchanged')

# Fresh-match entry invokes music only in multiplayer and retains native call results.
for multi in (0,1):
 u=fresh(1);w(u,0x513ed4,multi);w(u,B+0x76d80,0);u.mem_write(0x504b68,b'\0')
 asm(u,0x492280,'mov eax,123; ret')
 asm(u,0x4bc350,f'inc dword ptr [{B+0x76d80}]; mov eax,456; ret')
 call(u,'match_music',[])
 assert r(u,B+0x76d80)==multi and u.reg_read(UC_X86_REG_EAX)==123
# Replay chains after the diagnostic call instead of replacing/rejecting its hook.
u=fresh(1);site=M['blocks']['trace_barrier']+5
assert bytes(u.mem_read(site,5))==bytes.fromhex('b860220200')
asm(u,B+0xf000,'mov eax,0x22260; jmp 0x454491')
asm(u,site,f'jmp {B+0xf000}')
run(u,0x45448c,0x454491);assert u.reg_read(UC_X86_REG_EAX)==0x22260
print('PASS fresh multiplayer music entry and chained diagnostic/replay barrier')

# Execute the installed CALL site with the real caller stack, not just the helper.
for multi in (0,1):
 u=fresh(1);w(u,0x513ed4,multi);w(u,B+0x76d80,0);u.mem_write(0x504b68,b'\0')
 asm(u,0x4bc350,f'inc dword ptr [{B+0x76d80}]; ret')
 w(u,STACK,0x4d5054);w(u,STACK+4,RETURN)
 assert bytes(u.mem_read(0x45348e,1))==b'\xe8'
 run(u,0x45348e,0x453493)
 assert u.reg_read(UC_X86_REG_ESP)==STACK and r(u,STACK)==0x4d5054 and r(u,B+0x76d80)==multi
 # Reproduce the former JMP wiring: RET consumes the string argument as an address.
 u=fresh(1);w(u,0x513ed4,0);w(u,STACK,0x4d5054);asm(u,0x45348e,f"jmp {M['blocks']['match_music']}")
 run(u,0x45348e,0x4d5054);assert u.reg_read(UC_X86_REG_ESP)==STACK+4
print('PASS installed new-match CALL preserves caller stack; former JMP-to-string fault reproduced')

# Hidden-state extension: enter at the actual installed JMP site, then CALL
# through trace_barrier/sync_trace/state_trace and return to original code.
def fnv(data):
 h=0x811c9dc5
 for b in data:h=((h^b)*0x1000193)&0xffffffff
 return h
for tiles_w,tiles_h in ((1,1),(5,7),(16,17),(256,256),(0,5),(257,5)):
 u=fresh(1);grid=0x3800000;w(u,0x4f9de4,grid)
 u.mem_write(grid+0xe6,struct.pack('<HH',tiles_w,tiles_h))
 width,height=tiles_w*4,tiles_h*4
 valid=0<width<=1024 and 0<height<=1024
 data=bytes((i*31+i//2048)%256 for i in range(2048*height))
 u.mem_write(grid+0x12f808,data)
 w(u,B+0x8001c,1);w(u,0x513ed4,1);w(u,0x4f8a10,0xffffffff);w(u,0x503c6c,123)
 for player in range(1,9):
  for off in (0xa8c0,0xa8e8,0x2221c):w(u,MANAGER+off+player*4,off+player)
  for addr in (0x51bc50,0x51bcf4):w(u,addr+player*4,addr+player)
  for addr in (0x4fa618,0x4f9e40):u.mem_write(addr+player*2,struct.pack('<H',player+10))
  for addr in (0x51bd48,0x51be00):u.mem_write(addr+player*8,struct.pack('<ii',-player,player*10))
  # Let the original decoder place the per-player 0x51BC28 value: packet
  # word20 high bits for player p land at 0x51BC28+(p-1)*4 (0x408300).
  packet=0x52f510+player*64;u.mem_write(packet,b'\1');u.mem_write(packet+20,struct.pack('<H',(player<<10)|5))
 asm(u,0x4080000,'call 0x408300\nnop');run(u,0x4080000,0x4080005)
 for player in range(1,9):
  assert r(u,0x51bc28+(player-1)*4)==player,player
  u.mem_write(0x4f9e40+player*2,struct.pack('<H',player+10))
 w(u,0x51bc4c,0x3c);u.mem_write(0x4fa62c,struct.pack('<H',0x206))
 u.mem_write(MANAGER+0x711a,b'\x34\x12')
 manager_before=bytes(u.mem_read(MANAGER,0x25000));global_before=bytes(u.mem_read(0x4f0000,0x40000))
 regs=[UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
 for i,reg in enumerate(regs):u.reg_write(reg,0x11220000+i)
 saved=[u.reg_read(reg) for reg in regs];u.reg_write(UC_X86_REG_EFLAGS,0x246)
 run(u,0x45448c,0x454491,count=20000000)
 assert u.reg_read(UC_X86_REG_EAX)==0x22260 and [u.reg_read(reg) for reg in regs]==saved
 assert u.reg_read(UC_X86_REG_ESP)==STACK and u.reg_read(UC_X86_REG_EFLAGS)==0x246
 slot=B+0x81000+2048;ext=slot+1536
 assert r(u,slot)==r(u,slot+76)==1 and r(u,slot+88)==1
 assert [r(u,ext+i) for i in (0,4,8,12,20,24,448,452)]==[0x31545348,2,width,height,1 if valid else 2,0x1234,0x3c,0x206]
 for player in range(1,9):
  values=struct.unpack('<4i2H6i',u.mem_read(ext+32+(player-1)*44,44))
  assert values==(0xa8c0+player,0xa8e8+player,0x2221c+player,0x51bc50+player,player+10,player+10,player,0x51bcf4+player,-player,player*10,-player,player*10),(player,values)
 if valid:
  for stripe in range(16):
   expected=fnv(b''.join(data[y*2048:y*2048+width*2] for y in range(stripe*height//16,(stripe+1)*height//16)))
   assert r(u,ext+384+stripe*4)==expected,(tiles_w,tiles_h,stripe)
 assert bytes(u.mem_read(MANAGER,0x25000))==manager_before
 assert bytes(u.mem_read(0x4f0000,0x40000))==global_before
 assert bytes(u.mem_read(grid+0x12f808,len(data)))==data
 # OFF must not dereference even a deliberately invalid map pointer.
 w(u,B+0x8001c,0);w(u,0x4f9de4,0xdead0000);w(u,0x503c6c,124)
 before=bytes(u.mem_read(B+0x81000,4096));run(u,0x45448c,0x454491)
 assert bytes(u.mem_read(B+0x81000,4096))==before
print('PASS installed hidden-state trace v2: native 0x408300 player indexing for 0x51BC28, local UI mirrors 0x51BC4C/0x4FA62C, all eight players, fixed grid pitch, 16 FNV stripes, bounds, diagnostic OFF, original registers/flags/stack/return and read-only simulation')
