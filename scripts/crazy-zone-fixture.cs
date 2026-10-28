using System;using System.IO;using System.Linq;using System.Net;using System.Threading;using Amagadon;
class ZoneFixture {
 static int Main(string[] args) {try {
  string output=Path.GetFullPath(args[0]);Directory.CreateDirectory(output);
  File.WriteAllText(Path.Combine(output,"patch.json"),Core.Json.Serialize(CrazyZonePatch.Build(0x1000000,"127.0.0.1",19000).Select(e=>new {address=e.Key,bytes=Convert.ToBase64String(e.Value)}).ToArray()));
  using(var server=new CrazyZoneServer(output,"127.0.0.1")) {
   server.Start(IPAddress.Loopback,0);File.WriteAllText(Path.Combine(output,"port.txt"),server.Port.ToString());
   while(!File.Exists(Path.Combine(output,"stop")))Thread.Sleep(50);
  }
  return 0;
 }catch(Exception ex) {File.WriteAllText(Path.Combine(args[0],"error.txt"),ex.ToString());return 1;}}
}
