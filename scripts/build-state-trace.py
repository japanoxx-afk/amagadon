"""Read-only extension at sync frame +1536. Original grid row pitch is 2048 bytes."""
def assembly():
 return '''
pushfd
pushad
cld
add edi,1536
push edi
xor eax,eax
mov ecx,128
rep stosd
pop edi
mov dword ptr [edi],0x31545348
mov dword ptr [edi+4],1
movzx eax,word ptr [ebp+0x711a]
mov [edi+24],eax
lea edx,[edi+32]
mov ecx,1
players:
mov eax,[ebp+ecx*4+0xa8c0]
mov [edx],eax
mov eax,[ebp+ecx*4+0xa8e8]
mov [edx+4],eax
mov eax,[ebp+ecx*4+0x2221c]
mov [edx+8],eax
mov eax,[ecx*4+0x51bc50]
mov [edx+12],eax
mov ax,[ecx*2+0x4fa618]
mov [edx+16],ax
mov ax,[ecx*2+0x4f9e40]
mov [edx+18],ax
mov eax,[ecx*4+0x51bc28]
mov [edx+20],eax
mov eax,[ecx*4+0x51bcf4]
mov [edx+24],eax
mov eax,[ecx*8+0x51bd48]
mov [edx+28],eax
mov eax,[ecx*8+0x51bd4c]
mov [edx+32],eax
mov eax,[ecx*8+0x51be00]
mov [edx+36],eax
mov eax,[ecx*8+0x51be04]
mov [edx+40],eax
add edx,44
inc ecx
cmp ecx,9
jne players
mov esi,[0x4f9de4]
test esi,esi
jz done
movzx eax,word ptr [esi+0xe6]
movzx edx,word ptr [esi+0xe8]
shl eax,2
shl edx,2
mov [edi+8],eax
mov [edi+12],edx
dec eax
cmp eax,1023
ja invalid
dec edx
cmp edx,1023
ja invalid
inc eax
inc edx
imul eax,edx
add eax,eax
mov [edi+16],eax
mov dword ptr [edi+20],1
add esi,0x12f808
xor ebp,ebp
stripe:
mov eax,ebp
imul eax,[edi+12]
shr eax,4
shl eax,11
push esi
add esi,eax
lea eax,[ebp+1]
imul eax,[edi+12]
shr eax,4
mov ebx,ebp
imul ebx,[edi+12]
shr ebx,4
sub eax,ebx
mov ebx,eax
mov eax,0x811c9dc5
test ebx,ebx
jz stripe_done
row:
mov ecx,[edi+8]
add ecx,ecx
push esi
bytes_loop:
movzx edx,byte ptr [esi]
xor eax,edx
imul eax,eax,0x1000193
inc esi
dec ecx
jnz bytes_loop
pop esi
add esi,2048
dec ebx
jnz row
stripe_done:
pop esi
mov [edi+ebp*4+384],eax
inc ebp
cmp ebp,16
jne stripe
jmp done
invalid:
mov dword ptr [edi+20],2
done:
popad
popfd
ret
'''
