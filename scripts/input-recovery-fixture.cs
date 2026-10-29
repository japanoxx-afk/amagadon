using System;using System.IO;using System.Linq;using Amagadon;
class InputFixture {static int Main(string[] args) {try {
 File.WriteAllText(args[0],Core.Json.Serialize(InputRecovery.Build(0x1000000).Concat(FramePacing.Build(0x1004000)).Concat(InGameLayout.Build(0x1008000)).Select(e=>new {address=e.Key,bytes=Convert.ToBase64String(e.Value)}).ToArray()));return 0;
}catch(Exception ex){File.WriteAllText(args[0]+".error",ex.ToString());return 1;}}}
