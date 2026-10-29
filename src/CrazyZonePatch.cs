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
            var code=new byte[1024];
            // Server-list getter: exactly one local entry, then NULL. cdecl.
            byte[] getter=NetworkGuard.Hex("837c2404007506b800000000c331c0c3");
            Buffer.BlockCopy(BitConverter.GetBytes(cave+64),0,getter,8,4);
            Buffer.BlockCopy(getter,0,code,0,getter.Length);
            byte[] name=Encoding.ASCII.GetBytes("Amagadon Private Zone\0"),ip=Encoding.ASCII.GetBytes(address+"\0");
            Buffer.BlockCopy(name,0,code,64,name.Length);Buffer.BlockCopy(ip,0,code,128,ip.Length);
            byte[] jump=new byte[5];jump[0]=0xe9;Buffer.BlockCopy(BitConverter.GetBytes(cave-0x497b45),0,jump,1,4);
            byte[] push=new byte[5];push[0]=0x68;Buffer.BlockCopy(BitConverter.GetBytes(cave+128),0,push,1,4);
            // Native DirectPlay join notification marks slot zero active only
            // when another human joins. A private host versus AI has no such event.
            var start=new InputRecovery.Code(cave+160);
            start.Jump("e8",0x474e10);start.Hex("85c0");start.Branch("0f84","check");
            start.Hex("a1883e51003b059c3c5100");start.Branch("0f85","check");
            start.Hex("803d643c510003");start.Branch("0f85","check");
            start.Hex("c605803c510001");
            start.Label("check");start.Jump("e8",0x4754e0);start.Hex("c3");
            byte[] startCode=start.Finish();Buffer.BlockCopy(startCode,0,code,160,startCode.Length);
            byte[] startCall=new byte[5];startCall[0]=0xe8;Buffer.BlockCopy(BitConverter.GetBytes(cave+160-0x466e33),0,startCall,1,4);
            // A no-peer command is already acknowledged, so the native tick
            // clears it without running the network ACK's countdown/start actions.
            var complete=new InputRecovery.Code(cave+256);
            complete.Hex("9c60");complete.Jump("e8",0x474e10);complete.Hex("85c0");complete.Branch("0f84","done");
            complete.Hex("a1883e51003b059c3c5100");complete.Branch("0f85","done");
            complete.Hex("803d643c510003");complete.Branch("0f85","done");
            for(int i=1;i<8;i++) {complete.Hex("803d");complete.Int(0x513c64+i);complete.Hex("03");complete.Branch("0f84","done");}
            complete.Hex("803f02");complete.Branch("0f85","start-game");
            complete.Hex("c60553e7500005");complete.Branch("e9","done");
            complete.Label("start-game");complete.Hex("803f05");complete.Branch("0f85","launch");
            complete.Jump("e8",0x429850);complete.Hex("a3f0bc5000");
            complete.Jump("e8",0x429850);complete.Hex("a3f8bc5000");complete.Branch("e9","done");
            complete.Label("launch");complete.Hex("803f04");complete.Branch("0f85","done");
            // Match the native all-ACK handler at 473062, including the result
            // metadata notification; do not manufacture peer acknowledgements.
            complete.Jump("e8",0x497570);
            complete.Hex("ff357c405100ff35a8405100ff35a4405100");complete.Jump("e8",0x4975a0);complete.Hex("83c40c");
            complete.Jump("e8",0x456520);
            complete.Label("done");complete.Hex("619d558bce");complete.Jump("e8",0x4752c0);complete.Jump("e9",0x47543d);
            byte[] completeCode=complete.Finish();Buffer.BlockCopy(completeCode,0,code,256,completeCode.Length);
            byte[] completeJump=NetworkGuard.Hex("e900000000909090");Buffer.BlockCopy(BitConverter.GetBytes(cave+256-0x47543a),0,completeJump,1,4);
            // Native host quit waits for peer termination even when no peer exists.
            // Use the engine's ordinary end flag; never terminate its process here.
            var quit=new InputRecovery.Code(cave+768);
            quit.Hex("893560a651009c60");
            quit.Hex("a1883e51003b059c3c5100");quit.Branch("0f85","done");
            quit.Hex("803d643c510003");quit.Branch("0f85","done");
            for(int i=1;i<8;i++){quit.Hex("803d");quit.Int(0x513c64+i);quit.Hex("03");quit.Branch("0f84","done");}
            quit.Hex("c705f47b500001000000");
            quit.Label("done");quit.Hex("619d");quit.Jump("e9",0x483d2a);
            byte[] quitCode=quit.Finish();Buffer.BlockCopy(quitCode,0,code,768,quitCode.Length);
            byte[] quitJump=NetworkGuard.Hex("e90000000090");Buffer.BlockCopy(BitConverter.GetBytes(cave+768-0x483d29),0,quitJump,1,4);
            return new Dictionary<int,byte[]> {
                {0x483d24,quitJump},
                {0x475435,completeJump},
                // Keep cancel reachable while still in the idle (6) state.
                // Its original countdown/state guard and orderly leave stay intact.
                {0x466e7b,NetworkGuard.Hex("909090909090")},
                {0x466e2e,startCall},
                {cave,code}, {0x497b40,jump}, {0x497b50,new byte[]{0xc3}},
                {0x4958aa,push}, {0x4eaab8,BitConverter.GetBytes((ushort)port)},
                // The original join builder measures the title twice instead of measuring the password.
                {0x49740f,NetworkGuard.Hex("8bfe")},
                // Private accounts belong to our lobby. The original registration
                // preflight and post-success notification contact a separate legacy
                // service; its response wait has no timeout (48e5f0).
                // Keep caller argument cleanup and native ID/password validation.
                {0x495637,NetworkGuard.Hex("31c0909090")},
                {0x49583f,NetworkGuard.Hex("31c0909090")},
                // The defunct patch/list-download service is separate from the lobby.
                {0x4a0390,NetworkGuard.Hex("31c0c3")}
            };
        }
        public static void Apply(IntPtr process) {
            if(Address==null)return;
            Validate(Address,Port);
            var expected=new Dictionary<int,string> {{0x483d24,"893560a65100"},{0x466e7b,"89b09c010000"},{0x475435,"558bcee883feffff"},{0x466e2e,"e8ade60000"},{0x497b40,"8b4424048b"},{0x497b50,"8b"},{0x4958aa,"6808ba5700"},{0x4a0390,"a1502b"},{0x49740f,"8bfb"},{0x495637,"e88487ffff"},{0x49583f,"e83c87ffff"}};
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
