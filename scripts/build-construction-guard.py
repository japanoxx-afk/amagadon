"""Reject missing construction definitions before native footprint/cost use."""
def assembly(base):
 e=base+0x78000;t=base+0x80000
 return f'''
pushfd
pushad
movzx eax,word ptr [esi+0x414]
mov edx,eax
shr edx,8
cmp edx,3
ja bad_race
cmp al,100
jae bad_index
mov ecx,[edx*4+0x5049fc]
test ecx,ecx
jz bad_catalog
and eax,255
cmp dword ptr [ecx+eax*4+4],0
je bad_definition
popad
popfd
mov ecx,esi
call 0x41f090
jmp 0x438b58
bad_race:
mov ebx,1
jmp record
bad_index:
mov ebx,2
jmp record
bad_catalog:
mov ebx,3
jmp record
bad_definition:
mov ebx,4
record:
mov dword ptr [{e}],0x31444c42
mov dword ptr [{e}+8],32
mov ebp,[{e}+4]
inc ebp
mov edi,ebp
and edi,31
shl edi,7
add edi,{e}+256
mov dword ptr [edi],0
mov eax,[0x503c6c]
mov [edi+4],eax
movzx eax,word ptr [esi+14]
mov [edi+8],eax
movzx eax,word ptr [esi+12]
mov [edi+12],eax
movzx eax,byte ptr [esi+60]
mov [edi+16],eax
mov eax,[esi+0x414]
mov [edi+20],eax
mov eax,[esi+0xa4]
mov [edi+24],eax
mov eax,[esi+0xf4]
mov [edi+28],eax
movzx eax,byte ptr [esi+0x464]
mov [edi+32],eax
mov [edi+36],ebx
mov eax,[{t}+20]
mov [edi+40],eax
push edi
add edi,48
mov ecx,16
xor eax,eax
rep stosd
pop edi
mov eax,[edi+16]
cmp eax,1
jb commit
cmp eax,8
ja commit
shl eax,6
push edi
lea esi,[eax+0x52f510]
add edi,48
mov ecx,16
rep movsd dword ptr es:[edi],dword ptr [esi]
pop edi
commit:
mov [edi+120],ebp
mov [edi],ebp
mov [{e}+4],ebp
cmp dword ptr [{t}+4],0
je cancel
cmp dword ptr [{t}+12],0
jne cancel
mov dword ptr [{t}+12],2
mov eax,[0x503c6c]
mov [{t}+16],eax
cancel:
popad
popfd
jmp 0x438c01
'''
