"""Build ACE's window-scoped GDI presenter; distribute a recipe, never ACE assets.

The original 0x41fb80 presents the entire desktop-sized back buffer through a
primary-surface clipper whose HWND changes between the map/minimap/dialogs.
Modern primary-surface presentation loses sibling GDI controls. Get the current
clipper HWND and copy only its client rectangle to its own DC instead. Keep the
8-bit offscreen surfaces/palette and let GDI convert to desktop color depth.
"""
from pathlib import Path
import pefile, struct, sys, hashlib, json, gzip, base64, runpy
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
original=Path(sys.argv[1]).read_bytes()
assert hashlib.sha256(original).hexdigest()=='a1b1b0464ce5b9af1841973184adb8c9852ed78fbc922b182a1d90933877d507'
p=pefile.PE(data=original); b=bytearray(original)
align=lambda v,a:(v+a-1)//a*a
rva=align(p.OPTIONAL_HEADER.SizeOfImage,0x1000); va=0x400000+rva
raw=align(len(b),0x1000); b.extend(bytes(raw-len(b)+0x3000))
header=p.sections[-1].get_file_offset()+40
b[header:header+40]=struct.pack('<8sIIIIIIHHI',b'.acefix',0x3000,rva,0x3000,raw,0,0,0,0,0xe0000060)
struct.pack_into('<H',b,p.FILE_HEADER.get_field_absolute_offset('NumberOfSections'),len(p.sections)+1)
struct.pack_into('<I',b,p.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),rva+0x3000)
code=f'''
 push ebp
 push ebx
 push esi
 push edi
 sub esp, 40
 mov esi, ecx
 mov ebx, [esi+0x20]
 test ebx, ebx
 jz done
 mov eax, [0x467e8c]
 test eax,eax
 jz done
 lea edx,[esp]
 push edx
 push eax
 mov ecx,[eax]
 call dword ptr [ecx+0x10]
 test eax,eax
 jnz done
 mov edi,[esp]
 test edi,edi
 jz done
 lea eax,[esp+8]
 push eax
 push edi
 call dword ptr [0x44522c]
 test eax,eax
 jz done
 mov dword ptr [esp+24],0
 mov dword ptr [esp+28],0
 lea eax,[esp+24]
 push eax
 push edi
 call dword ptr [0x445200]
 lea eax,[esp+4]
 push eax
 push ebx
 mov eax,[ebx]
 call dword ptr [eax+0x44]
 test eax,eax
 jnz done
 push edi
 call dword ptr [0x445174]
 mov ebp,eax
 test ebp,ebp
 jz release_surface
 mov eax,[{va+0x800}]
 test eax,eax
 jnz blit
 push {va+0x810}
 call dword ptr [0x445164]
 test eax,eax
 jz release_window
 push {va+0x820}
 push eax
 call dword ptr [0x445148]
 mov [{va+0x800}],eax
 test eax,eax
 jz release_window
 blit:
 mov ecx,esp
 push 0x00cc0020
 push dword ptr [ecx+28]
 push dword ptr [ecx+24]
 push dword ptr [ecx+4]
 push dword ptr [ecx+20]
 push dword ptr [ecx+16]
 push 0
 push 0
 push ebp
 call eax
 release_window:
 push ebp
 push edi
 call dword ptr [0x445170]
 release_surface:
 push dword ptr [esp+4]
 push ebx
 mov eax,[ebx]
 call dword ptr [eax+0x68]
 done:
 xor eax,eax
 add esp,40
 pop edi
 pop esi
 pop ebx
 pop ebp
 ret
'''
enc=bytes(Ks(KS_ARCH_X86,KS_MODE_32).asm(code,va)[0]);b[raw:raw+len(enc)]=enc
b[raw+0x810:raw+0x81b]=b'gdi32.dll\0\0'; b[raw+0x820:raw+0x827]=b'BitBlt\0'
offset=p.get_offset_from_rva(0x1fb80);b[offset:offset+6]=b'\xe9'+struct.pack('<i',va-0x41fb85)+b'\x90'
runpy.run_path(str(Path(__file__).with_name('editor-navigation.py')))['install'](b,p,raw,va)
runpy.run_path(str(Path(__file__).with_name('editor-reverse-ramps.py')))['install'](b,p,raw,va)
Path(sys.argv[2]).write_bytes(b)
edits=[];i=0
while i<len(original):
    if original[i]==b[i]:i+=1;continue
    start=i
    while i<len(original) and original[i]!=b[i]:i+=1
    edits.append(dict(Offset=start,Before=original[start:i].hex(),After=b[start:i].hex()))
recipe=dict(Version='0.3.30',InputHash=hashlib.sha256(original).hexdigest(),InputLength=len(original),OutputHash=hashlib.sha256(b).hexdigest(),OutputLength=len(b),Edits=edits,AppendGzip=base64.b64encode(gzip.compress(b[len(original):],mtime=0)).decode())
path=Path(__file__).resolve().parent.parent/'compat/editor-gdi.json'
path.write_text(json.dumps(recipe,indent=2)+'\n',encoding='utf8')
print('Recipe',hashlib.sha256(path.read_bytes()).hexdigest(),'output',recipe['OutputHash'])
