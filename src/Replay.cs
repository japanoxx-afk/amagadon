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
            if(info==null || info.Format!=1 || !info.Complete || info.Frames<1 || info.Frames>1000000)throw new IOException("완료되지 않았거나 지원하지 않는 리플레이입니다.");
            if(Core.Hash(Path.Combine(directory,"start.sav"))!=info.SaveHash || Core.Hash(Path.Combine(directory,"commands.bin"))!=info.CommandsHash)throw new IOException("리플레이 파일 검증에 실패했습니다.");
            byte[] header=new byte[518];
            using(var save=File.OpenRead(Path.Combine(directory,"start.sav"))) {
                if(save.Read(header,0,header.Length)!=header.Length || Array.IndexOf(header,(byte)0,0,256)<0 || BitConverter.ToUInt32(header,514)>1700)
                    throw new IOException("리플레이 시작 저장본의 헤더가 올바르지 않습니다.");
            }
            using(var input=new ReplayReader(Path.Combine(directory,"commands.bin")))input.Validate(info.Frames);
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
        readonly BinaryReader reader;
        public ReplayReader(string path) {
            reader=new BinaryReader(File.OpenRead(path));
            if(Encoding.ASCII.GetString(reader.ReadBytes(8))!="AGRPL001") {reader.Dispose();throw new IOException("리플레이 헤더가 다릅니다.");}
        }
        public ReplayEvent Next() {
            if(reader.BaseStream.Position==reader.BaseStream.Length)return null;
            var e=new ReplayEvent {Kind=reader.ReadInt32(),Clock=reader.ReadUInt32(),Digest=reader.ReadUInt32()};
            int length=reader.ReadInt32();int expected=e.Kind==1?2072:(e.Kind==2?64:(e.Kind==3?1408:(e.Kind==0?0:-1)));
            if(length!=expected)throw new IOException("잘못된 리플레이 명령 길이입니다.");
            e.Data=reader.ReadBytes(length);if(e.Data.Length!=length)throw new IOException("리플레이 기록이 중간에 잘렸습니다.");return e;
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
    public sealed class ReplaySession : IDisposable {
        const int Box=0x233a000;
        const int KeyboardSize=2056;
        readonly string game,executable,source;
        readonly bool fixture;
        string work,relative,recordDirectory,recordDestination;
        ReplayInfo info; ReplayReader reader; BinaryWriter writer;
        IntPtr handle; uint request; int frames;
        bool playback,finished,disposed;
        volatile bool stopRequested;
        public bool IsPlayback {get {return playback;}}
        public void RequestStop() {if(playback)stopRequested=true;}
        public string Result { get; private set; }
        public string CreatedReplay {get;private set;}
        public int ChildExitCode {get;private set;}
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
        bool Exited {get {return WaitForSingleObject(handle,0)==0;}}
        int ExitCode {get {uint value;if(!GetExitCodeProcess(handle,out value))throw new IOException("게임 종료 코드를 읽을 수 없습니다.");return unchecked((int)value);}}
        public ReplaySession(string folder,string file,string replay) : this(folder,file,replay,false) {}
        internal ReplaySession(string folder,string file,string replay,bool testFixture) {game=folder;executable=file;source=replay;playback=replay!=null;fixture=testFixture;}
        byte[] Read(int address,int length) {
            byte[] bytes=new byte[length];IntPtr read;
            if(!ReadProcessMemory(handle,new IntPtr(address),bytes,length,out read) || read.ToInt64()!=length)throw new IOException("리플레이 기록용 게임 메모리를 읽을 수 없습니다.");return bytes;
        }
        void Write(int address,byte[] bytes) {IntPtr written;if(!WriteProcessMemory(handle,new IntPtr(address),bytes,bytes.Length,out written) || written.ToInt64()!=bytes.Length)throw new IOException("리플레이 입력을 전달할 수 없습니다.");}
        uint U32(int address) {return BitConverter.ToUInt32(Read(address,4),0);}
        void Number(int address,uint value) {Write(address,BitConverter.GetBytes(value));}
        void SetSavePath(string path) {
            byte[] name=Encoding.ASCII.GetBytes(path+"\0");if(name.Length>256)throw new IOException("리플레이 임시 경로가 너무 깁니다.");Write(Box+256,name);
        }
        public void Run() {
            Directory.CreateDirectory(ReplayFiles.Home);
            relative="LauncherReplayWork\\"+Guid.NewGuid().ToString("N");work=Path.Combine(game,relative);Directory.CreateDirectory(work);
            try {
                if(playback) {info=ReplayFiles.Unpack(source,work);ReplayFiles.CheckGame(info,game,executable);reader=new ReplayReader(Path.Combine(work,"commands.bin"));}
                var startup=new Startup {cb=Marshal.SizeOf(typeof(Startup))};ProcessInfo pi;
                if(!CreateProcess(executable,new StringBuilder("\""+executable+"\""),IntPtr.Zero,IntPtr.Zero,false,4,IntPtr.Zero,game,ref startup,out pi))throw new IOException("게임을 실행할 수 없습니다. 오류 "+Marshal.GetLastWin32Error());
                handle=pi.process;
                try {
                    // Verify our mailbox belongs to the exact known patch before activating.
                    if(fixture) {if(Encoding.ASCII.GetString(Read(Box+64,8))!="AGRTEST1")throw new IOException("리플레이 테스트 프로세스 서명이 다릅니다: "+BitConverter.ToString(Read(Box+64,8)));}
                    else if(Core.Hash(executable)!=NativePatch.Load(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"compat","hd-preview.json")).OutputHash)throw new IOException("지원하지 않는 리플레이 실행 파일입니다.");
                    SetSavePath(relative+"\\start.sav");Number(Box,playback?2U:1U);
                    if(ResumeThread(pi.thread)==UInt32.MaxValue)throw new IOException("게임 실행을 재개할 수 없습니다.");
                } catch {TerminateProcess(handle,0xe002);throw;} finally {CloseHandle(pi.thread);}
                while(!Exited) {
                    if(stopRequested) {Result="리플레이 재생을 중단했습니다.";finished=true;TerminateProcess(handle,0);WaitForSingleObject(handle,5000);break;}
                    byte[] state;
                    try {state=Read(Box,36);} catch(IOException) {if(Exited)break;throw;}
                    uint next=BitConverter.ToUInt32(state,4);
                    if(next==request) {
                        if(!finished && BitConverter.ToUInt32(state,32)!=0) {Result="리플레이 기록을 시작하지 못했거나 동기화 대기 시간이 초과되었습니다. 임시 기록은 보존했습니다.";finished=true;}
                        Thread.Sleep(1);continue;
                    }
                    request=next;int kind=BitConverter.ToInt32(state,12);
                    try {Handle(kind);} catch(Exception ex) {
                        if(Exited)break;
                        Result=(playback?"리플레이 재생 중단: ":"자동 기록 중단: ")+ex.Message;Core.Log(Result);
                        Number(Box,playback?3U:0U);finished=true;
                    }
                    try {Number(Box+8,request);}catch(IOException) {if(Exited)break;throw;}
                }
                ChildExitCode=ExitCode;
                if(playback && !finished && ChildExitCode==0xe001)Result="리플레이 동기화 대기 시간이 초과되어 재생을 중단했습니다.";
                if(!finished && !playback && writer!=null) {
                    if(ExitCode==0)FinishRecording();
                    else Result="게임 비정상 종료로 기록이 중단되었습니다. 임시 기록은 LauncherReplayWork 폴더에 보존했습니다.";
                }
                if(String.IsNullOrEmpty(Result))Result=playback?"게임이 종료되어 리플레이 재생을 마쳤습니다.":"게임을 종료했습니다. 기록한 리플레이가 없으면 싱글플레이와 1024×768 모드를 확인해주세요.";
                Core.Log("Replay child exit=0x"+ExitCode.ToString("X8")+" "+Result);
            } finally {
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
                info=new ReplayInfo {ExecutableHash=Core.Hash(executable),DataHash=Core.Hash(Path.Combine(game,"Armageddon.MFP")),IndexHash=Core.Hash(Path.Combine(game,"Armageddon.HED")),CreatedUtc=DateTime.UtcNow.ToString("o")};
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
            if(kind<1 || kind>3)throw new IOException("알 수 없는 리플레이 동기화 이벤트입니다.");
            if(playback) {
                var e=reader.Next();if(e==null)throw new IOException("리플레이 종료 정보가 없습니다.");
                if(e.Kind==0) {EndPlayback();return;}
                if(e.Kind!=kind)throw new IOException("기록과 현재 게임의 명령 처리 순서가 다릅니다.");
                if(kind==1) {
                    if(e.Clock!=U32(0x503c6c))throw new IOException("게임 진행 시간이 기록과 다릅니다.");
                    if(e.Digest!=0 && e.Digest!=Digest())throw new IOException("유닛 위치·체력 상태가 기록과 다릅니다. 다른 전투로 재생하지 않도록 중단했습니다.");
                    frames++;
                }
                Apply(kind,e.Data);
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
            if(kind==2)return Read(0x504d70,64);
            if(kind==3)return Read(0x52f210,1408);
            byte[] result=new byte[2072];Buffer.BlockCopy(Read((int)U32(Box+24)+0x1010,KeyboardSize),0,result,0,KeyboardSize);
            Buffer.BlockCopy(Read((int)U32(Box+28),4),0,result,KeyboardSize,4);Buffer.BlockCopy(Read(0x5812e8,8),0,result,KeyboardSize+4,8);Buffer.BlockCopy(Read((int)U32(Box+36),4),0,result,KeyboardSize+12,4);return result;
        }
        void Apply(int kind,byte[] data) {
            if(kind==2)Write(0x504d70,data);
            else if(kind==3)Write(0x52f210,data);
            else {Write((int)U32(Box+24)+0x1010,data.Take(KeyboardSize).ToArray());Write((int)U32(Box+28),data.Skip(KeyboardSize).Take(4).ToArray());Write(0x5812e8,data.Skip(KeyboardSize+4).Take(8).ToArray());Write((int)U32(Box+36),data.Skip(KeyboardSize+12).ToArray());}
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
        void EndPlayback() {finished=true;Result="리플레이 재생을 완료했습니다.";Number(Box,3);}
        public void Dispose() {
            if(disposed)return;disposed=true;
            if(handle!=IntPtr.Zero)CloseHandle(handle);
        }
    }
}
