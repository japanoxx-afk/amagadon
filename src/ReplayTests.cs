using System;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace Amagadon {
    static class ReplayTests {
        static void Check(bool result,string message) {if(!result)throw new Exception("Replay test: "+message);}
        static void Event(BinaryWriter writer,int kind,int size) {writer.Write(kind);writer.Write(0U);writer.Write(0U);writer.Write(size);writer.Write(new byte[size]);}
        public static void ProcessRoundTrip(string fixture) {
            string root=Path.Combine(Path.GetTempPath(),"AmagadonReplayProcess-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
            try {
                File.WriteAllText(Path.Combine(root,"Armageddon.MFP"),"fixture-data");File.WriteAllText(Path.Combine(root,"Armageddon.HED"),"fixture-index");
                string archive;
                using(var recording=new ReplaySession(root,fixture,null,true)) {recording.Run();Check(recording.ChildExitCode==0,"native recording simulation");archive=recording.CreatedReplay;Check(archive!=null && File.Exists(archive),"child recording completed: "+recording.Result);}
                using(var playback=new ReplaySession(root,fixture,archive,true)) {playback.Run();Check(playback.ChildExitCode==0,"native playback simulation");Check(playback.Result=="리플레이 재생을 완료했습니다.","child playback completed: "+playback.Result);}
                string changed=Path.Combine(root,"changed");var info=ReplayFiles.Unpack(archive,changed);
                byte[] commands=File.ReadAllBytes(Path.Combine(changed,"commands.bin"));commands[16]^=0x40;
                File.WriteAllBytes(Path.Combine(changed,"commands.bin"),commands);
                string divergent=Path.Combine(root,"divergent.agr");ReplayFiles.Pack(changed,divergent,info);
                using(var playback=new ReplaySession(root,fixture,divergent,true)) {playback.Run();Check(playback.ChildExitCode==0xe001,"desync fail-stop exit");Check(playback.Result.Contains("유닛 위치"),"desync reported");}
                using(var stopped=new ReplaySession(root,fixture,archive,true)) {stopped.RequestStop();stopped.Run();Check(stopped.Result=="리플레이 재생을 중단했습니다.","explicit playback cancellation");}
                Core.Log("REPLAY PROCESS TEST PASS: suspended child activation, snapshot, keyboard/mouse/RNG/command transport, archive finalization, playback, canonical world result");
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
                bool rejected=false;try {ReplayFiles.CheckGame(restored,root,Path.Combine(recording,"start.sav"));}catch(IOException){rejected=true;}Check(rejected,"different build rejected");
                Check(ReplayFiles.MapPath(root,"..\\outside.map")==null,"map traversal");Check(ReplayFiles.MapPath(root,"C:\\outside.map")==null,"absolute map path");
                string invalid=Path.Combine(root,"invalid.bin");
                using(var writer=new BinaryWriter(File.Create(invalid))) {writer.Write(Encoding.ASCII.GetBytes("AGRPL001"));Event(writer,1,12);}
                rejected=false;try {using(var reader=new ReplayReader(invalid))reader.Validate(1);}catch(IOException){rejected=true;}Check(rejected,"wrong payload size");
                using(var writer=new BinaryWriter(File.Create(invalid))) {writer.Write(Encoding.ASCII.GetBytes("AGRPL001"));Event(writer,3,1408);Event(writer,0,0);}
                rejected=false;try {using(var reader=new ReplayReader(invalid))reader.Validate(1);}catch(IOException){rejected=true;}Check(rejected,"out of order commands");
                using(var writer=new BinaryWriter(File.Create(invalid))) {writer.Write(Encoding.ASCII.GetBytes("AGRPL001"));Event(writer,1,2072);}
                rejected=false;try {using(var reader=new ReplayReader(invalid))reader.Validate(1);}catch(IOException){rejected=true;}Check(rejected,"incomplete journal");
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
