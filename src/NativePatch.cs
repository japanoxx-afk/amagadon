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
        public const string RecipeHash="e0ddfeaa65f0acde3870579f4f4a233b3f004ddbc0cbc2f94cbcdbb3190e5d47";
        public const string FileName="Armageddon.HD-preview.exe";
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
            if(File.Exists(dest)) {
                if(Core.Hash(dest)!=r.OutputHash)throw new IOException("기존 HD 시험본의 해시가 다릅니다. 파일을 별도 보관한 뒤 다시 실행해주세요.");
                return dest;
            }
            string temporary=dest+"."+Guid.NewGuid().ToString("N")+".tmp";
            try {
                File.WriteAllBytes(temporary,output);
                if(Core.Hash(temporary)!=r.OutputHash)throw new IOException("시험본 파일 쓰기 검증 실패");
                File.Move(temporary,dest);
            } finally {if(File.Exists(temporary))File.Delete(temporary);}
            Core.Log("HD preview created SHA256="+r.OutputHash+"; original unchanged");return dest;
        }
        public static void Remove(string folder,string recipe) {
            Core.EnsureIdle(folder);string file=Path.Combine(folder,FileName);
            if(!File.Exists(file))return;
            if(Core.Hash(file)!=Load(recipe).OutputHash)throw new IOException("시험본의 해시가 달라 자동 제거하지 않았습니다.");
            File.Delete(file);
        }
    }
}
