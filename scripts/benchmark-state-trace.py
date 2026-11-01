"""Native x86 benchmark of the identical grid hash assembly (not emulator timing)."""
import importlib.util,os,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'.tools'))
from keystone import Ks,KS_ARCH_X86,KS_MODE_32
spec=importlib.util.spec_from_file_location('state',Path(__file__).with_name('build-state-trace.py'))
state=importlib.util.module_from_spec(spec);spec.loader.exec_module(state)
source=state.assembly();core=source[source.index('movzx eax,word ptr [esi+0xe6]'):]
# cdecl args after pushfd + pushad: grid at ESP+40, result at ESP+44.
code=bytes(Ks(KS_ARCH_X86,KS_MODE_32).asm('pushfd\npushad\nmov esi,[esp+40]\nmov edi,[esp+44]\n'+core)[0])
fixture=r'''
using System;using System.IO;using System.Diagnostics;using System.Runtime.InteropServices;
class Bench {
 [DllImport("kernel32")]static extern IntPtr VirtualAlloc(IntPtr a,UIntPtr n,uint t,uint p);
 [DllImport("kernel32")]static extern bool VirtualProtect(IntPtr a,UIntPtr n,uint p,out uint old);
 [DllImport("kernel32")]static extern bool VirtualFree(IntPtr a,UIntPtr n,uint t);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate void Hash(IntPtr grid,IntPtr output);
 static void Main(string[] args) {
  byte[] bytes=File.ReadAllBytes(args[0]);IntPtr code=VirtualAlloc(IntPtr.Zero,(UIntPtr)4096,0x3000,4);
  IntPtr grid=Marshal.AllocHGlobal(0x340000),output=Marshal.AllocHGlobal(512);
  try {
   Marshal.Copy(bytes,0,code,bytes.Length);uint old;if(!VirtualProtect(code,(UIntPtr)4096,0x20,out old))throw new Exception("RX failed");
   var hash=(Hash)Marshal.GetDelegateForFunctionPointer(code,typeof(Hash));
   byte[] data=new byte[0x340000];for(int i=0;i<data.Length;i++)data[i]=(byte)(i*31+i/2048);
   Marshal.Copy(data,0,grid,data.Length);
   foreach(int tiles in new[]{64,128,256}) {
    Marshal.WriteInt16(grid,0xe6,(short)tiles);Marshal.WriteInt16(grid,0xe8,(short)tiles);
    for(int i=0;i<20;i++)hash(grid,output);
    double[] times=new double[200];for(int i=0;i<times.Length;i++){long start=Stopwatch.GetTimestamp();hash(grid,output);times[i]=(Stopwatch.GetTimestamp()-start)*1000.0/Stopwatch.Frequency;}
    Array.Sort(times);Console.WriteLine("{0}x{0} tiles: {1} bytes; median={2:F4} ms p95={3:F4} ms; status={4}",tiles,tiles*tiles*32,times[100],times[190],Marshal.ReadInt32(output,20));
   }
  }finally{VirtualFree(code,UIntPtr.Zero,0x8000);Marshal.FreeHGlobal(grid);Marshal.FreeHGlobal(output);}
 }
}'''
with tempfile.TemporaryDirectory(prefix='amagadon-state-bench-') as folder:
 p=Path(folder);(p/'hash.bin').write_bytes(code);(p/'Bench.cs').write_text(fixture)
 subprocess.run([str(Path(os.environ['WINDIR'])/'Microsoft.NET/Framework/v4.0.30319/csc.exe'),'/nologo','/platform:x86','/optimize+','/out:'+str(p/'Bench.exe'),str(p/'Bench.cs')],check=True)
 subprocess.run([str(p/'Bench.exe'),str(p/'hash.bin')],check=True)
