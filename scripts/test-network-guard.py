"""Run original and guarded network paths in x86 emulation; no network/UI input."""
import sys,json,base64,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'.tools'))
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE,UcError,UC_PROT_READ,UC_PROT_EXEC
from unicorn.x86_const import *
pe=pefile.PE(sys.argv[1]);edits=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8-sig'))
def machine(patched=True):
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x3000000);u.mem_write(0x400000,pe.get_memory_mapped_image())
 if patched:
  for e in edits:u.mem_write(e['address'],base64.b64decode(e['bytes']))
 u.mem_protect(0x475000,0x1000,UC_PROT_READ|UC_PROT_EXEC);u.mem_protect(0x1000000,0x1000,UC_PROT_READ|UC_PROT_EXEC)
 return u
def put(u,a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
def get(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
def ret(u,n,value):
 sp=u.reg_read(UC_X86_REG_ESP);u.reg_write(UC_X86_REG_EAX,value&0xffffffff);u.reg_write(UC_X86_REG_EIP,get(u,sp));u.reg_write(UC_X86_REG_ESP,sp+4+n)
def run(provider,stage='ok',patched=True,tcp=False):
 u=machine(patched);put(u,0x5140d0,0x580000);put(u,0x580000,0x580100);put(u,0x580108,0x590000);put(u,0x580198,0x590200);put(u,0x4cb3d8,0x590100)
 put(u,0x5140f8 if tcp else 0x5140f4,0x581000 if provider else 0);u.mem_write(0x581000,b'provider\0')
 sp=0x2008000;put(u,sp,0x5f0000);u.reg_write(UC_X86_REG_ESP,sp);u.reg_write(UC_X86_REG_EDI,0x12345678);calls=[]
 def hook(u,a,size,data):
  if a==0x590000:calls.append('release');ret(u,4,0)
  elif a==0x475910:ret(u,0,0x80004005 if stage=='address' else 0)
  elif a==0x590100:
   calls.append('create');out=get(u,u.reg_read(UC_X86_REG_ESP)+20);put(u,out,0 if stage=='create' else 0x580000);ret(u,20,0x80004005 if stage=='create' else 0)
  elif a==0x590200:ret(u,12,0x80004005 if stage=='initialize' else 0)
 u.hook_add(UC_HOOK_CODE,hook)
 try:u.emu_start(0x475bb0 if tcp else 0x475b20,0x5f0000,count=5000)
 except UcError:
  print(provider,stage,patched,tcp,hex(u.reg_read(UC_X86_REG_EIP)),calls,hex(get(u,0x5140d0)),hex(get(u,0x580000)),hex(get(u,0x580198)),hex(u.reg_read(UC_X86_REG_ESP)));raise
 assert u.reg_read(UC_X86_REG_ESP)==sp+4 and u.reg_read(UC_X86_REG_EDI)==0x12345678
 assert u.reg_read(UC_X86_REG_EAX)==(1 if provider and stage=='ok' else 0)
 if not provider:assert not calls
 if stage in ('address','create') and provider:assert get(u,0x5140d0)==0
try:run(False,patched=False)
except UcError:pass
else:raise AssertionError('Original missing-provider crash not reproduced')
for tcp in (False,True):
 for present in (False,True):
  for stage in ('ok','address','create','initialize'):run(present,stage,tcp=tcp)
for site,success,fail in [(0x45c08e,0x45c099,0x45c0a7),(0x45c100,0x45c10b,0x45c119)]:
 for result in (0,1):
  u=machine();sp=0x2008000;u.reg_write(UC_X86_REG_ESP,sp);u.reg_write(UC_X86_REG_EAX,result);put(u,0x4cb258,0x590300);calls=[]
  def hook(u,a,size,data):
   if a==0x590300:calls.append('message');ret(u,16,1)
  u.hook_add(UC_HOOK_CODE,hook);u.emu_start(site,success if result else fail,count=1000)
  assert u.reg_read(UC_X86_REG_ESP)==sp and u.reg_read(UC_X86_REG_EAX)==result
  assert calls==([] if result else ['message']) and get(u,get(u,0x475ba8))==(0 if result else 1)
print('PASS: original null-provider crash reproduced; IPX/TCP null and initialization failures; released pointer cleared; successful next-screen path; failure menu return/message/count; stack/register preservation')
