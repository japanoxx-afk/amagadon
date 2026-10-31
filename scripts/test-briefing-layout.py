import sys,subprocess,os,tempfile,struct
from pathlib import Path
sys.path.insert(0,'.tools')
from unicorn import *
from unicorn.x86_const import *
from keystone import *
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'Dump.cs').write_text('using System;using System.IO;using System.Reflection;using System.Collections.Generic;class T{static void Main(string[] a){var t=Assembly.LoadFrom(a[0]).GetType("Amagadon.InGameLayout");foreach(var e in (Dictionary<int,byte[]>)t.GetMethod("Build").Invoke(null,new object[]{0x20000000}))File.WriteAllBytes(Path.Combine(a[1],e.Key.ToString("x8")+".bin"),e.Value);}}')
 subprocess.run([os.environ['WINDIR']+r'\Microsoft.NET\Framework\v4.0.30319\csc.exe','/nologo','/platform:x86','/out:'+str(p/'Dump.exe'),str(p/'Dump.cs')],check=True)
 subprocess.run([str(p/'Dump.exe'),str(Path('dist/0.3.39-final/AmagadonLauncher.exe').resolve()),d],check=True)
 payload=(p/'20000000.bin').read_bytes()
u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x20000000,4096);u.mem_write(0x20000000,payload);u.mem_map(0x400000,0x200000);u.mem_map(0x3000000,0x10000)
k=Ks(KS_ARCH_X86,KS_MODE_32);u.mem_write(0x49eb80,bytes(k.asm('ret 28')[0]));obj=0x3001000;stack=0x300f000;end=0x400000
u.mem_write(obj+16,struct.pack('<2i',0,0));u.mem_write(stack,struct.pack('<8I',end,*range(1,8)));u.reg_write(UC_X86_REG_ECX,obj);u.reg_write(UC_X86_REG_ESP,stack)
def observe(uc,a,s,d):
 assert struct.unpack('<2i',uc.mem_read(obj+16,8))==(112,84)
 sp=uc.reg_read(UC_X86_REG_ESP);assert struct.unpack('<7I',uc.mem_read(sp+4,28))==tuple(range(1,8))
u.hook_add(UC_HOOK_CODE,observe,begin=0x49eb80,end=0x49eb80);u.emu_start(0x20000500,end,count=1000)
assert struct.unpack('<2i',u.mem_read(obj+16,8))==(0,0);assert u.reg_read(UC_X86_REG_ESP)==stack+32
u.mem_write(stack,struct.pack('<5I',end,196,349,25,0xffffff));u.reg_write(UC_X86_REG_ESP,stack);u.emu_start(0x20000100,0x4710f0,count=100)
assert struct.unpack('<2I',u.mem_read(stack+4,8))==(308,433)
print('PASS compiled briefing: container and text +112,+84; seven arguments, stack and stored origin preserved')

