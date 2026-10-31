using System;
using System.IO;
using Amagadon;
class TerrainTest {
    static void Assert(bool ok,string label){if(!ok)throw new Exception(label);}
    static void Main(string[] args) {
        string dir=Path.Combine(Path.GetDirectoryName(typeof(TerrainTest).Assembly.Location),"terrain-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(dir);
        foreach(string name in new[]{"Armageddon.HED","Armageddon.MFP"})File.Copy(Path.Combine(args[0],name),Path.Combine(dir,name));
        string hed=Path.Combine(dir,"Armageddon.HED"),mfp=Path.Combine(dir,"Armageddon.MFP");byte[] oldHed=File.ReadAllBytes(hed),oldMfp=File.ReadAllBytes(mfp);
        TerrainPatch.Prepare(dir);byte[] newHed=File.ReadAllBytes(hed),newMfp=File.ReadAllBytes(mfp);
        Assert(newMfp.Length>oldMfp.Length,"appended assets");
        for(int i=0;i<oldMfp.Length;i++)Assert(oldMfp[i]==newMfp[i],"original payload changed");
        int changed=0;
        for(int p=8;p<oldHed.Length;p+=72){bool different=false;for(int j=0;j<72;j++)if(oldHed[p+j]!=newHed[p+j]){different=true;Assert(j<4 || j>=68,"entry name changed");}if(different)changed++;}
        Assert(changed==2,"only two directory entries");
        Assert(TerrainPatch.MatchesOriginalArchive(dir,NativePatch.Digest(oldHed),NativePatch.Digest(oldMfp)),"original replay compatibility");
        Assert(!TerrainPatch.MatchesOriginalArchive(dir,NativePatch.Digest(oldHed),new string('0',64)),"foreign replay rejection");
        string[] backups=Directory.GetFiles(Path.Combine(dir,"LauncherBackups"));Assert(backups.Length==1 && Core.Hash(backups[0])==NativePatch.Digest(oldHed),"backup");
        string h=Core.Hash(hed),m=Core.Hash(mfp);TerrainPatch.Prepare(dir);Assert(Core.Hash(hed)==h && Core.Hash(mfp)==m,"idempotency");
        using(var f=new FileStream(mfp,FileMode.Open,FileAccess.Write)){f.Position=oldMfp.Length;f.WriteByte(0);}
        h=Core.Hash(hed);m=Core.Hash(mfp);bool rejected=false;try{TerrainPatch.Prepare(dir);}catch(IOException){rejected=true;}
        Assert(rejected && Core.Hash(hed)==h && Core.Hash(mfp)==m,"modified resource rejection");
        Assert(!TerrainPatch.MatchesOriginalArchive(dir,NativePatch.Digest(oldHed),NativePatch.Digest(oldMfp)),"modified extension replay rejection");
        Console.WriteLine("PASS: exact generated assets, original archive preserved, two entries only, backup, idempotency, foreign data rejection. "+dir);
    }
}
