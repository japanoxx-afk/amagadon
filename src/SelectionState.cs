using System;
using System.IO;
using System.Collections.Generic;

namespace Amagadon {
    public static partial class SelectionRuntime {
        public const int StateSize=0x65000;
        public static void ValidateState(byte[] state) {
            if(state==null || state.Length!=StateSize)throw new IOException("선택 상태 크기가 올바르지 않습니다.");
            for(int player=0;player<9;player++)ValidateList(state,player*4,0x1000+player*4096);
            for(int group=0;group<90;group++)ValidateList(state,0xa000+group*4,0xb000+group*4096);
        }
        static void ValidateList(byte[] state,int countOffset,int listOffset) {
            uint count=BitConverter.ToUInt32(state,countOffset);
            if(count>1700)throw new IOException("선택 상태의 유닛 수가 올바르지 않습니다.");
            var seen=new HashSet<ushort>();
            for(int i=0;i<count;i++) {
                ushort id=BitConverter.ToUInt16(state,listOffset+i*2);
                if(id>=1700 || !seen.Add(id))throw new IOException("선택 상태의 유닛 ID가 올바르지 않습니다.");
            }
        }
        public static byte[] CaptureState(IntPtr process,int cave) {
            if(cave==0)throw new IOException("선택 확장 코드가 설치되지 않았습니다.");
            byte[] state=new byte[StateSize];IntPtr read;
            if(!ReadProcessMemory(process,new IntPtr(cave+0x10000),state,state.Length,out read) || read.ToInt64()!=state.Length)
                throw new IOException("리플레이 선택 상태 읽기 실패");
            ValidateState(state);return state;
        }
        public static void RestoreState(IntPtr process,int cave,byte[] state) {
            if(cave==0)throw new IOException("선택 확장 코드가 설치되지 않았습니다.");
            ValidateState(state);NetworkGuard.Write(process,cave+0x10000,state);
            // The simulation-thread reset hook observes this process's manager
            // for the first time without discarding the restored selection.
            NetworkGuard.Write(process,cave+0x76100,new byte[8]);
        }
    }
}
