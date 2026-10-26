"""Exercise the emitted ACE presenter, including COM/GDI failure cleanup."""
import sys, struct, pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
p=pefile.PE(sys.argv[1]);image=p.get_memory_mapped_image();base=0x400000
def run(fail=None, origin=(221,113), size=(800,600), cached=False):
    u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(base,0x300000);u.mem_write(base,image)
    u.mem_map(0x800000,0x20000);u.mem_map(0x900000,0x10000)
    def put(a,v):u.mem_write(a,struct.pack('<I',v & 0xffffffff))
    def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
    obj,surface,clip=0x810000,0x811000,0x812000
    put(obj+0x20,0 if fail=='surface' else surface);put(surface,0x813000)
    put(0x467e8c,0 if fail=='clip' else clip);put(clip,0x814000)
    api={'hwnd':(0x900010,2),'rect':(0x900020,2),'origin':(0x900030,2),'surface_dc':(0x900040,2),'window_dc':(0x900050,1),'module':(0x900060,1),'proc':(0x900070,2),'blit':(0x900080,9),'release_window':(0x900090,2),'release_surface':(0x9000a0,2)}
    for a,key in [(0x814010,'hwnd'),(0x44522c,'rect'),(0x445200,'origin'),(0x813044,'surface_dc'),(0x445174,'window_dc'),(0x445164,'module'),(0x445148,'proc'),(0x445170,'release_window'),(0x813068,'release_surface')]:put(a,api[key][0])
    if cached:put(0x618800,api['blit'][0])
    calls=[]
    def hook(u,a,n,data):
        for key,(target,argc) in api.items():
            if a!=target:continue
            sp=u.reg_read(UC_X86_REG_ESP);args=[get(sp+4+i*4) for i in range(argc)];calls.append((key,args))
            result=1
            if key=='hwnd':put(args[1],123);result=1 if fail==key else 0
            elif key=='rect':
                u.mem_write(args[1],struct.pack('<4i',0,0,*size));result=0 if fail==key else 1
            elif key=='origin':u.mem_write(args[1],struct.pack('<2i',*origin))
            elif key=='surface_dc':put(args[1],456);result=1 if fail==key else 0
            elif key=='window_dc':result=0 if fail==key else 789
            elif key=='module':result=0 if fail==key else 555
            elif key=='proc':result=0 if fail==key else api['blit'][0]
            elif key=='blit':assert args==[789,0,0,*size,456,origin[0]&0xffffffff,origin[1]&0xffffffff,0xcc0020],args
            u.reg_write(UC_X86_REG_EAX,result);u.reg_write(UC_X86_REG_ESP,sp+4+argc*4);u.reg_write(UC_X86_REG_EIP,get(sp));return
    u.hook_add(UC_HOOK_CODE,hook)
    sp=0x80f000;put(sp,0x900fff);u.reg_write(UC_X86_REG_ESP,sp);u.reg_write(UC_X86_REG_ECX,obj)
    preserved=[UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
    for i,r in enumerate(preserved):u.reg_write(r,0x11220000+i)
    u.emu_start(0x41fb80,0x900fff,count=1000)
    assert u.reg_read(UC_X86_REG_EIP)==0x900fff and u.reg_read(UC_X86_REG_ESP)==sp+4
    assert all(u.reg_read(r)==0x11220000+i for i,r in enumerate(preserved))
    names=[c[0] for c in calls]
    assert ('blit' in names)==(fail is None)
    assert names.count('release_surface')==(0 if fail in ['surface','clip','hwnd','rect','surface_dc'] else 1)
    assert names.count('release_window')==(0 if fail in ['surface','clip','hwnd','rect','surface_dc','window_dc'] else 1)
    if cached:assert 'module' not in names and 'proc' not in names
for fail in [None,'surface','clip','hwnd','rect','surface_dc','window_dc','module','proc']:run(fail)
run(origin=(-1700,45),size=(128,128),cached=True)
print('PASS: ACE presenter client-only copy, palette DC path, negative screen origin, cached resolution, register/stack preservation and failure cleanup')
