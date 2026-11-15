"""Scope simulation minimap geometry to the command sender, not the receiver UI."""
def assemblies(base):
    table=base+0x77500
    saved=base+0x77540
    active=base+0x77550
    return {
'layout_send': f"""
pushfd
cmp dword ptr [0x513ed4],1
jne done
and word ptr [0x52f264],0x7fff
cmp dword ptr [0x4f75ec],1024
jne done
cmp dword ptr [0x4f75f0],768
jne done
or word ptr [0x52f264],0x8000
done:
popfd
jmp 0x483ce0
""",
'layout_receive': f"""
mov ax,word ptr [ebp+11]
pushfd
push ecx
movzx ecx,ax
shr ecx,15
mov [edx+{table}],ecx
pop ecx
popfd
mov esi,1
jmp 0x483840
""",
'layout_enter': f"""
pushfd
pushad
cmp dword ptr [0x513ed4],1
jne done
mov edi,{saved}
mov esi,0x4f9dd0
mov ecx,4
cld
rep movsd dword ptr es:[edi],dword ptr [esi]
mov dword ptr [{active}],1
mov eax,[esp+40]
dec eax
mov eax,[eax*4+{table}]
xor edx,edx
cmp dword ptr [0x4f75ec],1024
jne local_ready
cmp dword ptr [0x4f75f0],768
jne local_ready
mov edx,1
local_ready:
sub eax,edx
imul edx,eax,112
imul eax,eax,168
add [0x4f9dd0],edx
add [0x4f9dd8],edx
add [0x4f9dd4],eax
add [0x4f9ddc],eax
done:
popad
popfd
jmp 0x4080a0
""",
'layout_leave': f"""
pushfd
pushad
cmp dword ptr [{active}],0
je done
mov esi,{saved}
mov edi,0x4f9dd0
mov ecx,4
cld
rep movsd dword ptr es:[edi],dword ptr [esi]
mov dword ptr [{active}],0
done:
popad
popfd
add ebp,4
inc ebx
add esi,64
jmp 0x48bda6
"""}

