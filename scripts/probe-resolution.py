"""Isolated renderer research build. Never use as a release gameplay patch."""
import sys,pathlib,struct,hashlib,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'.tools'))
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
from keystone import Ks,KS_ARCH_X86,KS_MODE_32
expected='34f0bf9ed99fbf3ab88c410a3a52a2f6904e7bc7f5b88fb4ebadc935c2e9b466'
source=pathlib.Path(sys.argv[1]); dest=pathlib.Path(sys.argv[2]); original=source.read_bytes()
if hashlib.sha256(original).hexdigest()!=expected:raise ValueError('Unsupported executable')
if source.resolve()==dest.resolve():raise ValueError('Probe must use separate copy')
workspace=pathlib.Path(__file__).resolve().parent.parent
if dest.resolve().parent != (workspace/'test-game').resolve():raise ValueError('Destination must be the workspace test-game directory')
pe=pefile.PE(data=original); result=bytearray(original); records=[]
md=Cs(CS_ARCH_X86,CS_MODE_32);md.detail=True
ks=Ks(KS_ARCH_X86,KS_MODE_32)
section=bytearray(0x28000);code_cursor=0
section_rva=(pe.OPTIONAL_HEADER.SizeOfImage+0xfff)&~0xfff
section_va=pe.OPTIONAL_HEADER.ImageBase+section_rva

def bytes_patch(va,before,after,reason):
    offset=pe.get_offset_from_rva(va-pe.OPTIONAL_HEADER.ImageBase)
    if len(before)!=len(after) or original[offset:offset+len(before)]!=before:raise ValueError(hex(va)+' unexpected instruction bytes')
    result[offset:offset+len(after)]=after
    records.append({'va':hex(va),'offset':offset,'expected':before.hex(),'replacement':after.hex(),'purpose':reason})

def emit(assembly):
    global code_cursor
    address=section_va+code_cursor
    code=bytes(ks.asm(assembly,address)[0])
    if code_cursor+len(code)>(0x25000 if code_cursor>=0x21000 else 0x1f00):raise ValueError('Code section overflow')
    section[code_cursor:code_cursor+len(code)]=code
    code_cursor=(code_cursor+len(code)+15)&~15
    return address

def hook(va,before,assembly,reason):
    target=emit(assembly)
    after=b'\xe9'+struct.pack('<i',target-va-5)+b'\x90'*(len(before)-5)
    bytes_patch(va,before,after,reason)
def immediate(va,old,new,reason):
    offset=pe.get_offset_from_rva(va-pe.OPTIONAL_HEADER.ImageBase)
    i=next(md.disasm(original[offset:offset+15],va))
    if i.imm_size!=4 or struct.unpack('<I',i.bytes[i.imm_offset:i.imm_offset+4])[0]!=old:raise ValueError(hex(va)+' unexpected bytes')
    start=offset+i.imm_offset; result[start:start+4]=struct.pack('<I',new)
    records.append({'va':hex(va),'offset':start,'expected':struct.pack('<I',old).hex(),'replacement':struct.pack('<I',new).hex(),'purpose':reason})
for va in (0x40121a,0x4012cd,0x401398,0x454ad6,0x45bb4b,0x45bcab,0x491a6d,0x491e46,0x491e7b,0x491e93,0x4922ce):immediate(va,800,1024,'DirectDraw/display dimensions')
for va in (0x401215,0x4012c8,0x401393,0x454ad1,0x45bb46,0x45bca6,0x491a64,0x491e4c,0x491e76,0x491e8e,0x4922c9):immediate(va,600,768,'DirectDraw/display dimensions')
for va in (0x4ae172,0x4ae186,0x4ae1c9,0x4b7833,0x4bd89b,0x4bd930):immediate(va,800,1024,'Software renderer width/row stride')
for va in (0x4ae17c,0x4ae1cf,0x4b783d,0x4bd8a5,0x4bd93a,0x4ba60c):immediate(va,600,768,'Software renderer height')
immediate(0x4ae190,472,768,'World sprites cover HUD side regions')
for va in (0x40d704,0x453d66,0x453ef1,0x453fc5,0x4907b2):immediate(va,799,1023,'Mouse bounds')
for va in (0x40d710,0x453e1f,0x453f1d,0x45407d,0x490828):immediate(va,599,767,'Mouse bounds')
# Selection drag start, live rectangle and released rectangle retain a
# separate 475-pixel world/HUD cut-off, independent of mouse screen bounds.
# Start points still go through the relocated HUD silhouette test.
immediate(0x4076aa,475,767,'Allow selection drag start across full screen height')
bytes_patch(0x407aa0,bytes.fromhex('6681f9db01'),bytes.fromhex('6681f9ff02'),'Released selection rectangle clamps to screen bottom')
bytes_patch(0x407ab1,bytes.fromhex('8d88db010000'),bytes.fromhex('8d88ff020000'),'Released selection world-coordinate correction matches screen height')
bytes_patch(0x407d0d,bytes.fromhex('6681f9db01'),bytes.fromhex('6681f9ff02'),'Live selection rectangle clamps to screen bottom')
immediate(0x407d21,475,767,'Live selection world-coordinate correction matches screen height')
# Extra terrain rendering is a separate probe stage. The 25-column weather
# cache is NOT expanded here: stop before its memory indexing for extra tiles.
if '--terrain' in sys.argv:
    immediate(0x4a3f74,832,1056,'Terrain horizontal loop')
    va=0x4a3f84;off=pe.get_offset_from_rva(va-0x400000)
    if original[off:off+3]!=b'\x83\xfe\x10':raise ValueError('Terrain row signature')
    result[off+2]=24;records.append({'va':hex(va),'offset':off+2,'expected':'10','replacement':'18','purpose':'Terrain vertical loop covers 768 pixels'})
    if '--weather' not in sys.argv:
        # Early terrain-only comparison stage; the full stage retains weather.
        va=0x4a3f0d
        before=bytes.fromhex('8b15ec125800')
        after=b'\xe9'+struct.pack('<i',0x4a3f6c-(va+5))+b'\x90'
        bytes_patch(va,before,after,'Terrain-only comparison: weather omitted')

if '--guard' in sys.argv:
    # The tile library owns exactly 10000 surface entries (48d540/48d55f).
    # The sibling routine 48d5c0 already guards this range and null entries.
    # 48d570 lacks both checks; 0xffff from a missing tile reaches DDRAW as
    # an arbitrary COM pointer. Reject it before any library dereference.
    hook(0x48d570,bytes.fromhex('83ec10568d742404'),f'''
        movzx eax, word ptr [esp+4]
        cmp eax, 10000
        jae bad_tile
        cmp dword ptr [ecx+eax*4+16], 0
        je bad_tile
        sub esp, 16
        push esi
        lea esi, [esp+4]
        jmp 0x48d578
    bad_tile:
        inc dword ptr [{section_va+0x1fec}]
        xor eax, eax
        ret 24
    ''','Guard invalid and unloaded tile surfaces before DirectDraw')
    hook(0x4a3d6b,bytes.fromhex('83c40433f6'),f'''
        pushfd
        pushad
        inc dword ptr [{section_va+0x1fe0}]
        mov edi, dword ptr [0x4f75e8]
        test edi, edi
        jz cleared
        mov ecx, dword ptr [0x4f75f4]
        imul ecx, dword ptr [0x4f75f0]
        shr ecx, 2
        xor eax, eax
        cld
        rep stosd
    cleared:
        popad
        popfd
        add esp, 4
        xor esi, esi
        jmp 0x4a3d70
    ''','Clear expanded world surface so missing tiles cannot retain old pixels')

if '--weather' in sys.argv:
    if '--terrain' not in sys.argv:raise ValueError('--weather requires --terrain')
    cache=section_va+0x2000
    rng=section_va+0x1ff0
    struct.pack_into('<I',section,0x1ff0,0x12345678)
    # The existing 25*19 cache is embedded in a serialized object. Do not
    # resize that object or change saved-game byte counts. The original
    # 25*16 visible cells keep their exact indices and RNG calls. Additional
    # cells use separate storage and a separate CRT random stream.
    hook(0x4a3f0d,bytes.fromhex('8b15ec125800'),f'''
        cmp esi, 16
        jae expanded_cell
        cmp edi, 25
        jae expanded_cell
        mov edx, dword ptr [0x5812ec]
        jmp 0x4a3f13
    expanded_cell:
        pushfd
        pushad
        imul eax, esi, 32
        add eax, edi
        imul eax, eax, 132
        add eax, {cache}
        push eax
        call 0x4c2f13
        push eax
        push dword ptr [eax+20]
        mov edx, dword ptr [{rng}]
        mov dword ptr [eax+20], edx
        mov ebx, dword ptr [0x517000]
        mov edx, dword ptr [0x5812ec]
        add edx, esi
        cmp edx, 256
        jae inactive_cell
        mov eax, dword ptr [0x5812e8]
        add eax, edi
        cmp eax, 256
        jae inactive_cell
        shl edx, 8
        add edx, eax
        movsx eax, byte ptr [ebx+edx+4]
        test eax, eax
        jle inactive_cell
        mov ecx, dword ptr [esp+8]
        push esi
        push edi
        push eax
        call 0x476d00
        jmp cell_done
    inactive_cell:
        mov ecx, dword ptr [esp+8]
        mov byte ptr [ecx+4], 0
    cell_done:
        mov eax, dword ptr [esp+4]
        mov edx, dword ptr [eax+20]
        mov dword ptr [{rng}], edx
        pop edx
        mov dword ptr [eax+20], edx
        add esp, 8
        popad
        popfd
        jmp 0x4a3f6c
    ''','Retain original weather cells; isolate expanded cache and random state')
    hook(0x4a445b,bytes.fromhex('e8b02ffdff'),f'''
        call 0x477410
        pushfd
        pushad
        call 0x4c2f13
        push eax
        push dword ptr [eax+20]
        mov edx, dword ptr [{rng}]
        mov dword ptr [eax+20], edx
        mov esi, {cache}
        mov edi, 920
    draw_next:
        cmp byte ptr [esi+4], 0
        je draw_skip
        mov ecx, esi
        call 0x476e50
    draw_skip:
        add esi, 132
        dec edi
        jnz draw_next
        mov eax, dword ptr [esp+4]
        mov edx, dword ptr [eax+20]
        mov dword ptr [{rng}], edx
        pop edx
        mov dword ptr [eax+20], edx
        add esp, 4
        popad
        popfd
        jmp 0x4a4460
    ''','Draw expanded weather using isolated visual random state')
    hook(0x47752f,bytes.fromhex('c64603015f5e'),f'''
        pushfd
        pushad
        mov edi, {cache}
        mov ecx, 30360
        xor eax, eax
        cld
        rep stosd
        mov dword ptr [{rng}], 0x12345678
        popad
        popfd
        mov byte ptr [esi+3], 1
        pop edi
        pop esi
        jmp 0x477535
    ''','Reset added visual cache when weather/game state initializes')
    immediate(0x476ec0,790,1014,'Weather horizontal clipping')
    immediate(0x476ecb,480,760,'Weather vertical clipping including eight-pixel trails')
    for va in (0x476f16,0x476f33,0x476f4d,0x476f9a,0x476fe8):
        bytes_patch(va,bytes.fromhex('8d04808d0480c1e005'),bytes(ks.asm('imul eax, eax, 1024; nop; nop; nop')[0]),'Weather raster row stride 1024')
    for va in (0x476f70,0x476fbd,0x477009):
        # In these sites other instructions separate the two LEAs and SHL.
        # Replace 25*y with 32*y before the unchanged final shift by five.
        bytes_patch(va,bytes.fromhex('8d04808d0c80'),bytes(ks.asm('imul ecx, eax, 32; nop; nop; nop')[0]),'Weather raster row stride 1024 (ECX)')

if '--world-overlays' in sys.argv:
    # Cache preparation precedes both fog draw passes. Expand all three
    # phases together; retain the existing visibility lookup and fade policy.
    for va,before,after in (
        (0x42b4b5,'8d4310','8d4318'),
        (0x42b4ca,'8d6e19','8d6e20'),
        (0x42b52c,'83f810','83f818'),
        (0x42b545,'8d6e19','8d6e20')):
        bytes_patch(va,bytes.fromhex(before),bytes.fromhex(after),'Prepare fog cache across full 32x24 viewport')
    immediate(0x42b504,25,32,'Fog visibility cache columns; preserve original visibility values')
    for va in (0x42b78a,0x42b874):immediate(va,800,1024,'Terrain overlay/fog horizontal loop')
    for va in (0x42b79e,0x42b888):immediate(va,512,768,'Terrain overlay/fog vertical tile coverage')
    immediate(0x4a5016,800,1024,'Full-screen overlay rectangle width')
    immediate(0x4a5025,600,768,'Full-screen overlay rectangle height')

if '--camera' in sys.argv:
    immediate(0x48cac7,599,767,'Unit world viewport bottom; shared by ground, air, bars and selections')
    immediate(0x48cad9,799,1023,'Unit world viewport right; shared by ground, air, bars and selections')
    for va in (0x453c80,0x453d83,0x453dc3,0x453f12,0x453f94,0x453feb,0x454049,0x45416d,0x454184):
        bytes_patch(va,bytes.fromhex('83e819'),bytes.fromhex('83e820'),'Camera horizontal extent: 32 map tiles')
    for va in (0x453d02,0x453e3c,0x453e7e,0x453f43,0x453fb5,0x4540a3,0x4540ff,0x4541bc):
        bytes_patch(va,bytes.fromhex('83e80f'),bytes.fromhex('83e818'),'Camera vertical extent: 24 map tiles')
    bytes_patch(0x4541a5,bytes.fromhex('83e90f'),bytes.fromhex('83e918'),'Camera vertical extent in ECX')
    bytes_patch(0x454132,bytes.fromhex('83c0f4'),bytes.fromhex('83c0f0'),'Camera center request horizontal half extent')
    bytes_patch(0x454135,bytes.fromhex('83c1fa'),bytes.fromhex('83c1f4'),'Camera center request vertical half extent')
    hook(0x4a3d40,bytes.fromhex('a1dc125800'),'''
        pushfd
        pushad
        mov ecx, dword ptr [0x4f9de4]
        test ecx, ecx
        jz camera_done
        movzx eax, word ptr [ecx+230]
        sub eax, 32
        jns x_max_ready
        xor eax, eax
    x_max_ready:
        mov edx, dword ptr [0x5812e8]
        test edx, edx
        jns x_not_negative
        xor edx, edx
    x_not_negative:
        cmp edx, eax
        jle x_ready
        mov edx, eax
    x_ready:
        mov dword ptr [0x5812e8], edx
        movzx eax, word ptr [ecx+232]
        sub eax, 24
        jns y_max_ready
        xor eax, eax
    y_max_ready:
        mov edx, dword ptr [0x5812ec]
        test edx, edx
        jns y_not_negative
        xor edx, edx
    y_not_negative:
        cmp edx, eax
        jle y_ready
        mov edx, eax
    y_ready:
        mov dword ptr [0x5812ec], edx
    camera_done:
        popad
        popfd
        mov eax, dword ptr [0x5812dc]
        jmp 0x4a3d45
    ''','Clamp camera against expanded viewport, including maps smaller than viewport')

if '--hud' in sys.argv:
    immediate(0x402c7c,600,768,'HUD anchor uses actual screen bottom')
    hook(0x402c9e,bytes.fromhex('8935b09d4f00'),'''
        mov dword ptr [0x4f9db0], 112
        jmp 0x402ca4
    ''','Center original 800-pixel HUD on 1024-pixel surface')
    # Both the draw and hit-test containers add their stored x/y to each
    # child position. Use the same temporary anchor for both paths. Leave
    # the serialized UI object and relative child coordinates unchanged.
    for va,before,replay,resume in (
        (0x49edf0,'83ec108b54241c','sub esp, 16; mov edx, dword ptr [esp+28]',0x49edf7),
        (0x49efc0,'83ec085355','sub esp, 8; push ebx; push ebp',0x49efc5),
        (0x49eb80,'83ec105355','sub esp, 16; push ebx; push ebp',0x49eb85),
        (0x49f6c0,'83ec285355','sub esp, 40; push ebx; push ebp',0x49f6c5)
    ):
        argument_count=3 if va==0x49f6c0 else 7
        copy_arguments=';'.join(f'push dword ptr [ebp+{8+i*4}]' for i in reversed(range(argument_count)))
        trampoline=emit(f'{replay}; jmp {resume}')
        hook(va,bytes.fromhex(before),f'''
            cmp ecx, dword ptr [0x50313c]
            je translated_container
            cmp ecx, dword ptr [0x50310c]
            je translated_container
            cmp ecx, dword ptr [0x503110]
            je translated_container
            cmp ecx, dword ptr [0x5030d4]
            je translated_resources
            jmp {trampoline}
        translated_resources:
            push ebp
            mov ebp, esp
            push ebx
            push esi
            push edi
            mov esi, ecx
            mov edi, dword ptr [esi+16]
            mov ebx, dword ptr [esi+20]
            add dword ptr [esi+16], 112
            jmp container_call
        translated_container:
            push ebp
            mov ebp, esp
            push ebx
            push esi
            push edi
            mov esi, ecx
            mov edi, dword ptr [esi+16]
            mov ebx, dword ptr [esi+20]
            add dword ptr [esi+16], 112
            add dword ptr [esi+20], 168
        container_call:
            {copy_arguments}
            call {trampoline}
            mov dword ptr [esi+16], edi
            mov dword ptr [esi+20], ebx
            pop edi
            pop esi
            pop ebx
            pop ebp
            ret {argument_count*4}
        ''','Translate drawing, tooltips and actual mouse event dispatch; keep resource bar at top')
    # This routine tests the original HUD silhouette (800x300), not a
    # generic 800-wide screen bound. Convert only points over the centered
    # HUD into mask coordinates; the two side strips remain playable world.
    hook(0x48ed10,bytes.fromhex('8b4424083d2c010000'),'''
        mov ecx, dword ptr [esp+4]
        mov edx, dword ptr [esp+8]
        cmp ecx, 1024
        jae outside_screen
        cmp edx, 768
        jae outside_screen
        cmp edx, 468
        jl world_point
        sub ecx, 112
        cmp ecx, 800
        jae world_point
        sub edx, 468
        imul edx, edx, 800
        xor eax, eax
        cmp byte ptr [edx+ecx+0x5308c8], 0
        sete al
        ret
    world_point:
        mov eax, 1
        ret
    outside_screen:
        xor eax, eax
        ret
    ''','HUD silhouette hit mask uses inverse translation; outside HUD remains world')
    # Slot three is the HUD portrait video. World videos use other slots.
    # Translate on creation rather than every frame, including queued clips.
    for va,resume in ((0x4bcd27,0x4bcd2a),(0x4bcdd7,0x4bcdda)):
        # Include the following mov so the detour occupies whole instructions.
        hook(va,bytes.fromhex('8946188b442424'),f'''
            pushfd
            cmp edi, 3
            jne portrait_ready
            add eax, 112
            add ecx, 168
        portrait_ready:
            mov dword ptr [esi+24], eax
            mov eax, dword ptr [esp+40]
            popfd
            jmp {resume+4}
        ''','Move HUD portrait video slot three; leave world/cutscene video slots unchanged')
    hook(0x4039e0,bytes.fromhex('b90a000000'),'''
        add dword ptr [0x4f9dd0], 112
        add dword ptr [0x4f9dd8], 112
        add dword ptr [0x4f9dd4], 168
        add dword ptr [0x4f9ddc], 168
        mov ecx, 10
        jmp 0x4039e5
    ''','Move minimap bounds used by drawing, clicking and alarms together')
    # Existing projection modes are 2, 1 and 1/2 mini pixels per map tile.
    # Keep those projections, expand only the visible camera rectangle.
    bytes_patch(0x4a5553,bytes.fromhex('8d4831'),bytes.fromhex('8d483f'),'Minimap 2x horizontal camera span')
    bytes_patch(0x4a5563,bytes.fromhex('83c01e'),bytes.fromhex('83c030'),'Minimap 2x vertical span: 768/32*2=54')
    bytes_patch(0x4a5587,bytes.fromhex('8d4818'),bytes.fromhex('8d481f'),'Minimap 1x horizontal camera span')
    bytes_patch(0x4a5596,bytes.fromhex('83c00f'),bytes.fromhex('83c018'),'Minimap 1x vertical camera span')
    bytes_patch(0x4a55b2,bytes.fromhex('8d480c'),bytes.fromhex('8d480f'),'Minimap half-scale horizontal camera span')
    bytes_patch(0x4a55cc,bytes.fromhex('83c008'),bytes.fromhex('83c00c'),'Minimap half-scale vertical camera span')
    hook(0x4a55cf,bytes.fromhex('8b3578295700'),'''
        mov esi, dword ptr [0x4f9dd8]
        dec esi
        cmp ecx, esi
        jle mini_right_ready
        mov ecx, esi
    mini_right_ready:
        mov esi, dword ptr [0x4f9ddc]
        cmp eax, esi
        jle mini_bottom_ready
        mov eax, esi
    mini_bottom_ready:
        mov esi, dword ptr [0x572978]
        jmp 0x4a55d5
    ''','Clip camera border to actual minimap bounds on small maps')
    # HUD numeric text is drawn outside the generic UI containers.
    # Translate only the identified HUD call sites, never world labels.
    text_sites=(0x4a58f6,0x4a592e,0x4a598e,0x4a59c6,0x4a5a61,0x4a5a99,0x4a5bbc,0x4a5bf6)
    tests=';'.join(f'cmp eax, {site}; je hud_text' for site in text_sites)
    name_tests=';'.join(f'cmp eax, {site}; je hud_name' for site in (0x4a5146,0x4a517e))
    hook(0x428f70,bytes.fromhex('83ec08568b74241c'),f'''
        push eax
        mov eax, dword ptr [esp+4]
        {tests}
        {name_tests}
        jmp text_ready
    hud_name:
        add dword ptr [esp+16], 168
    hud_text:
        add dword ptr [esp+12], 112
    text_ready:
        pop eax
        sub esp, 8
        push esi
        mov esi, dword ptr [esp+28]
        jmp 0x428f78
    ''','Align selected name and shadow with HUD; keep resources at top and world labels unchanged')
    # Selection/production details use shadowed text helpers, independently
    # of the UI containers. Only these audited call sites need HUD translation.
    detail_calls=(0x4a6a39,0x4a6bce,0x4a6de5,0x4a6e9d,0x4a6f4f,0x4a7038,
        0x4a741b,0x4a7528,0x4a76bf,0x4a772f,0x4a7b9a,0x4a7cc9,0x4a7d2a,
        0x4a7dec,0x4a7e67,0x4a7eec,0x4a7ff4,0x4a82c2,0x4a837b,0x4a83de,
        0x4a843f,0x4a84a3,0x4a8507,0x4a869d)
    for entry in (0x4a8720,0x4a8790):
        sites=[]
        for call in detail_calls:
            off=pe.get_offset_from_rva(call-0x400000)
            instruction=next(md.disasm(original[off:off+5],call))
            if instruction.mnemonic!='call':raise ValueError('HUD detail call signature')
            if instruction.operands[0].imm==entry:sites.append(call+5)
        detail_tests=';'.join(f'cmp eax, {site}; je detail_text' for site in sites)
        hook(entry,bytes.fromhex('535556578b7c241c'),f'''
            push eax
            mov eax, dword ptr [esp+4]
            {detail_tests}
            jmp detail_ready
        detail_text:
            add dword ptr [esp+8], 112
            add dword ptr [esp+12], 168
        detail_ready:
            pop eax
            push ebx
            push ebp
            push esi
            push edi
            mov edi, dword ptr [esp+28]
            jmp {entry+8}
        ''','Move HUD health/shield numbers and detail text, including both shadow passes')

    # Read the engine's saved elapsed-seconds counter, not wall-clock time.
    # Format without CRT allocation; preserve all registers and flags around HUD draw.
    timer_buffer=section_va+0x1f00
    hook(0x4a602d,bytes.fromhex('8b3578295700'),f"""
        pushfd
        pushad
        cld
        movzx eax, word ptr [0x503c2a]
        xor edx, edx
        mov ecx, 60
        div ecx
        mov ebx, edx
        xor ecx, ecx
        mov esi, 10
    timer_minutes:
        xor edx, edx
        div esi
        push edx
        inc ecx
        test eax, eax
        jnz timer_minutes
        cmp ecx, 2
        jae timer_digits
        push 0
        inc ecx
    timer_digits:
        mov edi, {timer_buffer}
    timer_pop:
        pop eax
        add al, 48
        stosb
        loop timer_pop
        mov al, 58
        stosb
        mov eax, ebx
        xor edx, edx
        div esi
        add al, 48
        stosb
        mov eax, edx
        add al, 48
        stosb
        xor eax, eax
        stosb
        push 0xe6e6e6
        push {timer_buffer}
        push 14
        mov eax, dword ptr [0x4f75f0]
        sub eax, 164
        push eax
        mov eax, dword ptr [0x4f9db0]
        add eax, 304
        push eax
        call 0x4a8720
        add esp, 20
        popad
        popfd
        mov esi, dword ptr [0x572978]
        jmp 0x4a6033
    """,'Draw saved simulation elapsed time centered above HUD buttons')

# Replay uses a separate code area and a zero-initialized controller mailbox.
# The launcher activates it only in its own suspended child, never an existing game.
# Mailbox: mode, request, ack, event, initialized, active, keyboard, RNG, error.
if '--replay' in sys.argv:
    code_cursor=0x21000
    box=section_va+0x26000
    save_name=box+0x100
    notify=emit(f"""
        mov dword ptr [{box+12}], eax
        inc dword ptr [{box+4}]
        mov ebx, dword ptr [{box+4}]
        mov edi, 10000
    replay_wait:
        cmp dword ptr [{box+8}], ebx
        je replay_ack
        push 1
        call dword ptr [0x4cb0fc]
        dec edi
        jnz replay_wait
        mov dword ptr [{box+32}], 1
        cmp dword ptr [{box}], 2
        je replay_abort
        mov dword ptr [{box}], 0
    replay_ack:
        cmp dword ptr [{box}], 3
        je replay_abort
        ret
    replay_abort:
        push 0xe001
        call dword ptr [0x4cb204]
        int3
    """)
    # Run after input polling and before active-state dispatch. The save roundtrip
    # normalizes a fresh match through the same reconstruction path as playback.
    hook(0x4532c7,bytes.fromhex('a0484f5000'),f"""
        pushfd
        pushad
        cmp dword ptr [{box}], 0
        je replay_loop_done
        mov eax, dword ptr [esp+56]
        mov dword ptr [{box+24}], eax
        lea eax, [esp+52]
        mov dword ptr [{box+36}], eax
        call 0x4c2f13
        add eax, 20
        mov dword ptr [{box+28}], eax
        cmp dword ptr [{box+16}], 0
        jne replay_check_state
        cmp dword ptr [{box}], 2
        jne replay_mark_ready
        cmp byte ptr [0x504f48], 2
        jne replay_loop_done
        push {save_name}
        call 0x454ce0
        add esp, 4
        test eax, eax
        jz replay_load_fail
        cmp dword ptr [0x513ed4], 1
        je replay_load_fail
        mov dword ptr [{box+20}], 1
    replay_mark_ready:
        mov dword ptr [{box+16}], 1
    replay_check_state:
        cmp byte ptr [0x504f48], 4
        jne replay_outside
        cmp dword ptr [0x513ed4], 1
        je replay_outside
        cmp dword ptr [{box+20}], 0
        jne replay_frame
        mov eax, 10
        call {notify}
        cmp dword ptr [{box}], 0
        je replay_loop_done
        push {save_name}
        call 0x454be0
        add esp, 4
        test eax, eax
        jz replay_save_fail
        mov eax, 11
        call {notify}
        cmp dword ptr [{box}], 0
        je replay_loop_done
        push {save_name}
        call 0x454ce0
        add esp, 4
        test eax, eax
        jz replay_load_fail
        mov dword ptr [{box+20}], 1
    replay_frame:
        mov eax, 1
        call {notify}
        jmp replay_loop_done
    replay_outside:
        cmp dword ptr [{box+20}], 0
        je replay_loop_done
        mov eax, 4
        call {notify}
        mov dword ptr [{box+20}], 0
        jmp replay_loop_done
    replay_save_fail:
        mov dword ptr [{box+32}], 2
        mov dword ptr [{box}], 0
        jmp replay_loop_done
    replay_load_fail:
        mov dword ptr [{box+32}], 3
        mov dword ptr [{box}], 3
        mov eax, 99
        call {notify}
    replay_loop_done:
        popad
        popfd
        mov al, byte ptr [0x504f48]
        jmp 0x4532cc
    """,'Replay bootstrap, normalized initial save, frame input barrier, single-player gate')
    # Raw mouse state has been collected; the next instruction consumes it.
    for va,original_bytes,restore,resume,event in (
        (0x453830,'8b0d784d5000','mov ecx, dword ptr [0x504d78]',0x453836,2),
        (0x454429,'381dc83e5100','cmp byte ptr [0x513ec8], bl',0x45442f,3)):
        hook(va,bytes.fromhex(original_bytes),f"""
            pushfd
            pushad
            cmp dword ptr [{box}], 0
            je replay_event_done
            cmp dword ptr [{box+20}], 0
            je replay_event_done
            cmp dword ptr [0x513ed4], 1
            je replay_event_done
            mov eax, {event}
            call {notify}
        replay_event_done:
            popad
            popfd
            {restore}
            jmp {resume}
        """,'Replay synchronized mouse state' if event==2 else 'Replay synchronized player command packets')

    # A replay must never execute recorded UI actions that overwrite user saves.
    # Only our audited bootstrap/normalization calls may invoke load/save.
    for va,before,restore,resume in (
        (0x454be0,'8b44240481ec00010000','mov eax, dword ptr [esp+4]; sub esp, 256',0x454bea),
        (0x454ce0,'8b0d582b5700','mov ecx, dword ptr [0x572b58]',0x454ce6)):
        hook(va,bytes.fromhex(before),f"""
            pushfd
            pushad
            cmp dword ptr [{box}], 0
            je replay_io_ready
            mov eax, dword ptr [esp+36]
            cmp eax, {section_va+0x21000}
            jb replay_user_io
            cmp eax, {section_va+0x25000}
            jb replay_io_ready
        replay_user_io:
            cmp dword ptr [{box}], 2
            jne replay_record_io
            mov eax, 98
            call {notify}
            jmp replay_io_ready
        replay_record_io:
            cmp dword ptr [{box+20}], 0
            je replay_io_ready
            {'mov eax, 4; call '+str(notify)+'; mov dword ptr ['+str(box+20)+'], 0' if va==0x454ce0 else 'nop'}
        replay_io_ready:
            popad
            popfd
            {restore}
            jmp {resume}
        """,'Protect user saves during replay' if va==0x454be0 else 'Only internal replay load allowed; segment recording on user load')

if code_cursor:
    # Add our own section; never borrow unrelated executable padding or BSS.
    file_align=pe.OPTIONAL_HEADER.FileAlignment
    raw_offset=(len(result)+file_align-1)//file_align*file_align
    result.extend(b'\0'*(raw_offset-len(result)))
    result.extend(section)
    header=pe.sections[-1].get_file_offset()+40
    if header+40>pe.sections[0].PointerToRawData:raise ValueError('No section header room')
    result[header:header+40]=struct.pack('<8sIIIIIIHHI',b'.aghprobe',len(section),section_rva,len(section),raw_offset,0,0,0,0,0xe0000040)
    struct.pack_into('<H',result,pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'),pe.FILE_HEADER.NumberOfSections+1)
    struct.pack_into('<I',result,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),section_rva+len(section))
    struct.pack_into('<I',result,pe.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum'),0)
dest.parent.mkdir(parents=True,exist_ok=True)
temporary=dest.with_suffix('.probe.tmp')
temporary.write_bytes(result)
temporary.replace(dest)
dest.with_suffix('.probe.json').write_text(json.dumps({'supported_hash':expected,'output_hash':hashlib.sha256(result).hexdigest(),'release_candidate':False,'stages':[a for a in sys.argv[3:] if a.startswith('--')],'section_va':hex(section_va),'changes':records},indent=2),encoding='utf8')
print('Created isolated probe with',len(records),'validated edits')
