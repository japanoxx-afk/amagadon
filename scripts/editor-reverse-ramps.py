"""Mirror ACE's actual terrain queries, not just A/B labels, for north ramps.

The drawn footprint is four paired columns by six rows: [cx-1,cx+2]
and [cy-2,cy+3]. Its centre is (cx+.5,cy+.5). The original placement
validator samples an asymmetric halo; swapping terrain IDs is not its rotation.
"""
import struct
from keystone import Ks,KS_ARCH_X86,KS_MODE_32
from capstone import Cs,CS_ARCH_X86,CS_MODE_32

def install(b,pe,raw,va):
    active,mx,my=va+0x2820,va+0x2824,va+0x2828
    # NW base hill edging sits three rows below the rotated south validator's
    # accepted anchor. Sample its halo three rows up, so the actual footprint
    # straddles the cliff instead of floating on the low ground.
    delta=va+0x282c
    ks=Ks(KS_ARCH_X86,KS_MODE_32)
    def emit(off,code):
        data=bytes(ks.asm(code,va+off)[0]);assert off+len(data)<0x2800
        b[raw+off:raw+off+len(data)]=data
    def jump(address,n,target):
        off=pe.get_offset_from_rva(address-0x400000)
        b[off:off+n]=b'\xe9'+struct.pack('<i',target-address-5)+b'\x90'*(n-5)
    emit(0x2000,f'''
        push eax
        push edx
        movzx eax,byte ptr [esp+20]
        cmp eax,57
        je check
        cmp eax,58
        jne original
      check:
        imul edx,eax,0x3384
        add edx,[0x452480]
        cmp dword ptr [edx+0x2c6],4139053246
        jne original
        cmp word ptr [edx+0x2e6],0x0100
        jne original
        cmp byte ptr [edx+0x2e4],4
        jb original
        cmp byte ptr [edx+0x2e4],5
        ja original
        pop edx
        pop eax
        pushad
        mov eax,[esp+36]
        dec eax
        sar eax,1
        lea eax,[eax*2+1]
        mov [{mx}],eax
        mov eax,[esp+40]
        lea eax,[eax*2+1]
        mov [{my}],eax
        mov dword ptr [{active}],1
        movzx edx,byte ptr [esp+44]
        mov dword ptr [{delta}],0
        cmp edx,57
        jne no_shift
        mov dword ptr [{delta}],-3
      no_shift:
        mov eax,72
        sub eax,edx
        mov ecx,[esp+36]
        mov edx,[esp+40]
        push eax
        push edx
        push ecx
        call {va+0x2200}
        add esp,12
        mov dword ptr [{active}],0
        mov [esp+28],eax
        xor ebx,ebx
      mask_column:
        xor ecx,ecx
      mask_row:
        mov esi,ebx
        shl esi,3
        add esi,ecx
        mov edi,61
        sub edi,esi
        mov eax,[0x45450c+esi*4]
        mov edx,[0x45450c+edi*4]
        mov [0x45450c+esi*4],edx
        mov [0x45450c+edi*4],eax
        inc ecx
        cmp ecx,6
        jl mask_row
        inc ebx
        cmp ebx,4
        jl mask_column
        popad
        ret
      original:
        pop edx
        pop eax
        jmp {va+0x2200}
    ''')
    emit(0x2200,'sub esp,0x14; mov eax,[esp+0x18]; jmp 0x42ea97')
    for off,target in [(0x2240,0x423290),(0x2380,0x4238a0)]:
        self_check = f'''
            push eax
            mov eax,[{mx}]
            inc eax
            sar eax,1
            cmp eax,[esp+8]
            jne not_self
            mov eax,[{my}]
            inc eax
            sar eax,1
            add eax,[{delta}]
            cmp eax,[esp+12]
            jne not_self
            pop eax
            xor eax,eax
            ret 12
          not_self:
            pop eax
        ''' if target==0x4238a0 else ''
        emit(off,f'''
            cmp dword ptr [{active}],0
            je original
            {self_check}
            push eax
            mov eax,[{mx}]
            sub eax,[esp+8]
            mov [esp+8],eax
            mov eax,[{my}]
            sub eax,[esp+12]
            add eax,[{delta}]
            mov [esp+12],eax
            pop eax
          original:
            jmp {target}
        ''')
    start=pe.get_offset_from_rva(0x2ea90);end=pe.get_offset_from_rva(0x310b8)
    for ins in Cs(CS_ARCH_X86,CS_MODE_32).disasm(bytes(b[start:end]),0x42ea90):
        if ins.mnemonic=='call' and ins.op_str in ('0x423290','0x4238a0'):
            target=va+(0x2240 if ins.op_str=='0x423290' else 0x2380)
            off=pe.get_offset_from_rva(ins.address-0x400000)
            b[off:off+5]=b'\xe8'+struct.pack('<i',target-ins.address-5)
    jump(0x42ea90,7,va+0x2000)

    # Original south ramps first clear a 2x2 ground patch. North ramps
    # straddle the opposite edge: this destroys their required high ground.
    emit(0x2300,f'''
        cmp byte ptr [eax+0xc1404],57
        je check
        cmp byte ptr [eax+0xc1404],58
        jne original
      check:
        cmp dword ptr [eax+ecx*4+0x2c6],4139053246
        jne original
        cmp word ptr [eax+ecx*4+0x2e6],0x0100
        jne original
        jmp 0x429433
      original:
        push -1
        push 0
        push 2
        jmp 0x4293ba
    ''')
    jump(0x4293b4,6,va+0x2300)

    # Snap north-west brush to an adjacent valid anchor, consistently in preview
    # and paint. Validation/cleanup of existing map records never snaps.
    emit(0x2440,f'''
        push ebx
        push esi
        push edi
        push ebp
        mov esi,[esp+20]
        mov edi,[esp+24]
        cmp byte ptr [0x44dbf3],2
        jne unchanged
        mov eax,[0x452480]
        cmp byte ptr [eax+0xc1404],57
        jne unchanged
        cmp dword ptr [eax+{57*0x3384+0x2c6}],4139053246
        jne unchanged
        cmp word ptr [eax+{57*0x3384+0x2e6}],0x0100
        jne unchanged
        xor ebx,ebx
      candidate:
        movsx eax,byte ptr [{va+0x2740}+ebx*2]
        movsx edx,byte ptr [{va+0x2741}+ebx*2]
        add eax,esi
        add edx,edi
        push edx
        push eax
        push 57
        push edx
        push eax
        call 0x42ea90
        add esp,12
        test eax,eax
        jne failed
        call 0x4310d0
        test eax,eax
        jne failed
        pop eax
        pop edx
        jmp done
      failed:
        add esp,8
        inc ebx
        cmp ebx,9
        jl candidate
      unchanged:
        mov eax,esi
        mov edx,edi
      done:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    ''')
    offsets=[(0,0),(0,-1),(0,1),(-2,0),(2,0),(-2,-1),(2,1),(-2,1),(2,-1)]
    b[raw+0x2740:raw+0x2752]=bytes(v&255 for xy in offsets for v in xy)
    emit(0x2580,f'''
        pushad
        mov eax,[esp+36]
        mov edx,[esp+40]
        push edx
        push eax
        call {va+0x2440}
        add esp,8
        mov [esp+36],eax
        mov [esp+40],edx
        popad
        sub esp,0x10
        push ebx
        push ebp
        jmp 0x428265
    ''')
    jump(0x428260,5,va+0x2580)
    emit(0x2600,f'''
        pushad
        mov eax,esi
        sar eax,5
        add eax,[0x44dbe8]
        dec eax
        mov edx,edi
        sar edx,5
        add edx,[0x44dbec]
        dec edx
        push edx
        push eax
        call {va+0x2440}
        add esp,8
        sub eax,[0x44dbe8]
        inc eax
        sub edx,[0x44dbec]
        inc edx
        mov [esp+56],eax
        mov [esp+68],edx
        mov ecx,esi
        sar ecx,5
        sub eax,ecx
        shl eax,5
        add eax,esi
        mov [esp+4],eax
        mov ecx,edi
        sar ecx,5
        sub edx,ecx
        shl edx,5
        add edx,edi
        mov [esp],edx
        popad
        jmp 0x425cb6
    ''')
    jump(0x425ca4,18,va+0x2600)
