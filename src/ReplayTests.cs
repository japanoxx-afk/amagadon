using System;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace Amagadon {
    static class ReplayTests {
        static void Check(bool result,string message) {if(!result)throw new Exception("Replay test: "+message);}
        static void Event(BinaryWriter writer,int kind,int size) {writer.Write(kind);writer.Write(0U);writer.Write(0U);writer.Write(size);writer.Write(new byte[size]);}
        public static void ArchiveRun(string source,string game) {
            string root=Path.Combine(Path.GetTempPath(),"AmagadonReplayVerify-"+Guid.NewGuid().ToString("N"));
            try {
                var info=ReplayFiles.Unpack(source,root);ReplayFiles.CheckGame(info,game,Path.Combine(game,NativePatch.FileName));
                Core.Log("REPLAY ARCHIVE VERIFY PASS frames="+info.Frames+" version="+info.Version+"; file structure and game hashes checked; no gameplay launched");
            } finally {if(Directory.Exists(root))Directory.Delete(root,true);}
        }
        public static void ProcessRoundTrip(string fixture) {
            string root=Path.Combine(Path.GetTempPath(),"AmagadonReplayProcess-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
            try {
                File.WriteAllText(Path.Combine(root,"Armageddon.MFP"),"fixture-data");File.WriteAllText(Path.Combine(root,"Armageddon.HED"),"fixture-index");
                string archive;
                using(var recording=new ReplaySession(root,fixture,null,true)) {recording.Run();Check(recording.ChildExitCode==0,"native recording simulation");archive=recording.CreatedReplay;Check(archive!=null && File.Exists(archive),"child recording completed: "+recording.Result);}
                using(var playback=new ReplaySession(root,fixture,archive,true)) {playback.Run();Check(playback.ChildExitCode==0,"native playback simulation");Check(playback.Result=="리플레이 재생을 완료했습니다.","child playback completed: "+playback.Result);}
                string changed=Path.Combine(root,"changed");var info=ReplayFiles.Unpack(archive,changed);Check(info.Format==2,"new recording stores engine RNG format");
                byte[] commands=File.ReadAllBytes(Path.Combine(changed,"commands.bin"));commands[16]^=0x40;
                File.WriteAllBytes(Path.Combine(changed,"commands.bin"),commands);
                string divergent=Path.Combine(root,"divergent.agr");ReplayFiles.Pack(changed,divergent,info);
                using(var playback=new ReplaySession(root,fixture,divergent,true)) {playback.Run();Check(playback.ChildExitCode==0xe001,"desync fail-stop exit");Check(playback.Result.Contains("유닛 위치"),"desync reported");}
                using(var stopped=new ReplaySession(root,fixture,archive,true)) {stopped.RequestStop();stopped.Run();Check(stopped.Result=="리플레이 재생을 중단했습니다.","explicit playback cancellation");}
                string legacyArchive;
                using(var recording=new ReplaySession(root,fixture,null,true,false)) {recording.Run();Check(recording.ChildExitCode==0,"polling recording exit race");legacyArchive=recording.CreatedReplay;Check(legacyArchive!=null,"polling archive completed");}
                using(var playback=new ReplaySession(root,fixture,legacyArchive,true,false)) {playback.Run();Check(playback.ChildExitCode==0 && playback.Result=="리플레이 재생을 완료했습니다.","polling playback exit race");}
                Core.Log("REPLAY PROCESS TEST PASS: kernel events and legacy polling, suspended child activation, snapshot, keyboard/mouse/RNG/command transport, archive finalization, playback, canonical world result");
            } finally {Directory.Delete(root,true);}
        }
        public static void Run() {
            string root=Path.Combine(Path.GetTempPath(),"AmagadonReplay-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
            try {
                string recording=Path.Combine(root,"record");Directory.CreateDirectory(recording);
                File.WriteAllBytes(Path.Combine(recording,"start.sav"),new byte[1024]);
                using(var writer=new BinaryWriter(File.Create(Path.Combine(recording,"commands.bin")))) {
                    writer.Write(Encoding.ASCII.GetBytes("AGRPL001"));
                    Event(writer,1,2072);Event(writer,2,64);Event(writer,3,1408);
                    Event(writer,1,2072);Event(writer,2,64);Event(writer,3,1408);Event(writer,0,0);
                }
                var info=new ReplayInfo {Frames=2,Complete=true,ExecutableHash="test",DataHash="test",IndexHash="test"};
                string archive=Path.Combine(root,"match.agr");ReplayFiles.Pack(recording,archive,info);
                var restored=ReplayFiles.Unpack(archive,Path.Combine(root,"restored"));Check(restored.Frames==2,"round trip");
                Check(ReplayFiles.Inspect(archive).Frames==2,"list metadata round trip");
                byte[] selectionState=new byte[SelectionRuntime.StateSize];
                Buffer.BlockCopy(BitConverter.GetBytes(65),0,selectionState,4,4);
                for(int id=0;id<65;id++)Buffer.BlockCopy(BitConverter.GetBytes((ushort)id),0,selectionState,0x2000+id*2,2);
                File.WriteAllBytes(Path.Combine(recording,"selection.bin"),selectionState);
                info.ControlsVersion=SelectionRuntime.Protocol;
                string extended=Path.Combine(root,"extended.agr");ReplayFiles.Pack(recording,extended,info);
                string extendedRoot=Path.Combine(root,"extended");var extendedInfo=ReplayFiles.Unpack(extended,extendedRoot);
                Check(extendedInfo.ControlsVersion==1 && Core.Hash(Path.Combine(extendedRoot,"selection.bin"))==info.SelectionHash,"extended selection replay round trip");
                bool badSelection=false;byte[] badState=(byte[])selectionState.Clone();badState[0x2002]=0;
                try {SelectionRuntime.ValidateState(badState);}catch(IOException){badSelection=true;}Check(badSelection,"duplicate selection rejected");
                badSelection=false;Buffer.BlockCopy(BitConverter.GetBytes(1701),0,badState,4,4);
                try {SelectionRuntime.ValidateState(badState);}catch(IOException){badSelection=true;}Check(badSelection,"selection count bounds");
                using(var stream=File.Open(extended,FileMode.Open,FileAccess.ReadWrite))using(var zip=new ZipArchive(stream,ZipArchiveMode.Update)) {
                    zip.GetEntry("selection.bin").Delete();using(var output=zip.CreateEntry("selection.bin").Open())output.WriteByte(0);
                }
                badSelection=false;try {ReplayFiles.Unpack(extended,Path.Combine(root,"badSelection"));}catch(IOException){badSelection=true;}Check(badSelection,"selection archive corruption rejected");
                info.ControlsVersion=0;
                string peek=Path.Combine(root,"peek.bin");
                using(var writer=new BinaryWriter(File.Create(peek))) {writer.Write(Encoding.ASCII.GetBytes("AGRPL001"));Event(writer,1,2072);Event(writer,2,64);writer.Write(3);writer.Write(0U);writer.Write(0U);writer.Write(1408);var packet=new byte[1408];packet[64]=0x7a;writer.Write(packet);Event(writer,0,0);}
                using(var input=new ReplayReader(peek)) {var packet=input.PreviousFinalPacket();Check(packet!=null && packet.Length==64 && packet[0]==0x7a,"resolved packet lookahead");Check(input.Next().Kind==1 && input.Next().Kind==2 && input.Next().Kind==3,"lookahead preserves event cursor");Check(input.PreviousFinalPacket()==null,"final frame lookahead terminates");}
                bool rejected=false;try {ReplayFiles.CheckGame(restored,root,Path.Combine(recording,"start.sav"));}catch(IOException){rejected=true;}Check(rejected,"different build rejected");
                Check(ReplayFiles.MapPath(root,"..\\outside.map")==null,"map traversal");Check(ReplayFiles.MapPath(root,"C:\\outside.map")==null,"absolute map path");
                string invalid=Path.Combine(root,"invalid.bin");
                using(var writer=new BinaryWriter(File.Create(invalid))) {writer.Write(Encoding.ASCII.GetBytes("AGRPL001"));Event(writer,1,12);}
                rejected=false;try {using(var reader=new ReplayReader(invalid))reader.Validate(1);}catch(IOException){rejected=true;}Check(rejected,"wrong payload size");
                using(var writer=new BinaryWriter(File.Create(invalid))) {writer.Write(Encoding.ASCII.GetBytes("AGRPL001"));Event(writer,3,1408);Event(writer,0,0);}
                rejected=false;try {using(var reader=new ReplayReader(invalid))reader.Validate(1);}catch(IOException){rejected=true;}Check(rejected,"out of order commands");
                using(var writer=new BinaryWriter(File.Create(invalid))) {writer.Write(Encoding.ASCII.GetBytes("AGRPL001"));Event(writer,1,2072);}
                rejected=false;try {using(var reader=new ReplayReader(invalid))reader.Validate(1);}catch(IOException){rejected=true;}Check(rejected,"incomplete journal");
                string rng=Path.Combine(root,"rng.bin");
                using(var writer=new BinaryWriter(File.Create(rng))) {writer.Write(Encoding.ASCII.GetBytes("AGRPL001"));Event(writer,1,2080);Event(writer,2,72);Event(writer,3,1416);Event(writer,0,0);}
                using(var input=new ReplayReader(rng,2))input.Validate(1);
                string finalCommands=Path.Combine(root,"final-commands.bin");
                using(var writer=new BinaryWriter(File.Create(finalCommands))) {writer.Write(Encoding.ASCII.GetBytes("AGRPL001"));Event(writer,1,2080);Event(writer,2,72);Event(writer,3,1612);Event(writer,0,0);}
                using(var input=new ReplayReader(finalCommands,3))input.Validate(1);
                rejected=false;try {using(var input=new ReplayReader(finalCommands,2))input.Validate(1);}catch(IOException){rejected=true;}Check(rejected,"final command format cannot be read as pre-input packets");
                using(var stream=File.Open(rng,FileMode.Open,FileAccess.Write)) {stream.Position=8+16+2080-8;stream.Write(BitConverter.GetBytes(251U),0,4);}
                rejected=false;try {using(var input=new ReplayReader(rng,2))input.Validate(1);}catch(IOException){rejected=true;}Check(rejected,"engine RNG index bounds");
                rejected=false;try {using(var input=new ReplayReader(rng,1))input.Validate(1);}catch(IOException){rejected=true;}Check(rejected,"format and payload binding");
                string malicious=Path.Combine(root,"traversal.agr");
                using(var stream=File.Create(malicious))using(var zip=new ZipArchive(stream,ZipArchiveMode.Create)) {
                    zip.CreateEntry("../outside");zip.CreateEntry("start.sav");zip.CreateEntry("commands.bin");
                }
                rejected=false;try {ReplayFiles.Unpack(malicious,Path.Combine(root,"bad"));}catch(IOException){rejected=true;}Check(rejected,"archive traversal");Check(!File.Exists(Path.Combine(root,"outside")),"no escaped output");
                File.AppendAllText(Path.Combine(recording,"start.sav"),"tamper");
                using(var stream=File.Open(archive,FileMode.Open,FileAccess.ReadWrite))using(var zip=new ZipArchive(stream,ZipArchiveMode.Update)) {
                    zip.GetEntry("start.sav").Delete();using(var output=zip.CreateEntry("start.sav").Open())output.WriteByte(7);
                }
                rejected=false;try {ReplayFiles.Unpack(archive,Path.Combine(root,"corrupt"));}catch(IOException){rejected=true;}Check(rejected,"checksum corruption");
                using(var input=new MemoryStream(new byte[33]))using(var output=new MemoryStream()) {rejected=false;try {ReplayFiles.CopyBounded(input,output,32);}catch(IOException){rejected=true;}Check(rejected,"decompression cap");}
                Core.Log("REPLAY TEST PASS: round trip, build binding, sizes, command order, completion, traversal, corruption, decompression bounds");
            } finally {Directory.Delete(root,true);}
        }
    }
}
