"""Native debugger for the isolated test-game only. Records exceptions, not gameplay."""
import ctypes as c,ctypes.wintypes as w,pathlib,sys,json,struct,time
k=c.WinDLL('kernel32',use_last_error=True)
class Startup(c.Structure):
    _fields_=[('cb',w.DWORD),('reserved',w.LPWSTR),('desktop',w.LPWSTR),('title',w.LPWSTR),('x',w.DWORD),('y',w.DWORD),('xs',w.DWORD),('ys',w.DWORD),('xc',w.DWORD),('yc',w.DWORD),('fill',w.DWORD),('flags',w.DWORD),('show',w.WORD),('r2',w.WORD),('r3',c.c_void_p),('stdin',w.HANDLE),('stdout',w.HANDLE),('stderr',w.HANDLE)]
class ProcessInfo(c.Structure):_fields_=[('process',w.HANDLE),('thread',w.HANDLE),('pid',w.DWORD),('tid',w.DWORD)]
class Event(c.Structure):_fields_=[('code',w.DWORD),('pid',w.DWORD),('tid',w.DWORD),('data',c.c_ulonglong*20)]
k.CreateProcessW.argtypes=[w.LPCWSTR,w.LPWSTR,c.c_void_p,c.c_void_p,w.BOOL,w.DWORD,c.c_void_p,w.LPCWSTR,c.POINTER(Startup),c.POINTER(ProcessInfo)];k.CreateProcessW.restype=w.BOOL
k.WaitForDebugEvent.argtypes=[c.POINTER(Event),w.DWORD];k.ContinueDebugEvent.argtypes=[w.DWORD,w.DWORD,w.DWORD]
k.ReadProcessMemory.argtypes=[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)];k.OpenThread.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenThread.restype=w.HANDLE
k.Wow64GetThreadContext.argtypes=[w.HANDLE,c.c_void_p];k.CloseHandle.argtypes=[w.HANDLE]
k.TerminateProcess.argtypes=[w.HANDLE,w.UINT]
exe=pathlib.Path(sys.argv[1]).resolve()
root=pathlib.Path(__file__).resolve().parent.parent
if exe.parent != (root/'test-game').resolve():raise ValueError('Only workspace test-game is accepted')
seconds=next((int(a.split('=')[1]) for a in sys.argv[2:] if a.startswith('--seconds=')),60)
if not 1<=seconds<=600:raise ValueError('Timeout must be 1..600 seconds')
si=Startup();si.cb=c.sizeof(si);pi=ProcessInfo()
if not k.CreateProcessW(str(exe),None,None,None,False,2,None,str(exe.parent),c.byref(si),c.byref(pi)):raise c.WinError(c.get_last_error())
print('DEBUG PID',pi.pid,flush=True);records=[];started=time.monotonic();timed_out=False;snapshots=[];last_snapshot=-1
report=root/'analysis/raw/probe-exceptions.json';report.parent.mkdir(parents=True,exist_ok=True)
def read(addr,size):
    b=c.create_string_buffer(size);got=c.c_size_t()
    k.ReadProcessMemory(pi.process,c.c_void_p(addr),b,size,c.byref(got));return b.raw[:got.value]
while True:
    elapsed=time.monotonic()-started
    if int(elapsed)//5 != last_snapshot:
        last_snapshot=int(elapsed)//5
        values={}
        for label,addr in {'width':0x4f75ec,'height':0x4f75f0,'pitch':0x4f75f4,'ddraw_pitch':0x572968,'hud_x':0x4f9db0,'hud_y':0x4f9db4}.items():
            b=read(addr,4)
            if len(b)==4:values[label]=struct.unpack('<i',b)[0]
        snapshots.append({'elapsed_seconds':round(elapsed,2),'values':values})
    if elapsed>=seconds and not timed_out:
        timed_out=True;k.TerminateProcess(pi.process,0xdead0001)
    e=Event()
    if not k.WaitForDebugEvent(c.byref(e),1000):continue
    raw=bytes(e.data);status=0x10002
    if e.code==1:
        code=struct.unpack_from('<I',raw,0)[0];address=struct.unpack_from('<Q',raw,16)[0]
        if code not in (0x80000003,0x4000001f,0x40010006,0x4001000a):
            thread=k.OpenThread(0x1fffff,False,e.tid);ctx=c.create_string_buffer(716);struct.pack_into('<I',ctx,0,0x10007)
            regs={}
            if k.Wow64GetThreadContext(thread,ctx):regs={name:hex(struct.unpack_from('<I',ctx.raw,off)[0]) for name,off in [('edi',156),('esi',160),('ebx',164),('edx',168),('ecx',172),('eax',176),('ebp',180),('eip',184),('esp',196)]}
            k.CloseHandle(thread);esp=int(regs.get('esp','0'),16);stack=read(esp,160)
            record={'exception':hex(code),'address':hex(address),'first_chance':struct.unpack_from('<I',raw,152)[0],'registers':regs,'stack':[hex(v[0]) for v in struct.iter_unpack('<I',stack[:len(stack)//4*4])],'code_bytes':read(address-16,48).hex()}
            records.append(record);report.write_text(json.dumps(records,indent=2));print(json.dumps(record),flush=True);status=0x80010001
    elif e.code==6:
        handle,base=struct.unpack_from('<QQ',raw,0)
        if handle:k.CloseHandle(handle)
    elif e.code==5:
        exit_code=struct.unpack_from('<I',raw,0)[0]
        print('EXIT',hex(exit_code),'timed_out='+str(timed_out),flush=True);k.ContinueDebugEvent(e.pid,e.tid,status);break
    k.ContinueDebugEvent(e.pid,e.tid,status)
report.write_text(json.dumps(records,indent=2))
(report.parent/'probe-runtime.json').write_text(json.dumps({'pid':pi.pid,'seconds':round(time.monotonic()-started,2),'test_terminated_at_deadline':timed_out,'exit_code':hex(exit_code),'exceptions':records,'snapshots':snapshots},indent=2))
k.CloseHandle(pi.thread);k.CloseHandle(pi.process)
