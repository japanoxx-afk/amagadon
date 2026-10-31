using System;
using System.IO;
using System.Text;
using System.Collections.Generic;

namespace Amagadon {
    // Keep the original archive payload intact. Only the directory switches to
    // the appended, verified resources, after both writes have reached disk.
    public static class TerrainPatch {
        const int Header=276, Stride=13188;
        const string OriginalMs="095f2f1ced76a11b6434ed0ea2ddfbd1da788650627a9ff28b8151da2e882cc6";
        const string OriginalPi="e0d3b0ef5b5f061ab971f7fa886bc60055a9a7148491a900280fd68f6b883c1b";
        public const string PatchedMs="6985b057074006bd07fe714d9d797cc33e890a030082069c7c3f88abc7d820e8";
        public const string PatchedPi="87bc98a1fff88a006b8b1ef0969f747a760d8c734977509d39ad02a5c6f022a9";
        static void Put16(byte[] a,int p,int v) {a[p]=(byte)v;a[p+1]=(byte)(v>>8);}
        static void Put32(byte[] a,int p,long v) {if(v<0 || v>uint.MaxValue)throw new IOException("지형 아카이브 크기 초과");Buffer.BlockCopy(BitConverter.GetBytes((uint)v),0,a,p,4);}
        static void Check(bool ok,string message) {if(!ok)throw new IOException(message);}
        public static byte[][] Build(byte[] ms,byte[] pi) {
            Check(NativePatch.Digest(ms)==OriginalMs && NativePatch.Digest(pi)==OriginalPi,"지원하지 않는 지구 지형 자료입니다. 원본을 보존하기 위해 적용을 중단합니다.");
            byte[] result=(byte[])ms.Clone();var pixels=new List<byte>(pi);var tiles=new Dictionary<int,int>();
            for(int direction=0;direction<2;direction++) {
                int source=direction==0?15:14,slot=57+direction;
                byte[] record=new byte[Stride];Buffer.BlockCopy(ms,Header+source*Stride,record,0,Stride);
                byte[] old=(byte[])record.Clone();
                foreach(int grid in new int[]{0,0x68,0xd0,0x138})
                    for(int x=0;x<8;x++)for(int y=0;y<6;y++)record[grid+x*13+y]=old[grid+(7-x)*13+5-y];
                Array.Clear(record,0x1b2,30);byte[] name=Encoding.GetEncoding(949).GetBytes(direction==0?"언덕경사-10시":"언덕경사-2시");Buffer.BlockCopy(name,0,record,0x1b2,name.Length);
                record[0x1d2]=old[0x1d3];record[0x1d3]=old[0x1d2];
                for(int x=0;x<8;x++)for(int y=0;y<6;y++)for(int variant=0;variant<15;variant++)for(int frame=0;frame<4;frame++) {
                    int target=0x1d4+((x*13+y)*15+variant)*8+frame*2;
                    int src=0x1d4+(((7-x)*13+5-y)*15+variant)*8+frame*2;
                    int index=BitConverter.ToUInt16(old,src),mapped;
                    if(index==65535)mapped=index;
                    else if(!tiles.TryGetValue(index,out mapped)) {
                        Check(index<BitConverter.ToUInt16(pi,18),"지형 타일 범위 오류");
                        mapped=(pixels.Count-24)/1024;Check(mapped<10000,"지형 타일 한도 초과");tiles.Add(index,mapped);
                        for(int i=1023;i>=0;i--)pixels.Add(pi[24+index*1024+i]);
                    }
                    Put16(record,target,mapped);
                }
                Buffer.BlockCopy(record,0,result,Header+slot*Stride,Stride);
            }
            byte[] output=pixels.ToArray();Put16(output,18,(output.Length-24)/1024);
            Check(NativePatch.Digest(result)==PatchedMs && NativePatch.Digest(output)==PatchedPi,"지형 생성 결과 검증 실패");
            return new byte[][]{result,output};
        }
        static int Find(byte[] hed,string name) {
            Check(hed.Length>=8,"지형 목록 헤더 오류");uint count=BitConverter.ToUInt32(hed,4);
            Check(count<=100000 && hed.Length==8L+count*72L,"지형 목록 크기 오류");
            byte[] key=Encoding.ASCII.GetBytes(name);int found=-1;
            for(int i=0;i<(int)count;i++) {
                int p=8+i*72;bool match=true;
                for(int j=0;j<key.Length;j++)if(char.ToUpperInvariant((char)hed[p+4+j])!=char.ToUpperInvariant((char)key[j])){match=false;break;}
                if(match){Check(found<0,"지형 항목 중복");found=p;}
            }
            Check(found>=0,"지형 항목 없음: "+name);return found;
        }
        static byte[] Read(FileStream archive,byte[] hed,int p) {
            long offset=BitConverter.ToUInt32(hed,p),size=BitConverter.ToUInt32(hed,p+68);
            Check(size<=16000000 && offset+size<=archive.Length,"지형 자료 범위 오류");
            byte[] bytes=new byte[(int)size];archive.Position=offset;int got=0;
            while(got<bytes.Length){int n=archive.Read(bytes,got,bytes.Length-got);Check(n>0,"지형 자료 읽기 실패");got+=n;}return bytes;
        }
        public static void Prepare(string folder) {
            Core.EnsureIdle(folder);
            string directory=Path.Combine(folder,"Armageddon.HED"),payload=Path.Combine(folder,"Armageddon.MFP");
            string temp=directory+"."+Guid.NewGuid().ToString("N")+".tmp";
            try {
                // The exclusive payload handle also serializes competing installers.
                using(var archive=new FileStream(payload,FileMode.Open,FileAccess.ReadWrite,FileShare.None)) {
                    byte[] hed=File.ReadAllBytes(directory);int m=Find(hed,"Data\\Earth.ms"),p=Find(hed,"Data\\Earth.pi");
                    byte[] ms=Read(archive,hed,m),pi=Read(archive,hed,p);
                    if(NativePatch.Digest(ms)==PatchedMs && NativePatch.Digest(pi)==PatchedPi)return;
                    byte[][] output=Build(ms,pi);byte[] changed=(byte[])hed.Clone();
                    archive.Position=archive.Length;
                    for(int i=0;i<2;i++){int entry=i==0?m:p;Put32(changed,entry,archive.Position);Put32(changed,entry+68,output[i].Length);archive.Write(output[i],0,output[i].Length);}
                    archive.Flush(true);
                    using(var staged=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None)){staged.Write(changed,0,changed.Length);staged.Flush(true);}
                    Check(NativePatch.Digest(File.ReadAllBytes(directory))==NativePatch.Digest(hed),"적용 중 지형 목록이 변경되었습니다.");
                    string backups=Path.Combine(folder,"LauncherBackups");Directory.CreateDirectory(backups);
                    File.Replace(temp,directory,Path.Combine(backups,"Terrain-"+DateTime.UtcNow.ToString("yyyyMMdd-HHmmss")+"-"+Guid.NewGuid().ToString("N")+".HED"));
                }
                Core.Log("Earth terrain: installed reverse ramps 57/58; original payload preserved, HED backed up.");
            }finally {if(File.Exists(temp))File.Delete(temp);}
        }
        // Old recordings may keep their exact original data hash: the only
        // accepted difference is our verified append-only extension of empty slots.
        public static bool MatchesOriginalArchive(string folder,string indexHash,string dataHash) {
            try {
                byte[] hed=File.ReadAllBytes(Path.Combine(folder,"Armageddon.HED"));int m=Find(hed,"Data\\Earth.ms"),p=Find(hed,"Data\\Earth.pi");
                using(var archive=File.OpenRead(Path.Combine(folder,"Armageddon.MFP"))) {
                    if(NativePatch.Digest(Read(archive,hed,m))!=PatchedMs || NativePatch.Digest(Read(archive,hed,p))!=PatchedPi)return false;
                    long originalLength=BitConverter.ToUInt32(hed,m);
                    if(BitConverter.ToUInt32(hed,p)!=originalLength+BitConverter.ToUInt32(hed,m+68) || archive.Length!=BitConverter.ToUInt32(hed,p)+(long)BitConverter.ToUInt32(hed,p+68))return false;
                    bool knownIndex=false;string backups=Path.Combine(folder,"LauncherBackups");
                    if(!Directory.Exists(backups))return false;
                    foreach(string backup in Directory.GetFiles(backups,"Terrain-*.HED")) {
                        byte[] old=File.ReadAllBytes(backup);if(NativePatch.Digest(old)!=indexHash || old.Length!=hed.Length)continue;
                        Buffer.BlockCopy(hed,m,old,m,4);Buffer.BlockCopy(hed,m+68,old,m+68,4);Buffer.BlockCopy(hed,p,old,p,4);Buffer.BlockCopy(hed,p+68,old,p+68,4);
                        if(NativePatch.Digest(old)==NativePatch.Digest(hed)){knownIndex=true;break;}
                    }
                    if(!knownIndex)return false;
                    archive.Position=0;using(var sha=System.Security.Cryptography.SHA256.Create()) {
                        byte[] buffer=new byte[65536];long remaining=originalLength;
                        while(remaining>0){int n=archive.Read(buffer,0,(int)Math.Min(buffer.Length,remaining));if(n==0)return false;sha.TransformBlock(buffer,0,n,null,0);remaining-=n;}
                        sha.TransformFinalBlock(new byte[0],0,0);return BitConverter.ToString(sha.Hash).Replace("-","").ToLowerInvariant()==dataHash;
                    }
                }
            }catch(IOException){return false;}
        }
    }
}
