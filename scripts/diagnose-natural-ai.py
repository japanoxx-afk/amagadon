"""Paired natural AI progression using the original scheduler and asset data.

Set AMAGADON_LAB_REAL_SPRITES=1, AMAGADON_LAB_AI_PLAYERS=1/2/3 and
AMAGADON_LAB_TICKS to reproduce a faction run. No plan index or completion
flag is forced. Exit 2 explicitly means the plan list remains incomplete.
"""
import importlib.util,struct,json,collections,os,pathlib
s=importlib.util.spec_from_file_location('b',pathlib.Path(__file__).with_name('test-battle-flow.py'));b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
REAL_SPRITES=os.environ.get('AMAGADON_LAB_REAL_SPRITES')=='1'
ACTIVE_PLAYERS=[int(x) for x in os.environ.get('AMAGADON_LAB_AI_PLAYERS','1,2,3,4,5,6,7,8').split(',')]
assert ACTIVE_PLAYERS and all(1<=p<=8 for p in ACTIVE_PLAYERS)
TICKS=int(os.environ.get('AMAGADON_LAB_TICKS','6000'))
PROGRESS={}
RUN_NAME=('natural-ai-real' if REAL_SPRITES else 'natural-ai')+'-'+'-'.join(map(str,ACTIVE_PLAYERS))
from unicorn import UC_HOOK_MEM_INVALID,UC_HOOK_BLOCK
from unicorn.x86_const import UC_X86_REG_EIP,UC_X86_REG_ESP

def fixture(local,width):
 p=b.BattlePeer(local,width)
 p.u.mem_map(0x7400000,0x100000);p.u.mem_map(0x7500000,0x100000)
 # Original vision constructor; building completion reads these buffers.
 for player in range(10):
  p.w(0x51a4c0+player*4,0x7400000+player*0x3000)
  p.call(0x482730,(),0x7400000+player*0x3000)
  p.w(0x51a4e4+player*4,0x7500000+player*0x11000)
 real=REAL_SPRITES
 if real:
  p.u.mem_map(0x8000000,0x8000000);p.heap=0x8000000;p.heap_limit=0x10000000
  p.missing_sprites=[]
  for race in range(4):
   for index in range(50):
    ptr=struct.unpack('<I',b.n.m.pe.get_data(0x4d9700+race*200+index*4-0x400000,4))[0]
    if ptr<0x400000:continue
    try:p.sprite(race*256+index)
    except ValueError:p.missing_sprites.append(hex(race*256+index))
  p.u.mem_write(b.n.m.WORLD+0xe6,struct.pack('<HH',128,128))
 p.load_ai(0)
 for player in range(1,9):p.u.mem_write(b.n.m.MANAGER+0x25137+player,bytes([int(player in ACTIVE_PLAYERS)]))
 # Empty native selection is -1, not slot zero. Keep UI comparisons enabled.
 p.u.mem_write(b.n.m.MANAGER+0x7498,b'\xff'*64)
 p.w(0x4fa65c,0xffffffff)
 p.w(0x50310c,0x73a0000);p.w(0x50313c,0x73b0000)
 for i in range(10):
  p.w(0x73a0000+0x13bc+i*4,0x73c0000+i*0x200)
  p.w(0x73b0000+0x13b0+i*4,0x73d0000+i*0x200)
  p.w(b.n.m.MANAGER+0x90d8+i*4,0xffffffff)
 for player in range(1,9):
  x=240+((player-1)%4)*600 if real else 160+(player-1)*80
  ybase=800+((player-1)//4)*1200 if real else 400
  if real:
   p.place(p.r(b.n.m.MANAGER+8+(player-1)*8),x,ybase)
   p.place(p.r(b.n.m.MANAGER+12+(player-1)*8),x,ybase+160)
  # Initial map-load base registration only; later construction remains native.
  p.call(0x434e60,(player,0,(player-1)*2),b.n.m.MANAGER,12)
  p.call(0x434e90,(player,1),b.n.m.MANAGER,8)
  p.w(0x4f9840+player*8,x);p.w(0x4f9844+player*8,ybase)
  p.w(b.n.m.MANAGER+0xa8c0+player*4,100000)
  p.w(b.n.m.MANAGER+0xa8e8+player*4,100000)
  # Native hydrogen search accepts 0x306..0x30b, not 0x303.
  for kind,y in ((0x300,600),(0x306,300)):
   slot=p.r(b.n.m.MANAGER+4)
   assert p.call(0x4458b0,(slot,kind,9,0),b.n.m.MANAGER,16)
   c=p.r(b.n.m.MANAGER+8+slot*4);p.place(c,x,ybase+y-400)
 p.recent_blocks=collections.deque(maxlen=40)
 def block(u,a,size,data):p.recent_blocks.append(hex(a))
 def fault(u,access,address,size,value,data):
  (b.n.m.root/('.tools/'+RUN_NAME+'-memory-fault.json')).write_text(json.dumps({'tick':p.tick,'local':local,'eip':hex(u.reg_read(UC_X86_REG_EIP)),'address':hex(address),'blocks':list(p.recent_blocks),'stack':bytes(u.mem_read(u.reg_read(UC_X86_REG_ESP),64)).hex()},indent=2),encoding='utf-8')
  return False
 if os.environ.get('AMAGADON_LAB_BLOCK_TRACE')=='1':p.u.hook_add(UC_HOOK_BLOCK,block)
 p.u.hook_add(UC_HOOK_MEM_INVALID,fault)
 return p

def main():
 local_players=[ACTIVE_PLAYERS[0],1 if ACTIVE_PLAYERS[0]!=1 else 2]
 peers=[fixture(local_players[0],800),fixture(local_players[1],1024)];samples=[]
 for tick in range(1,TICKS+1):
  for p in peers:
   PROGRESS.update(tick=tick,peer=peers.index(p),phase='unit scheduler')
   p.scheduler_step(tick,(0,0) if p is peers[0] else (8,6),instruction_budget=50000000 if REAL_SPRITES else 5000000)
   PROGRESS['phase']='AI'
   p.ai_step(50000000 if REAL_SPRITES else 5000000)
   PROGRESS['phase']='projectiles'
   p.projectiles((0,0) if p is peers[0] else (8,6))
  try:
   b.n.l.compare(*peers)
   if REAL_SPRITES:
    for p in peers:
     for slot,c in p.children:
      kind=struct.unpack('<H',p.u.mem_read(c+12,2))[0]
      assert kind in p.loaded,('active unit sprite missing',slot,hex(kind))
  except Exception as exc:
   (b.n.m.root/('.tools/'+RUN_NAME+'-failure.json')).write_text(json.dumps({'tick':tick,'error':str(exc),'samples':samples},indent=2),encoding='utf-8')
   raise
  assert bytes(peers[0].u.mem_read(0x7400000,0x1e000))==bytes(peers[1].u.mem_read(0x7400000,0x1e000))
  assert bytes(peers[0].u.mem_read(0x7500000,0xaa000))==bytes(peers[1].u.mem_read(0x7500000,0xaa000))
  assert bytes(peers[0].u.mem_read(0x7080000,0x1000))==bytes(peers[1].u.mem_read(0x7080000,0x1000))
  assert bytes(peers[0].u.mem_read(0x504dd8,160))==bytes(peers[1].u.mem_read(0x504dd8,160))
  if tick%500==0:
   row={'tick':tick,'indices':[peers[0].r(0x7080000+i*256+28) for i in range(1,9)],'units':peers[0].r(b.n.m.MANAGER+4),'kinds':dict(collections.Counter(hex(struct.unpack('<H',peers[0].u.mem_read(c+12,2))[0]) for slot,c in peers[0].children if peers[0].u.mem_read(c+0x13b8,1)==b'\1'))}
   samples.append(row);print(row,flush=True)
 complete=all(peers[0].r(0x7080000+i*256+28)>=peers[0].r(0x7080000+i*256+24) for i in ACTIVE_PLAYERS)
 report={'paired_ticks':TICKS,'active_players':ACTIVE_PLAYERS,'local_players':local_players,'samples':samples,'plan_lists_exhausted':complete,'full_match':False,'seeded_plan_indices':False,'initial_resources':100000,'real_unit_sprites':REAL_SPRITES,'sprite_assets':peers[0].sprite_report,'missing_sprites':getattr(peers[0],'missing_sprites',[]),'unit_states':[{'slot':slot,'kind':hex(struct.unpack('<H',peers[0].u.mem_read(c+12,2))[0]),'owner':peers[0].u.mem_read(c+0x3c,1)[0],'mode':peers[0].u.mem_read(c+0x464,1)[0],'hp':peers[0].r(c+0x9c4),'state48':peers[0].r(c+0x48),'queue750':peers[0].r(c+0x750),'queue85c':peers[0].r(c+0x85c),'target414':peers[0].r(c+0x414)} for slot,c in peers[0].children],'limitations':['flat synthetic map',('real unit SPR metadata' if REAL_SPRITES else 'synthetic sprite metadata'),'initial resources are generous; not a full economy test','no completed late-tech claim unless all plans finish']}
 (b.n.m.root/('.tools/'+RUN_NAME+'-results.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
 print('PLAN LISTS EXHAUSTED (not full match coverage)' if complete else 'INCOMPLETE: paired state matched, tech plans did not finish')
 return 0 if complete else 2
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:
  (b.n.m.root/('.tools/'+RUN_NAME+'-failure.json')).write_text(json.dumps({'progress':PROGRESS,'error':repr(exc)},indent=2),encoding='utf-8')
  raise
