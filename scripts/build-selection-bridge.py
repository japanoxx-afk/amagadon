"""Build the isolated x86 batching prototype; this does not install game hooks.

cdecl bridge(player, count, ushort* ids, immutable byte[64]* packet, handler)
handler must be the audited native right-click or explicit-order entrypoint.
The caller must run on the simulation thread, at a command barrier.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / '.tools'))
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

BASE = 0x20000000
ASSEMBLY = '''
push ebp
mov ebp, esp
push ebx
push esi
push edi
sub esp, 160
cld
mov eax, [ebp+8]
cmp eax, 1
jb invalid
cmp eax, 8
ja invalid
mov ecx, [ebp+12]
cmp ecx, 1700
ja invalid
test ecx, ecx
jz empty
cmp dword ptr [ebp+16], 0
je invalid
cmp dword ptr [ebp+20], 0
je invalid
mov edx, [ebp+24]
cmp edx, 0x408390
je handler_ok
cmp edx, 0x420410
jne invalid
handler_ok:
mov edx, [0x504a10]
test edx, edx
jz invalid
mov ecx, eax
shl ecx, 6
lea esi, [edx+ecx+0x7218]
mov [ebp-20], esi
lea edi, [ebp-96]
mov ecx, 16
rep movsd dword ptr es:[edi], dword ptr [esi]
mov eax, [ebp+8]
shl eax, 6
lea esi, [eax+0x52f510]
mov [ebp-24], esi
lea edi, [ebp-160]
mov ecx, 16
rep movsd dword ptr es:[edi], dword ptr [esi]
mov eax, [ebp+8]
mov edx, [eax*4+0x51bc50]
mov [ebp-28], edx
mov dword ptr [ebp-16], 0
mov dword ptr [ebp-32], 0
batch:
mov edi, [ebp-20]
mov eax, -1
mov ecx, 16
rep stosd
mov edi, [ebp-20]
xor ebx, ebx
fill:
mov ecx, [ebp-16]
cmp ecx, [ebp+12]
jae dispatch
mov esi, [ebp+16]
movzx eax, word ptr [esi+ecx*2]
inc dword ptr [ebp-16]
cmp eax, 1700
jae next_id
mov edx, [0x504a10]
mov edx, [edx+eax*4+8]
test edx, edx
jz next_id
cmp byte ptr [edx+0x13b8], 0
je next_id
movzx ecx, byte ptr [edx+0x3c]
cmp ecx, [ebp+8]
jne next_id
mov [edi+ebx*4], eax
inc ebx
cmp ebx, 16
je dispatch
next_id:
jmp fill
dispatch:
test ebx, ebx
jz complete
mov esi, [ebp+20]
mov edi, [ebp-24]
mov ecx, 16
rep movsd dword ptr es:[edi], dword ptr [esi]
mov eax, [ebp+8]
mov edx, [ebp-28]
mov [eax*4+0x51bc50], edx
push eax
call dword ptr [ebp+24]
add esp, 4
inc dword ptr [ebp-32]
mov eax, [ebp-16]
cmp eax, [ebp+12]
jb batch
complete:
lea esi, [ebp-96]
mov edi, [ebp-20]
mov ecx, 16
rep movsd dword ptr es:[edi], dword ptr [esi]
lea esi, [ebp-160]
mov edi, [ebp-24]
mov ecx, 16
rep movsd dword ptr es:[edi], dword ptr [esi]
mov eax, [ebp-32]
jmp done
empty:
xor eax, eax
jmp done
invalid:
mov eax, -1
done:
add esp, 160
pop edi
pop esi
pop ebx
pop ebp
ret
'''

def build(base=BASE):
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(ASSEMBLY, base)[0])

if __name__ == '__main__':
    target = Path(sys.argv[1] if len(sys.argv) > 1 else '.tools/selection-bridge.bin')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build())
    print(f'Built isolated selection bridge: {len(build())} bytes; no executable modified')
