"""Original targeted attack command CALL through scheduler, projectile and death.
No periodic fire injection. This begins after decoded selection/target resolution,
not at the Windows input or DirectPlay packet decoder.
"""
import importlib.util,pathlib,struct,json
s=importlib.util.spec_from_file_location('battle',pathlib.Path(__file__).with_name('test-battle-flow.py'));b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
from unicorn.x86_const import *
from unicorn import UC_HOOK_CODE

def command(p,slot,target,x,y):
 p.u.mem_write(b.n.m.MANAGER+0x7218+64,struct.pack('<16I',slot,*([0xffffffff]*15)))
 p.u.reg_write(UC_X86_REG_ESP,b.n.m.STACK)
 p.u.reg_write(UC_X86_REG_ESI,1);p.u.reg_write(UC_X86_REG_EAX,target)
 p.u.reg_write(UC_X86_REG_ECX,x);p.u.reg_write(UC_X86_REG_EDX,y)
 assert bytes(p.u.mem_read(0x42078c,5))==b'\xe8'+struct.pack('<i',0x40aa40-0x420791)
 saved=[p.u.reg_read(r) for r in b.n.m.REGS]
 # Native caller pushes y, x, target, player and calls 0x40AA40.
 b.n.m.run(p.u,0x420788,0x420791,5000000)
 assert p.u.reg_read(UC_X86_REG_ESP)==b.n.m.STACK-16
 assert saved==[p.u.reg_read(r) for r in b.n.m.REGS]
 return p.u.reg_read(UC_X86_REG_EFLAGS)&0x8d5

def case(kind,target_kind,weapon_override=None,target_hp=None,healing=False,direct_damage=False,target_distance=None):
 peers=[b.BattlePeer(1,800),b.BattlePeer(2,1024)];units=[];shots=[0,0];factories=[{},{}];command_flags=[];hp_writes=[0,0]
 for i,p in enumerate(peers):
  # Child factories can create another unit kind during an attack.
  # Preload every available original SPR, and reject fallback sprite use.
  p.u.mem_map(0x8000000,0x8000000);p.heap=0x8000000;p.heap_limit=0x10000000
  for race in range(4):
   for index in range(50):
    ptr=struct.unpack('<I',b.n.m.pe.get_data(0x4d9700+race*200+index*4-0x400000,4))[0]
    if ptr<0x400000:continue
    try:p.sprite(race*256+index)
    except ValueError:pass
  target_x=496 if kind in (0x17,0x16) else 368
  if weapon_override is not None:
   definition=p.r(0x51a8ec+weapon_override*4)
   target_x=304+max(96,p.u.mem_read(definition+5,1)[0]*32+64)
  if target_distance is not None:target_x=304+target_distance
  a=p.unit(kind,1,304,240);t=p.unit(target_kind,1 if healing else 2,target_x,240);units.append((a,t))
  if target_hp is not None:p.w(t[1]+0x9c4,target_hp)
  if healing:p.w(b.n.m.MANAGER+0xa8c0+4,1000)
  if weapon_override is not None:
   # Explicit isolated branch fixture, not a naturally acquired upgrade.
   p.w(a[1]+0x9cc,10000);p.w(a[1]+0x9d4,10000)
   p.w(a[1]+0x1388,weapon_override);p.u.mem_write(a[1]+0x9ec,bytes([weapon_override]))
  def health_write(u,address,size,data,i=i,t=t):
   if u.reg_read(UC_X86_REG_ECX)==t[1]:hp_writes[i]+=1
  p.u.hook_add(UC_HOOK_CODE,health_write,begin=0x42ced0,end=0x42ced0)
  def observe(u,address,size,data,i=i,p=p,a=a):
   source=p.r(u.reg_read(UC_X86_REG_ESP)+4)
   if source and p.u.mem_read(source+0x3c,1)==b'\1':
    shots[i]+=1;factories[i][hex(address)]=factories[i].get(hex(address),0)+1
  for address in (0x48b170,0x48b300):p.u.hook_add(UC_HOOK_CODE,observe,begin=address,end=address)
  command_flags.append(command(p,a[0],t[0],target_x,240))
  assert p.r(a[1]+0x414)==t[0]
 assert command_flags[0]==command_flags[1]
 b.n.l.compare(*peers)
 initial=peers[0].r(units[0][1][1]+0x9c4);first=None;death=None
 for tick in range(1,4001):
  for p in peers:
   p.scheduler_step(tick,(0,0) if p is peers[0] else (8,6))
   p.projectiles((0,0) if p is peers[0] else (8,6))
  b.n.l.compare(*peers)
  for p in peers:
   for slot,c in p.children:
    assert struct.unpack('<H',p.u.mem_read(c+12,2))[0] in p.loaded
  if tick%500==0:print('PROGRESS',hex(kind),tick,shots,flush=True)
  # Native HP is signed; a lethal hit may leave a negative value.
  hp=struct.unpack('<i',peers[0].u.mem_read(units[0][1][1]+0x9c4,4))[0]
  if ((hp>initial) if healing else (hp<initial)) and first is None:first=tick
  if (hp>=peers[0].r(units[0][1][1]+0x9c8) if healing else peers[0].u.mem_read(units[0][1][1]+0x13b8,1)==b'\0'):death=tick;break
 assert first and death and (hp_writes[0]>0 if direct_damage else shots[0]>0),(hex(kind),first,death,shots)
 assert hp_writes[0]==hp_writes[1]
 assert shots[0]==shots[1] and factories[0]==factories[1]
 for tick in range(death+1,death+61):
  for p in peers:p.scheduler_step(tick,(0,0) if p is peers[0] else (8,6));p.projectiles((0,0) if p is peers[0] else (8,6))
  b.n.l.compare(*peers)
 return {'kind':hex(kind),'target':hex(target_kind),'first_effect':first,'death':None if healing else death,'healed_tick':death if healing else None,'initial_hp':initial,'post_completion_ticks':60,'projectile_calls':shots[0],'factory_entries':factories[0],'weapon_override':weapon_override,'direct_damage':direct_damage,'hp_write_calls':hp_writes[0]}

def rejected_target_control():
 peers=[b.BattlePeer(1,800),b.BattlePeer(2,1024)];units=[]
 for p in peers:
  a=p.unit(0x119,1,304,240);t=p.unit(0x223,2,368,240);units.append((a,t))
  command(p,a[0],t[0],368,240)
 for tick in range(1,121):
  for p in peers:p.scheduler_step(tick);p.projectiles((0,0))
  b.n.l.compare(*peers)
 for p,pair in zip(peers,units):
  assert p.r(pair[1][1]+0x9c4)==120 and p.hits==0
  assert p.u.mem_read(pair[0][1]+0x464,1)==bytes([0])
 # Sentinel 0x35 does not arm transports; 0x117 uses the native override.
 p=b.BattlePeer(1,800)
 for kind,expected in ((0x227,0),(0x117,30),(0x11f,53),(0x10b,0)):
  _,unit=p.unit(kind,1,304,240);assert p.r(unit+0x1388)==expected
 print('PASS invalid ground target rejected and native weapon exceptions retained',flush=True)

def main():
 rejected_target_control()
 results=[case(0x11f,0x1b,target_hp=20,healing=True),case(0x228,0x1b,direct_damage=True),case(0x220,0x1b,target_distance=32)];failures=[]
 for result in results:print('PASS native healing/direct/short-range command',result,flush=True)
 for kind,target in ((0x223,0x223),(0x17,0x223),(0x1b,0x223),(0x119,0x1b),(0x11b,0x1b),(0x224,0x223),(0x226,0x1b),(0x16,0x223),(0x117,0x223),(0x122,0x223),(0x221,0x223),(0x229,0x223),(0x21f,0x1b)):
  try:r=case(kind,target);results.append(r);print('PASS',r,flush=True)
  except Exception as e:failures.append({'kind':hex(kind),'target':hex(target),'error':repr(e)});print('FAIL',failures[-1],flush=True)
 report={'cases':results,'failures':failures,'full_match':False,'limitations':['decoded selection and target supplied by fixture','weapon visual resources omitted','flat synthetic map','not all special command branches']}
 (b.n.m.root/'.tools/attack-command-flow-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 assert not failures,failures
if __name__=='__main__':main()
