using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace Amagadon {
    public sealed class ReleaseAsset { public string name; public string browser_download_url; }
    public sealed class LauncherRelease {
        public string tag_name; public bool draft,prerelease; public ReleaseAsset[] assets;
    }
    public static class Updates {
        public const string LatestUrl="https://api.github.com/repos/japanoxx-afk/amagadon/releases/latest";
        public static LauncherRelease Parse(string json) {
            // Typed arrays avoid JavaScriptSerializer's untyped ArrayList representation.
            var release=new JavaScriptSerializer().Deserialize<LauncherRelease>(json);
            Version version;
            if(release==null || release.draft || release.prerelease || release.tag_name==null ||
                !Regex.IsMatch(release.tag_name,@"^v?\d+\.\d+\.\d+$") ||
                !Version.TryParse(release.tag_name.TrimStart('v'),out version))throw new IOException("올바른 정식 릴리스 정보가 아닙니다.");
            return release;
        }
        static string Asset(LauncherRelease release,string name) {
            var matches=(release.assets??new ReleaseAsset[0]).Where(a=>a!=null && a.name==name).ToArray();
            if(matches.Length!=1)throw new IOException("업데이트 파일이 없거나 중복되었습니다: "+name);
            Uri uri;
            if(!Uri.TryCreate(matches[0].browser_download_url,UriKind.Absolute,out uri) || uri.Scheme!="https" || uri.Host!="github.com" || !uri.IsDefaultPort || uri.UserInfo!="" ||
                !uri.AbsolutePath.StartsWith("/japanoxx-afk/amagadon/releases/download/",StringComparison.Ordinal))throw new IOException("신뢰할 수 없는 업데이트 주소입니다.");
            return uri.AbsoluteUri;
        }
        // Both startup and button checks use this exact network/confirmation path.
        public static async Task<string> Prepare(HttpClient client,string current,string directory,Func<LauncherRelease,bool> confirm,Action<string> progress,CancellationToken token) {
            LauncherRelease release;
            using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(token)) {
                timeout.CancelAfter(TimeSpan.FromSeconds(15));
                using(var response=await client.GetAsync(LatestUrl,timeout.Token)) {
                    if(response.StatusCode==HttpStatusCode.NotFound) {progress("아직 배포된 업데이트가 없습니다.");return null;}
                    response.EnsureSuccessStatusCode();release=Parse(await response.Content.ReadAsStringAsync());
                }
            }
            token.ThrowIfCancellationRequested();
            if(new Version(release.tag_name.TrimStart('v'))<=new Version(current)) {progress("최신 버전입니다.");return null;}
            string zip=Asset(release,"AmagadonLauncher.zip"),sha=Asset(release,"AmagadonLauncher.zip.sha256");
            if(!confirm(release)) {progress("업데이트를 취소했습니다. 업데이트 버튼으로 다시 진행할 수 있습니다.");return null;}
            token.ThrowIfCancellationRequested();Directory.CreateDirectory(directory);
            string package=Path.Combine(directory,"AmagadonLauncher.zip"),partial=package+".partial";
            try {
                progress("업데이트 다운로드 중…");
                using(var response=await client.GetAsync(zip,token)) {response.EnsureSuccessStatusCode();File.WriteAllBytes(partial,await response.Content.ReadAsByteArrayAsync());}
                string hash;
                using(var response=await client.GetAsync(sha,token)) {response.EnsureSuccessStatusCode();hash=(await response.Content.ReadAsStringAsync()).Trim();}
                token.ThrowIfCancellationRequested();
                if(!Regex.IsMatch(hash,"^[0-9a-fA-F]{64}$") || !String.Equals(hash,Core.Hash(partial),StringComparison.OrdinalIgnoreCase))throw new IOException("업데이트 SHA-256 검증 실패");
                File.Move(partial,package);return package;
            } finally {if(File.Exists(partial))File.Delete(partial);}
        }
        public static async Task StartInstaller(string package,string target,string entrypoint,int pid,CancellationToken token) {
            string folder=Path.GetDirectoryName(package),session=Path.Combine(folder,"installer-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(session);
            string helper=Path.Combine(session,"apply-update.ps1"),ready=Path.Combine(session,"installer-ready.txt");
            using(var resource=typeof(Updates).Assembly.GetManifestResourceStream("Amagadon.UpdateInstaller"))using(var output=File.Create(helper))resource.CopyTo(output);
            string args="-NoProfile -ExecutionPolicy Bypass -File \""+helper+"\" -LauncherPid "+pid+" -Package \""+package+"\" -Target \""+Path.Combine(Path.GetFullPath(target),".")+"\" -CurrentEntrypoint \""+entrypoint+"\" -ReadyFile \""+ready+"\"";
            using(var installer=Process.Start(new ProcessStartInfo("powershell.exe",args){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden})) {
                // Do not exit the launcher until extraction and verification succeeded.
                var clock=Stopwatch.StartNew();
                while(clock.ElapsedMilliseconds<60000) {
                    token.ThrowIfCancellationRequested();
                    if(File.Exists(ready)) {
                        string result=File.ReadAllText(ready).Trim();
                        if(result=="ready") {token.ThrowIfCancellationRequested();File.WriteAllText(ready+".commit","install");return;}
                        if(result.StartsWith("failed:"))throw new IOException(result.Substring(7));
                    }
                    if(installer.HasExited)throw new IOException("업데이트 설치 도구가 종료되었습니다. "+Path.Combine(folder,"update-result.log"));
                    await Task.Delay(100,token);
                }
                throw new IOException("업데이트 설치 준비 시간이 초과되었습니다. "+Path.Combine(folder,"update-result.log"));
            }
        }
    }
}
