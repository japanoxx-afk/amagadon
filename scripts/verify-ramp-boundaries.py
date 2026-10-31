"""Compare north-ramp validation against rotated original maps, including rejects."""
import hashlib,importlib.util,struct,sys
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP,UC_X86_REG_EIP,UC_X86_REG_EAX
s=importlib.util.spec_from_file_location('ramps',Path(__file__).with_name('build-reverse-ramps.py'));r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
folder=Path(sys.argv[1]);ms,pi=r.build(r.terrain.archive_entry(folder,b'Data\\Earth.ms'),r.terrain.archive_entry(folder,b'Data\\Earth.pi'))
def engine(path):
    u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x300000);u.mem_write(0x400000,pefile.PE(str(path)).get_memory_mapped_image());u.mem_map(0x800000,0x100000);u.mem_map(0xa00000,0x100000);u.mem_write(0xa00000,ms);u.mem_write(0x452480,struct.pack('<I',0xa00000));return u
base=engine(folder/'ACE.exe');patched=engine(Path(sys.argv[2]));ctx={};counts=[0,0]
def hook(u,a,n,d):
    if a not in (0x423290,0x4238a0):return
    sp=u.reg_read(UC_X86_REG_ESP);ret,x,y=struct.unpack('<Iii',u.mem_read(sp,12))
    if u==patched and ctx['mirror']:x,y=101-x,201-y+ctx.get("shift",0)
    dx,dy=x-50,y-100
    if a==0x423290:
        v=int(ctx['sign']*(dy-ctx['slope']*dx-ctx['offset'])>0)
        if (dx,dy)==ctx['hole']:v=2
    else:v=0
    u.reg_write(UC_X86_REG_EAX,v);u.reg_write(UC_X86_REG_ESP,sp+16);u.reg_write(UC_X86_REG_EIP,ret)
for u in (base,patched):u.hook_add(UC_HOOK_CODE,hook)
def call(u,rec):
    sp=0x80f000;u.mem_write(sp,struct.pack('<4I',0x8ffff0,101,100,rec));u.reg_write(UC_X86_REG_ESP,sp);u.emu_start(0x42ea90,0x8ffff0,count=100000);assert u.reg_read(UC_X86_REG_EIP)==0x8ffff0;return u.reg_read(UC_X86_REG_EAX)
for source,dest in [(15,57),(14,58)]:
    for slope in (-2,-1,0,1,2):
        for sign in (-1,1):
            for offset in range(-5,6):
                for hole in (None,(-1,-1),(0,0),(1,1),(2,-2)):
                    ctx.update(shift=-3 if dest==57 else 0,slope=slope,sign=sign,offset=offset,hole=hole,mirror=True)
                    expected=call(base,source);actual=call(patched,dest)
                    assert actual==expected,(source,ctx,expected,actual)
                    counts[expected==0]+=1
                    ctx['mirror']=False
                    assert call(base,source)==call(patched,source),'original direction changed'
assert min(counts)>0,counts
print('PASS: 1100 reflected boundary/obstacle cases, 1100 original direction cases; rejected/accepted',counts)
