using System;
using System.IO;
using System.Text;

namespace Amagadon {
    public static class EditorPatch {
        public const string FileName="ACE.Compat.exe";
        public const string InputHash="a1b1b0464ce5b9af1841973184adb8c9852ed78fbc922b182a1d90933877d507";
        public const string RecipeHash="3cd9504fde126f39f4a1bbb29c3e94980b3399bade4e5179352f361f38e072ca";
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
                if(Core.Hash(dest)==NativePatch.Digest(patched))return dest;
                throw new IOException("기존 ACE.Compat.exe가 변경되었습니다. 파일을 다른 곳으로 옮긴 뒤 다시 실행해주세요.");
            }
            string temp=dest+"."+Guid.NewGuid().ToString("N")+".tmp";
            try {File.WriteAllBytes(temp,patched);File.Move(temp,dest);}finally {if(File.Exists(temp))File.Delete(temp);}
            Core.Log("ACE window-scoped GDI presenter prepared: "+NativePatch.Digest(patched));return dest;
        }
    }
}
