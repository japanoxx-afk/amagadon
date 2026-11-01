"""Original-code check: option.dat music flag (+0x0C) decides whether match BGM plays.
Runs the unpatched x86 code with Unicorn: option apply tail 0x4A36BE..0x4A36E5,
then the BGM player 0x4BC350. Miles imports are replaced by recording stubs.
Usage: python scripts/test-game-music.py [path\\to\\Armageddon.exe]
"""
import struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'.tools'))
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP,UC_X86_REG_ESI,UC_X86_REG_EAX,UC_X86_REG_EIP

EXE=Path(sys.argv[1]) if len(sys.argv)>1 else Path(r'C:\Users\seo\Downloads\armaggeddon\armaggeddon\Armageddon.exe')
P=pefile.PE(str(EXE));IMAGE=P.get_memory_mapped_image();BASE=P.OPTIONAL_HEADER.ImageBase
STACK,STUBS,DATA,RET=0x3000000,0x3100000,0x3200000,0x31ff000
MILES={0x4cb384:('AIL_pause_stream',8),0x4cb3ac:('AIL_set_stream_loop_count',8),0x4cb3b4:('AIL_start_stream',4),
       0x4cb3b8:('AIL_set_stream_volume',8),0x4cb3bc:('AIL_open_stream',12),0x4cb3c0:('AIL_close_stream',4)}

def machine():
 u=Uc(UC_ARCH_X86,UC_MODE_32)
 u.mem_map(BASE,(len(IMAGE)+0xfff)&~0xfff);u.mem_write(BASE,IMAGE)
 u.mem_map(STACK-0x10000,0x20000);u.mem_map(STUBS,0x1000);u.mem_map(DATA,0x1000);u.mem_map(RET,0x1000)
 calls=[]
 for i,(iat,(name,pop)) in enumerate(sorted(MILES.items())):
  stub=STUBS+i*16;u.mem_write(stub,b'\xb8'+struct.pack('<I',0x5000+i)+b'\xc2'+struct.pack('<H',pop));u.mem_write(iat,struct.pack('<I',stub))
 def hook(uc,address,size,_):
  i=(address-STUBS)//16
  if address==STUBS+i*16 and 0<=i<len(MILES):calls.append(sorted(MILES.items())[i][1][0])
 u.hook_add(UC_HOOK_CODE,hook,begin=STUBS,end=STUBS+0x100)
 w=lambda a,v:u.mem_write(a,struct.pack('<i',v))
 w(0x2240d44,1);w(0x2240d34,0x1234);w(0x2240d38,0);w(0x2240d3c,0);w(0x4f8628,-1)
 u.mem_write(0x4f8240,b'Bgm\\Menu.wav\0')  # menu music already chosen before the match
 return u,calls,w

def run(u,start,stop):
 u.reg_write(UC_X86_REG_EIP,start);u.emu_start(start,stop,count=200000)

def call_player(u,path):
 u.mem_write(DATA,path+b'\0');esp=STACK-0x100
 u.mem_write(esp,struct.pack('<II',RET,DATA));u.reg_write(UC_X86_REG_ESP,esp)
 u.emu_start(0x4bc350,RET,count=200000);return u.reg_read(UC_X86_REG_EAX)

def r(u,a):return struct.unpack('<i',u.mem_read(a,4))[0]

for flag in (0,1):
 u,calls,w=machine()
 option=DATA+0x400;u.mem_write(option,struct.pack('<9i',0,100,100,flag,100,1,100,4,49))
 u.reg_write(UC_X86_REG_ESI,option);u.reg_write(UC_X86_REG_ESP,STACK-0x200)
 run(u,0x4a36be,0x4a36e5)  # original: test [esi+0xc]; pause+disable or enable+resume
 assert r(u,0x4eac34)==flag
 assert r(u,0x4f8628)==(1 if flag==0 else -1),r(u,0x4f8628)
 calls.clear();result=call_player(u,b'BGM\\04-into the war.wav')
 played=bytes(u.mem_read(0x4f8240,32)).split(b'\0')[0]
 assert played==b'BGM\\04-into the war.wav'
 if flag==0:
  assert result==0 and 'AIL_open_stream' not in calls,calls
 else:
  assert result==1 and calls[:1]==['AIL_open_stream'] and 'AIL_start_stream' in calls,calls
print('PASS original option apply + BGM player: option.dat +0x0C=0 pauses music (0x4F8628=1) and match BGM only records its path; +0x0C=1 opens and starts the stream')
