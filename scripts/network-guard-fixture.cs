using System;using System.IO;using System.Linq;using System.Text;using System.Runtime.InteropServices;using System.Web.Script.Serialization;using Amagadon;
class Test {
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Startup {public int cb;public string reserved,desktop,title;public int x,y,cx,cy,xchars,ychars,fill,flags;public short show,reserved2;public IntPtr bytes,input,output,error;}
 [StructLayout(LayoutKind.Sequential)] struct Info{public IntPtr process,thread;public uint pid,tid;}
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern bool CreateProcess(string app,StringBuilder cmd,IntPtr a,IntPtr b,bool inherit,uint flags,IntPtr env,string cwd,ref Startup startup,out Info pi);
 [DllImport("kernel32.dll")]static extern bool TerminateProcess(IntPtr p,uint code);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr p);
 [DllImport("kernel32.dll")]static extern bool ReadProcessMemory(IntPtr p,IntPtr address,byte[] b,int size,out IntPtr count);
 static int Main(string[] args){try {
  File.WriteAllText(args[0],new JavaScriptSerializer().Serialize(NetworkGuard.Build(0x1000000).Select(e=>new {address=e.Key,bytes=Convert.ToBase64String(e.Value)}).ToArray()));
  foreach(string exe in args.Skip(1)) {string before=Core.Hash(exe);var s=new Startup{cb=Marshal.SizeOf(typeof(Startup))};Info p;
   if(!CreateProcess(exe,new StringBuilder("\""+exe+"\""),IntPtr.Zero,IntPtr.Zero,false,4,IntPtr.Zero,Path.GetDirectoryName(exe),ref s,out p))throw new Exception("Create suspended failed");
   try {NetworkGuard.Apply(p.process,exe);var bytes=new byte[10];IntPtr count;if(!ReadProcessMemory(p.process,new IntPtr(0x475b31),bytes,10,out count)||!bytes.SequenceEqual(NetworkGuard.Hex("85ff7406803f00909090")))throw new Exception("Patch not installed");
    if(!ReadProcessMemory(p.process,new IntPtr(0x4906f5),bytes,5,out count)||bytes[0]!=0xe9)throw new Exception("Input recovery not installed");
    using(var child=System.Diagnostics.Process.GetProcessById((int)p.pid)) {var read=typeof(Diagnostics).GetMethod("InputState",System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.NonPublic);string input=Core.Json.Serialize(read.Invoke(null,new object[]{child}));if(!input.Contains("\"acquireAttempts\":0") || !input.Contains("\"backgroundSkips\":0"))throw new Exception("Input recovery telemetry unavailable: "+input);}
   }
   finally {TerminateProcess(p.process,0);CloseHandle(p.thread);CloseHandle(p.process);}if(Core.Hash(exe)!=before)throw new Exception("Original changed");
  }return 0;
 }catch(Exception e){File.WriteAllText(args[0]+".error",e.ToString());return 1;}}
}
