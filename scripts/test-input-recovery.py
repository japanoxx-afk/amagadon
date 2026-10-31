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

def keyboard(results,acquire=0,foreground=True,patched=True):
 u=machine(patched);obj=0x582000;put(u,obj+12,DEVICE);u.reg_write(UC_X86_REG_ECX,obj);pending=list(results);calls=[]
 def hook(u,a,size,_):
  if a==0x590000:
   sp=u.reg_read(UC_X86_REG_ESP);assert get(u,sp+4)==DEVICE and get(u,sp+8)==16
   assert get(u,get(u,sp+16))==256
   status=pending.pop(0);calls.append('read');put(u,get(u,sp+16),1)
   u.mem_write(get(u,sp+12),struct.pack('<IIII',30,128,0,0));ret(u,20,status)
  elif a==0x590100:calls.append('acquire');ret(u,4,acquire)
  elif a==0x590400:ret(u,0,0x1234 if foreground else 0x5678)
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x4905c0,STOP,count=10000);preserved(u)
 return calls,get(u,obj+0x1010+30*4),u
assert keyboard([0x8007000c],patched=False)[:2]==(['read'],0)
for error in (0x8007000c,0x8007001e):
 assert keyboard([error,0])[:2]==(['read','acquire','read'],30)
 assert keyboard([error],acquire=0x80070005)[:2]==(['read','acquire'],0)
 assert keyboard([error,error])[:2]==(['read','acquire','read'],0)
 assert keyboard([error],foreground=False)[:2]==(['read'],0)
for ok in (0,1):assert keyboard([ok])[:2]==(['read'],30)
assert keyboard([0x80070057])[:2]==(['read'],0)
print('PASS: keyboard NOTACQUIRED/INPUTLOST bounded recovery, overflow, failed/background reads, exact stack and registers')

def startup_acquire(status,patched=True):
 u=machine(patched);u.reg_write(UC_X86_REG_EDX,TABLE)
 # Enter at the original COM call with its existing this argument.
 put(u,SP,DEVICE);calls=[];dest=[]
 def hook(u,a,size,_):
  if a==0x590100:
   assert get(u,u.reg_read(UC_X86_REG_ESP)+4)==DEVICE
   calls.append('acquire');ret(u,4,status)
  elif a in (0x490dcc,0x490da8):dest.append(a);u.emu_stop()
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x490da1,STOP,count=1000)
 assert calls==['acquire'] and u.reg_read(UC_X86_REG_ESP)==SP+4
 assert [u.reg_read(r) for r in (UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP)]==[0x11111111,0x22222222,0x33333333,0x44444444]
 return dest[0]
assert startup_acquire(0x80070005,False)==0x490da8
for status in (0,1,0x80070005,0x8007001e,0x8007000c):assert startup_acquire(status)==0x490dcc
for status in (0x80070057,0x80004005):assert startup_acquire(status)==0x490da8
print('PASS: transient startup Acquire failures preserve recovery thread; fatal failures retain original cleanup')

def pacing(last,interval,times,patched=True):
 u=machine(patched);put(u,0x50bcf8,last);put(u,0x50bc64,interval);put(u,0x4cb0fc,0x590700)
 pending=list(times);calls=[]
 def hook(u,a,size,_):
  if a==0x429850:
   calls.append('clock');ret(u,0,pending.pop(0))
  elif a==0x590700:
   assert get(u,u.reg_read(UC_X86_REG_ESP)+4)==0
   calls.append('yield');ret(u,4)
  elif a==0x482e15:u.emu_stop()
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x482dfe,STOP,count=1000)
 assert u.reg_read(UC_X86_REG_EIP)==0x482e15
 assert u.reg_read(UC_X86_REG_ESP)==SP
 assert [u.reg_read(r) for r in (UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP)]==[0x11111111,0x22222222,0x33333333,0x44444444]
 return calls
assert pacing(100,10,[105,110],False)==['clock','clock']
assert pacing(100,10,[105,110])==['clock','yield','clock']
assert pacing(100,10,[110])==['clock']
assert pacing(100,0,[100])==['clock']
assert pacing(0xfffffff0,32,[0,16])==['clock','yield','clock']
assert pacing(100,10,[101,102,103,110])==['clock','yield','clock','clock','yield','clock']
print('PASS: native frame deadline unchanged, no yield when due, repeated waits and unsigned clock wraparound')

# Execute translated RECT initialization through the original call convention.
for pointer in (0x507bb0,0x507bc8,0x507bcc,0x507bd0,0x507bd4,0x507bb4,0x507bb8):
 u=machine();obj=0x1300000;put(u,pointer,obj);put(u,0x4cb254,0x590a00)
 for i,value in enumerate((obj+16,219,18,580,409)):put(u,SP+4+i*4,value)
 seen=[]
 def rect_api(u,a,size,_):
  if a==0x590a00:
   sp=u.reg_read(UC_X86_REG_ESP);seen.append([get(u,sp+4+i*4) for i in range(5)]);ret(u,20,1)
 u.hook_add(UC_HOOK_CODE,rect_api);u.emu_start(0x1008000,STOP,count=300);preserved(u,20)
 translated=pointer not in (0x507bb4,0x507bb8)
 assert seen==[[obj+16,219+112*translated,18+84*translated,580+112*translated,409+84*translated]],seen
 # Calling initialization again must not accumulate offsets.
 put(u,SP,STOP);u.reg_write(UC_X86_REG_ESP,SP)
 for i,value in enumerate((obj+16,219,18,580,409)):put(u,SP+4+i*4,value)
 u.emu_start(0x1008000,STOP,count=300);assert seen[0]==seen[1]
u=machine();u.reg_write(UC_X86_REG_ECX,0x507cd8)
for i,value in enumerate((196,349,25,0xffffff)):put(u,SP+4+i*4,value)
seen=[]
def message_api(u,a,size,_):
 if a==0x4710f0:
  assert u.reg_read(UC_X86_REG_ECX)==0x507cd8
  sp=u.reg_read(UC_X86_REG_ESP);seen.append([get(u,sp+4+i*4) for i in range(4)]);ret(u,16)
u.hook_add(UC_HOOK_CODE,message_api);u.emu_start(0x1008100,STOP,count=100);preserved(u,16)
assert seen==[[308,517,25,0xffffff]]
print('PASS: F10/confirmation draw-hit rectangles, save/load exclusion, repeat initialization, HUD notification arguments and stack')

# Status text is NOT the chat/message list: execute its own original draw call.
u=machine();put(u,SP,STOP)
for i,value in enumerate((400,370,16,0x4f9c7c,0xc8c8c8)):put(u,SP+4+i*4,value)
seen=[]
def banner_api(u,a,size,_):
 if a==0x4a8720:
  sp=u.reg_read(UC_X86_REG_ESP);seen.append([get(u,sp+4+i*4) for i in range(5)]);ret(u,0)
u.hook_add(UC_HOOK_CODE,banner_api);u.emu_start(0x1008140,STOP,count=100);preserved(u)
assert seen==[[512,538,16,0x4f9c7c,0xc8c8c8]]

# Scoreboard sample conversion preserves actual release events and delegates
# acceptance to the native OK rectangle/release path (not forced return).
for x,y,click,accepted in ((858,680,2,True),(858,680,1,False),(100,100,2,False)):
 u=machine();u.reg_write(UC_X86_REG_ESI,0);put(u,SP+0x44,DEVICE)
 def sample_api(u,a,size,_):
  if a==0x490ea0:
   dest=get(u,u.reg_read(UC_X86_REG_ESP)+4)
   for i,v in enumerate((x,y,click,0,0)):put(u,dest+i*4,v)
   ret(u,4)
 u.hook_add(UC_HOOK_CODE,sample_api);u.emu_start(0x4a9b23,0x4a9b36,count=200)
 assert get(u,SP+0x90)==x*25//32 and get(u,SP+0x94)==y*25//32 and get(u,SP+0x98)==click
 # EBP and stack hold the right/bottom derived from the button sprite.
 u.reg_write(UC_X86_REG_EBP,705);put(u,SP+0xb0,551)
 def exit_api(u,a,size,_):
  if a in (0x4a9afe,0x4aa1ab):u.emu_stop()
 u.hook_add(UC_HOOK_CODE,exit_api);u.emu_start(0x4aa15c,STOP,count=200)
 assert (u.reg_read(UC_X86_REG_EIP)==0x4aa1ab)==accepted
 assert u.reg_read(UC_X86_REG_ESP)==SP

# Background and final blit must use the same 800x600 canvas. Cursor is drawn
# in canvas coordinates before the final stretch, then restored as usual.
u=machine();put(u,0x572974,0x580400);put(u,0x572980,0x580500);put(u,0x580400,0x580600);put(u,0x580600+0x14,0x590a00)
u.reg_write(UC_X86_REG_ECX,0x580800);put(u,0x580800+0x1c,0)
events=[]
def present_api(u,a,size,_):
 sp=u.reg_read(UC_X86_REG_ESP)
 if a==0x490e90:ret(u,0,1)
 elif a==0x490e50:
  dest=get(u,sp+4);put(u,dest,858);put(u,dest+4,680);ret(u,4)
 elif a==0x4916b0:
  assert [get(u,sp+4+i*4) for i in range(5)]==[0x580500,670,531,800,600];events.append('cursor');ret(u,0)
 elif a==0x590a00:
  assert [get(u,sp+4+i*4) for i in range(6)]==[0x580400,0,0x580500,0x1008600,0x1000000,0]
  assert list(struct.unpack('<4I',u.mem_read(0x1008600,16)))==[0,0,800,600]
  events.append('stretch');ret(u,24)
 elif a in (0x4919a0,0x491be0):events.append('restore' if a==0x4919a0 else 'finish');ret(u,0)
u.hook_add(UC_HOOK_CODE,present_api);u.emu_start(0x1008200,STOP,count=500);preserved(u)
assert events==['cursor','stretch','restore','finish'] and get(u,0x572990)==0
u=machine();u.reg_write(UC_X86_REG_EDI,0x580400);u.reg_write(UC_X86_REG_EDX,0x580500);u.reg_write(UC_X86_REG_ECX,0x580600);put(u,0x580600+0x14,0x590a00)
seen=[]
def background_api(u,a,size,_):
 if a==0x590a00:
  sp=u.reg_read(UC_X86_REG_ESP);seen.append([get(u,sp+4+i*4) for i in range(6)]);ret(u,24)
u.hook_add(UC_HOOK_CODE,background_api);u.emu_start(0x4a9b68,0x4a9b78,count=100)
assert seen==[[0x580400,0x1008600,0x580500,0,0x1000000,0]] and u.reg_read(UC_X86_REG_ESP)==SP
print('PASS: production banner, scoreboard canvas/background/cursor scaling, actual OK release path, no exit on outside click or press-only')

# Upgrade fill/outline: run each actual call site, all fractions; source RECT
# feeds subsequent width arithmetic and must never acquire the HUD offset.
for site,target,count,index in ((0x4a6a50,0x48f230,3,1),(0x4a6be5,0x48f230,3,1),(0x4a6d44,0x48f230,3,1),(0x4a6a9e,0x48f540,4,2),(0x4a6c33,0x48f540,4,2)):
 for width in (0,55,110):
  u=machine();rect=0x1300000;original=[300,500,300+width,510]
  for i,v in enumerate(original):put(u,rect+i*4,v)
  args=[0x1234,0x5678,0x9abc,0xdef0][:count];args[index]=rect
  for i,v in enumerate(args):put(u,SP+i*4,v)
  seen=[]
  def progress_api(u,a,size,_):
   if a==target:
    sp=u.reg_read(UC_X86_REG_ESP);actual=[get(u,sp+4+i*4) for i in range(count)]
    translated=[get(u,actual[index]+i*4) for i in range(4)]
    assert translated==[original[i]+(112 if i%2==0 else 168) for i in range(4)]
    assert actual[index]!=rect
    actual[index]=rect;assert actual==args;seen.append(True);ret(u,0)
  u.hook_add(UC_HOOK_CODE,progress_api);u.emu_start(site,site+5,count=300)
  assert seen==[True] and u.reg_read(UC_X86_REG_ESP)==SP
  assert u.reg_read(UC_X86_REG_EBX)==0x11111111
  assert [get(u,rect+i*4) for i in range(4)]==original
print('PASS: five upgrade fill/outline sites at 0/50/100 percent, private rectangles, caller arguments and stack preserved')
