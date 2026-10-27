using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace Amagadon {
    // The helper observes only a child launched by this launcher. It never
    // handles game exceptions, writes game memory or captures keyboard text.
    public static class Diagnostics {
        static readonly object gate=new object();
        public static readonly string Home=Path.Combine(Core.Home,"Diagnostics");
        [StructLayout(LayoutKind.Sequential)] struct Point {public int x,y;}
        [StructLayout(LayoutKind.Sequential)] struct Rect {public int left,top,right,bottom;}
        [DllImport("user32.dll")] static extern bool GetCursorPos(out Point p);
        [DllImport("user32.dll")] static extern bool GetClipCursor(out Rect r);
        [DllImport("user32.dll")] static extern bool ClipCursor(IntPtr r);
        [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr w,out uint pid);
        [DllImport("user32.dll")] static extern bool IsHungAppWindow(IntPtr window);
        [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr w,out Rect r);
        [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
        [DllImport("user32.dll")] static extern bool IsProcessDPIAware();
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr process,IntPtr address,byte[] buffer,int size,out IntPtr read);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool DebugActiveProcess(uint pid);
        [DllImport("kernel32.dll")] static extern bool DebugActiveProcessStop(uint pid);
        [DllImport("kernel32.dll")] static extern bool DebugSetProcessKillOnExit(bool kill);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool WaitForDebugEvent(IntPtr e,uint ms);
        [DllImport("kernel32.dll")] static extern bool ContinueDebugEvent(uint pid,uint tid,uint status);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
        [DllImport("kernel32.dll")] static extern IntPtr OpenThread(uint access,bool inherit,uint tid);
        [DllImport("kernel32.dll")] static extern bool GetThreadContext(IntPtr thread,IntPtr context);
        [DllImport("dbghelp.dll",SetLastError=true)] static extern bool MiniDumpWriteDump(IntPtr process,uint pid,IntPtr file,uint type,IntPtr exception,IntPtr streams,IntPtr callback);
        public static void Write(string folder,string kind,object data) {
            try {lock(gate) {Directory.CreateDirectory(folder);string log=Path.Combine(folder,"events.jsonl");if(File.Exists(log) && new FileInfo(log).Length>8*1024*1024) {File.Copy(log,log+".1",true);File.Delete(log);}File.AppendAllText(log,Core.Json.Serialize(new {time=DateTime.Now.ToString("o"),kind=kind,data=data})+Environment.NewLine,Encoding.UTF8);}} catch { }
        }
        public static ProcessStartInfo StartInfo(string executable,string folder) {
            var info=new ProcessStartInfo(executable){WorkingDirectory=folder,UseShellExecute=false};
            string layer=info.EnvironmentVariables["__COMPAT_LAYER"]??"";
            if(EditorPatch.IsEditor(Path.GetFileName(executable))) {
                // ACE's GDI controls and DirectDraw surfaces need one legacy DPI
                // coordinate space. Let its dedicated wrapper set awareness.
                info.EnvironmentVariables.Remove("__COMPAT_LAYER");
            } else info.EnvironmentVariables["__COMPAT_LAYER"]=layer+" HIGHDPIAWARE DISABLEDXMAXIMIZEDWINDOWEDMODE";
            return info;
        }
        static void NetworkEnvironment(string session,string folder) {
            try {
                Write(session,"network-adapters",System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces().Select(n=>new {type=n.NetworkInterfaceType.ToString(),status=n.OperationalStatus.ToString(),multicast=n.SupportsMulticast}).ToArray());
                using(var root=Microsoft.Win32.RegistryKey.OpenBaseKey(Microsoft.Win32.RegistryHive.LocalMachine,Microsoft.Win32.RegistryView.Registry32)) {
                    using(var providers=root.OpenSubKey(@"SOFTWARE\Microsoft\DirectPlay\Service Providers"))Write(session,"directplay-providers",providers==null?new string[0]:providers.GetSubKeyNames());
                    using(var cls=root.OpenSubKey(@"SOFTWARE\Classes\CLSID\{D1EB6D20-8923-11D0-9D97-00A0C90A43CB}\InprocServer32"))Write(session,"directplay-com",new {registered=cls!=null,server=cls==null?null:cls.GetValue("")});
                }
                foreach(string name in new[]{"dplayx.dll","dpnet.dll","dpwsockx.dll","ipxwrapper.dll","wsock32.dll","mswsock.dll","ws2_32.dll"}) {
                    string file=Path.Combine(folder,name);if(File.Exists(file))Write(session,"network-local-dll",new {name=name,sha256=Core.Hash(file),version=FileVersionInfo.GetVersionInfo(file).FileVersion});
                }
            }catch(Exception ex) {Write(session,"network-environment-error",ex.Message);}
        }
        static object NetworkState(Process p) {
            Func<int,int?> read=address=>{var b=new byte[4];IntPtr count;return ReadProcessMemory(p.Handle,new IntPtr(address),b,4,out count)&&count.ToInt64()==4?(int?)BitConverter.ToInt32(b,0):null;};
            int? counter=read(NetworkGuard.Counter);
            return new {directPlayObject=read(0x5140d0),ipxProvider=read(0x5140f4),tcpProvider=read(0x5140f8),initializationFailure=read(0x4d96f0),guardFailureCount=counter.HasValue?read(counter.Value):null};
        }
        public static void Begin(int pid,string executable,string folder,Settings settings) {
            if(settings==null || !settings.DiagnosticLogging)return;
            try {
                using(var p=Process.GetProcessById(pid)) {
                    string session=Path.Combine(Home,DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")+"-"+pid);Directory.CreateDirectory(session);
                    Write(session,"start",new {pid=pid,version=Core.DisplayVersion,executable=executable,sha256=Core.Hash(executable),settings=settings,os=Environment.OSVersion.ToString(),processors=Environment.ProcessorCount,systemDpiAware=IsProcessDPIAware(),screens=System.Windows.Forms.Screen.AllScreens.Select(screen=>new {bounds=screen.Bounds,primary=screen.Primary}).ToArray()});
                    try {using(var key=Microsoft.Win32.Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion"))Write(session,"windows-build",new {product=key.GetValue("ProductName"),build=key.GetValue("CurrentBuildNumber"),revision=key.GetValue("UBR"),release=key.GetValue("DisplayVersion")});}catch(Exception ex) {Write(session,"windows-build-error",ex.Message);}
                    foreach(string n in new[]{"Armageddon.exe","ACE.exe","ACE.Compat.exe","ddraw.dll","binkw32.dll","Mss32.dll","dinput.dll","dinput8.dll"}) {
                        string candidate=Path.Combine(folder,n);if(!File.Exists(candidate))continue;
                        try {var version=FileVersionInfo.GetVersionInfo(candidate);Write(session,"binary",new {name=n,sha256=Core.Hash(candidate),bytes=new FileInfo(candidate).Length,version=version.FileVersion});}catch(Exception ex) {Write(session,"binary-error",new {name=n,error=ex.Message});}
                    }
                    foreach(string n in new[]{"ddraw.ini","DDrawCompat.ini","DDrawCompat-ACE.ini","DDrawCompat-ACE.Compat.ini","option.dat"}) if(File.Exists(Path.Combine(folder,n)))File.Copy(Path.Combine(folder,n),Path.Combine(session,n));
                    NetworkEnvironment(session,folder);
                    var info=new ProcessStartInfo(System.Reflection.Assembly.GetExecutingAssembly().Location,"--watch-process "+pid+" "+p.StartTime.ToUniversalTime().Ticks+" \""+session+"\""){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden};
                    using(var helper=Process.Start(info)) { }
                    Core.Log("Diagnostic session="+session+" pid="+pid);
                }
            } catch(Exception ex) {Core.Log("Diagnostic start failed: "+ex.Message);}
        }
        public sealed class StallDetector {
            bool previous;int gx,gy,cx,cy,suspect;long movement;
            public bool Observe(bool valid,int gameX,int gameY,int cursorX,int cursorY,bool hung) {
                if(!valid) {previous=false;suspect=0;movement=0;return false;}
                bool stationary=previous && gx==gameX && gy==gameY && (gameX!=0 || gameY!=0);
                if(hung || stationary) {suspect++;if(previous)movement+=Math.Abs((long)cursorX-cx)+Math.Abs((long)cursorY-cy);}
                else {suspect=0;movement=0;}
                previous=true;gx=gameX;gy=gameY;cx=cursorX;cy=cursorY;
                return suspect>=2 && (hung || movement>=64);
            }
        }
        public static void CaptureStall(Process p,string folder) {
            // A live-process dump has no exception stream. This is evidence of a
            // suspected stall, not proof of a crash; never terminate the child.
            string dest=Path.Combine(folder,"stall-"+DateTime.Now.ToString("HHmmss-fff")+".dmp");
            using(var file=new FileStream(dest,FileMode.CreateNew,FileAccess.Write,FileShare.Read)) {
                if(!MiniDumpWriteDump(p.Handle,(uint)p.Id,file.SafeFileHandle.DangerousGetHandle(),0x1000,IntPtr.Zero,IntPtr.Zero,IntPtr.Zero))throw new IOException("Stall dump error "+Marshal.GetLastWin32Error());
            }
            Write(folder,"suspected-stall-dump",Path.GetFileName(dest));
            try {Write(folder,"loaded-modules",p.Modules.Cast<ProcessModule>().Select(m=>new {name=m.ModuleName,path=m.FileName,address=m.BaseAddress.ToInt64(),bytes=m.ModuleMemorySize}).ToArray());}catch(Exception ex) {Write(folder,"module-error",ex.Message);}
        }
        static void Snapshot(Process p,string folder,bool recover,bool engineMouse,StallDetector detector,ref bool captured) {
            try {
                p.Refresh();Point cursor;Rect clip,client;uint foreground;GetWindowThreadProcessId(GetForegroundWindow(),out foreground);
                bool haveCursor=GetCursorPos(out cursor),haveClip=GetClipCursor(out clip);GetClientRect(p.MainWindowHandle,out client);
                bool degenerate=haveClip && (clip.right-clip.left<=1 || clip.bottom-clip.top<=1);
                // Repair only a collapsed clip owned by our foreground game.
                // Never constrain the cursor or alter another application's clip.
                if(recover && foreground==(uint)p.Id && degenerate)Write(folder,"mouse-clip-recovery",new {success=ClipCursor(IntPtr.Zero),previous=clip});
                object gameInput=null;int gx=0,gy=0;
                if(engineMouse) {byte[] bytes=new byte[8];IntPtr read;if(ReadProcessMemory(p.Handle,new IntPtr(0x504d70),bytes,8,out read) && read.ToInt64()==8) {gx=BitConverter.ToInt32(bytes,0);gy=BitConverter.ToInt32(bytes,4);gameInput=new {x=gx,y=gy};}}
                bool hung=IsHungAppWindow(p.MainWindowHandle);
                if(engineMouse)Write(folder,"network-state",NetworkState(p));
                Write(folder,"sample",new {gameInput=gameInput,foreground=foreground==(uint)p.Id,window=p.MainWindowHandle.ToInt64(),hungWindow=hung,cursorAvailable=haveCursor,cursor=cursor,clipAvailable=haveClip,clip=clip,client=client,workingSet=p.WorkingSet64,privateBytes=p.PrivateMemorySize64,handles=p.HandleCount,threads=p.Threads.Count,cpuMs=p.TotalProcessorTime.TotalMilliseconds});
                bool suspected=detector.Observe(engineMouse && gameInput!=null && haveCursor && foreground==(uint)p.Id,gx,gy,cursor.x,cursor.y,hung);
                if(suspected && !captured) {
                    captured=true;Write(folder,"suspected-input-stall",new {hungWindow=hung,gameInput=gameInput,note="Two consecutive foreground samples: hung window or unchanged engine mouse despite OS cursor movement. May include menus/pause; not a confirmed crash."});
                    try {CaptureStall(p,folder);}catch(Exception ex) {Write(folder,"stall-dump-error",ex.Message);}
                }
            } catch(Exception ex) {Write(folder,"sample-error",ex.Message);}
        }
        static void Dump(Process p,uint tid,IntPtr debugEvent,string folder) {
            IntPtr context=Marshal.AllocHGlobal(716),record=Marshal.AllocHGlobal(80),pointers=Marshal.AllocHGlobal(8),info=Marshal.AllocHGlobal(12);
            IntPtr thread=OpenThread(0x48,false,tid);
            try {
                byte[] empty=new byte[716];Marshal.Copy(empty,0,context,empty.Length);Marshal.WriteInt32(context,0x1003f);
                if(thread==IntPtr.Zero || !GetThreadContext(thread,context))throw new IOException("GetThreadContext failed");
                byte[] bytes=new byte[80];Marshal.Copy(IntPtr.Add(debugEvent,12),bytes,0,80);Marshal.Copy(bytes,0,record,80);
                Marshal.WriteIntPtr(pointers,record);Marshal.WriteIntPtr(pointers,4,context);
                Marshal.WriteInt32(info,unchecked((int)tid));Marshal.WriteIntPtr(info,4,pointers);Marshal.WriteInt32(info,8,0);
                string dest=Path.Combine(folder,"crash-"+DateTime.Now.ToString("HHmmss-fff")+".dmp");
                using(var file=new FileStream(dest,FileMode.CreateNew,FileAccess.Write,FileShare.Read)) {
                    if(!MiniDumpWriteDump(p.Handle,(uint)p.Id,file.SafeFileHandle.DangerousGetHandle(),0x1000,info,IntPtr.Zero,IntPtr.Zero))throw new IOException("MiniDumpWriteDump error "+Marshal.GetLastWin32Error());
                }
                Write(folder,"crash-dump",Path.GetFileName(dest));
            } finally {if(thread!=IntPtr.Zero)CloseHandle(thread);Marshal.FreeHGlobal(info);Marshal.FreeHGlobal(pointers);Marshal.FreeHGlobal(record);Marshal.FreeHGlobal(context);}
        }
        public static int Watch(int pid,long ticks,string folder) {
            string root=Path.GetFullPath(Home)+Path.DirectorySeparatorChar;
            if(!Path.GetFullPath(folder).StartsWith(root,StringComparison.OrdinalIgnoreCase))return 2;
            bool attached=false;IntPtr buffer=Marshal.AllocHGlobal(96);
            try {using(var p=Process.GetProcessById(pid)) {
                if(p.StartTime.ToUniversalTime().Ticks!=ticks)return 3;
                IntPtr retainedHandle=p.Handle;
                string binaryFolder=Path.GetDirectoryName(p.MainModule.FileName);
                string name=Path.GetFileName(p.MainModule.FileName);
                if(!name.StartsWith("Armageddon",StringComparison.OrdinalIgnoreCase) && !EditorPatch.IsEditor(name) && !name.Equals("Amagadon.DiagnosticFixture.exe",StringComparison.OrdinalIgnoreCase))return 4;
                string hash=Core.Hash(p.MainModule.FileName);
                bool engineMouse=name.StartsWith("Armageddon",StringComparison.OrdinalIgnoreCase) && (hash==NativePatch.InputHash || NativePatch.IsPrevious(hash) || hash==NativePatch.Load(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"compat","hd-preview.json")).OutputHash);
                attached=DebugActiveProcess((uint)pid);
                if(attached && !DebugSetProcessKillOnExit(false)) {DebugActiveProcessStop((uint)pid);attached=false;}
                Write(folder,"crash-monitor",new {attached=attached,error=attached?0:Marshal.GetLastWin32Error()});
                File.WriteAllText(Path.Combine(folder,"ready.txt"),attached?"attached":"telemetry-only");
                bool initialBreak=true,captured=false;var detector=new StallDetector();int exceptions=0;var sampleClock=Stopwatch.StartNew();long lastSample=-5000;
                while(true) {
                    if(sampleClock.ElapsedMilliseconds-lastSample>=5000) {lastSample=sampleClock.ElapsedMilliseconds;Snapshot(p,folder,!EditorPatch.IsEditor(name),engineMouse,detector,ref captured);}
                    if(!attached) {if(p.HasExited)break;Thread.Sleep(1000);continue;}
                    if(!WaitForDebugEvent(buffer,1000)) {if(p.HasExited)break;continue;}
                    uint kind=unchecked((uint)Marshal.ReadInt32(buffer)),tid=unchecked((uint)Marshal.ReadInt32(buffer,8)),status=0x10002;
                    bool exited=false;
                    try {
                        if(kind==1) {
                            uint code=unchecked((uint)Marshal.ReadInt32(buffer,12));bool first=Marshal.ReadInt32(buffer,92)!=0;
                            bool bootstrap=initialBreak && first && code==0x80000003;if(bootstrap)initialBreak=false;
                            status=bootstrap?0x10002U:0x80010001U;
                            if(!bootstrap && (exceptions++<100 || !first))Write(folder,"exception",new {code="0x"+code.ToString("X8"),address="0x"+unchecked((uint)Marshal.ReadInt32(buffer,24)).ToString("X8"),thread=tid,firstChance=first});
                            if(!first) {if(engineMouse)Write(folder,"network-at-crash",NetworkState(p));try {Dump(p,tid,buffer,folder);}catch(Exception ex) {Write(folder,"dump-error",ex.Message);}}
                        } else if(kind==3 || kind==6) {IntPtr f=Marshal.ReadIntPtr(buffer,12);if(f!=IntPtr.Zero && f!=new IntPtr(-1))CloseHandle(f);}
                        else if(kind==5) {Write(folder,"exit",new {code="0x"+unchecked((uint)Marshal.ReadInt32(buffer,12)).ToString("X8")});exited=true;}
                    } finally {if(!ContinueDebugEvent((uint)pid,tid,status))Write(folder,"continue-error",Marshal.GetLastWin32Error());}
                    if(exited)break;
                }
                p.WaitForExit();
                try {string logName="DDrawCompat-"+Path.GetFileNameWithoutExtension(name)+".log";string log=Path.Combine(binaryFolder,logName);if(EditorPatch.IsEditor(name) && File.Exists(log) && new FileInfo(log).Length<=8*1024*1024)File.Copy(log,Path.Combine(folder,logName),true);}catch(Exception ex) {Write(folder,"editor-log-copy-error",ex.Message);}
                foreach(string logName in new[]{"ipxwrapper.log","dplayx.log","directplay.log"})try {string file=Path.Combine(binaryFolder,logName);if(File.Exists(file)&&new FileInfo(file).Length<=8*1024*1024)File.Copy(file,Path.Combine(folder,logName),true);}catch(Exception ex){Write(folder,"network-log-error",ex.Message);}
                Write(folder,"process-end",new {exit="0x"+p.ExitCode.ToString("X8")});
            }return 0;}catch(Exception ex) {Write(folder,"monitor-error",ex.ToString());return 1;}
            finally {if(attached)DebugActiveProcessStop((uint)pid);Marshal.FreeHGlobal(buffer);}
        }
        public static string Report(string game,string destination) {
            string temp=destination+"."+Guid.NewGuid().ToString("N")+".partial";var index=new List<object>();long total=0;
            try {using(var zip=ZipFile.Open(temp,ZipArchiveMode.Create)) {
                var files=new List<string>();
                foreach(string name in new[]{"launcher.log","launcher.log.1","settings.json"}) {string f=Path.Combine(Core.Home,name);if(File.Exists(f))files.Add(f);}
                string updates=Path.Combine(Core.Home,"updates");if(Directory.Exists(updates))files.AddRange(Directory.GetFiles(updates,"update-result.log",SearchOption.AllDirectories));
                foreach(string directory in new[]{Home,Path.Combine(Core.Home,"NetworkSetup"),Path.Combine(Core.Home,"ReplayDiagnostics"),Path.Combine(Core.Home,"CrashDumps")})if(Directory.Exists(directory))files.AddRange(Directory.GetFiles(directory,"*",SearchOption.AllDirectories).Where(f=>new[]{".jsonl",".log",".json",".txt",".dmp",".ini",".dat",".1"}.Contains(Path.GetExtension(f).ToLowerInvariant())));
                foreach(string file in files.OrderByDescending(f=>File.GetLastWriteTimeUtc(f))) {
                    string relative=file.Substring(Core.Home.Length+1).Replace('\\','/');
                    try {
                        if((File.GetAttributes(file)&FileAttributes.ReparsePoint)!=0) {index.Add(new {file=relative,status="skipped-link"});continue;}
                        using(var input=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete)) {
                            long length=input.Length;if(length>64L*1024*1024 || total+length>512L*1024*1024) {index.Add(new {file=relative,status="skipped-size-limit",bytes=length});continue;}
                            var entry=zip.CreateEntry(relative,CompressionLevel.Optimal);
                            using(var output=entry.Open()) {byte[] buffer=new byte[65536];long left=length;while(left>0) {int n=input.Read(buffer,0,(int)Math.Min(left,buffer.Length));if(n==0)break;output.Write(buffer,0,n);left-=n;}if(left!=0)throw new IOException("File changed during report");}
                            total+=length;index.Add(new {file=relative,status="included",bytes=length});
                        }
                    }catch(Exception ex) {index.Add(new {file=relative,status="failed",error=ex.Message});}
                }
                foreach(string n in new[]{"ddraw.ini","DDrawCompat.ini","DDrawCompat-ACE.ini","DDrawCompat-ACE.Compat.ini","DDrawCompat-ACE.log","DDrawCompat-ACE.Compat.log","cnc-ddraw.log","ddraw.log","ipxwrapper.log","dplayx.log","directplay.log",".amagadon-editor.json"}) {
                    string f=Path.Combine(game??"",n);if(String.IsNullOrWhiteSpace(game) || !File.Exists(f))continue;
                    try {if(new FileInfo(f).Length<=8*1024*1024) {using(var input=new FileStream(f,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete))using(var output=zip.CreateEntry("game/"+n).Open())input.CopyTo(output);}}catch(Exception ex) {index.Add(new {file=n,status="failed",error=ex.Message});}
                }
                using(var writer=new StreamWriter(zip.CreateEntry("report.json").Open()))writer.Write(Core.Json.Serialize(new {version=Core.DisplayVersion,created=DateTime.Now.ToString("o"),os=Environment.OSVersion.ToString(),files=index,notes="Local diagnostic report. Includes local paths and crash thread memory; no automatic upload. Size limits: 64 MiB/file, 512 MiB total. No game data/replays included."}));
            }File.Copy(temp,destination,true);return destination;}finally {if(File.Exists(temp))File.Delete(temp);}
        }
    }
}
