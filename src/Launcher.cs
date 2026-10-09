using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyVersion("0.1.0.0")]
namespace Amagadon {
    public class Settings { public string GamePath = @"C:\Users\seo\Downloads\armaggeddon\armaggeddon"; public bool HD = true; public bool Compatibility = true; }
    public class Backup { public string Directory; public string[] Existing; }
    public static class Core {
        public const string Version = "0.1.0";
        public static readonly string Home = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AmagadonLauncher");
        public static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
        public static string Hash(string path) { using(var h=SHA256.Create()) using(var f=File.OpenRead(path)) return BitConverter.ToString(h.ComputeHash(f)).Replace("-", "").ToLowerInvariant(); }
        public static void Log(string s) { Directory.CreateDirectory(Home); File.AppendAllText(Path.Combine(Home,"launcher.log"), DateTime.Now.ToString("o")+" "+s+Environment.NewLine); }
        public static void Validate(string folder) { foreach(var n in new[]{"Armageddon.exe","ACE.exe","Armageddon.HED","Armageddon.MFP"}) if(!File.Exists(Path.Combine(folder,n))) throw new IOException("게임 파일이 없습니다: "+n); }
        public static string Profile(bool hd) {
            return "[ddraw]\r\nwidth="+(hd?1280:800)+"\r\nheight="+(hd?720:600)+"\r\nwindowed=true\r\nfullscreen=false\r\nmaintas=false\r\naspect_ratio=\r\nrenderer=auto\r\nmaxfps=60\r\nmaxgameticks=0\r\nsinglecpu=true\r\nnonexclusive=true\r\nadjmouse=true\r\nfixchilds=2\r\nsavesettings=0\r\nresizable=false\r\n";
        }
        public static void EnsureIdle(string folder) {
            foreach(var name in new[]{"Armageddon","ACE"}) foreach(var p in Process.GetProcessesByName(name)) { using(p) { throw new IOException("게임 또는 맵 에디터를 먼저 종료해주세요."); } }
        }
        public static void Apply(string folder, bool hd, string dll) {
            Validate(folder); EnsureIdle(folder);
            if(!File.Exists(dll)) throw new IOException("compat/ddraw.dll이 없습니다. 전체 런처 패키지를 사용해주세요.");
            string marker=Path.Combine(folder,".amagadon-backup.json");
            if(!File.Exists(marker)) {
                string backup=Path.Combine(folder,"LauncherBackups",DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")); Directory.CreateDirectory(backup);
                var exists=new List<string>();
                foreach(var n in new[]{"ddraw.dll","ddraw.ini"}) if(File.Exists(Path.Combine(folder,n))) { File.Copy(Path.Combine(folder,n),Path.Combine(backup,n)); exists.Add(n); }
                File.WriteAllText(marker,Json.Serialize(new Backup{Directory=backup,Existing=exists.ToArray()}));
            }
            try { File.Copy(dll,Path.Combine(folder,"ddraw.dll"),true); File.WriteAllText(Path.Combine(folder,"ddraw.ini"),Profile(hd),Encoding.ASCII); }
            catch { Restore(folder); throw; }
        }
        public static void Restore(string folder) {
            EnsureIdle(folder); string marker=Path.Combine(folder,".amagadon-backup.json"); if(!File.Exists(marker)) return;
            var b=Json.Deserialize<Backup>(File.ReadAllText(marker));
            foreach(var n in new[]{"ddraw.dll","ddraw.ini"}) { string dest=Path.Combine(folder,n); if(b.Existing.Contains(n)) File.Copy(Path.Combine(b.Directory,n),dest,true); else if(File.Exists(dest)) File.Delete(dest); }
            File.Delete(marker);
        }
    }
    public class Launcher : Form {
        TextBox path=new TextBox(); ComboBox resolution=new ComboBox(); CheckBox compat=new CheckBox(); Label status=new Label(); Button game,editor,update; Settings settings;
        string Base { get { return AppDomain.CurrentDomain.BaseDirectory; } }
        public Launcher() {
            Text="아마게돈 런처"; ClientSize=new Size(760,530); MinimumSize=new Size(776,569); MaximumSize=MinimumSize; StartPosition=FormStartPosition.CenterScreen;
            BackColor=Color.FromArgb(17,22,30); ForeColor=Color.FromArgb(226,231,239); Font=new Font("맑은 고딕",10);
            Label title=new Label {Text="ARMAGEDDON",Font=new Font("Segoe UI",28,FontStyle.Bold),AutoSize=true,Location=new Point(30,22)}; Controls.Add(title);
            AddLabel("아마게돈  /  LAUNCHER v"+Core.Version,32,85);
            AddLabel("게임 설치 폴더",32,128); path.SetBounds(32,155,570,30); Controls.Add(path); Button browse=Button("찾아보기",614,152,112,36); browse.Click+=delegate { using(var d=new FolderBrowserDialog()) { d.SelectedPath=path.Text; if(d.ShowDialog()==DialogResult.OK) path.Text=d.SelectedPath; } };
            AddLabel("화면 해상도",32,207); resolution.DropDownStyle=ComboBoxStyle.DropDownList; resolution.Items.AddRange(new object[]{"800 × 600 · 기본","1280 × 720 · 16:9 확대"}); resolution.SetBounds(32,235,320,34); Controls.Add(resolution);
            compat.Text="그래픽 호환성 적용 (백업 포함)"; compat.SetBounds(380,231,340,36); Controls.Add(compat);
            AddLabel("16:9 옵션은 원본 화면을 확대합니다. ACE는 원본 그래픽 방식으로 실행됩니다.",32,282);
            game=Button("게임 실행",32,326,338,60); game.BackColor=Color.FromArgb(169,66,39); editor=Button("맵 에디터 실행",388,326,338,60);
            update=Button("업데이트",32,410,160,40); var notes=Button("패치노트",208,410,160,40); var restore=Button("호환성 복원",388,410,160,40); var logs=Button("실행 로그",564,410,162,40);
            status.SetBounds(32,469,694,45); status.ForeColor=Color.FromArgb(158,174,194); Controls.Add(status);
            settings=new Settings(); try { string f=Path.Combine(Core.Home,"settings.json"); if(File.Exists(f)) settings=Core.Json.Deserialize<Settings>(File.ReadAllText(f)); } catch(Exception ex) { Core.Log(ex.Message); }
            path.Text=settings.GamePath; resolution.SelectedIndex=settings.HD?1:0; compat.Checked=settings.Compatibility; status.Text="설치 경로를 확인한 뒤 실행해주세요.";
            game.Click+=async delegate { await Launch("Armageddon.exe"); }; editor.Click+=async delegate { await Launch("ACE.exe"); }; update.Click+=async delegate { await CheckUpdate(); };
            notes.Click+=delegate { ShowNotes(); }; restore.Click+=delegate { try { Core.Restore(path.Text); status.Text="원본 그래픽 설정을 복원했습니다."; } catch(Exception ex) { Error(ex); } };
            logs.Click+=delegate { Directory.CreateDirectory(Core.Home); Process.Start("explorer.exe",Core.Home); }; FormClosing+=delegate { try { Save(); } catch(Exception ex) { Core.Log(ex.Message); } };
        }
        void AddLabel(string text,int x,int y) { Controls.Add(new Label{Text=text,AutoSize=true,Location=new Point(x,y)}); }
        Button Button(string text,int x,int y,int w,int h) { var b=new Button{Text=text,BackColor=Color.FromArgb(33,43,57),ForeColor=ForeColor,FlatStyle=FlatStyle.Flat,Cursor=Cursors.Hand}; b.FlatAppearance.BorderSize=0; b.SetBounds(x,y,w,h); Controls.Add(b); return b; }
        void Save() { settings.GamePath=Path.GetFullPath(path.Text.Trim()); settings.HD=resolution.SelectedIndex==1; settings.Compatibility=compat.Checked; Directory.CreateDirectory(Core.Home); File.WriteAllText(Path.Combine(Core.Home,"settings.json"),Core.Json.Serialize(settings)); }
        void Error(Exception ex) { status.Text=ex.Message; Core.Log(ex.ToString()); MessageBox.Show(this,ex.Message,"실행 오류",MessageBoxButtons.OK,MessageBoxIcon.Warning); }
        async Task Launch(string exe) {
            game.Enabled=editor.Enabled=update.Enabled=false;
            try {
                Save(); Core.Validate(settings.GamePath); Core.EnsureIdle(settings.GamePath);
                if(exe=="ACE.exe") Core.Restore(settings.GamePath);
                else if(settings.Compatibility) Core.Apply(settings.GamePath,settings.HD,Path.Combine(Base,"compat","ddraw.dll"));
                else { Core.Restore(settings.GamePath); if(settings.HD) throw new IOException("1280×720 출력에는 그래픽 호환성 적용이 필요합니다."); }
                var file=Path.Combine(settings.GamePath,exe); Core.Log("Start "+file+" SHA256="+Core.Hash(file));
                using(var p=Process.Start(new ProcessStartInfo(file){WorkingDirectory=settings.GamePath,UseShellExecute=false})) {
                    status.Text=exe+" 실행 중"; await Task.Run(()=>p.WaitForExit());
                    Core.Log(exe+" exit=0x"+p.ExitCode.ToString("X8")); status.Text=p.ExitCode==0?"정상 종료했습니다.":"비정상 종료: 0x"+p.ExitCode.ToString("X8")+" · 실행 로그를 확인해주세요.";
                }
            } catch(Exception ex) { Error(ex); } finally { game.Enabled=editor.Enabled=update.Enabled=true; }
        }
        void ShowNotes() {
            var f=new Form{Text="패치노트",Size=new Size(650,500),StartPosition=FormStartPosition.CenterParent}; var t=new TextBox{Multiline=true,ReadOnly=true,Dock=DockStyle.Fill,ScrollBars=ScrollBars.Vertical,Font=Font};
            t.Text=File.Exists(Path.Combine(Base,"PATCHNOTES.md"))?File.ReadAllText(Path.Combine(Base,"PATCHNOTES.md")):"패치노트 파일이 없습니다."; f.Controls.Add(t); f.ShowDialog(this); f.Dispose();
        }
        async Task CheckUpdate() {
            update.Enabled=game.Enabled=editor.Enabled=false;
            try {
                status.Text="GitHub에서 최신 버전을 확인하는 중…"; ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
                using(var client=new HttpClient()) {
                    client.DefaultRequestHeaders.UserAgent.ParseAdd("AmagadonLauncher/"+Core.Version); client.Timeout=TimeSpan.FromSeconds(90);
                    var response=await client.GetAsync("https://api.github.com/repos/japanoxx-afk/amagadon/releases/latest");
                    if(response.StatusCode==HttpStatusCode.NotFound) {status.Text="아직 배포된 업데이트가 없습니다.";return;} response.EnsureSuccessStatusCode();
                    var release=Core.Json.Deserialize<Dictionary<string,object>>(await response.Content.ReadAsStringAsync()); string tag=(string)release["tag_name"]; Version latest;
                    if(!System.Version.TryParse(tag.TrimStart('v'),out latest)) throw new IOException("올바르지 않은 릴리스 버전입니다.");
                    if(latest<=new Version(Core.Version)) {status.Text="최신 버전입니다.";return;}
                    var assets=((object[])release["assets"]).Cast<Dictionary<string,object>>().ToArray();
                    var zip=assets.Single(a=>(string)a["name"]=="AmagadonLauncher.zip"); var sha=assets.Single(a=>(string)a["name"]=="AmagadonLauncher.zip.sha256");
                    string dir=Path.Combine(Core.Home,"updates",Guid.NewGuid().ToString("N")); Directory.CreateDirectory(dir); string package=Path.Combine(dir,"AmagadonLauncher.zip");
                    foreach(var a in new[]{zip,sha}) {var uri=new Uri((string)a["browser_download_url"]); if(uri.Scheme!="https" || uri.Host!="github.com" || !uri.AbsolutePath.StartsWith("/japanoxx-afk/amagadon/releases/download/",StringComparison.Ordinal)) throw new IOException("신뢰할 수 없는 업데이트 주소입니다.");}
                    status.Text="업데이트 다운로드 중…"; File.WriteAllBytes(package,await client.GetByteArrayAsync((string)zip["browser_download_url"]));
                    string hash=(await client.GetStringAsync((string)sha["browser_download_url"])).Trim(); if(!String.Equals(hash,Core.Hash(package),StringComparison.OrdinalIgnoreCase)) throw new IOException("업데이트 SHA-256 검증 실패");
                    Core.EnsureIdle(settings.GamePath); string helper=Path.Combine(dir,"apply-update.ps1"); File.Copy(Path.Combine(Base,"apply-update.ps1"),helper);
                    string args="-NoProfile -ExecutionPolicy Bypass -File \""+helper+"\" -LauncherPid "+Process.GetCurrentProcess().Id+" -Package \""+package+"\" -Target \""+Base.TrimEnd(Path.DirectorySeparatorChar)+"\"";
                    Process.Start(new ProcessStartInfo("powershell.exe",args){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden}); Close();
                }
            } catch(Exception ex) {Error(ex);} finally {update.Enabled=game.Enabled=editor.Enabled=true;}
        }
        [STAThread] public static int Main(string[] args) {
            if(args.Contains("--self-test")) { try { SelfTest.Run();return 0; } catch(Exception ex) {Core.Log(ex.ToString());return 1;} }
            bool first; using(var mutex=new System.Threading.Mutex(true,"Local\\AmagadonLauncher",out first)) {if(!first)return 0; Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new Launcher());} return 0;
        }
    }
    static class SelfTest {
        public static void Run() {
            string d=Path.Combine(Path.GetTempPath(),"amagadon-test-"+Guid.NewGuid().ToString("N")); Directory.CreateDirectory(d);
            try {
                foreach(var n in new[]{"Armageddon.exe","ACE.exe","Armageddon.HED","Armageddon.MFP"}) File.WriteAllText(Path.Combine(d,n),"fixture");
                string dll=Path.Combine(d,"wrapper");File.WriteAllText(dll,"new"); File.WriteAllText(Path.Combine(d,"ddraw.ini"),"original");
                Core.Apply(d,true,dll); if(!File.ReadAllText(Path.Combine(d,"ddraw.ini")).Contains("width=1280"))throw new Exception("HD profile failed");
                Core.Apply(d,false,dll); Core.Restore(d); if(File.ReadAllText(Path.Combine(d,"ddraw.ini"))!="original" || File.Exists(Path.Combine(d,"ddraw.dll")))throw new Exception("Restore failed");
                File.WriteAllText(Path.Combine(d,"ddraw.dll"),"old-dll"); Core.Apply(d,true,dll);Core.Restore(d);if(File.ReadAllText(Path.Combine(d,"ddraw.dll"))!="old-dll")throw new Exception("DLL backup failed");
                File.Delete(Path.Combine(d,"ACE.exe"));bool failed=false;try{Core.Validate(d);}catch(IOException){failed=true;}if(!failed)throw new Exception("Validation failed");Core.Log("SELF-TEST PASS");
            } finally {Directory.Delete(d,true);}
        }
    }
}
