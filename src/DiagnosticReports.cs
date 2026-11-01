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
                File.WriteAllText(Path.Combine(folder,"session-summary.txt"),notes.ToString(),Encoding.UTF8);
                using(var writer=new StreamWriter(zip.CreateEntry("summary.txt").Open(),Encoding.UTF8))writer.Write(notes.ToString());
            }File.Copy(temp,destination,true);return destination;}finally{if(File.Exists(temp))File.Delete(temp);}
        }
        public static void MergeAutomatic(ZipArchive target,List<object> index,HashSet<string> names,ref long total) {
            if(!Directory.Exists(Home))return;
            foreach(string file in Directory.GetFiles(Home,"Amagadon-Session-*.zip").OrderByDescending(File.GetLastWriteTimeUtc))try {
                using(var source=ZipFile.OpenRead(file))foreach(var entry in source.Entries) {
                    string name=entry.FullName;
                    if(name=="summary.txt")name="Diagnostics/"+Path.GetFileNameWithoutExtension(file).Substring("Amagadon-Session-".Length)+"/session-summary.txt";
                    if(!name.StartsWith("Diagnostics/",StringComparison.Ordinal) || name.Contains("..") || name.Contains("\\") || name.EndsWith("/") || names.Contains(name))continue;
                    if(entry.Length>64L*1024*1024 || total+entry.Length>512L*1024*1024){index.Add(new {file=name,status="skipped-automatic-size-limit"});continue;}
                    using(var input=entry.Open())using(var output=target.CreateEntry(name,CompressionLevel.Optimal).Open()) {long remaining=entry.Length;byte[] buffer=new byte[65536];while(remaining>0){int n=input.Read(buffer,0,(int)Math.Min(buffer.Length,remaining));if(n==0)throw new IOException("Truncated diagnostic archive");output.Write(buffer,0,n);remaining-=n;}}
                    total+=entry.Length;names.Add(name);index.Add(new {file=name,status="included-automatic-backup",bytes=entry.Length});
                }
            }catch(Exception ex){index.Add(new {file=Path.GetFileName(file),status="automatic-merge-failed",error=ex.Message});}
        }
        public static string[] Records(string path) {
            using(var zip=ZipFile.OpenRead(path))return zip.Entries.Where(e=>e.FullName.EndsWith("/sync-trace.json",StringComparison.OrdinalIgnoreCase)).Select(e=>e.FullName).OrderByDescending(n=>n,StringComparer.Ordinal).ToArray();
        }
        static Dictionary<long,Dictionary<string,object>> Frames(string path,string record) {
            using(var zip=ZipFile.OpenRead(path)) {
                using(var reader=new StreamReader(zip.GetEntry(record).Open())) {
                    if(zip.GetEntry(record).Length>8*1024*1024)throw new IOException("진단 인덱스가 너무 큽니다.");
                    var doc=Core.Json.Deserialize<Dictionary<string,object>>(reader.ReadToEnd());
                    var result=new Dictionary<long,Dictionary<string,object>>();
                    foreach(object item in (System.Collections.IEnumerable)doc["stableFrames"]) {var f=(Dictionary<string,object>)item;result[Convert.ToInt64(f["clock"])]=f;}return result;
                }
            }
        }
        static string Choose(IWin32Window owner,string path) {
            string[] records=Records(path);if(records.Length==0)throw new InvalidOperationException("동기화 기록이 없습니다: "+Path.GetFileName(path));if(records.Length==1)return records[0];
            using(var dialog=new Form {Text=Path.GetFileName(path)+" · 비교할 실행/동결 기록 선택",Width=850,Height=340,StartPosition=FormStartPosition.CenterParent}) {
                var list=new ListBox {Dock=DockStyle.Fill,HorizontalScrollbar=true};list.Items.AddRange(records);list.SelectedIndex=0;
                var ok=new Button {Text="이 기록 비교",Dock=DockStyle.Bottom,DialogResult=DialogResult.OK};dialog.Controls.Add(list);dialog.Controls.Add(ok);dialog.AcceptButton=ok;
                return dialog.ShowDialog(owner)==DialogResult.OK?(string)list.SelectedItem:null;
            }
        }
        public static string Compare(string left,string right) {
            var l=Records(left);var r=Records(right);if(l.Length!=1 || r.Length!=1)throw new InvalidOperationException("여러 실행이 포함되어 있습니다. 런처에서 비교할 실행을 선택해주세요.");return Compare(left,right,l[0],r[0]);
        }
        public static string Compare(string left,string right,string leftRecord,string rightRecord) {
            var a=Frames(left,leftRecord);var b=Frames(right,rightRecord);var clocks=a.Keys.Intersect(b.Keys).OrderBy(x=>x).ToArray();
            if(clocks.Length==0)return "공통 프레임이 없습니다. 같은 경기의 양측 리포트인지 확인해주세요.";
            foreach(long clock in clocks)foreach(string key in new[]{"unitHash","orderHash","engineRngIndex"})if(a[clock].ContainsKey(key)&&b[clock].ContainsKey(key)&&Convert.ToString(a[clock][key])!=Convert.ToString(b[clock][key]))return "최초 기록 차이: 프레임 "+clock+" / "+key+"\r\n좌측: "+a[clock][key]+" / 우측: "+b[clock][key]+"\r\n공통 프레임 "+clocks.Length+"개. 같은 경기인지 확인이 필요하며, 상태 차이가 곧 원인은 아닙니다.";
            return "공통 프레임 "+clocks.Length+"개의 유닛·명령 지문과 엔진 난수 인덱스가 같습니다. 기록 범위 밖의 문제는 배제할 수 없습니다.";
        }
        public static void Open(IWin32Window owner) {
            using(var form=new Form {Text="로깅 리포트 분석",Width=680,Height=260,StartPosition=FormStartPosition.CenterParent}) {
                var label=new Label {Left=20,Top=20,Width=620,Height=95,Text="로깅 리포트 ZIP 하나에 실행 로그와 자동 진단 기록이 함께 포함됩니다.\r\n동기화 오류는 게임이 살아 있는 동안 먼저 보존합니다. 자동 업로드는 하지 않습니다.\r\n양측 로깅 리포트 ZIP을 선택한 뒤 같은 경기의 실행 기록을 선택하세요.\r\nZIP에는 PC 경로와 충돌 메모리가 포함될 수 있습니다."};
                var folder=new Button {Text="자동 보존 기록 폴더",Left=20,Top=130,Width=200};folder.Click+=delegate {Directory.CreateDirectory(Home);System.Diagnostics.Process.Start("explorer.exe",Home);};
                var compare=new Button {Text="양측 ZIP 비교",Left=240,Top=130,Width=200};compare.Click+=delegate {using(var d=new OpenFileDialog {Filter="진단 ZIP|*.zip",Multiselect=true,Title="같은 경기의 양측 ZIP 2개 선택"})if(d.ShowDialog(form)==DialogResult.OK)try {if(d.FileNames.Length!=2)throw new InvalidOperationException("ZIP 2개를 선택해주세요.");string l=Choose(form,d.FileNames[0]);if(l==null)return;string r=Choose(form,d.FileNames[1]);if(r==null)return;MessageBox.Show(form,l+"\r\n"+r+"\r\n\r\n"+Compare(d.FileNames[0],d.FileNames[1],l,r),"비교 결과");}catch(Exception ex){MessageBox.Show(form,ex.Message,"비교 안내");}};
                form.Controls.AddRange(new Control[]{label,folder,compare});form.ShowDialog(owner);
            }
        }
    }
}
