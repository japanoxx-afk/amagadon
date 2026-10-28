"""Real TCP multi-client tests and original x86 Crazy Zone consumers/builders.
Only isolated test accounts/data and local loopback are used.
"""
import base64,json,os,socket,struct,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'.tools'))
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
launcher=Path(sys.argv[1]).resolve();original=Path(sys.argv[2]).resolve()
fixture=launcher.parent/'CrazyZoneFixture.exe'
subprocess.run([str(Path(os.environ['WINDIR'])/'Microsoft.NET/Framework/v4.0.30319/csc.exe'),'/nologo','/target:exe','/platform:x86',f'/reference:{launcher}',f'/out:{fixture}',str(ROOT/'scripts/crazy-zone-fixture.cs')],check=True)
pe=pefile.PE(str(original));IMAGE=pe.get_memory_mapped_image()

def exact(s,n):
    out=b''
    while len(out)<n:
        p=s.recv(n-len(out))
        if not p:raise EOFError()
        out+=p
    return out
def field(b):
    if isinstance(b,str):b=b.encode('cp949')
    return struct.pack('<I',len(b))+b
def request(op,*fields):return struct.pack('<HH',op+1234,(1234-4443)&65535)+b''.join(field(f) for f in fields)
def blob(s,op):
    assert exact(s,1)==bytes([op]);n=struct.unpack('<I',exact(s,4))[0];assert n<=299;return exact(s,n)
def connect(port):
    s=socket.create_connection(('127.0.0.1',port),timeout=3);s.settimeout(3);assert exact(s,1)==b'\x5d';return s
def login(s,name,password='testpass'):
    s.sendall(request(3,name,password));return exact(s,2)
def machine():
    u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x3000000);u.mem_write(0x400000,IMAGE);return u
def put(u,a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
def get(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
def ret(u,n,value=1):
    sp=u.reg_read(UC_X86_REG_ESP);u.reg_write(UC_X86_REG_EAX,value&0xffffffff);u.reg_write(UC_X86_REG_EIP,get(u,sp));u.reg_write(UC_X86_REG_ESP,sp+4+n)
def consume(u,data):
    # Original 495ab0 parser, exact original read/rollback helpers and record consumers.
    u.mem_write(0x1200000,data);put(u,0x5815e0,0x1200000);put(u,0x4eb298,5000);put(u,0x5815e4,0);put(u,0x5815e8,len(data));put(u,0x2008000,0x5f0000);u.reg_write(UC_X86_REG_ESP,0x2008000)
    u.emu_start(0x495ab0,0x5f0000,count=10000);assert u.reg_read(UC_X86_REG_ESP)==0x2008004
    assert u.reg_read(UC_X86_REG_EAX)==1
    assert get(u,0x5815e4)==len(data)

def native_send(entry,args,wait=None,private=False):
    u=machine();captured=[];sp=0x2008000;put(u,sp,0x5f0000)
    if private:u.mem_write(0x49740f,b'\x8b\xfe')
    put(u,0x4cb1a8,0x590100)
    for i,value in enumerate(args):
        if isinstance(value,(bytes,str)):
            if isinstance(value,str):value=value.encode('cp949')
            pointer=0x1300000+i*4096;u.mem_write(pointer,value+b'\0');value=pointer
        put(u,sp+4+i*4,value)
    u.reg_write(UC_X86_REG_ESP,sp)
    def hook(u,a,size,_):
        if a==0x4bfff0:ret(u,0,1234)
        elif a==0x590100:ret(u,0,100)
        elif a==0x4aa710:
            s=u.reg_read(UC_X86_REG_ESP);captured.append(bytes(u.mem_read(get(u,s+8),get(u,s+12))));ret(u,0)
        elif a==wait:ret(u,0,111)
    u.hook_add(UC_HOOK_CODE,hook);u.emu_start(entry,0x5f0000,count=10000)
    assert u.reg_read(UC_X86_REG_ESP)==sp+4
    return captured

# Execute the original packet builders through the original opcode encoder.
assert native_send(0x4960c0,['TestHost','testpass'],0x496170)==[request(3,'TestHost','testpass')]
assert native_send(0x4962c0,['1.15'])==[request(2,'1.15')]
assert native_send(0x496510,[])==[request(8)]
assert native_send(0x496900,[])==[request(17)]
assert native_send(0x4972a0,[])==[request(78)]
assert native_send(0x4969d0,['Lobby',''],0x496920)==[request(14,'Lobby','')]
assert native_send(0x497570,[])==[request(85)]
assert native_send(0x4973a0,['Room',''],0x4974d0)[0]==request(83,'Room',bytes(4))
join_wire=native_send(0x4973a0,['Room',''],0x4974d0,private=True)[0]
assert join_wire==request(83,'Room','')
assert native_send(0x4973a0,['Room','secret'],0x4974d0,private=True)[0]==request(83,'Room','secret')
mapinfo=bytearray(256);mapinfo[30:35]=b'Map1\0';struct.pack_into('<HH',mapinfo,0xe6,64,64);struct.pack_into('<H',mapinfo,0xee,0);mapinfo[0xf0]=1
create_wire=native_send(0x496f80,['Room','',bytes(mapinfo)],0x497210)[0]
assert create_wire[:8]==request(74)+struct.pack('<I',88)
assert create_wire[8:13]==b'Room\0' and create_wire[54:59]==b'Map1\0'
assert create_wire[88:95]==struct.pack('<HHHB',64,64,0,1)
locked_wire=native_send(0x496f80,['LockedRoom','secret',bytes(mapinfo)],0x497210)[0]
locked_join=native_send(0x4973a0,['LockedRoom','secret'],0x4974d0,private=True)[0]

with tempfile.TemporaryDirectory(prefix='amagadon-zone-') as temp:
    d=Path(temp);p=subprocess.Popen([str(fixture),str(d)],stdout=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if (d/'port.txt').exists():break
            if p.poll() is not None:raise AssertionError((d/'error.txt').read_text())
            time.sleep(.05)
        port=int((d/'port.txt').read_text());a=connect(port);b=connect(port)
        # TCP fragmentation: each command-header/field byte may arrive separately.
        for byte in request(3,'TestHost','testpass'):a.sendall(bytes([byte]))
        assert exact(a,2)==b'\x04\x00';assert login(b,'TestGuest')==b'\x04\x00'
        bad=connect(port);assert login(bad,'TestHost','wrong')==b'\x04\x02';bad.close()
        dup=connect(port);assert login(dup,'TestHost')==b'\x04\x03';dup.close()
        a.sendall(request(8));assert exact(a,5)==b'\x09'+bytes(4);channel=blob(a,10);assert channel==struct.pack('<I',1)+b'Lobby\0';assert exact(a,1)==b'\x0b'
        u=machine();consume(u,b'\x5d');assert get(u,0x57ca30)==1
        consume(u,b'\x04\x00');assert get(u,0x4eaaac)==0
        consume(u,b'\x0a'+field(channel));assert get(u,0x57ca40)==1 and bytes(u.mem_read(0x577e30,6))==b'Lobby\0'
        a.sendall(request(17));users=[blob(a,16),blob(a,16)];assert all(x[0]==1 for x in users)
        consume(u,b'\x10'+field(users[0]));assert get(u,0x57bc14)==1
        b.sendall(request(17));blob(b,16);blob(b,16);blob(a,16)
        a.sendall(request(50,'hello'));chat_a=blob(a,51);chat_b=blob(b,51);assert chat_a==chat_b and b'TestHost: hello' in chat_a
        # No-body requests coalesced in the same TCP write.
        b.sendall(request(78)+request(89));assert blob(b,79)==b'\x01'
        a.sendall(create_wire);assert exact(a,2)==b'\x4b\x6f';roomid=exact(a,4);record=blob(b,79);assert len(record)==115 and record[1:6]==b'Room\0' and record[95:104]==b'TestHost\0'
        consume(u,b'\x4f'+field(record));assert get(u,0x57ca68)==1
        b.sendall(join_wire);assert exact(b,2)==b'\x54\x6f';n=exact(b,4);assert struct.unpack('<I',n)[0]==120;info=exact(b,120)
        consume(u,b'\x54\x6f'+n+info);assert get(u,0x57ca6c)==111 and get(u,0x57b93c)==struct.unpack('<I',roomid)[0]
        assert bytes(u.mem_read(0x57b925,10)).split(b'\0')[0]==b'127.0.0.1'
        a.sendall(request(83,'Room',''));assert exact(a,2)==b'\x54\x01' # host cannot orphan its own room by joining it
        a.sendall(request(76)+request(78));assert blob(a,79)==b'\x01'
        b.sendall(request(77)+request(78));assert blob(b,79)==b'\x01'
        a.sendall(locked_wire);assert exact(a,2)==b'\x4b\x6f';exact(a,4);blob(b,79)
        b.sendall(request(83,'LockedRoom','wrong'));assert exact(b,2)==b'\x54\x01'
        b.sendall(locked_join);assert exact(b,2)==b'\x54\x6f';assert struct.unpack('<I',exact(b,4))[0]==120;exact(b,120)
        # Host-only state changes and host disconnect clean up the room.
        b.sendall(request(85));a.sendall(request(76)+request(78));assert blob(a,79)==b'\x01'
        b.sendall(request(78));assert blob(b,79)==b'\x01'
        a.close();b.close()
        recover=connect(port);assert login(recover,'Recovery')==b'\x04\x00'
        recover.sendall(request(80,'Lobby',''));assert exact(recover,2)==b'\x51\x02';recover.close()
        malformed=connect(port);malformed.sendall(request(3)+struct.pack('<i',-1));assert malformed.recv(1)==b'';malformed.close()
        oversized=connect(port);oversized.sendall(request(3)+struct.pack('<I',2000000));assert oversized.recv(1)==b'';oversized.close()
        partial=connect(port);partial.sendall(request(3)[:2]);healthy=connect(port);assert login(healthy,'Healthy')==b'\x04\x00';healthy.close();partial.close()
        stored=(d/'accounts.json').read_text();assert 'testpass' not in stored
        ping=connect(port);assert login(ping,'Heartbeat')==b'\x04\x00';ping.settimeout(35)
        assert exact(ping,1)==b'\x58';ping.sendall(request(89));ping.close()
        edits=json.loads((d/'patch.json').read_text());v=machine()
        for e in edits:v.mem_write(e['address'],base64.b64decode(e['bytes']))
        for index in [0,1,29,0xffffffff]:
            sp=0x2008000;put(v,sp,0x5f0000);put(v,sp+4,index);v.reg_write(UC_X86_REG_ESP,sp);v.emu_start(0x497b40,0x5f0000,count=100)
            assert v.reg_read(UC_X86_REG_EAX)==(0x1000040 if index==0 else 0) and v.reg_read(UC_X86_REG_ESP)==sp+4
        # Patched native connect constructs the requested endpoint; all OS calls mocked.
        calls=[];iat={0x4cb2e8:0x590000,0x4cb2ec:0x590100,0x4cb2cc:0x590200}
        for address,target in iat.items():put(v,address,target)
        def api(u,address,size,_):
            sp=u.reg_read(UC_X86_REG_ESP)
            if address==0x590000:assert get(u,sp+4)&65535==19000;ret(u,4,socket.htons(19000))
            elif address==0x590100:assert bytes(u.mem_read(get(u,sp+4),10))==b'127.0.0.1\0';ret(u,4,0x100007f)
            elif address==0x590200:
                addr=get(u,sp+8);assert bytes(u.mem_read(addr,8))==b'\x02\x00'+struct.pack('!H',19000)+socket.inet_aton('127.0.0.1');calls.append('connect');ret(u,12,0)
            elif address==0x4958f0:ret(u,0)
        v.hook_add(UC_HOOK_CODE,api);put(v,0x2008000,0x5f0000);v.reg_write(UC_X86_REG_ESP,0x2008000);v.emu_start(0x495880,0x5f0000,count=1000);assert calls==['connect']
        # Stop releases the listener; a new process loads the persisted password hash.
        (d/'stop').touch();p.wait(timeout=10);assert p.returncode==0
        (d/'stop').unlink();(d/'port.txt').unlink();p=subprocess.Popen([str(fixture),str(d)],stdout=subprocess.DEVNULL)
        for _ in range(100):
            if (d/'port.txt').exists():break
            time.sleep(.05)
        again=connect(int((d/'port.txt').read_text()));assert login(again,'TestHost','wrong')==b'\x04\x02';assert login(again,'TestHost')==b'\x04\x00';again.close()
        assert all('testpass' not in f.read_text(encoding='utf-8-sig') for f in d.glob('server-*.jsonl'))
        print('PASS: real TCP fragmentation/coalescing, two accounts, bad/duplicate login, channels/users/chat/rooms, malformed/partial clients, heartbeat, restart/persisted hashes, credential-free logs; original x86 builders/consumers and patched endpoint/stack')
    finally:
        (d/'stop').touch();p.wait(timeout=10)
        assert p.returncode==0
