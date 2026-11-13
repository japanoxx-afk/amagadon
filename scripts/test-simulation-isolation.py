"""Two independent original-x86 states; no game/launcher processes required.
Runs installed UI CALL and construction target gate, plus native resource debit.
Only UI selection/sound leaves are substituted. Not a full match/pathfinding test.
"""
import os, sys, json, struct, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'.tools'))
import pefile
from unicorn import *
from unicorn.x86_const import *
P=pefile.PE(os.environ.get('AMAGADON_GAME_EXE',r'C:\Users\seo\Downloads\armaggeddon\armaggeddon\Armageddon.exe'))
M=json.loads((ROOT/'.tools/selection-runtime.json').read_text())
compiled=None
if len(sys.argv)>1:
 launcher=Path(sys.argv[1]).resolve();newbase=0x2340000
 source='using System;using System.IO;using System.Reflection;using System.Collections.Generic;class Dump {static void Main(string[] a){foreach(var e in (Dictionary<int,byte[]>)Assembly.LoadFrom(a[0]).GetType("Amagadon.SelectionRuntime",true).GetMethod("Build").Invoke(null,new object[]{0x2340000}))File.WriteAllBytes(Path.Combine(a[1],e.Key.ToString("x8")+".bin"),e.Value);}}'
 with tempfile.TemporaryDirectory(prefix='amagadon-simulation-') as folder:
  folder=Path(folder);(folder/'Dump.cs').write_text(source)
  subprocess.run([str(Path(os.environ['WINDIR'])/'Microsoft.NET/Framework/v4.0.30319/csc.exe'),'/nologo','/platform:x86','/out:'+str(folder/'Dump.exe'),str(folder/'Dump.cs')],check=True)
  subprocess.run([str(folder/'Dump.exe'),str(launcher),str(folder)],check=True)
  compiled={int(p.stem,16):p.read_bytes() for p in folder.glob('*.bin')}
 delta=newbase-M['base'];M['base']=newbase
 for h in M['hooks']:h['target']+=delta
MAN,STACK,RET,CAT,DEF=0x3000000,0x400f000,0x4001000,0x3010000,0x3020000

def put(u,a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
def get(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
def run(u,a,end):
 u.emu_start(a,end,count=100000)
 assert u.reg_read(UC_X86_REG_EIP)==end,hex(u.reg_read(UC_X86_REG_EIP))
def fresh(local,multi,patched):
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,P.OPTIONAL_HEADER.SizeOfImage)
 for s in P.sections:u.mem_write(0x400000+s.VirtualAddress,s.get_data())
 u.mem_map(MAN,0x100000);u.mem_map(0x4000000,0x100000)
 u.mem_map(M['base'],M['size']);u.mem_write(M['base'],compiled[M['base']] if compiled else (ROOT/'.tools/selection-runtime.bin').read_bytes())
 if patched:
  for h in M['hooks']:
   original=bytes.fromhex(h['before']);assert bytes(u.mem_read(h['site'],len(original)))==original
   u.mem_write(h['site'],bytes([h['opcode']])+struct.pack('<i',h['target']-h['site']-5)+b'\x90'*(len(original)-5))
 if compiled and patched:
  for h in M['hooks']:assert bytes(u.mem_read(h['site'],len(bytes.fromhex(h['before']))))==compiled[h['site']]
 put(u,0x504a10,MAN);put(u,0x513ed4,multi);u.mem_write(0x4e7270,bytes([local]))
 # Suppress presentation only; target write happens before this leaf.
 u.mem_write(0x44e7e0,b'\x31\xc0\xc3')
 u.mem_write(0x471260,b'\xc3');u.mem_write(0x4712c0,b'\xc3')
 return u

def preview(u,p,target):
 u.mem_write(0x52f510+p*64+26,struct.pack('<H',target))
 u.mem_write(0x52f510+p*64+7,b'\x3c')
 u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_EAX,p);u.reg_write(UC_X86_REG_EDX,0x3c)
 run(u,0x407699,0x4076a0)
 assert u.reg_read(UC_X86_REG_ESP)==STACK-8
 assert get(u,0x51bc4c)==0x3c,'preview mode must remain functional'

def target_gate(u,p,target):
 # Actual native building eligibility CMP/JNE, stop before object/grid checks.
 u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ESI,target);u.reg_write(UC_X86_REG_EDI,MAN);u.reg_write(UC_X86_REG_EBP,p)
 u.emu_start(0x425299,0,count=2)
 return u.reg_read(UC_X86_REG_EIP)==0x4252a6

def debit(u,p,a,b):
 put(u,0x5049fc+4,CAT);put(u,CAT+4+4,DEF);put(u,DEF+0x240,100);put(u,DEF+0x244,50)
 put(u,MAN+0xa8c0+p*4,a);put(u,MAN+0xa8e8+p*4,b)
 u.mem_write(STACK,struct.pack('<III',RET,p,0x101));u.reg_write(UC_X86_REG_ESP,STACK)
 run(u,0x425090,RET);assert u.reg_read(UC_X86_REG_ESP)==STACK+4
 return (u.reg_read(UC_X86_REG_EAX),get(u,MAN+0xa8c0+p*4),get(u,MAN+0xa8e8+p*4))

for p in range(1,9):
 for patched in (False,True):
  left=fresh(p,1,patched);right=fresh(p%8+1,1,patched)
  for u in (left,right):put(u,MAN+0x2221c+p*4,170)
  preview(left,p,171)
  result=(target_gate(left,p,170),target_gate(right,p,170))
  assert result==((True,True) if patched else (False,True)),(p,patched,result)
  # A later synchronized setter must still set the new target on both peers.
  for u in (left,right):
   u.mem_write(STACK,struct.pack('<III',RET,p,171));u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ECX,MAN)
   run(u,0x41f530,RET);assert u.reg_read(UC_X86_REG_ESP)==STACK+12
   assert target_gate(u,p,171)
 for patched in (False,True):
  u=fresh(p,0,patched);put(u,MAN+0x2221c+p*4,170);preview(u,p,171)
  assert get(u,MAN+0x2221c+p*4)==171,'singleplayer changed'
 for a,b in ((0,0),(99,50),(100,49),(100,50),(1000,500)):
  expected=(1,a-100,b-50) if a>=100 and b>=50 else (0,a,b)
  for patched in (False,True):
   for local in (p,p%8+1):
    assert debit(fresh(local,1,patched),p,a,b)==expected
# Installed write hook: ABI, flags, and unknown caller semantics.
for multi in (0,1):
 for caller in (0x4076a0,RET):
  u=fresh(1,multi,True);put(u,STACK+16,caller);u.reg_write(UC_X86_REG_ESP,STACK)
  regs={UC_X86_REG_EAX:MAN,UC_X86_REG_ECX:1,UC_X86_REG_EDX:171,UC_X86_REG_EBX:123,UC_X86_REG_ESI:456,UC_X86_REG_EDI:789,UC_X86_REG_EBP:321}
  for reg,val in regs.items():u.reg_write(reg,val)
  u.reg_write(UC_X86_REG_EFLAGS,0x246);put(u,MAN+0x22220,170)
  run(u,0x427bb0,0x427bb7)
  assert all(u.reg_read(reg)==val for reg,val in regs.items())
  assert u.reg_read(UC_X86_REG_ESP)==STACK and u.reg_read(UC_X86_REG_EFLAGS)==0x246
  assert get(u,MAN+0x22220)==(170 if multi and caller==0x4076a0 else 171)
print('PASS: 8-player native divergence reproduction, installed fix, synchronized target changes, singleplayer preservation; 160 native resource-debit cases; hook ABI/flags/caller guards')
