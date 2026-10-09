import sys, pathlib, json, hashlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / '.tools'))
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM

source=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
pe=pefile.PE(str(source));base=pe.OPTIONAL_HEADER.ImageBase
imports={i.address:i.name.decode('ascii') if i.name else '#'+str(i.ordinal) for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports}
md=Cs(CS_ARCH_X86,CS_MODE_32);md.detail=True;md.skipdata=True
instructions=[]
for s in pe.sections:
    if s.Characteristics&0x20000000:
        instructions.extend(md.disasm(s.get_data(),base+s.VirtualAddress))
lines=[f'{i.address:08x}: {i.bytes.hex():24s} {i.mnemonic:8s} {i.op_str}' for i in instructions]
(out/'disassembly.txt').write_text('\n'.join(lines),encoding='utf8')
constants=[];calls=[]
for idx,i in enumerate(instructions):
    if i.id==0:continue
    for op in i.operands:
        if op.type==X86_OP_IMM and op.imm in (800,600,799,599,400,300,1600,480000,960000,640,480,16):
            constants.append({'address':hex(i.address),'value':op.imm,'instruction':lines[idx],'context':lines[max(0,idx-4):idx+5]})
        if op.type==X86_OP_MEM and op.mem.disp in imports:
            calls.append({'address':hex(i.address),'import':imports[op.mem.disp],'context':lines[max(0,idx-8):idx+5]})
(out/'constants.json').write_text(json.dumps(constants,indent=2),encoding='utf8')
(out/'imports.json').write_text(json.dumps(calls,indent=2),encoding='utf8')
(out/'metadata.json').write_text(json.dumps({'file':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'image_base':hex(base),'entry':hex(base+pe.OPTIONAL_HEADER.AddressOfEntryPoint),'sections':[{'name':s.Name.rstrip(b'\0').decode(),'va':hex(base+s.VirtualAddress),'virtual_size':s.Misc_VirtualSize,'raw_size':s.SizeOfRawData} for s in pe.sections],'imports':{hex(k):v for k,v in imports.items()},'constants_count':len(constants)},indent=2),encoding='utf8')
print(json.dumps({'instructions':len(instructions),'constants':len(constants),'imports':len(imports)}))
