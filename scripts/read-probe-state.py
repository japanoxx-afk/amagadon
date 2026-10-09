import ctypes as c,ctypes.wintypes as w,sys,json,pathlib
k=c.WinDLL('kernel32',use_last_error=True);k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE;k.ReadProcessMemory.argtypes=[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)];k.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)];k.CloseHandle.argtypes=[w.HANDLE]
h=k.OpenProcess(0x1010,False,int(sys.argv[1]));name=c.create_unicode_buffer(32768);length=w.DWORD(32768)
if not h or not k.QueryFullProcessImageNameW(h,0,name,c.byref(length)):raise c.WinError(c.get_last_error())
if pathlib.Path(name.value).parent.name!='test-game':raise ValueError('Only isolated test-game is accepted')
values={}
for label,addr in {'software_width':0x4f75ec,'software_height':0x4f75f0,'software_pitch':0x4f75f4,'sprite_bottom_clip':0x4f7600,'directdraw_pitch':0x572968,'directdraw_height':0x572964,'camera_tile_x':0x5812e8,'camera_tile_y':0x5812ec,'cursor_x':0x4e89d8,'cursor_y':0x4e89dc,'hud_x':0x4f9db0,'hud_y':0x4f9db4}.items():
    v=c.c_int();got=c.c_size_t()
    if k.ReadProcessMemory(h,c.c_void_p(addr),c.byref(v),4,c.byref(got)):values[label]=v.value
k.CloseHandle(h);print(json.dumps(values,indent=2));pathlib.Path('analysis/raw/runtime-state.json').write_text(json.dumps(values,indent=2))
