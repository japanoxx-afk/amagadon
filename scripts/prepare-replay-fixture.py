"""Build a disposable native transport fixture. Never executes game code or assets."""
from pathlib import Path
import struct,sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'.tools'))
import pefile
from keystone import Ks,KS_ARCH_X86,KS_MODE_32
source=Path(sys.argv[1]);target=Path(sys.argv[2]);data=bytearray(source.read_bytes());pe=pefile.PE(data=data)
if pe.OPTIONAL_HEADER.ImageBase!=0x400000:raise ValueError('Fixture image base')
section=pe.sections[-1];base=0x400000+section.VirtualAddress;box=base+0x26000
imports={i.name.decode():i.address for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports if i.name}
notify=base+0x24000;entry=base+0x24200
ks=Ks(KS_ARCH_X86,KS_MODE_32)
asm=f'''
 mov dword ptr [{box+12}], eax
 inc dword ptr [{box+4}]
 mov ebx, dword ptr [{box+4}]
 cmp dword ptr [{box+40}], 0
 je poll_start
 push dword ptr [{box+40}]
 call dword ptr [{imports['SetEvent']}]
 push 10000
 push dword ptr [{box+44}]
 call dword ptr [{imports['WaitForSingleObject']}]
 test eax, eax
 jnz timeout
 cmp dword ptr [{box+8}], ebx
 je ack
 jmp timeout
 poll_start:
 mov edi, 10000
 wait_ack:
 cmp dword ptr [{box+8}], ebx
 je ack
 push 1
 call dword ptr [{imports['Sleep']}]
 dec edi
 jnz wait_ack
 timeout:
 push 1
 call dword ptr [{imports['ExitProcess']}]
 ack:
 cmp dword ptr [{box}], 3
 jne ack_return
 cmp dword ptr [{box+12}], 4
 je ack_return
 push 0xe001
 call dword ptr [{imports['ExitProcess']}]
 ack_return: ret
'''
code=bytes(ks.asm(asm,notify)[0]);offset=section.PointerToRawData+0x24000;data[offset:offset+len(code)]=code
asm=f'''
 cld
 mov edi, 0x600000
 mov ecx, 0x8000
 xor eax, eax
 rep stosd
 mov dword ptr [0x504a10], 0x600000
 mov dword ptr [0x600008], 0x604000
 mov dword ptr [0x5049fc], 0x61b000
 mov dword ptr [0x61b00c], 0x61c000
 mov dword ptr [0x604004], 0xdead0000
 mov dword ptr [0x604008], 0xdead1000
 mov dword ptr [0x6041cc], 0xdead2000
 mov dword ptr [0x604210], 0xdead3000
 mov dword ptr [0x604234], 0xdead4000
 mov dword ptr [{0x61b000+0x57c+2*68}], 0x61f000
 mov dword ptr [{0x61b000+0x57c+2*68+4}], 0x61f00c
 mov dword ptr [{0x61b000+0x200c+2*4}], 0x61f004
 mov dword ptr [{0x61b000+0x296c+2*36}], 0x61f008
 mov dword ptr [0x60400c], 2
 mov dword ptr [0x604014], 10
 mov dword ptr [0x604018], 20
 mov dword ptr [0x6049c4], 100
 mov dword ptr [{box+24}], 0x610000
 mov dword ptr [{box+28}], 0x61a000
 mov dword ptr [{box+36}], 0x61a004
 cmp dword ptr [{box}], 2
 je start_frames
 mov eax, 10
 call {notify}
 push 0
 push 128
 push 2
 push 0
 push 0
 push 0x40000000
 push {box+256}
 call dword ptr [{imports['CreateFileA']}]
 cmp eax, -1
 je failed
 mov esi, eax
 push 0
 push {box+80}
 push 1024
 push {base+0x27000}
 push esi
 call dword ptr [{imports['WriteFile']}]
 test eax, eax
 jz failed
 push esi
 call dword ptr [{imports['CloseHandle']}]
 mov eax, 11
 call {notify}
 start_frames:
 xor ebp, ebp
 next_frame:
 mov dword ptr [0x503c6c], ebp
 mov eax, ebp
 imul eax, eax, 0x01010101
 mov edx, 1234
 add edx, ebp
 cmp dword ptr [{box}], 2
 jne keys_ready
 mov eax, -1
 mov edx, 99
 keys_ready:
 mov dword ptr [0x61a000], edx
 mov edi, 0x611010
 mov ecx, 514
 rep stosd
 mov dword ptr [0x61a004], ebp
 cmp dword ptr [{box}], 2
 jne key_cached
 mov dword ptr [0x61a004], 99
 key_cached:
 lea eax, [ebp+10]
 cmp dword ptr [{box}], 2
 jne engine_rng1
 mov eax, 99
 engine_rng1:
 mov byte ptr [0x581158], al
 mov eax, 1
 call {notify}
 lea eax, [ebp+10]
 cmp byte ptr [0x581158], al
 jne failed
 cmp dword ptr [{box}], 2
 jne refs_checked
 cmp dword ptr [0x604004], 0xdead0000
 jne failed
 cmp dword ptr [0x604008], 0x61c000
 jne failed
 cmp dword ptr [0x6041cc], 0x61f000
 jne failed
 cmp dword ptr [0x6041d0], 0
 jne failed
 cmp dword ptr [0x604210], 0x61f004
 jne failed
 cmp dword ptr [0x604234], 0x61f008
 jne failed
 refs_checked:
 cmp dword ptr [0x61a004], ebp
 jne failed
 imul eax, ebp, 0x01010101
 cmp dword ptr [0x611010], eax
 jne failed
 lea eax, [ebp+1234]
 cmp dword ptr [0x61a000], eax
 jne failed
 lea eax, [ebp+10]
 imul eax, eax, 0x01010101
 cmp dword ptr [{box}], 2
 jne mouse_ready
 mov eax, -1
 mouse_ready:
 mov edi, 0x504d70
 mov ecx, 16
 rep stosd
 lea eax, [ebp+20]
 cmp dword ptr [{box}], 2
 jne engine_rng2
 mov eax, 99
 engine_rng2:
 mov byte ptr [0x581158], al
 lea eax, [ebp+2000]
 cmp dword ptr [{box}], 2
 jne crt_rng2
 mov eax, 99
 crt_rng2:
 mov dword ptr [0x61a000], eax
 mov eax, 2
 call {notify}
 lea eax, [ebp+2000]
 cmp dword ptr [0x61a000], eax
 jne failed
 lea eax, [ebp+20]
 cmp byte ptr [0x581158], al
 jne failed
 lea eax, [ebp+10]
 imul eax, eax, 0x01010101
 cmp dword ptr [0x504d70], eax
 jne failed
 xor eax, eax
 mov edi, 0x52f210
 mov ecx, 352
 rep stosd
 mov eax, 5
 mov edx, 1
 cmp dword ptr [{box}], 2
 jne commands_ready
 mov eax, 99
 mov edx, 99
 commands_ready:
 mov dword ptr [0x52f210], eax
 mov dword ptr [0x52f214], edx
 lea eax, [ebp+30]
 cmp dword ptr [{box}], 2
 jne engine_rng3
 mov eax, 99
 engine_rng3:
 mov byte ptr [0x581158], al
 lea eax, [ebp+3000]
 cmp dword ptr [{box}], 2
 jne crt_rng3
 mov eax, 99
 crt_rng3:
 mov dword ptr [0x61a000], eax
 mov eax, 3
 call {notify}
 lea eax, [ebp+3000]
 cmp dword ptr [0x61a000], eax
 jne failed
 lea eax, [ebp+30]
 cmp byte ptr [0x581158], al
 jne failed
 mov eax, dword ptr [0x52f210]
 add dword ptr [0x604014], eax
 mov eax, dword ptr [0x52f214]
 sub dword ptr [0x6049c4], eax
 inc ebp
 cmp ebp, 4
 jne next_frame
 cmp dword ptr [0x604014], 30
 jne failed
 cmp dword ptr [0x6049c4], 96
 jne failed
 mov eax, 4
 call {notify}
 push {base+0x27c00}
 call dword ptr [{imports['GetModuleHandleA']}]
 push {base+0x27c20}
 push eax
 call dword ptr [{imports['GetProcAddress']}]
 test eax, eax
 jz failed
 push {base+0x27c80}
 push 1
 push 4096
 push {box}
 call eax
 test eax, eax
 jz failed
 push 150
 call dword ptr [{imports['Sleep']}]
 push 0
 call dword ptr [{imports['ExitProcess']}]
 failed:
 push 1
 call dword ptr [{imports['ExitProcess']}]
'''
code=bytes(ks.asm(asm,entry)[0])
if len(code)>0x1000:raise ValueError('Fixture code limit')
offset=section.PointerToRawData+0x24200;data[offset:offset+len(code)]=code
for relative,value in ((0x27c00,b'kernel32.dll\0'),(0x27c20,b'VirtualProtect\0')):
 offset=section.PointerToRawData+relative;data[offset:offset+len(value)]=value
# Strip all replay game hooks from consideration: entry executes only the fixture.
struct.pack_into('<I',data,pe.OPTIONAL_HEADER.get_field_absolute_offset('AddressOfEntryPoint'),entry-0x400000)
data[section.PointerToRawData+0x26040:section.PointerToRawData+0x26048]=b'AGRTEST1'
# Only the fixture's kernel32 calls are needed. Avoid any game DLL loading.
from pefile import DIRECTORY_ENTRY
kernel=next(d for d in pe.DIRECTORY_ENTRY_IMPORT if d.dll.lower()==b'kernel32.dll')
directory=pe.OPTIONAL_HEADER.DATA_DIRECTORY[DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']]
first=pe.get_offset_from_rva(directory.VirtualAddress)
data[first:first+20]=kernel.struct.__pack__()
data[first+20:first+40]=bytes(20)
target.write_bytes(data)
