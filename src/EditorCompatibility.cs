using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text;

namespace Amagadon {
    public sealed class EditorCompatibility : IDisposable {
        public class Lease {public string Backup;public string[] Files;public Dictionary<string,string> Installed;}
        readonly string folder;
        public const string WrapperHash="94895cf6ede8fd0f74ee1447fdc08b7044a9c65a1a25a49a4df893a0370975a3";
        public const string Profile="GdiInterops=none\r\nDesktopColorDepth=8\r\nDpiAwareness=unaware\r\nPresentDelay=on(10)\r\nDisplayResolution=app\r\nLogLevel=info\r\n";
        static readonly string[] Names={"ddraw.dll","ddraw.ini","DDrawCompat-ACE.ini","DDrawCompat-ACE.Compat.ini"};
        static string Marker(string folder) {return Path.Combine(folder,".amagadon-editor.json");}
        public static void Recover(string folder) {
            if(!File.Exists(Marker(folder)))return;
            Core.EnsureIdle(folder);
            var lease=Core.Json.Deserialize<Lease>(File.ReadAllText(Marker(folder)));
            string backupRoot=Path.GetFullPath(Path.Combine(folder,"LauncherBackups"))+Path.DirectorySeparatorChar;
            if(!Path.GetFullPath(lease.Backup).StartsWith(backupRoot,StringComparison.OrdinalIgnoreCase))throw new IOException("에디터 백업 경로가 올바르지 않습니다.");
            foreach(string name in lease.Files.Concat(lease.Installed==null?new string[0]:lease.Installed.Keys.ToArray()).Distinct()) {
                if(!Names.Contains(name))throw new IOException("에디터 복원 파일이 올바르지 않습니다.");
                string source=Path.Combine(lease.Backup,name),dest=Path.Combine(folder,name);
                bool original=lease.Files.Contains(name),backedUp=File.Exists(source);
                if(original && !backedUp)continue; // move not started, or already restored
                if(File.Exists(dest)) {
                    string expected;
                    if(lease.Installed==null || !lease.Installed.TryGetValue(name,out expected) || Core.Hash(dest)!=expected)throw new IOException("에디터 실행 중 그래픽 파일이 변경되었습니다. 백업: "+lease.Backup);
                    File.Delete(dest);
                }
                if(backedUp)File.Move(source,dest);
            }
            File.Delete(Marker(folder));Core.Log("ACE graphics lease restored");
        }
        public static byte[] WrapperBytes() {
            using(var stream=System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceStream("Amagadon.EditorWrapper"))
            using(var memory=new MemoryStream()) {
                if(stream==null)throw new IOException("에디터 그래픽 호환 자료가 없습니다.");
                stream.CopyTo(memory);byte[] bytes=memory.ToArray();
                if(NativePatch.Digest(bytes)!=WrapperHash)throw new IOException("에디터 그래픽 호환 자료가 손상되었습니다.");
                return bytes;
            }
        }
        public EditorCompatibility(string game) {
            folder=game;
            byte[] dll=WrapperBytes();
            Recover(folder);Core.Restore(folder);
            string backup=Path.Combine(folder,"LauncherBackups","ACE-"+DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")+"-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(backup);
            string[] files=Names.Where(n=>File.Exists(Path.Combine(folder,n))).ToArray();
            var installed=new Dictionary<string,string>{{"ddraw.dll",WrapperHash},{"DDrawCompat-ACE.Compat.ini",NativePatch.Digest(Encoding.ASCII.GetBytes(Profile))}};
            // Finish writes before touching the originals. Atomic renames then
            // prevent a partial DLL/config from blocking interrupted recovery.
            string nextDll=Path.Combine(backup,"next-ddraw.dll"),nextConfig=Path.Combine(backup,"next-config.ini");
            File.WriteAllBytes(nextDll,dll);File.WriteAllText(nextConfig,Profile,Encoding.ASCII);
            File.WriteAllText(Marker(folder)+".new",Core.Json.Serialize(new Lease{Backup=backup,Files=files,Installed=installed}));
            File.Move(Marker(folder)+".new",Marker(folder));
            try {
                foreach(string name in files)File.Move(Path.Combine(folder,name),Path.Combine(backup,name));
                File.Move(nextDll,Path.Combine(folder,"ddraw.dll"));
                File.Move(nextConfig,Path.Combine(folder,"DDrawCompat-ACE.Compat.ini"));
            } catch {Recover(folder);throw;}
            Core.Log("ACE: DDrawCompat 0.7.2; window-scoped GDI presenter, 8-bit offscreen palette, unaware DPI; game profile suspended");
        }
        public void Dispose() {Recover(folder);}
    }
}
