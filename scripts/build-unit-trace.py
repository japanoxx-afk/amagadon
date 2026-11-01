"""Bounded, read-only per-unit snapshots paired with the sync trace clock."""
def assembly(base):
 t=base+0x281000
 return f"""
pushfd
pushad
mov ecx,[edi+28]
mov eax,ebx
and eax,63
imul eax,eax,54464
lea edi,[eax+{t+4096}]
mov dword ptr [edi],0
mov dword ptr [edi+20],0
mov eax,[0x503c6c]
mov [edi+4],eax
mov eax,[{base+0x80014}]
mov [edi+8],eax
mov [edi+12],ecx
push edi
add edi,64
xor esi,esi
loop_units:
cmp esi,ecx
jae commit
mov edx,[ebp+esi*4+8]
test edx,edx
jz empty
mov [edi],esi
mov ax,[edx+12]
mov [edi+4],ax
mov al,[edx+60]
mov [edi+6],al
mov al,[edx+0x13b8]
mov [edi+7],al
mov eax,[edx+20]
mov [edi+8],eax
mov eax,[edx+24]
mov [edi+12],eax
mov eax,[edx+0x9c4]
mov [edi+16],eax
mov eax,[edx+0x414]
mov [edi+20],eax
mov eax,[edx+0x478]
mov [edi+24],eax
mov al,[edx+0x464]
mov [edi+28],al
mov al,[edx+0x4d0]
mov [edi+29],al
mov al,[edx+0x13b9]
mov [edi+30],al
mov al,[edx+0x10]
mov [edi+31],al
jmp next
empty:
mov dword ptr [edi],0xffffffff
next:
add edi,32
inc esi
jmp loop_units
commit:
pop edi
mov [edi+20],ebx
mov [edi],ebx
mov dword ptr [{t}],0x31544e55
mov [{t+4}],ebx
mov eax,[{base+0x80014}]
mov [{t+8}],eax
popad
popfd
ret
"""
