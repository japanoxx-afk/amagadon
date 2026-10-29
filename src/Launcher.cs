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

[assembly: System.Reflection.AssemblyVersion("0.3.24.0")]
[assembly: System.Reflection.AssemblyInformationalVersion("0.3.24")]
namespace Amagadon {
    public class Settings {
        public string GamePath="";
        public bool NativeHD=false, OutputHD=false, Fullscreen=true, MaintainAspect=false, ConfineMouse=true, Compatibility=true;
        public string Renderer="auto";
        public bool AutoReplay=true;
        public bool DiagnosticLogging=true, MouseCompatibility=true;
        public int InputProfile=0;
        public int ScreenProfile=0;
        public string ZoneAddress="127.0.0.1";
        public int ZonePort=9000;
    }
    public class Backup { public string Directory; public string[] Existing; }
    public static class Core {
        public const string Version = "0.3.24";
        public const string DisplayVersion = "0.3.24";
        public static readonly string Home = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AmagadonLauncher");
        public static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
        public static string Hash(string path) { using(var h=SHA256.Create()) using(var f=File.OpenRead(path)) return BitConverter.ToString(h.ComputeHash(f)).Replace("-", "").ToLowerInvariant(); }
        static readonly object logGate=new object();
        public static void Log(string s) {try {lock(logGate) {Directory.CreateDirectory(Home);string file=Path.Combine(Home,"launcher.log");if(File.Exists(file) && new FileInfo(file).Length>4*1024*1024) {File.Copy(file,file+".1",true);File.Delete(file);}File.AppendAllText(file,DateTime.Now.ToString("o")+" "+s+Environment.NewLine);}}catch {}}
        public static readonly string[] RequiredFiles={"Armageddon.exe","ACE.exe","Armageddon.HED","Armageddon.MFP","binkw32.dll","Mss32.dll"};
        public static void Validate(string folder) {
            var missing=RequiredFiles.Where(n=>!File.Exists(Path.Combine(folder,n))).ToArray();
            if(missing.Length>0)throw new IOException("필수 게임 파일이 없습니다: "+String.Join(", ",missing));
        }
        public static string FindGame() {
            string here=AppDomain.CurrentDomain.BaseDirectory;
            string downloads=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"Downloads","armaggeddon");
            foreach(var candidate in new[]{here,Path.Combine(here,"game"),Path.Combine(here,"armaggeddon"),downloads,Path.Combine(downloads,"armaggeddon")})
                if(RequiredFiles.All(n=>File.Exists(Path.Combine(candidate,n))))return Path.GetFullPath(candidate);
            return "";
        }
        public static void MigrateScreen(Settings s) {
            if(s.ScreenProfile<1) {s.NativeHD=true;s.Fullscreen=true;s.MaintainAspect=false;s.Compatibility=true;s.ScreenProfile=1;}
        }
        public static void MigrateInput(Settings s) {
            // Older profiles enabled a wrapper hook that can discard mouse input.
            // Migrate once; subsequent explicit choices remain user controlled.
            if(s.InputProfile<1) {s.MouseCompatibility=true;s.InputProfile=1;}
        }
        public static string Profile(Settings s) {
            if(!new[]{"auto","gdi","direct3d9","opengl"}.Contains(s.Renderer))throw new IOException("지원하지 않는 렌더러 설정입니다.");
            int width=s.NativeHD?0:(s.OutputHD?1024:800),height=s.NativeHD?0:(s.OutputHD?768:600);
            return "[ddraw]\r\nwidth="+width+"\r\nheight="+height+"\r\nwindowed=true\r\nfullscreen="+s.Fullscreen.ToString().ToLowerInvariant()+"\r\nmaintas="+s.MaintainAspect.ToString().ToLowerInvariant()+"\r\naspect_ratio=\r\nboxing=false\r\nrenderer="+s.Renderer+"\r\ndevmode="+(!s.ConfineMouse).ToString().ToLowerInvariant()+"\r\nmaxfps=60\r\nmaxgameticks=-1\r\nsinglecpu=true\r\nnonexclusive=true\r\nadjmouse=true\r\nno_dinput_hook="+s.MouseCompatibility.ToString().ToLowerInvariant()+"\r\ncenter_cursor_fix=false\r\nlock_mouse_top_left=false\r\nfixchilds=2\r\nsavesettings=0\r\nresizable=false\r\ntoggle_borderless=true\r\nkeytogglefullscreen=0x0D\r\nd3d9_filter=0\r\nshader=\r\n";
        }
        public static void EnsureIdle(string folder) {
            string target=Path.GetFullPath(folder).TrimEnd(Path.DirectorySeparatorChar);
            foreach(var name in new[]{"Armageddon","Armageddon.HD-preview","Armageddon.Replay","Armageddon.Replay032","Armageddon.Replay033","Armageddon.Replay033Final","Armageddon.Replay034","ACE","ACE.Compat"}) foreach(var p in Process.GetProcessesByName(name)) { using(p) {
                string running;
                try {running=Path.GetDirectoryName(p.MainModule.FileName).TrimEnd(Path.DirectorySeparatorChar);}
                catch(Exception) {if(p.HasExited)continue;throw new IOException("실행 중인 게임 경로를 확인할 수 없습니다. 게임 또는 맵 에디터를 종료해주세요.");}
                if(String.Equals(running,target,StringComparison.OrdinalIgnoreCase))throw new IOException("이 설치 폴더의 게임 또는 맵 에디터를 먼저 종료해주세요.");
            } }
        }
        public static void Apply(string folder, Settings settings, string dll) {
            Validate(folder); EnsureIdle(folder);
            if(!File.Exists(dll)) throw new IOException("compat/ddraw.dll이 없습니다. 전체 런처 패키지를 사용해주세요.");
            string marker=Path.Combine(folder,".amagadon-backup.json");
            if(!File.Exists(marker)) {
                string backup=Path.Combine(folder,"LauncherBackups",DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")); Directory.CreateDirectory(backup);
                var exists=new List<string>();
                foreach(var n in new[]{"ddraw.dll","ddraw.ini"}) if(File.Exists(Path.Combine(folder,n))) { File.Copy(Path.Combine(folder,n),Path.Combine(backup,n)); exists.Add(n); }
                File.WriteAllText(marker,Json.Serialize(new Backup{Directory=backup,Existing=exists.ToArray()}));
            }
            try { File.Copy(dll,Path.Combine(folder,"ddraw.dll"),true); File.WriteAllText(Path.Combine(folder,"ddraw.ini"),Profile(settings),Encoding.ASCII); }
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
        TextBox path=new TextBox(); ComboBox resolution=new ComboBox(),output=new ComboBox(),aspect=new ComboBox(),renderer=new ComboBox();
        CheckBox diagnostic=new CheckBox(),mouseCompatibility=new CheckBox(),autoReplay=new CheckBox(),compat=new CheckBox(),fullscreen=new CheckBox(),confine=new CheckBox();
        bool gameRunning; Button replay; ReplaySession activeReplay; Label status=new Label(); Button game,editor,update; Settings settings;
        readonly CrazyZoneHost zoneHost=new CrazyZoneHost();
        string Base { get { return AppDomain.CurrentDomain.BaseDirectory; } }
        public Launcher() {
            AutoScaleMode=AutoScaleMode.None;
            Text="아마게돈 런처 · "+Core.DisplayVersion; ClientSize=new Size(760,950); AutoScroll=true;AutoScrollMinSize=new Size(740,940); StartPosition=FormStartPosition.CenterScreen;
            BackColor=Color.FromArgb(17,22,30); ForeColor=Color.FromArgb(226,231,239); Font=new Font("맑은 고딕",10);
            Label title=new Label {Text="ARMAGEDDON",Font=new Font("Segoe UI",28,FontStyle.Bold),AutoSize=true,Location=new Point(30,22)}; Controls.Add(title);
            AddLabel("아마게돈  /  LAUNCHER v"+Core.DisplayVersion,32,85);
            AddLabel("게임 설치 폴더",32,118); path.SetBounds(32,145,570,30); Controls.Add(path); Button browse=Button("찾아보기",614,142,112,36); browse.Click+=delegate { using(var d=new FolderBrowserDialog()) { d.SelectedPath=path.Text; if(d.ShowDialog()==DialogResult.OK) path.Text=d.SelectedPath; } };
            AddLabel("내부 해상도 · 지도 표시 영역",32,205); resolution.DropDownStyle=ComboBoxStyle.DropDownList; resolution.Items.AddRange(new object[]{"800 × 600 · 원본","1024 × 768 · 실제 영역 확장"}); resolution.SetBounds(32,232,338,34); Controls.Add(resolution);
            AddLabel("출력 크기 · 화면 확대",388,205); output.DropDownStyle=ComboBoxStyle.DropDownList; output.Items.AddRange(new object[]{"내부 해상도와 동일","1024 × 768 출력"}); output.SetBounds(388,232,338,34); Controls.Add(output);
            fullscreen.Text="전체 화면 채우기 (Alt+Enter로 전환)";fullscreen.SetBounds(32,282,338,36);Controls.Add(fullscreen);
            aspect.DropDownStyle=ComboBoxStyle.DropDownList;aspect.Items.AddRange(new object[]{"비율 유지 · 여백 허용","화면 채우기 · 비율이 다르면 늘어남"});aspect.SetBounds(388,283,338,34);Controls.Add(aspect);
            AddLabel("그래픽 렌더러",32,329);renderer.DropDownStyle=ComboBoxStyle.DropDownList;renderer.Items.AddRange(new object[]{"자동","GDI","Direct3D 9","OpenGL"});renderer.SetBounds(32,356,338,34);Controls.Add(renderer);
            confine.Text="게임에 포커스가 있을 때 마우스 가두기";confine.SetBounds(388,351,338,44);Controls.Add(confine);
            compat.Text="그래픽 호환성 적용 (원본 DLL/설정 백업)"; compat.SetBounds(32,401,680,36); Controls.Add(compat);
            Controls.Add(new Label{Text="1024×768 내부 해상도는 4:3 시야를 사용합니다. 화면 늘리기로 모니터를 채울 수 있습니다.\r\n원본 EXE를 유지하고 별도 HD 실행 파일을 사용합니다. ACE는 전용 그래픽 호환 설정으로 실행합니다.",Location=new Point(32,447),Size=new Size(694,46),Font=new Font("맑은 고딕",9)});
            game=Button("게임 실행",32,506,338,60); game.BackColor=Color.FromArgb(169,66,39); editor=Button("맵 에디터 실행",388,506,338,60);
            update=Button("업데이트",32,585,160,40); var notes=Button("패치노트",208,585,160,40); var restore=Button("원본 설정 복원",388,585,160,40); var logs=Button("로깅 리포트 ZIP",564,585,162,40);
            autoReplay.Text="싱글플레이 리플레이 자동 기록 · 실험 (AI 동기화 검증 중)";autoReplay.SetBounds(32,636,694,34);Controls.Add(autoReplay);
            replay=Button("리플레이 재생",32,681,338,40);var replayFolder=Button("리플레이 저장 폴더",388,681,338,40);
            replay.Click+=async delegate {if(activeReplay!=null && activeReplay.IsPlayback) {activeReplay.RequestStop();return;}using(var dialog=new ReplayBrowser()) {if(dialog.ShowDialog(this)==DialogResult.OK) {resolution.SelectedIndex=1;compat.Checked=true;await Launch("Armageddon.exe",dialog.SelectedReplay);}}};
            replayFolder.Click+=delegate {Directory.CreateDirectory(ReplayFiles.Home);Process.Start("explorer.exe",ReplayFiles.Home);};
            diagnostic.Text="진단 기록 및 충돌 덤프 수집";diagnostic.SetBounds(32,736,338,32);Controls.Add(diagnostic);
            mouseCompatibility.Text="마우스 입력 호환 모드 (재실행 필요)";mouseCompatibility.SetBounds(388,736,338,32);Controls.Add(mouseCompatibility);
            Controls.Add(new Label {Text="마우스가 멈추면 Ctrl+Tab으로 제한을 해제하거나 입력 호환 모드로 재실행하세요.\r\n진단은 로컬에 저장됩니다. ZIP에는 PC 경로와 충돌 메모리가 포함될 수 있습니다.",Location=new Point(32,775),Size=new Size(694,40),Font=new Font("맑은 고딕",9)});
            var ipxRepair=Button("IPX 등록 복구 (관리자 권한)",32,823,338,36);
            var zone=Button("Crazy Zone 서버 / 접속",388,823,338,36);
            zone.Click+=async delegate {if(gameRunning || checkingUpdate)return;using(var dialog=new CrazyZoneWindow(zoneHost,settings)) {if(dialog.ShowDialog(this)==DialogResult.OK) {settings.ZoneAddress=dialog.Address;settings.ZonePort=dialog.Port;Save();await Launch("Armageddon.exe",null,true);}}};
            FormClosed+=delegate {zoneHost.Dispose();};
            ipxRepair.Click+=async delegate {if(gameRunning || checkingUpdate)return;gameRunning=true;ipxRepair.Enabled=game.Enabled=editor.Enabled=update.Enabled=replay.Enabled=false;try {Save();await IpxSetup.RunElevated(path.Text);status.Text="IPX 공급자 등록을 복구했습니다. 게임을 다시 실행해 IPX를 선택해주세요.";}catch(System.ComponentModel.Win32Exception ex){if(ex.NativeErrorCode==1223)status.Text="IPX 복구 권한 요청을 취소했습니다.";else Error(ex);}catch(Exception ex){Error(ex);}finally{gameRunning=false;ipxRepair.Enabled=game.Enabled=editor.Enabled=update.Enabled=replay.Enabled=true;}};
            status.SetBounds(32,870,694,55); status.ForeColor=Color.FromArgb(158,174,194); Controls.Add(status);
            settings=new Settings(); try { string f=Path.Combine(Core.Home,"settings.json"); if(File.Exists(f)) settings=Core.Json.Deserialize<Settings>(File.ReadAllText(f)); } catch(Exception ex) { Core.Log(ex.Message); }
            Core.MigrateScreen(settings);
            Core.MigrateInput(settings);
            if(String.IsNullOrWhiteSpace(settings.GamePath))settings.GamePath=Core.FindGame();
            autoReplay.Checked=settings.AutoReplay;diagnostic.Checked=settings.DiagnosticLogging;mouseCompatibility.Checked=settings.MouseCompatibility;
            path.Text=settings.GamePath; resolution.SelectedIndex=settings.NativeHD?1:0; output.SelectedIndex=settings.OutputHD?1:0; compat.Checked=settings.Compatibility;
            fullscreen.Checked=settings.Fullscreen;aspect.SelectedIndex=settings.MaintainAspect?0:1;confine.Checked=settings.ConfineMouse;
            renderer.SelectedIndex=Math.Max(0,Array.IndexOf(new[]{"auto","gdi","direct3d9","opengl"},settings.Renderer));
            resolution.SelectedIndexChanged+=delegate {output.Enabled=resolution.SelectedIndex==0;autoReplay.Enabled=resolution.SelectedIndex==1;};output.Enabled=!settings.NativeHD;autoReplay.Enabled=settings.NativeHD;
            // Coordinates above are 96-DPI design units. SetProcessDPIAware alone
            // leaves the whole UI tiny on high-DPI monitors; scale controls too.
            float uiScale;using(var graphics=CreateGraphics())uiScale=Math.Max(1.15f,graphics.DpiX/96f);
            Scale(new SizeF(uiScale,uiScale));
            var workArea=Screen.FromControl(this).WorkingArea;
            MinimumSize=new Size(Math.Min((int)(776*uiScale),workArea.Width),Math.Min((int)(600*uiScale),workArea.Height));
            Size=new Size(Math.Min(Width,workArea.Width),Math.Min(Height,workArea.Height));
            status.Text=String.IsNullOrEmpty(path.Text)?"게임 설치 폴더를 선택해주세요.":"설치 경로를 확인한 뒤 실행해주세요.";
            game.Click+=async delegate { await Launch("Armageddon.exe"); }; editor.Click+=async delegate { await Launch("ACE.exe"); }; update.Click+=async delegate { await CheckUpdate(); };
            notes.Click+=delegate { ShowNotes(); }; restore.Click+=delegate { try { NativePatch.Remove(path.Text,Path.Combine(Base,"compat","hd-preview.json"));Core.Restore(path.Text); status.Text="원본 그래픽 설정을 복원하고 생성한 HD 실행 파일을 제거했습니다."; } catch(Exception ex) { Error(ex); } };
            logs.Click+=async delegate {using(var dialog=new SaveFileDialog {Filter="진단 ZIP (*.zip)|*.zip",FileName="Amagadon-Report-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+".zip"}) {if(dialog.ShowDialog(this)!=DialogResult.OK)return;logs.Enabled=false;try {string gameFolder=path.Text;await Task.Run(()=>Diagnostics.Report(gameFolder,dialog.FileName));status.Text="진단 리포트를 저장했습니다: "+dialog.FileName;Process.Start("explorer.exe","/select,\""+dialog.FileName+"\"");}catch(Exception ex) {Error(ex);}finally {logs.Enabled=true;}}}; FormClosing+=delegate(object sender,FormClosingEventArgs args) {if(gameRunning) {args.Cancel=true;status.Text="실행 중인 게임 또는 에디터를 먼저 종료해주세요.";return;}try { Save(); } catch(Exception ex) { Core.Log(ex.Message); } };
        }
        void AddLabel(string text,int x,int y) { Controls.Add(new Label{Text=text,AutoSize=true,Location=new Point(x,y)}); }
        Button Button(string text,int x,int y,int w,int h) { var b=new Button{Text=text,BackColor=Color.FromArgb(33,43,57),ForeColor=ForeColor,FlatStyle=FlatStyle.Flat,Cursor=Cursors.Hand}; b.FlatAppearance.BorderSize=0; b.SetBounds(x,y,w,h); Controls.Add(b); return b; }
        void Save() {
            settings.GamePath=String.IsNullOrWhiteSpace(path.Text)?"":Path.GetFullPath(path.Text.Trim()); settings.NativeHD=resolution.SelectedIndex==1;settings.OutputHD=output.SelectedIndex==1; settings.Compatibility=compat.Checked;
            settings.DiagnosticLogging=diagnostic.Checked;settings.MouseCompatibility=mouseCompatibility.Checked;settings.AutoReplay=autoReplay.Checked;settings.Fullscreen=fullscreen.Checked;settings.MaintainAspect=aspect.SelectedIndex==0;settings.ConfineMouse=confine.Checked;settings.Renderer=new[]{"auto","gdi","direct3d9","opengl"}[renderer.SelectedIndex];
            Directory.CreateDirectory(Core.Home); File.WriteAllText(Path.Combine(Core.Home,"settings.json"),Core.Json.Serialize(settings));
        }
        void Error(Exception ex) { status.Text=ex.Message; Core.Log(ex.ToString()); MessageBox.Show(this,ex.Message,"실행 오류",MessageBoxButtons.OK,MessageBoxIcon.Warning); }
        async Task Launch(string exe,string replaySource=null,bool privateZone=false) {
            EditorCompatibility editorLease=null;gameRunning=true;game.Enabled=editor.Enabled=update.Enabled=replay.Enabled=false;
            try {
                Save(); Core.Validate(settings.GamePath); Core.EnsureIdle(settings.GamePath);EditorCompatibility.Recover(settings.GamePath);
                CrazyZonePatch.Address=privateZone?settings.ZoneAddress:null;CrazyZonePatch.Port=settings.ZonePort;
                if(privateZone)CrazyZonePatch.Validate(settings.ZoneAddress,settings.ZonePort);
                string file=Path.Combine(settings.GamePath,exe);
                if(exe=="ACE.exe") {file=EditorPatch.Prepare(settings.GamePath);editorLease=new EditorCompatibility(settings.GamePath);}
                else {
                    if(settings.NativeHD) {
                        if(!settings.Compatibility)throw new IOException("HD 실행 파일은 그래픽 호환성 적용이 필요합니다.");
                        file=replaySource==null?NativePatch.Prepare(settings.GamePath,Path.Combine(Base,"compat","hd-preview.json")):NativePatch.PrepareReplay(settings.GamePath,replaySource);
                    }
                    if(settings.Compatibility) {
                        string wrapper=Path.Combine(Base,"compat","ddraw.dll");
                        if(!File.Exists(wrapper) || Core.Hash(wrapper)!="85e0f7d530dfda134793a57cb3e76b0287dcc96892ee57162dd68f47283b03a9")throw new IOException("호환성 DLL의 SHA-256이 다릅니다. 전체 패키지를 다시 설치해주세요.");
                        Core.Apply(settings.GamePath,settings,wrapper);
                    }
                    else { if(settings.OutputHD || settings.Fullscreen || !settings.ConfineMouse)throw new IOException("출력/화면/마우스 설정은 그래픽 호환성 적용이 필요합니다."); Core.Restore(settings.GamePath); }
                }
                Core.Log("Display internal="+(settings.NativeHD?"1024x768":"800x600")+" fullscreen="+settings.Fullscreen+" maintainAspect="+settings.MaintainAspect+" desktop="+Screen.FromControl(this).Bounds.Size);
                Core.Log("Start version="+Core.DisplayVersion+" "+file+" SHA256="+Core.Hash(file)+" settings="+Core.Json.Serialize(settings));
                if(!privateZone && exe=="Armageddon.exe" && settings.NativeHD && (settings.AutoReplay || replaySource!=null)) {
                    status.Text=replaySource!=null?"리플레이 시작 상태를 불러오는 중…":"게임 실행 중 · 싱글플레이 자동 기록 준비";
                    using(var session=new ReplaySession(settings.GamePath,file,replaySource)) {session.DiagnosticSettings=settings;activeReplay=session;session.Progress=delegate(string text) {if(!IsDisposed && IsHandleCreated)BeginInvoke((Action)delegate {status.Text=text;});};if(session.IsPlayback) {replay.Text="재생 중단";replay.Enabled=true;}await Task.Run(()=>session.Run());status.Text=session.Result;}
                } else using(var p=exe=="Armageddon.exe"?NetworkGuard.Start(file,settings.GamePath):Process.Start(Diagnostics.StartInfo(file,settings.GamePath))) {
                    Diagnostics.Begin(p.Id,file,settings.GamePath,settings);status.Text=exe+" 실행 중"; await Task.Run(()=>p.WaitForExit());
                    int exitCode=p.ExitCode;Core.Log(exe+" exit=0x"+exitCode.ToString("X8")); status.Text=exitCode==0?"정상 종료했습니다.":"비정상 종료: 0x"+exitCode.ToString("X8")+" · 실행 로그를 확인해주세요.";
                }
            } catch(Exception ex) { Error(ex); } finally {CrazyZonePatch.Address=null;if(editorLease!=null)try {editorLease.Dispose();}catch(Exception ex) {Error(ex);} activeReplay=null;replay.Text="리플레이 재생";gameRunning=false;game.Enabled=editor.Enabled=update.Enabled=replay.Enabled=true; }
        }
        void ShowNotes() {
            var f=new Form{Text="패치노트",Size=new Size(650,500),StartPosition=FormStartPosition.CenterParent}; var t=new TextBox{Multiline=true,ReadOnly=true,Dock=DockStyle.Fill,ScrollBars=ScrollBars.Vertical,Font=Font};
            t.Text=File.Exists(Path.Combine(Base,"PATCHNOTES.md"))?File.ReadAllText(Path.Combine(Base,"PATCHNOTES.md")):"패치노트 파일이 없습니다."; f.Controls.Add(t); f.ShowDialog(this); f.Dispose();
        }
        bool checkingUpdate;
        readonly System.Threading.CancellationTokenSource updateCancellation=new System.Threading.CancellationTokenSource();
        protected override void OnShown(EventArgs e) {base.OnShown(e);CheckStartupUpdate();}
        async void CheckStartupUpdate() {await CheckUpdate(true);}
        protected override void OnFormClosing(FormClosingEventArgs e) {base.OnFormClosing(e);if(!e.Cancel)updateCancellation.Cancel();}
        async Task CheckUpdate(bool automatic=false) {
            if(checkingUpdate || gameRunning || IsDisposed)return;
            checkingUpdate=true;
            update.Enabled=game.Enabled=editor.Enabled=replay.Enabled=false;
            try {
                status.Text="GitHub에서 최신 버전을 확인하는 중…"; ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
                using(var client=new HttpClient()) {
                    client.DefaultRequestHeaders.UserAgent.ParseAdd("AmagadonLauncher/"+Core.Version); client.Timeout=TimeSpan.FromSeconds(90);
                    string directory=Path.Combine(Core.Home,"updates",Guid.NewGuid().ToString("N"));
                    string package=await Updates.Prepare(client,Core.Version,directory,
                        release=>MessageBox.Show(this,"새 버전 "+release.tag_name+"이 있습니다. (현재 "+Core.DisplayVersion+")\r\n\r\n확인을 누르면 업데이트를 설치한 뒤 런처를 다시 실행합니다.","런처 업데이트",MessageBoxButtons.OKCancel,MessageBoxIcon.Information)==DialogResult.OK,
                        message=>{if(!IsDisposed)status.Text=message;},updateCancellation.Token);
                    if(package==null)return;
                    Core.EnsureIdle(settings.GamePath);Save();status.Text="업데이트 파일 검증 및 설치 준비 중…";
                    await Updates.StartInstaller(package,Base,Path.GetFileName(Application.ExecutablePath),Process.GetCurrentProcess().Id,updateCancellation.Token);
                    Close();
                }
            } catch(Exception ex) {
                Core.Log("Update check/install: "+ex);
                if(!IsDisposed && !updateCancellation.IsCancellationRequested) {
                    if(automatic)status.Text="업데이트를 완료하지 못했습니다. 업데이트 버튼으로 다시 시도해주세요.";
                    else Error(ex);
                }
            } finally {checkingUpdate=false;if(!IsDisposed)update.Enabled=game.Enabled=editor.Enabled=replay.Enabled=!gameRunning;}
        }
        [STAThread] public static int Main(string[] args) {
            Diagnostics.SetProcessDPIAware();
            if(args.Length==2 && args[0]=="--repair-ipx")return IpxSetup.Repair(args[1]);
            if(args.Length==4 && args[0]=="--watch-process")return Diagnostics.Watch(Int32.Parse(args[1]),Int64.Parse(args[2]),args[3]);
            if(args.Length==3 && args[0]=="--diagnostic-report") {try {Diagnostics.Report(args[1],args[2]);return 0;}catch(Exception ex) {Core.Log(ex.ToString());return 1;}}
            AppDomain.CurrentDomain.UnhandledException+=delegate(object sender,UnhandledExceptionEventArgs e) {Core.Log("Launcher unhandled: "+e.ExceptionObject);};
            Application.ThreadException+=delegate(object sender,System.Threading.ThreadExceptionEventArgs e) {Core.Log("Launcher UI exception: "+e.Exception);MessageBox.Show(e.Exception.Message,"런처 오류");};
            if(args.Length==4 && args[0]=="--capture-replay-scenario") {try {Core.EnsureIdle(args[2]);string exe=NativePatch.Prepare(args[2],Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"compat","hd-preview.json"));using(var session=new ReplaySession(args[2],exe,args[1])) {session.CaptureDiagnostic=args[3];session.Run();return File.Exists(args[3])?0:1;}}catch(Exception ex){Core.Log(ex.ToString());return 1;}}
            if(args.Length==3 && args[0]=="--diagnose-replay") {try {Core.EnsureIdle(args[2]);string exe=NativePatch.PrepareReplay(args[2],args[1]);using(var session=new ReplaySession(args[2],exe,args[1])) {session.Run();Core.Log("REAL REPLAY DIAGNOSTIC "+session.Result);return session.Result=="리플레이 재생을 완료했습니다."?0:1;}}catch(Exception ex){Core.Log(ex.ToString());return 1;}}
            if(args.Length==3 && args[0]=="--verify-replay") {try {ReplayTests.ArchiveRun(args[1],args[2]);return 0;}catch(Exception ex) {Core.Log(ex.ToString());return 1;}}
            if(args.Length==2 && args[0]=="--test-replay-process") {try {ReplayTests.ProcessRoundTrip(args[1]);return 0;}catch(Exception ex) {Core.Log(ex.ToString());return 1;}}
            if(args.Length==2 && args[0]=="--verify-native") {try{SelfTest.NativeRun(args[1]);return 0;}catch(Exception ex){Core.Log(ex.ToString());return 1;}}
            if(args.Contains("--self-test")) { try { SelfTest.Run();ReplayTests.Run();return 0; } catch(Exception ex) {Core.Log(ex.ToString());return 1;} }
            bool first; using(var mutex=new System.Threading.Mutex(true,"Local\\AmagadonLauncher-"+Core.DisplayVersion,out first)) {if(!first)return 0; Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new Launcher());} return 0;
        }
    }
    static class SelfTest {
        public static void Run() {
            string d=Path.Combine(Path.GetTempPath(),"amagadon-test-"+Guid.NewGuid().ToString("N")); Directory.CreateDirectory(d);
            try {
                foreach(var n in Core.RequiredFiles) File.WriteAllText(Path.Combine(d,n),"fixture");
                string dll=Path.Combine(d,"wrapper");File.WriteAllText(dll,"new"); File.WriteAllText(Path.Combine(d,"ddraw.ini"),"original");
                Core.Apply(d,new Settings{OutputHD=true},dll); if(!File.ReadAllText(Path.Combine(d,"ddraw.ini")).Contains("width=1024"))throw new Exception("Output profile failed");
                Core.Apply(d,new Settings(),dll); Core.Restore(d); if(File.ReadAllText(Path.Combine(d,"ddraw.ini"))!="original" || File.Exists(Path.Combine(d,"ddraw.dll")))throw new Exception("Restore failed");
                File.WriteAllText(Path.Combine(d,"ddraw.dll"),"old-dll"); Core.Apply(d,new Settings{NativeHD=true},dll);Core.Restore(d);if(File.ReadAllText(Path.Combine(d,"ddraw.dll"))!="old-dll")throw new Exception("DLL backup failed");
                if(!Core.Profile(new Settings{NativeHD=true}).Contains("width=0\r\nheight=0"))throw new Exception("Native/output separation failed");
                string fill=Core.Profile(new Settings{NativeHD=true,Fullscreen=true,MaintainAspect=false});
                foreach(string option in new[]{"fullscreen=true","windowed=true","maintas=false","boxing=false","adjmouse=true"})if(!fill.Contains(option+"\r\n"))throw new Exception("Screen fill profile failed: "+option);
                if(!Core.Profile(new Settings{ConfineMouse=false,Fullscreen=true,Renderer="gdi"}).Contains("devmode=true"))throw new Exception("Mouse profile failed");
                var migrated=new Settings {NativeHD=false,Fullscreen=false,MaintainAspect=true,Compatibility=false};Core.MigrateScreen(migrated);
                if(!migrated.NativeHD || !migrated.Fullscreen || migrated.MaintainAspect || !migrated.Compatibility || migrated.ScreenProfile!=1)throw new Exception("Screen migration failed");
                migrated.NativeHD=false;migrated.Fullscreen=false;migrated.MaintainAspect=true;Core.MigrateScreen(migrated);
                if(migrated.NativeHD || migrated.Fullscreen || !migrated.MaintainAspect)throw new Exception("Saved screen choice was overwritten");
                bool unknown=false;try{NativePatch.Build(Encoding.ASCII.GetBytes("unknown"),new PatchRecipe());}catch(IOException){unknown=true;}if(!unknown)throw new Exception("Unknown EXE accepted");
                File.Delete(Path.Combine(d,"ACE.exe"));bool failed=false;try{Core.Validate(d);}catch(IOException){failed=true;}if(!failed)throw new Exception("Validation failed");Core.Log("SELF-TEST PASS");
            } finally {Directory.Delete(d,true);}
        }
        public static void NativeRun(string source) {
            string recipe=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"compat","hd-preview.json");
            var r=NativePatch.Load(recipe);byte[] original=File.ReadAllBytes(source);var output=NativePatch.Build(original,r);
            if(NativePatch.Digest(output)!=r.OutputHash)throw new Exception("Native output hash mismatch");
            var changed=(byte[])original.Clone();changed[0]^=1;bool rejected=false;
            try{NativePatch.Build(changed,r);}catch(IOException){rejected=true;}if(!rejected)throw new Exception("Modified input accepted");
            var tampered=Core.Json.Deserialize<PatchRecipe>(Core.Json.Serialize(r));tampered.Edits[0].After="ff";
            rejected=false;try{NativePatch.Build(original,tampered);}catch(IOException){rejected=true;}if(!rejected)throw new Exception("Modified recipe accepted");
            string fixture=Path.Combine(Path.GetTempPath(),"AmagadonNative-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(fixture);
            try {
                foreach(string name in Core.RequiredFiles)File.WriteAllBytes(Path.Combine(fixture,name),name=="Armageddon.exe"?original:new byte[]{0});
                string previous=Path.Combine(Path.GetDirectoryName(source),NativePatch.FileName);
                if(File.Exists(previous) && NativePatch.IsPrevious(Core.Hash(previous))) {
                    File.Copy(previous,Path.Combine(fixture,NativePatch.FileName));NativePatch.Prepare(fixture,recipe);
                    string backup=Directory.GetFiles(Path.Combine(fixture,"LauncherBackups"),"*.exe").Single();
                    if(Core.Hash(backup)!=Core.Hash(previous))throw new Exception("Prior trial backup failed");
                }
                string trial=NativePatch.Prepare(fixture,recipe);
                if(Core.Hash(trial)!=r.OutputHash || NativePatch.Prepare(fixture,recipe)!=trial)throw new Exception("Trial creation/reuse failed");
                string oldReplay=Path.Combine(fixture,"old.agr");
                using(var archive=System.IO.Compression.ZipFile.Open(oldReplay,System.IO.Compression.ZipArchiveMode.Create))
                using(var writer=new StreamWriter(archive.CreateEntry("manifest.json").Open()))writer.Write(Core.Json.Serialize(new ReplayInfo {Frames=1,Complete=true,ExecutableHash=NativePatch.LegacyOutputHash,Version="0.3.0-preview"}));
                string legacy=NativePatch.PrepareReplay(fixture,oldReplay);
                if(Core.Hash(legacy)!=NativePatch.LegacyOutputHash || NativePatch.PrepareReplay(fixture,oldReplay)!=legacy || Core.Hash(trial)!=r.OutputHash)throw new Exception("Legacy replay selection changed current patch");
                File.WriteAllBytes(legacy,new byte[]{1});rejected=false;
                try {NativePatch.PrepareReplay(fixture,oldReplay);}catch(IOException){rejected=true;}
                if(!rejected)throw new Exception("Unknown legacy replay executable accepted");
                File.WriteAllBytes(trial,new byte[]{1});rejected=false;
                try{NativePatch.Remove(fixture,recipe);}catch(IOException){rejected=true;}
                if(!rejected || !File.Exists(trial))throw new Exception("Foreign trial removal allowed");
                File.WriteAllBytes(trial,output);NativePatch.Remove(fixture,recipe);
                if(File.Exists(trial) || Core.Hash(Path.Combine(fixture,"Armageddon.exe"))!=NativePatch.InputHash)throw new Exception("Trial restore changed original");
            } finally {Directory.Delete(fixture,true);}
            Core.Log("NATIVE VERIFY PASS output="+r.OutputHash+"; modified input/recipe rejected; original unchanged");
        }
    }
}
