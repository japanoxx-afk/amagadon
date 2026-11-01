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

# Both lockstep diagnostics must preserve the original comparison, every register,
# and the stack. In particular, error 60 must still trigger the native disconnect.
for site,reason in [(0x483b4a,1),(0x483baa,2)]:
 for errors in (0,59,60,61,70):
  snapshots=[]
  for patched in (False,True):
   u=machine(patched)
   registers=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP,UC_X86_REG_ESP]
   values=[0x123456ab,3,0x765432cd,0x99,50 if reason==2 else 7,0x8811,0x9922,0x2008000]
   for r,v in zip(registers,values):u.reg_write(r,v)
   u.reg_write(UC_X86_REG_EFLAGS,0x202)
   u.mem_write(0x51a8e4,bytes([errors]));u.mem_write(0x4e7270,b'\x02')
   u.mem_write(0x52f510+2*64,bytes(range(64)))
   u.mem_write(0x525990+(3*61+7)*64,bytes(range(64,128)))
   put(u,0x503c6c,54321);u.mem_write(0x52f54e+2*64,struct.pack('<H',4321))
   u.emu_start(site,site+7,count=1000)
   snapshots.append(([u.reg_read(r) for r in registers],u.reg_read(UC_X86_REG_EFLAGS)))
   if patched:
    b=get(u,0x475ba8)
    assert get(u,b+8+(reason-1)*4)==1 and get(u,b+16)==reason
    assert get(u,b+20)==3 and get(u,b+24)==values[4]
    assert get(u,b+28)&255==0xab and get(u,b+32)&255==0xcd
    assert [get(u,b+x) for x in (36,40,44,48)]==[54321,errors,2,4321]
    assert (get(u,b+64)==0x31435953)==(errors==0)
    if errors==0:
     assert get(u,b+68)==54321 and get(u,b+72)==reason and get(u,b+76)==3 and get(u,b+80)==values[4]
     assert bytes(u.mem_read(b+128,64))==bytes(u.mem_read(0x52f510+2*64,64))
     assert bytes(u.mem_read(b+192,64))==(bytes(range(64,128)) if reason==1 else bytes(64))
  assert snapshots[0]==snapshots[1],(site,errors,snapshots)
print('Lockstep diagnostics: register/flag preservation and native disconnect threshold passed')
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
for site,success,fail in [(0x45c08e,0x45c099,0x45c0ae),(0x45c100,0x45c10b,0x45c120)]:
 for result in (0,1):
  u=machine();sp=0x2008000;u.reg_write(UC_X86_REG_ESP,sp);u.reg_write(UC_X86_REG_EAX,result);put(u,0x4cb258,0x590300);calls=[]
  saved=[0x11111111,0x22222222,0x33333333,0x44444444]
  for i,v in enumerate(saved):put(u,sp+4*i,v)
  put(u,sp+16+0x1c,0x5f0000)
  def hook(u,a,size,data):
   if a==0x590300:calls.append('message');ret(u,16,1)
  u.hook_add(UC_HOOK_CODE,hook);u.emu_start(site,success if result else 0x5f0000,count=1000)
  assert calls==([] if result else ['message']) and get(u,get(u,0x475ba8))==(0 if result else 1)
  if result:assert u.reg_read(UC_X86_REG_ESP)==sp
  else:
   assert u.reg_read(UC_X86_REG_ESP)==sp+16+0x1c+4
   assert [u.reg_read(r) for r in (UC_X86_REG_EDI,UC_X86_REG_EBP,UC_X86_REG_EBX,UC_X86_REG_ESI)]==saved
# The 0.3.13 destination erroneously adds twelve bytes belonging to arguments
# that the failure path never pushed. Execute through RET to catch this.
u=machine();sp=0x2008000;u.reg_write(UC_X86_REG_ESP,sp);put(u,sp+16+0x1c,0x5f0000)
try:u.emu_start(0x45c0a7,0x5f0000,count=100)
except UcError:pass
else:raise AssertionError('0.3.13 bad epilogue regression not reproduced')
print('PASS: null provider and 16 initialization combinations; 0.3.13 bad epilogue reproduced; fixed IPX failure and retry return through caller with exact stack/register restoration')
