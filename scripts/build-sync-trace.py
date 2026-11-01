"""Read-only simulation-boundary trace. Writes only its own bounded ring."""
def assembly(base,unit_trace):
 t=base+0x80000;r=base+0x81000
 return f'''
pushfd
pushad
cmp dword ptr [{t}+28],1
jne done
inc dword ptr [{t}+36]
cmp byte ptr [0x504f48],4
jne done
cmp dword ptr [0x513ed4],1
jne done
mov ebp,[0x504a10]
test ebp,ebp
jz done
mov eax,[0x503c6c]
cmp ebp,[{t}+24]
jne reset
cmp eax,[{t}+8]
jb reset
cmp dword ptr [{t}+4],0
je capture
cmp eax,[{t}+8]
je done
jmp freeze_check
reset:
mov [{t}+24],ebp
mov dword ptr [{t}+4],0
mov dword ptr [{t}+12],0
inc dword ptr [{t}+20]
mov dword ptr [{t}],0x31525453
jmp capture
freeze_check:
cmp dword ptr [{t}+12],0
jne done
cmp byte ptr [0x51a8e4],0
je capture
mov dword ptr [{t}+12],1
mov [{t}+16],eax
jmp capture
capture:
mov [{t}+8],eax
mov ebx,[{t}+4]
inc ebx
mov edi,ebx
and edi,1023
shl edi,11
add edi,{r}
mov dword ptr [edi],0
mov [edi+4],eax
movzx ecx,byte ptr [0x581158]
mov [edi+8],ecx
mov ecx,[0x503c70]
mov [edi+12],ecx
movzx ecx,byte ptr [0x4e7270]
mov [edi+16],ecx
movzx ecx,byte ptr [0x51a8e4]
mov [edi+20],ecx
mov dword ptr [edi+24],0x811c9dc5
mov dword ptr [edi+92],0x811c9dc5
mov ecx,[ebp+4]
cmp ecx,1700
jbe count_ok
mov ecx,1700
count_ok:
mov [edi+28],ecx
xor eax,eax
mov ecx,10
push edi
add edi,32
rep stosd
pop edi
fnstcw word ptr [edi+80]
mov dword ptr [edi+84],0xffffffff
mov ecx,[0x4f8a10]
cmp ecx,64
jae tls_done
mov edx,fs:[ecx*4+0xe10]
test edx,edx
jz tls_done
mov edx,[edx+20]
mov [edi+84],edx
tls_done:
push edi
add edi,96
xor eax,eax
mov ecx,8
rep stosd
pop edi
xor esi,esi
unit_loop:
cmp esi,[edi+28]
jae unit_done
mov edx,[ebp+esi*4+8]
test edx,edx
jz unit_next
push edx
mov eax,[edx+0x414]
xor eax,[edx+0x478]
imul eax,eax,0x1000193
movzx ecx,byte ptr [edx+0x464]
xor eax,ecx
imul eax,eax,0x1000193
xor eax,[edx+0x1398]
imul eax,eax,0x1000193
xor eax,[edx+0x139c]
xor eax,esi
xor [edi+92],eax
imul ecx,[edi+92],0x1000193
mov [edi+92],ecx
movzx ecx,byte ptr [edx+60]
dec ecx
cmp ecx,7
ja order_hash_done
xor [edi+ecx*4+96],eax
imul edx,[edi+ecx*4+96],0x1000193
mov [edi+ecx*4+96],edx
order_hash_done:
pop edx
movzx eax,word ptr [edx+12]
xor eax,esi
imul eax,eax,0x1000193
xor eax,[edx+20]
imul eax,eax,0x1000193
xor eax,[edx+24]
imul eax,eax,0x1000193
xor eax,[edx+0x9c4]
imul eax,eax,0x1000193
movzx ecx,byte ptr [edx+0x13b8]
xor eax,ecx
movzx ecx,byte ptr [edx+60]
xor eax,ecx
xor [edi+24],eax
imul edx,[edi+24],0x1000193
mov [edi+24],edx
cmp ecx,9
ja unit_next
xor [edi+ecx*4+32],eax
imul edx,[edi+ecx*4+32],0x1000193
mov [edi+ecx*4+32],edx
unit_next:
inc esi
jmp unit_loop
unit_done:
call {unit_trace}
mov eax,[{t}+20]
mov [edi+88],eax
push edi
add edi,128
mov esi,0x52f210
mov ecx,352
rep movsd dword ptr es:[edi], dword ptr [esi]
pop edi
mov [edi+76],ebx
mov [edi],ebx
mov [{t}+4],ebx
done:
popad
popfd
ret
'''
