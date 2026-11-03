using System;using System.IO;using System.Reflection;using System.Diagnostics;using System.Runtime.InteropServices;using System.Web.Script.Serialization;using System.Collections;using System.Collections.Generic;
class PositionTraceFixture {
 static void Main(string[] args) {
  string folder=Path.Combine(Path.GetTempPath(),"AmagadonPosition-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(folder);
  IntPtr buffer=Marshal.AllocHGlobal(0x101000);
  try {
   byte[] raw=new byte[0x101000];Action<int,int> w=(o,v)=>Buffer.BlockCopy(BitConverter.GetBytes(v),0,raw,o,4);
   w(0,0x31534f50);w(4,8192);w(8,1);
   for(int seq=1;seq<=8192;seq++) {int o=4096+(seq&8191)*128;w(o,seq);w(o+4,21803);w(o+8,1);w(o+12,236);w(o+16,0x43f550);w(o+20,1931);w(o+24,1926);w(o+28,3755);w(o+96,0x4423d6);w(o+124,seq);}
   // One torn record and one stale generation must not be published.
   w(4096+128+124,0);w(4096+256+8,2);
   Marshal.Copy(raw,0,buffer,raw.Length);
   var assembly=Assembly.LoadFrom(Path.GetFullPath(args[0]));var type=assembly.GetType("Amagadon.Diagnostics",true);
   var capture=type.GetMethod("CapturePositionTrace",BindingFlags.Static|BindingFlags.NonPublic);
   capture.Invoke(null,new object[]{Process.GetCurrentProcess(),folder,unchecked(buffer.ToInt32()-0x5d5000),(uint)1});
   var json=new JavaScriptSerializer {MaxJsonLength=16*1024*1024};
   var doc=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(folder,"position-trace.json")));
   var rows=(ArrayList)doc["records"];
   if(rows.Count!=8190)throw new Exception("Torn/generation filtering failed: "+rows.Count);
   var row=(Dictionary<string,object>)rows[0];
   if(Convert.ToInt32(row["unit"])!=236 || Convert.ToInt32(row["requested"])!=1931 || Convert.ToInt32(row["caller"])!=0x4423d6)throw new Exception("Coordinate record decode failed");
   Console.WriteLine("PASS native process capture: 8190 records, >2MB JSON, torn and stale-generation records rejected");
  } finally {Marshal.FreeHGlobal(buffer);Directory.Delete(folder,true);}
 }
}
