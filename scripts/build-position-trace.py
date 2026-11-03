"""Observe original coordinate setter entry; never change game state or decisions."""
def assembly(base, site):
    t=base+0x5d5000
    return f'''
lea esp,[esp-256]
pushfd
pushad
cmp dword ptr [{base+0x80000}+28],1
jne done
cmp byte ptr [0x504f48],4
jne done
cmp dword ptr [0x513ed4],1
jne done
cmp dword ptr [{base+0x80000}+12],0
jne done
mov edx,[{base+0x80000}+20]
test edx,edx
jz done
cmp edx,[{t}+8]
je generation_ok
mov [{t}+8],edx
mov dword ptr [{t}+4],0
generation_ok:
mov ebx,[{t}+4]
inc ebx
mov eax,ebx
and eax,8191
shl eax,7
lea edi,[eax+{t+4096}]
mov dword ptr [edi],0
mov dword ptr [edi+124],0
mov [edi+8],edx
mov eax,[0x503c6c]
mov [edi+4],eax
mov esi,[esp+24]
movzx eax,word ptr [esi+14]
mov [edi+12],eax
mov dword ptr [edi+16],{site}
mov eax,[esp+296]
mov [edi+20],eax
mov eax,[esi+20]
mov [edi+24],eax
mov eax,[esi+24]
mov [edi+28],eax
mov eax,[esp+292]
mov [edi+96],eax
movzx eax,byte ptr [esi+60]
mov [edi+100],eax
movzx eax,word ptr [esi+12]
mov [edi+104],eax
mov [edi+108],esi
push edi
add edi,32
add esi,0x400
mov ecx,16
cld
rep movsd dword ptr es:[edi], dword ptr [esi]
pop edi
mov [edi+124],ebx
mov [edi],ebx
mov [{t}+4],ebx
mov dword ptr [{t}],0x31534f50
done:
popad
popfd
lea esp,[esp+256]
sub esp,0x10
push esi
mov esi,ecx
jmp {site+6}
'''

