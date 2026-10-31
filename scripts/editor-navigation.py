"""Emit ACE's native wheel/splitter handlers (no map or terrain format changes)."""
import struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

def install(b, pe, raw, va):
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    width, dragging, wheel = va+0x2800, va+0x2804, va+0x2808
    def emit(offset, source):
        code=bytes(ks.asm(source,va+offset)[0])
        assert offset+len(code)<0x2800
        b[raw+offset:raw+offset+len(code)]=code
    def patch(address, expected, replacement):
        off=pe.get_offset_from_rva(address-0x400000)
        assert bytes(b[off:off+len(expected)])==bytes.fromhex(expected.hex())
        b[off:off+len(expected)]=replacement
    def jump(address, expected, dest):
        patch(address,expected,b'\xe9'+struct.pack('<i',dest-address-5)+b'\x90'*(len(expected)-5))
    # EBP drives both the tree width and map origin in ACE's WM_SIZE handler.
    emit(0x900,f'''
        sub ebp,eax
        cmp dword ptr [{width}],0
        je width_default
        mov ebp,[{width}]
      width_default:
        push ecx
        lea ecx,[ebx-168]
        cmp ecx,144
        jge limit_ok
        mov ecx,144
      limit_ok:
        cmp ebp,ecx
        jle width_max
        mov ebp,ecx
      width_max:
        cmp ebp,144
        jge width_min
        mov ebp,144
      width_min:
        mov [{width}],ebp
        pop ecx
        mov eax,[esp+0x30]
        jmp 0x401a1c
    ''')
    jump(0x401a16,bytes.fromhex('2be88b442430'),va+0x900)
    patch(0x401a33,bytes.fromhex('83c503'),bytes.fromhex('83c508'))
    patch(0x401b5b,bytes.fromhex('8d55fd'),bytes.fromhex('8d55f8'))
    # Preserve the dialog procedure's SEH prologue for all unhandled messages.
    # Local stack: RECT[16]; saved EDI/ESI/EBX/EBP; return; hwnd/msg/wp/lp.
    emit(0x1000,f'''
        push ebp
        push ebx
        push esi
        push edi
        sub esp,16
        mov edi,[esp+36]
        mov eax,[esp+40]
        cmp eax,0x20a
        je on_wheel
        cmp eax,0x201
        je on_down
        cmp eax,0x200
        je on_move
        cmp eax,0x202
        je on_up
        cmp eax,0x215
        je lost_capture
        cmp eax,0x1f
        je on_up
        jmp original
      on_wheel:
        cmp dword ptr [0x44dba0],0
        je original
        mov eax,[esp+44]
        sar eax,16
        add eax,[{wheel}]
        mov ebx,120
        cdq
        idiv ebx
        mov [{wheel}],edx
        test eax,eax
        jz handled
        xor esi,esi
        test eax,eax
        jg wheel_count
        neg eax
        inc esi
      wheel_count:
        cmp eax,16
        jle wheel_bounded
        mov eax,16
      wheel_bounded:
        lea ebx,[eax+eax*2]
      wheel_loop:
        push dword ptr [0x44db70]
        push esi
        push 0x115
        push edi
        call dword ptr [0x4451a0]
        dec ebx
        jnz wheel_loop
        jmp handled
      on_down:
        cmp dword ptr [{width}],0
        je original
        movsx eax,word ptr [esp+48]
        sub eax,[{width}]
        cmp eax,8
        jae original
        mov dword ptr [{dragging}],1
        push edi
        call dword ptr [0x4451d4]
        jmp handled
      on_move:
        cmp dword ptr [{dragging}],0
        je original
        movsx ebx,word ptr [esp+48]
        mov eax,esp
        push eax
        push edi
        call dword ptr [0x44522c]
        test eax,eax
        jz handled
        mov ecx,[esp+8]
        sub ecx,168
        cmp ecx,144
        jl handled
        cmp ebx,ecx
        jle drag_max
        mov ebx,ecx
      drag_max:
        cmp ebx,144
        jge drag_min
        mov ebx,144
      drag_min:
        mov [{width}],ebx
        mov eax,[esp+12]
        shl eax,16
        mov ax,word ptr [esp+8]
        push eax
        push 0
        push 5
        push edi
        call dword ptr [0x4451a0]
        jmp handled
      on_up:
        cmp dword ptr [{dragging}],0
        je original
        mov dword ptr [{dragging}],0
        call dword ptr [0x4451d0]
        jmp handled
      lost_capture:
        mov dword ptr [{dragging}],0
        jmp original
      handled:
        add esp,16
        pop edi
        pop esi
        pop ebx
        pop ebp
        mov eax,1
        ret 16
      original:
        add esp,16
        pop edi
        pop esi
        pop ebx
        pop ebp
        mov eax,fs:[0]
        jmp 0x4017c6
    ''')
    jump(0x4017c0,bytes.fromhex('64a100000000'),va+0x1000)
