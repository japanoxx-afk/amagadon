using System;using System.Text;using System.Linq;using System.Runtime.InteropServices;using System.Collections.Generic;using System.IO;using System.Reflection;using System.Diagnostics;using Amagadon;
// Development-only adapter. Never ship with the launcher or use on an installed game.
// This changes only the native singleton name in addition to normal launcher hooks.
class NativeMultiplayerSession {
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Startup {public int cb;public string reserved,desktop,title;public int x,y,cx,cy,xchars,ychars,fill,flags;public short show,reserved2;public IntPtr bytes,input,output,error;}
 [StructLayout(LayoutKind.Sequential)] struct Info {public IntPtr process,thread;public uint pid,tid;}
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(string app,StringBuilder cmd,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref Startup startup,out Info info);
 [DllImport("kernel32.dll")] static extern uint ResumeThread(IntPtr thread);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr h,uint code);
 [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h,IntPtr a,byte[] b,int size,out IntPtr read);
 static Process StartIsolated(string exe,string folder) {
  var values=new SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase);
  foreach(System.Collections.DictionaryEntry item in Diagnostics.StartInfo(exe,folder).EnvironmentVariables)values[(string)item.Key]=(string)item.Value;
  IntPtr env=Marshal.StringToHGlobalUni(String.Join("\0",values.Select(v=>v.Key+"="+v.Value))+"\0\0");var startup=new Startup{cb=Marshal.SizeOf(typeof(Startup))};Info info;
  try {if(!CreateProcess(exe,new StringBuilder("\""+exe+"\""),IntPtr.Zero,IntPtr.Zero,false,0x404,env,folder,ref startup,out info))throw new IOException("CreateProcess "+Marshal.GetLastWin32Error());}finally{Marshal.FreeHGlobal(env);}
  try {
   NetworkGuard.Apply(info.process,exe);
   byte[] expected=Encoding.ASCII.GetBytes("ArmageddonIsRunning\0"),actual=new byte[expected.Length];IntPtr count;
   if(!ReadProcessMemory(info.process,new IntPtr(0x4d4f4c),actual,actual.Length,out count)||count.ToInt32()!=actual.Length||!expected.SequenceEqual(actual))throw new IOException("Single-instance mutex signature differs");
   byte[] name=Encoding.ASCII.GetBytes(("Lab"+Guid.NewGuid().ToString("N")).Substring(0,expected.Length-1)+"\0");
   typeof(NetworkGuard).GetMethod("Write",BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,new object[]{info.process,0x4d4f4c,name});
   var p=Process.GetProcessById((int)info.pid);IntPtr handle=p.Handle;
   if(ResumeThread(info.thread)==UInt32.MaxValue)throw new IOException("Resume failed");return p;
  }catch{TerminateProcess(info.process,1);throw;}finally{CloseHandle(info.thread);CloseHandle(info.process);}
 }
 [STAThread] static int Main(string[] args) {try {
  Diagnostics.SetProcessDPIAware();
  if(args.Length!=3)throw new ArgumentException("game-folder session-folder internal-width");
  string game=Path.GetFullPath(args[0]),session=Path.GetFullPath(args[1]);
  if(args[2]!="800" && args[2]!="1024")throw new ArgumentException("internal-width must be 800 or 1024");
  string marker=Path.Combine(game,"native-lab-copy.txt");
  if(!File.Exists(marker)||File.ReadAllText(marker).Trim()!="isolated native multiplayer test copy")throw new IOException("Refusing to use an unmarked game installation");
  if(Directory.Exists(session))throw new IOException("Session already exists; use a new session directory");
  Directory.CreateDirectory(session);string home=Path.Combine(session,"home");
  typeof(Core).GetField("Home").SetValue(null,home);
  typeof(Diagnostics).GetField("Home").SetValue(null,Path.Combine(home,"Diagnostics"));
  string evidence=Path.Combine(Diagnostics.Home,"match");Directory.CreateDirectory(evidence);
  var settings=new Settings {GamePath=game,NativeHD=args[2]=="1024",Fullscreen=false,ConfineMouse=true,MouseCompatibility=false,Renderer="gdi",AutoReplay=false,DiagnosticLogging=true};
  Core.Validate(game);Core.EnsureIdle(game);NetworkGuard.TraceLogging=true;
  string file=settings.NativeHD?NativePatch.Prepare(game,Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"compat","hd-preview.json")):Path.Combine(game,"Armageddon.exe");
  Core.Apply(game,settings,Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"compat","ddraw.dll"));
  using(var p=StartIsolated(file,game)) {
   File.WriteAllText(Path.Combine(session,"process.json"),Core.Json.Serialize(new {pid=p.Id,startUtcTicks=p.StartTime.ToUniversalTime().Ticks,game=game,exe=file,hash=Core.Hash(file),launcher=Core.Hash(typeof(Core).Assembly.Location)}));
   Diagnostics.Write(evidence,"start",new {pid=p.Id,version=Core.Version,settings=settings,executable=file,sha256=Core.Hash(file),scope="actual native multiplayer process, isolated development copy"});
   int result=Diagnostics.Watch(p.Id,p.StartTime.ToUniversalTime().Ticks,evidence);
   File.WriteAllText(Path.Combine(session,"monitor-result.txt"),result.ToString());return result;
  }
 }catch(Exception ex){Console.Error.WriteLine(ex);return 1;}}
}
