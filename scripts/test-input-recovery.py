"""Original x86 focus callbacks, mouse reads and notification-thread regression.
OS/COM test doubles execute the actual original/patched paths without desktop input.
"""
import sys,json,base64,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'.tools'))
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE,UC_PROT_READ,UC_PROT_EXEC
from unicorn.x86_const import *
pe=pefile.PE(sys.argv[1]);edits=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8-sig'))
STOP=0x5f0000;SP=0x2008000;DEVICE=0x580000;TABLE=0x580100;STATS=0x1001000
def put(u,a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
def get(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
def machine(patched=True):
 u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x3000000);u.mem_write(0x400000,pe.get_memory_mapped_image())
 if patched:
  for e in edits:u.mem_write(e['address'],base64.b64decode(e['bytes']))
 u.mem_protect(0x1000000,0x1000,UC_PROT_READ|UC_PROT_EXEC)
 put(u,0x5727e8,DEVICE);put(u,DEVICE,TABLE);put(u,TABLE+0x28,0x590000);put(u,TABLE+0x1c,0x590100)
 put(u,STATS+32,0x590400);put(u,0x572b50,0x1234)
 put(u,SP,STOP);u.reg_write(UC_X86_REG_ESP,SP)
 for r,v in [(UC_X86_REG_EBX,0x11111111),(UC_X86_REG_ESI,0x22222222),(UC_X86_REG_EDI,0x33333333),(UC_X86_REG_EBP,0x44444444)]:u.reg_write(r,v)
 return u
def ret(u,n,value=0):
 sp=u.reg_read(UC_X86_REG_ESP);u.reg_write(UC_X86_REG_EAX,value&0xffffffff);u.reg_write(UC_X86_REG_EIP,get(u,sp));u.reg_write(UC_X86_REG_ESP,sp+4+n)
def preserved(u,args=0):
 assert u.reg_read(UC_X86_REG_ESP)==SP+4+args
 assert [u.reg_read(r) for r in (UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP)]==[0x11111111,0x22222222,0x33333333,0x44444444]
def focus(wparam,patched=True):
 u=machine(patched);put(u,0x504dc4,1);put(u,0x572b5c,1);put(u,0x572b54,0x581000);put(u,0x572b58,0x582000);put(u,0x4cb2a8,0x590200)
 for i,v in enumerate([0x1234,6,wparam,0]):put(u,SP+4+i*4,v)
 calls=[]
 def hook(u,a,size,_):
  if a==0x590100:calls.append('mouse-acquire');ret(u,4)
  elif a==0x4904c0:calls.append('keyboard-acquire');ret(u,0)
  elif a in (0x491c10,0x492280,0x4a3430,0x4a3310,0x491540,0x4a3420):ret(u,0)
  elif a==0x590200:ret(u,16)
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x494ec0,STOP,count=5000);preserved(u,16)
 return get(u,0x572b5c),calls
assert focus(2,False)==(1,[]) # original click-return leaves the mouse paused
for activation in (1,2,0x10002):assert focus(activation)==(0,['keyboard-acquire','mouse-acquire'])
assert focus(0)==(1,[]) and focus(3)==(1,[])

def mouse(results,acquire=0,count_on_error=0,patched=True,foreground=True,resolve=False):
 u=machine(patched);put(u,SP+4,0x581000);put(u,0x581000,99);put(u,0x4e89d8,100);put(u,0x4e89dc,100);put(u,0x4e89d0,0)
 calls=[];pending=list(results)
 if resolve:put(u,STATS+32,0);put(u,0x4cb124,0x590500);put(u,0x4cb09c,0x590600)
 def hook(u,a,size,_):
  if a==0x590000:
   sp=u.reg_read(UC_X86_REG_ESP);assert get(u,sp+4)==DEVICE and get(u,sp+8)==16 and get(u,get(u,sp+16))==64
   status=pending.pop(0);calls.append('read');n=get(u,sp+16);data=get(u,sp+12)
   if status in (0,1):put(u,n,1);u.mem_write(data,struct.pack('<IIII',0,5,0,0))
   else:put(u,n,count_on_error);u.mem_write(data,struct.pack('<IIII',0,123,0,0))
   ret(u,20,status)
  elif a==0x590100:calls.append('acquire');ret(u,4,acquire)
  elif a==0x590400:ret(u,0,0x1234 if foreground else 0x5678)
  elif a==0x590500:
   assert bytes(u.mem_read(get(u,u.reg_read(UC_X86_REG_ESP)+4),11))==b'user32.dll\0';ret(u,4,0x77000000)
  elif a==0x590600:
   assert bytes(u.mem_read(get(u,u.reg_read(UC_X86_REG_ESP)+8),20))==b'GetForegroundWindow\0';ret(u,8,0x590400)
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x4906c0,STOP,count=10000);preserved(u)
 return calls,get(u,0x4e89d8),get(u,0x581000),u
assert mouse([0x8007001e],patched=False)[:3]==(['read'],100,0)
assert mouse([0x8007000c],patched=False)[:3]==(['read'],100,0)
for error in (0x8007001e,0x8007000c):
 for count in (0,64):
  calls,x,changed,u=mouse([error,0],count_on_error=count)
  assert calls==['read','acquire','read'] and x==105 and changed==1
  assert get(u,STATS+8)==1 and get(u,STATS+16)==1
  for failure in (0x80070005,0x8007001e):
   calls,x,changed,u=mouse([error],acquire=failure,count_on_error=count)
   assert calls==['read','acquire'] and x==100 and changed==0 and get(u,STATS+20)==1
  calls,x,changed,u=mouse([error,error],count_on_error=count)
  assert calls==['read','acquire','read'] and x==100 and changed==0 # bounded: no retry loop
for status in (0,1):assert mouse([status])[:3]==(['read'],105,1) # DI_OK / DI_BUFFEROVERFLOW
assert mouse([0x80070057],count_on_error=64)[:3]==(['read'],100,0) # never consume undefined data
assert mouse([0x8007000c],foreground=False)[:3]==(['read'],100,0)
assert mouse([0x8007000c,0],resolve=True)[:3]==(['read','acquire','read'],105,1)

def notification(first,paused=0,patched=True,foreground=True,enabled=1):
 u=machine(patched);put(u,SP+4,0x123);put(u,0x5727d0,enabled);put(u,0x572b5c,paused);put(u,0x572990,0);put(u,0x4cb0e8,0x590300)
 waits=[];reads=[]
 def hook(u,a,size,_):
  if a==0x590300:
   sp=u.reg_read(UC_X86_REG_ESP);waits.append(get(u,sp+8));ret(u,8,first if len(waits)==1 else 0xffffffff)
  elif a==0x590000:
   reads.append(1);put(u,get(u,u.reg_read(UC_X86_REG_ESP)+16),0);ret(u,20)
  elif a==0x590400:ret(u,0,0x1234 if foreground else 0x5678)
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x4909a0,STOP,count=10000);preserved(u,4)
 return waits,reads
assert notification(258,patched=False)==([0xffffffff],[])
assert notification(258)==([100,100],[1])
assert notification(0)==([100,100],[1])
assert notification(258,paused=1)==([100,100],[1]) # restore a missed activation only when truly foreground
assert notification(258,foreground=False)==([100,100],[])
assert notification(0,foreground=False)==([100,100],[])
assert notification(258,enabled=0)==([100,100],[])
assert notification(0xffffffff)==([100],[])
print('PASS: original WA_CLICKACTIVE freeze and zero-event INPUTLOST/NOTACQUIRED reproduced; activation/refocus, bounded read/reacquire/retry, overflow/error data safety, notification timeout recovery, inactive gating and exact stack/register restoration')
