using System;using System.Collections.Generic;using System.IO;using System.Linq;using System.Runtime.InteropServices;
namespace Amagadon {
 public static class RallySpawn {
  [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr p,IntPtr address,UIntPtr size,uint type,uint protection);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr p,IntPtr address,byte[] b,int size,out IntPtr read);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool VirtualProtectEx(IntPtr p,IntPtr address,UIntPtr size,uint protection,out uint old);
  public static Dictionary<int,byte[]> Build(int cave) {
   var result=new Dictionary<int,byte[]>();var payload=new byte[1024];
   {var c=new InputRecovery.Code(cave+0);c.Hex("508b44246889442420588844246488c8");c.Jump("e9",0x44cf10);var code=c.Finish();Buffer.BlockCopy(code,0,payload,0,code.Length);}
   {byte[] jump=Enumerable.Repeat((byte)0x90,6).ToArray();jump[0]=0xe9;Buffer.BlockCopy(BitConverter.GetBytes(cave+0-4509455),0,jump,1,4);result.Add(0x44cf0a,jump);}
   {var c=new InputRecovery.Code(cave+128);c.Hex("894c2444895c24489c6081bc24800000007bf941000f859e0000008b4424403da40600000f838f0000008b0d104a500085c90f84810000008b4c810885c974798b81981300008b919c13000089c309d374672b41142b511889c3c1fb1f31d829d889d6c1fe1f31f229f239d0722385db7810c6442437018b7c24608b74246c4eeb30c6442437038b7c24688b742464eb2185f67810c6442437008b7c24688b74246c4eeb0dc6442437028b7c24608b742464893c2489742404619d");c.Jump("e9",0x44cf63);var code=c.Finish();Buffer.BlockCopy(code,0,payload,128,code.Length);}
   {byte[] jump=Enumerable.Repeat((byte)0x90,8).ToArray();jump[0]=0xe9;Buffer.BlockCopy(BitConverter.GetBytes(cave+128-4509536),0,jump,1,4);result.Add(0x44cf5b,jump);}
   result.Add(cave,payload);return result;
  }
  public static void Apply(IntPtr process,string hash) {
   // Archived replay binaries retain their original behavior. The HD recipe
   // already contains these hooks; only the unmodified 800x600 game needs them.
   if(hash!=NativePatch.InputHash)return;
   {byte[] expected=NetworkGuard.Hex("884424648ac1"),actual=new byte[expected.Length];IntPtr n;if(!ReadProcessMemory(process,new IntPtr(0x44cf0a),actual,actual.Length,out n)||n.ToInt64()!=actual.Length||!actual.SequenceEqual(expected))throw new IOException("랠리 생성 패치 대상 코드가 다릅니다.");}
   {byte[] expected=NetworkGuard.Hex("894c2444895c2448"),actual=new byte[expected.Length];IntPtr n;if(!ReadProcessMemory(process,new IntPtr(0x44cf5b),actual,actual.Length,out n)||n.ToInt64()!=actual.Length||!actual.SequenceEqual(expected))throw new IOException("랠리 생성 패치 대상 코드가 다릅니다.");}
   IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,new UIntPtr(4096),0x3000,4);if(memory==IntPtr.Zero)throw new IOException("랠리 생성 패치 할당 실패");
   var edits=Build(memory.ToInt32());NetworkGuard.Write(process,memory.ToInt32(),edits[memory.ToInt32()]);uint old;
   if(!VirtualProtectEx(process,memory,new UIntPtr(4096),0x20,out old))throw new IOException("랠리 생성 패치 보호 설정 실패");
   foreach(var edit in edits)if(edit.Key!=memory.ToInt32())NetworkGuard.Write(process,edit.Key,edit.Value);
   Core.Log("Rally spawn: original 800x600 production now uses rally-facing collision-aware exit search");
  }
 }
}
