using System;
using System.IO;
using System.Text;

namespace Amagadon {
    public static class EditorPatch {
        public const string FileName="ACE.Compat.exe";
        public const string InputHash="a1b1b0464ce5b9af1841973184adb8c9852ed78fbc922b182a1d90933877d507";
        public const string RecipeHash="cefb65523926411e111f43317b361cbf6c03eb4f6f036aeabac5ff167b4e51fc";
        const string PreviousOutputHash="37ba22c6aa857d65588a2c6c7e7959e4c441196faaf8641bb3f3588cb3fcc51b";
        public static bool IsEditor(string name) {return name.Equals("ACE.exe",StringComparison.OrdinalIgnoreCase) || name.Equals(FileName,StringComparison.OrdinalIgnoreCase);}
        public static byte[] Build(byte[] original) {
            using(var stream=System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceStream("Amagadon.EditorRecipe"))
            using(var memory=new MemoryStream()) {
                if(stream==null)throw new IOException("에디터 패치 자료가 없습니다.");
                stream.CopyTo(memory);byte[] recipe=memory.ToArray();
                if(NativePatch.Digest(recipe)!=RecipeHash)throw new IOException("에디터 패치 자료 검증 실패");
                return NativePatch.BuildVerified(original,Core.Json.Deserialize<PatchRecipe>(Encoding.UTF8.GetString(recipe)),InputHash);
            }
        }
        public static string Prepare(string folder) {
            Core.EnsureIdle(folder);
            byte[] patched=Build(File.ReadAllBytes(Path.Combine(folder,"ACE.exe")));
            string dest=Path.Combine(folder,FileName);
            if(File.Exists(dest)) {
                string existing=Core.Hash(dest);
                if(existing==NativePatch.Digest(patched))return dest;
                if(existing!="f3ce6640095b3fa2c4690caccd114b0adf263de543db8d39d149f53d363f6f84" && existing!="189697f5b830c44cc7f67ebf522c903330df74ce675d20b79352f38cd427338f" && existing!=PreviousOutputHash && existing!="cc521decacbd3f902c13fa438260fa2d64070701bfaec77771f51912e76b896b")throw new IOException("기존 ACE.Compat.exe가 변경되었습니다. 파일을 다른 곳으로 옮긴 뒤 다시 실행해주세요.");
            }
            string temp=dest+"."+Guid.NewGuid().ToString("N")+".tmp";
            try {
                File.WriteAllBytes(temp,patched);
                if(File.Exists(dest))File.Replace(temp,dest,dest+"."+Guid.NewGuid().ToString("N")+".bak");
                else File.Move(temp,dest);
            }finally {if(File.Exists(temp))File.Delete(temp);}
            Core.Log("ACE window-scoped GDI presenter prepared: "+NativePatch.Digest(patched));return dest;
        }
    }
}
