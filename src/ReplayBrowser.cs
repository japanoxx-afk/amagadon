using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
namespace Amagadon {
    public sealed class ReplayBrowser : Form {
        readonly ListView list=new ListView(); readonly Label message=new Label();
        public string SelectedReplay {get;private set;}
        public ReplayBrowser() {
            Text="아마게돈 리플레이 · 더블클릭하여 재생";Size=new Size(860,480);MinimumSize=new Size(700,350);StartPosition=FormStartPosition.CenterParent;
            Font=new Font("맑은 고딕",10);
            var actions=new FlowLayoutPanel {Dock=DockStyle.Bottom,Height=48,Padding=new Padding(8),FlowDirection=FlowDirection.RightToLeft};
            var play=new Button {Text="선택 재생",AutoSize=true};play.Click+=delegate {Choose();};actions.Controls.Add(play);
            var refresh=new Button {Text="새로고침",AutoSize=true};refresh.Click+=delegate {Reload();};actions.Controls.Add(refresh);
            var browse=new Button {Text="다른 파일…",AutoSize=true};browse.Click+=delegate {using(var dialog=new OpenFileDialog {Filter="아마게돈 리플레이 (*.agr)|*.agr",InitialDirectory=ReplayFiles.Home})if(dialog.ShowDialog(this)==DialogResult.OK) {SelectedReplay=dialog.FileName;DialogResult=DialogResult.OK;}};actions.Controls.Add(browse);
            message.Dock=DockStyle.Bottom;message.Height=32;message.Padding=new Padding(10,4,0,0);
            list.Dock=DockStyle.Fill;list.View=View.Details;list.FullRowSelect=true;list.MultiSelect=false;list.HideSelection=false;
            list.Columns.Add("기록 시간",180);list.Columns.Add("맵",250);list.Columns.Add("프레임",85);list.Columns.Add("버전 / 상태",260);
            list.DoubleClick+=delegate {Choose();};list.KeyDown+=delegate(object sender,KeyEventArgs e) {if(e.KeyCode==Keys.Enter) {e.Handled=true;Choose();}};
            Controls.Add(list);Controls.Add(message);Controls.Add(actions);Reload();
        }
        void Choose() {
            if(list.SelectedItems.Count==0)return;
            var path=list.SelectedItems[0].Tag as string;
            if(path==null) {message.Text="손상되었거나 완료되지 않은 기록은 재생할 수 없습니다.";return;}
            SelectedReplay=path;DialogResult=DialogResult.OK;
        }
        void Reload() {
            Directory.CreateDirectory(ReplayFiles.Home);list.Items.Clear();var files=new DirectoryInfo(ReplayFiles.Home).GetFiles("*.agr");
            Array.Sort(files,(a,b)=>b.LastWriteTimeUtc.CompareTo(a.LastWriteTimeUtc));
            foreach(var file in files) {
                var row=new ListViewItem(file.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss"));
                try {
                    var info=ReplayFiles.Inspect(file.FullName);DateTime created;
                    if(DateTime.TryParse(info.CreatedUtc,null,System.Globalization.DateTimeStyles.RoundtripKind,out created))row.Text=created.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss");
                    row.SubItems.Add(info.MapName??file.Name);row.SubItems.Add(info.Frames.ToString("N0"));row.SubItems.Add(info.Version??"알 수 없음");row.Tag=file.FullName;
                } catch(Exception ex) {row.SubItems.Add(file.Name);row.SubItems.Add("—");row.SubItems.Add(ex.Message);row.ForeColor=Color.Firebrick;}
                list.Items.Add(row);
            }
            message.Text=files.Length==0?"저장된 리플레이가 없습니다. 싱글플레이 게임을 기록해주세요.":files.Length+"개 · 더블클릭 또는 Enter로 재생합니다.";
            if(list.Items.Count>0)list.Items[0].Selected=true;
        }
    }
}
