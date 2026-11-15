"""Actual wire codec / multiplayer extraction / installed HUD scope regression.
Original native x86 is executed. No DirectPlay socket or renderer is emulated.
"""
import sys,os,json,struct,pathlib,tempfile,subprocess
root=pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'.tools'))
import pefile
from unicorn import *
from unicorn.x86_const import *
P=pefile.PE(os.environ.get('AMAGADON_GAME_EXE',r'C:\Users\seo\Downloads\armaggeddon\armaggeddon\Armageddon.exe'))
M=json.loads((root/'.tools/selection-runtime.json').read_text());B=0x2340000
launcher=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else 'dist/mixed-resolution-fix/AmagadonLauncher.exe').resolve()
source='''using System;using System.IO;using System.Reflection;using System.Collections.Generic;class Dump{static void Main(string[] a){foreach(var e in (Dictionary<int,byte[]>)Assembly.LoadFrom(a[0]).GetType("Amagadon.SelectionRuntime").GetMethod("Build").Invoke(null,new object[]{0x2340000}))File.WriteAllBytes(Path.Combine(a[1],e.Key.ToString("x8")+".bin"),e.Value);}}'''
with tempfile.TemporaryDirectory() as tmp:
 t=pathlib.Path(tmp);(t/'d.cs').write_text(source)
 subprocess.run([os.environ['WINDIR']+'/Microsoft.NET/Framework/v4.0.30319/csc.exe','/nologo','/platform:x86','/out:'+str(t/'d.exe'),str(t/'d.cs')],check=True)
 subprocess.run([str(t/'d.exe'),str(launcher),str(t)],check=True)
 edits={int(p.stem,16):p.read_bytes() for p in t.glob('*.bin')}
STACK=0x400f000;END=0x4001000;MANAGER=0x3000000
REGS=(UC_X86_REG_EBX,UC_X86_REG_EBP,UC_X86_REG_ESI,UC_X86_REG_EDI)
def w(u,a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
def r(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
def run(u,a,b):
 u.emu_start(a,b,count=2000000);assert u.reg_read(UC_X86_REG_EIP)==b,hex(u.reg_read(UC_X86_REG_EIP))
def call(u,a,args=()):
 u.mem_write(STACK,struct.pack('<'+'I'*(len(args)+1),END,*args));u.reg_write(UC_X86_REG_ESP,STACK)
 saved=[u.reg_read(x) for x in REGS];run(u,a,END)
 assert u.reg_read(UC_X86_REG_ESP)==STACK+4
 assert [u.reg_read(x) for x in REGS]==saved

def fresh(width,patched=True):
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,P.OPTIONAL_HEADER.SizeOfImage)
 for s in P.sections:u.mem_write(0x400000+s.VirtualAddress,s.get_data())
 u.mem_map(B,M['size']);u.mem_map(MANAGER,0x100000);u.mem_map(0x4000000,0x100000)
 for a,b in edits.items():
  if a in [h['site'] for h in M['hooks']]:
   h=next(h for h in M['hooks'] if h['site']==a);assert bytes(u.mem_read(a,len(bytes.fromhex(h['before']))))==bytes.fromhex(h['before']),hex(a)
  if patched or a>=B:u.mem_write(a,b)
 w(u,0x504a10,MANAGER);w(u,0x513ed4,1);w(u,0x4f75ec,width);w(u,0x4f75f0,768 if width==1024 else 600)
 # Native 128-tile map bounds, shifted by the installed HD recipe.
 dx,dy=(112,168) if width==1024 else (0,0)
 u.mem_write(0x4f9dd0,struct.pack('<4i',16+dx,462+dy,144+dx,590+dy));w(u,0x4f9db8,1)
 u.mem_write(0x52f290,b'\0'*64)
 return u

def encode(width,packet,patched):
 u=fresh(width,patched);u.mem_write(0x52f250,packet)
 u.reg_write(UC_X86_REG_ESP,STACK)
 if patched:
  # Installed CALL wrapper; stop at the original transmit routine entry.
  flags=0x246;u.reg_write(UC_X86_REG_EFLAGS,flags)
  run(u,0x483754,0x483ce0)
  assert u.reg_read(UC_X86_REG_ESP)==STACK-4 and r(u,STACK-4)==0x483759
  assert u.reg_read(UC_X86_REG_EFLAGS)==flags
 call(u,0x4851c0,(0x52f250,MANAGER+0x40000))
 return bytes(u.mem_read(MANAGER+0x40000,10))

def decode_scope(width,wire,p,patched):
 u=fresh(width,patched);u.mem_write(MANAGER+0x40000,wire)
 call(u,0x485280,(p,MANAGER+0x40000,0x52f510+p*64))
 slot=0x52f510+p*64
 # Exact native multiplayer ring-consumer register contract.
 u.reg_write(UC_X86_REG_EBP,slot+9);u.reg_write(UC_X86_REG_EDX,(p-1)*4)
 u.reg_write(UC_X86_REG_ESP,STACK);w(u,STACK+0x1c,0x4f9e40+p*2)
 run(u,0x483837,0x483872)
 assert r(u,0x51bc24+p*4)==2
 rect=bytes(u.mem_read(0x4f9dd0,16))
 # Actual installed CALL to native minimap coordinate preparation.
 w(u,STACK,p);u.reg_write(UC_X86_REG_ESP,STACK)
 saved=[u.reg_read(x) for x in REGS]
 run(u,0x48bc9d,0x48bca2)
 assert u.reg_read(UC_X86_REG_ESP)==STACK and saved==[u.reg_read(x) for x in REGS]
 call(u,0x4203a0,(p,))
 state=(r(u,0x51bcf4+p*4),r(u,0x51bd48+p*8),r(u,0x51bd4c+p*8))
 # Execute the actual right-command acceptance gate, not a Python substitute.
 result=[]
 def gate(uc,a,size,data):
  if a in (0x40841b,0x4096d8):result.append(a==0x40841b);uc.emu_stop()
 h=u.hook_add(UC_HOOK_CODE,gate)
 w(u,STACK,END);w(u,STACK+4,p);u.reg_write(UC_X86_REG_ESP,STACK)
 u.emu_start(0x408390,END,count=100000);u.hook_del(h);assert len(result)==1
 # Actual loop-exit detour restores the receiver UI even after a rejected command.
 u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_EBX,p);u.reg_write(UC_X86_REG_EBP,4*(p-1));u.reg_write(UC_X86_REG_ESI,slot+14)
 run(u,0x48bd9f,0x48bda6)
 assert bytes(u.mem_read(0x4f9dd0,16))==rect
 assert u.reg_read(UC_X86_REG_ESP)==STACK and u.reg_read(UC_X86_REG_EBX)==p+1
 return state,result[0]

# Commands immediately preceding the two real incident divergences; no user data.
for sx,sy,camx,camy,p,target in [(248,633,96,19,1,(3840,96)),(226,733,45,105,2,(3136,3296))]:
 packet=bytearray(64);packet[0]=4;packet[3]=255;packet[5]=camx;packet[6]=camy
 struct.pack_into('<H',packet,14,1700);struct.pack_into('<HH',packet,20,sx|(2<<10),sy)
 raw=encode(1024,bytes(packet),False)
 old=[decode_scope(wid,raw,p,False) for wid in (800,1024)]
 assert old[0][1] is False and old[1][1] is True,old
 raw=encode(1024,bytes(packet),True)
 new=[decode_scope(wid,raw,p,True) for wid in (800,1024)]
 assert new[0]==new[1] and new[0][1],new
 print('PASS incident',p,'before',old,'after',new)
# Both sender directions, all eight players, minimap boundaries and viewport.
count=0
for sender in (800,1024):
 dx,dy=(112,168) if sender==1024 else (0,0)
 for p in range(1,9):
  for sx,sy in [(17+dx,463+dy),(80+dx,520+dy),(143+dx,589+dy),(500,250),(700,400),(16+dx,462+dy),(144+dx,590+dy)]:
   packet=bytearray(64);packet[0]=4;packet[3]=255;packet[5]=20;packet[6]=20
   struct.pack_into('<HH',packet,20,sx|(2<<10),sy)
   wire=encode(sender,bytes(packet),True)
   a,b=[decode_scope(wid,wire,p,True) for wid in (800,1024)]
   assert a==b,(sender,p,sx,sy,a,b);count+=1
print('PASS mixed resolution codec + installed hooks:',count,'paired cases; original bug reproduced twice')
# Preserve all native mode/viewport/modifier fields and exact world projection.
for sender in (800,1024):
 for mode in range(4):
  for viewport in (0,1):
   for modifier in (0,2,4,6):
    packet=bytearray(64);packet[0]=1;packet[3]=255;packet[4]=modifier;packet[5]=31;packet[6]=27
    struct.pack_into('<HH',packet,20,521|(mode<<10),413|(viewport<<10))
    old=encode(sender,bytes(packet),False);new=encode(sender,bytes(packet),True)
    expected=bytearray(old)
    if sender==1024:expected[7]|=0x80
    assert new==bytes(expected)
    for wire in (old,new):
     u=fresh(800);u.mem_write(MANAGER+0x40000,wire)
     call(u,0x485280,(1,MANAGER+0x40000,0x52f550))
     assert struct.unpack('<HH',u.mem_read(0x52f560,4))==(31*32+521,27*32+413)
     assert u.mem_read(0x52f554,1)==bytes([modifier])
# Singleplayer never receives a layout marker or a temporary geometry override.
u=fresh(1024);w(u,0x513ed4,0);u.mem_write(0x52f264,struct.pack('<H',1234))
u.reg_write(UC_X86_REG_ESP,STACK);run(u,0x483754,0x483ce0)
assert bytes(u.mem_read(0x52f264,2))==struct.pack('<H',1234)
rect=bytes(u.mem_read(0x4f9dd0,16));w(u,STACK,1);u.reg_write(UC_X86_REG_ESP,STACK)
run(u,0x48bc9d,0x48bca2);assert bytes(u.mem_read(0x4f9dd0,16))==rect
print('PASS 64 native flag/codec combinations and singleplayer unchanged')

# The loop continuation must have exactly the original register/flag effects.
for initial_flags in (0x202,0x246,0x603):
 results=[]
 for patched in (False,True):
  u=fresh(1024,patched);u.reg_write(UC_X86_REG_ESP,STACK)
  for reg,value in ((UC_X86_REG_EAX,123),(UC_X86_REG_ECX,456),(UC_X86_REG_EDX,789),(UC_X86_REG_EBX,2),(UC_X86_REG_EBP,4),(UC_X86_REG_ESI,0x52f59e),(UC_X86_REG_EDI,12345)):
   u.reg_write(reg,value)
  u.reg_write(UC_X86_REG_EFLAGS,initial_flags)
  if patched:
   u.mem_write(B+0x77540,bytes(u.mem_read(0x4f9dd0,16)));w(u,B+0x77550,1)
  run(u,0x48bd9f,0x48bda6)
  results.append([u.reg_read(reg) for reg in (UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_EBP,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_ESP,UC_X86_REG_EFLAGS)])
 assert results[0]==results[1],results
print('PASS loop-exit stack/register/flags equivalence, including DF preservation')

# Full native move handler followed by 120 native unit-scheduler ticks.
# Real ARO definitions; existing fixture declares allocation/render seams.
import importlib.util
spec=importlib.util.spec_from_file_location('native',root/'scripts/test-native-scheduler.py');n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
peers=[n.RealPeer(1,800),n.RealPeer(2,1024)]
packet=bytearray(64);packet[0]=4;packet[3]=255
struct.pack_into('<H',packet,14,1700);struct.pack_into('<HH',packet,20,(138|(2<<10)),640)
wire=encode(1024,bytes(packet),True)
for peer,width in zip(peers,(800,1024)):
 u=peer.u;slot,unit=peer.create(0x12);peer.place(unit,160,200)
 # CRT thread-local storage accessor is an OS seam; run native rand itself.
 u.mem_write(0x4c2f13,b'\xb8'+struct.pack('<I',0x70c0000)+b'\xc3')
 peer.w(0x70c0000+20,1)
 # Exact USER32 SetRect semantics; no simulation result is substituted.
 rect_stub=bytes(n.m.ks.asm('mov edx,[esp+4]; mov eax,[esp+8]; mov [edx],eax; mov eax,[esp+12]; mov [edx+4],eax; mov eax,[esp+16]; mov [edx+8],eax; mov eax,[esp+20]; mov [edx+12],eax; mov eax,1; ret 20',0x70c1000)[0])
 u.mem_write(0x70c1000,rect_stub);peer.w(0x4cb254,0x70c1000)
 u.mem_write(n.m.MANAGER+0x7218+64,struct.pack('<16I',slot,*([0xffffffff]*15)))
 dx,dy=(112,168) if width==1024 else (0,0)
 u.mem_write(0x4f9dd0,struct.pack('<4i',16+dx,462+dy,144+dx,590+dy));peer.w(0x4f9db8,1)
 rect=bytes(u.mem_read(0x4f9dd0,16));u.mem_write(n.m.OUTPUT,wire)
 peer.call(0x485280,(1,n.m.OUTPUT,0x52f550))
 # Target resolution for an empty minimap location, as produced by 0x41A040.
 u.mem_write(0x52f55e,struct.pack('<H',1700))
 u.reg_write(UC_X86_REG_EBP,0x52f559);u.reg_write(UC_X86_REG_EDX,0);u.reg_write(UC_X86_REG_ESP,n.m.STACK);peer.w(n.m.STACK+0x1c,0x4f9e42)
 n.m.run(u,0x483837,0x483872)
 peer.w(n.m.STACK,1);u.reg_write(UC_X86_REG_ESP,n.m.STACK)
 n.m.run(u,0x48bc9d,0x48bca2)
 peer.call(0x4203a0,(1,))
 # Use installed command-batching CALL, including the original handler.
 peer.w(n.m.STACK,1);u.reg_write(UC_X86_REG_ESP,n.m.STACK)
 trace=[]
 def record(uc,a,size,data):
  trace.append(hex(a))
  if len(trace)>16:trace.pop(0)
 h=u.hook_add(UC_HOOK_CODE,record)
 try:n.m.run(u,0x48bd48,0x48bd4d)
 except Exception:
  print('native trace',trace);raise
 finally:u.hook_del(h)
 assert u.mem_read(unit+0x464,1)==b'\2',bytes(u.mem_read(unit+0x464,1)).hex()
 u.reg_write(UC_X86_REG_EBP,0);u.reg_write(UC_X86_REG_EBX,1);u.reg_write(UC_X86_REG_ESI,0x52f55e)
 n.m.run(u,0x48bd9f,0x48bda6)
 assert bytes(u.mem_read(0x4f9dd0,16))==rect
 peer.w(0x57e2a0,0x70a0000)
 for j in range(3):peer.w(0x70a0000+0x33a8+4*j,100)
initial=peers[0].positions()
for tick in range(1,121):
 for peer in peers:peer.scheduler_step(tick)
 n.l.compare(*peers)
assert peers[0].positions()!=initial
print('PASS real worker native right-click -> path -> 120 scheduler ticks, identical full unit/world state',peers[0].positions())
