"""Selection state must change only at command execution, identically on every PC.

Reproduces the 2026-11-04 paired desync (P2 workers 265/269/272, right-click on
resource 60 at clock 12461): the commanding player's own PC changed the extended
selection sidecar at UI time (before the command executed), and the installed
execution hook then rewrote the synchronized native selection from it.

Executes the original x86 local-input swap (0x407b11..0x407b5d / 0x407c3f..0x407cac),
the installed 0x44dbd0 rectangle hook with the original selector, the original
per-player execution 0x48bbaf..0x48bc97 including the installed 0x48bc82 hook, and
the installed 0x48bd48 CALL. Only the native right-click handler is replaced by a
probe that records the 16-slot selection it would act on. Sprite bounds and
SetRect leaves are substituted as in test-selection-runtime.py.

Usage: python scripts/test-selection-sync-isolation.py   (after build-selection-runtime.py)
Env AMAGADON_GAME_EXE overrides the original Armageddon.exe path.
"""
import json,struct,sys,os
from pathlib import Path
REPO=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(REPO/'.tools'))
import pefile
from unicorn import *
from unicorn.x86_const import *
from keystone import *
M=json.loads((REPO/'.tools/selection-runtime.json').read_text());B=M['base']
P=pefile.PE(os.environ.get('AMAGADON_GAME_EXE',r'C:\Users\seo\Downloads\armaggeddon\armaggeddon\Armageddon.exe'))
K=Ks(KS_ARCH_X86,KS_MODE_32)
STACK,RETURN,MANAGER,UNITS,DEFS=0x400f000,0x4001000,0x3000000,0x3100000,0x3e00000
def w(u,a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
def r(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
def asm(u,a,s):u.mem_write(a,bytes(K.asm(s,a)[0]))
def run(u,a,b,count=5000000):
 u.emu_start(a,b,count=count);assert u.reg_read(UC_X86_REG_EIP)==b,hex(u.reg_read(UC_X86_REG_EIP))
def fresh(n,owned,local,multiplayer=1):
 u=Uc(UC_ARCH_X86,UC_MODE_32)
 u.mem_map(0x400000,P.OPTIONAL_HEADER.SizeOfImage)
 for s in P.sections:u.mem_write(0x400000+s.VirtualAddress,s.get_data())
 u.mem_map(0x3000000,0x1000000);u.mem_map(0x4000000,0x100000);u.mem_map(0x233a000,4096);u.mem_map(B,M['size'])
 u.mem_write(B,(REPO/'.tools/selection-runtime.bin').read_bytes())
 for h in M['hooks']:
  before=bytes.fromhex(h['before']);assert bytes(u.mem_read(h['site'],len(before)))==before,hex(h['site'])
  u.mem_write(h['site'],bytes([h['opcode']])+struct.pack('<i',h['target']-h['site']-5)+b'\x90'*(len(before)-5))
 w(u,0x504a10,MANAGER);w(u,MANAGER+4,n);u.mem_write(0x4e7270,bytes([local]));u.mem_write(0x504f48,b'\4');w(u,0x513ed4,multiplayer)
 u.mem_write(MANAGER+0x7218,b'\xff'*(12*64))
 for i in range(n):
  unit=UNITS+i*0x1400;w(u,MANAGER+8+i*4,unit);w(u,unit+8,DEFS)
  u.mem_write(unit+12,struct.pack('<HH',0x113,i));u.mem_write(unit+0x3c,bytes([2 if i in owned else 1]));u.mem_write(unit+0x13b8,b'\1')
  w(u,unit+20,100+i%10*20);w(u,unit+24,100+i//10*20)
 u.mem_write(DEFS+0x23d,b'\1');w(u,0x51a4e4,DEFS+0x20000)
 asm(u,0x43f610,'mov eax,[esp+4]; mov dword ptr [eax],-8; mov dword ptr [eax+4],-8; mov dword ptr [eax+8],8; mov dword ptr [eax+12],8; ret 8')
 w(u,0x4cb254,RETURN+0x100)
 asm(u,RETURN+0x100,'mov eax,[esp+4]; mov edx,[esp+8]; mov [eax],edx; mov edx,[esp+12]; mov [eax+4],edx; mov edx,[esp+16]; mov [eax+8],edx; mov edx,[esp+20]; mov [eax+12],edx; ret 20')
 return u
def slots(u,offset):return [i for i in struct.unpack('<16i',u.mem_read(MANAGER+offset,64)) if i>=0]
def native(u,p):return slots(u,0x7218+p*64)
def sidecar(u,p):
 c=r(u,M['counts']+p*4);return list(struct.unpack('<'+'H'*c,u.mem_read(M['lists']+p*4096,c*2)))
def ui_select(u,rect):
 """Local multiplayer input: original backup/load, 0x40b010's slot-0 copy and -1
 fill (0x40bac4), its 0x44dbd0 call (0x40bb22), original copy-back/restore."""
 local=u.mem_read(0x4e7270,1)[0]
 u.reg_write(UC_X86_REG_ESP,STACK);run(u,0x407b11,0x407b5d)
 u.mem_write(MANAGER+0x7218,bytes(u.mem_read(MANAGER+0x7218+local*64,64)));u.mem_write(MANAGER+0x7218+local*64,b'\xff'*64)
 u.mem_write(DEFS+0x1000,struct.pack('<4i',*rect));u.reg_write(UC_X86_REG_ECX,MANAGER)
 u.mem_write(STACK,struct.pack('<5I',RETURN,local,local,DEFS+0x1000,1));u.reg_write(UC_X86_REG_ESP,STACK);run(u,0x44dbd0,RETURN)
 assert u.reg_read(UC_X86_REG_ESP)==STACK+20
 u.reg_write(UC_X86_REG_EBX,0);u.reg_write(UC_X86_REG_EDI,MANAGER);run(u,0x407c3f,0x407cac)
 return slots(u,0x7498)
def execute(u,p,packet):
 base=0x52f510+p*64;u.mem_write(base,packet);u.mem_write(0x513c89+p,b'\1')
 u.reg_write(UC_X86_REG_ESP,STACK);u.mem_write(STACK+0x10,struct.pack('<II',base+0xe,p*4))
 u.reg_write(UC_X86_REG_ESI,base+0xe);u.reg_write(UC_X86_REG_EBX,p);run(u,0x48bbaf,0x48bc97)
 seen=[]
 def probe(uc,a,s,x):seen.append(native(uc,p))
 asm(u,0x408390,'ret');hk=u.hook_add(UC_HOOK_CODE,probe,begin=0x408390,end=0x408390)
 u.mem_write(STACK,struct.pack('<I',p));u.reg_write(UC_X86_REG_ESP,STACK);run(u,0x48bd48,0x48bd4d);u.hook_del(hk)
 assert u.reg_read(UC_X86_REG_ESP)==STACK
 return sorted(x for batch in seen for x in batch),len(seen)
# Recorded packets of the paired match (P2): 12416 selection release, 12461 right-click.
SELECT=bytes.fromhex('020000ff000000001a0001000100a406')+bytes(14)+b'\xa4\x06'*16+bytes(2)
RIGHT=bytes.fromhex('040001ff002467000000000100003c002708120fa7033202000000000000a406a406a406a406a406a406a406a406a406a406a406a406a406a406a406a406a130')
def select_packet(ids):
 b=bytearray(SELECT)
 for i in range(16):struct.pack_into('<H',b,0x1e+i*2,ids[i] if i<len(ids) else 0x6a4)
 return bytes(b)
def marker_packet(rect):
 b=bytearray(SELECT);struct.pack_into('<2H',b,30,4095,0xa31)
 for i,v in enumerate(rect):struct.pack_into('<2H',b,34+i*4,v&4095,(v>>12)&4095)
 return bytes(b)
checks=0
CASES=(('3 units (observed match)',{5,6,7},(190,90,250,110),(190,90,205,110),[5,6,7]),
       ('20 units, extended',set(range(20)),(90,90,290,130),(90,90,105,110),list(range(16))))
for name,owned,first,later,expected in CASES:
 for ui_change in (True,False):
  owner=fresh(70,owned,2);transmitted=ui_select(owner,first)
  assert native(owner,2)==[] and sidecar(owner,2)==[],'UI-time selection leaked into synchronized state'
  assert r(owner,M['pending'])==0,'multiplayer UI rectangle must not leak into a later wire invocation'
  results={}
  for local in (1,2):
   u=owner if local==2 else fresh(70,owned,1)
   execute(u,2,select_packet(transmitted))
   if local==2 and ui_change:
    assert ui_select(u,later)==[min(owned)]
    assert native(u,2)==transmitted,'UI-time click changed the synchronized selection'
   results[local]=execute(u,2,RIGHT)
  assert results[1]==results[2]==(expected,1),(name,ui_change,results)
  checks+=1
# Execution-time extended rectangle (installed marker protocol) stays identical per PC.
for local in (1,2):
 u=fresh(70,set(range(20)),local);acted=execute(u,2,marker_packet((90,90,290,130)))
 assert sidecar(u,2)==list(range(20)),sidecar(u,2)
 assert execute(u,2,RIGHT)==(list(range(20)),2);checks+=1
# Single player keeps immediate sidecar selection (UI and execution coincide).
u=fresh(70,set(range(20)),2,multiplayer=0)
u.mem_write(DEFS+0x1000,struct.pack('<4i',90,90,290,130));u.reg_write(UC_X86_REG_ECX,MANAGER)
u.mem_write(STACK,struct.pack('<5I',RETURN,2,2,DEFS+0x1000,1));u.reg_write(UC_X86_REG_ESP,STACK);run(u,0x44dbd0,RETURN)
assert sidecar(u,2)==list(range(20)) and r(u,M['pending'])==0;checks+=1
print('PASS',checks,'selection isolation scenarios: commanding PC and peer act on identical units for the recorded P2 right-click after a later UI click (3 and 20 units), execution-time extended rectangle on both PCs, single-player immediate selection unchanged')

# A native selection packet supersedes an earlier sidecar even if it shares a prefix.
# Start from a synchronized execution-time selection of one unit, then select 3.
for local in (1,2):
 u=fresh(70,{5,6,7},local)
 execute(u,2,marker_packet((190,90,205,110)))
 assert sidecar(u,2)==[5]
 acted=execute(u,2,select_packet([5,6,7]))
 assert acted==([5,6,7],1),('native selection overwritten by old prefix',local,acted)
 assert sidecar(u,2)==[]
 assert execute(u,2,RIGHT)==([5,6,7],1)
print('PASS explicit native selection replaces stale sidecar prefix on both PCs')

# A later wire invocation must retain its own native selection bytes, not emit
# a rectangle from an earlier multiplayer UI click (including a stale flag).
u=fresh(70,set(range(20)),2)
w(u,M['pending'],1)
ui_select(u,(90,90,290,130))
wire=bytes(range(28));u.mem_write(0x51be70,wire)
u.reg_write(UC_X86_REG_ESP,STACK)
run(u,0x4079b7,0x4079bc)
assert bytes(u.mem_read(0x51be70,28))==wire
assert r(u,M['pending'])==0
# Replacing a 20-unit selection with exactly its first 16 or with empty selection
# must also stop extended batching.
for ids in (list(range(16)),[]):
 for local in (1,2):
  u=fresh(70,set(range(20)),local)
  execute(u,2,marker_packet((90,90,290,130)))
  assert len(sidecar(u,2))==20
  # Native ignores an all-sentinel list (0x48bbaf path); compare with that
  # original behavior, while ensuring the stale 20-unit sidecar cannot return.
  expected=ids if ids else list(range(16))
  actual=execute(u,2,select_packet(ids));assert actual==(expected,1),(local,ids,actual)
  baseline=fresh(70,set(range(20)),local)
  execute(baseline,2,select_packet(list(range(16))))
  assert execute(baseline,2,select_packet(ids))==actual
  assert sidecar(u,2)==[]
print('PASS delayed wire preserves current packet; native 16/empty selections cancel old expanded batches')
