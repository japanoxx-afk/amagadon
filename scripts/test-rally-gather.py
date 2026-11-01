"""Compare original-renderer ore rally hooks with the shipped HD implementation."""
import sys,subprocess,os,json,base64,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT/'.tools'))
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
launcher=Path(sys.argv[1]).resolve();folder=Path(sys.argv[2]);fixture=launcher.parent/'RallyGatherFixture.exe';output=launcher.parent/'rally-gather.json'
subprocess.run([str(Path(os.environ['WINDIR'])/'Microsoft.NET/Framework/v4.0.30319/csc.exe'),'/nologo','/platform:x86',f'/reference:{launcher}',f'/out:{fixture}',str(ROOT/'scripts/rally-gather-fixture.cs')],check=True)
subprocess.run([str(fixture),str(output)],check=True);edits=json.loads(output.read_text(encoding='utf-8-sig'))
def put(u,a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
def get(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
def run(hd,case):
 p=pefile.PE(str(folder/('Armageddon.HD-preview.exe' if hd else 'Armageddon.exe')))
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x4000000);u.mem_write(0x400000,p.get_memory_mapped_image())
 if not hd:
  for e in edits:u.mem_write(e['address'],base64.b64decode(e['bytes']))
 data=0x232f000 if hd else 0x1001000;hq=0x1200000;ore=0x1206000;worker=0x120c000;manager=0x1100000;sp=0x2008000
 put(u,0x504a10,manager);put(u,manager+5*4+8,ore);put(u,manager+8*4+8,worker)
 u.mem_write(hq+12,struct.pack('<HH',case.get('hq',0),7));u.mem_write(ore+12,struct.pack('<H',case.get('resource',0x300)))
 u.mem_write(ore+0x13b8,b'\x01');put(u,hq+0x1398,100);put(u,ore+0x14,100);put(u,ore+0x18,200)
 u.reg_write(UC_X86_REG_ESI,hq);u.reg_write(UC_X86_REG_EAX,200);put(u,sp+20,5);u.reg_write(UC_X86_REG_ESP,sp)
 u.emu_start(0x408730,0x408736,count=10000)
 remembered=bytes(u.mem_read(data+7*12,12));assert get(u,hq+0x139c)==200
 if case.get('scan'):u.mem_write(data+7*12,bytes(12))
 u.reg_write(UC_X86_REG_EDI,8);u.reg_write(UC_X86_REG_ESP,sp);u.reg_write(UC_X86_REG_EFLAGS,0x246)
 before={r:u.reg_read(r) for r in [UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EBP]}
 def api(u,a,size,_):
  if a==0x40a210:
   t=u.reg_read(UC_X86_REG_ESP);u.reg_write(UC_X86_REG_EAX,case.get('worker',1));u.reg_write(UC_X86_REG_EIP,get(u,t));u.reg_write(UC_X86_REG_ESP,t+4)
 u.hook_add(UC_HOOK_CODE,api);u.emu_start(0x430e49,0x430e4e,count=100000)
 assert u.reg_read(UC_X86_REG_ESP)==sp and u.reg_read(UC_X86_REG_EDI)==0xfffff793
 assert all(u.reg_read(r)==v for r,v in before.items()) and u.reg_read(UC_X86_REG_EFLAGS)==0x246
 return remembered,bytes(u.mem_read(worker+0x414,4)),bytes(u.mem_read(worker+0x464,1)),bytes(u.mem_read(worker+0x478,4))
for case in [{},{'hq':0x100},{'hq':0x200},{'resource':0x305},{'scan':True},{'hq':1},{'worker':0},{'resource':0x306}]:
 a=run(False,case);b=run(True,case);assert a==b,(case,a,b)
 if case in [{},{'hq':0x100},{'hq':0x200},{'resource':0x305},{'scan':True}]:assert a[2]==b'\x2d' and a[1]==struct.pack('<I',5)
print('PASS: original/HD exact ore-rally state parity across three HQs, ore variants, scan fallback and exclusions; registers/flags/stack preserved')
