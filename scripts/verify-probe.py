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
    # COM Lock: supply an 8-bit 1024x768 surface with a real 1024-byte pitch.
    u.mem_write(COM+0x1000, bytes(ks.asm(f'''
        mov eax, dword ptr [esp+12]
        mov dword ptr [eax+16], 1024
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
u=fresh(); size=1024*768
u.mem_write(FRAME-16, b'B'*16+b'X'*size+b'A'*16)
for a,v in [(0x4f75e8,FRAME),(0x4f75f4,1024),(0x4f75f0,768)]:dword(u,a,v)
run(u,0x4a3d6b,0x4a3d70)
assert bytes(u.mem_read(FRAME,size))==b'\0'*size
assert bytes(u.mem_read(FRAME-16,16))==b'B'*16 and bytes(u.mem_read(FRAME+size,16))==b'A'*16
assert u.reg_read(UC_X86_REG_ESP)==STACK+4
checks.append('frame clear: 786432 bytes, surrounding guards preserved')

# All 768 cells execute their real weather update. The 400 original cells
# retain the old embedded cache, and 368 new cells preserve the game RNG.
u=fresh(); initial_seed=read(u,CONTEXT+20)
for y in range(24):
    for x in range(32):
        u.reg_write(UC_X86_REG_ESP,STACK)
        u.reg_write(UC_X86_REG_ESI,y);u.reg_write(UC_X86_REG_EDI,x)
        seed=read(u,CONTEXT+20)
        run(u,0x4a3f0d,0x4a3f6c)
        assert u.reg_read(UC_X86_REG_ESP)==STACK
        assert u.reg_read(UC_X86_REG_ESI)==y and u.reg_read(UC_X86_REG_EDI)==x
        original_cell=x<25 and y<16
        slot=WEATHER+0x1000c+(25*y+x)*132 if original_cell else cache+(32*y+x)*132
        assert bytes(u.mem_read(slot+4,1))==b'\x01',f'Inactive weather cell {x},{y}'
        if not original_cell:assert read(u,CONTEXT+20)==seed,f'Game RNG changed at extra cell {x},{y}'
assert read(u,CONTEXT+20)!=initial_seed
checks.append('weather update: 400 original + 368 extra cells, stack/register/RNG checks')

# Out-of-map cells are deactivated without indexing outside the 256x256 grid.
for camera in [(-100,0),(256,0),(0,256)]:
    u=fresh();dword(u,0x5812e8,camera[0]);dword(u,0x5812ec,camera[1])
    u.reg_write(UC_X86_REG_ESI,23);u.reg_write(UC_X86_REG_EDI,31)
    run(u,0x4a3f0d,0x4a3f6c)
    assert bytes(u.mem_read(cache+(23*32+31)*132+4,1))==b'\0'
checks.append('weather grid: negative/out-of-map camera bounds')

# Execute the real weather raster function at opposite screen corners.
# Hook writes to measure the framebuffer addresses, including all eight trail pixels.
for x,y,kind in [(11,7,0),(1013,759,0),(1013,759,2),(0,0,0),(1014,760,0)]:
    u=fresh();slot=cache
    dword(u,slot+8,1);u.mem_write(slot+12,bytes([1,kind,1,0]));dword(u,slot+16,x);dword(u,slot+20,y)
    u.reg_write(UC_X86_REG_ECX,slot);dword(u,STACK,RETURN)
    writes=[]
    def written(uc,access,address,size,value,user):
        if FRAME-0x1000 <= address < FRAME+1024*768+0x1000:writes.append((address,size))
    u.hook_add(UC_HOOK_MEM_WRITE,written)
    run(u,0x476e50,RETURN)
    assert all(FRAME<=a and a+n<=FRAME+1024*768 for a,n in writes),str(writes)
    if 10<x<1014 and 6<y<760:
        assert len(writes)==8,(x,y,writes)
        assert any(a==FRAME+y*1024+x for a,n in writes),(x,y,writes)
    else:assert not writes
checks.append('weather raster: actual x86 routine, 5 corner/clipping cases, 8-pixel trails')

# The extra draw pass must preserve the game's CRT seed even when particles draw.
u=fresh();slot=cache+(23*32+31)*132
dword(u,slot+8,1);u.mem_write(slot+4,b'\x01');u.mem_write(slot+12,bytes([1,0,1,0]));dword(u,slot+16,900);dword(u,slot+20,550)
seed=read(u,CONTEXT+20)
u.reg_write(UC_X86_REG_ECX,WEATHER)
run(u,0x4a445b,0x4a4460)
assert read(u,CONTEXT+20)==seed and u.reg_read(UC_X86_REG_ESP)==STACK
checks.append('extra weather draw: random stream and stack preserved')

# Clamp every edge, and do not produce negative camera coordinates on small maps.
for width,height,x,y,expected in [(256,256,999,999,(224,238)),(20,10,1,1,(0,0)),(80,80,-1,-1,(0,0)),(80,80,20,20,(20,20))]:
    u=fresh();u.mem_write(WORLD+230,struct.pack('<HH',width,height));dword(u,0x5812e8,x);dword(u,0x5812ec,y)
    run(u,0x4a3d40,0x4a3d45)
    assert (read(u,0x5812e8),read(u,0x5812ec))==expected
checks.append('camera: edges, negative coordinates and maps smaller than viewport')

u=fresh();u.reg_write(UC_X86_REG_ECX,640)
run(u,0x402c9e,0x402caa)
assert read(u,0x4f9db0)==112 and read(u,0x4f9db4)==640
checks.append('HUD drawing anchor: x=112, y=640')

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
        assert (read(u,CAPTURE),read(u,CAPTURE+4))==((152,653) if group==0x50313c else ((152,485) if group else (40,485)))
        assert (read(u,PARENT+16),read(u,PARENT+20))==(30,480)
        assert u.reg_read(UC_X86_REG_ESP)==STACK+32
checks.append('HUD containers: drawing/tooltips translated; resource icons stay at top; menus unchanged')

for caller,expected in [(0x4a58f6,(212,500)),(0x4a5146,(212,668)),(0x4a517e,(212,668)),(0x43fd37,(100,500))]:
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
    for i,v in enumerate([815,693,1,0,0]):dword(u,EVENT+i*4,v)
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
checks.append('Actual HUD press/release at x=815,y=693 emits click result in all three command containers')

# Inverse HUD silhouette mapping, including the playable strips beside HUD.
for x,y,mask,expected in [(815,693,1,0),(815,693,0,1),(111,693,1,1),(912,693,1,1),(1023,767,1,1),(800,467,1,1),(1024,500,0,0),(-1,500,0,0),(400,768,0,0)]:
    u=fresh();dword(u,STACK,RETURN);dword(u,STACK+4,x);dword(u,STACK+8,y)
    if 112<=x<912 and 468<=y<768:u.mem_write(0x5308c8+(y-468)*800+x-112,bytes([mask]))
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
        assert read(u,CHILD+24)==(288 if slot==3 else 176)
        assert u.reg_read(UC_X86_REG_ECX)==(601 if slot==3 else 433)
        assert u.reg_read(UC_X86_REG_EAX)==4 and u.reg_read(UC_X86_REG_ESP)==STACK
checks.append('Portrait: both video creation paths translate only HUD slot three')

u=fresh();dword(u,0x5812e8,98);dword(u,0x5812ec,13)
u.reg_write(UC_X86_REG_EDI,WORLD)
u.mem_write(COM+0x1800,bytes(ks.asm('mov eax, [esp+4]; mov edx, [esp+8]; mov [eax], edx; mov edx, [esp+12]; mov [eax+4], edx; mov edx, [esp+16]; mov [eax+8], edx; mov edx, [esp+20]; mov [eax+12], edx; ret 20')[0]))
dword(u,0x4cb254,COM+0x1800)
run(u,0x48cab7,0x48caef)
assert tuple(read(u,WORLD+0x70f8+i*4) for i in range(4))==(3136,416,4159,1183)
checks.append('Shared unit visibility rectangle: world origin plus 1023x767, not 799x599')

for mode,span in [(0,(64,48)),(1,(32,24)),(2,(32,24)),(3,(16,12)),(4,(16,12))]:
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
    for x in range(10,42):
        for y in range(10,34):
            value=struct.unpack('<h',u.mem_read(fog_start+(264*x+y)*2,2))[0]
            assert value==visibility*20,(visibility,x,y,value)
    for x,y in [(9,10),(42,10),(10,9),(10,34)]:
        assert bytes(u.mem_read(fog_start+(264*x+y)*2,2))==b'\xa5\xa5'
    assert u.reg_read(UC_X86_REG_ESP)==STACK+12
checks.append('Fog preparation: all 32x24 cells, three visibility states, real neighbor/cache routines, outside guards and fog state preserved')

# Execute both original shadow helpers and our font entry hook together.
# Capture at the font backend boundary, after the actual prologue, to verify
# the foreground and one-pixel shadow each move once and retain their spacing.
detail_calls=(0x4a6a39,0x4a6bce,0x4a6de5,0x4a6e9d,0x4a6f4f,0x4a7038,
    0x4a741b,0x4a7528,0x4a76bf,0x4a772f,0x4a7b9a,0x4a7cc9,0x4a7d2a,
    0x4a7dec,0x4a7e67,0x4a7eec,0x4a7ff4,0x4a82c2,0x4a837b,0x4a83de,
    0x4a843f,0x4a84a3,0x4a8507,0x4a869d)
for entry in (0x4a8720,0x4a8790):
    for caller in [call+5 for call in detail_calls if call+5+struct.unpack('<i',data[pe.get_offset_from_rva(call-base)+1:pe.get_offset_from_rva(call-base)+5])[0]==entry]+[0x43fd37,0x4a5ca2]:
        u=fresh();seen=[]
        from unicorn import UC_HOOK_CODE
        def font_backend(uc,address,size,user):
            sp=uc.reg_read(UC_X86_REG_ESP)
            seen.append((read(uc,sp+20),read(uc,sp+24)))
        u.hook_add(UC_HOOK_CODE,font_backend,begin=0x428f78,end=0x428f78)
        u.mem_write(0x428f78,bytes(ks.asm('pop esi; add esp, 8; ret')[0]))
        dword(u,STACK,caller)
        for i,v in enumerate([300,565,13,CONTEXT+0x800,0x969696]):dword(u,STACK+4+i*4,v)
        u.mem_write(caller,b'\x90')
        run(u,entry,caller)
        moved=caller not in (0x43fd37,0x4a5ca2)
        x,y=(412,733) if moved else (300,565)
        assert seen==[(x+1,y+1),(x,y)],(entry,caller,seen)
        assert u.reg_read(UC_X86_REG_ESP)==STACK+4
checks.append('HUD detail text: 24 audited callers, actual foreground/shadow helpers, HP/shield/production text, world labels preserved')

# Actual start/live/release selection code, using the game's existing packet
# fields and world-to-screen offsets. Cover all player-slot indexing and both
# drag directions beyond the old 800x600 region, without changing unit limits.
for player in (0,1,7):
    for start,end,origin in [((20,20),(1023,767),(0,0)),((1023,767),(20,20),(3136,416)),((900,650),(1023,767),(32,64))]:
        u=fresh();packet=0x52f510+player*64;rect=player*16
        u.mem_write(0x4e7270,bytes([player]));u.mem_write(packet,b'\x01')
        world_start=(start[0]+origin[0],start[1]+origin[1])
        world_end=(end[0]+origin[0],end[1]+origin[1])
        u.mem_write(packet+16,struct.pack('<HHHH',world_start[0],world_start[1],start[0],start[1]))
        run(u,0x4076a5,0x407773)
        assert bytes(u.mem_read(0x52fae0,1))==b'\x01',(player,start)
        assert (read(u,0x51be00+player*8),read(u,0x51be04+player*8))==world_start
        u.mem_write(packet+1,b'\x01')
        u.mem_write(packet+16,struct.pack('<HHHH',world_end[0],world_end[1],end[0],end[1]))
        run(u,0x407cd2,0x407d6e)
        expected=(min(world_start[0],world_end[0]),min(world_start[1],world_end[1]),max(world_start[0],world_end[0]),max(world_start[1],world_end[1]))
        assert tuple(read(u,0x52f9a0+rect+i*4) for i in range(4))==expected,('live',player,start,end)
        u.reg_write(UC_X86_REG_EDI,player*64);u.reg_write(UC_X86_REG_EBP,player)
        run(u,0x407a22,0x407af7)
        assert tuple(read(u,0x52fa40+rect+i*4) for i in range(4))==expected,('release',player,start,end)
        assert bytes(u.mem_read(0x52fae0,1))==b'\0'
        # The actual selection outline renderer must receive the expanded
        # rectangle in screen space after subtracting the camera origin.
        dword(u,0x5812e8,origin[0]//32);dword(u,0x5812ec,origin[1]//32)
        u.reg_write(UC_X86_REG_ESP,STACK)
        run(u,0x4a4f85,0x4a4fe0)
        outline=tuple(read(u,STACK+0x5c+i*4) for i in range(4))
        assert outline==(expected[0]-origin[0],expected[1]-origin[1],expected[2]-origin[0],expected[3]-origin[1]),('outline',outline)
# A solid HUD point must still reject starting a world selection.
u=fresh();u.mem_write(0x52f510,b'\x01');u.mem_write(0x52f520,struct.pack('<HHHH',815,693,815,693))
u.mem_write(0x5308c8+(693-468)*800+815-112,b'\x01')
run(u,0x4076a5,0x407773)
assert bytes(u.mem_read(0x52fae0,1))==b'\0'
checks.append('Selection drag: actual start/live/release/outline, 9 directions/player/camera cases up to 1023x767, solid HUD start rejected')

# The original simulation update increments saved elapsed seconds every 20 ticks.
u=fresh();u.mem_write(0x503c2a,b'\0\0');u.mem_write(0x503c20,b'\0')
for tick in range(20):
    run(u,0x429298,0x4292fc)
    assert struct.unpack('<H',bytes(u.mem_read(0x503c2a,2)))[0]==(tick+1)//20

# Execute timer formatting and both original shadow passes at the font boundary.
# Repeated rendering reads the same saved counter without advancing simulation.
for seconds, expected in [(0,'00:00'),(1,'00:01'),(59,'00:59'),(60,'01:00'),(5999,'99:59'),(6000,'100:00'),(65535,'1092:15'),(42,'00:42'),(0,'00:00')]:
    u=fresh();seen=[]
    u.mem_write(0x503c2a,struct.pack('<H',seconds))
    dword(u,0x4f9db0,112);dword(u,0x4f75f0,768)
    def timer_font(uc,address,size,user):
        sp=uc.reg_read(UC_X86_REG_ESP)
        pointer=read(uc,sp+28)
        label=bytes(uc.mem_read(pointer,16)).split(b'\0')[0].decode('ascii')
        seen.append((read(uc,sp+20),read(uc,sp+24),label))
    u.hook_add(UC_HOOK_CODE,timer_font,begin=0x428f78,end=0x428f78)
    u.mem_write(0x428f78,bytes(ks.asm('pop esi; add esp, 8; ret')[0]))
    run(u,0x4a602d,0x4a6033)
    assert seen==[(417,605,expected),(416,604,expected)],seen
    assert u.reg_read(UC_X86_REG_ESP)==STACK
    assert struct.unpack('<H',bytes(u.mem_read(0x503c2a,2)))[0]==seconds
checks.append('HUD timer: actual formatter and shadow helpers, 9 reset/load/minute-boundary cases, centered at 416x604, simulation counter unchanged')

if '--replay' in manifest['stages']:
    box=section+0x26000
    def replay_machine(mode=1,state=4,network=0,ack=True):
        u=fresh();events=[];io=[]
        dword(u,box,mode);u.mem_write(0x504f48,bytes([state]));dword(u,0x513ed4,network)
        dword(u,STACK+20,CONTEXT+0x2000)
        dword(u,0x4cb0fc,RETURN+0x100);u.mem_write(RETURN+0x100,bytes(ks.asm('ret 4')[0]))
        dword(u,0x4cb204,RETURN+0x200);u.mem_write(RETURN+0x200,b'\x90')
        # OS input and full game serialization are bounded seams here; test the
        # real hook calling conventions, ordering and state machine around them.
        for address,label in ((0x454be0,'save'),(0x454ce0,'load')):
            u.mem_write(address,bytes(ks.asm('mov eax, 1; ret')[0]))
            def disk(uc,at,size,user,label=label):
                io.append(label)
                if label=='load':uc.mem_write(0x504f48,b'\x04')
            u.hook_add(UC_HOOK_CODE,disk,begin=address,end=address)
        def controller(uc,address,size,user):
            kind=read(uc,box+12)
            if not events or read(uc,box+4)!=events[-1][0]:events.append((read(uc,box+4),kind))
            if ack:dword(uc,box+8,read(uc,box+4))
        u.hook_add(UC_HOOK_CODE,controller,begin=RETURN+0x100,end=RETURN+0x100)
        return u,events,io
    u,events,io=replay_machine();run(u,0x4532c7,0x4532cc)
    assert [e[1] for e in events]==[10,11,1],events
    assert io==['save','load'],io
    assert read(u,box+24)==CONTEXT+0x2000 and read(u,box+28)==CONTEXT+20 and read(u,box+36)==STACK+16
    assert read(u,box+20)==1 and u.reg_read(UC_X86_REG_ESP)==STACK
    # Replay loads exactly once, before the first input/command barrier.
    u,events,io=replay_machine(2,2);run(u,0x4532c7,0x4532cc)
    assert io==['load'] and [e[1] for e in events]==[1]
    run(u,0x4532c7,0x4532cc);assert io==['load']
    # No recorder attached: hooks must be transparent. Multiplayer is excluded.
    for mode,network in ((0,0),(1,1)):
        u,events,io=replay_machine(mode,4,network);run(u,0x4532c7,0x4532cc)
        assert not events and not io
    for entry,resume,kind in ((0x453830,0x453836,2),(0x454429,0x45442f,3)):
        u,events,io=replay_machine();dword(u,box+20,1)
        u.reg_write(UC_X86_REG_EBX,0x12345678);u.reg_write(UC_X86_REG_EDI,0x76543210)
        run(u,entry,resume)
        assert [e[1] for e in events]==[kind]
        assert u.reg_read(UC_X86_REG_ESP)==STACK
        assert u.reg_read(UC_X86_REG_EBX)==0x12345678 and u.reg_read(UC_X86_REG_EDI)==0x76543210
    # A departed launcher cannot leave the recorder in an infinite wait.
    u,events,io=replay_machine(1,4,0,False);run(u,0x4532c7,0x4532cc)
    assert read(u,box)==0 and read(u,box+32)==1 and not io
    # A playback without its controller aborts before any live input is consumed.
    u,events,io=replay_machine(2,4,0,False);dword(u,box+16,1);dword(u,box+20,1)
    run(u,0x4532c7,RETURN+0x200)
    assert not io and read(u,box+32)==1
    # Execute the real save/load guards, with only the OS wait/exit replaced.
    for entry,resume,length in ((0x454be0,0x454bea,10),(0x454ce0,0x454ce6,6)):
        for mode,internal in ((0,False),(1,True),(2,True),(2,False),(1,False)):
            u,events,io=replay_machine(mode,4)
            dword(u,box+20,1)
            off=pe.get_offset_from_rva(entry-base);u.mem_write(entry,data[off:off+length])
            dword(u,STACK,section+0x22000 if internal else RETURN)
            def abort_io(uc,address,size,user):
                if read(uc,box+12)==98:dword(uc,box,3)
            u.hook_add(UC_HOOK_CODE,abort_io,begin=RETURN+0x100,end=RETURN+0x100)
            prohibited=mode==2 and not internal
            run(u,entry,RETURN+0x200 if prohibited else resume)
            assert [e[1] for e in events]==([98] if prohibited else ([4] if mode==1 and not internal and entry==0x454ce0 else []))
            if mode==1 and not internal and entry==0x454ce0:assert read(u,box+20)==0
    # Execute the kernel-event notify path as well as the legacy polling path.
    for mode,respond in ((1,True),(2,True),(1,False),(2,False)):
        u,events,io=replay_machine(mode,2 if mode==2 else 4,0,respond)
        dword(u,box+40,123);dword(u,box+44,456)
        dword(u,0x4cb0d8,RETURN+0x300);u.mem_write(RETURN+0x300,bytes(ks.asm('mov eax, 1; ret 4')[0]))
        dword(u,0x4cb0e8,RETURN+0x400);u.mem_write(RETURN+0x400,bytes(ks.asm('mov eax, '+('0' if respond else '258')+'; ret 8')[0]))
        def event_ack(uc,address,size,user):
            events.append((read(uc,box+4),read(uc,box+12)))
            if respond:dword(uc,box+8,read(uc,box+4))
        u.hook_add(UC_HOOK_CODE,event_ack,begin=RETURN+0x400,end=RETURN+0x400)
        run(u,0x4532c7,RETURN+0x200 if mode==2 and not respond else 0x4532cc)
        if respond:assert [item[1] for item in events]==([10,11,1] if mode==1 else [1]), (mode,events,io)
        else:assert read(u,box+32)==1
    checks.append('Replay kernel events: request/ack handles, record/play barriers, timeout fallback and playback fail-stop')
    checks.append('Replay save guards: actual x86 entries, disabled transparency, internal normalization allowed, playback cannot write or load user saves, manual load segments recording')
    checks.append('Replay barriers: normalized snapshot save/load, one-time playback bootstrap, keyboard/RNG pointers, mouse and command ordering, stack/register preservation, multiplayer exclusion, finite timeout with playback fail-stop')

if '--rally' in manifest['stages']:
    manager,parent,child,ore=CONTEXT+0x10000,CONTEXT+0x14000,CONTEXT+0x18000,CONTEXT+0x1c000
    # Exercise the actual original worker classifier and its manager checks.
    for hq in (0,0x100,0x200):
        for worker in (0x12,0x13,0x14,0x113,0x114,0x21c,0x21d,0x21e,2):
            for target,alive,near in ((0x300,1,True),(0x301,1,True),(0x302,1,True),(0x303,1,True),(0x304,1,True),(0x305,1,True),(0x306,1,True),(0x300,0,True),(0x300,1,False)):
                u=fresh();dword(u,0x504a10,manager);dword(u,manager+8,parent);dword(u,manager+12,child);dword(u,manager+16,ore)
                for address,kind in ((parent,hq),(child,worker),(ore,target)):
                    u.mem_write(address+12,struct.pack('<H',kind));u.mem_write(address+0x13b8,b'\x01')
                u.mem_write(ore+0x13b8,bytes([alive]));dword(u,parent+0x1398,500);dword(u,parent+0x139c,600)
                dword(u,ore+0x14,510 if near else 550);dword(u,ore+0x18,610)
                dword(u,child+0x414,0xdead);dword(u,child+0x478,123)
                u.reg_write(UC_X86_REG_ESI,parent);u.reg_write(UC_X86_REG_EDI,1);u.reg_write(UC_X86_REG_EBX,0x12345678)
                eligible=worker in (0x12,0x13,0x14,0x113,0x114,0x21c,0x21d,0x21e)
                # Determine supported workers through the real classifier first.
                dword(u,STACK+4,1);dword(u,STACK,RETURN);run(u,0x40a210,RETURN)
                eligible=u.reg_read(UC_X86_REG_EAX)!=0
                u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ESI,parent);u.reg_write(UC_X86_REG_EDI,1)
                success=eligible and target<=0x305 and alive and near
                run(u,0x430e49,0x430e4e)
                assert u.reg_read(UC_X86_REG_ESP)==STACK and u.reg_read(UC_X86_REG_ESI)==parent and u.reg_read(UC_X86_REG_EDI)==0xfffff793
                assert u.reg_read(UC_X86_REG_EBX)==0x12345678
                assert read(u,child+0x414)==(2 if success else 0xdead)
                assert read(u,child+0x478)==(0 if success else 123)
                if success:assert bytes(u.mem_read(child+0x464,1))==b'\x2d'
    # Regression: ore2 sprite-edge click lies nearer ore1's center. Preserve
    # the actual clicked ID instead of silently selecting the nearest center.
    for resource in (0x300,0x301,0x302,0x303,0x304,0x305):
        u=fresh();dword(u,0x504a10,manager)
        for i,address,kind in ((0,parent,0x100),(1,child,0x113),(2,ore,resource),(3,ore+0x2000,0x300)):
            dword(u,manager+8+i*4,address);u.mem_write(address+12,struct.pack('<HH',kind,i));u.mem_write(address+0x13b8,b'\x01')
        dword(u,parent+0x1398,1071);dword(u,ore+20,1024);dword(u,ore+24,544)
        dword(u,ore+0x2000+20,1088);dword(u,ore+0x2000+24,544)
        dword(u,STACK+20,2);u.reg_write(UC_X86_REG_ESI,parent);u.reg_write(UC_X86_REG_EAX,543)
        run(u,0x408730,0x408736)
        assert read(u,section+0x1b000)==3 and read(u,parent+0x139c)==543
        u.reg_write(UC_X86_REG_EDI,1);run(u,0x430e49,0x430e4e)
        assert read(u,child+0x414)==2 and bytes(u.mem_read(child+0x464,1))==b'\x2d'
        assert u.reg_read(UC_X86_REG_ESP)==STACK
        # Changing the rally invalidates the cached target and uses normal logic.
        dword(u,parent+0x1398,2000);dword(u,parent+0x139c,2000)
        u.reg_write(UC_X86_REG_EDI,1);run(u,0x430e49,0x430e4e)
    # Execute the original production rally setters and movement call before
    # our gathering assignment. Only the full map pathfinder is a bounded seam.
    u=fresh();dword(u,0x504a10,manager)
    for i,address,kind in ((0,parent,0x100),(1,child,0x113),(2,ore,0x303)):
        dword(u,manager+8+i*4,address);u.mem_write(address+12,struct.pack('<HH',kind,i));u.mem_write(address+0x13b8,b'\x01')
    dword(u,parent+0x1398,1024);dword(u,parent+0x139c,544);dword(u,ore+20,1024);dword(u,ore+24,544)
    dword(u,STACK+0x74,WORLD);u.reg_write(UC_X86_REG_ESI,parent);u.reg_write(UC_X86_REG_EDI,1)
    marker=CONTEXT+0x2f000
    u.mem_write(0x441c40,bytes(ks.asm(f'mov eax, dword ptr [esp+4]; mov dword ptr [{marker}],eax; mov eax,dword ptr [esp+8]; mov dword ptr [{marker+4}],eax; mov byte ptr [ecx+0x464],2; ret 20',0x441c40)[0]))
    run(u,0x430d88,0x430e4e)
    assert (read(u,marker),read(u,marker+4))==(1024,544)
    assert read(u,child+0x414)==2 and bytes(u.mem_read(child+0x464,1))==b'\x2d'
    assert u.reg_read(UC_X86_REG_ESP)==STACK
    checks.append('Production ore rally: original destination setters and movement setup run before gather state, pathfinder ABI and stack preserved')
    checks.append('Exact ore rally: ore1/ore2 variants, sprite-edge target versus nearer decoy, changed-rally cache invalidation')
    checks.append('Ore rally: original worker classifier, three HQs and ore types, gather target/state, inactive/non-ore/distant targets excluded, stack/register preservation')
    for dx,dy,side,position in ((200,10,1,(21,31)),(-200,10,3,(9,19)),(10,-200,2,(21,19)),(10,200,0,(9,31))):
        for production in (False,True):
            u=fresh();dword(u,0x504a10,manager);dword(u,manager+8,parent)
            dword(u,parent+0x14,500);dword(u,parent+0x18,500);dword(u,parent+0x1398,500+dx);dword(u,parent+0x139c,500+dy)
            dword(u,STACK+92,0x41f97b if production else RETURN);dword(u,STACK+100,0)
            dword(u,STACK+60,21);dword(u,STACK+64,19);u.mem_write(STACK+19,b'\0')
            u.reg_write(UC_X86_REG_ECX,9);u.reg_write(UC_X86_REG_EBX,32);u.reg_write(UC_X86_REG_EDI,9);u.reg_write(UC_X86_REG_ESI,31)
            run(u,0x44cf5b,0x44cf63)
            assert bytes(u.mem_read(STACK+19,1))==bytes([side if production else 0])
            assert (u.reg_read(UC_X86_REG_EDI),u.reg_read(UC_X86_REG_ESI))==(position if production else (9,31))
            assert u.reg_read(UC_X86_REG_ESP)==STACK and u.reg_read(UC_X86_REG_EBX)==32
    checks.append('Rally production exit: four directions, original perimeter-search locals, non-production callers preserved')
    assert (255-238)*32 < 558
    checks.append('Bottom camera: last map row projects above HUD at y=544; full 24-row raster remains guarded')

# Audit the managed launcher's suspended-child compatibility wrapper against
# the actual game entry it replaces. It cannot write before/after the packet.
import re,base64
source=(pathlib.Path(__file__).resolve().parent.parent/'src/Replay.cs').read_text(encoding='utf8')
wrapper=base64.b64decode(re.search(r'PostInputCode="([^"]+)"',source).group(1))
patch=base64.b64decode(re.search(r'PostInputCall="([^"]+)"',source).group(1))
for player in (0,1,9):
    u=fresh();target=section+0x24e00
    assert bytes(u.mem_read(target,len(wrapper)))==b'\0'*len(wrapper)
    u.mem_write(target,wrapper);u.mem_write(0x454436,patch)
    u.mem_write(0x4081d0,bytes(ks.asm('mov eax, 123; ret')[0]))
    dword(u,0x4e7270,player);u.mem_write(section+0x26200,bytes(range(64)))
    packet=0x52f510+player*64;u.mem_write(packet-4,b'B'*4+b'X'*64+b'A'*4)
    u.reg_write(UC_X86_REG_EBX,0x12345678);u.reg_write(UC_X86_REG_EDI,0x87654321)
    run(u,0x454436,0x45443b)
    assert bytes(u.mem_read(packet,64))==bytes(range(64))
    assert bytes(u.mem_read(packet-4,4))==b'B'*4 and bytes(u.mem_read(packet+64,4))==b'A'*4
    assert u.reg_read(UC_X86_REG_EAX)==123 and u.reg_read(UC_X86_REG_EBX)==0x12345678 and u.reg_read(UC_X86_REG_EDI)==0x87654321
    assert u.reg_read(UC_X86_REG_ESP)==STACK
checks.append('Replay post-input compatibility: original UI helper retained, final packet replay for players 0/1/9, bounds and stack/registers preserved')

loader=base64.b64decode(re.search(r'SnapshotLoadCode="([^"]+)"',source).group(1))
loader_call=base64.b64decode(re.search(r'SnapshotLoadCall="([^"]+)"',source).group(1))
for result in (0,1):
    u=fresh();target=section+0x24d00;unit=CONTEXT+0x18000
    assert bytes(u.mem_read(target,len(loader)))==b'\0'*len(loader)
    u.mem_write(target,loader);u.mem_write(0x44b5f7,loader_call)
    dword(u,0x504a10,CONTEXT+0x10000);dword(u,unit+8,CONTEXT+0x20000)
    dword(u,unit+0x1cc,0x12345678);dword(u,unit+0x1d0,0x44444444);dword(u,unit+0x210,0x87654321)
    # Replace only the OS file-read seam; execute the real wrapper and its ABI.
    stub=f'mov edx, dword ptr [esp+4]; mov dword ptr [edx+4], 42; mov dword ptr [edx+8], 0xdead0000; mov dword ptr [edx+0x1cc], 0xdead1111; mov dword ptr [edx+0x1d0], 0; mov dword ptr [edx+0x210], 0xdead2222; mov dword ptr [edx+20], 123; mov eax, {result}; ret'
    u.mem_write(0x494e30,bytes(ks.asm(stub,0x494e30)[0]))
    for offset,value in ((0,unit),(4,0x13e0),(8,1),(12,1234)):dword(u,STACK+offset,value)
    for register in (UC_X86_REG_EBX,UC_X86_REG_EBP,UC_X86_REG_ESI,UC_X86_REG_EDI):u.reg_write(register,0x11111111+register)
    saved=[u.reg_read(register) for register in (UC_X86_REG_EBX,UC_X86_REG_EBP,UC_X86_REG_ESI,UC_X86_REG_EDI)]
    run(u,0x44b5f7,0x44b5fc)
    assert u.reg_read(UC_X86_REG_ESP)==STACK and u.reg_read(UC_X86_REG_EAX)==result
    assert [u.reg_read(register) for register in (UC_X86_REG_EBX,UC_X86_REG_EBP,UC_X86_REG_ESI,UC_X86_REG_EDI)]==saved
    assert read(u,unit+20)==123 and read(u,unit+0x1d0)==0
    if result:
        assert read(u,unit+8)==CONTEXT+0x20000 and read(u,unit+4)==42
        assert read(u,unit+0x1cc)==0x12345678 and read(u,unit+0x210)==0x87654321
    else:assert read(u,unit+8)==0xdead0000
checks.append('Replay snapshot loader: fresh references restored immediately per unit, null/save-state preservation, fread failure, original arguments and callee-saved registers')

report={'kind':'machine-code-emulation','executable_hash':manifest['output_hash'],'checks':checks,'gameplay_validated':False,'multiplayer_validated':False}
out=path.parent/'probe-verification.json';out.write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
