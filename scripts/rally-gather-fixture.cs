using System;using System.IO;using System.Linq;using Amagadon;
class RallyGatherFixture {static void Main(string[] args) {File.WriteAllText(args[0],Core.Json.Serialize(RallySpawn.Build(0x1000000).Select(e=>new {address=e.Key,bytes=Convert.ToBase64String(e.Value)}).ToArray()));}}
