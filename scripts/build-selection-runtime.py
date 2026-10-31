"""Generate the installed extended-selection runtime and its relocation table."""
from pathlib import Path
import sys, struct, json, importlib.util
sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'.tools'))
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import *
from capstone.x86 import *
import pefile
BASE=0x20000000
DATA=BASE+0x10000
COUNTS=DATA
LISTS=DATA+0x1000
GROUP_COUNTS=DATA+0xa000
GROUPS=DATA+0xb000
PENDING=DATA+0x66000
TRACK=DATA+0x66020
SUPPRESS=DATA+0x66024
STAMP=DATA+0x66040
TEXT=DATA+0x66080
SIZE=0x78000
blocks={}; hooks=[]; cursor=0
ks=Ks(KS_ARCH_X86,KS_MODE_32)
def reserve(name):
 global cursor
 blocks[name]={'address':BASE+cursor};cursor+=0x800
 return blocks[name]['address']
for name in ('add','sync','select','rectangle','rect_native','first_accept','second_accept','rescan','wire','before','right','order','batch','group','group_native','key','hud','filter','reset','prune','terrain_visibility','resource_text','observer_view','replay_hud_gate','observer_visibility','replay_voice'):
 reserve(name)
def at(name):return blocks[name]['address']
def code(name,source):
 source=source.replace('jz flags','jz draw_flags').replace('flags:','draw_flags:');result=bytes(ks.asm(source,at(name))[0]);assert len(result)<=0x800,(name,len(result));blocks[name]['code']=result;blocks[name]['asm']=source

def hook(site,name,before):hooks.append((site,at(name),bytes.fromhex(before)))
code('add',f'''
mov eax,[esp+4]
cmp eax,1
jb done
cmp eax,8
ja done
mov edx,[esp+8]
cmp edx,1700
jae done
mov ecx,[eax*4+{COUNTS}]
cmp ecx,1700
jae done
inc dword ptr [eax*4+{COUNTS}]
shl eax,12
mov word ptr [eax+ecx*2+{LISTS}],dx
done: ret
''')
code('sync',f'''
push ebp
mov ebp,esp
push ebx
push esi
push edi
mov ebx,[ebp+8]
cmp ebx,1
jb done
cmp ebx,8
ja done
mov edx,[0x504a10]
test edx,edx
jz done
mov eax,ebx
shl eax,6
lea edi,[edx+eax+0x7218]
mov ecx,16
mov eax,-1
cld
rep stosd
mov eax,ebx
shl eax,6
lea edi,[edx+eax+0x7218]
mov esi,ebx
shl esi,12
add esi,{LISTS}
mov ecx,[ebx*4+{COUNTS}]
cmp ecx,1700
ja done
cmp ecx,16
jbe copy
mov ecx,16
copy:
test ecx,ecx
jz flags
movzx eax,word ptr [esi]
mov [edi],eax
add esi,2
add edi,4
dec ecx
jmp copy
flags:
movzx eax,byte ptr [0x4e7270]
cmp eax,ebx
jne done
mov eax,[ebx*4+{COUNTS}]
mov dword ptr [0x4fa65c],-1
test eax,eax
jz no_primary
mov eax,ebx
shl eax,12
movzx eax,word ptr [eax+{LISTS}]
mov [0x4fa65c],eax
no_primary:
mov eax,ebx
shl eax,6
lea esi,[edx+eax+0x7218]
lea edi,[edx+0x7498]
mov ecx,16
rep movsd dword ptr es:[edi],dword ptr [esi]
lea edi,[edx+0x1a98]
mov ecx,1700
xor eax,eax
rep stosb
mov esi,ebx
shl esi,12
add esi,{LISTS}
mov ecx,[ebx*4+{COUNTS}]
flag_loop:
test ecx,ecx
jz done
movzx eax,word ptr [esi]
cmp eax,1700
jae flag_next
mov byte ptr [edx+eax+0x1a98],1
flag_next:
add esi,2
dec ecx
jmp flag_loop
done:
pop edi
pop esi
pop ebx
pop ebp
ret
''')
code('select',f'''
push ebp
mov ebp,esp
push ebx
push esi
push edi
mov ebx,[ebp+8]
cmp ebx,1
jb done
cmp ebx,8
ja done
mov dword ptr [ebx*4+{COUNTS}],0
xor esi,esi
scan:
mov edx,[0x504a10]
test edx,edx
jz done
cmp esi,1700
jae finish
cmp esi,[edx+4]
jae finish
mov edi,[edx+esi*4+8]
test edi,edi
jz next
cmp byte ptr [edi+0x13b8],0
je next
movzx eax,byte ptr [edi+0x3c]
cmp eax,ebx
jne next
cmp dword ptr [edi+0x30],0
jne next
cmp byte ptr [edi+0x464],0xc
je next
cmp byte ptr [edi+0x464],0xd
je next
push esi
call 0x40a210
add esp,4
cmp dword ptr [ebp+12],14
je worker
test eax,eax
jnz next
mov edx,[edi+8]
test edx,edx
jz next
cmp byte ptr [edx+0x23d],6
je next
jmp accept
worker:
test eax,eax
jz next
cmp byte ptr [edi+0x464],0
je accept
cmp byte ptr [edi+0x464],5
jne next
accept:
push esi
push ebx
call {at('add')}
add esp,8
next:
inc esi
jmp scan
finish:
push ebx
call {at('sync')}
add esp,4
movzx eax,byte ptr [0x4e7270]
cmp eax,ebx
jne done
mov dword ptr [{DATA+0x66028}],1
cmp dword ptr [0x50313c],0
je done
cmp dword ptr [ebx*4+{COUNTS}],0
je done
push 3
call 0x40f630
add esp,4
push 1
push 0
call 0x425ee0
add esp,8
done:
pop edi
pop esi
pop ebx
pop ebp
ret
''')
# Capture every native accepted unit before the old sixteen-slot write guard.
for name,site,old,resume,playerOffset in (
 ('first_accept',0x44dd7f,'8b4c241c83f910',0x44dd86,0x38),
 ('second_accept',0x44df1b,'83fb107d24',0x44df20,0x38)):
 body=f'''pushfd
pushad
mov eax,[esp+{playerOffset+36}]
and eax,255
cmp eax,[{TRACK}]
jne skip
push esi
push eax
call {at('add')}
add esp,8
skip:
popad
popfd
'''
 if name=='first_accept':body+='mov ecx,[esp+0x1c]\ncmp ecx,16\njmp 0x44dd86'
 else:body+='cmp ebx,16\njge 0x44df44\njmp 0x44df20'
 code(name,body);hook(site,name,old)
code('rescan',f'''pushfd
push eax
movzx eax,byte ptr [esp+0x40]
cmp eax,[{TRACK}]
jne skip
mov dword ptr [eax*4+{COUNTS}],0
skip:
pop eax
popfd
mov edx,[esp+0x38]
mov esi,16
jmp 0x44de09
''')
hook(0x44de00,'rescan','8b542438be10000000')
code('rect_native','sub esp,0x20\npush ebx\npush ebp\njmp 0x44dbd5')
code('rectangle',f'''
push ebp
mov ebp,esp
push ebx
push esi
push edi
sub esp,8
mov [ebp-16],ecx
mov ebx,[ebp+12]
and ebx,255
cmp ebx,1
jb original
cmp ebx,8
ja original
mov [{TRACK}],ebx
mov dword ptr [ebx*4+{COUNTS}],0
original:
push dword ptr [ebp+20]
push dword ptr [ebp+16]
push dword ptr [ebp+12]
push dword ptr [ebp+8]
mov ecx,[ebp-16]
call {at('rect_native')}
mov [ebp-20],eax
mov dword ptr [{TRACK}],0
cmp ebx,1
jb done
cmp ebx,8
ja done
push ebx
call {at('filter')}
add esp,4
mov eax,[0x503c6c]
mov [ebx*4+{STAMP}],eax
push ebx
call {at('sync')}
add esp,4
cmp dword ptr [{SUPPRESS}],0
jne done
cmp dword ptr [0x513ed4],1
jne done
movzx eax,byte ptr [0x4e7270]
cmp eax,ebx
jne done
mov dword ptr [{PENDING}],1
mov esi,[ebp+16]
mov edi,{PENDING+4}
mov ecx,4
cld
rep movsd dword ptr es:[edi],dword ptr [esi]
done:
mov eax,[ebp-20]
add esp,8
pop edi
pop esi
pop ebx
pop ebp
ret 16
''')
hook(0x44dbd0,'rectangle','83ec205355')
code('wire',f'''
pushfd
pushad
cmp dword ptr [{PENDING}],1
jne done
mov dword ptr [{PENDING}],0
sub esp,32
mov edi,esp
mov eax,0x06a406a4
mov ecx,8
cld
rep stosd
mov word ptr [esp],4095
mov word ptr [esp+2],0xa31
mov esi,{PENDING+4}
lea edi,[esp+4]
mov ecx,4
coordinates:
mov eax,[esi]
mov edx,eax
and eax,4095
shr edx,12
and edx,4095
mov [edi],ax
mov [edi+2],dx
add esi,4
add edi,4
loop coordinates
mov esi,esp
mov edi,0x51be70
mov ecx,8
pack:
movzx eax,word ptr [esi]
movzx edx,word ptr [esi+2]
mov [edi],al
shr eax,8
shl al,4
mov [edi+2],dl
shr edx,8
or al,dl
mov [edi+1],al
add esi,4
add edi,3
loop pack
mov byte ptr [0x51be8b],16
add esp,32
done:
popad
popfd
mov eax,[0x504a10]
jmp 0x4079bc
''')
hook(0x4079b7,'wire','a1104a5000')
code('before',f'''
pushfd
pushad
mov eax,ebx
cmp eax,1
jb done
cmp eax,8
ja done
shl eax,6
lea edi,[eax+0x52f510]
movzx eax,byte ptr [edi+3]
cmp eax,13
je select_all
cmp eax,14
je select_all
cmp byte ptr [edi+10],0
je compare
cmp word ptr [edi+30],4095
jne compare
cmp word ptr [edi+32],0xa31
jne compare
sub esp,16
mov esi,esp
lea edx,[edi+34]
mov ecx,4
unpack:
movzx eax,word ptr [edx]
and eax,4095
movzx ebp,word ptr [edx+2]
and ebp,4095
shl ebp,12
or eax,ebp
shl eax,8
sar eax,8
mov [esi],eax
add edx,4
add esi,4
loop unpack
mov eax,[esp]
cmp eax,[esp+8]
jg invalid_rect
mov eax,[esp+4]
cmp eax,[esp+12]
jg invalid_rect
mov dword ptr [{SUPPRESS}],1
mov esi,esp
push 1
push esi
push ebx
movzx eax,byte ptr [0x4e7270]
push eax
mov ecx,[0x504a10]
call 0x44dbd0
mov dword ptr [{SUPPRESS}],0
invalid_rect:
add esp,16
jmp done
select_all:
push eax
push ebx
call {at('select')}
add esp,8
jmp done
compare:
cmp dword ptr [ebx*4+{COUNTS}],0
je done
mov eax,ebx
shl eax,6
mov edx,[0x504a10]
lea edi,[edx+eax+0x7218]
mov esi,ebx
shl esi,12
add esi,{LISTS}
mov ecx,[ebx*4+{COUNTS}]
cmp ecx,16
jbe check
mov ecx,16
check:
movzx eax,word ptr [esi]
cmp eax,[edi]
je matched
cmp dword ptr [edi],-1
jne clear
mov ebp,[0x504a10]
mov ebp,[ebp+eax*4+8]
test ebp,ebp
jz matched
cmp byte ptr [ebp+0x13b8],0
jne clear
matched:
add esi,2
add edi,4
loop check
push ebx
call {at('prune')}
add esp,4
jmp done
clear:
mov dword ptr [ebx*4+{COUNTS}],0
done:
popad
popfd
mov esi,[esp+0x10]
mov eax,[0x4e7270]
jmp 0x48bc8b
''')
hook(0x48bc82,'before','8b742410a170724e00')
# Preserve the input packet in a private stack copy during each native batch.
for name,handler,site in [('right',0x408390,0x48bd48),('order',0x420410,0x48bd41)]:
 code(name,f'''
push ebp
mov ebp,esp
push esi
push edi
sub esp,64
mov eax,[ebp+8]
cmp eax,1
jb normal
cmp eax,8
ja normal
mov edx,[eax*4+{COUNTS}]
cmp edx,16
jbe normal
cmp edx,1700
ja normal
mov esi,eax
shl esi,6
add esi,0x52f510
mov edi,esp
mov ecx,16
cld
rep movsd dword ptr es:[edi],dword ptr [esi]
mov ecx,esp
mov esi,eax
shl esi,12
add esi,{LISTS}
push {handler}
push ecx
push esi
push edx
push eax
call {at('batch')}
add esp,20
jmp done
normal:
push eax
call {handler}
add esp,4
done:
add esp,64
pop edi
pop esi
pop ebp
ret
''')
 hooks.append((site,at(name),b'\xe8'+struct.pack('<i',handler-site-5)))
spec=importlib.util.spec_from_file_location('batch',Path(__file__).with_name('build-selection-bridge.py'));batch=importlib.util.module_from_spec(spec);spec.loader.exec_module(batch)
code('batch',batch.ASSEMBLY)
code('group_native','sub esp,0x14\npush ebx\nmov ebx,[esp+0x1c]\njmp 0x40c0e8')
code('group',f'''
push ebp
mov ebp,esp
push ebx
push esi
push edi
mov ebx,[ebp+8]
push ebx
call {at('group_native')}
add esp,4
cmp ebx,1
jb done
cmp ebx,8
ja done
mov eax,ebx
shl eax,6
movzx edx,byte ptr [eax+0x52f513]
cmp edx,10
jae done
imul ecx,ebx,10
add ecx,edx
mov esi,ebx
shl esi,12
add esi,{LISTS}
mov edi,ecx
shl edi,12
add edi,{GROUPS}
test byte ptr [eax+0x52f514],1
jz recall
mov edx,[ebx*4+{COUNTS}]
mov [ecx*4+{GROUP_COUNTS}],edx
cmp edx,1700
ja done
mov ecx,edx
cld
rep movsw
jmp done
recall:
mov edx,[ecx*4+{GROUP_COUNTS}]
mov [ebx*4+{COUNTS}],edx
test edx,edx
jz done
cmp edx,1700
ja done
xchg edi,esi
mov ecx,edx
cld
rep movsw
push ebx
call {at('sync')}
add esp,4
done:
pop edi
pop esi
pop ebx
pop ebp
ret
''')
hook(0x40c0e0,'group','83ec14538b5c241c')
code('key',f'''
pushfd
pushad
call {at('reset')}
popad
popfd
cmp esi,0x3b
je army
cmp esi,0x33
je idle
jmp original
army:
push edx
mov edx,13
jmp guards
idle:
push edx
mov edx,14
guards:
cmp byte ptr [0x504f48],4
jne denied
cmp dword ptr [0x51a8a0],1
je denied
cmp byte ptr [0x513ec8],0
jne denied
cmp byte ptr [0x5030c9],0
jne denied
cmp byte ptr [ecx+0x5304dc],0
jne denied
cmp dword ptr [ecx*4+0x507b30],0
jne denied
mov byte ptr [eax+0x52f513],dl
pop edx
jmp 0x4537be
denied:
pop edx
original:
cmp esi,0x43
ja 0x4537be
xor edx,edx
mov dl,byte ptr [esi+0x454844]
jmp 0x4537a3
''')
hook(0x453799,'key','772333d28a9644484500')
code('hud',f'''
pushfd
pushad
cmp dword ptr [0x4f75ec],1024
jne replay_resources_done
cmp dword ptr [0x233a000],2
jne replay_resources_done
xor ebx,ebx
replay_resource_row:
mov esi,ebx
shl esi,7
add esi,{BASE+0x76800}
cmp byte ptr [esi],0
je next_resource_row
push 0xe6e6e6
push esi
push 14
imul eax,ebx,18
add eax,40
push eax
push 760
call 0x4a8720
add esp,20
next_resource_row:
inc ebx
cmp ebx,8
jb replay_resource_row
replay_resources_done:
cmp dword ptr [{DATA+0x66028}],0
je count_only
cmp dword ptr [0x50313c],0
je count_only
mov dword ptr [{DATA+0x66028}],0
movzx ebx,byte ptr [0x4e7270]
push ebx
call {at('sync')}
add esp,4
cmp dword ptr [ebx*4+{COUNTS}],0
je clear_panel
push 3
jmp panel
clear_panel:
push 2
panel:
call 0x40f630
add esp,4
push 1
push 0
call 0x425ee0
add esp,8
count_only:
movzx eax,byte ptr [0x4e7270]
cmp eax,1
jb done
cmp eax,8
ja done
mov eax,[eax*4+{COUNTS}]
cmp eax,16
jbe done
cmp eax,1700
ja done
mov edi,{TEXT+16}
mov byte ptr [edi],0
mov ebx,10
digit:
xor edx,edx
div ebx
add dl,48
dec edi
mov [edi],dl
test eax,eax
jnz digit
push 0xe6e6e6
push edi
push 14
mov eax,[0x4f75f0]
sub eax,164
push eax
mov eax,[0x4f9db0]
add eax,470
push eax
call 0x4a8720
add esp,20
done:
popad
popfd
add esp,8
push ebx
push ebx
jmp 0x4a6038
''')
hook(0x4a6033,'hud','83c4085353')

code('filter',f'''
push ebp
mov ebp,esp
push ebx
push esi
push edi
mov ebx,[ebp+8]
mov esi,ebx
shl esi,12
add esi,{LISTS}
mov edi,esi
mov ecx,[ebx*4+{COUNTS}]
xor edx,edx
scan:
test ecx,ecx
jz finish
movzx eax,word ptr [esi]
push ecx
mov ecx,[0x504a10]
mov ecx,[ecx+eax*4+8]
test ecx,ecx
jz skip
cmp dword ptr [ecx+0x30],0
jne skip
cmp word ptr [ecx+12],0x22a
je skip
mov [edi],ax
add edi,2
inc edx
skip:
pop ecx
add esi,2
dec ecx
jmp scan
finish:
test edx,edx
jnz count
mov eax,ebx
shl eax,6
mov ecx,[0x504a10]
mov eax,[ecx+eax+0x7218]
cmp eax,1700
jae count
mov ecx,ebx
shl ecx,12
mov word ptr [ecx+{LISTS}],ax
mov edx,1
count:
mov [ebx*4+{COUNTS}],edx
pop edi
pop esi
pop ebx
pop ebp
ret
''')
code('reset',f'''
mov eax,[0x504a10]
mov edx,[0x503c6c]
cmp dword ptr [{PENDING+0x100}],0
je update
cmp eax,[{PENDING+0x100}]
jne clear
cmp edx,[{PENDING+0x104}]
jae update
clear:
push eax
push edx
mov edi,{DATA}
mov ecx,0x65000/4
xor eax,eax
cld
rep stosd
mov dword ptr [{PENDING}],0
pop edx
pop eax
update:
mov [{PENDING+0x100}],eax
mov [{PENDING+0x104}],edx
ret
''')


code('prune',f'''
push ebp
mov ebp,esp
push ebx
push esi
push edi
mov ebx,[ebp+8]
mov esi,ebx
shl esi,12
add esi,{LISTS}
mov edi,esi
mov ecx,[ebx*4+{COUNTS}]
xor edx,edx
scan:
test ecx,ecx
jz finish
movzx eax,word ptr [esi]
push ecx
mov ecx,[0x504a10]
mov ecx,[ecx+eax*4+8]
test ecx,ecx
jz skip
cmp byte ptr [ecx+0x13b8],0
je skip
movzx ecx,byte ptr [ecx+0x3c]
cmp ecx,ebx
jne skip
mov [edi],ax
add edi,2
inc edx
skip:
pop ecx
add esi,2
dec ecx
jmp scan
finish:
mov [ebx*4+{COUNTS}],edx
push ebx
call {at('sync')}
add esp,4
pop edi
pop esi
pop ebx
pop ebp
ret
''')

# Relocate absolute sidecar addresses and external relative calls/branches.
# Only viewport terrain-cache queries receive explored-style shading.
# Authoritative sight buffers and entity visibility queries remain unchanged.
code('terrain_visibility',"""
mov eax,[esp+8]
push eax
push dword ptr [esp+8]
call 0x42b230
cmp dword ptr [0x4f75ec],1024
jne shading
cmp dword ptr [0x233a000],2
jne shading
xor eax,eax
ret 8
shading:
cmp al,2
jne done
mov al,1
done:
ret 8
""")
terrain_sites=[4366496, 4366517, 4366550, 4366573, 4366589, 4366608, 4366624, 4366643, 4366659, 4366678, 4366705, 4366725, 4366741, 4366757, 4366773, 4366792, 4366812, 4366831, 4366862, 4366885, 4366901, 4366920, 4366936, 4366955, 4366971, 4366990, 4367017, 4367037, 4367053, 4367069, 4367085, 4367104, 4367124, 4367143, 4367174, 4367197, 4367213, 4367232, 4367248, 4367267, 4367283, 4367302, 4367329, 4367349, 4367365, 4367381, 4367397, 4367416, 4367436, 4367455, 4367486, 4367509, 4367525, 4367544, 4367560, 4367579, 4367595, 4367614, 4367641, 4367661, 4367677, 4367693, 4367709, 4367728, 4367748, 4367767, 4367798, 4367821, 4367837, 4367856, 4367872, 4367891, 4367907, 4367926, 4367953, 4367969, 4367985, 4368004, 4368020, 4368047, 4368063, 4368079, 4368095, 4368114, 4368141, 4368160, 4368176, 4368192, 4368208, 4368235, 4368251, 4368270, 4368286, 4368302, 4368329, 4368352, 4368368, 4368387, 4368403, 4368422, 4368438, 4368457, 4368484, 4368507, 4368527, 4368550, 4368570, 4368593, 4368613, 4368636, 4368674, 4368697, 4368713, 4368732, 4368748, 4368767, 4368783, 4368802, 4368829, 4368849, 4368865, 4368881, 4368897, 4368916, 4368936, 4368955, 4368986, 4369009, 4369025, 4369044, 4369060, 4369079, 4369095, 4369114, 4369141, 4369161, 4369177, 4369193, 4369209, 4369228, 4369248, 4369267, 4369298, 4369321, 4369337, 4369356, 4369372, 4369391, 4369407, 4369426, 4369453, 4369473, 4369489, 4369505, 4369521, 4369540, 4369560, 4369579, 4369610, 4369633, 4369649, 4369668, 4369684, 4369703, 4369719, 4369738, 4369765, 4369785, 4369801, 4369817, 4369833, 4369852, 4369872, 4369891, 4369922, 4369945, 4369961, 4369980, 4369996, 4370015, 4370031, 4370050, 4370077, 4370093, 4370109, 4370128, 4370144, 4370171, 4370187, 4370203, 4370219, 4370238, 4370265, 4370284, 4370300, 4370316, 4370332, 4370359, 4370375, 4370394, 4370410, 4370426, 4371728, 4371900, 4371924, 4371943, 4371959, 4371979, 4371998, 4372014, 4372030, 4372049, 4372065, 4372081, 4372100, 4372116]
for site in terrain_sites:hooks.append((site,at('terrain_visibility'),b'\xe8'+struct.pack('<i',0x42b230-site-5)))

code('resource_text',"jmp 0x428f70")
resource_sites=[]
for site in resource_sites:hooks.append((site,at('resource_text'),b'\xe8'+struct.pack('<i',0x428f70-site-5)))

code('observer_view',"jmp 0x4296d0")
observer_sites=[4767183, 4767767, 4768498, 4768805, 4768978, 4769114, 4769845, 4770149, 4770320, 4770673, 4770728, 4870529]
for site in observer_sites:hooks.append((site,at('observer_view'),b'\xe8'+struct.pack('<i',0x4296d0-site-5)))

code('replay_hud_gate',f"""
cmp dword ptr [0x4f75ec],1024
jne normal
cmp dword ptr [0x233a000],2
jne normal
cmp dword ptr [{BASE+0x76704}],0
je normal
jmp 0x4a61af
normal:
mov eax,[0x4fa65c]
jmp 0x4a49f4
""")
hook(0x4a49ef,'replay_hud_gate','a15ca64f00')

code('observer_visibility',"""
cmp dword ptr [0x4f75ec],1024
jne normal
cmp dword ptr [0x233a000],2
jne normal
xor eax,eax
ret 8
normal:
jmp 0x42b230
""")
visibility_sites=[4745594, 4745750, 4751616, 4751797, 4752145, 4752295, 4753114, 4753282, 4757631, 4758100, 4758611, 4759065, 4759409, 4760060, 4760777, 4874800, 4876100]
for site in visibility_sites:hooks.append((site,at('observer_visibility'),b'\xe8'+struct.pack('<i',0x42b230-site-5)))
code('replay_voice',"""
cmp dword ptr [0x4f75ec],1024
jne normal
cmp dword ptr [0x233a000],2
jne normal
xor eax,eax
ret
normal:
jmp 0x4bbf80
""")
voice_sites=[0x493a3d,0x493b26,0x493c7f,0x493e0f]
for site in voice_sites:hooks.append((site,at('replay_voice'),b'\xe8'+struct.pack('<i',0x4bbf80-site-5)))
payload=bytearray(0x10000);absolute=[];relative=[]
md=Cs(CS_ARCH_X86,CS_MODE_32);md.detail=True
for name,b in blocks.items():
 blob=b['code'];offset=b['address']-BASE;payload[offset:offset+len(blob)]=blob
 for ins in md.disasm(blob,b['address']):
  for op in ins.operands:
   if op.type==X86_OP_MEM and BASE<=op.mem.disp<BASE+SIZE:
    assert ins.disp_size==4;absolute.append(ins.address-BASE+ins.disp_offset)
   if op.type==X86_OP_IMM:
    branch=ins.group(CS_GRP_JUMP) or ins.group(CS_GRP_CALL) or ins.mnemonic.startswith("loop")
    if branch and not BASE<=op.imm<BASE+SIZE:
     assert ins.imm_size==4,(name,ins.mnemonic,ins.op_str);relative.append(ins.address-BASE+ins.imm_offset)
    elif not branch and BASE<=op.imm<BASE+SIZE:
     assert ins.imm_size==4,(name,ins.mnemonic,ins.op_str,ins.imm_size);absolute.append(ins.address-BASE+ins.imm_offset)
# Keep native CALL sites as calls, all other replacements as jumps.
call_sites={0x48bd48,0x48bd41}.union(terrain_sites).union(resource_sites).union(observer_sites).union(visibility_sites).union(voice_sites)
meta={'base':BASE,'size':SIZE,'data':DATA,'counts':COUNTS,'lists':LISTS,'group_counts':GROUP_COUNTS,'groups':GROUPS,'pending':PENDING,'stamp':STAMP,'blocks':{n:b['address'] for n,b in blocks.items()},'absolute':sorted(set(absolute)),'relative':sorted(set(relative)),'hooks':[{'site':s,'target':t,'before':v.hex(),'opcode':0xe8 if s in call_sites else 0xe9} for s,t,v in hooks]}
Path('.tools/selection-runtime.bin').write_bytes(payload)
Path('.tools/selection-runtime.json').write_text(json.dumps(meta,indent=2))
import base64
cs='''using System;using System.IO;using System.Linq;using System.Collections.Generic;using System.Runtime.InteropServices;
namespace Amagadon {
 public static partial class SelectionRuntime {
  public const int Protocol=1,AllocationSize=SIZEVALUE;
  [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr p,IntPtr a,UIntPtr s,uint type,uint protect);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool VirtualProtectEx(IntPtr p,IntPtr a,UIntPtr s,uint protect,out uint old);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr p,IntPtr a,byte[] b,int s,out IntPtr n);
  public static Dictionary<int,byte[]> Build(int cave) {
   var result=new Dictionary<int,byte[]>();byte[] payload=Convert.FromBase64String("PAYLOAD");int delta=unchecked(cave-0x20000000);
   foreach(int offset in new int[]{ABSOLUTE})Buffer.BlockCopy(BitConverter.GetBytes(unchecked(BitConverter.ToInt32(payload,offset)+delta)),0,payload,offset,4);
   foreach(int offset in new int[]{RELATIVE})Buffer.BlockCopy(BitConverter.GetBytes(unchecked(BitConverter.ToInt32(payload,offset)-delta)),0,payload,offset,4);
   result.Add(cave,payload);
HOOKS
   result.Add(0x4d96e0,NetworkGuard.Hex("d65f12bfb6aa8347b154d17783ab6831"));
   result.Add(0x4a5274,NetworkGuard.Hex("eb1f"));
   result.Add(0x4a5380,NetworkGuard.Hex("eb19"));
   result.Add(0x4a52a6,NetworkGuard.Hex("3c007450"));
   result.Add(0x4a53a8,NetworkGuard.Hex("3c00744a"));
   return result;
  }
  public static int Apply(IntPtr process,string hash) {
   if(hash!=NativePatch.InputHash && hash!="1a3051c992ea27f3b10545f6623642c2071d31070ae54d5e98129f99c9cb6c22")throw new IOException("선택 확장을 지원하지 않는 게임 버전입니다.");
   var expected=new Dictionary<int,string>{EXPECTED,{0x4d96e0,"c0bed0f7db66d311acd300105a6b9578"},{0x4a5274,"751f"},{0x4a5380,"7519"},{0x4a52a6,"3c017550"},{0x4a53a8,"3c01754a"}};
   foreach(var e in expected){byte[] b=new byte[e.Value.Length/2];IntPtr n;if(!ReadProcessMemory(process,new IntPtr(e.Key),b,b.Length,out n)||n.ToInt64()!=b.Length||!b.SequenceEqual(NetworkGuard.Hex(e.Value)))throw new IOException("선택 확장 대상 코드 불일치: "+e.Key.ToString("X8"));}
   IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,new UIntPtr(AllocationSize),0x3000,4);if(memory==IntPtr.Zero)throw new IOException("선택 확장 메모리 할당 실패");
   int cave=memory.ToInt32();var edits=Build(cave);NetworkGuard.Write(process,cave,edits[cave]);uint old;
   if(!VirtualProtectEx(process,memory,new UIntPtr(65536),0x20,out old))throw new IOException("선택 확장 코드 보호 설정 실패");
   foreach(var e in edits)if(e.Key!=cave)NetworkGuard.Write(process,e.Key,e.Value);
   Core.Log("Selection runtime installed: F2/period, 1700-unit sidecar, native command batches, rectangle wire protocol 1; address="+cave.ToString("X8"));return cave;
  }
 }
}
'''
hookcs=[]
for h in meta['hooks']:
 hookcs.append('   {byte[] b=Enumerable.Repeat((byte)0x90,'+str(len(bytes.fromhex(h['before'])))+').ToArray();b[0]='+str(h['opcode'])+';Buffer.BlockCopy(BitConverter.GetBytes(unchecked(cave+'+str(h['target']-BASE)+'-'+str(h['site']+5)+')),0,b,1,4);result.Add('+hex(h['site'])+',b);}')
cs=cs.replace('SIZEVALUE',str(SIZE)).replace('PAYLOAD',base64.b64encode(payload).decode()).replace('ABSOLUTE',','.join(map(str,sorted(set(absolute))))).replace('RELATIVE',','.join(map(str,sorted(set(relative))))).replace('HOOKS','\n'.join(hookcs)).replace('EXPECTED',','.join('{'+hex(s)+',"'+v.hex()+'"}' for s,t,v in hooks))
Path('src/SelectionRuntime.cs').write_text(cs,encoding='utf-8-sig')
print('Generated installed selection runtime:',len(hooks),'hooks;',len(absolute),'absolute and',len(relative),'relative relocations')
