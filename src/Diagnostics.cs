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
            Func<int,string> text=address=>{var b=new byte[128];IntPtr n;if(!ReadProcessMemory(p.Handle,new IntPtr(address),b,b.Length,out n)||n.ToInt64()!=b.Length)return null;int end=Array.IndexOf(b,(byte)0);return System.Text.Encoding.GetEncoding(949).GetString(b,0,end<0?b.Length:end);};
            int? counter=read(NetworkGuard.Counter);
            object sync=null;
            if(counter.HasValue && read(counter.Value+4)==0x53594e31) {
                int b=counter.Value;
                sync=new {fingerprintMismatches=read(b+8),missingHistory=read(b+12),lastReason=read(b+16),peerSlot=read(b+20),historyIndex=read(b+24),localFingerprint=read(b+28)&255,remoteFingerprint=read(b+32)&255,clock=read(b+36),nativeErrorCount=read(b+40),localPlayer=read(b+44),sequence=read(b+48)};
            }
            object lobbyRefresh=null;
            if((read(0x47538a)&255)==0xe9) {
                int? displacement=read(0x47538b);
                if(displacement.HasValue) {int data=unchecked(0x47538f+displacement.Value-1024+4096);lobbyRefresh=new {sent=read(data),received=read(data+4)};}
            }
            object firstComparison=null;
            if(counter.HasValue && read(counter.Value+64)==0x31435953) {
                var bytes=new byte[256];IntPtr got;
                if(ReadProcessMemory(p.Handle,new IntPtr(counter.Value+64),bytes,bytes.Length,out got)&&got.ToInt32()==bytes.Length && BitConverter.ToInt32(bytes,0)==0x31435953)
                    firstComparison=new {clock=BitConverter.ToInt32(bytes,4),reason=BitConverter.ToInt32(bytes,8),peerSlot=BitConverter.ToInt32(bytes,12),historyIndex=BitConverter.ToInt32(bytes,16),sequence=BitConverter.ToInt32(bytes,20),localFingerprint=bytes[24],remoteFingerprint=bytes[28],localPacket=Convert.ToBase64String(bytes.Skip(64).Take(64).ToArray()),peerHistoryPacket=Convert.ToBase64String(bytes.Skip(128).Take(64).ToArray())};
            }
            var lobbySlots=new List<object>();
            for(int i=0;i<8;i++)lobbySlots.Add(new {slot=i,kind=read(0x513c64+i)&255,active=read(0x513c80+i)&255,playerId=read(0x513c9c+i*60),hasName=read(0x513ca0+i*60)!=0,race=read(0x513cd3+i*60)&255});
            return new {directPlayObject=read(0x5140d0),ipxProvider=read(0x5140f4),tcpProvider=read(0x5140f8),initializationFailure=read(0x4d96f0),guardFailureCount=counter.HasValue?read(counter.Value):null,
                audioDriver=read(0x2240d44),musicState=read(0x4f8628),music=new {enabled=read(0x4eac34),volume=read(0x4f862c),stream=read(0x2240d38).GetValueOrDefault()!=0,playing=text(0x4f8240),map=text(0x504b68)},nativeTickBatch=read(0x503bc8),nativeFrameInterval=read(0x50bc64),lockstep=sync,firstNativeComparison=firstComparison,lobby=new {session=read(0x51429c),phase=read(0x513ed8),inGame=read(0x513ed4),localId=read(0x513e88),hostId=read(0x513e7c),countdown=read(0x50e753)&255,refresh=lobbyRefresh,slots=lobbySlots},
                crazyZone=new {connected=read(0x57ca38),connectionEnded=read(0x57ca3c),welcome=read(0x57ca30),loginResult=read(0x4eaaac),channelResult=read(0x4eaaa8),roomCreateResult=read(0x57ca28),roomJoinResult=read(0x57ca6c),roomId=read(0x57b93c)}};
        }
        static object InputState(Process p) {
            Func<int,int?> read=address=>{var b=new byte[4];IntPtr n;return ReadProcessMemory(p.Handle,new IntPtr(address),b,4,out n)&&n.ToInt64()==4?(int?)BitConverter.ToInt32(b,0):null;};
            int? pointer=read(InputRecovery.CounterPointer);byte[] counters=new byte[60];IntPtr count;
            object recovery=null;
            if(pointer.HasValue && pointer.Value>0 && ReadProcessMemory(p.Handle,new IntPtr(pointer.Value),counters,60,out count) && count.ToInt64()==60)
                recovery=new {reads=BitConverter.ToUInt32(counters,0),lastRead="0x"+BitConverter.ToUInt32(counters,4).ToString("X8"),acquireAttempts=BitConverter.ToUInt32(counters,8),lastAcquire="0x"+BitConverter.ToUInt32(counters,12).ToString("X8"),acquireSuccess=BitConverter.ToUInt32(counters,16),failedReads=BitConverter.ToUInt32(counters,20),activations=BitConverter.ToUInt32(counters,24),notificationTimeouts=BitConverter.ToUInt32(counters,28),backgroundSkips=BitConverter.ToUInt32(counters,36),focusResumes=BitConverter.ToUInt32(counters,40),keyboardReads=BitConverter.ToUInt32(counters,44),keyboardLastRead="0x"+BitConverter.ToUInt32(counters,48).ToString("X8"),keyboardAcquireAttempts=BitConverter.ToUInt32(counters,52),keyboardLastAcquire="0x"+BitConverter.ToUInt32(counters,56).ToString("X8")};
            return new {pausedForFocus=read(0x572b5c),mouseEnabled=read(0x5727d0),mouseDevice=read(0x5727e8),notificationEvent=read(0x5727f4),inputThread=read(0x5727f8),recovery=recovery};
        }
        static object MatchState(Process p) {
            Func<int,int,int?> read=(address,size)=>{var b=new byte[size];IntPtr n;return ReadProcessMemory(p.Handle,new IntPtr(address),b,size,out n)&&n.ToInt64()==size?(int?)(size==1?b[0]:BitConverter.ToInt32(b,0)):null;};
            var computers=new List<object>();int manager=read(0x504a10,4).GetValueOrDefault();
            if(read(0x504f48,1)==4 && read(0x504f72,1)==1 && read(0x513ed4,4)==0 && manager>0)for(int slot=1;slot<=8;slot++){
                int brain=read(0x504ea0+slot*4,4).GetValueOrDefault();computers.Add(new {slot=slot,kind=read(0x513c63+slot,1),active=read(0x513c7f+slot,1),aiEnabled=read(manager+0x240f0+slot,1),planLength=brain>0?read(brain+0x18,4):null,planStep=brain>0?read(brain+0x1c,4):null});
            }
            // Raw engine values, not inferred victory/defeat labels. No player names or chat.
            return new {skirmish=computers,mode=read(0x504f48,1),multiplayer=read(0x513ed4,4),crazyZone=read(0x513ed0,4),
                endFlag=read(0x507bf4,4),terminationWait=read(0x51a660,4),dialog=read(0x507bf8,4),result=read(0x51a668,4),lobbyCountdown=read(0x50e753,1),startPending=read(0x507b20,4),
                startedAt=read(0x51a690,4),minimumDuration=read(0x51a68c,4),
                localPlayer=read(0x4e7270,1),nativeSyncErrors=read(0x51a8e4,1),simulationClock=read(0x503c6c,4),nativeMouseX=read(0x4e89d8,4),nativeMouseY=read(0x4e89dc,4),
                displayWidth=read(0x4f75ec,4),displayHeight=read(0x4f75f0,4),frameInterval=read(0x50bc64,4)};
        }
        static object MenuState(Process p) {
            Func<int,int?> read=address=>{byte[] b=new byte[4];IntPtr n;return ReadProcessMemory(p.Handle,new IntPtr(address),b,4,out n)&&n.ToInt64()==4?(int?)BitConverter.ToInt32(b,0):null;};
            var races=new List<object>();
            for(int i=0;i<8;i++) {
                int? pointer=read(0x504f08+i*4);
                if(pointer.HasValue && pointer.Value>0)races.Add(new {slot=i,address=pointer,enabled=read(pointer.Value+0x19c),items=read(pointer.Value+0x244),selected=read(pointer.Value+0x248)});
            }
            int? dialog=read(0x507bac);int?[] bounds=null;
            if(dialog.HasValue && dialog.Value>0)bounds=Enumerable.Range(0,4).Select(i=>read(dialog.Value+16+i*4)).ToArray();
            return new {menu=read(0x4d6d78),raceControls=races,dialog=dialog,dialogBounds=bounds,nativeMouseX=read(0x4e89d8),nativeMouseY=read(0x4e89dc)};
        }
        public static void Begin(int pid,string executable,string folder,Settings settings) {
            if(settings==null || !settings.DiagnosticLogging)return;
            try {
                using(var p=Process.GetProcessById(pid)) {
                    string session=Path.Combine(Home,DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")+"-"+pid);Directory.CreateDirectory(session);
                    Write(session,"start",new {pid=pid,version=Core.DisplayVersion,executable=executable,sha256=Core.Hash(executable),settings=settings,os=Environment.OSVersion.ToString(),processors=Environment.ProcessorCount,systemDpiAware=IsProcessDPIAware(),screens=System.Windows.Forms.Screen.AllScreens.Select(screen=>new {bounds=screen.Bounds,primary=screen.Primary}).ToArray()});
                    try {using(var key=Microsoft.Win32.Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion"))Write(session,"windows-build",new {product=key.GetValue("ProductName"),build=key.GetValue("CurrentBuildNumber"),revision=key.GetValue("UBR"),release=key.GetValue("DisplayVersion")});}catch(Exception ex) {Write(session,"windows-build-error",ex.Message);}
                    foreach(string n in new[]{"Armageddon.exe","Armageddon.HED","Armageddon.MFP","ACE.exe","ACE.Compat.exe","ddraw.dll","binkw32.dll","Mss32.dll","dinput.dll","dinput8.dll"}) {
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
                if(engineMouse) {Write(folder,"network-state",NetworkState(p));Write(folder,"input-state",InputState(p));Write(folder,"match-state",MatchState(p));Write(folder,"menu-state",MenuState(p));}
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
        // Native trace slots are committed with matching sequence markers. Re-read
        // the ring to reject a slot overwritten while the helper was copying it.
        internal static int[] StableTraceOffsets(byte[] first,byte[] second) {
            const int header=4096,stride=2048,slots=1024;
            if(first==null||second==null||first.Length!=header+stride*slots||second.Length!=first.Length)return new int[0];
            if(BitConverter.ToUInt32(first,0)!=0x31525453||BitConverter.ToUInt32(second,0)!=0x31525453||BitConverter.ToUInt32(first,20)!=BitConverter.ToUInt32(second,20))return new int[0];
            uint generation=BitConverter.ToUInt32(first,20),head=BitConverter.ToUInt32(first,4);var valid=new List<int>();
            for(int i=0;i<slots;i++){int o=header+i*stride;uint seq=BitConverter.ToUInt32(first,o);if(seq!=0&&seq<=head&&head-seq<slots&&(seq&1023)==i&&seq==BitConverter.ToUInt32(first,o+76)&&seq==BitConverter.ToUInt32(second,o)&&seq==BitConverter.ToUInt32(second,o+76)&&BitConverter.ToUInt32(first,o+88)==generation)valid.Add(o);}
            return valid.OrderBy(o=>BitConverter.ToUInt32(first,o)).ToArray();
        }
        static void AtomicDiagnosticJson(string path,object value) {
            string pending=path+".partial";File.WriteAllText(pending,Core.Json.Serialize(value));if(File.Exists(path))File.Replace(pending,path,null);else File.Move(pending,path);
        }
        static uint CaptureConstructionGuard(Process p,string folder,uint previous) {
            Func<int,int,byte[]> read=(a,n)=>{var b=new byte[n];IntPtr got;if(!ReadProcessMemory(p.Handle,new IntPtr(a),b,n,out got)||got.ToInt32()!=n)throw new IOException("건설 보호 기록 읽기 실패");return b;};
            byte[] hook=read(0x48bc82,5);if(hook[0]!=0xe9)return previous;
            int runtime=unchecked(0x48bc87+BitConverter.ToInt32(hook,1)-SelectionRuntime.BeforeOffset),address=runtime+0x78000;
            byte[] header=read(address,12);uint count=BitConverter.ToUInt32(header,4);if(BitConverter.ToUInt32(header,0)!=0x31444c42 || count==previous)return previous;
            byte[] first=read(address,4352),second=read(address,4352);var rows=new List<object>();
            for(int i=0;i<32;i++){int o=256+i*128;uint seq=BitConverter.ToUInt32(first,o);if(seq==0||seq>count||count-seq>=32||(seq&31)!=i||seq!=BitConverter.ToUInt32(first,o+120)||seq!=BitConverter.ToUInt32(second,o)||seq!=BitConverter.ToUInt32(second,o+120))continue;
                rows.Add(new {sequence=seq,clock=BitConverter.ToUInt32(first,o+4),actorId=BitConverter.ToUInt32(first,o+8),actorType=BitConverter.ToUInt32(first,o+12),player=BitConverter.ToUInt32(first,o+16),targetType=BitConverter.ToUInt32(first,o+20),targetX=BitConverter.ToInt32(first,o+24),targetY=BitConverter.ToInt32(first,o+28),orderState=BitConverter.ToUInt32(first,o+32),reason=BitConverter.ToUInt32(first,o+36),generation=BitConverter.ToUInt32(first,o+40),finalPacket=Convert.ToBase64String(first.Skip(o+48).Take(64).ToArray())});
            }
            AtomicDiagnosticJson(Path.Combine(folder,"invalid-build-targets.json"),new {format=1,total=count,events=rows,notes="Rejected before footprint/cost access; native construction cancellation path used. reason 1=race range, 2=definition index range, 3=missing catalog, 4=missing definition."});
            Write(folder,"invalid-build-targets",new {total=count,records=rows.Count});return count;
        }
        static void CaptureUnitTrace(Process p,string folder,int runtime,uint generation,bool frozen,uint clock) {
            const int size=0x354000,stride=54464;int address=runtime+0x281000;
            byte[] magic=new byte[4];IntPtr got;
            if(!ReadProcessMemory(p.Handle,new IntPtr(address),magic,4,out got)||got.ToInt32()!=4||BitConverter.ToUInt32(magic,0)!=0x31544e55)return;
            byte[] raw=new byte[size];if(!ReadProcessMemory(p.Handle,new IntPtr(address),raw,size,out got)||got.ToInt32()!=size)throw new IOException("개별 유닛 이력 읽기 실패");
            var frames=new List<object>();
            for(int i=0;i<64;i++) {int o=4096+i*stride;uint seq=BitConverter.ToUInt32(raw,o),count=BitConverter.ToUInt32(raw,o+12);if(seq==0||(seq&63)!=i||count>1700||BitConverter.ToUInt32(raw,o+20)!=seq||BitConverter.ToUInt32(raw,o+8)!=generation)continue;
                byte[] again=new byte[24];if(!ReadProcessMemory(p.Handle,new IntPtr(address+o),again,24,out got)||got.ToInt32()!=24||!again.SequenceEqual(raw.Skip(o).Take(24)))continue;
                frames.Add(new {sequence=seq,clock=BitConverter.ToUInt32(raw,o+4),count=count,offset=o});
            }
            if(frames.Count==0)return;
            var index=new {format=1,generation=generation,frameStride=stride,unitStride=32,unitOffset=64,frames=frames,notes="Frame-boundary unit records; id=-1 is empty. Packed fields: id:i32,type:u16,owner:u8,active:u8,x:i32,y:i32,health:i32,target:i32,timer:i32,order:u8,raw4d0:u8,raw13b9:u8,raw10:u8."};
            string target=Path.Combine(folder,"unit-trace.dat"),pending=target+".partial";File.WriteAllBytes(pending,raw);if(File.Exists(target))File.Replace(pending,target,null);else File.Move(pending,target);AtomicDiagnosticJson(Path.Combine(folder,"unit-trace.json"),index);
            if(frozen) {string archive=Path.Combine(folder,"SyncTrace","g"+generation.ToString("D8")+"-f"+clock.ToString("D10"));Directory.CreateDirectory(archive);if(!File.Exists(Path.Combine(archive,"unit-trace.dat")))File.WriteAllBytes(Path.Combine(archive,"unit-trace.dat"),raw);if(!File.Exists(Path.Combine(archive,"unit-trace.json")))AtomicDiagnosticJson(Path.Combine(archive,"unit-trace.json"),index);}
        }
        static object CaptureSyncTrace(Process p,string folder,string reason) {
            Func<int,int,byte[]> read=(a,n)=>{var b=new byte[n];IntPtr got;if(!ReadProcessMemory(p.Handle,new IntPtr(a),b,n,out got)||got.ToInt32()!=n)throw new IOException("동기화 이력 읽기 실패");return b;};
            byte[] hook=read(0x48bc82,5);if(hook[0]!=0xe9)return new {available=false,reason="no-runtime-hook"};
            int runtime=unchecked(0x48bc87+BitConverter.ToInt32(hook,1)-SelectionRuntime.BeforeOffset),address=runtime+0x80000,size=4096+2048*1024;
            byte[] header=read(address,64),barrier=read(0x45448c,5);uint committed=BitConverter.ToUInt32(header,4),calls=BitConverter.ToUInt32(header,36);bool enabled=BitConverter.ToUInt32(header,28)==1;
            bool installed=barrier[0]==0xe9 && unchecked(0x454491+BitConverter.ToInt32(barrier,1))==runtime+SelectionRuntime.TraceBarrierOffset;
            string state=!installed?"barrier-not-installed":!enabled?"disabled":calls==0?"no-barrier-calls":committed==0?"no-multiplayer-frames":"recording";
            AtomicDiagnosticJson(Path.Combine(folder,"sync-trace-status.json"),new {savedUtc=DateTime.UtcNow,reason=reason,state=state,enabled=enabled,barrierInstalled=installed,barrierCalls=calls,committed=committed,mode=read(0x504f48,1)[0],multiplayer=BitConverter.ToUInt32(read(0x513ed4,4),0),simulationClock=BitConverter.ToUInt32(read(0x503c6c,4),0)});
            if(committed==0)return new {available=false,reason=state};
            byte[] first=read(address,size),second=read(address,size);var offsets=StableTraceOffsets(first,second);
            if(offsets.Length==0)return new {available=false,reason="no-stable-trace-slots"};
            // Keep the raw ring and a decoded index together; decoded fields omit heap pointers.
            string target=Path.Combine(folder,"sync-trace.dat"),pending=target+".partial";File.WriteAllBytes(pending,first);if(File.Exists(target))File.Replace(pending,target,null);else File.Move(pending,target);
            var frames=offsets.Select(o=>new {sequence=BitConverter.ToUInt32(first,o),clock=BitConverter.ToUInt32(first,o+4),engineRngIndex=BitConverter.ToUInt32(first,o+8),frameInterval=BitConverter.ToUInt32(first,o+12),localPlayer=BitConverter.ToUInt32(first,o+16),syncErrors=BitConverter.ToUInt32(first,o+20),unitHash=BitConverter.ToUInt32(first,o+24),unitCount=BitConverter.ToUInt32(first,o+28),playerHashes=Enumerable.Range(0,10).Select(i=>BitConverter.ToUInt32(first,o+32+i*4)).ToArray(),fpuControl=BitConverter.ToUInt16(first,o+80),crtRng=BitConverter.ToUInt32(first,o+84),orderHash=BitConverter.ToUInt32(first,o+92),playerOrderHashes=Enumerable.Range(0,8).Select(i=>BitConverter.ToUInt32(first,o+96+i*4)).ToArray(),offset=o}).ToArray();
            var index=new {format=1,reason=reason,generation=BitConverter.ToUInt32(first,20),frozen=BitConverter.ToUInt32(first,12)!=0,freezeReason=BitConverter.ToUInt32(first,12),barrierCalls=BitConverter.ToUInt32(first,36),freezeClock=BitConverter.ToUInt32(first,16),slots=1024,stride=2048,commandsOffset=128,commandsBytes=1408,hiddenStateOffset=1536,hiddenStateBytes=512,hiddenStateFormat=2,gridRowPitch=2048,stableFrames=frames,notes="Simulation command barrier samples. Compare peers by generation/clock, excluding localPlayer. CRT RNG 0xffffffff means TLS slot unavailable. Ring duration depends on simulation speed. Raw slots must pass sequence validation."};
            string json=Path.Combine(folder,"sync-trace.json"),part=json+".partial";File.WriteAllText(part,Core.Json.Serialize(index));if(File.Exists(json))File.Replace(part,json,null);else File.Move(part,json);
            if(BitConverter.ToUInt32(first,12)!=0) {
                string archive=Path.Combine(folder,"SyncTrace","g"+BitConverter.ToUInt32(first,20).ToString("D8")+"-f"+BitConverter.ToUInt32(first,16).ToString("D10"));Directory.CreateDirectory(archive);
                string raw=Path.Combine(archive,"sync-trace.dat"),metadata=Path.Combine(archive,"sync-trace.json");if(!File.Exists(raw))File.WriteAllBytes(raw,first);if(!File.Exists(metadata))AtomicDiagnosticJson(metadata,index);
            }
            CaptureUnitTrace(p,folder,runtime,BitConverter.ToUInt32(first,20),BitConverter.ToUInt32(first,12)!=0,BitConverter.ToUInt32(first,16));
            return new {available=true,reason=reason,frames=frames.Length,firstClock=frames[0].clock,lastClock=frames[frames.Length-1].clock,frozen=BitConverter.ToUInt32(first,12)!=0};
        }
        static object DivergenceState(Process p) {
            Func<int,int,byte[]> read=(a,n)=>{var b=new byte[n];IntPtr got;if(!ReadProcessMemory(p.Handle,new IntPtr(a),b,n,out got)||got.ToInt32()!=n)throw new IOException("동기화 상태 읽기 실패");return b;};
            int clock=BitConverter.ToInt32(read(0x503c6c,4),0),manager=BitConverter.ToInt32(read(0x504a10,4),0);
            int count=manager==0?0:Math.Max(0,Math.Min(1700,BitConverter.ToInt32(read(manager+4,4),0)));var units=new List<object>();
            for(int i=0;i<count;i++){int ptr=BitConverter.ToInt32(read(manager+8+i*4,4),0);if(ptr==0)continue;var b=read(ptr,0x13bc);units.Add(new {id=i,type=BitConverter.ToUInt16(b,12),owner=b[60],alive=b[0x13b8],x=BitConverter.ToInt32(b,20),y=BitConverter.ToInt32(b,24),health=BitConverter.ToInt32(b,0x9c4),orderTarget=BitConverter.ToInt32(b,0x414),orderState=b[0x464],orderTimer=BitConverter.ToInt32(b,0x478),rallyX=BitConverter.ToInt32(b,0x1398),rallyY=BitConverter.ToInt32(b,0x139c)});}
            return new {clockBefore=clock,clockAfter=BitConverter.ToInt32(read(0x503c6c,4),0),network=NetworkState(p),units=units,commands=Convert.ToBase64String(read(0x52f510,640)),note="Read-only asynchronous sample; clockBefore/After identify concurrent simulation advancement."};
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
                bool initialBreak=true,captured=false;var detector=new StallDetector();long handledExceptions=0,reportedExceptions=0;uint lastExceptionCode=0,lastExceptionAddress=0;var sampleClock=Stopwatch.StartNew();long lastSample=-5000,lastMatch=-250,lastCapture=-30000;string previousMatch=null;bool divergenceCaptured=false;bool sawDivergence=false;uint lastConstructionGuard=0;
                var recentMatch=new Queue<object>();object lastMatchState=null,lastNetworkState=null;DateTime? lastStateUtc=null;bool sawUnhandledException=false;int? debugExit=null;
                while(true) {
                    // Drain pending debugger events before telemetry: a pending event suspends the target.
                    bool pendingDebugEvent=attached && WaitForDebugEvent(buffer,0);
                    if(!pendingDebugEvent) {
                    if(sampleClock.ElapsedMilliseconds-lastCapture>=30000) {
                        lastCapture=sampleClock.ElapsedMilliseconds;
                        try {Write(folder,"capture-environment",new {affinity=p.ProcessorAffinity.ToInt64(),modules=p.Modules.Cast<ProcessModule>().Select(m=>m.ModuleName).Where(n=>n.IndexOf("obs",StringComparison.OrdinalIgnoreCase)>=0||n.IndexOf("capture",StringComparison.OrdinalIgnoreCase)>=0||n.IndexOf("graphics-hook",StringComparison.OrdinalIgnoreCase)>=0).ToArray()});}catch(Exception ex) {Write(folder,"capture-environment-error",ex.Message);}
                    }
                    if(engineMouse && sampleClock.ElapsedMilliseconds-lastMatch>=250) {
                        lastMatch=sampleClock.ElapsedMilliseconds;
                        try {
                            uint rejected=CaptureConstructionGuard(p,folder,lastConstructionGuard);
                            if(rejected!=lastConstructionGuard){lastConstructionGuard=rejected;try{Write(folder,"sync-trace-captured",CaptureSyncTrace(p,folder,"invalid-build-target"));}catch(Exception ex){Write(folder,"sync-trace-save-error",ex.Message);}}
                            var values=new List<int?>();
                            foreach(int address in new[]{0x504f48,0x507bf4,0x507bf8,0x51a668,0x51a8e4}) {
                                int size=address==0x504f48||address==0x51a8e4?1:4;byte[] b=new byte[size];IntPtr n;
                                values.Add(ReadProcessMemory(p.Handle,new IntPtr(address),b,size,out n)&&n.ToInt64()==size?(int?)(size==1?b[0]:BitConverter.ToInt32(b,0)):null);
                            }
                            if(values[0]==4 && values[4].GetValueOrDefault()>0 && !divergenceCaptured){divergenceCaptured=true;sawDivergence=true;try{Write(folder,"sync-trace-captured",CaptureSyncTrace(p,folder,"first-divergence"));}catch(Exception ex){Write(folder,"sync-trace-save-error",ex.Message);}try{Write(folder,"first-sync-divergence",DivergenceState(p));}catch(Exception ex){Write(folder,"sync-divergence-error",ex.Message);}}
                            if(values[0].GetValueOrDefault()!=4)divergenceCaptured=false;
                            string current=Core.Json.Serialize(values);
                            if(values[0].HasValue) {
                            lastMatchState=MatchState(p);lastNetworkState=NetworkState(p);lastStateUtc=DateTime.UtcNow;
                            recentMatch.Enqueue(new {utc=lastStateUtc,state=lastMatchState,network=lastNetworkState});while(recentMatch.Count>120)recentMatch.Dequeue();
                            if(current!=previousMatch) {
                                previousMatch=current;lastNetworkState=NetworkState(p);Write(folder,"match-transition",lastMatchState);Write(folder,"network-at-transition",lastNetworkState);
                                // Dialog 14 is shared by several outcomes; retain raw values,
                                // not a guessed DRAW/disconnect label.
                                if(values[2]==14 || values[1]==1)Write(folder,"match-result-context",new {match=lastMatchState,network=lastNetworkState,players=MenuState(p),input=InputState(p),history=recentMatch.ToArray()});
                            }
                            }
                        }catch(Exception ex) {Write(folder,"match-sample-error",ex.Message);}
                    }
                    if(sampleClock.ElapsedMilliseconds-lastSample>=5000) {
                        lastSample=sampleClock.ElapsedMilliseconds;
                        if(handledExceptions!=reportedExceptions){Write(folder,"first-chance-summary",new {total=handledExceptions,sinceLast=handledExceptions-reportedExceptions,lastCode="0x"+lastExceptionCode.ToString("X8"),lastAddress="0x"+lastExceptionAddress.ToString("X8"),note="First-chance exceptions are passed to the application; not proof of a crash."});reportedExceptions=handledExceptions;}
                        Snapshot(p,folder,!EditorPatch.IsEditor(name),engineMouse,detector,ref captured);
                        // Persist a bounded rolling copy before a crash/forced monitor exit.
                        // Atomic replacement leaves the previous valid copy on write failure.
                        try {
                            string target=Path.Combine(folder,"recent-state.json"),pending=target+".partial";
                            if(engineMouse){lastNetworkState=NetworkState(p);try{CaptureSyncTrace(p,folder,"periodic");}catch(Exception ex){Write(folder,"sync-trace-save-error",ex.Message);}}
                            File.WriteAllText(pending,Core.Json.Serialize(new {savedUtc=DateTime.UtcNow,lastStateUtc=lastStateUtc,match=lastMatchState,network=lastNetworkState,history=recentMatch.ToArray()}));
                            if(File.Exists(target))File.Replace(pending,target,null);else File.Move(pending,target);
                        }catch(Exception ex){Write(folder,"recent-state-save-error",ex.Message);}
                    }
                    if(!attached) {if(p.HasExited)break;Thread.Sleep(engineMouse?250:1000);continue;}
                    if(!WaitForDebugEvent(buffer,engineMouse?250U:1000U)) {if(p.HasExited)break;continue;}
                    }
                    uint kind=unchecked((uint)Marshal.ReadInt32(buffer)),tid=unchecked((uint)Marshal.ReadInt32(buffer,8)),status=0x10002;
                    bool exited=false;
                    try {
                        if(kind==1) {
                            uint code=unchecked((uint)Marshal.ReadInt32(buffer,12));bool first=Marshal.ReadInt32(buffer,92)!=0;
                            bool bootstrap=initialBreak && first && code==0x80000003;if(bootstrap)initialBreak=false;
                            status=bootstrap?0x10002U:0x80010001U;
                            if(!bootstrap && first){handledExceptions++;lastExceptionCode=code;lastExceptionAddress=unchecked((uint)Marshal.ReadInt32(buffer,24));}
                            if(!first)Write(folder,"exception",new {code="0x"+code.ToString("X8"),address="0x"+unchecked((uint)Marshal.ReadInt32(buffer,24)).ToString("X8"),thread=tid,firstChance=false});
                            if(!first) {sawUnhandledException=true;if(engineMouse) {try{lastConstructionGuard=CaptureConstructionGuard(p,folder,lastConstructionGuard);Write(folder,"sync-trace-captured",CaptureSyncTrace(p,folder,"crash"));}catch(Exception ex){Write(folder,"sync-trace-save-error",ex.Message);}Write(folder,"network-at-crash",NetworkState(p));Write(folder,"match-at-crash",MatchState(p));Write(folder,"input-at-crash",InputState(p));}try {Dump(p,tid,buffer,folder);}catch(Exception ex) {Write(folder,"dump-error",ex.Message);}}
                        } else if(kind==3 || kind==6) {IntPtr f=Marshal.ReadIntPtr(buffer,12);if(f!=IntPtr.Zero && f!=new IntPtr(-1))CloseHandle(f);}
                        else if(kind==5) {if(engineMouse)try{lastConstructionGuard=CaptureConstructionGuard(p,folder,lastConstructionGuard);Write(folder,"sync-trace-captured",CaptureSyncTrace(p,folder,"exit"));}catch(Exception ex){Write(folder,"sync-trace-save-error",ex.Message);}debugExit=Marshal.ReadInt32(buffer,12);Write(folder,"exit",new {code="0x"+unchecked((uint)debugExit.Value).ToString("X8")});exited=true;}
                    } finally {if(!ContinueDebugEvent((uint)pid,tid,status))Write(folder,"continue-error",Marshal.GetLastWin32Error());}
                    if(exited)break;
                }
                Write(folder,"first-chance-summary",new {total=handledExceptions,sinceLast=handledExceptions-reportedExceptions,lastCode="0x"+lastExceptionCode.ToString("X8"),lastAddress="0x"+lastExceptionAddress.ToString("X8")});
                Write(folder,"process-end-context",new {lastStateUtc=lastStateUtc,debugExit=debugExit,unhandledException=sawUnhandledException,match=lastMatchState,network=lastNetworkState,history=recentMatch.ToArray(),note="Cached state before exit; exit code zero does not prove a normal match completion."});
                p.WaitForExit();
                try {string logName="DDrawCompat-"+Path.GetFileNameWithoutExtension(name)+".log";string log=Path.Combine(binaryFolder,logName);if(EditorPatch.IsEditor(name) && File.Exists(log) && new FileInfo(log).Length<=8*1024*1024)File.Copy(log,Path.Combine(folder,logName),true);}catch(Exception ex) {Write(folder,"editor-log-copy-error",ex.Message);}
                foreach(string logName in new[]{"ipxwrapper.log","dplayx.log","directplay.log"})try {string file=Path.Combine(binaryFolder,logName);if(File.Exists(file)&&new FileInfo(file).Length<=8*1024*1024)File.Copy(file,Path.Combine(folder,logName),true);}catch(Exception ex){Write(folder,"network-log-error",ex.Message);}
                Write(folder,"process-end",new {exit="0x"+p.ExitCode.ToString("X8")});
                try {DiagnosticReports.SaveSession(folder,sawUnhandledException?"미처리 예외 감지":sawDivergence?"동기화 불일치 감지":"프로세스 종료 / 정상 여부 미판정");}catch(Exception ex){Write(folder,"automatic-report-error",ex.Message);}
            }return 0;}catch(Exception ex) {Write(folder,"monitor-error",ex.ToString());try{DiagnosticReports.SaveSession(folder,"진단 감시 중단 / 마지막 저장 기록");}catch(Exception saveError){Write(folder,"automatic-report-error",saveError.Message);}return 1;}
            finally {if(attached)DebugActiveProcessStop((uint)pid);Marshal.FreeHGlobal(buffer);}
        }
        public static string Report(string game,string destination) {
            string temp=destination+"."+Guid.NewGuid().ToString("N")+".partial";var index=new List<object>();var includedNames=new HashSet<string>(StringComparer.OrdinalIgnoreCase);long total=0;
            try {using(var zip=ZipFile.Open(temp,ZipArchiveMode.Create)) {
                var files=new List<string>();
                foreach(string name in new[]{"launcher.log","launcher.log.1","settings.json"}) {string f=Path.Combine(Core.Home,name);if(File.Exists(f))files.Add(f);}
                string updates=Path.Combine(Core.Home,"updates");if(Directory.Exists(updates))files.AddRange(Directory.GetFiles(updates,"update-result.log",SearchOption.AllDirectories));
                foreach(string directory in new[]{Home,Path.Combine(Core.Home,"NetworkSetup"),Path.Combine(Core.Home,"ReplayDiagnostics"),Path.Combine(Core.Home,"CrashDumps")})if(Directory.Exists(directory))files.AddRange(Directory.GetFiles(directory,"*",SearchOption.AllDirectories).Where(f=>new[]{".jsonl",".log",".json",".txt",".dmp",".ini",".dat",".1"}.Contains(Path.GetExtension(f).ToLowerInvariant())));
                if(Directory.Exists(CrazyZoneServer.Home))files.AddRange(Directory.GetFiles(CrazyZoneServer.Home,"server-*.jsonl*",SearchOption.TopDirectoryOnly));
                foreach(string file in files.OrderByDescending(f=>File.GetLastWriteTimeUtc(f))) {
                    string relative=file.Substring(Core.Home.Length+1).Replace('\\','/');
                    try {
                        if((File.GetAttributes(file)&FileAttributes.ReparsePoint)!=0) {index.Add(new {file=relative,status="skipped-link"});continue;}
                        using(var input=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete)) {
                            long length=input.Length;if(length>64L*1024*1024 || total+length>512L*1024*1024) {index.Add(new {file=relative,status="skipped-size-limit",bytes=length});continue;}
                            var entry=zip.CreateEntry(relative,CompressionLevel.Optimal);
                            using(var output=entry.Open()) {byte[] buffer=new byte[65536];long left=length;while(left>0) {int n=input.Read(buffer,0,(int)Math.Min(left,buffer.Length));if(n==0)break;output.Write(buffer,0,n);left-=n;}if(left!=0)throw new IOException("File changed during report");}
                            includedNames.Add(relative);total+=length;index.Add(new {file=relative,status="included",bytes=length});
                        }
                    }catch(Exception ex) {index.Add(new {file=relative,status="failed",error=ex.Message});}
                }
                DiagnosticReports.MergeAutomatic(zip,index,includedNames,ref total);
                foreach(string n in new[]{"ddraw.ini","DDrawCompat.ini","DDrawCompat-ACE.ini","DDrawCompat-ACE.Compat.ini","DDrawCompat-ACE.log","DDrawCompat-ACE.Compat.log","cnc-ddraw.log","ddraw.log","ipxwrapper.log","dplayx.log","directplay.log",".amagadon-editor.json"}) {
                    string f=Path.Combine(game??"",n);if(String.IsNullOrWhiteSpace(game) || !File.Exists(f))continue;
                    try {if(new FileInfo(f).Length<=8*1024*1024) {using(var input=new FileStream(f,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete))using(var output=zip.CreateEntry("game/"+n).Open())input.CopyTo(output);}}catch(Exception ex) {index.Add(new {file=n,status="failed",error=ex.Message});}
                }
                using(var writer=new StreamWriter(zip.CreateEntry("report.json").Open()))writer.Write(Core.Json.Serialize(new {version=Core.DisplayVersion,created=DateTime.Now.ToString("o"),os=Environment.OSVersion.ToString(),files=index,notes="Local diagnostic report. Includes local paths and crash thread memory; no automatic upload. Size limits: 64 MiB/file, 512 MiB total. No game data/replays included."}));
            }File.Copy(temp,destination,true);return destination;}finally {if(File.Exists(temp))File.Delete(temp);}
        }
    }
}
