"""Generate the original-resolution runtime rally patch from the audited HD hook."""
from pathlib import Path
import sys,re
sys.path.insert(0,'.tools')
from keystone import *
from capstone import *
s=Path('scripts/probe-resolution.py').read_text();base=0x20000000
hooks=[]
for site,offset in [(0x44cf0a,0),(0x44cf5b,128)]:
 match=re.search(r'hook\(0x'+format(site,'x')+r',bytes.fromhex\(\'([^\']+)\'\),"""(.*?)"""',s,re.S)
 code=bytes(Ks(KS_ARCH_X86,KS_MODE_32).asm(match[2],base+offset)[0]);lines=[];last=0
 md=Cs(CS_ARCH_X86,CS_MODE_32);md.detail=True
 for i in md.disasm(code,base+offset):
  if i.mnemonic=='jmp' and i.op_str.startswith('0x4'):
   at=i.address-base-offset
   if at>last:lines.append('c.Hex("'+code[last:at].hex()+'");')
   lines.append('c.Jump("e9",'+i.op_str+');');last=at+len(i.bytes)
 if last<len(code):lines.append('c.Hex("'+code[last:].hex()+'");')
 hooks.append((site,offset,match[1],lines))
header='''using System;using System.Collections.Generic;using System.IO;using System.Linq;using System.Runtime.InteropServices;
namespace Amagadon {
 public static class RallySpawn {
  [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr p,IntPtr address,UIntPtr size,uint type,uint protection);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr p,IntPtr address,byte[] b,int size,out IntPtr read);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool VirtualProtectEx(IntPtr p,IntPtr address,UIntPtr size,uint protection,out uint old);
  public static Dictionary<int,byte[]> Build(int cave) {
   var result=new Dictionary<int,byte[]>();var payload=new byte[1024];
'''
for site,offset,expected,lines in hooks:
 header+='   {var c=new InputRecovery.Code(cave+'+str(offset)+');'+''.join(lines)+'var code=c.Finish();Buffer.BlockCopy(code,0,payload,'+str(offset)+',code.Length);}\n'
 header+='   {byte[] jump=Enumerable.Repeat((byte)0x90,'+str(len(bytes.fromhex(expected)))+').ToArray();jump[0]=0xe9;Buffer.BlockCopy(BitConverter.GetBytes(cave+'+str(offset)+'-'+str(site+5)+'),0,jump,1,4);result.Add('+hex(site)+',jump);}\n'
header+='''   result.Add(cave,payload);return result;
  }
  public static void Apply(IntPtr process,string hash) {
   // Archived replay binaries retain their original behavior. The HD recipe
   // already contains these hooks; only the unmodified 800x600 game needs them.
   if(hash!=NativePatch.InputHash)return;
'''
for site,off,expected,lines in hooks:
 header+='   {byte[] expected=NetworkGuard.Hex("'+expected+'"),actual=new byte[expected.Length];IntPtr n;if(!ReadProcessMemory(process,new IntPtr('+hex(site)+'),actual,actual.Length,out n)||n.ToInt64()!=actual.Length||!actual.SequenceEqual(expected))throw new IOException("랠리 생성 패치 대상 코드가 다릅니다.");}\n'
header+='''   IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,new UIntPtr(4096),0x3000,4);if(memory==IntPtr.Zero)throw new IOException("랠리 생성 패치 할당 실패");
   var edits=Build(memory.ToInt32());NetworkGuard.Write(process,memory.ToInt32(),edits[memory.ToInt32()]);uint old;
   if(!VirtualProtectEx(process,memory,new UIntPtr(4096),0x20,out old))throw new IOException("랠리 생성 패치 보호 설정 실패");
   foreach(var edit in edits)if(edit.Key!=memory.ToInt32())NetworkGuard.Write(process,edit.Key,edit.Value);
   Core.Log("Rally spawn: original 800x600 production now uses rally-facing collision-aware exit search");
  }
 }
}
'''
Path('src/RallySpawn.cs').write_text(header,encoding='utf-8-sig')
