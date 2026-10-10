using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;

namespace Amagadon {
    public class ByteEdit { public int Offset; public string Before; public string After; }
    public class PatchRecipe {
        public string Version, InputHash, OutputHash, AppendGzip;
        public int InputLength, OutputLength;
        public bool ReleaseCandidate;
        public ByteEdit[] Edits;
    }
    public static class NativePatch {
        public const string InputHash="34f0bf9ed99fbf3ab88c410a3a52a2f6904e7bc7f5b88fb4ebadc935c2e9b466";
        public const string RecipeHash="a6c614f1085892d0556e0e11cb5bd40addb008efac4dc98e1c4a226a1dfda32c";
        public const string FileName="Armageddon.HD-preview.exe";
        public const string PreviousOutputHash="2e5d6c572858167e1190d1948375f25d8a90abbb3bded3a585fa8fc88904f579";
        public const string PriorOutputHash="98223eeeb25c1a57860acdbfbab4cd06e445e96f831bd92cc9d150fe9a670921";
        public const string WideOutputHash="b0c91cee843f10d718ead02be28b72236cbfcabc3c6471841dfaee9a6a07cc7a";
        public const string LargerOutputHash="99e6b96114bced78e2e8bc6eb42c9f366e8fa148d9d4f482b71064bbbc252931";
        public static bool IsPrevious(string hash) { return hash==PreviousOutputHash || hash==PriorOutputHash || hash==WideOutputHash || hash==LargerOutputHash; }
        public static string Digest(byte[] b) { using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(b)).Replace("-","").ToLowerInvariant(); }
        static byte[] Hex(string s) {
            if(s==null || s.Length%2!=0) throw new IOException("패치 바이트 형식 오류");
            var b=new byte[s.Length/2];for(int i=0;i<b.Length;i++)b[i]=Convert.ToByte(s.Substring(i*2,2),16);return b;
        }
        public static byte[] Build(byte[] original,PatchRecipe r) {
            if(r==null || r.InputHash!=InputHash || r.InputLength!=original.Length || Digest(original)!=InputHash)
                throw new IOException("지원하지 않는 Armageddon.exe입니다. 원본 1.15 파일의 SHA-256이 필요합니다.");
            if(r.OutputLength<original.Length || r.OutputLength>original.Length+4*1024*1024 || r.Edits==null)
                throw new IOException("패치 크기 오류");
            var output=new byte[r.OutputLength];Buffer.BlockCopy(original,0,output,0,original.Length);
            int end=0;
            foreach(var edit in r.Edits) {
                var before=Hex(edit.Before);var after=Hex(edit.After);
                if(before.Length==0 || before.Length!=after.Length || edit.Offset<end || edit.Offset>original.Length-before.Length)
                    throw new IOException("패치 범위 또는 중복 오류");
                for(int i=0;i<before.Length;i++)if(original[edit.Offset+i]!=before[i])throw new IOException("패치 대상 바이트가 다릅니다.");
                Buffer.BlockCopy(after,0,output,edit.Offset,after.Length);end=edit.Offset+after.Length;
            }
            using(var packed=new MemoryStream(Convert.FromBase64String(r.AppendGzip)))
            using(var unzip=new GZipStream(packed,CompressionMode.Decompress)) {
                int pos=original.Length,n;
                while(pos<output.Length && (n=unzip.Read(output,pos,output.Length-pos))>0)pos+=n;
                if(pos!=output.Length || unzip.ReadByte()!=-1)throw new IOException("추가 코드 크기 오류");
            }
            if(Digest(output)!=r.OutputHash)throw new IOException("완성된 시험본의 SHA-256 검증 실패");
            return output;
        }
        public static PatchRecipe Load(string recipe) {
            byte[] bytes;
            if(File.Exists(recipe))bytes=File.ReadAllBytes(recipe);
            else using(var resource=System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceStream("Amagadon.HdPreviewRecipe")) {
                if(resource==null)throw new IOException("고해상도 패치 자료가 없습니다. 전체 런처 패키지를 사용해주세요.");
                using(var memory=new MemoryStream()){resource.CopyTo(memory);bytes=memory.ToArray();}
            }
            if(Digest(bytes)!=RecipeHash)throw new IOException("고해상도 패치 자료가 손상되었습니다.");
            return Core.Json.Deserialize<PatchRecipe>(System.Text.Encoding.UTF8.GetString(bytes));
        }
        public static string Prepare(string folder,string recipe) {
            Core.Validate(folder);Core.EnsureIdle(folder);
            var r=Load(recipe);string source=Path.Combine(folder,"Armageddon.exe"),dest=Path.Combine(folder,FileName);
            byte[] output=Build(File.ReadAllBytes(source),r);
            bool upgrade=false;
            if(File.Exists(dest)) {
                string current=Core.Hash(dest);
                if(current==r.OutputHash)return dest;
                if(!IsPrevious(current))throw new IOException("기존 HD 시험본의 해시가 다릅니다. 파일을 별도 보관한 뒤 다시 실행해주세요.");
                upgrade=true;
            }
            string temporary=dest+"."+Guid.NewGuid().ToString("N")+".tmp";
            try {
                File.WriteAllBytes(temporary,output);
                if(Core.Hash(temporary)!=r.OutputHash)throw new IOException("시험본 파일 쓰기 검증 실패");
                if(upgrade) {
                    string backupFolder=Path.Combine(folder,"LauncherBackups");Directory.CreateDirectory(backupFolder);
                    string backup=Path.Combine(backupFolder,"Armageddon.HD-preview-prior-"+Guid.NewGuid().ToString("N")+".exe");
                    File.Replace(temporary,dest,backup);
                    Core.Log("Previous HD preview backed up; upgraded to "+r.Version);
                } else File.Move(temporary,dest);
            } finally {if(File.Exists(temporary))File.Delete(temporary);}
            Core.Log("HD preview created SHA256="+r.OutputHash+"; original unchanged");return dest;
        }
        public static void Remove(string folder,string recipe) {
            Core.EnsureIdle(folder);string file=Path.Combine(folder,FileName);
            if(!File.Exists(file))return;
            string hash=Core.Hash(file);
            if(hash!=Load(recipe).OutputHash && !IsPrevious(hash))throw new IOException("시험본의 해시가 달라 자동 제거하지 않았습니다.");
            File.Delete(file);
        }
    }
}
