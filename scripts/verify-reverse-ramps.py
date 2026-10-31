"""Exercise the original ACE placement and collision-copy machine code."""
import importlib.util,struct,sys,hashlib
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP,UC_X86_REG_EIP,UC_X86_REG_EAX
spec=importlib.util.spec_from_file_location('ramps',Path(__file__).with_name('build-reverse-ramps.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
folder=Path(sys.argv[1])
assert hashlib.sha256((folder/'ACE.exe').read_bytes()).hexdigest()=='a1b1b0464ce5b9af1841973184adb8c9852ed78fbc922b182a1d90933877d507'
ms=r.terrain.archive_entry(folder,b'Data\\Earth.ms');pi=r.terrain.archive_entry(folder,b'Data\\Earth.pi');patched,tiles=r.build(ms,pi)
u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x300000);u.mem_write(0x400000,pefile.PE(sys.argv[2]).get_memory_mapped_image());u.mem_map(0x800000,0x100000);u.mem_map(0xa00000,0x100000);u.mem_write(0xa00000,patched);u.mem_write(0x452480,struct.pack('<I',0xa00000))
mode='placement';slope=sign=offset=0;writes=[]
def get(p):return struct.unpack('<I',u.mem_read(p,4))[0]
def hook(u,a,n,d):
    if mode=='placement':
        if a not in (0x423290,0x4238a0):return
        sp=u.reg_read(UC_X86_REG_ESP);x,y=struct.unpack('<2i',u.mem_read(sp+4,8));v=int(sign*((y-100)-slope*(x-50)-offset)>0) if a==0x423290 else 0;size=12
    else:
        sizes={0x423690:12,0x423640:16,0x423900:24,0x423aa0:16,0x423b80:16}
        if a not in sizes:return
        sp=u.reg_read(UC_X86_REG_ESP);size=sizes[a];v=0
        if a in (0x423aa0,0x423b80):writes.append((a,*struct.unpack('<4I',u.mem_read(sp+4,16))))
    u.reg_write(UC_X86_REG_EAX,v);u.reg_write(UC_X86_REG_ESP,sp+size+4);u.reg_write(UC_X86_REG_EIP,get(sp))
u.hook_add(UC_HOOK_CODE,hook)
def call(address,*args):
    sp=0x80f000;u.mem_write(sp,struct.pack('<'+'I'*(len(args)+1),0x8ffff0,*args));u.reg_write(UC_X86_REG_ESP,sp);u.emu_start(address,0x8ffff0,count=100000);assert u.reg_read(UC_X86_REG_EIP)==0x8ffff0;return u.reg_read(UC_X86_REG_EAX)
mode='collision'
for source,dest in [(15,57),(14,58)]:
    for x in range(0,8,2):
        for y in range(6):
            writes.clear();call(0x428ef0,dest,50,100,x,y,255)
            assert len(writes)==4
            for address,mx,my,plane,value in writes:
                dx=mx-100;grid=0 if address==0x423aa0 else 0x68
                expected=ms[276+source*0x3384+grid+(7-x-dx)*13+5-y]
                assert value&255==expected,(dest,x,y,address,value,expected)
assert patched[:276+57*0x3384]==ms[:276+57*0x3384]
assert patched[276+59*0x3384:]==ms[276+59*0x3384:]
assert tiles[:18]==pi[:18] and tiles[20:len(pi)]==pi[20:]
print('PASS: native connection-layer collision writes all 96 cells; existing records and tiles unchanged')
