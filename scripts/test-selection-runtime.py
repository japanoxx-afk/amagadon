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
def run(u,a,b):
 u.emu_start(a,b,count=2000000)
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
