using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Windows.Forms;

namespace Amagadon {
    public sealed class CrazyZoneHost : IDisposable {
        public CrazyZoneServer Server;
        public void Dispose() {if(Server!=null) {Server.Dispose();Server=null;}}
    }
    sealed class CrazyZoneWindow : Form {
        readonly CrazyZoneHost host;
        readonly TextBox address=new TextBox(),advertise=new TextBox();
        readonly NumericUpDown port=new NumericUpDown();
        readonly Label state=new Label();readonly Button start=new Button(),stop=new Button();
        readonly Timer timer=new Timer();
        public string Address {get {return address.Text.Trim();}}
        public int Port {get {return (int)port.Value;}}
        public CrazyZoneWindow(CrazyZoneHost host,Settings settings) {
            this.host=host;Text="Crazy Zone · 멀티플레이 서버";Font=new Font("맑은 고딕",10);AutoScaleMode=AutoScaleMode.None;
            ClientSize=new Size(690,510);MinimumSize=new Size(640,520);StartPosition=FormStartPosition.CenterParent;
            Controls.Add(new Label {Text="CRAZY ZONE",Font=new Font("Segoe UI",22,FontStyle.Bold),Location=new Point(24,16),AutoSize=true});
            Controls.Add(new Label {Text="서버를 여는 PC에서 서버 시작을 누르세요. 다른 플레이어도 같은 서버 주소를 사용합니다.",Location=new Point(24,70),Size=new Size(640,40)});
            LabelAt("접속할 서버 IPv4",24,118);address.SetBounds(24,145,360,30);address.Text=String.IsNullOrEmpty(settings.ZoneAddress)?"127.0.0.1":settings.ZoneAddress;Controls.Add(address);
            LabelAt("TCP 포트",410,118);port.SetBounds(410,145,230,30);port.Minimum=1024;port.Maximum=65535;port.Value=settings.ZonePort>=1024 && settings.ZonePort<=65535?settings.ZonePort:9000;Controls.Add(port);
            LabelAt("이 PC의 방 접속 주소 (LAN 또는 VPN IPv4)",24,191);advertise.SetBounds(24,218,360,30);advertise.Text=LocalAddress();Controls.Add(advertise);
            start.Text="서버 시작";start.SetBounds(24,268,176,42);Controls.Add(start);
            stop.Text="서버 종료";stop.SetBounds(216,268,176,42);Controls.Add(stop);
            var logs=new Button {Text="서버 로그 폴더",Location=new Point(408,268),Size=new Size(232,42)};Controls.Add(logs);
            state.SetBounds(24,323,616,40);Controls.Add(state);
            Controls.Add(new Label {Text="게임에서 Multi Play → Crazy Zone → Amagadon Private Zone을 선택하세요.\r\n로그인: 영문·숫자·_·- 아이디 1~19자 / 비밀번호 1~9바이트. 새 계정 등록 또는 첫 로그인으로 계정을 만듭니다.\r\n대기실에서 Lobby에 입장한 뒤 방을 만들거나 참가하세요. 같은 LAN/VPN에서 먼저 사용하세요.\r\n전투는 기존 DirectPlay TCP 연결을 사용하므로 방장의 PC에도 연결할 수 있어야 합니다.",Location=new Point(24,369),Size=new Size(640,92),Font=new Font("맑은 고딕",9)});
            var launch=new Button {Text="이 서버로 게임 실행",Location=new Point(408,466),Size=new Size(232,34)};Controls.Add(launch);
            launch.Click+=delegate {try {CrazyZonePatch.Validate(Address,Port);DialogResult=DialogResult.OK;Close();}catch(Exception ex){MessageBox.Show(this,ex.Message,"서버 주소 확인");}};
            start.Click+=delegate {try {
                CrazyZonePatch.Validate(advertise.Text.Trim(),Port);
                var server=new CrazyZoneServer(CrazyZoneServer.Home,advertise.Text.Trim());
                try {server.Start(IPAddress.Any,Port);}catch {server.Dispose();throw;}
                host.Server=server;RefreshStatus();
            }catch(Exception ex){Core.Log("Crazy Zone start: "+ex);MessageBox.Show(this,ex.Message,"서버 시작 실패");}};
            stop.Click+=delegate {host.Dispose();RefreshStatus();};
            logs.Click+=delegate {Directory.CreateDirectory(CrazyZoneServer.Home);System.Diagnostics.Process.Start("explorer.exe",CrazyZoneServer.Home);};
            timer.Interval=1000;timer.Tick+=delegate {RefreshStatus();};timer.Start();FormClosed+=delegate {timer.Dispose();};RefreshStatus();
            float scale;using(var graphics=CreateGraphics())scale=Math.Max(1.15f,graphics.DpiX/96f);Scale(new SizeF(scale,scale));
            var work=Screen.FromControl(this).WorkingArea;Size=new Size(Math.Min(Width,work.Width),Math.Min(Height,work.Height));
        }
        void LabelAt(string text,int x,int y) {Controls.Add(new Label {Text=text,Location=new Point(x,y),AutoSize=true});}
        void RefreshStatus() {bool running=host.Server!=null;state.Text=running?host.Server.Status:"서버가 중지되어 있습니다.";start.Enabled=!running;stop.Enabled=running;port.Enabled=advertise.Enabled=!running;}
        static string LocalAddress() {
            try {return NetworkInterface.GetAllNetworkInterfaces().Where(n=>n.OperationalStatus==OperationalStatus.Up && n.NetworkInterfaceType!=NetworkInterfaceType.Loopback).SelectMany(n=>n.GetIPProperties().UnicastAddresses).Select(a=>a.Address).First(a=>a.AddressFamily==AddressFamily.InterNetwork && !IPAddress.IsLoopback(a)).ToString();}catch {return "127.0.0.1";}
        }
    }
}
