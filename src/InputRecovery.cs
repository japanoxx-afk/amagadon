using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;

namespace Amagadon {
    public static class InputRecovery {
        public const int CounterPointer=0x490998;
        [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr process,IntPtr address,UIntPtr size,uint type,uint protection);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr process,IntPtr address,byte[] bytes,int size,out IntPtr count);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool VirtualProtectEx(IntPtr process,IntPtr address,UIntPtr size,uint protection,out uint previous);
        sealed class Code {
            public readonly MemoryStream Stream=new MemoryStream();readonly BinaryWriter writer;
            readonly int address;readonly Dictionary<string,int> labels=new Dictionary<string,int>();readonly List<Tuple<int,string>> fixups=new List<Tuple<int,string>>();
            public Code(int address) {this.address=address;writer=new BinaryWriter(Stream);}
            public void Hex(string bytes) {writer.Write(NetworkGuard.Hex(bytes));}
            public void Int(int value) {writer.Write(value);}
            public void Label(string name) {labels.Add(name,(int)Stream.Position);}
            public void Jump(string condition,int target) {Hex(condition);int displacement=target-(address+(int)Stream.Position+4);Int(displacement);}
            public void Branch(string condition,string label) {Hex(condition);fixups.Add(Tuple.Create((int)Stream.Position,label));Int(0);}
            public byte[] Finish() {byte[] result=Stream.ToArray();foreach(var f in fixups)Buffer.BlockCopy(BitConverter.GetBytes(labels[f.Item2]-f.Item1-4),0,result,f.Item1,4);return result;}
        }
        static byte[] Detour(int site,int target,int count) {byte[] bytes=Enumerable.Repeat((byte)0x90,count).ToArray();bytes[0]=0xe9;Buffer.BlockCopy(BitConverter.GetBytes(target-site-5),0,bytes,1,4);return bytes;}
        public static readonly Dictionary<int,string> Expected=new Dictionary<int,string> {
            {0x494f33,"480f85f2000000"},
            {0x4906f5,"ff51288b4c24103bce0f84680200003d1e0007807511a1e8275700508b08ff511c89335e5b59c3"},
            {0x4909ac,"6aff"},{0x4909fb,"6aff"},{0x4909af,"ffd785c0754f"},{0x4909fe,"ffd785c074b1"},
            {CounterPointer,"90909090"}
        };
        public static Dictionary<int,byte[]> Build(int cave) {
            int stats=cave+4096;var c=new Code(cave);
            // WA_INACTIVE (0) already took the original loss branch. Accept both
            // WA_ACTIVE (1) and WA_CLICKACTIVE (2), retaining the original acquire/reset path.
            c.Hex("83f802");c.Jump("0f87",0x49502c);c.Hex("ff05");c.Int(stats+24);c.Jump("e9",0x494f3a);
            byte[] focus=c.Finish();
            var m=new Code(cave+128);
            m.Hex("ff5128"); // original GetDeviceData, same 5 stdcall arguments
            m.Hex("ff05");m.Int(stats);m.Hex("a3");m.Int(stats+4);
            m.Hex("3d1e000780");m.Branch("0f84","acquire"); // DIERR_INPUTLOST
            m.Hex("3d0c000780");m.Branch("0f84","acquire"); // DIERR_NOTACQUIRED
            m.Branch("e9","result");
            m.Label("acquire");
            m.Jump("e8",cave+1024);m.Hex("85c0");m.Branch("0f84","failed");
            m.Hex("ff05");m.Int(stats+8);
            m.Hex("a1e827570085c0");m.Branch("0f84","failed");
            m.Hex("8b0850ff511c");m.Hex("a3");m.Int(stats+12);
            m.Hex("85c0");m.Branch("0f88","failed"); // another app has priority: return, never loop
            m.Hex("ff05");m.Int(stats+16);
            m.Hex("c7442410400000008d542410a1e82757008b086a005268d0c356006a1050ff5128");
            m.Hex("a3");m.Int(stats+4);
            m.Label("result");m.Hex("85c0");m.Branch("0f88","failed");
            m.Hex("8b4c241085c9");m.Jump("0f84",0x49096c);m.Jump("e9",0x49071c);
            m.Label("failed");m.Hex("ff05");m.Int(stats+20);
            // On failure the event buffer is undefined. Do not parse stale clicks/motion.
            m.Hex("c7442410000000008933");m.Jump("e9",0x49096c);
            byte[] mouse=m.Finish();
            var w=new Code(cave+512);
            w.Hex("ffd73d02010000");w.Branch("0f85","checked"); // WaitForSingleObject timeout
            w.Hex("ff05");w.Int(stats+28);w.Hex("31c0");
            w.Label("checked");w.Hex("85c0");w.Jump("0f85",0x490a04);
            w.Jump("e8",cave+1024);w.Hex("85c0");w.Jump("0f84",0x4909fb);
            // Restore only the focus-suspension flag, not the engine's deliberate
            // mouse-enable flag. This also covers swallowed activation messages.
            w.Hex("833d5c2b570000");w.Jump("0f84",0x4909b5);
            w.Hex("c7055c2b570000000000ff05");w.Int(stats+40);w.Jump("e9",0x4909b5);
            byte[] wait=w.Finish();var f=new Code(cave+1024);
            // The wrapper can keep the game's old focus flag set while another
            // app is foreground. Resolve in the child; never assume shared DLL addresses.
            f.Hex("a1");f.Int(stats+32);f.Hex("85c0");f.Branch("0f85","resolved");
            f.Hex("68");f.Int(cave+1280);f.Hex("ff1524b14c0085c0");f.Branch("0f84","inactive");
            f.Hex("68");f.Int(cave+1296);f.Hex("50ff159cb04c00a3");f.Int(stats+32);f.Hex("85c0");f.Branch("0f84","inactive");
            f.Label("resolved");f.Hex("ffd03b05502b5700");f.Branch("0f85","inactive");f.Hex("b801000000c3");
            f.Label("inactive");f.Hex("ff05");f.Int(stats+36);f.Hex("31c0c3");
            byte[] foreground=f.Finish();var payload=new byte[1536];
            Buffer.BlockCopy(focus,0,payload,0,focus.Length);Buffer.BlockCopy(mouse,0,payload,128,mouse.Length);Buffer.BlockCopy(wait,0,payload,512,wait.Length);
            Buffer.BlockCopy(foreground,0,payload,1024,foreground.Length);
            Buffer.BlockCopy(System.Text.Encoding.ASCII.GetBytes("user32.dll\0"),0,payload,1280,11);
            byte[] api=System.Text.Encoding.ASCII.GetBytes("GetForegroundWindow\0");Buffer.BlockCopy(api,0,payload,1296,api.Length);
            return new Dictionary<int,byte[]> {
                {cave,payload},{stats,new byte[44]},{CounterPointer,BitConverter.GetBytes(stats)},
                {0x494f33,Detour(0x494f33,cave,7)},{0x4906f5,Detour(0x4906f5,cave+128,39)},
                {0x4909ac,NetworkGuard.Hex("6a64")},{0x4909fb,NetworkGuard.Hex("6a64")},
                {0x4909af,Detour(0x4909af,cave+512,6)},{0x4909fe,Detour(0x4909fe,cave+512,6)}
            };
        }
        public static void Apply(IntPtr process) {
            foreach(var item in Expected) {
                byte[] before=NetworkGuard.Hex(item.Value),actual=new byte[before.Length];IntPtr count;
                if(!ReadProcessMemory(process,new IntPtr(item.Key),actual,actual.Length,out count) || count.ToInt64()!=actual.Length || !before.SequenceEqual(actual))throw new IOException("마우스 입력 복구 패치 대상 코드가 다릅니다.");
            }
            IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,new UIntPtr(8192),0x3000,4);
            if(memory==IntPtr.Zero)throw new IOException("입력 복구 메모리 할당 실패");
            var edits=Build(memory.ToInt32());NetworkGuard.Write(process,memory.ToInt32(),edits[memory.ToInt32()]);uint previous;
            if(!VirtualProtectEx(process,memory,new UIntPtr(4096),0x20,out previous))throw new IOException("입력 복구 코드 보호 설정 실패");
            foreach(var edit in edits)if(edit.Key!=memory.ToInt32())NetworkGuard.Write(process,edit.Key,edit.Value);
            Core.Log("Input recovery applied: click activation, bounded DirectInput reacquire/retry, 100ms notification fallback; counters=0x"+(memory.ToInt32()+4096).ToString("X8"));
        }
    }
}
