using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Collections.Generic;
using System.Text;
using System.Windows.Forms;
namespace Amagadon {
    public static class DiagnosticReports {
        public static readonly string Home=Path.Combine(Core.Home,"AutomaticReports");
        public static string SaveSession(string folder,string outcome) {
            Directory.CreateDirectory(Home);
            string destination=Path.Combine(Home,"Amagadon-Session-"+Path.GetFileName(folder)+".zip"),temp=destination+".partial";
            var notes=new StringBuilder();notes.AppendLine("아마게돈 "+Core.DisplayVersion+" / "+outcome);
            notes.AppendLine("이 ZIP은 한 번의 실행 기록입니다. 종료 코드 0도 정상적인 경기 종료를 보장하지 않습니다.");
            notes.AppendLine("양측 ZIP을 비교하면 같은 프레임의 최초 상태 차이를 확인할 수 있습니다. 원인 확정이나 자동 복구 기능은 아닙니다.");
            string trace=Path.Combine(folder,"sync-trace.json");
            if(File.Exists(trace))try {var metadata=Core.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(trace));notes.AppendLine("동결 프레임: "+metadata["freezeClock"]+" / 동결 사유 코드: "+metadata["freezeReason"]);notes.AppendLine("기록 계기: "+metadata["reason"]);}catch(Exception ex){notes.AppendLine("동기화 요약 읽기 실패: "+ex.Message);}
            long total=0;
            try {using(var zip=ZipFile.Open(temp,ZipArchiveMode.Create)) {
                foreach(string file in Directory.GetFiles(folder,"*",SearchOption.AllDirectories).OrderBy(f=>f.EndsWith(".dmp")?1:0)) {
                    string relative=file.Substring(folder.Length+1).Replace('\\','/');
                    if(file.EndsWith(".partial") || (File.GetAttributes(file)&FileAttributes.ReparsePoint)!=0)continue;
                    using(var input=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete)) {
                        if(input.Length>64L*1024*1024 || total+input.Length>128L*1024*1024){notes.AppendLine("용량 제한으로 제외: "+relative);continue;}
                        total+=input.Length;using(var output=zip.CreateEntry("Diagnostics/"+Path.GetFileName(folder)+"/"+relative,CompressionLevel.Optimal).Open())input.CopyTo(output);
                    }
                }
                notes.AppendLine(File.Exists(Path.Combine(folder,"unit-trace.json"))?"개별 유닛 이력 포함":"개별 유닛 이력 없음: 멀티플레이 미진입 또는 수집 실패 가능");
                using(var writer=new StreamWriter(zip.CreateEntry("summary.txt").Open(),Encoding.UTF8))writer.Write(notes.ToString());
            }File.Copy(temp,destination,true);return destination;}finally{if(File.Exists(temp))File.Delete(temp);}
        }
        static Dictionary<long,Dictionary<string,object>> Frames(string path) {
            using(var zip=ZipFile.OpenRead(path)) {
                var entries=zip.Entries.Where(e=>e.FullName.EndsWith("/sync-trace.json",StringComparison.OrdinalIgnoreCase) && e.FullName.IndexOf("/SyncTrace/",StringComparison.OrdinalIgnoreCase)<0).ToArray();
                if(entries.Length!=1)throw new InvalidOperationException("실행/동결 기록이 여러 개이거나 없습니다. 비교할 단일 기록을 포함하는 ZIP이 필요합니다. 자동 ZIP은 분석용 원본으로 보관해주세요.");
                using(var reader=new StreamReader(entries[0].Open())) {
                    var doc=Core.Json.Deserialize<Dictionary<string,object>>(reader.ReadToEnd());
                    var result=new Dictionary<long,Dictionary<string,object>>();
                    foreach(object item in (System.Collections.IEnumerable)doc["stableFrames"]) {var f=(Dictionary<string,object>)item;result[Convert.ToInt64(f["clock"])]=f;}return result;
                }
            }
        }
        public static string Compare(string left,string right) {
            var a=Frames(left);var b=Frames(right);var clocks=a.Keys.Intersect(b.Keys).OrderBy(x=>x).ToArray();
            if(clocks.Length==0)return "공통 프레임이 없습니다. 같은 경기의 양측 리포트인지 확인해주세요.";
            foreach(long clock in clocks)foreach(string key in new[]{"unitHash","orderHash","engineRngIndex"})if(a[clock].ContainsKey(key)&&b[clock].ContainsKey(key)&&Convert.ToString(a[clock][key])!=Convert.ToString(b[clock][key]))return "최초 기록 차이: 프레임 "+clock+" / "+key+"\r\n좌측: "+a[clock][key]+" / 우측: "+b[clock][key]+"\r\n공통 프레임 "+clocks.Length+"개. 같은 경기인지 확인이 필요하며, 상태 차이가 곧 원인은 아닙니다.";
            return "공통 프레임 "+clocks.Length+"개의 유닛·명령 지문과 엔진 난수 인덱스가 같습니다. 기록 범위 밖의 문제는 배제할 수 없습니다.";
        }
        public static void Open(IWin32Window owner) {
            using(var form=new Form {Text="자동 진단 리포트",Width=680,Height=260,StartPosition=FormStartPosition.CenterParent}) {
                var label=new Label {Left=20,Top=20,Width=620,Height=95,Text="진단 기록이 켜져 있으면 실행 종료 후 해당 실행의 ZIP을 자동 저장합니다.\r\n동기화 오류는 게임이 살아 있는 동안 먼저 보존합니다. 자동 업로드는 하지 않습니다.\r\n같은 경기의 양측 ZIP을 선택해 기록 차이를 비교할 수 있습니다.\r\nZIP에는 PC 경로와 충돌 메모리가 포함될 수 있습니다."};
                var folder=new Button {Text="자동 ZIP 폴더",Left=20,Top=130,Width=200};folder.Click+=delegate {Directory.CreateDirectory(Home);System.Diagnostics.Process.Start("explorer.exe",Home);};
                var compare=new Button {Text="양측 ZIP 비교",Left=240,Top=130,Width=200};compare.Click+=delegate {using(var d=new OpenFileDialog {Filter="진단 ZIP|*.zip",Multiselect=true,Title="같은 경기의 양측 ZIP 2개 선택"})if(d.ShowDialog(form)==DialogResult.OK)try {if(d.FileNames.Length!=2)throw new InvalidOperationException("ZIP 2개를 선택해주세요.");MessageBox.Show(form,Compare(d.FileNames[0],d.FileNames[1]),"비교 결과");}catch(Exception ex){MessageBox.Show(form,ex.Message,"비교 안내");}};
                form.Controls.AddRange(new Control[]{label,folder,compare});form.ShowDialog(owner);
            }
        }
    }
}
