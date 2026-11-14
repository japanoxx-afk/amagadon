"""EAD plan repair and unavailable-producer starvation prevention."""
def plan():
 # Use the native 4558D0 replenishment producer (206), not a building name.
 # EAX is the original plan-table index, ECX the AI brain. Return the
 # normalized row count while preserving the native selector's other state.
 return '''
pushfd
pushad
cmp eax,6
jb done
cmp eax,8
ja done
mov ebx,[ecx+0xfc]
test ebx,ebx
jz done
mov eax,[eax*4+0x504e78]
cmp eax,1
jb done
cmp eax,399
ja done
xor esi,esi
xor edx,edx
xor ebp,ebp
mov edi,ebx
scan:
cmp esi,eax
jae finish
cmp dword ptr [edi+4],1
jne building
cmp dword ptr [edi+8],0x226
jb next
cmp dword ptr [edi+8],0x229
ja next
cmp dword ptr [edi+12],0x210
jne next
mov dword ptr [edi+12],0x206
jmp next
building:
cmp dword ptr [edi+4],0
jne next
cmp dword ptr [edi+8],0x204
jne addon
inc edx
jmp next
addon:
cmp dword ptr [edi+8],0x205
je counted
cmp dword ptr [edi+8],0x206
jne next
counted:
inc ebp
cmp ebp,edx
jbe next
cmp eax,399
jae next
pushad
mov ecx,eax
sub ecx,esi
imul ecx,ecx,5
imul esi,eax,20
lea esi,[ebx+esi-4]
lea edi,[esi+20]
std
rep movsd dword ptr es:[edi], dword ptr [esi]
cld
popad
mov dword ptr [edi],2
mov dword ptr [edi+4],0
mov dword ptr [edi+8],0x204
mov dword ptr [edi+12],0
mov dword ptr [edi+16],0
inc eax
inc edx
inc esi
add edi,20
next:
inc esi
add edi,20
jmp scan
finish:
mov ecx,[esp+28]
mov [ecx*4+0x504e78],eax
done:
popad
popfd
mov eax,[eax*4+0x504e78]
ret
'''

def replenishment():
 # The original ascending deficit scan must continue when its chosen native
 # producer cannot admit a request; otherwise one full queue starves all
 # later unit kinds. Do not change target counts, RNG or plan advancement.
 return """
call 0x4552a0
test al,al
jz next
pushfd
pushad
cmp dword ptr [esi+0x10],2
jne accepted
cmp edi,0x1c
jb accepted
cmp edi,0x2b
ja accepted
mov edx,0x200
cmp edi,0x1f
jb parent
mov edx,0x204
cmp edi,0x20
jb parent
cmp edi,0x23
jb parasite
cmp edi,0x26
jb parent
mov edx,0x206
jmp parent
parasite:
mov edx,0x205
parent:
push edx
push dword ptr [esi+0x14]
mov ecx,[0x504a10]
call 0x4510f0
cmp eax,-1
je rejected
mov ecx,[0x504a10]
mov eax,[ecx+eax*4+8]
cmp dword ptr [eax+0x85c],8
jge rejected
accepted:
popad
popfd
jmp 0x455eb2
rejected:
popad
popfd
next:
jmp 0x455e72
"""

def population():
 # Replaces CALL 455C90, after the native resource snapshot. Only emit
 # ordinary housing construction when an EAD front queue lacks population.
 return """
pushfd
pushad
sub esp,8
mov esi,ecx
cmp dword ptr [esi+0x10],2
jne native
mov ebx,[esi+0x14]
mov ebp,[0x504a10]
lea eax,[ebx+ebx*2]
add eax,2
mov edx,[ebp+eax*4+0x24998]
cmp edx,200
jge native
mov [esp+4],edx
mov edx,[ebp+eax*4+0x24920]
mov [esp],edx
xor edi,edi
scan:
cmp edi,[ebp+4]
jge native
mov eax,[ebp+edi*4+8]
test eax,eax
jz next
cmp byte ptr [eax+0x3c],bl
jne next
cmp byte ptr [eax+0x13b8],1
jne next
cmp dword ptr [eax+0x85c],1
jle next
mov edx,[eax+0x75c]
cmp edx,0x21c
jb next
cmp edx,0x22b
ja next
and edx,0xff
push edx
mov ecx,[0x504a04]
call 0x40ddf0
movzx eax,byte ptr [eax+0x24c]
add eax,[esp]
cmp eax,[esp+4]
jg shortage
next:
inc edi
jmp scan
shortage:
push 0x203
push ebx
mov ecx,ebp
call 0x451090
test al,al
jnz native
push 0x203
push ebx
mov ecx,ebp
call 0x4510c0
test al,al
jnz native
push 0x203
mov ecx,esi
call 0x4552a0
test al,al
jz native
push 0
push 0x203
mov ecx,esi
call 0x4558a0
add esp,8
popad
popfd
mov eax,1
jmp 0x454f0d
native:
add esp,8
popad
popfd
call 0x455c90
jmp 0x454f0d
"""
