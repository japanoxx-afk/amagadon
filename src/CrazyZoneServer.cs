using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Amagadon {
    // Crazy Zone 1.15 compatibility lobby. Gameplay uses the client's DirectPlay TCP provider.
    public sealed class CrazyZoneServer : IDisposable {
        public static readonly string Home=Path.Combine(Core.Home,"CrazyZone");
        static readonly Encoding Korean=Encoding.GetEncoding(949);
        readonly object gate=new object(),logGate=new object();
        readonly string directory,advertise;
        readonly Dictionary<string,Account> accounts=new Dictionary<string,Account>(StringComparer.OrdinalIgnoreCase);
        readonly List<Client> clients=new List<Client>();
        readonly Dictionary<int,Room> rooms=new Dictionary<int,Room>();
        readonly Dictionary<string,string> channels=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase) {{"Lobby",""}};
        TcpListener listener;Task acceptTask;Timer heartbeat;volatile bool stopping;
        int nextRoom=1,nextClient;
        public int Port {get;private set;}
        public string LogPath {get;private set;}
        public sealed class Account {public string Name,Salt,Digest;}
        sealed class Room {public int Id;public Client Host;public string Title,Password,Channel;public byte[] Native;public bool Playing;public HashSet<Client> Members=new HashSet<Client>();}
        sealed class Client {
            public int Id;public TcpClient Socket;public NetworkStream Stream;public string Name,Channel="Lobby",IP;public int Room;
            public bool Users,Rooms;public readonly object SendGate=new object();
            public readonly Queue<byte[]> Outgoing=new Queue<byte[]>();public int Queued;public bool Sending;
        }
        public CrazyZoneServer(string directory,string advertisedAddress) {
            this.directory=directory;advertise=advertisedAddress;
            if(!String.IsNullOrEmpty(advertise))CrazyZonePatch.Validate(advertise,9000);
        }
        public void Start(IPAddress bind,int port) {
            if(listener!=null)throw new InvalidOperationException("서버가 이미 실행 중입니다.");
            if(bind.AddressFamily!=AddressFamily.InterNetwork)throw new ArgumentException("IPv4 바인딩만 지원합니다.");
            if(port!=0 && (port<1024 || port>65535))throw new ArgumentException("서버 포트가 잘못되었습니다.");
            Directory.CreateDirectory(directory);
            string file=Path.Combine(directory,"accounts.json");
            if(File.Exists(file))foreach(Account a in Core.Json.Deserialize<Account[]>(File.ReadAllText(file))) {
                if(!ValidName(a.Name) || Convert.FromBase64String(a.Salt).Length!=24 || Convert.FromBase64String(a.Digest).Length!=32)throw new IOException("Crazy Zone 계정 파일이 손상됐습니다.");
                accounts.Add(a.Name,a);
            }
            var socket=new TcpListener(bind,port);
            try {socket.Start(24);}catch {socket.Stop();throw;}
            listener=socket;Port=((IPEndPoint)socket.LocalEndpoint).Port;
            LogPath=Path.Combine(directory,"server-"+DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")+".jsonl");
            Log("start",new {version=Core.Version,bind=bind.ToString(),port=Port,advertise=advertise,transport="native DirectPlay TCP",maxClients=24});
            acceptTask=Task.Run((Action)Accept);
            heartbeat=new Timer(delegate {lock(gate) {if(!stopping)foreach(var c in clients.ToArray())Send(c,new byte[]{88});}},null,30000,30000);
        }
        void Log(string kind,object data) {
            try {lock(logGate) {
                if(LogPath==null)return;
                if(File.Exists(LogPath) && new FileInfo(LogPath).Length>4*1024*1024) {File.Copy(LogPath,LogPath+".1",true);File.WriteAllText(LogPath,"");}
                File.AppendAllText(LogPath,Core.Json.Serialize(new {time=DateTime.Now.ToString("o"),kind=kind,data=data})+Environment.NewLine,Encoding.UTF8);
            }}catch(Exception ex) {Core.Log("Crazy Zone logging: "+ex.Message);}
        }
        public string Status {get {lock(gate)return listener==null?"서버 중지됨":"TCP "+Port+" · 접속 "+clients.Count+"명 · 대기 방 "+rooms.Values.Count(r=>!r.Playing)+"개";}}
        void Accept() {
            while(!stopping) {
                TcpClient socket;
                try {socket=listener.AcceptTcpClient();}catch(Exception ex) {if(!stopping)Log("accept-error",new {error=ex.Message});break;}
                lock(gate) {
                    if(stopping || clients.Count>=24) {socket.Close();continue;}
                    socket.NoDelay=true;socket.SendTimeout=1500;socket.ReceiveTimeout=120000;
                    var c=new Client {Id=++nextClient,Socket=socket,Stream=socket.GetStream(),IP=((IPEndPoint)socket.Client.RemoteEndPoint).Address.ToString()};
                    clients.Add(c);Log("connect",new {client=c.Id,ip=c.IP});Task.Run(()=>Serve(c));
                }
            }
        }
        public static byte[] Exact(Stream stream,int size) {
            if(size<0 || size>1024)throw new InvalidDataException("Invalid Crazy Zone field size");
            byte[] result=new byte[size];int done=0;
            while(done<size) {int n=stream.Read(result,done,size-done);if(n==0)throw new EndOfStreamException();done+=n;}
            return result;
        }
        static byte[] Field(Stream stream,int maximum) {
            int n=BitConverter.ToInt32(Exact(stream,4),0);
            if(n<0 || n>maximum)throw new InvalidDataException("Crazy Zone field exceeds client limit");
            return Exact(stream,n);
        }
        static string Text(byte[] bytes) {return Korean.GetString(bytes).Split('\0')[0];}
        static bool ValidName(string name) {return !String.IsNullOrEmpty(name) && name.Length<=19 && name.All(c=>c>='A'&&c<='Z'||c>='a'&&c<='z'||c>='0'&&c<='9'||c=='_'||c=='-');}
        static byte[] Join(params byte[][] parts) {int length=parts.Sum(p=>p.Length);byte[] result=new byte[length];int offset=0;foreach(var p in parts){Buffer.BlockCopy(p,0,result,offset,p.Length);offset+=p.Length;}return result;}
        public static byte[] Blob(int op,byte[] body) {
            if(body.Length>299)throw new InvalidDataException("Crazy Zone reply exceeds native 300-byte buffer");
            return Join(new[]{(byte)op},BitConverter.GetBytes(body.Length),body);
        }
        static byte[] Fixed(string value,int length) {byte[] text=Korean.GetBytes(value),result=new byte[length];if(text.Length>=length)throw new InvalidDataException("Crazy Zone text too long");Buffer.BlockCopy(text,0,result,0,text.Length);return result;}
        void Send(Client c,byte[] bytes) {
            lock(c.SendGate) {
                if(c.Queued+bytes.Length>65536) {c.Socket.Close();return;}
                c.Outgoing.Enqueue(bytes);c.Queued+=bytes.Length;
                if(c.Sending)return;c.Sending=true;
            }
            Task.Run(delegate {
                try {while(true) {
                    byte[] next;
                    lock(c.SendGate) {if(c.Outgoing.Count==0) {c.Sending=false;return;}next=c.Outgoing.Dequeue();c.Queued-=next.Length;}
                    c.Stream.Write(next,0,next.Length);
                }}catch(Exception) {c.Socket.Close();lock(c.SendGate) {c.Outgoing.Clear();c.Queued=0;c.Sending=false;}}
            });
        }
        void Reply(Client c,int op,int value) {Send(c,new[]{(byte)op,(byte)value});}
        void RequireLogin(Client c) {if(c.Name==null)throw new InvalidDataException("Login required");}
        void Serve(Client c) {
            try {
                // 93 means ready/current version; 92 would invoke the old updater.
                Send(c,new byte[]{93});
                int packets=0;DateTime window=DateTime.UtcNow;
                while(!stopping) {
                    byte[] encoded=Exact(c.Stream,4);
                    int salt=unchecked((short)(BitConverter.ToInt16(encoded,2)+4443));
                    int op=unchecked((short)(BitConverter.ToInt16(encoded,0)-salt));
                    if(salt<0 || salt>=10000 || op<1 || op>94)throw new InvalidDataException("Invalid Crazy Zone command header");
                    if((DateTime.UtcNow-window).TotalSeconds>=1) {window=DateTime.UtcNow;packets=0;}
                    if(++packets>200)throw new InvalidDataException("Crazy Zone request rate exceeded");
                    Handle(c,op);
                    // Credentials, chats and raw packets are never written to the report.
                    Log("command",new {client=c.Id,op=op});
                }
            } catch(EndOfStreamException) {}catch(Exception ex) {if(!stopping)Log("client-error",new {client=c.Id,type=ex.GetType().Name,error=ex.Message});}
            finally {
                lock(gate) {LeaveRoom(c);if(c.Name!=null)BroadcastUser(c,0);clients.Remove(c);}
                c.Socket.Close();Log("disconnect",new {client=c.Id});
            }
        }
        int Authenticate(string name,string password,bool register) {
            if(!ValidName(name) || password.Length<1 || Korean.GetByteCount(password)>9)return 1;
            Account a;
            if(!accounts.TryGetValue(name,out a)) {
                byte[] salt=new byte[24];using(var rng=RandomNumberGenerator.Create())rng.GetBytes(salt);
                byte[] hash;using(var kdf=new Rfc2898DeriveBytes(password,salt,100000))hash=kdf.GetBytes(32);
                a=new Account{Name=name,Salt=Convert.ToBase64String(salt),Digest=Convert.ToBase64String(hash)};
                accounts.Add(name,a);
                try {string target=Path.Combine(directory,"accounts.json"),temp=target+".tmp";File.WriteAllText(temp,Core.Json.Serialize(accounts.Values.ToArray()));if(File.Exists(target))File.Replace(temp,target,null);else File.Move(temp,target);}
                catch {accounts.Remove(name);throw;}
                return 0;
            }
            if(register)return 1;
            byte[] actual;using(var kdf=new Rfc2898DeriveBytes(password,Convert.FromBase64String(a.Salt),100000))actual=kdf.GetBytes(32);
            byte[] expected=Convert.FromBase64String(a.Digest);int difference=0;for(int i=0;i<actual.Length;i++)difference|=actual[i]^expected[i];return difference==0?0:2;
        }
        void BroadcastUser(Client user,byte action) {
            if(user.Name==null)return;
            byte[] body=Join(new[]{action,(byte)17},BitConverter.GetBytes(0),Korean.GetBytes(user.Name+"\0"));
            foreach(Client c in clients.Where(x=>x.Name!=null && x.Users && x.Channel.Equals(user.Channel,StringComparison.OrdinalIgnoreCase)).ToArray())Send(c,Blob(16,body));
        }
        byte[] RoomRecord(Room room,byte action) {
            byte[] b=new byte[115];b[0]=action;
            Buffer.BlockCopy(room.Native,0,b,1,33);Buffer.BlockCopy(room.Native,46,b,34,34);
            Buffer.BlockCopy(room.Native,80,b,68,7);
            Buffer.BlockCopy(Fixed(HostIP(room),20),0,b,75,20);Buffer.BlockCopy(Fixed(room.Host.Name,20),0,b,95,20);
            return b;
        }
        string HostIP(Room room) {return IPAddress.IsLoopback(IPAddress.Parse(room.Host.IP)) && !String.IsNullOrEmpty(advertise)?advertise:room.Host.IP;}
        void BroadcastRoom(Room room,byte action) {
            foreach(Client c in clients.Where(x=>x.Name!=null && x.Rooms && x.Channel.Equals(room.Channel,StringComparison.OrdinalIgnoreCase)).ToArray())Send(c,Blob(79,RoomRecord(room,action)));
        }
        void LeaveRoom(Client c) {
            Room room;if(c.Room==0 || !rooms.TryGetValue(c.Room,out room)) {c.Room=0;return;}
            room.Members.Remove(c);c.Room=0;
            if(room.Host==c) {BroadcastRoom(room,0);rooms.Remove(room.Id);foreach(var member in room.Members)member.Room=0;}
        }
        void Handle(Client c,int op) {
            // Read the complete command before taking the world lock: a partial TCP write must not block other clients.
            byte[][] f;byte[] raw;
            switch(op) {
                case 2: Field(c.Stream,64);return; // original version string
                case 70: Field(c.Stream,1);return; // original product byte
                case 3: case 12: case 14: case 80: case 83:
                    f=new[]{Field(c.Stream,op==83?32:op==3?19:49),Field(c.Stream,op==3?9:op==83?32:49)};break;
                case 5: f=new[]{Field(c.Stream,19),Field(c.Stream,9),Field(c.Stream,11)};break;
                case 50: case 71: case 90: f=new[]{Field(c.Stream,op==50?240:49)};break;
                case 74: raw=Field(c.Stream,88);if(raw.Length!=88)throw new InvalidDataException("Invalid native room record");f=new[]{raw};break;
                case 86: f=new[]{Field(c.Stream,12)};if(f[0].Length!=12)throw new InvalidDataException("Invalid match result");break;
                case 87: f=new[]{Field(c.Stream,4)};if(f[0].Length!=4)throw new InvalidDataException("Invalid room state");break;
                case 8: case 17: case 18: case 76: case 77: case 78: case 85: case 89: f=new byte[0][];break;
                default:throw new InvalidDataException("Unsupported Crazy Zone command "+op);
            }
            lock(gate) {
                if(op==3 || op==5) {
                    if(c.Name!=null)throw new InvalidDataException("Already logged in");
                    string name=Text(f[0]),password=Text(f[1]);int result=Authenticate(name,password,op==5);
                    if(result==0 && clients.Any(x=>x!=c && x.Name!=null && x.Name.Equals(name,StringComparison.OrdinalIgnoreCase)))result=3;
                    Reply(c,op==3?4:6,result);
                    if(op==3 && result==0) {c.Name=accounts[name].Name;Log("login",new {client=c.Id});}
                    return;
                }
                RequireLogin(c);
                switch(op) {
                    case 8:
                        Send(c,Join(new byte[]{9},BitConverter.GetBytes(0)));
                        int id=0;foreach(string channel in channels.Keys)Send(c,Blob(10,Join(BitConverter.GetBytes(++id),Korean.GetBytes(channel+"\0"))));
                        Send(c,new byte[]{11});break;
                    case 12:
                        string newChannel=Text(f[0]);
                        if(newChannel.Length==0 || Korean.GetByteCount(newChannel)>40 || channels.Count>=24 || channels.ContainsKey(newChannel)) {Reply(c,13,1);break;}
                        channels.Add(newChannel,Text(f[1]));Reply(c,13,0);break;
                    case 14: case 80:
                        string target=Text(f[0]),pass;
                        if(!channels.TryGetValue(target,out pass) || pass!=Text(f[1])) {Reply(c,op==14?15:81,1);break;}
                        LeaveRoom(c);BroadcastUser(c,0);c.Channel=channels.Keys.First(name=>name.Equals(target,StringComparison.OrdinalIgnoreCase));c.Users=c.Rooms=false;
                        // Command 80 is recovery after a failed/closed DirectPlay room.
                        // Its native caller expects 2 to return to the channel chooser.
                        Reply(c,op==14?15:81,op==14?1:2);break;
                    case 17:
                        bool newSubscriber=!c.Users;c.Users=true;
                        foreach(var user in clients.Where(x=>x.Name!=null && x.Channel.Equals(c.Channel,StringComparison.OrdinalIgnoreCase)).ToArray()) {
                            byte[] body=Join(new byte[]{1,17},BitConverter.GetBytes(0),Korean.GetBytes(user.Name+"\0"));Send(c,Blob(16,body));
                        }
                        if(newSubscriber)foreach(var other in clients.Where(x=>x!=c && x.Users && x.Channel.Equals(c.Channel,StringComparison.OrdinalIgnoreCase)).ToArray())Send(other,Blob(16,Join(new byte[]{1,17},BitConverter.GetBytes(0),Korean.GetBytes(c.Name+"\0"))));
                        break;
                    case 18:c.Users=c.Rooms=false;break;
                    case 50:
                        byte[] chat=Join(new byte[]{1},Korean.GetBytes(c.Name+": "),f[0],new byte[]{0});
                        if(chat.Length>299)throw new InvalidDataException("Chat too long");
                        foreach(var peer in clients.Where(x=>x.Name!=null && x.Channel.Equals(c.Channel,StringComparison.OrdinalIgnoreCase)).ToArray())Send(peer,Blob(51,chat));break;
                    case 78:
                        c.Rooms=true;Send(c,Blob(79,new byte[]{1}));
                        foreach(Room room in rooms.Values.Where(r=>!r.Playing && r.Channel.Equals(c.Channel,StringComparison.OrdinalIgnoreCase)).ToArray())Send(c,Blob(79,RoomRecord(room,1)));break;
                    case 74:
                        LeaveRoom(c);raw=f[0];string title=Text(raw.Take(33).ToArray());
                        if(title.Length==0 || Array.IndexOf(raw,(byte)0,0,33)<0 || Array.IndexOf(raw,(byte)0,33,13)<0 || Array.IndexOf(raw,(byte)0,46,34)<0 || rooms.Values.Any(r=>r.Channel==c.Channel && r.Title.Equals(title,StringComparison.OrdinalIgnoreCase)) || raw[86]<1 || raw[86]>2) {Reply(c,75,1);break;}
                        var created=new Room {Id=nextRoom++,Host=c,Title=title,Password=Text(raw.Skip(33).Take(13).ToArray()),Channel=c.Channel,Native=raw};
                        rooms.Add(created.Id,created);created.Members.Add(c);c.Room=created.Id;c.Users=c.Rooms=false;
                        Send(c,Join(new byte[]{75,111},BitConverter.GetBytes(created.Id)));BroadcastRoom(created,1);break;
                    case 83:
                        Room found=rooms.Values.FirstOrDefault(r=>r.Channel==c.Channel && r.Title.Equals(Text(f[0]),StringComparison.OrdinalIgnoreCase));
                        if(found==null || found.Host==c || found.Playing || found.Members.Count>=8 || found.Password!=Text(f[1])) {Reply(c,84,1);break;}
                        LeaveRoom(c);found.Members.Add(c);c.Room=found.Id;c.Users=c.Rooms=false;
                        byte[] info=new byte[120];Buffer.BlockCopy(found.Native,0,info,0,33);Buffer.BlockCopy(found.Native,46,info,33,33);Buffer.BlockCopy(found.Native,80,info,66,7);
                        Buffer.BlockCopy(Fixed(c.IP,20),0,info,73,20);Buffer.BlockCopy(Fixed(HostIP(found),20),0,info,93,20);Buffer.BlockCopy(BitConverter.GetBytes(found.Id),0,info,116,4);
                        Send(c,Join(new byte[]{84,111},BitConverter.GetBytes(120),info));Log("room-join",new {client=c.Id,room=found.Id});break;
                    case 76:case 77:LeaveRoom(c);break;
                    case 85:
                        Room active;if(rooms.TryGetValue(c.Room,out active) && active.Host==c && !active.Playing) {active.Playing=true;BroadcastRoom(active,0);Log("match-start",new {room=active.Id,players=active.Members.Count});}break;
                    case 86:Log("match-result",new {client=c.Id,room=c.Room});break;
                    case 87:break; // native result/state notification, never trusted as identity
                    case 89:break; // heartbeat reply
                    case 71:
                        byte[] stats=Join(BitConverter.GetBytes(f[0].Length),f[0],new byte[1+4*3+1+4*2+10]);Send(c,Blob(72,stats));break;
                    case 90:Send(c,Blob(94,Korean.GetBytes("Amagadon Private Zone\0")));break;
                }
            }
        }
        public void Dispose() {
            TcpListener socket;
            lock(gate) {if(listener==null)return;stopping=true;socket=listener;foreach(var c in clients.ToArray())c.Socket.Close();}
            if(heartbeat!=null)heartbeat.Dispose();socket.Stop();if(acceptTask!=null)acceptTask.Wait(3000);
            lock(gate)listener=null;Log("stop",new {});
        }
    }
}
