using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;

namespace Amagadon {
    // Runtime layout fixes for the supported HD recipe; game files stay unchanged.
    public static class InGameLayout {
        [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr p,IntPtr address,UIntPtr size,uint type,uint protection);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool ReadProcessMemory(IntPtr p,IntPtr address,byte[] b,int size,out IntPtr read);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool VirtualProtectEx(IntPtr p,IntPtr address,UIntPtr size,uint protection,out uint old);
        // Only the current 1024x768 recipe uses this HUD anchor. Original files
        // remain untouched, including their save/load text-entry coordinates.
        public static Dictionary<int,byte[]> Build(int cave) {
            var c=new InputRecovery.Code(cave);
            // Stack: return, RECT*, left, top, right, bottom.
            c.Hex("50" ); // preserve EAX
            c.Hex("8b44240883e810");
            foreach(int pointer in new[]{0x507bb0,0x507bc8,0x507bcc,0x507bd0,0x507bd4}) {
                c.Hex("3b05");c.Int(pointer);c.Branch("0f84","shift");
            }
            c.Branch("e9","rect");
            c.Label("shift");
            c.Hex("8344240c70834424105483442414708344241854");
            c.Label("rect");c.Hex("58ff2554b24c00");
            byte[] rect=c.Finish();var payload=new byte[2048];Buffer.BlockCopy(rect,0,payload,0,rect.Length);
            var text=new InputRecovery.Code(cave+256);
            // thiscall message list: return, x, y, line spacing, colour.
            text.Hex("83442404708344240854");text.Jump("e9",0x4710f0);
            byte[] message=text.Finish();Buffer.BlockCopy(message,0,payload,256,message.Length);
            byte[] load=NetworkGuard.Hex("be0000000090");Buffer.BlockCopy(BitConverter.GetBytes(cave),0,load,1,4);
            byte[] call=NetworkGuard.Hex("e800000000");Buffer.BlockCopy(BitConverter.GetBytes(cave+256-0x4a6122),0,call,1,4);
            // Production complete and similar status banners use a separate shadowed helper.
            var banner=new InputRecovery.Code(cave+320);
            banner.Hex("834424047081442408a8000000");banner.Jump("e9",0x4a8720);
            Copy(payload,320,banner.Finish());
            // Scoreboard assets and hit rectangles are authored at 800x600.
            // Compose the whole board at that size, then stretch it once to the
            // actual primary surface. Convert only this loop's mouse sample.
            var mouse=new InputRecovery.Code(cave+384);
            mouse.Hex("568b74240856");mouse.Jump("e8",0x490ea0);
            mouse.Hex("6b0619c1f80589066b460419c1f8058946045ec20400");
            Copy(payload,384,mouse.Finish());
            var background=new InputRecovery.Code(cave+448);
            background.Hex("6a0068000000016a005268");background.Int(cave+1536);
            background.Hex("57ff5114");background.Jump("e9",0x4a9b78);
            Copy(payload,448,background.Finish());
            var present=new InputRecovery.Code(cave+512);
            present.Hex("83ec08c7059029570001000000568bf18b0d582b5700");present.Jump("e8",0x490e90);
            present.Hex("85c0");present.Branch("0f84","blit");
            present.Hex("8b4e1c8d44240450");present.Jump("e8",0x490e50);
            present.Hex("6b4c240819c1f9056b54240419c1fa05a18029570068580200006820030000515250");
            present.Jump("e8",0x4916b0);present.Hex("83c414");
            present.Label("blit");present.Hex("a1742957008b15802957006a0068000000018b0868");present.Int(cave+1536);
            present.Hex("526a0050ff5114a18029570050");present.Jump("e8",0x4919a0);present.Hex("83c404");
            present.Jump("e8",0x491be0);present.Hex("c70590295700000000005e83c408c3");
            Copy(payload,512,present.Finish());
            // Briefing container uses seven stdcall arguments; translate its
            // common child origin temporarily, restoring serialized coordinates.
            var briefing=new InputRecovery.Code(cave+1280);
            briefing.Hex("558bec5356578bf18b7e108b5e148346107083461454");
            for(int i=6;i>=0;i--)briefing.Hex("ff75"+(8+i*4).ToString("x2"));
            briefing.Jump("e8",0x49eb80);
            briefing.Hex("897e10895e145f5e5b5dc21c00");
            Copy(payload,1280,briefing.Finish());
            Copy(payload,1536,NetworkGuard.Hex("00000000000000002003000058020000"));
            // Upgrade/transform progress uses palette fill, unlike production fill.
            Copy(payload,800,Progress(cave+800,0x48f230,3,1));
            Copy(payload,1024,Progress(cave+1024,0x48f540,4,2));
            return new Dictionary<int,byte[]> {{cave,payload},{0x4a60cc,Call(0x4a60cc,cave+1280)},{0x46d95e,load},{0x4a611d,call},
                {0x4a5c9d,Call(0x4a5c9d,cave+320)}, {0x4a9b31,Call(0x4a9b31,cave+384)},
                {0x4a6a50,Call(0x4a6a50,cave+800)}, {0x4a6be5,Call(0x4a6be5,cave+800)},
                {0x4a6d44,Call(0x4a6d44,cave+800)}, {0x4a6a9e,Call(0x4a6a9e,cave+1024)},
                {0x4a6c33,Call(0x4a6c33,cave+1024)}, {0x4aa157,Call(0x4aa157,cave+512)}, {0x4a9b68,Jump(0x4a9b68,cave+448,16)}};
        }
        static byte[] Progress(int address,int target,int count,int rectIndex) {
            var c=new InputRecovery.Code(address);
            c.Hex("538bdc83ec108b43");c.Hex((8+rectIndex*4).ToString("x2"));
            for(int i=0;i<4;i++) {
                c.Hex("8b48"+ (i*4).ToString("x2") + "81c1");c.Int(i%2==0?112:168);
                c.Hex("894b"+((byte)(240+i*4)).ToString("x2"));
            }
            for(int i=count-1;i>=0;i--) {
                if(i==rectIndex)c.Hex("8d43f050");
                else c.Hex("ff73"+(8+i*4).ToString("x2"));
            }
            c.Jump("e8",target);c.Hex("83c4"+(16+count*4).ToString("x2")+"5bc3");return c.Finish();
        }
        static void Copy(byte[] target,int offset,byte[] bytes){Buffer.BlockCopy(bytes,0,target,offset,bytes.Length);}
        static byte[] Jump(int site,int target,int size){byte[] b=Enumerable.Repeat((byte)0x90,size).ToArray();b[0]=0xe9;Copy(b,1,BitConverter.GetBytes(target-site-5));return b;}
        static byte[] Call(int site,int target){byte[] b=Jump(site,target,5);b[0]=0xe8;return b;}
        public static void Apply(IntPtr process,string hash) {
            if(hash!="1a3051c992ea27f3b10545f6623642c2071d31070ae54d5e98129f99c9cb6c22")return;
            foreach(var entry in new Dictionary<int,string>{{0x4a60cc,"e8af8affff"},{0x46d95e,"8b3554b24c00"},{0x4a611d,"e8ceaffcff"},{0x4a6a50,"e8db87feff"},{0x4a6be5,"e84686feff"},{0x4a6d44,"e8e784feff"},{0x4a6a9e,"e89d8afeff"},{0x4a6c33,"e80889feff"},{0x4a5c9d,"e87e2a0000"},{0x4a9b31,"e86a73feff"},{0x4aa157,"e83481feff"},{0x4a9b68,"6a0068000000016a00526a0057ff5114"}}) {
                byte[] expected=NetworkGuard.Hex(entry.Value),actual=new byte[expected.Length];IntPtr n;
                if(!ReadProcessMemory(process,new IntPtr(entry.Key),actual,actual.Length,out n)||n.ToInt64()!=actual.Length||!actual.SequenceEqual(expected))throw new IOException("게임 UI 패치 대상 코드가 다릅니다.");
            }
            IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,new UIntPtr(4096),0x3000,4);
            if(memory==IntPtr.Zero)throw new IOException("게임 UI 패치 메모리 할당 실패");
            var edits=Build(memory.ToInt32());NetworkGuard.Write(process,memory.ToInt32(),edits[memory.ToInt32()]);uint previous;
            if(!VirtualProtectEx(process,memory,new UIntPtr(4096),0x20,out previous))throw new IOException("게임 UI 패치 보호 설정 실패");
            foreach(var edit in edits)if(edit.Key!=memory.ToInt32())NetworkGuard.Write(process,edit.Key,edit.Value);
            Core.Log("In-game layout: HUD notifications +112,+168; production banner +112,+168; F10/confirmation +112,+84; score composition 800x600 stretched to full surface with matching mouse/cursor mapping");
        }
    }
}
