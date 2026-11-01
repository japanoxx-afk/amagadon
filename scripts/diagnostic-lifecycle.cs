using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using Amagadon;

// Real Windows debug ownership, against disposable fixture children only.
static class LifecycleChecks {
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool DebugActiveProcess(uint pid);
 [DllImport("kernel32.dll")]static extern bool DebugSetProcessKillOnExit(bool kill);
 [DllImport("kernel32.dll")]static extern bool DebugActiveProcessStop(uint pid);
 [DllImport("kernel32.dll")]static extern bool WaitForDebugEvent(IntPtr buffer,uint timeout);
 [DllImport("kernel32.dll")]static extern bool ContinueDebugEvent(uint pid,uint tid,uint status);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
 static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
 public static void Run(string executable,string temp) {
  string gate=Path.Combine(temp,"telemetry-only.gate");
  using(var child=Process.Start(new ProcessStartInfo(executable,"child \""+gate+"\" clean"){UseShellExecute=false,CreateNoWindow=true}))
  using(var ready=new ManualResetEvent(false))using(var stop=new ManualResetEvent(false)) {
   for(int i=0;i<100&&!File.Exists(gate+".started");i++)Thread.Sleep(50);
   Check(File.Exists(gate+".started"),"fixture did not initialize");
   bool attached=false;Exception failure=null;
   var owner=new Thread(()=>{
    IntPtr buffer=Marshal.AllocHGlobal(96);bool initial=true;
    try {
     attached=DebugActiveProcess((uint)child.Id);if(attached)DebugSetProcessKillOnExit(false);ready.Set();
     while(attached&&!stop.WaitOne(0)) {
      if(!WaitForDebugEvent(buffer,100)){if(child.HasExited)break;continue;}
      uint kind=(uint)Marshal.ReadInt32(buffer),tid=(uint)Marshal.ReadInt32(buffer,8),status=0x10002;
      if(kind==1){uint code=(uint)Marshal.ReadInt32(buffer,12);bool bootstrap=initial&&code==0x80000003;if(bootstrap)initial=false;status=bootstrap?0x10002U:0x80010001U;}
      if(kind==3||kind==6){IntPtr file=Marshal.ReadIntPtr(buffer,12);if(file!=IntPtr.Zero&&file!=new IntPtr(-1))CloseHandle(file);}
      ContinueDebugEvent((uint)child.Id,tid,status);if(kind==5)break;
     }
    }catch(Exception ex){failure=ex;ready.Set();}
    finally{if(attached)DebugActiveProcessStop((uint)child.Id);Marshal.FreeHGlobal(buffer);}
   });owner.IsBackground=true;owner.Start();
   try {
    Check(ready.WaitOne(5000)&&attached,"fixture primary debugger did not attach");
    Diagnostics.Begin(child.Id,executable,temp,new Settings{DiagnosticLogging=true});string session=null;
    for(int i=0;i<150;i++){session=Directory.GetDirectories(Diagnostics.Home).FirstOrDefault(d=>d.EndsWith("-"+child.Id)&&File.Exists(Path.Combine(d,"ready.txt")));if(session!=null)break;Thread.Sleep(100);}
    Check(session!=null&&File.ReadAllText(Path.Combine(session,"ready.txt"))=="telemetry-only","second debugger did not fall back");
    Thread.Sleep(1200);File.WriteAllText(gate,"");Check(child.WaitForExit(5000),"telemetry-only child did not exit");
    string log="";for(int i=0;i<100;i++){log=File.ReadAllText(Path.Combine(session,"events.jsonl"));if(log.Contains("\"process-end\""))break;Thread.Sleep(100);}
    Check(log.Contains("\"sample\"")&&log.Contains("\"process-end\""),"telemetry fallback omitted samples/exit");
   }finally{stop.Set();owner.Join(5000);if(!child.HasExited)child.Kill();}
   Check(!owner.IsAlive&&failure==null,"fixture primary debugger did not stop");
  }
  gate=Path.Combine(temp,"monitor-error.gate");
  using(var child=Process.Start(new ProcessStartInfo(executable,"child \""+gate+"\" clean"){UseShellExecute=false,CreateNoWindow=true})) {
   try {
    string folder=Path.Combine(Diagnostics.Home,"lifecycle-"+Guid.NewGuid().ToString("N")+"-"+child.Id);Directory.CreateDirectory(folder);
    // Force a telemetry-thread exception after attachment, before its main loop.
    Directory.CreateDirectory(Path.Combine(folder,"ready.txt"));
    string launcher=typeof(Diagnostics).Assembly.Location;
    using(var watcher=Process.Start(new ProcessStartInfo(launcher,"--watch-process "+child.Id+" "+child.StartTime.ToUniversalTime().Ticks+" \""+folder+"\""){UseShellExecute=false,CreateNoWindow=true})) {
     Check(watcher.WaitForExit(10000)&&watcher.ExitCode==1,"failed monitor did not terminate both threads");
    }
    Check(!child.HasExited,"monitor failure killed its child");File.WriteAllText(gate,"");Check(child.WaitForExit(5000)&&child.ExitCode==0,"child stayed frozen after monitor detach");
    Check(File.ReadAllText(Path.Combine(folder,"events.jsonl")).Contains("monitor-error"),"monitor failure not recorded");
   }finally{if(!child.HasExited)child.Kill();}
  }
 }
}
