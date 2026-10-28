using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;

namespace Amagadon {
    public static class CrazyZonePatch {
        // Set only for a new private-server game, before its first thread runs.
        public static string Address;
        public static int Port=9000;
        [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr p,IntPtr address,UIntPtr size,uint type,uint protect);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr p,IntPtr address,byte[] bytes,int length,out IntPtr read);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool VirtualProtectEx(IntPtr p,IntPtr address,UIntPtr size,uint protect,out uint previous);
        public static void Validate(string address,int port) {
            IPAddress ip;
            if(!IPAddress.TryParse(address,out ip) || ip.AddressFamily!=AddressFamily.InterNetwork || !String.Equals(ip.ToString(),address,StringComparison.Ordinal) || ip.Equals(IPAddress.Any) || ip.Equals(IPAddress.Broadcast) || ip.GetAddressBytes()[0]>=224)
                throw new ArgumentException("접속할 서버의 IPv4 주소를 입력하세요. 같은 PC에서는 127.0.0.1입니다.");
            if(port<1024 || port>65535)throw new ArgumentException("서버 포트는 1024~65535로 입력하세요.");
        }
        public static Dictionary<int,byte[]> Build(int cave,string address,int port) {
            Validate(address,port);
            var code=new byte[256];
            // Server-list getter: exactly one local entry, then NULL. cdecl.
            byte[] getter=NetworkGuard.Hex("837c2404007506b800000000c331c0c3");
            Buffer.BlockCopy(BitConverter.GetBytes(cave+64),0,getter,8,4);
            Buffer.BlockCopy(getter,0,code,0,getter.Length);
            byte[] name=Encoding.ASCII.GetBytes("Amagadon Private Zone\0"),ip=Encoding.ASCII.GetBytes(address+"\0");
            Buffer.BlockCopy(name,0,code,64,name.Length);Buffer.BlockCopy(ip,0,code,128,ip.Length);
            byte[] jump=new byte[5];jump[0]=0xe9;Buffer.BlockCopy(BitConverter.GetBytes(cave-0x497b45),0,jump,1,4);
            byte[] push=new byte[5];push[0]=0x68;Buffer.BlockCopy(BitConverter.GetBytes(cave+128),0,push,1,4);
            return new Dictionary<int,byte[]> {
                {cave,code}, {0x497b40,jump}, {0x497b50,new byte[]{0xc3}},
                {0x4958aa,push}, {0x4eaab8,BitConverter.GetBytes((ushort)port)},
                // The original join builder measures the title twice instead of measuring the password.
                {0x49740f,NetworkGuard.Hex("8bfe")},
                // The defunct patch/list-download service is separate from the lobby.
                {0x4a0390,NetworkGuard.Hex("31c0c3")}
            };
        }
        public static void Apply(IntPtr process) {
            if(Address==null)return;
            Validate(Address,Port);
            var expected=new Dictionary<int,string> {{0x497b40,"8b4424048b"},{0x497b50,"8b"},{0x4958aa,"6808ba5700"},{0x4a0390,"a1502b"},{0x49740f,"8bfb"}};
            foreach(var item in expected) {
                byte[] bytes=NetworkGuard.Hex(item.Value),actual=new byte[bytes.Length];IntPtr read;
                if(!ReadProcessMemory(process,new IntPtr(item.Key),actual,actual.Length,out read) || read.ToInt64()!=actual.Length || !actual.SequenceEqual(bytes))throw new IOException("Crazy Zone 패치 대상 코드가 다릅니다.");
            }
            IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,new UIntPtr(4096),0x3000,4);
            if(memory==IntPtr.Zero)throw new IOException("Crazy Zone 메모리 할당 실패");
            var edits=Build(memory.ToInt32(),Address,Port);
            NetworkGuard.Write(process,memory.ToInt32(),edits[memory.ToInt32()]);uint previous;
            if(!VirtualProtectEx(process,memory,new UIntPtr(4096),0x20,out previous))throw new IOException("Crazy Zone 코드 보호 설정 실패");
            foreach(var edit in edits)if(edit.Key!=memory.ToInt32())NetworkGuard.Write(process,edit.Key,edit.Value);
            Core.Log("Crazy Zone private endpoint="+Address+":"+Port+"; native lobby and DirectPlay TCP gameplay; applied before resume");
        }
    }
}
