using System;using System.Collections.Generic;using System.Diagnostics;using System.IO;using System.Linq;using System.Runtime.InteropServices;using System.Text;
namespace Amagadon {
 public static class NetworkGuard {
  public const int Counter=0x475ba8;
  public static int HarvestVolume=100;
  public static bool TraceLogging=true;
  [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Startup {public int cb;public string reserved,desktop,title;public int x,y,cx,cy,xchars,ychars,fill,flags;public short show,reserved2;public IntPtr bytes,input,output,error;}
  [StructLayout(LayoutKind.Sequential)] struct Info {public IntPtr process,thread;public uint pid,tid;}
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(string app,StringBuilder cmd,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref Startup startup,out Info info);
  [DllImport("kernel32.dll")] static extern uint ResumeThread(IntPtr thread);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
  [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr process,uint code);
  [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr p,IntPtr address,UIntPtr length,uint type,uint protect);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool VirtualProtectEx(IntPtr p,IntPtr address,UIntPtr size,uint protect,out uint previous);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr p,IntPtr address,byte[] bytes,int length,out IntPtr read);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool WriteProcessMemory(IntPtr p,IntPtr address,byte[] bytes,int length,out IntPtr written);
  [DllImport("kernel32.dll")] static extern bool FlushInstructionCache(IntPtr p,IntPtr address,UIntPtr length);
  public static byte[] Hex(string text){var b=new byte[text.Length/2];for(int i=0;i<b.Length;i++)b[i]=Convert.ToByte(text.Substring(i*2,2),16);return b;}
  static byte[] Branch(byte opcode,int source,int target,int size){var b=Enumerable.Repeat((byte)0x90,size).ToArray();b[0]=opcode;Buffer.BlockCopy(BitConverter.GetBytes(target-source-5),0,b,1,4);return b;}
  // Public pure builder also feeds the machine-code regression fixture.
  public static Dictionary<int,byte[]> Build(int cave) {
   var edits=new Dictionary<int,byte[]>();var payload=new byte[2048];
   byte[] release=Hex("8b0252ff5008c705d040510000000000c3");Buffer.BlockCopy(release,0,payload,0,release.Length);
   byte[] title=Encoding.ASCII.GetBytes("Armageddon IPX\0"),message=Encoding.ASCII.GetBytes("IPX connection could not be initialized.\r\nDirectPlay or the IPX provider may be unavailable.\r\nThe game will stay in the menu.\r\nRun IPX registration repair in the launcher, then retry.\0");
   Buffer.BlockCopy(title,0,payload,256,title.Length);Buffer.BlockCopy(message,0,payload,320,message.Length);
   int[] sites={0x45c092,0x45c104},returns={0x45c0ae,0x45c120};
   for(int i=0;i<sites.Length;i++) {
    int start=64+i*64;using(var m=new MemoryStream())using(var w=new BinaryWriter(m)) {
     w.Write((byte)0x60);w.Write(Hex("ff05"));w.Write(cave+4096);w.Write(Hex("6a3068"));w.Write(cave+256);w.Write((byte)0x68);w.Write(cave+320);w.Write(Hex("6a00ff1558b24c0061"));
     int branch=cave+start+(int)m.Length;w.Write(Branch(0xe9,branch,returns[i],5));byte[] code=m.ToArray();Buffer.BlockCopy(code,0,payload,start,code.Length);
    }
    edits[sites[i]]=Branch(0xe9,sites[i],cave+start,7);
   }
   // Observe both native lockstep failure paths without changing their decision.
   // Missing history and unequal fingerprints share one lifetime error counter.
   // Keep registers/flags intact; never hide a genuine simulation desync.
   int[] syncSites={0x483b4a,0x483baa};
   for(int i=0;i<syncSites.Length;i++) {
    int start=512+i*192, data=cave+4096;
    using(var m=new MemoryStream())using(var w=new BinaryWriter(m)) {
     w.Write(Hex("9c60ff05"));w.Write(data+8+i*4);
     w.Write(Hex("c705"));w.Write(data+16);w.Write(i+1);
     w.Write(Hex("891d"));w.Write(data+20); // peer slot
     w.Write(Hex("8935"));w.Write(data+24); // history index (50 means absent)
     w.Write(Hex("a3"));w.Write(data+28); // AL: local fingerprint on mismatch path
     w.Write(Hex("890d"));w.Write(data+32); // CL: remote fingerprint on mismatch path
     w.Write(Hex("a16c3c5000a3"));w.Write(data+36); // simulation clock
     w.Write(Hex("0fb605e4a85100a3"));w.Write(data+40);
     w.Write(Hex("0fb60570724e00a3"));w.Write(data+44);
     w.Write(Hex("c1e0060fb7804ef55200a3"));w.Write(data+48);
     w.Write(Branch(0xe8,cave+start+(int)m.Length,cave+1024,5));
     w.Write(Hex("619d803de4a851003c")); // displaced native comparison
     w.Write(Branch(0xe9,cave+start+(int)m.Length,syncSites[i]+7,5));
     byte[] code=m.ToArray();Buffer.BlockCopy(code,0,payload,start,code.Length);
    }
    edits[syncSites[i]]=Branch(0xe9,syncSites[i],cave+start,7);
   }
   // Keep the exact first native comparison operands before later frames overwrite them.
   int snapshot=cave+4096+64;
   var first=new InputRecovery.Code(cave+1024);
   first.Hex("803de4a8510000");first.Branch("0f85","done");
   first.Hex("c705");first.Int(snapshot);first.Int(0);
   first.Hex("a16c3c5000a3");first.Int(snapshot+4);
   first.Hex("a1");first.Int(cave+4096+16);first.Hex("a3");first.Int(snapshot+8);
   first.Hex("891d");first.Int(snapshot+12);first.Hex("8935");first.Int(snapshot+16);
   first.Hex("a1");first.Int(cave+4096+28);first.Hex("a3");first.Int(snapshot+24);
   first.Hex("a1");first.Int(cave+4096+32);first.Hex("a3");first.Int(snapshot+28);
   first.Hex("a1104a5000a3");first.Int(snapshot+32);
   first.Hex("a1");first.Int(cave+4096+48);first.Hex("a3");first.Int(snapshot+20);
   first.Hex("89f5"); // history slot must survive rep movsd
   first.Hex("bf");first.Int(snapshot+64);first.Hex("31c0b930000000fcf3ab");
   first.Hex("0fb60570724e00c1e0060510f552008bf0bf");first.Int(snapshot+64);first.Hex("b910000000f3a5");
   first.Hex("83fd32");first.Branch("0f83","commit");
   first.Hex("833d");first.Int(cave+4096+16);first.Hex("01");first.Branch("0f85","commit");
   first.Hex("6bfb3d03fdc1e70681c7905952008bf7bf");first.Int(snapshot+128);first.Hex("b910000000f3a5");
   first.Label("commit");first.Hex("c705");first.Int(snapshot);first.Int(0x31435953);
   first.Label("done");first.Hex("c3");
   byte[] firstCode=first.Finish();Buffer.BlockCopy(firstCode,0,payload,1024,firstCode.Length);
   edits[cave]=payload;
   foreach(int site in new[]{0x475b31,0x475bc1})edits[site]=Hex("85ff7406803f00909090");
   foreach(int site in new[]{0x475b3e,0x475bce})edits[site]=Branch(0xe8,site,cave,6);
   edits[Counter]=BitConverter.GetBytes(cave+4096);var state=new byte[52];Buffer.BlockCopy(BitConverter.GetBytes(0x53594e31),0,state,4,4);edits[cave+4096]=state;return edits;
  }
  internal static void Write(IntPtr process,int address,byte[] bytes) {
   uint old;IntPtr count;var size=new UIntPtr((uint)bytes.Length);
   if(!VirtualProtectEx(process,new IntPtr(address),size,0x40,out old))throw new IOException("Network guard protection failed");
   try {if(!WriteProcessMemory(process,new IntPtr(address),bytes,bytes.Length,out count) || count.ToInt64()!=bytes.Length || !FlushInstructionCache(process,new IntPtr(address),size))throw new IOException("Network guard write failed");}
   finally {uint ignored;VirtualProtectEx(process,new IntPtr(address),size,old,out ignored);}
  }
  public static int Apply(IntPtr process,string executable,bool extendedSelection=true) {
   string hash=Core.Hash(executable);
   if(hash!=NativePatch.InputHash && !NativePatch.IsPrevious(hash) && hash!="1a3051c992ea27f3b10545f6623642c2071d31070ae54d5e98129f99c9cb6c22")throw new IOException("네트워크 보호 패치가 지원하지 않는 실행 파일입니다.");
   var expected=new Dictionary<int,string>{{0x475b31,"83c9ff33c0f2aef7d149"},{0x475bc1,"83c9ff33c0f2aef7d149"},{0x475b3e,"8b0252ff5008"},{0x475bce,"8b0252ff5008"},{0x45c092,"50ff1564b24c00"},{0x45c104,"50ff1564b24c00"},{Counter,"90909090"}};
   expected[0x483b4a]="803de4a851003c";expected[0x483baa]="803de4a851003c";
   foreach(var item in expected) {byte[] before=Hex(item.Value),actual=new byte[before.Length];IntPtr count;if(!ReadProcessMemory(process,new IntPtr(item.Key),actual,actual.Length,out count) || count.ToInt64()!=actual.Length || !before.SequenceEqual(actual))throw new IOException("네트워크 보호 패치 대상 코드가 다릅니다.");}
   IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,new UIntPtr(8192),0x3000,0x04);if(memory==IntPtr.Zero)throw new IOException("Network guard allocation failed");
   var edits=Build(memory.ToInt32());Write(process,memory.ToInt32(),edits[memory.ToInt32()]);uint previous;if(!VirtualProtectEx(process,memory,new UIntPtr(4096),0x20,out previous))throw new IOException("Network guard executable protection failed");
   foreach(var edit in edits)if(edit.Key!=memory.ToInt32())Write(process,edit.Key,edit.Value);
   InputRecovery.Apply(process);
   FramePacing.Apply(process);
   InGameLayout.Apply(process,hash);
   RallySpawn.Apply(process,hash);
   CrazyZonePatch.Apply(process);
   int selection=extendedSelection?SelectionRuntime.Apply(process,hash):0;
   Core.Log("IPX guard applied before first thread resume: null provider, released pointer, failure menu return; original file unchanged");
   return selection;
  }
  internal static Process TrackProcess(int pid) {
   Process process=Process.GetProcessById(pid);
   try {IntPtr retained=process.Handle;return process;}catch{process.Dispose();throw;}
  }
  public static Process Start(string executable,string folder) {
   var values=new SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase);foreach(System.Collections.DictionaryEntry item in Diagnostics.StartInfo(executable,folder).EnvironmentVariables)values[(string)item.Key]=(string)item.Value;
   IntPtr env=Marshal.StringToHGlobalUni(String.Join("\0",values.Select(v=>v.Key+"="+v.Value))+"\0\0");var startup=new Startup{cb=Marshal.SizeOf(typeof(Startup))};Info info;
   try {if(!CreateProcess(executable,new StringBuilder("\""+executable+"\""),IntPtr.Zero,IntPtr.Zero,false,0x404,env,folder,ref startup,out info))throw new IOException("게임 시작 실패: "+Marshal.GetLastWin32Error());}finally{Marshal.FreeHGlobal(env);}
   Process tracked=null;
   // Retain a managed handle while the native child is still suspended. A PID-only
   // Process loses access to its exit code after WaitForExit closes its temporary
   // handle; it can also race an immediately exiting child after ResumeThread.
   try {Apply(info.process,executable);tracked=TrackProcess((int)info.pid);if(ResumeThread(info.thread)==UInt32.MaxValue)throw new IOException("게임 재개 실패");return tracked;}catch{if(tracked!=null)tracked.Dispose();TerminateProcess(info.process,1);throw;}finally{CloseHandle(info.thread);CloseHandle(info.process);}
  }
 }
}
