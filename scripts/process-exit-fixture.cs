using System;using System.Diagnostics;using System.IO;using System.Reflection;using System.Runtime.InteropServices;using System.Text;using Amagadon;
class ProcessExitFixture {
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Startup {public int cb;public string reserved,desktop,title;public int x,y,cx,cy,xchars,ychars,fill,flags;public short show,reserved2;public IntPtr bytes,input,output,error;}
 [StructLayout(LayoutKind.Sequential)] struct Info {public IntPtr process,thread;public uint pid,tid;}
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool CreateProcess(string app,StringBuilder command,IntPtr a,IntPtr b,bool inherit,uint flags,IntPtr env,string dir,ref Startup startup,out Info info);
 [DllImport("kernel32.dll")]static extern uint ResumeThread(IntPtr thread);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
 [DllImport("kernel32.dll")]static extern bool TerminateProcess(IntPtr handle,uint code);
 static int Main(string[] args){if(args.Length==2&&args[0]=="child")return Int32.Parse(args[1]);try{
  foreach(bool fixedPath in new[]{false,true})foreach(int expected in new[]{0,42})for(int i=0;i<5;i++){
   var startup=new Startup{cb=Marshal.SizeOf(typeof(Startup))};Info info;string exe=Assembly.GetExecutingAssembly().Location;
   if(!CreateProcess(exe,new StringBuilder("\""+exe+"\" child "+expected),IntPtr.Zero,IntPtr.Zero,false,0x08000004,IntPtr.Zero,Path.GetDirectoryName(exe),ref startup,out info))throw new Exception("CreateProcess failed");
   Process child=null;
   try {
    child=fixedPath?(Process)typeof(NetworkGuard).GetMethod("TrackProcess",BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,new object[]{(int)info.pid}):Process.GetProcessById((int)info.pid);
    ResumeThread(info.thread);CloseHandle(info.thread);info.thread=IntPtr.Zero;CloseHandle(info.process);info.process=IntPtr.Zero;
    if(!child.WaitForExit(10000))throw new Exception("Timeout");
    bool failed=false;try {int code=child.ExitCode;if(code!=expected)throw new Exception("Wrong exit code "+code);}catch(InvalidOperationException){failed=true;}
    if(failed==fixedPath)throw new Exception("Unexpected result fixed="+fixedPath+" failed="+failed);
   }finally{if(info.process!=IntPtr.Zero){TerminateProcess(info.process,1);CloseHandle(info.process);}if(info.thread!=IntPtr.Zero)CloseHandle(info.thread);if(child!=null)child.Dispose();}
  }
  File.WriteAllText(args[0],"PASS: old PID-only exit-code error reproduced; retained handles preserve normal/abnormal exit code, 20 native child launches");return 0;
 }catch(Exception ex){File.WriteAllText(args[0]+".error",ex.ToString());return 1;}}
}
