"""Check NW anchor snap, matching preview pixels, guards and full paint."""
exec(compile(open('scripts/verify-ramp-pipeline.py',encoding='utf-8').read(),'pipeline','exec'))
va=0x400000+next(s.VirtualAddress for s in p.sections if s.Name.startswith(b'.acefix'))
u.mem_write(0xa00000+0xc1404,b'\x39');u.mem_write(0x44dbf3,b'\x02')
# Fresh NW boundary; do not reuse NE terrain from the pipeline loop.
u.mem_write(0x1000000,bytes(0x9d0000));u.mem_write(0x44dbf0,b"\x00")
for x in range(-4,132):
 for y in range(-4,260):u.mem_write(0x1000000+0x1e2712+x*264+y,bytes([int(y-100+(x-50)>0)]))
def resolve(x,y):
 sp=0x80f000;u.mem_write(sp,struct.pack('<3I',0x8ffff0,x,y));u.reg_write(UC_X86_REG_ESP,sp);u.emu_start(va+0x2440,0x8ffff0,count=1000000)
 assert u.reg_read(UC_X86_REG_EIP)==0x8ffff0
 return u.reg_read(UC_X86_REG_EAX),u.reg_read(UC_X86_REG_EDX)
assert resolve(101,100)==(101,100)
assert resolve(101,99)==(101,100)
assert resolve(101,99)==(101,100)
assert resolve(101,120)==(101,120),'must reject distant/non-boundary terrain'
u.mem_write(0x44dbf3,b'\x01');assert resolve(101,99)==(101,99)
u.mem_write(0x44dbf3,b'\x02');u.mem_write(0xa00000+0xc1404,b'\x3a');assert resolve(101,99)==(101,99)
u.mem_write(0xa00000+0xc1404,b'\x39')
# Preview validates and renders at precisely the same snapped cell.
u.mem_write(0x44dbe8,bytes(8));sp=0x80f000
u.reg_write(UC_X86_REG_ESP,sp);u.reg_write(UC_X86_REG_ESI,102*32);u.reg_write(UC_X86_REG_EDI,100*32)
u.emu_start(0x425ca4,0x425cb6,count=1000000)
assert struct.unpack('<I',u.mem_read(sp+0x18,4))[0]==102
assert struct.unpack('<I',u.mem_read(sp+0x24,4))[0]==101
assert u.reg_read(UC_X86_REG_ESI)==102*32 and u.reg_read(UC_X86_REG_EDI)==101*32
u.mem_write(sp,struct.pack('<3I',0x8ffff0,101,99));u.reg_write(UC_X86_REG_ESP,sp);u.emu_start(0x428260,0x8ffff0,count=20000000)
assert u.reg_read(UC_X86_REG_EIP)==0x8ffff0
assert bytes(u.mem_read(0x1000000+0x424f92+50*264+100,1))==b'\x39'
print('PASS: NW adjacent anchor, matching preview pixels, NE/terrain brush guards, distant rejection, complete snapped paint')
