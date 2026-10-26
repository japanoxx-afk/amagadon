using System;
using System.IO;

namespace Amagadon {
    public sealed class EditorCompatibility : IDisposable {
        public class Lease {public string Backup;public string[] Files;}
        readonly string folder;
        const string WrapperHash="85e0f7d530dfda134793a57cb3e76b0287dcc96892ee57162dd68f47283b03a9";
        static string Marker(string folder) {return Path.Combine(folder,".amagadon-editor.json");}
        public static void Recover(string folder) {
            if(!File.Exists(Marker(folder)))return;
            Core.EnsureIdle(folder);
            var lease=Core.Json.Deserialize<Lease>(File.ReadAllText(Marker(folder)));
            string backupRoot=Path.GetFullPath(Path.Combine(folder,"LauncherBackups"))+Path.DirectorySeparatorChar;
            if(!Path.GetFullPath(lease.Backup).StartsWith(backupRoot,StringComparison.OrdinalIgnoreCase))throw new IOException("에디터 백업 경로가 올바르지 않습니다.");
            foreach(string name in lease.Files) {
                if(name!="ddraw.dll" && name!="ddraw.ini")throw new IOException("에디터 복원 파일이 올바르지 않습니다.");
                string source=Path.Combine(lease.Backup,name),dest=Path.Combine(folder,name);
                if(!File.Exists(source))continue; // marker is written before any move
                if(File.Exists(dest))throw new IOException("에디터 실행 중 그래픽 파일이 변경되었습니다. 백업: "+lease.Backup);
                File.Move(source,dest);
            }
            File.Delete(Marker(folder));Core.Log("ACE graphics isolation restored");
        }
        public EditorCompatibility(string game) {
            folder=game;Recover(folder);Core.Restore(folder);
            string dll=Path.Combine(folder,"ddraw.dll");
            // A pre-existing backup may itself contain our wrapper. Restore()
            // alone then leaves ACE loading the incompatible palette wrapper.
            if(!File.Exists(dll) || Core.Hash(dll)!=WrapperHash)return;
            string backup=Path.Combine(folder,"LauncherBackups","ACE-"+DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")+"-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(backup);
            string[] files=File.Exists(Path.Combine(folder,"ddraw.ini"))?new[]{"ddraw.dll","ddraw.ini"}:new[]{"ddraw.dll"};
            File.WriteAllText(Marker(folder),Core.Json.Serialize(new Lease{Backup=backup,Files=files}));
            try {foreach(string name in files)File.Move(Path.Combine(folder,name),Path.Combine(backup,name));}
            catch {Recover(folder);throw;}
            Core.Log("ACE: known cnc-ddraw wrapper temporarily isolated; native DirectDraw retained");
        }
        public void Dispose() {Recover(folder);}
    }
}
