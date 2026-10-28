using System;using System.Collections.Generic;using System.Diagnostics;using System.IO;using System.Linq;using System.Runtime.InteropServices;using System.Text;
namespace Amagadon {
 public static class NetworkGuard {
  public const int Counter=0x475ba8;
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
   var edits=new Dictionary<int,byte[]>();var payload=new byte[1024];
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
   edits[cave]=payload;
   foreach(int site in new[]{0x475b31,0x475bc1})edits[site]=Hex("85ff7406803f00909090");
   foreach(int site in new[]{0x475b3e,0x475bce})edits[site]=Branch(0xe8,site,cave,6);
   edits[Counter]=BitConverter.GetBytes(cave+4096);edits[cave+4096]=new byte[4];return edits;
  }
  internal static void Write(IntPtr process,int address,byte[] bytes) {
   uint old;IntPtr count;var size=new UIntPtr((uint)bytes.Length);
   if(!VirtualProtectEx(process,new IntPtr(address),size,0x40,out old))throw new IOException("Network guard protection failed");
   try {if(!WriteProcessMemory(process,new IntPtr(address),bytes,bytes.Length,out count) || count.ToInt64()!=bytes.Length || !FlushInstructionCache(process,new IntPtr(address),size))throw new IOException("Network guard write failed");}
   finally {uint ignored;VirtualProtectEx(process,new IntPtr(address),size,old,out ignored);}
  }
  public static void Apply(IntPtr process,string executable) {
   string hash=Core.Hash(executable);
   if(hash!=NativePatch.InputHash && !NativePatch.IsPrevious(hash) && hash!="1a3051c992ea27f3b10545f6623642c2071d31070ae54d5e98129f99c9cb6c22")throw new IOException("네트워크 보호 패치가 지원하지 않는 실행 파일입니다.");
   var expected=new Dictionary<int,string>{{0x475b31,"83c9ff33c0f2aef7d149"},{0x475bc1,"83c9ff33c0f2aef7d149"},{0x475b3e,"8b0252ff5008"},{0x475bce,"8b0252ff5008"},{0x45c092,"50ff1564b24c00"},{0x45c104,"50ff1564b24c00"},{Counter,"90909090"}};
   foreach(var item in expected) {byte[] before=Hex(item.Value),actual=new byte[before.Length];IntPtr count;if(!ReadProcessMemory(process,new IntPtr(item.Key),actual,actual.Length,out count) || count.ToInt64()!=actual.Length || !before.SequenceEqual(actual))throw new IOException("네트워크 보호 패치 대상 코드가 다릅니다.");}
   IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,new UIntPtr(8192),0x3000,0x04);if(memory==IntPtr.Zero)throw new IOException("Network guard allocation failed");
   var edits=Build(memory.ToInt32());Write(process,memory.ToInt32(),edits[memory.ToInt32()]);uint previous;if(!VirtualProtectEx(process,memory,new UIntPtr(4096),0x20,out previous))throw new IOException("Network guard executable protection failed");
   foreach(var edit in edits)if(edit.Key!=memory.ToInt32())Write(process,edit.Key,edit.Value);
   CrazyZonePatch.Apply(process);
   Core.Log("IPX guard applied before first thread resume: null provider, released pointer, failure menu return; original file unchanged");
  }
  public static Process Start(string executable,string folder) {
   var values=new SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase);foreach(System.Collections.DictionaryEntry item in Diagnostics.StartInfo(executable,folder).EnvironmentVariables)values[(string)item.Key]=(string)item.Value;
   IntPtr env=Marshal.StringToHGlobalUni(String.Join("\0",values.Select(v=>v.Key+"="+v.Value))+"\0\0");var startup=new Startup{cb=Marshal.SizeOf(typeof(Startup))};Info info;
   try {if(!CreateProcess(executable,new StringBuilder("\""+executable+"\""),IntPtr.Zero,IntPtr.Zero,false,0x404,env,folder,ref startup,out info))throw new IOException("게임 시작 실패: "+Marshal.GetLastWin32Error());}finally{Marshal.FreeHGlobal(env);}
   try {Apply(info.process,executable);if(ResumeThread(info.thread)==UInt32.MaxValue)throw new IOException("게임 재개 실패");return Process.GetProcessById((int)info.pid);}catch{TerminateProcess(info.process,1);throw;}finally{CloseHandle(info.thread);CloseHandle(info.process);}
  }
 }
}
