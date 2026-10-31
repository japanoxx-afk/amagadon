# Read-only live-game memory supplies real unit/map structures to a detached CPU.
# All mutations and native command execution occur inside Unicorn, never the game.
import ctypes as c,ctypes.wintypes as w,struct,json,sys
from pathlib import Path
sys.path.insert(0,'.tools')
from unicorn import *
from unicorn.x86_const import *
k=c.WinDLL('kernel32',use_last_error=True);k.OpenProcess.restype=w.HANDLE;k.ReadProcessMemory.argtypes=[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)];k.CloseHandle.argtypes=[w.HANDLE]
h=k.OpenProcess(0x1010,False,int(sys.argv[1]));assert h
cache={}
def page(a):
 a&=~4095
 if a not in cache:
  b=c.create_string_buffer(4096);n=c.c_size_t()
  if not k.ReadProcessMemory(h,a,b,4096,c.byref(n)):raise RuntimeError('unreadable live page '+hex(a))
  cache[a]=b.raw
 return cache[a]
u=Uc(UC_ARCH_X86,UC_MODE_32);mapped=set()
def ensure(a,size):
 for addr in range(a&~4095,(a+size+4095)&~4095,4096):
  if addr not in mapped:u.mem_map(addr,4096);u.mem_write(addr,page(addr));mapped.add(addr)
def fault(uc,access,a,size,value,data):
 try:ensure(a,size);return True
 except Exception as e:print(e,'at',hex(uc.reg_read(UC_X86_REG_EIP)),trace);return False
u.hook_add(UC_HOOK_MEM_UNMAPPED,fault)
trace=[]
def trace_code(uc,a,size,d):
 trace.append(hex(a))
 if len(trace)>30:trace.pop(0)
u.hook_add(UC_HOOK_CODE,trace_code)
def read(a,n=4):ensure(a,n);return bytes(u.mem_read(a,n))
def num(a,n=4):return int.from_bytes(read(a,n),'little')
def write(a,b):ensure(a,len(b));u.mem_write(a,b)
M=json.loads(Path('.tools/selection-runtime.json').read_text());u.mem_map(M['base'],M['size']);u.mem_write(M['base'],Path('.tools/selection-runtime.bin').read_bytes())
STACK=0x600f000;END=0x6001000;u.mem_map(0x6000000,0x100000)
def call(name,args):
 u.reg_write(UC_X86_REG_ESP,STACK);u.mem_write(STACK,struct.pack('<'+'I'*(len(args)+1),END,*args));u.emu_start(M['blocks'][name],END,count=10000000);assert u.reg_read(UC_X86_REG_EIP)==END,hex(u.reg_read(UC_X86_REG_EIP))
m=num(0x504a10);units=[]
for i in range(min(num(m+4),1700)):
 p=num(m+8+i*4)
 if p and num(p+0x13b8,1) and num(p+0x30)==0 and num(p+0x464,1) not in (12,13):
  read(p,0x13e0);write(p+0x3c,b'\1');units.append((i,p))
# Populate 65 independent copies of a real worker in the isolated address space.
assert units
sample=read(units[0][1],0x13e0);u.mem_map(0x6500000,0x100000);mapped.update(range(0x6500000,0x6600000,4096))
units=[]
for i in range(65):
 p=0x6500000+i*0x1400;u.mem_write(p,sample);u.mem_write(p+14,struct.pack('<H',i));u.mem_write(p+0x3c,b'\1');u.mem_write(p+0x464,b'\0');write(m+8+i*4,struct.pack('<I',p));units.append((i,p))
write(m+4,struct.pack('<I',65))
call('select',(1,14));count=int.from_bytes(u.mem_read(M['counts']+4,4),'little');ids=struct.unpack('<'+'H'*count,u.mem_read(M['lists']+4096,count*2));print('real worker structures, isolated copies',count);assert count>16
before={i:bytes(u.mem_read(p,0x13e0)) for i,p in units if i in ids}
packet=bytearray(64);packet[0]=4;packet[3]=255
# World target and screen-space target both lie in the current map's viewport.
first=dict(units)[ids[0]];x=num(first+20);y=num(first+24)
struct.pack_into('<H',packet,14,1700)
struct.pack_into('<HH',packet,16,x+64,y+64);struct.pack_into('<HH',packet,20,300,200)
write(0x52f550,bytes(packet));write(0x4f9e42,b'\1\0')
write(0x4f9dd0,struct.pack('<4i',-100,-100,-50,-50))
# Supply the original thread-local CRT state without emulating Windows TEB.
tls=num(0x233a01c)-20;read(tls,256);write(0x4c2f13,b'\xb8'+struct.pack('<I',tls)+b'\xc3')
for dx,dy in ((64,64),(-64,64),(64,-64),(-64,-64),(128,0),(0,128),(-128,0),(0,-128)):
 for i,p in units:u.mem_write(p,before[i])
 struct.pack_into('<HH',packet,16,max(1,x+dx),max(1,y+dy));write(0x52f550,bytes(packet))
 call('right',(1,))
 changed=[i for i,p in units if bytes(u.mem_read(p,0x13e0))!=before[i]]
 if len(changed)==65 and all(num(p+0x464,1)==2 for i,p in units):break
print('native ground move changed',len(changed),'of',count,'units; pages',len(cache));assert len(changed)==65
assert all(num(p+0x464,1)==2 for i,p in units)
packet[0]=1;write(0x52f550,bytes(packet));write(0x51bc54,struct.pack('<I',5))
call('order',(1,))
print('states after native order 5',sorted(set(num(p+0x464,1) for i,p in units)),'order',num(0x51bc54))
assert all(num(p+0x464,1)==5 for i,p in units)
assert num(0x51bc54)==0
Path('.tools/native-selection-result.json').write_text(json.dumps({'selected':count,'changed':len(changed),'ids':changed,'pages':len(cache),'method':'read-only live memory, original native handlers executed in isolated Unicorn'}))
k.CloseHandle(h)
