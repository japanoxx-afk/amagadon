"""Execute patched x86 code in a bounded emulator, without controlling the desktop.

This verifies calling conventions, cache indices, RNG isolation and raster bounds.
It does not substitute for visual gameplay or multiplayer validation.
"""
import pathlib, sys, struct, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / '.tools'))
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_MEM_WRITE
from unicorn.x86_const import *
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

path = pathlib.Path(sys.argv[1])
data = path.read_bytes()
pe = pefile.PE(data=data)
manifest = json.loads(path.with_suffix('.probe.json').read_text())
base = pe.OPTIONAL_HEADER.ImageBase
section = int(manifest['section_va'], 16)
cache = section + 0x2000
rng = section + 0x1ff0
ks = Ks(KS_ARCH_X86, KS_MODE_32)
STACK, RETURN, CONTEXT = 0x400f000, 0x4001000, 0x3000000
WEATHER, LIBRARY, FRAME, COM, WORLD = 0x3010000, 0x3050000, 0x3100000, 0x3200000, 0x3210000
checks = []

def fresh():
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    u.mem_map(base, pe.OPTIONAL_HEADER.SizeOfImage)
    for s in pe.sections:
        u.mem_write(base + s.VirtualAddress, s.get_data())
    u.mem_map(0x3000000, 0x300000)
    u.mem_map(0x4000000, 0x100000)
    u.reg_write(UC_X86_REG_ESP, STACK)
    # Game's statically linked CRT thread-local context accessor; only this
    # OS-dependent leaf is substituted. The actual rand arithmetic executes.
    u.mem_write(0x4c2f13, bytes(ks.asm(f'mov eax, {CONTEXT}; ret')[0]))
    dword(u, CONTEXT+20, 0x76543210)
    dword(u, 0x517000, WEATHER)
    u.mem_write(WEATHER+4, bytes([2])*65536)
    dword(u, 0x4f9de4, WORLD)
    dword(u, 0x572978, COM)
    dword(u, COM, COM+0x100)
    dword(u, COM+0x100+100, COM+0x1000)
    dword(u, COM+0x100+128, COM+0x1100)
    # COM Lock: supply an 8-bit 1152x864 surface with a real 1152-byte pitch.
    u.mem_write(COM+0x1000, bytes(ks.asm(f'''
        mov eax, dword ptr [esp+12]
        mov dword ptr [eax+16], 1152
        mov dword ptr [eax+36], {FRAME}
        xor eax, eax
        ret 20
    ''')[0]))
    u.mem_write(COM+0x1100, bytes(ks.asm('xor eax, eax; ret 8')[0]))
    return u

def dword(u, a, v): u.mem_write(a, struct.pack('<I', v & 0xffffffff))
def read(u, a): return struct.unpack('<I', u.mem_read(a, 4))[0]
def run(u, start, stop, budget=1000000):
    u.emu_start(start, stop, count=budget)
    assert u.reg_read(UC_X86_REG_EIP) == stop, f'Instruction budget exhausted at {u.reg_read(UC_X86_REG_EIP):x}'

# Invalid/sentinel, out-of-range and unloaded tile IDs must return without
# dereferencing a foreign COM pointer. Valid IDs must enter the original body.
for index, loaded in [(0xffff, False), (10000, False), (0, False), (9999, False), (0, True), (9999, True)]:
    u=fresh(); dword(u, STACK, RETURN); dword(u, STACK+4, index)
    u.reg_write(UC_X86_REG_ECX, LIBRARY); u.reg_write(UC_X86_REG_ESI, 0xabc123)
    if loaded:dword(u, LIBRARY+16+index*4, COM)
    stop = 0x48d578 if loaded else RETURN
    run(u, 0x48d570, stop)
    if not loaded:
        assert u.reg_read(UC_X86_REG_ESP)==STACK+28
        assert u.reg_read(UC_X86_REG_ESI)==0xabc123
    else:
        assert u.reg_read(UC_X86_REG_ESP)==STACK-20
checks.append('tile guards: 6 boundary/sentinel/null/valid cases')

# Pixel clear must write exactly one frame and preserve sentinel bytes around it.
u=fresh(); size=1152*864
u.mem_write(FRAME-16, b'B'*16+b'X'*size+b'A'*16)
for a,v in [(0x4f75e8,FRAME),(0x4f75f4,1152),(0x4f75f0,864)]:dword(u,a,v)
run(u,0x4a3d6b,0x4a3d70)
assert bytes(u.mem_read(FRAME,size))==b'\0'*size
assert bytes(u.mem_read(FRAME-16,16))==b'B'*16 and bytes(u.mem_read(FRAME+size,16))==b'A'*16
assert u.reg_read(UC_X86_REG_ESP)==STACK+4
checks.append('frame clear: 995328 bytes, surrounding guards preserved')

# All 972 cells execute their real weather update. The 400 original cells
# retain the old embedded cache, and 572 new cells preserve the game RNG.
u=fresh(); initial_seed=read(u,CONTEXT+20)
for y in range(27):
    for x in range(36):
        u.reg_write(UC_X86_REG_ESP,STACK)
        u.reg_write(UC_X86_REG_ESI,y);u.reg_write(UC_X86_REG_EDI,x)
        seed=read(u,CONTEXT+20)
        run(u,0x4a3f0d,0x4a3f6c)
        assert u.reg_read(UC_X86_REG_ESP)==STACK
        assert u.reg_read(UC_X86_REG_ESI)==y and u.reg_read(UC_X86_REG_EDI)==x
        original_cell=x<25 and y<16
        slot=WEATHER+0x1000c+(25*y+x)*132 if original_cell else cache+(36*y+x)*132
        assert bytes(u.mem_read(slot+4,1))==b'\x01',f'Inactive weather cell {x},{y}'
        if not original_cell:assert read(u,CONTEXT+20)==seed,f'Game RNG changed at extra cell {x},{y}'
assert read(u,CONTEXT+20)!=initial_seed
checks.append('weather update: 400 original + 572 extra cells, stack/register/RNG checks')

# Out-of-map cells are deactivated without indexing outside the 256x256 grid.
for camera in [(-100,0),(256,0),(0,256)]:
    u=fresh();dword(u,0x5812e8,camera[0]);dword(u,0x5812ec,camera[1])
    u.reg_write(UC_X86_REG_ESI,26);u.reg_write(UC_X86_REG_EDI,35)
    run(u,0x4a3f0d,0x4a3f6c)
    assert bytes(u.mem_read(cache+(26*36+35)*132+4,1))==b'\0'
checks.append('weather grid: negative/out-of-map camera bounds')

# Execute the real weather raster function at opposite screen corners.
# Hook writes to measure the framebuffer addresses, including all eight trail pixels.
for x,y,kind in [(11,7,0),(1141,855,0),(1141,855,2),(0,0,0),(1142,856,0)]:
    u=fresh();slot=cache
    dword(u,slot+8,1);u.mem_write(slot+12,bytes([1,kind,1,0]));dword(u,slot+16,x);dword(u,slot+20,y)
    u.reg_write(UC_X86_REG_ECX,slot);dword(u,STACK,RETURN)
    writes=[]
    def written(uc,access,address,size,value,user):
        if FRAME-0x1000 <= address < FRAME+1152*864+0x1000:writes.append((address,size))
    u.hook_add(UC_HOOK_MEM_WRITE,written)
    run(u,0x476e50,RETURN)
    assert all(FRAME<=a and a+n<=FRAME+1152*864 for a,n in writes),str(writes)
    if 10<x<1142 and 6<y<856:
        assert len(writes)==8,(x,y,writes)
        assert any(a==FRAME+y*1152+x for a,n in writes),(x,y,writes)
    else:assert not writes
checks.append('weather raster: actual x86 routine, 5 corner/clipping cases, 8-pixel trails')

# The extra draw pass must preserve the game's CRT seed even when particles draw.
u=fresh();slot=cache+(26*36+35)*132
dword(u,slot+8,1);u.mem_write(slot+4,b'\x01');u.mem_write(slot+12,bytes([1,0,1,0]));dword(u,slot+16,900);dword(u,slot+20,550)
seed=read(u,CONTEXT+20)
u.reg_write(UC_X86_REG_ECX,WEATHER)
run(u,0x4a445b,0x4a4460)
assert read(u,CONTEXT+20)==seed and u.reg_read(UC_X86_REG_ESP)==STACK
checks.append('extra weather draw: random stream and stack preserved')

# Clamp every edge, and do not produce negative camera coordinates on small maps.
for width,height,x,y,expected in [(256,256,999,999,(220,229)),(20,10,1,1,(0,0)),(80,80,-1,-1,(0,0)),(80,80,20,20,(20,20))]:
    u=fresh();u.mem_write(WORLD+230,struct.pack('<HH',width,height));dword(u,0x5812e8,x);dword(u,0x5812ec,y)
    run(u,0x4a3d40,0x4a3d45)
    assert (read(u,0x5812e8),read(u,0x5812ec))==expected
checks.append('camera: edges, negative coordinates and maps smaller than viewport')

u=fresh();u.reg_write(UC_X86_REG_ECX,736)
run(u,0x402c9e,0x402caa)
assert read(u,0x4f9db0)==176 and read(u,0x4f9db4)==736
checks.append('HUD drawing anchor: x=176, y=736')

# Execute both real container paths with a child that records the coordinates
# it receives. Drawing and hit testing must share exactly the same positions,
# including restoration of the parent anchor and the seven-argument ABI.
PARENT, CHILD, CAPTURE = 0x3220000, 0x3230000, CONTEXT+0x400
for entry,virtual,cleanup in [(0x49edf0,0,36),(0x49efc0,24,36),(0x49eb80,0,36)]:
    for group in [None,0x50313c,0x5030d4]:
        u=fresh();dword(u,STACK,RETURN)
        for i in range(7):dword(u,STACK+4+i*4,COM if i==1 else 0)
        dword(u,PARENT+16,30);dword(u,PARENT+20,480)
        dword(u,PARENT+0x1640,1);u.mem_write(PARENT+0x1608,b'\x01')
        dword(u,PARENT+0x13b0,CHILD);dword(u,PARENT+0x1478,10);dword(u,PARENT+0x147c,5)
        dword(u,CHILD,CHILD+0x500);dword(u,CHILD+0x500+virtual,CHILD+0x1000)
        if entry==0x49eb80:dword(u,CHILD+0x500+24,CHILD+0x1000)
        u.mem_write(CHILD+0x1000,bytes(ks.asm(f'''
            mov eax, dword ptr [esp+12]
            mov dword ptr [{CAPTURE}], eax
            mov eax, dword ptr [esp+16]
            mov dword ptr [{CAPTURE+4}], eax
            mov eax, 1
            ret {cleanup}
        ''')[0]))
        if group:dword(u,group,PARENT)
        u.reg_write(UC_X86_REG_ECX,PARENT)
        try:run(u,entry,RETURN)
        except Exception as error:
            raise RuntimeError(f'UI entry {entry:x} group={group}, EIP={u.reg_read(UC_X86_REG_EIP):x}, ESP={u.reg_read(UC_X86_REG_ESP):x}') from error
        assert (read(u,CAPTURE),read(u,CAPTURE+4))==((216,749) if group==0x50313c else ((216,485) if group else (40,485)))
        assert (read(u,PARENT+16),read(u,PARENT+20))==(30,480)
        assert u.reg_read(UC_X86_REG_ESP)==STACK+32
checks.append('HUD containers: drawing/tooltips translated; resource icons stay at top; menus unchanged')

for caller,expected in [(0x4a58f6,(276,500)),(0x4a5146,(100,500))]:
    u=fresh();dword(u,STACK,caller);dword(u,STACK+8,100);dword(u,STACK+12,500)
    run(u,0x428f70,0x428f78)
    assert (read(u,STACK+8),read(u,STACK+12))==expected
checks.append('Resource numbers: horizontal translation only, same top row as icons')

# Real click dispatch (49f6c0), real button event handler (499e60), and
# real point/rectangle test. Earlier tooltip tests did not exercise clicks.
EVENT, RESULT = CONTEXT+0x600, CONTEXT+0x700
for group in [None,0x50313c,0x50310c,0x503110]:
    u=fresh();dword(u,STACK,RETURN)
    for i,v in enumerate([RESULT,EVENT,0]):dword(u,STACK+4+i*4,v)
    dword(u,PARENT+0x13b0,CHILD)
    dword(u,PARENT+0x1478,675);dword(u,PARENT+0x147c,520)
    dword(u,CHILD,CHILD+0x500);dword(u,CHILD+0x500+28,0x499e60)
    dword(u,CHILD+0x19c,1)
    for i,v in enumerate([0,0,40,40]):dword(u,CHILD+0x84+i*4,v)
    for i,v in enumerate([879,789,1,0,0]):dword(u,EVENT+i*4,v)
    if group:dword(u,group,PARENT)
    u.reg_write(UC_X86_REG_ECX,PARENT)
    run(u,0x49f6c0,RETURN)
    assert read(u,CHILD+0x16c)==(1 if group else 0),(group,read(u,CHILD+0x16c))
    assert (read(u,PARENT+16),read(u,PARENT+20))==(0,0)
    assert u.reg_read(UC_X86_REG_ESP)==STACK+16
    u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ECX,PARENT)
    dword(u,EVENT+8,2)
    run(u,0x49f6c0,RETURN)
    assert read(u,CHILD+0x16c)==0
    assert read(u,RESULT)&0xffff==(1 if group else 0),(group,read(u,RESULT))
    if group:assert read(u,RESULT+8)==CHILD
checks.append('Actual HUD press/release at x=879,y=789 emits click result in all three command containers')

# Inverse HUD silhouette mapping, including the playable strips beside HUD.
for x,y,mask,expected in [(879,789,1,0),(879,789,0,1),(175,789,1,1),(976,789,1,1),(1151,863,1,1),(800,563,1,1),(1152,500,0,0),(-1,500,0,0),(400,864,0,0)]:
    u=fresh();dword(u,STACK,RETURN);dword(u,STACK+4,x);dword(u,STACK+8,y)
    if 176<=x<976 and 564<=y<864:u.mem_write(0x5308c8+(y-564)*800+x-176,bytes([mask]))
    run(u,0x48ed10,RETURN)
    assert u.reg_read(UC_X86_REG_EAX)==expected,(x,y,mask)
    assert u.reg_read(UC_X86_REG_ESP)==STACK+4
checks.append('HUD silhouette: inverse mapping, transparent holes, playable side strips, screen bounds')

for entry,stop in [(0x4bcd27,0x4bcd2e),(0x4bcdd7,0x4bcdde)]:
    for slot in [0,3,5]:
        u=fresh();u.reg_write(UC_X86_REG_EDI,slot);u.reg_write(UC_X86_REG_ESI,CHILD)
        u.reg_write(UC_X86_REG_EAX,176);u.reg_write(UC_X86_REG_ECX,433)
        dword(u,STACK+36,4)
        run(u,entry,stop)
        assert read(u,CHILD+24)==(352 if slot==3 else 176)
        assert u.reg_read(UC_X86_REG_ECX)==(697 if slot==3 else 433)
        assert u.reg_read(UC_X86_REG_EAX)==4 and u.reg_read(UC_X86_REG_ESP)==STACK
checks.append('Portrait: both video creation paths translate only HUD slot three')

u=fresh();dword(u,0x5812e8,98);dword(u,0x5812ec,13)
u.reg_write(UC_X86_REG_EDI,WORLD)
u.mem_write(COM+0x1800,bytes(ks.asm('mov eax, [esp+4]; mov edx, [esp+8]; mov [eax], edx; mov edx, [esp+12]; mov [eax+4], edx; mov edx, [esp+16]; mov [eax+8], edx; mov edx, [esp+20]; mov [eax+12], edx; ret 20')[0]))
dword(u,0x4cb254,COM+0x1800)
run(u,0x48cab7,0x48caef)
assert tuple(read(u,WORLD+0x70f8+i*4) for i in range(4))==(3136,416,4287,1279)
checks.append('Shared unit visibility rectangle: world origin plus 1151x863, not 799x599')

for mode,span in [(0,(72,54)),(1,(36,27)),(2,(36,27)),(3,(18,14)),(4,(18,14))]:
    u=fresh();dword(u,0x4f9db8,mode);dword(u,0x4f9dd0,256);dword(u,0x4f9dd4,582)
    dword(u,0x4f9dd8,384);dword(u,0x4f9ddc,710)
    dword(u,0x5812e8,20);dword(u,0x5812ec,10)
    run(u,0x4a5531,0x4a55d5)
    left,top=read(u,0x4f9dc0),read(u,0x4f9dc4)
    right,bottom=u.reg_read(UC_X86_REG_ECX)+1,u.reg_read(UC_X86_REG_EAX)
    assert (right-left,bottom-top)==span,(mode,left,top,right,bottom)
checks.append('minimap camera border: all five existing projection modes')

u=fresh();dword(u,0x4f9db8,0);dword(u,0x4f9dd0,256);dword(u,0x4f9dd4,582)
dword(u,0x4f9dd8,288);dword(u,0x4f9ddc,602)
run(u,0x4a5531,0x4a55d5)
assert u.reg_read(UC_X86_REG_ECX)+1==288 and u.reg_read(UC_X86_REG_EAX)==602
checks.append('minimap camera border: clipped to maps smaller than viewport')

# Execute all real fog preparation, lookup, neighbor and cache routines.
# Uniform unseen/explored/visible fields exercise the player's existing policy;
# enlarging the viewport must never reveal or mutate the underlying fog grid.
for visibility in (0,1,2):
    u=fresh()
    grid=struct.pack('<H',visibility)* (272*264)
    u.mem_write(WORLD,grid);u.mem_write(WORLD+0x23100,b'\x01')
    fog_start=WORLD+0x2418a
    u.mem_write(fog_start,b'\xa5'*(264*264*2))
    dword(u,STACK,RETURN);dword(u,STACK+4,10*32);dword(u,STACK+8,10*32)
    u.reg_write(UC_X86_REG_ECX,WORLD)
    before=bytes(u.mem_read(WORLD,len(grid)))
    run(u,0x42b4a0,RETURN,3000000)
    assert bytes(u.mem_read(WORLD,len(grid)))==before,'Fog preparation changed explored/visible state'
    for x in range(10,46):
        for y in range(10,37):
            value=struct.unpack('<h',u.mem_read(fog_start+(264*x+y)*2,2))[0]
            assert value==visibility*20,(visibility,x,y,value)
    for x,y in [(9,10),(46,10),(10,9),(10,37)]:
        assert bytes(u.mem_read(fog_start+(264*x+y)*2,2))==b'\xa5\xa5'
    assert u.reg_read(UC_X86_REG_ESP)==STACK+12
checks.append('Fog preparation: all 36x27 cells, three visibility states, real neighbor/cache routines, outside guards and fog state preserved')

report={'kind':'machine-code-emulation','executable_hash':manifest['output_hash'],'checks':checks,'gameplay_validated':False,'multiplayer_validated':False}
out=path.parent/'probe-verification.json';out.write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
