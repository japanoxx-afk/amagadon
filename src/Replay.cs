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
    public sealed class ReplayInfo {
        public int Format=1, Frames;
        public string Version=Core.DisplayVersion, ExecutableHash, DataHash, IndexHash, SaveHash, CommandsHash;
        public string CreatedUtc, MapName, MapHash;
        public bool Complete;
    }
    public static class ReplayFiles {
        public static string Home { get { return Path.Combine(Core.Home,"Replays"); } }
        public const long MaxCommands=512L*1024*1024, MaxSave=64L*1024*1024;
        public static ReplayInfo Inspect(string file) {
            using(var zip=ZipFile.OpenRead(file)) {
                var entry=zip.GetEntry("manifest.json");if(entry==null || entry.Length>65536)throw new IOException("리플레이 목록 정보가 올바르지 않습니다.");
                using(var reader=new StreamReader(entry.Open())) {
                    var info=Core.Json.Deserialize<ReplayInfo>(reader.ReadToEnd());
                    if(info==null || (info.Format!=1 && info.Format!=2) || !info.Complete || info.Frames<1)throw new IOException("완료되지 않은 리플레이입니다.");return info;
                }
            }
        }
        public static void CopyBounded(Stream input,Stream output,long limit) {
            byte[] buffer=new byte[65536];long total=0;int n;
            while((n=input.Read(buffer,0,buffer.Length))>0) { total+=n;if(total>limit)throw new IOException("리플레이 파일 크기 제한을 초과했습니다.");output.Write(buffer,0,n); }
        }
        public static void Pack(string directory,string destination,ReplayInfo info) {
            info.SaveHash=Core.Hash(Path.Combine(directory,"start.sav"));info.CommandsHash=Core.Hash(Path.Combine(directory,"commands.bin"));
            File.WriteAllText(Path.Combine(directory,"manifest.json"),Core.Json.Serialize(info),Encoding.UTF8);
            string temporary=destination+".partial";
            using(var stream=new FileStream(temporary,FileMode.CreateNew)) using(var zip=new ZipArchive(stream,ZipArchiveMode.Create)) {
                foreach(string name in new[]{"manifest.json","start.sav","commands.bin"}) using(var output=zip.CreateEntry(name,CompressionLevel.Optimal).Open()) using(var input=File.OpenRead(Path.Combine(directory,name)))input.CopyTo(output);
            }
            File.Move(temporary,destination);
        }
        public static ReplayInfo Unpack(string source,string directory) {
            Directory.CreateDirectory(directory);
            using(var stream=File.OpenRead(source)) using(var zip=new ZipArchive(stream,ZipArchiveMode.Read)) {
                string[] names={"manifest.json","start.sav","commands.bin"};
                if(zip.Entries.Count!=3 || names.Any(n=>zip.Entries.Count(e=>e.FullName==n)!=1))throw new IOException("지원하지 않는 리플레이 구성입니다.");
                foreach(string name in names) {
                    var entry=zip.GetEntry(name);long limit=name=="manifest.json"?16384:(name=="start.sav"?MaxSave:MaxCommands);
                    if(entry.Length>limit)throw new IOException("리플레이 파일 크기 제한을 초과했습니다.");
                    using(var input=entry.Open()) using(var output=new FileStream(Path.Combine(directory,name),FileMode.CreateNew))CopyBounded(input,output,limit);
                }
            }
            var info=Core.Json.Deserialize<ReplayInfo>(File.ReadAllText(Path.Combine(directory,"manifest.json")));
            if(info==null || (info.Format!=1 && info.Format!=2) || !info.Complete || info.Frames<1 || info.Frames>1000000)throw new IOException("완료되지 않았거나 지원하지 않는 리플레이입니다.");
            if(Core.Hash(Path.Combine(directory,"start.sav"))!=info.SaveHash || Core.Hash(Path.Combine(directory,"commands.bin"))!=info.CommandsHash)throw new IOException("리플레이 파일 검증에 실패했습니다.");
            byte[] header=new byte[518];
            using(var save=File.OpenRead(Path.Combine(directory,"start.sav"))) {
                if(save.Read(header,0,header.Length)!=header.Length || Array.IndexOf(header,(byte)0,0,256)<0 || BitConverter.ToUInt32(header,514)>1700)
                    throw new IOException("리플레이 시작 저장본의 헤더가 올바르지 않습니다.");
            }
            using(var input=new ReplayReader(Path.Combine(directory,"commands.bin"),info.Format))input.Validate(info.Frames);
            return info;
        }
        public static void CheckGame(ReplayInfo info,string game,string executable) {
            if(Core.Hash(executable)!=info.ExecutableHash || Core.Hash(Path.Combine(game,"Armageddon.MFP"))!=info.DataHash || Core.Hash(Path.Combine(game,"Armageddon.HED"))!=info.IndexHash)
                throw new IOException("기록 당시의 게임 데이터 및 런처 패치 버전이 필요합니다.");
            if(!String.IsNullOrEmpty(info.MapHash)) {
                string map=MapPath(game,info.MapName);
                if(map==null || !File.Exists(map) || Core.Hash(map)!=info.MapHash)throw new IOException("기록 당시의 사용자 맵이 필요합니다: "+info.MapName);
            }
        }
        public static string MapPath(string game,string map) {
            if(String.IsNullOrWhiteSpace(map) || Path.IsPathRooted(map))return null;
            string root=Path.GetFullPath(game).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
            string full=Path.GetFullPath(Path.Combine(root,map));
            return full.StartsWith(root,StringComparison.OrdinalIgnoreCase)?full:null;
        }
    }
    public sealed class ReplayEvent {
        public int Kind; public uint Clock, Digest; public byte[] Data;
    }
    public sealed class ReplayReader : IDisposable {
        readonly BinaryReader reader;int format;
        public ReplayReader(string path,int expectedFormat=0) {
            format=expectedFormat;
            reader=new BinaryReader(File.OpenRead(path));
            if(Encoding.ASCII.GetString(reader.ReadBytes(8))!="AGRPL001") {reader.Dispose();throw new IOException("리플레이 헤더가 다릅니다.");}
        }
        public ReplayEvent Next() {
            if(reader.BaseStream.Position==reader.BaseStream.Length)return null;
            var e=new ReplayEvent {Kind=reader.ReadInt32(),Clock=reader.ReadUInt32(),Digest=reader.ReadUInt32()};
            int length=reader.ReadInt32();int expected=e.Kind==1?2072:(e.Kind==2?64:(e.Kind==3?1408:(e.Kind==0?0:-1)));
            if(e.Kind!=0 && format==0)format=length==expected?1:(length==expected+8?2:-1);
            if(expected<0 || length!=(expected+(e.Kind!=0 && format==2?8:0)))throw new IOException("잘못된 리플레이 명령 길이입니다.");
            e.Data=reader.ReadBytes(length);if(e.Data.Length!=length)throw new IOException("리플레이 기록이 중간에 잘렸습니다.");if(e.Kind!=0 && format==2 && BitConverter.ToUInt32(e.Data,expected)>250)throw new IOException("리플레이 엔진 난수 범위 오류");return e;
        }
        // The next frame retains this frame's resolved packet at 52f250.
        // Read it without advancing the event stream, including legacy files.
        public byte[] PreviousFinalPacket() {
            long position=reader.BaseStream.Position;
            try {ReplayEvent next;while((next=Next())!=null) {if(next.Kind==0)return null;if(next.Kind==3)return next.Data.Skip(64).Take(64).ToArray();}return null;}
            finally {reader.BaseStream.Position=position;}
        }
        public void Validate(int frames) {
            int count=0,phase=0;bool ended=false;ReplayEvent e;
            while((e=Next())!=null) {
                if(ended)throw new IOException("리플레이 종료 뒤 데이터가 있습니다.");
                if(e.Kind==0) {ended=true;continue;}
                if(e.Kind==1) {count++;phase=1;}
                else if(e.Kind==2 && phase==1)phase=2;
                else if(e.Kind==3 && phase==2)phase=3;
                else throw new IOException("리플레이 명령 순서가 다릅니다.");
            }
            if(!ended || count!=frames)throw new IOException("리플레이 완료 정보가 다릅니다.");
        }
        public void Dispose() {reader.Dispose();}
    }
    // Only controls the process that this instance creates suspended. No attach,
    // discovery, remote thread, or injection into an already-running game.
    sealed class ReplayMemoryException : IOException {
        public ReplayMemoryException(string operation,int address,int length,int error) : base("리플레이 메모리 "+operation+" 실패: 0x"+address.ToString("X8")+", "+length+"바이트, Windows 오류 "+error) {}
    }
    public sealed class ReplaySession : IDisposable {
        const int Box=0x233a000;
        const int KeyboardSize=2056;
        const int SnapshotLoadAddress=0x2338d00;
        const string SnapshotLoadCode="VVNWV4HskAAAAIucJKQAAACLawiNs8wBAACJ57kjAAAA/POl/7QksAAAAP+0JLAAAAD/tCSwAAAA/7QksAAAAOjrwBX+g8QQg/gBdSGJawiJ5o27zAEAALkjAAAAgz8AdASLFokXg8YEg8cE4u+BxJAAAABfXltdww==";
        const string SnapshotLoadCall="6ATX7gE=";
        const int PostInputAddress=0x2338e00;
        // call original UI helper; preserve flags/registers; replace the local
        // final command packet from our mailbox; return to the original loop.
        const string PostInputCode="6MvzDP6cYA+2BXByTgDB4AaNuBD1UgC+AKIzArkQAAAA/POlYZ3D";
        const string PostInputCall="6MVJ7gE=";
        readonly string game,executable,source;
        readonly bool fixture,eventsEnabled;
        string work,relative,recordDirectory,recordDestination;
        ReplayInfo info; ReplayReader reader; BinaryWriter writer;
        IntPtr handle,requestEvent,ackEvent; bool preciseTimer; uint request; int frames;
        bool playback,finished,disposed;
        volatile bool stopRequested;
        public bool IsPlayback {get {return playback;}}
        public void RequestStop() {if(playback)stopRequested=true;}
        public Action<string> Progress;
        bool reportedScreen;
        public string Result { get; private set; }
        public string CreatedReplay {get;private set;}
        internal string CaptureDiagnostic;BinaryWriter scenarioWriter;string scenarioDirectory;
        public int ChildExitCode {get;private set;}
        public Settings DiagnosticSettings;
        [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Startup {
            public int cb;public string reserved,desktop,title;public int x,y,cx,cy,xchars,ychars,fill,flags;public short show,reserved2;public IntPtr bytes,input,output,error;
        }
        [StructLayout(LayoutKind.Sequential)] struct ProcessInfo {public IntPtr process,thread;public uint pid,tid;}
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(string app,StringBuilder cmd,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr environment,string cwd,ref Startup startup,out ProcessInfo pi);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr process,IntPtr address,byte[] buffer,int size,out IntPtr read);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool WriteProcessMemory(IntPtr process,IntPtr address,byte[] buffer,int size,out IntPtr written);
        [DllImport("kernel32.dll")] static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr handle,uint code);
        [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
        [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr handle,out uint code);
        [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr CreateEvent(IntPtr attributes,bool manual,bool initial,string name);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetEvent(IntPtr value);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool DuplicateHandle(IntPtr sourceProcess,IntPtr source,IntPtr targetProcess,out IntPtr target,uint access,bool inherit,uint options);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool FlushInstructionCache(IntPtr process,IntPtr address,UIntPtr size);
        [DllImport("winmm.dll")] static extern uint timeBeginPeriod(uint value);
        [DllImport("winmm.dll")] static extern uint timeEndPeriod(uint value);
        void SetupEvents() {
            requestEvent=CreateEvent(IntPtr.Zero,false,false,null);ackEvent=CreateEvent(IntPtr.Zero,false,false,null);
            if(requestEvent==IntPtr.Zero || ackEvent==IntPtr.Zero)throw new IOException("리플레이 동기화 이벤트 생성 실패");
            IntPtr childRequest,childAck;
            if(!DuplicateHandle(new IntPtr(-1),requestEvent,handle,out childRequest,0,false,2) || !DuplicateHandle(new IntPtr(-1),ackEvent,handle,out childAck,0,false,2))throw new IOException("리플레이 동기화 이벤트 전달 실패");
            Number(Box+40,unchecked((uint)childRequest.ToInt32()));Number(Box+44,unchecked((uint)childAck.ToInt32()));
        }
        bool Exited {get {return WaitForSingleObject(handle,0)==0;}}
        // During ExitProcess the address space can disappear before the process
        // object is signaled. Wait for that signal before treating RPM as failure.
        bool ExitedSoon() {bool ended=WaitForSingleObject(handle,500)==0;if(ended)Core.Log("Replay memory unavailable during exit; process exit confirmed");return ended;}
        int ExitCode {get {uint value;if(!GetExitCodeProcess(handle,out value))throw new IOException("게임 종료 코드를 읽을 수 없습니다.");return unchecked((int)value);}}
        public ReplaySession(string folder,string file,string replay) : this(folder,file,replay,false) {}
        internal ReplaySession(string folder,string file,string replay,bool testFixture,bool useEvents=true) {game=folder;executable=file;source=replay;playback=replay!=null;fixture=testFixture;eventsEnabled=useEvents;}
        byte[] Read(int address,int length) {
            byte[] bytes=new byte[length];IntPtr read;
            if(!ReadProcessMemory(handle,new IntPtr(address),bytes,length,out read) || read.ToInt64()!=length)throw new ReplayMemoryException("읽기",address,length,Marshal.GetLastWin32Error());return bytes;
        }
        void Write(int address,byte[] bytes) {IntPtr written;if(!WriteProcessMemory(handle,new IntPtr(address),bytes,bytes.Length,out written) || written.ToInt64()!=bytes.Length)throw new ReplayMemoryException("쓰기",address,bytes.Length,Marshal.GetLastWin32Error());}
        uint U32(int address) {return BitConverter.ToUInt32(Read(address,4),0);}
        void Number(int address,uint value) {Write(address,BitConverter.GetBytes(value));}
        void SetSavePath(string path) {
            byte[] name=Encoding.ASCII.GetBytes(path+"\0");if(name.Length>256)throw new IOException("리플레이 임시 경로가 너무 깁니다.");Write(Box+256,name);
        }
        public void Run() {
            try {
                preciseTimer=(!eventsEnabled || Core.Hash(executable)==NativePatch.LegacyOutputHash) && timeBeginPeriod(1)==0;
                Directory.CreateDirectory(ReplayFiles.Home);
                relative="LauncherReplayWork\\"+Guid.NewGuid().ToString("N");work=Path.Combine(game,relative);Directory.CreateDirectory(work);
                if(playback) {
                    info=ReplayFiles.Unpack(source,work);
                    if(CaptureDiagnostic!=null)info.ExecutableHash=Core.Hash(executable);
                    ReplayFiles.CheckGame(info,game,executable);reader=new ReplayReader(Path.Combine(work,"commands.bin"),info.Format);
                    if(CaptureDiagnostic!=null) {
                        scenarioDirectory=Path.Combine(work,"scenario");Directory.CreateDirectory(scenarioDirectory);File.Copy(Path.Combine(work,"start.sav"),Path.Combine(scenarioDirectory,"start.sav"));
                        scenarioWriter=new BinaryWriter(new FileStream(Path.Combine(scenarioDirectory,"commands.bin"),FileMode.CreateNew));scenarioWriter.Write(Encoding.ASCII.GetBytes("AGRPL001"));
                        Core.Log("SCENARIO CAPTURE: scripted inputs only; source state hashes are not used as a recovery claim");
                    }
                }
                var startup=new Startup {cb=Marshal.SizeOf(typeof(Startup))};ProcessInfo pi;
                var environment=new System.Collections.Generic.SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase);
                foreach(System.Collections.DictionaryEntry item in Environment.GetEnvironmentVariables())environment[(string)item.Key]=(string)item.Value;
                environment["__COMPAT_LAYER"]=(environment.ContainsKey("__COMPAT_LAYER")?environment["__COMPAT_LAYER"]:"")+" HIGHDPIAWARE DISABLEDXMAXIMIZEDWINDOWEDMODE";
                IntPtr environmentBlock=Marshal.StringToHGlobalUni(String.Join("\0",environment.Select(item=>item.Key+"="+item.Value))+"\0\0");
                try {if(!CreateProcess(executable,new StringBuilder("\""+executable+"\""),IntPtr.Zero,IntPtr.Zero,false,4|0x400,environmentBlock,game,ref startup,out pi))throw new IOException("게임을 실행할 수 없습니다. 오류 "+Marshal.GetLastWin32Error());}finally {Marshal.FreeHGlobal(environmentBlock);}
                handle=pi.process;
                if(!fixture)Diagnostics.Begin((int)pi.pid,executable,game,DiagnosticSettings);
                Core.Log("Replay start pid="+pi.pid+" mode="+(playback?"play":"record")+" executable="+executable+" mailbox=0x"+Box.ToString("X8"));
                try {
                    // Verify our mailbox belongs to the exact known patch before activating.
                    if(fixture) {if(Encoding.ASCII.GetString(Read(Box+64,8))!="AGRTEST1")throw new IOException("리플레이 테스트 프로세스 서명이 다릅니다: "+BitConverter.ToString(Read(Box+64,8)));}
                    else if(Core.Hash(executable)!=NativePatch.Replay034Hash && Core.Hash(executable)!=NativePatch.Replay033FinalHash && Core.Hash(executable)!=NativePatch.LegacyOutputHash && Core.Hash(executable)!=NativePatch.Replay032Hash && Core.Hash(executable)!=NativePatch.Replay033Hash && Core.Hash(executable)!=NativePatch.Load(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"compat","hd-preview.json")).OutputHash)throw new IOException("지원하지 않는 리플레이 실행 파일입니다.");
                    if(eventsEnabled && Core.Hash(executable)!=NativePatch.LegacyOutputHash)SetupEvents();
                    if(playback && !fixture) {
                        if(BitConverter.ToString(Read(0x454436,5))!="E8-95-3D-FB-FF")throw new IOException("지원하지 않는 리플레이 명령 생성 코드입니다.");
                        if(BitConverter.ToString(Read(0x44b5f7,5))!="E8-34-98-04-00")throw new IOException("지원하지 않는 저장본 로더입니다.");
                        byte[] loader=Convert.FromBase64String(SnapshotLoadCode);
                        if(Read(SnapshotLoadAddress,loader.Length).Any(value=>value!=0))throw new IOException("저장본 호환 코드 공간이 사용 중입니다.");
                        Write(SnapshotLoadAddress,loader);Write(0x44b5f7,Convert.FromBase64String(SnapshotLoadCall));
                        byte[] code=Convert.FromBase64String(PostInputCode);
                        if(Read(PostInputAddress,code.Length).Any(value=>value!=0))throw new IOException("리플레이 호환 코드 공간이 사용 중입니다.");
                        Write(PostInputAddress,code);Write(0x454436,Convert.FromBase64String(PostInputCall));
                        if(!FlushInstructionCache(handle,IntPtr.Zero,UIntPtr.Zero))throw new IOException("리플레이 호환 코드 반영 실패");
                    }
                    SetSavePath(relative+"\\start.sav");Number(Box,playback?2U:1U);
                    if(ResumeThread(pi.thread)==UInt32.MaxValue)throw new IOException("게임 실행을 재개할 수 없습니다.");
                } catch {TerminateProcess(handle,0xe002);throw;} finally {CloseHandle(pi.thread);}
                while(!Exited) {
                    if(stopRequested) {Result="리플레이 재생을 중단했습니다.";finished=true;TerminateProcess(handle,0);WaitForSingleObject(handle,5000);break;}
                    if(requestEvent!=IntPtr.Zero && WaitForSingleObject(requestEvent,100)!=0)continue;
                    byte[] state;
                    try {state=Read(Box,36);} catch(ReplayMemoryException ex) {if(ExitedSoon())break;Core.Log(ex.Message);throw;}
                    uint next=BitConverter.ToUInt32(state,4);
                    if(next==request) {
                        if(!finished && BitConverter.ToUInt32(state,32)!=0) {Result="리플레이 기록을 시작하지 못했거나 동기화 대기 시간이 초과되었습니다. 임시 기록은 보존했습니다.";finished=true;}
                        Thread.Sleep(1);continue;
                    }
                    request=next;int kind=BitConverter.ToInt32(state,12);
                    try {Handle(kind);} catch(Exception ex) {
                        if(Exited || (ex is ReplayMemoryException && ExitedSoon()))break;
                        Result=(playback?"리플레이 재생 중단: ":"자동 기록 중단: ")+ex.Message;Core.Log(Result);
                        Number(Box,playback?3U:0U);finished=true;
                    }
                    try {Number(Box+8,request);if(ackEvent!=IntPtr.Zero && !SetEvent(ackEvent))throw new IOException("리플레이 응답 이벤트 실패");}catch(ReplayMemoryException ex) {if(ExitedSoon())break;Core.Log(ex.Message);throw;}
                }
                ChildExitCode=ExitCode;
                if(playback && !finished && ChildExitCode==0xe001)Result="리플레이 동기화 대기 시간이 초과되어 재생을 중단했습니다.";
                if(!finished && !playback && writer!=null) {
                    if(ExitCode==0)FinishRecording();
                    else Result="게임 비정상 종료로 기록이 중단되었습니다. 임시 기록은 LauncherReplayWork 폴더에 보존했습니다.";
                }
                if(playback && !finished && ChildExitCode!=0 && String.IsNullOrEmpty(Result))Result="리플레이 게임이 비정상 종료했습니다: 0x"+ChildExitCode.ToString("X8")+" · 재생 "+frames+"프레임. 진단 로그를 확인해주세요.";
                if(String.IsNullOrEmpty(Result))Result=playback?"게임이 종료되어 리플레이 재생을 마쳤습니다.":"게임을 종료했습니다. 기록한 리플레이가 없으면 싱글플레이와 1024×768 모드를 확인해주세요.";
                Core.Log("Replay child exit=0x"+ExitCode.ToString("X8")+" "+Result);
            } finally {
                if(requestEvent!=IntPtr.Zero) {CloseHandle(requestEvent);requestEvent=IntPtr.Zero;}
                if(ackEvent!=IntPtr.Zero) {CloseHandle(ackEvent);ackEvent=IntPtr.Zero;}
                if(preciseTimer) {timeEndPeriod(1);preciseTimer=false;}
                if(scenarioWriter!=null) {scenarioWriter.Dispose();scenarioWriter=null;}
                if(writer!=null) {writer.Dispose();writer=null;}
                if(reader!=null) {reader.Dispose();reader=null;}
                // Keep failed recording journals for diagnostics/recovery. Only our
                // unique playback extraction directory is disposable.
                if(playback && work!=null && Directory.Exists(work))Directory.Delete(work,true);
            }
        }
        void Handle(int kind) {
            if(kind==98)throw new IOException("재생 중 저장·불러오기 명령은 지원하지 않습니다. 원본 저장 파일은 변경하지 않았습니다.");
            if(kind==99)throw new IOException("시작 상태를 게임에서 불러오지 못했습니다.");
            if(kind==10) {
                if(writer!=null)FinishRecording();frames=0;
                recordDirectory=Path.Combine(work,"match-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(recordDirectory);
                SetSavePath(relative+"\\"+Path.GetFileName(recordDirectory)+"\\start.sav");
                info=new ReplayInfo {Format=2,ExecutableHash=Core.Hash(executable),DataHash=Core.Hash(Path.Combine(game,"Armageddon.MFP")),IndexHash=Core.Hash(Path.Combine(game,"Armageddon.HED")),CreatedUtc=DateTime.UtcNow.ToString("o")};
                string destination=fixture?Path.Combine(game,"results"):ReplayFiles.Home;Directory.CreateDirectory(destination);
                recordDestination=Path.Combine(destination,DateTime.Now.ToString("yyyyMMdd-HHmmss")+"-"+Guid.NewGuid().ToString("N").Substring(0,8)+".agr");
                writer=new BinaryWriter(new FileStream(Path.Combine(recordDirectory,"commands.bin"),FileMode.CreateNew,FileAccess.Write,FileShare.Read));writer.Write(Encoding.ASCII.GetBytes("AGRPL001"));
                return;
            }
            if(kind==11) {
                string save=Path.Combine(recordDirectory,"start.sav");
                if(!File.Exists(save) || new FileInfo(save).Length<512 || new FileInfo(save).Length>ReplayFiles.MaxSave)throw new IOException("게임 시작 상태를 저장하지 못했습니다.");
                using(var input=File.OpenRead(save)) {byte[] bytes=new byte[256];if(input.Read(bytes,0,256)!=256)throw new IOException("시작 상태가 잘렸습니다.");info.MapName=Encoding.Default.GetString(bytes).Split('\0')[0];}
                string map=ReplayFiles.MapPath(game,info.MapName);if(map!=null && File.Exists(map))info.MapHash=Core.Hash(map);
                return;
            }
            if(kind==4) {
                if(playback) {var end=reader.Next();if(end==null || end.Kind!=0)throw new IOException("기록보다 먼저 게임 장면이 종료되었습니다.");EndPlayback();return;}
                if(writer!=null)FinishRecording();return;
            }
            if(kind==1 && !reportedScreen) {
                if(playback)RestoreSnapshotReferences();
                if(fixture) {reportedScreen=true;} else {
                int width=(int)U32(0x4f75ec),height=(int)U32(0x4f75f0);
                Core.Log("Game speed index="+Read(0x4d4c64,1)[0]+" native delay="+U32(0x503c70)+"ms sync="+(requestEvent!=IntPtr.Zero?"kernel events":"legacy polling"));
                string message="실제 내부 해상도 "+width+"×"+height+" · "+(playback?"리플레이 재생 중":"리플레이 자동 기록 중");
                Core.Log(message);if(Progress!=null)Progress(message);reportedScreen=true;}
            }
            if(kind<1 || kind>3)throw new IOException("알 수 없는 리플레이 동기화 이벤트입니다.");
            if(playback) {
                var e=reader.Next();if(e==null)throw new IOException("리플레이 종료 정보가 없습니다.");
                if(e.Kind==0) {EndPlayback();return;}
                if(e.Kind!=kind)throw new IOException("기록과 현재 게임의 명령 처리 순서가 다릅니다.");
                if(kind==1) {
                    if(e.Clock!=U32(0x503c6c))throw new IOException("게임 진행 시간이 기록과 다릅니다.");
                    if(CaptureDiagnostic==null && e.Digest!=0 && e.Digest!=Digest()) {if(!fixture) {try {DumpReplayState();}catch(Exception diagnostic) {Core.Log("Replay diagnostics unavailable: "+diagnostic.Message);}}throw new IOException((info.Format==1?"이전 형식 리플레이의 AI 상태가 기록과 달라 재생을 중단했습니다. 프레임=":"유닛 위치·체력 상태가 기록과 다릅니다. 프레임=")+(frames+1)+", clock="+e.Clock+", expected="+e.Digest.ToString("X8")+", actual="+Digest().ToString("X8"));}
                    frames++;
                    if(frames%600==0) {string progress="리플레이 재생 · "+frames+" / "+info.Frames+" 프레임";Core.Log(progress);if(Progress!=null)Progress(progress);}
                }
                Apply(kind,e.Data);
                if(scenarioWriter!=null) {
                    byte[] captured=Capture(kind);scenarioWriter.Write(kind);scenarioWriter.Write(U32(0x503c6c));scenarioWriter.Write(kind==1 && (frames==1 || frames%60==0)?Digest():0);scenarioWriter.Write(captured.Length);scenarioWriter.Write(captured);scenarioWriter.Flush();
                }
            } else {
                if(writer==null)throw new IOException("리플레이 기록이 시작되지 않았습니다.");
                if(writer.BaseStream.Length>ReplayFiles.MaxCommands-8192 || frames>=1000000)throw new IOException("자동 기록 용량 한도에 도달했습니다.");
                if(kind==1)frames++;
                WriteEvent(kind,U32(0x503c6c),kind==1 && (frames==1 || frames%60==0)?Digest():0,Capture(kind));
                // Flush a complete event at every barrier; a game crash cannot
                // leave a partial command that was already acknowledged.
                writer.Flush();
            }
        }
        byte[] Capture(int kind) {
            byte[] raw=CaptureRaw(kind),result=new byte[raw.Length+8];Buffer.BlockCopy(raw,0,result,0,raw.Length);Buffer.BlockCopy(BitConverter.GetBytes((uint)Read(0x581158,1)[0]),0,result,raw.Length,4);Buffer.BlockCopy(Read((int)U32(Box+28),4),0,result,raw.Length+4,4);return result;
        }
        byte[] CaptureRaw(int kind) {
            if(kind==2)return Read(0x504d70,64);
            if(kind==3)return Read(0x52f210,1408);
            byte[] result=new byte[2072];Buffer.BlockCopy(Read((int)U32(Box+24)+0x1010,KeyboardSize),0,result,0,KeyboardSize);
            Buffer.BlockCopy(Read((int)U32(Box+28),4),0,result,KeyboardSize,4);Buffer.BlockCopy(Read(0x5812e8,8),0,result,KeyboardSize+4,8);Buffer.BlockCopy(Read((int)U32(Box+36),4),0,result,KeyboardSize+12,4);return result;
        }
        void Apply(int kind,byte[] data) {
            int size=kind==1?2072:(kind==2?64:1408);
            if(data.Length==size+8) {uint index=BitConverter.ToUInt32(data,size);if(index>250)throw new IOException("엔진 난수 상태가 올바르지 않습니다.");Write(0x581158,new[]{(byte)index});Write((int)U32(Box+28),data.Skip(size+4).Take(4).ToArray());data=data.Take(size).ToArray();}
            if(kind==2)Write(0x504d70,data);
            else if(kind==3) {
                if(playback && !fixture) {int player=Read(0x4e7270,1)[0];if(player>=10)throw new IOException("리플레이 플레이어 범위 오류");var packet=reader.PreviousFinalPacket()??data.Skip(0x300+player*64).Take(64).ToArray();Write(Box+0x200,packet);}
                Write(0x52f210,data);
            }
            else {Write((int)U32(Box+24)+0x1010,data.Take(KeyboardSize).ToArray());Write((int)U32(Box+28),data.Skip(KeyboardSize).Take(4).ToArray());Write(0x5812e8,data.Skip(KeyboardSize+4).Take(8).ToArray());Write((int)U32(Box+36),data.Skip(KeyboardSize+12).ToArray());}
        }
        // The original save loader copies complete unit structs, including the
        // previous process's definition and sprite pointers. Rebind those
        // constructor-owned references before the first replay command/render.
        void RestoreSnapshotReferences() {
            int manager=(int)U32(0x504a10);if(manager==0)throw new IOException("리플레이 유닛 관리자가 없습니다.");
            byte[] table=Read(manager,8+1700*4),catalogs=Read(0x5049fc,16);
            int count=0;
            for(int i=0;i<1700;i++) {
                int unit=BitConverter.ToInt32(table,8+i*4);if(unit==0)continue;
                ushort type=BitConverter.ToUInt16(Read(unit+12,2),0);int race=type>>8,index=type&255;
                if(race>3 || index>=100)throw new IOException("지원하지 않는 저장 유닛 종류: "+type.ToString("X4"));
                int catalog=BitConverter.ToInt32(catalogs,race*4);
                if(catalog==0)throw new IOException("리플레이 유닛 정의가 준비되지 않았습니다.");
                uint definition=U32(catalog+4+index*4);if(definition==0)throw new IOException("저장 유닛의 정의를 찾을 수 없습니다.");
                Number(unit+8,definition);
                // Preserve null handles: constructors can leave directional
                // frames unused until the corresponding animation is selected.
                {
                    for(int j=0;j<17;j++)if(U32(unit+0x1cc+j*4)!=0)Number(unit+0x1cc+j*4,U32(catalog+0x57c+index*68+j*4));
                    int[] fields={0x210,0x218,0x220,0x228,0x22c,0x230};
                    for(int j=0;j<fields.Length;j++)if(U32(unit+fields[j])!=0)Number(unit+fields[j],U32(catalog+0x200c+j*0x190+index*4));
                    for(int j=0;j<9;j++)if(U32(unit+0x234+j*4)!=0)Number(unit+0x234+j*4,U32(catalog+0x296c+index*36+j*4));
                }
                count++;
            }
            Core.Log("Replay snapshot references rebound units="+count);
        }
        void DumpReplayState() {
            int manager=(int)U32(0x504a10);byte[] table=Read(manager,8+1700*4);var states=new List<object>();
            for(int i=0;i<1700;i++) {int pointer=BitConverter.ToInt32(table,8+i*4);if(pointer==0)continue;byte[] state=Read(pointer,0x9c8);states.Add(new {Id=i,Type=BitConverter.ToUInt16(state,12),X=BitConverter.ToInt32(state,20),Y=BitConverter.ToInt32(state,24),Owner=state[60],HP=BitConverter.ToInt32(state,0x9c4)});}
            string diagnostics=Path.Combine(Core.Home,"ReplayDiagnostics");Directory.CreateDirectory(diagnostics);File.WriteAllText(Path.Combine(diagnostics,"mismatch-frame"+(frames+1)+".json"),Core.Json.Serialize(states));
        }
        uint Digest() {
            int manager=(int)U32(0x504a10);if(manager==0)throw new IOException("게임 상태가 준비되지 않았습니다.");
            byte[] table=Read(manager,8+1700*4);uint hash=2166136261;
            // Canonical fields only; heap pointers and uninitialized padding are
            // deliberately excluded. This checks the simulation, not rendering.
            for(int i=0;i<1700;i++) {
                int pointer=BitConverter.ToInt32(table,8+i*4);if(pointer==0)continue;
                byte[] unit=Read(pointer,0x9c8);
                foreach(int offset in new[]{12,13,20,21,22,23,24,25,26,27,60,0x9c4,0x9c5,0x9c6,0x9c7})hash=unchecked((hash^unit[offset])*16777619);
                hash=unchecked((hash^(uint)i)*16777619);
            }
            return hash==0?1:hash;
        }
        void WriteEvent(int kind,uint clock,uint digest,byte[] bytes) {writer.Write(kind);writer.Write(clock);writer.Write(digest);writer.Write(bytes.Length);writer.Write(bytes);}
        void FinishRecording() {
            if(writer==null)return;
            WriteEvent(0,0,0,new byte[0]);writer.Dispose();writer=null;
            if(frames==0)return;
            info.Frames=frames;info.Complete=true;ReplayFiles.Pack(recordDirectory,recordDestination,info);
            CreatedReplay=recordDestination;
            Result="리플레이 자동 저장: "+Path.GetFileName(recordDestination);Core.Log(Result);
        }
        void EndPlayback() {
            if(scenarioWriter!=null) {
                scenarioWriter.Write(0);scenarioWriter.Write(0U);scenarioWriter.Write(0U);scenarioWriter.Write(0);scenarioWriter.Dispose();scenarioWriter=null;
                var captured=Core.Json.Deserialize<ReplayInfo>(Core.Json.Serialize(info));captured.Format=2;captured.Version=Core.DisplayVersion;captured.Frames=frames;captured.Complete=true;captured.CreatedUtc=DateTime.UtcNow.ToString("o");ReplayFiles.Pack(scenarioDirectory,CaptureDiagnostic,captured);Core.Log("SCENARIO FORMAT2 WRITTEN "+CaptureDiagnostic);
            }
            finished=true;Result="리플레이 재생을 완료했습니다.";Number(Box,3);}
        public void Dispose() {
            if(disposed)return;disposed=true;
            if(handle!=IntPtr.Zero)CloseHandle(handle);
        }
    }
}
