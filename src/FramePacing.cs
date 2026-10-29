using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;

namespace Amagadon {
    // Yield only inside the engine's existing deadline wait. Keep its clock,
    // interval and unsigned deadline comparison, including timer wraparound.
    public static class FramePacing {
        public const int Site=0x482dfe;
        [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr p,IntPtr address,UIntPtr size,uint type,uint protection);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr p,IntPtr address,byte[] b,int size,out IntPtr read);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool VirtualProtectEx(IntPtr p,IntPtr address,UIntPtr size,uint protection,out uint old);
        public static Dictionary<int,byte[]> Build(int cave) {
            var c=new InputRecovery.Code(cave);
            c.Jump("e8",0x429850);
            c.Hex("8bd02b15f8bc50003b1564bc5000"); // elapsed = now - last; unsigned elapsed >= interval
            c.Branch("0f83","ready");
            // Sleep(0) offers the current timeslice to ready threads, without
            // imposing a 1/15ms sleep that could slow the simulation deadline.
            c.Hex("6a00ff15fcb04c00");
            c.Jump("e8",0x429850);
            c.Label("ready");c.Hex("c3");
            byte[] call=new byte[5];call[0]=0xe8;Buffer.BlockCopy(BitConverter.GetBytes(cave-Site-5),0,call,1,4);
            return new Dictionary<int,byte[]> {{cave,c.Finish()},{Site,call}};
        }
        public static void Apply(IntPtr process) {
            byte[] expected=NetworkGuard.Hex("e84d6afaff"),actual=new byte[5];IntPtr n;
            if(!ReadProcessMemory(process,new IntPtr(Site),actual,5,out n)||n.ToInt64()!=5||!actual.SequenceEqual(expected))throw new IOException("프레임 대기 패치 대상 코드가 다릅니다.");
            IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,new UIntPtr(4096),0x3000,4);
            if(memory==IntPtr.Zero)throw new IOException("프레임 대기 패치 메모리 할당 실패");
            var edits=Build(memory.ToInt32());NetworkGuard.Write(process,memory.ToInt32(),edits[memory.ToInt32()]);uint previous;
            if(!VirtualProtectEx(process,memory,new UIntPtr(4096),0x20,out previous))throw new IOException("프레임 대기 패치 보호 설정 실패");
            NetworkGuard.Write(process,Site,edits[Site]);
            Core.Log("Frame pacing: yield ready threads during native deadline wait; native game speed and deadline unchanged");
        }
    }
}
