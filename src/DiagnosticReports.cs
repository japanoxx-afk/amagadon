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
        static Dictionary<long,Dictionary<int,string>> Units(string path,string record) {
            var result=new Dictionary<long,Dictionary<int,string>>();
            using(var zip=ZipFile.OpenRead(path)) {
                string name=record.Replace("sync-trace.json","unit-trace.json");var entry=zip.GetEntry(name);var binary=zip.GetEntry(name.Replace(".json",".dat"));
                if(entry==null || binary==null)return result;
                if(entry.Length>8*1024*1024 || binary.Length>8*1024*1024)throw new IOException("개별 유닛 기록 크기 제한 초과");
                Dictionary<string,object> doc;using(var reader=new StreamReader(entry.Open()))doc=Core.Json.Deserialize<Dictionary<string,object>>(reader.ReadToEnd());
                byte[] raw;using(var input=binary.Open())using(var buffer=new MemoryStream()){input.CopyTo(buffer);raw=buffer.ToArray();}
                foreach(object value in (System.Collections.IEnumerable)doc["frames"]) {
                    var row=(Dictionary<string,object>)value;long offset=Convert.ToInt64(row["offset"]),count=Convert.ToInt64(row["count"]);uint seq=Convert.ToUInt32(row["sequence"]);
                    if(offset<4096 || count<0 || count>1700 || offset+64+count*32>raw.Length)continue;
                    int o=(int)offset;if(BitConverter.ToUInt32(raw,o)!=seq || BitConverter.ToUInt32(raw,o+20)!=seq || BitConverter.ToUInt32(raw,o+8)!=Convert.ToUInt32(doc["generation"]))continue;
                    long clock=Convert.ToInt64(row["clock"]);if(BitConverter.ToUInt32(raw,o+4)!=clock || BitConverter.ToUInt32(raw,o+12)!=count)continue;
                    var units=new Dictionary<int,string>();
                    for(int i=0;i<count;i++) {int u=o+64+i*32,id=BitConverter.ToInt32(raw,u);if(id<0 || id>=1700)continue;
                        units[id]="종류="+BitConverter.ToUInt16(raw,u+4)+" 소유자="+raw[u+6]+" 활성="+raw[u+7]+" 위치=("+BitConverter.ToInt32(raw,u+8)+","+BitConverter.ToInt32(raw,u+12)+") 체력="+BitConverter.ToInt32(raw,u+16)+" 대상="+BitConverter.ToInt32(raw,u+20)+" 타이머="+BitConverter.ToInt32(raw,u+24)+" 명령="+raw[u+28]+" 상태="+raw[u+29]+","+raw[u+30]+","+raw[u+31];
                    }result[clock]=units;
                }
            }return result;
        }
        static readonly string[] StateFields={"자원1","자원2","건설대상","대기모드","건물종류","배치플래그","모드BC28","커서BCF4","커서BD48X","커서BD48Y","커서BE00X","커서BE00Y"};
        // Cursor-derived fields keep the local live cursor in idle frames, so they are
        // compared only on frames where that player's slot carries a command.
        static readonly HashSet<int> CursorFields=new HashSet<int>{5,6,7,8,9,10,11};
        static Dictionary<long,KeyValuePair<Dictionary<string,long>,HashSet<int>>> Hidden(string path,string record,out int version) {
            var result=new Dictionary<long,KeyValuePair<Dictionary<string,long>,HashSet<int>>>();version=0;
            using(var zip=ZipFile.OpenRead(path)) {
                var entry=zip.GetEntry(record);var binary=zip.GetEntry(record.Replace(".json",".dat"));if(entry==null || binary==null)return result;
                if(entry.Length>8*1024*1024 || binary.Length>8*1024*1024)throw new IOException("동기화 기록 크기 제한 초과");
                Dictionary<string,object> doc;using(var reader=new StreamReader(entry.Open()))doc=Core.Json.Deserialize<Dictionary<string,object>>(reader.ReadToEnd());
                byte[] raw;using(var input=binary.Open())using(var buffer=new MemoryStream()){input.CopyTo(buffer);raw=buffer.ToArray();}
                uint generation=Convert.ToUInt32(doc["generation"]);
                foreach(object item in (System.Collections.IEnumerable)doc["stableFrames"]) {
                    var row=(Dictionary<string,object>)item;long offset=Convert.ToInt64(row["offset"]);uint seq=Convert.ToUInt32(row["sequence"]);
                    if(offset<4096 || offset+2048>raw.Length)continue;int o=(int)offset;
                    if(BitConverter.ToUInt32(raw,o)!=seq || BitConverter.ToUInt32(raw,o+76)!=seq || BitConverter.ToUInt32(raw,o+88)!=generation)continue;
                    int h=o+1536;uint v=BitConverter.ToUInt32(raw,h+4);if(BitConverter.ToUInt32(raw,h)!=0x31545348 || (v!=1 && v!=2))continue;version=(int)Math.Max(version,v);
                    var values=new Dictionary<string,long>{{"격자상태",BitConverter.ToUInt32(raw,h+20)},{"mgr+711A",BitConverter.ToUInt32(raw,h+24)}};
                    for(int p=1;p<=8;p++) {
                        int b=h+32+(p-1)*44;long[] f={BitConverter.ToInt32(raw,b),BitConverter.ToInt32(raw,b+4),BitConverter.ToInt32(raw,b+8),BitConverter.ToInt32(raw,b+12),BitConverter.ToUInt16(raw,b+16),BitConverter.ToUInt16(raw,b+18),BitConverter.ToInt32(raw,b+20),BitConverter.ToInt32(raw,b+24),BitConverter.ToInt32(raw,b+28),BitConverter.ToInt32(raw,b+32),BitConverter.ToInt32(raw,b+36),BitConverter.ToInt32(raw,b+40)};
                        // 0.3.67 (v1) stored player p+1's 0x51BC28 value under p.
                        if(v==1)f[6]=p>1?BitConverter.ToInt32(raw,h+32+(p-2)*44+20):long.MinValue;
                        for(int i=0;i<f.Length;i++)if(f[i]!=long.MinValue)values["P"+p+"."+i]=f[i];
                    }
                    if(BitConverter.ToUInt32(raw,h+20)==1)for(int i=0;i<16;i++)values["격자띠"+i]=BitConverter.ToUInt32(raw,h+384+i*4);
                    var active=new HashSet<int>();for(int p=1;p<=8;p++){int packet=o+128+768+p*64;if(raw[packet]!=0 || BitConverter.ToUInt16(raw,packet+24)!=0)active.Add(p);}
                    result[Convert.ToInt64(row["clock"])]=new KeyValuePair<Dictionary<string,long>,HashSet<int>>(values,active);
                }
            }return result;
        }
        static string Label(string key) {
            if(!key.StartsWith("P") || key.IndexOf('.')<0)return key;
            int dot=key.IndexOf('.');return "플레이어"+key.Substring(1,dot-1)+" "+StateFields[int.Parse(key.Substring(dot+1))];
        }
        static string HiddenDetails(string left,string right,string l,string r) {
            int lv,rv;var a=Hidden(left,l,out lv);var b=Hidden(right,r,out rv);var clocks=a.Keys.Intersect(b.Keys).OrderBy(c=>c).ToArray();
            if(clocks.Length==0)return "숨은 상태 기록의 공통 프레임이 없습니다. 0.3.67 이전 버전이거나 기록이 없으면 비교할 수 없습니다 (같다는 뜻이 아님).";
            var first=new Dictionary<string,string>();int idle=0;
            foreach(long c in clocks)foreach(string key in a[c].Key.Keys.Intersect(b[c].Key.Keys)) {
                if(a[c].Key[key]==b[c].Key[key] || first.ContainsKey(key))continue;
                int dot=key.IndexOf('.');
                if(key.StartsWith("P") && dot>0 && CursorFields.Contains(int.Parse(key.Substring(dot+1)))) {int p=int.Parse(key.Substring(1,dot-1));if(!a[c].Value.Contains(p) && !b[c].Value.Contains(p)){idle++;continue;}}
                first[key]="프레임 "+c+" · "+Label(key)+" · 좌측="+a[c].Key[key]+" 우측="+b[c].Key[key];
            }
            var text=new StringBuilder("숨은 상태 공통 프레임 "+clocks.Length+"개 (기록 형식 v"+Math.Min(lv,rv)+"~v"+Math.Max(lv,rv)+")\r\n");
            if(first.Count==0)text.AppendLine("자원·건설대상·대기모드·격자 등 후보 항목의 차이가 없습니다.");
            foreach(var line in first.Values.OrderBy(x=>long.Parse(x.Split(' ')[1])).Take(40))text.AppendLine("후보 차이: "+line);
            text.AppendLine("명령 없는 프레임의 커서 파생값 차이 "+idle+"건은 로컬 커서 때문이며 후보에서 제외했습니다.");
            text.Append("후보 차이는 원인 확정이 아닙니다. 가장 이른 프레임과 직전 명령을 함께 확인하세요.");
            return text.ToString();
        }
        static string Version(string path,string record) {
            using(var zip=ZipFile.OpenRead(path)) {
                string[] parts=record.Split('/');int i=Array.IndexOf(parts,"Diagnostics");if(i<0 || i+1>=parts.Length)return null;
                var entry=zip.GetEntry(string.Join("/",parts.Take(i+2))+"/events.jsonl");if(entry==null)return null;
                using(var reader=new StreamReader(entry.Open()))for(int n=0;n<64;n++) {
                    string line=reader.ReadLine();if(line==null)break;
                    try {var e=Core.Json.Deserialize<Dictionary<string,object>>(line.TrimStart('﻿'));if(Convert.ToString(e["kind"])=="start")return Convert.ToString(((Dictionary<string,object>)e["data"])["version"]);}catch(Exception){}
                }
            }return null;
        }
        static string UnitDetails(string left,string right,string l,string r) {
            var a=Units(left,l);var b=Units(right,r);var clocks=a.Keys.Intersect(b.Keys).OrderBy(c=>c).ToArray();
            if(clocks.Length==0)return "개별 유닛의 공통 프레임이 없습니다. 구버전 또는 기록 누락일 수 있습니다.";
            foreach(long clock in clocks) {
                var ids=a[clock].Keys.Union(b[clock].Keys).Where(i=>!a[clock].ContainsKey(i)||!b[clock].ContainsKey(i)||a[clock][i]!=b[clock][i]).OrderBy(i=>i).ToArray();
                if(ids.Length==0)continue;
                var text=new StringBuilder("개별 유닛 최초 차이: 프레임 "+clock+" / "+ids.Length+"개 (최대 16개 표시)\r\n");
                foreach(long c in clocks.Where(c=>c>=clock-2 && c<=clock+2))foreach(int id in ids.Take(16)) {
                    text.AppendLine("프레임 "+c+" · 유닛 "+id);text.AppendLine("좌측: "+(a[c].ContainsKey(id)?a[c][id]:"없음"));text.AppendLine("우측: "+(b[c].ContainsKey(id)?b[c][id]:"없음"));
                }return text.ToString();
            }return "개별 유닛 공통 프레임 "+clocks.Length+"개에서 기록된 상태가 같습니다.";
        }
        static void ShowResult(IWin32Window owner,string text) {
            using(var dialog=new Form {Text="로깅 리포트 비교 결과",Width=1000,Height=700,StartPosition=FormStartPosition.CenterParent}) {
                var box=new TextBox {Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Both,WordWrap=false,Dock=DockStyle.Fill,Text=text};
                var save=new Button {Text="분석 결과 TXT 저장",Dock=DockStyle.Bottom,Height=36};save.Click+=delegate {using(var d=new SaveFileDialog {Filter="분석 결과|*.txt",FileName="Amagadon-Analysis.txt"})if(d.ShowDialog(dialog)==DialogResult.OK)try{File.WriteAllText(d.FileName,text,Encoding.UTF8);}catch(Exception ex){MessageBox.Show(dialog,ex.Message);}};
                dialog.Controls.Add(box);dialog.Controls.Add(save);dialog.ShowDialog(owner);
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
            var text=new StringBuilder();
            string lv=null,rv=null;try{lv=Version(left,leftRecord);rv=Version(right,rightRecord);}catch(Exception){}
            if(lv!=rv)text.AppendLine("주의: 양측 런처 버전이 다릅니다 ("+(lv??"알 수 없음")+" / "+(rv??"알 수 없음")+"). 런타임 패치가 다를 수 있으므로 같은 버전 경기로 다시 비교하세요.\r\n");
            text.AppendLine("공통 프레임 "+clocks.Length+"개 ("+clocks.First()+" ~ "+clocks.Last()+")");
            foreach(string key in new[]{"unitHash","orderHash","engineRngIndex"}) {
                long? first=clocks.Where(c=>a[c].ContainsKey(key)&&b[c].ContainsKey(key)&&Convert.ToString(a[c][key])!=Convert.ToString(b[c][key])).Select(c=>(long?)c).FirstOrDefault();
                text.AppendLine(first.HasValue?"최초 기록 차이: 프레임 "+first.Value+" / "+key+" · 좌측="+a[first.Value][key]+" 우측="+b[first.Value][key]:key+": 제공된 공통 기록은 같습니다 (누락 필드 제외).");
            }
            text.AppendLine("같은 경기인지 확인해주세요. 기록 범위 밖의 문제는 배제할 수 없으며, 상태 차이가 곧 원인은 아닙니다.");
            text.AppendLine("엔진 난수 인덱스와 PC별 CRT 난수는 구분합니다. 이 결과의 난수 비교는 엔진 인덱스 기준입니다.");
            try{text.AppendLine(UnitDetails(left,right,leftRecord,rightRecord));}catch(Exception ex){text.AppendLine("개별 유닛 분석 실패: "+ex.Message);}
            try{text.AppendLine(HiddenDetails(left,right,leftRecord,rightRecord));}catch(Exception ex){text.AppendLine("숨은 상태 분석 실패: "+ex.Message);}
            return text.ToString();
        }
        public static void Open(IWin32Window owner) {
            using(var form=new Form {Text="로깅 리포트 분석",Width=680,Height=260,StartPosition=FormStartPosition.CenterParent}) {
                var label=new Label {Left=20,Top=20,Width=620,Height=95,Text="로깅 리포트 ZIP 하나에 실행 로그와 자동 진단 기록이 함께 포함됩니다.\r\n동기화 오류는 게임이 살아 있는 동안 먼저 보존합니다. 자동 업로드는 하지 않습니다.\r\n양측 로깅 리포트 ZIP을 선택한 뒤 같은 경기의 실행 기록을 선택하세요.\r\nZIP에는 PC 경로와 충돌 메모리가 포함될 수 있습니다."};
                var folder=new Button {Text="자동 보존 기록 폴더",Left=20,Top=130,Width=200};folder.Click+=delegate {Directory.CreateDirectory(Home);System.Diagnostics.Process.Start("explorer.exe",Home);};
                var compare=new Button {Text="양측 ZIP 비교",Left=240,Top=130,Width=200};compare.Click+=delegate {using(var d=new OpenFileDialog {Filter="진단 ZIP|*.zip",Multiselect=true,Title="같은 경기의 양측 ZIP 2개 선택"})if(d.ShowDialog(form)==DialogResult.OK)try {if(d.FileNames.Length!=2)throw new InvalidOperationException("ZIP 2개를 선택해주세요.");string l=Choose(form,d.FileNames[0]);if(l==null)return;string r=Choose(form,d.FileNames[1]);if(r==null)return;ShowResult(form,Path.GetFileName(d.FileNames[0])+" : "+l+"\r\n"+Path.GetFileName(d.FileNames[1])+" : "+r+"\r\n\r\n"+Compare(d.FileNames[0],d.FileNames[1],l,r));}catch(Exception ex){MessageBox.Show(form,ex.Message,"비교 안내");}};
                form.Controls.AddRange(new Control[]{label,folder,compare});form.ShowDialog(owner);
            }
        }
    }
}
