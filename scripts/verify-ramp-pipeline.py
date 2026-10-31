"""Run ACE's complete paint/cleanup/stamp pipeline on isolated synthetic hills.
Only randomness and final UI redraw are stubbed; terrain getters/setters run.
Usage: verify-ramp-pipeline.py ORIGINAL_GAME_DIRECTORY PATCHED_ACE
"""
import sys,struct,importlib.util
from pathlib import Path
import pefile
from unicorn import *
from unicorn.x86_const import *
spc=importlib.util.spec_from_file_location('ramps',Path(__file__).with_name('build-reverse-ramps.py'));r=importlib.util.module_from_spec(spc);spc.loader.exec_module(r)
folder=Path(sys.argv[1]);ms,pi=r.build(r.terrain.archive_entry(folder,b'Data\\Earth.ms'),r.terrain.archive_entry(folder,b'Data\\Earth.pi'))
plane=0
for rec,slope,offset in [(57,-1,0),(58,1,1)]:
 objbytes=bytearray(0x9d0000)
 for x in range(-4,132):
  for y in range(-4,260):objbytes[0x1e2712+x*264+y]=int(y-100-slope*(x-50)-offset>0)
 p=pefile.PE(sys.argv[2]);u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x300000);u.mem_write(0x400000,p.get_memory_mapped_image());u.mem_map(0x800000,0x100000);u.mem_map(0xa00000,0x100000);u.mem_write(0xa00000,ms);u.mem_write(0x452480,struct.pack('<I',0xa00000));u.mem_map(0x1000000,0xa00000);u.mem_write(0x1000000,bytes(objbytes));u.mem_write(0x44dba0,struct.pack('<I',0x1000000));u.mem_write(0x44dbf0,bytes([plane]));u.mem_write(0xa00000+0xc1404,bytes([rec]))
 def hook(u,a,n,d):
  if a in (0x4248b0,0x4279a0):
   sp=u.reg_read(UC_X86_REG_ESP);ret=struct.unpack('<I',u.mem_read(sp,4))[0];u.reg_write(UC_X86_REG_EAX,0);u.reg_write(UC_X86_REG_ESP,sp+4);u.reg_write(UC_X86_REG_EIP,ret)

 u.hook_add(UC_HOOK_CODE,hook)
 sp=0x80f000;u.mem_write(sp,struct.pack('<3I',0x8ffff0,101,100));u.reg_write(UC_X86_REG_ESP,sp);u.emu_start(0x428260,0x8ffff0,count=20000000)
 assert u.reg_read(UC_X86_REG_EIP)==0x8ffff0
 addr=0x1000000+0x424f92+(50+plane*136)*264+100
 assert bytes(u.mem_read(addr,1))==bytes([rec]);print('PASS: full native paint and cleanup retained ramp',rec)
