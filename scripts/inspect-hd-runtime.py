"""Read-only renderer/UI diagnostics; never writes to or controls the game."""
import ctypes as c, ctypes.wintypes as w, sys, json
k=c.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]; k.OpenProcess.restype=w.HANDLE
k.ReadProcessMemory.argtypes=[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
k.CloseHandle.argtypes=[w.HANDLE]
h=k.OpenProcess(0x1010,False,int(sys.argv[1]))
if not h: raise c.WinError(c.get_last_error())
def read(address,count=1):
    buf=(c.c_uint32*count)(); got=c.c_size_t()
    if not k.ReadProcessMemory(h,c.c_void_p(address),buf,c.sizeof(buf),c.byref(got)): raise c.WinError(c.get_last_error())
    return list(buf)
try:
    out={'screen':read(0x4f75ec,6),'effects':read(0x4f78c0,2),'mouse':read(0x4e89d8,2),'frame_mouse':read(0x504d70,2),'hud':read(0x4f9db0,2)}
    owner=read(0x504a10)[0]
    if owner:out['unit_world_viewport']=read(owner+0x70f8,4)
    out['videos']=[]
    for slot in range(8):
        ptr=read(0x22fc550+slot*8)[0]
        if ptr:out['videos'].append({'slot':slot,'fields':read(ptr,12)})
    for label,addr in [('resources',0x5030d4),('controls',0x50313c),('commands',0x50310c),('active_commands',0x503110)]:
        ptr=read(addr)[0]
        if ptr:
            child=read(ptr+0x13b0)[0]
            out[label]={'anchor':read(ptr+0x10,2),'child_positions':read(ptr+0x1478,16),'child_vtable':hex(read(child)[0]),'virtuals':[hex(v) for v in read(read(child)[0],10)]} if child else {'anchor':read(ptr+0x10,2)}
    print(json.dumps(out,indent=2))
finally:k.CloseHandle(h)
