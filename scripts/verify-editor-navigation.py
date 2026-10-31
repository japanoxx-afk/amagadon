"""Execute emitted x86 handlers against Win32 stubs; check ABI and native routing."""
import sys,struct,pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
p=pefile.PE(sys.argv[1]); image=p.get_memory_mapped_image()
base=0x400000; cave=base+p.sections[-1].VirtualAddress
u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(base,0x300000);u.mem_write(base,image)
u.mem_map(0x800000,0x20000);u.mem_map(0x900000,0x10000)
def put(a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
calls=[]
apis={0x900010:('send',4),0x900020:('capture',1),0x900030:('release',0),0x900040:('rect',2)}
for a,v in [(0x4451a0,0x900010),(0x4451d4,0x900020),(0x4451d0,0x900030),(0x44522c,0x900040)]:put(a,v)
def hook(u,a,n,d):
    if a==0x4017c6:u.emu_stop();return
    if a not in apis:return
    name,argc=apis[a];sp=u.reg_read(UC_X86_REG_ESP);args=[get(sp+4+4*i) for i in range(argc)]
    calls.append((name,args))
    if name=='rect':u.mem_write(args[1],struct.pack('<4i',0,0,1024,768))
    u.reg_write(UC_X86_REG_EAX,1);u.reg_write(UC_X86_REG_ESP,sp+4+argc*4);u.reg_write(UC_X86_REG_EIP,get(sp))
u.hook_add(UC_HOOK_CODE,hook)
saved=[UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
def message(msg,wp=0,lp=0,handled=True):
    calls.clear();sp=0x80f000
    for i,v in enumerate([0x900fff,123,msg,wp,lp]):put(sp+4*i,v)
    for i,r in enumerate(saved):u.reg_write(r,0x11220000+i)
    u.reg_write(UC_X86_REG_ESP,sp)
    # Start at the cave: the original SEH load is checked structurally below.
    u.emu_start(cave+0x1000,0x900fff,count=5000)
    assert u.reg_read(UC_X86_REG_ESP)==sp+(20 if handled else 0)
    assert all(u.reg_read(r)==0x11220000+i for i,r in enumerate(saved))
    return list(calls)
# Nonhandled messages reach the exact original prologue without losing arguments.
# FS:[0] requires page zero in this isolated emulator.
u.mem_map(0,0x1000)
message(0x111,handled=False)
put(0x44dba0,1);put(0x44db70,456)
assert message(0x20a,(-60&0xffff)<<16)==[]
assert message(0x20a,(-60&0xffff)<<16)==[('send',[123,0x115,1,456])]*3
assert message(0x20a,240<<16)==[('send',[123,0x115,0,456])]*6
put(cave+0x2800,144)
message(0x201,lp=150);assert get(cave+0x2804)==1
assert message(0x200,lp=350)[-1]==('send',[123,5,0,(768<<16)|1024])
assert get(cave+0x2800)==350
message(0x200,lp=2000);assert get(cave+0x2800)==856
message(0x200,lp=0xffff);assert get(cave+0x2800)==144
assert message(0x202)==[('release',[])] and get(cave+0x2804)==0
message(0x201,lp=20,handled=False)
message(0x201,lp=150);message(0x215,handled=False);assert get(cave+0x2804)==0
# Width hook preserves the height operands, clamps map space, and changes only EBP.
for requested,client,expected in [(0,1024,144),(350,1024,350),(900,640,472),(40,640,144)]:
    put(cave+0x2800,requested);sp=0x80f000;put(sp+0x30,777)
    for r,v in [(UC_X86_REG_ESP,sp),(UC_X86_REG_EBP,244),(UC_X86_REG_EAX,100),(UC_X86_REG_EBX,client),(UC_X86_REG_ECX,888)]:u.reg_write(r,v)
    u.emu_start(cave+0x900,0x401a1c,count=100)
    assert u.reg_read(UC_X86_REG_EBP)==expected and get(cave+0x2800)==expected
    assert u.reg_read(UC_X86_REG_ESP)==sp and u.reg_read(UC_X86_REG_EAX)==777 and u.reg_read(UC_X86_REG_ECX)==888
print('PASS: wheel direction/partial deltas, native scroll routing, splitter bounds/capture loss, layout and x86 ABI')
