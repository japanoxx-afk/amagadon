
using System;using System.IO;using System.IO.Compression;using System.Linq;using System.Diagnostics;using System.Threading;using System.Runtime.InteropServices;using Amagadon;
class Test {
 [DllImport("kernel32.dll")]static extern uint SetErrorMode(uint flags);
 static void Require(bool b,string s){if(!b)throw new Exception(s);}
 static int Main(string[] args){if(args.Length>0 && args[0]=="child"){SetErrorMode(3);while(!File.Exists(args[1]))Thread.Sleep(50);if(args[2]=="crash")throw new InvalidOperationException("Diagnostic fixture deliberate unhandled exception");return 0;}
 try {string executable=System.Reflection.Assembly.GetExecutingAssembly().Location;string temp=Path.Combine(Path.GetDirectoryName(executable),"diagnostic-fixture-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(temp);
 foreach(string mode in new[]{"clean","crash"}){string gate=Path.Combine(temp,mode+".gate");DateTime start=DateTime.Now;
 using(var p=Process.Start(new ProcessStartInfo(executable,"child \""+gate+"\" "+mode){UseShellExecute=false,CreateNoWindow=true})) {
 Diagnostics.Begin(p.Id,executable,temp,new Settings{DiagnosticLogging=true});string session=null;
 for(int i=0;i<150;i++){session=Directory.GetDirectories(Diagnostics.Home).FirstOrDefault(d=>d.EndsWith("-"+p.Id) && File.Exists(Path.Combine(d,"ready.txt")));if(session!=null)break;Thread.Sleep(100);}
 Require(session!=null,"helper not ready");Require(File.ReadAllText(Path.Combine(session,"ready.txt"))=="attached","debug attach unavailable");File.WriteAllText(gate,"");
 if(!p.WaitForExit(15000)){p.Kill();throw new Exception("Fixture did not exit");}Thread.Sleep(500);
 string log=File.ReadAllText(Path.Combine(session,"events.jsonl"));Require(log.Contains("process-end"),"exit telemetry missing");
 if(mode=="crash"){var dumps=Directory.GetFiles(session,"*.dmp");Require(dumps.Length==1,"dump missing: "+log);using(var r=new BinaryReader(File.OpenRead(dumps[0]))){Require(r.ReadUInt32()==0x504d444d,"bad dump");r.ReadUInt32();uint n=r.ReadUInt32(),dir=r.ReadUInt32();bool exception=false;for(int j=0;j<n;j++){r.BaseStream.Position=dir+j*12;uint kind=r.ReadUInt32();r.ReadUInt32();uint address=r.ReadUInt32();if(kind==6){r.BaseStream.Position=address+8;Require(r.ReadUInt32()==0xe0434352,"dump exception mismatch");exception=true;}}Require(exception,"exception stream missing");}}
 else Require(Directory.GetFiles(session,"*.dmp").Length==0,"clean exit produced dump");
 }}
 string wrapper=Path.Combine(Path.GetDirectoryName(executable),"compat","ddraw.dll");foreach(string f in Core.RequiredFiles)File.WriteAllText(Path.Combine(temp,f),"fixture");File.Copy(wrapper,Path.Combine(temp,"ddraw.dll"));File.WriteAllText(Path.Combine(temp,"ddraw.ini"),"fixture ini");
 using(var lease=new EditorCompatibility(temp)){Require(Core.Hash(Path.Combine(temp,"ddraw.dll"))==EditorCompatibility.WrapperHash,"ACE dedicated wrapper not applied");Require(File.ReadAllText(Path.Combine(temp,"DDrawCompat-ACE.Compat.ini")).Contains("GdiInterops=none"),"ACE GDI interop profile missing");}Require(Core.Hash(Path.Combine(temp,"ddraw.dll"))==Core.Hash(wrapper),"ACE wrapper restore mismatch");
 var interrupted=new EditorCompatibility(temp);EditorCompatibility.Recover(temp);interrupted.Dispose();Require(File.Exists(Path.Combine(temp,"ddraw.dll")),"ACE interruption recovery failed");
 Require(!Diagnostics.StartInfo(Path.Combine(temp,"ACE.exe"),temp).EnvironmentVariables.ContainsKey("__COMPAT_LAYER"),"ACE inherits game DPI flags");
 Require(Diagnostics.StartInfo(Path.Combine(temp,"Armageddon.exe"),temp).EnvironmentVariables["__COMPAT_LAYER"].Contains("HIGHDPIAWARE"),"game DPI profile lost");
 File.WriteAllText(Path.Combine(temp,"ddraw.dll"),"foreign wrapper");File.WriteAllText(Path.Combine(temp,"DDrawCompat-ACE.Compat.ini"),"user editor config");
 using(var lease=new EditorCompatibility(temp)){Require(Core.Hash(Path.Combine(temp,"ddraw.dll"))==EditorCompatibility.WrapperHash,"foreign wrapper swap failed");}
 Require(File.ReadAllText(Path.Combine(temp,"ddraw.dll"))=="foreign wrapper" && File.ReadAllText(Path.Combine(temp,"DDrawCompat-ACE.Compat.ini"))=="user editor config","foreign wrapper/config not restored");
 var changed=new EditorCompatibility(temp);File.WriteAllText(Path.Combine(temp,"ddraw.dll"),"changed during editor");bool refused=false;try{changed.Dispose();}catch(IOException){refused=true;}Require(refused && File.Exists(Path.Combine(temp,".amagadon-editor.json")),"editor changed-file protection failed");
 File.WriteAllBytes(Path.Combine(temp,"ddraw.dll"),EditorCompatibility.WrapperBytes());EditorCompatibility.Recover(temp);
 Require(File.ReadAllText(Path.Combine(temp,"ddraw.dll"))=="foreign wrapper","editor recovery after conflict failed");
 string profile=Core.Profile(new Settings{MouseCompatibility=true});Require(profile.Contains("no_dinput_hook=true"),"mouse compatibility profile missing");Require(Core.Profile(new Settings()).Contains("no_dinput_hook=true"),"default input bypass missing");
 var legacy=Core.Json.Deserialize<Settings>("{\"MouseCompatibility\":false,\"ScreenProfile\":1}");Core.MigrateInput(legacy);Require(legacy.MouseCompatibility && legacy.InputProfile==1,"old input profile not migrated");legacy.MouseCompatibility=false;Core.MigrateInput(legacy);Require(!legacy.MouseCompatibility,"explicit input choice overwritten");
 var detector=new Diagnostics.StallDetector();Require(!detector.Observe(true,367,338,1203,915,false),"initial sample flagged");Require(!detector.Observe(true,367,338,1195,915,false),"single sample flagged");Require(detector.Observe(true,367,338,1956,1025,false),"reported frozen input not detected");Require(!detector.Observe(false,367,338,2000,1000,false),"background flagged");Require(!detector.Observe(true,368,339,2010,1010,false),"moving input flagged");
 string live=Path.Combine(temp,"live-stall");Directory.CreateDirectory(live);using(var self=Process.GetCurrentProcess()){Diagnostics.CaptureStall(self,live);}Require(Directory.GetFiles(live,"stall-*.dmp").Length==1,"live stall dump missing");
 string report=Path.Combine(temp,"report.zip");Diagnostics.Report(temp,report);using(var z=ZipFile.OpenRead(report)){Require(z.GetEntry("report.json")!=null,"report index missing");Require(z.Entries.Any(e=>e.FullName.EndsWith(".dmp")),"report excludes dump");Require(!z.Entries.Any(e=>e.FullName.StartsWith("Replays/")),"report includes replays");}
 File.WriteAllText(Path.Combine(Path.GetDirectoryName(executable),"diagnostic-test-result.txt"),"PASS: crash second-chance exception and minidump exception stream, clean exit, telemetry, ZIP contents, ACE isolation/restore/interruption recovery, input profiles");return 0;
 }catch(Exception ex){File.WriteAllText(Path.Combine(Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location),"diagnostic-test-result.txt"),ex.ToString());return 1;}}
}
