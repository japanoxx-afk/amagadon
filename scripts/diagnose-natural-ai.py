"""Paired natural AI progression using the original scheduler and asset data.

Set AMAGADON_LAB_REAL_SPRITES=1, AMAGADON_LAB_AI_PLAYERS=1/2/3 and
AMAGADON_LAB_TICKS to reproduce a faction run. No plan index or completion
flag is forced. AMAGADON_LAB_SUPPLEMENT_EAD_PARENT=1 adds one explicitly
reported native build request at the stalled EAD plan. Exit 2 explicitly
means the plan list remains incomplete.
AMAGADON_LAB_COMBAT_PRESSURE=1 supplies declared hostile tank attack input
for an EAD-only run, so ordinary combat losses free native population capacity.
"""
import importlib.util,struct,json,collections,os,pathlib,hashlib
s=importlib.util.spec_from_file_location('b',pathlib.Path(__file__).with_name('test-battle-flow.py'));b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
REAL_SPRITES=os.environ.get('AMAGADON_LAB_REAL_SPRITES')=='1'
ACTIVE_PLAYERS=[int(x) for x in os.environ.get('AMAGADON_LAB_AI_PLAYERS','1,2,3,4,5,6,7,8').split(',')]
assert ACTIVE_PLAYERS and all(1<=p<=8 for p in ACTIVE_PLAYERS)
TICKS=int(os.environ.get('AMAGADON_LAB_TICKS','6000'))
TICK_INSTRUCTIONS=int(os.environ.get('AMAGADON_LAB_TICK_INSTRUCTIONS','50000000' if REAL_SPRITES else '5000000'))
assert 1000000<=TICK_INSTRUCTIONS<=500000000
SUPPLEMENT_EAD_PARENT=os.environ.get("AMAGADON_LAB_SUPPLEMENT_EAD_PARENT")=="1"
AI_VARIANT=int(os.environ.get("AMAGADON_LAB_AI_VARIANT","0"))
assert AI_VARIANT in (0,1,2)
PROGRESS={}
RUN_NAME=('natural-ai-real' if REAL_SPRITES else 'natural-ai')+'-'+'-'.join(map(str,ACTIVE_PLAYERS))+('-supplement' if SUPPLEMENT_EAD_PARENT else '')+'-v'+str(AI_VARIANT)
from unicorn import UC_HOOK_MEM_INVALID,UC_HOOK_BLOCK,UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EIP,UC_X86_REG_ESP,UC_X86_REG_ESI,UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_EBP

def thread_runtime(p,local):
 # OS-only seams for native CRT rand(): preserve 4BFFF0's real LCG and
 # 4C2F13's TLS access. Different presentation seeds must not affect units.
 p.u.mem_write(0x73f2000,bytes.fromhex('31c0c3')) # GetLastError
 p.u.mem_write(0x73f2010,b'\xb8'+struct.pack('<I',0x73f2100)+b'\xc2\x04\x00')
 p.u.mem_write(0x73f2020,bytes.fromhex('c20400')) # SetLastError
 for address,stub in ((0x4cb110,0x73f2000),(0x4cb1e8,0x73f2010),(0x4cb1ec,0x73f2020)):p.w(address,stub)
 p.w(0x73f2114,local*101)
 expected=(local*101*214013+2531011)&0xffffffff
 assert p.call(0x4bfff0)==((expected>>16)&0x7fff)
 assert p.r(0x73f2114)==expected
 p.w(0x73f2114,local*101)

def combat_pressure(p,tick):
 """Controlled opposing attack orders at population pressure; no HP/death edits.

 EAD's own AI, production, research and population cap remain native. The
 fixture supplies eight tanks and two Hunters with decoded attack input.
 An optional declared wave uses forty tanks/eight Hunters on multiple ground
 targets; it is opponent input, never an EAD production or population edit.
 """
 assert ACTIVE_PLAYERS==[3],'Controlled opponent input is an EAD-only scenario'
 if tick%250 or tick<int(os.environ.get('AMAGADON_LAB_COMBAT_START_TICK','0')):return
 used=p.r(b.n.m.MANAGER+0x24920+44);capacity=p.r(b.n.m.MANAGER+0x24998+44)
 if capacity<=0:return
 p.state()
 # Plans may end below 200 (Ead2: 138). Use actual front-air population
 # cost instead of an unreachable fixed 180 threshold.
 blocked_air=False
 for _,producer in p.children:
  if p.u.mem_read(producer+0x3c,1)!=b'\3' or p.r(producer+0x85c)<=1:continue
  kind=p.r(producer+0x75c)
  if 0x226<=kind<=0x229:
   definition=p.r(p.catalogs[2][0]+4+(kind&255)*4)
   blocked_air|=used+p.u.mem_read(definition+0x24c,1)[0]>capacity
 if not blocked_air:return
 targets=[(slot,c) for slot,c in p.children if p.u.mem_read(c+0x13b8,1)==b'\1' and p.u.mem_read(c+0x3c,1)==b'\3' and struct.unpack('<H',p.u.mem_read(c+12,2))[0] in (0x21f,0x220,0x221,0x223,0x224,0x225)]
 if not targets:return
 target,c=min(targets,key=lambda item:(p.u.mem_read(item[1]+0x464,1)!=b'\0',p.r(item[1]+0x9c4),item[0]))
 x=p.r(c+20);y=p.r(c+24)
 wave=tick>=int(os.environ.get('AMAGADON_LAB_COMBAT_WAVE_TICK','200001'))
 ranked_targets=sorted(targets,key=lambda item:(-p.u.mem_read(p.r(p.catalogs[2][0]+4+(p.r(item[1]+12)&255)*4)+0x24c,1)[0],item[0]))
 actors=[(slot,a) for slot,a in getattr(p,'pressure_actors',[]) if p.r(b.n.m.MANAGER+8+slot*4)==a and p.u.mem_read(a+0x13b8,1)==b'\1' and p.u.mem_read(a+0x3c,1)==b'\1' and p.u.mem_read(a+12,2) in (b'\x1b\0',b'\x1e\0')]
 while len(actors)<(48 if wave else 10):
  if wave:
   _,spawn_target=ranked_targets[(len(actors)//4)%len(ranked_targets)]
   x=p.r(spawn_target+20);y=p.r(spawn_target+24)
  kind=0x1b if sum(p.u.mem_read(a+12,2)==b'\x1b\0' for _,a in actors)<(40 if wave else 8) else 0x1e
  # The creation-only fixture parent slot is reused during a long run. Use
  # the real manager factory with explicit ownership, not that initial slot.
  slot=p.call(0x447400,(),b.n.m.MANAGER)
  assert slot!=0xffffffff
  assert p.call(0x4458b0,(slot,kind,1,0),b.n.m.MANAGER,16)
  a=p.r(b.n.m.MANAGER+8+slot*4)
  assert p.u.mem_read(a+0x3c,1)==b'\1'
  p.place(a,max(64,min(4000,x+128)),max(64,min(4000,y+(len(actors)%4 if wave else len(actors))*48)))
  p.u.reg_write(UC_X86_REG_ESP,b.n.m.STACK)
  p.u.reg_write(UC_X86_REG_ESI,b.n.m.MANAGER+8+slot*4);p.u.reg_write(UC_X86_REG_EBP,slot)
  b.n.m.run(p.u,0x44cb07,0x44cc01,1000000)
  assert p.u.reg_read(UC_X86_REG_ESP)==b.n.m.STACK
  actors.append((slot,a))
 p.pressure_actors=actors
 for actor_index,(slot,a) in enumerate(actors):
  if wave:
   target,c=ranked_targets[(actor_index//4)%len(ranked_targets)]
   x=p.r(c+20);y=p.r(c+24)
  p.u.mem_write(b.n.m.MANAGER+0x7218+64,struct.pack('<16I',slot,*([0xffffffff]*15)))
  p.u.reg_write(UC_X86_REG_ESP,b.n.m.STACK);p.u.reg_write(UC_X86_REG_ESI,1)
  p.u.reg_write(UC_X86_REG_EAX,target);p.u.reg_write(UC_X86_REG_ECX,x);p.u.reg_write(UC_X86_REG_EDX,y)
  saved=[p.u.reg_read(r) for r in b.n.m.REGS]
  b.n.m.run(p.u,0x420788,0x420791,5000000)
  assert p.u.reg_read(UC_X86_REG_ESP)==b.n.m.STACK-16
  assert saved==[p.u.reg_read(r) for r in b.n.m.REGS]
  if wave:p.pressure_order_events=getattr(p,'pressure_order_events',[])+[(tick,slot,target,x,y)]
 p.pressure_events=getattr(p,'pressure_events',[])+[(tick,target,[slot for slot,a in actors])]

def fixture(local,width):
 p=b.BattlePeer(local,width)
 thread_runtime(p,local)
 p.produced=[]
 p.production_pending={}
 def producing(u,address,size,data):
  sp=u.reg_read(UC_X86_REG_ESP)
  p.production_pending[sp]=(p.r(sp+4),p.r(sp+8),p.r(sp+12)&255)
 def produced(u,address,size,data):
  sp=u.reg_read(UC_X86_REG_ESP)
  slot,kind,owner=p.production_pending.pop(sp)
  if u.reg_read(UC_X86_REG_EAX):
   child=p.r(b.n.m.MANAGER+8+slot*4)
   assert child # The caller activates the returned object after this factory.
   assert struct.unpack('<H',p.u.mem_read(child+12,2))[0]==kind
   assert p.u.mem_read(child+0x3c,1)[0]==owner
   p.produced.append((p.tick,kind,owner))
 # Successful native factory return, not merely an attempted request/entry.
 p.u.hook_add(UC_HOOK_CODE,producing,begin=0x4458b0,end=0x4458b0)
 p.u.hook_add(UC_HOOK_CODE,produced,begin=0x4465fa,end=0x4465fa)
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
 p.load_ai(AI_VARIANT)
 plan=p.r(0x70803fc)
 p.ead_research=sorted({p.r(plan+i*20+8) for i in range(p.r(0x7080318)) if p.r(plan+i*20+4)==2})
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

def supplemental_parent_order(p):
 # Controlled extra input, not a forced plan index or completed building.
 assert p.call(0x452d30,(3,0x204),b.n.m.MANAGER,8)==0xffffffff
 p.u.mem_write(0x504dd8,bytes(160))
 p.u.mem_write(0x504dd8+3*16,struct.pack("<4I",1,0x204,0,0))
 p.u.mem_write(b.n.m.STACK,struct.pack("<I",b.n.m.RETURN))
 p.u.reg_write(UC_X86_REG_ESP,b.n.m.STACK)
 saved=[p.u.reg_read(reg) for reg in b.n.m.REGS]
 b.n.m.run(p.u,0x406160,b.n.m.RETURN,50000000)
 assert [p.u.reg_read(reg) for reg in b.n.m.REGS]==saved
 assert p.u.reg_read(UC_X86_REG_ESP)==b.n.m.STACK+4

def main():
 if os.environ.get('AMAGADON_LAB_VERIFY_EAD')=='1':
  assert ACTIVE_PLAYERS==[3] and REAL_SPRITES,'Full EAD verification requires actual sprites and EAD-only AI'
 local_players=[ACTIVE_PLAYERS[0],1 if ACTIVE_PLAYERS[0]!=1 else 2]
 peers=[fixture(local_players[0],800),fixture(local_players[1],1024)];samples=[];supplement_tick=None;ead_wait_started=None;ead_complete_tick=None
 for tick in range(1,TICKS+1):
  for p in peers:
   if os.environ.get('AMAGADON_LAB_COMBAT_PRESSURE')=='1':combat_pressure(p,tick)
   PROGRESS.update(tick=tick,peer=peers.index(p),phase='unit scheduler')
   p.scheduler_step(tick,(0,0) if p is peers[0] else (8,6),instruction_budget=TICK_INSTRUCTIONS)
   PROGRESS['phase']='AI'
   p.ai_step(50000000 if REAL_SPRITES else 5000000)
   PROGRESS['phase']='projectiles'
   p.projectiles((0,0) if p is peers[0] else (8,6))
  if SUPPLEMENT_EAD_PARENT and supplement_tick is None and all(p.r(0x708031c)==72 for p in peers):
   assert ACTIVE_PLAYERS==[3],"Supplement scenario is EAD-only"
   if ead_wait_started is None:ead_wait_started=tick
   if tick>=ead_wait_started+200:
    for p in peers:supplemental_parent_order(p)
    supplement_tick=tick
    print("CONTROLLED supplemental SUMMONER construction order",tick,flush=True)
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
  assert peers[0].produced==peers[1].produced
  assert getattr(peers[0],'pressure_events',[])==getattr(peers[1],'pressure_events',[])
  assert getattr(peers[0],'pressure_order_events',[])==getattr(peers[1],'pressure_order_events',[])
  if tick%500==0:
   row={'tick':tick,'indices':[peers[0].r(0x7080000+i*256+28) for i in range(1,9)],'units':peers[0].r(b.n.m.MANAGER+4),'resources':{str(i):[peers[0].r(b.n.m.MANAGER+0xa8c0+i*4),peers[0].r(b.n.m.MANAGER+0xa8e8+i*4)] for i in ACTIVE_PLAYERS},'kinds':dict(collections.Counter(hex(struct.unpack('<H',peers[0].u.mem_read(c+12,2))[0]) for slot,c in peers[0].children if peers[0].u.mem_read(c+0x13b8,1)==b'\1'))}
   row['ead_population']=[peers[0].r(b.n.m.MANAGER+a+44) for a in (0x24920,0x24998)]
   row['ead_produced']=dict(collections.Counter(hex(k) for t,k,o in peers[0].produced if o==3))
   row['ead_research_busy']={str(k):peers[0].r(b.n.m.MANAGER+0xacf4+(3*110+k)*76) for k in peers[0].ead_research}
   row['ead_research']={str(k):peers[0].r(b.n.m.MANAGER+0xacac+(3*110+k)*76) for k in peers[0].ead_research}
   samples.append(row);print(row,flush=True)
  if os.environ.get('AMAGADON_LAB_VERIFY_EAD')=='1':
   p=peers[0]
   finished=p.r(0x708031c)>=p.r(0x7080318)
   finished=finished and {0x226,0x227,0x228,0x229}<={k for t,k,o in p.produced if o==3}
   finished=finished and all(p.r(b.n.m.MANAGER+0xacac+(3*110+k)*76)>0 and p.r(b.n.m.MANAGER+0xacf4+(3*110+k)*76)==0 for k in p.ead_research)
   if finished and ead_complete_tick is None:ead_complete_tick=tick
   if finished and tick>=ead_complete_tick+1000:break
 complete=all(peers[0].r(0x7080000+i*256+28)>=peers[0].r(0x7080000+i*256+24) for i in ACTIVE_PLAYERS)
 report={'ai_variant':AI_VARIANT,'ead_research':{str(k):[peers[0].r(b.n.m.MANAGER+0xacac+(3*110+k)*76),peers[0].r(b.n.m.MANAGER+0xacf4+(3*110+k)*76)] for k in peers[0].ead_research},'production_events':peers[0].produced,'supplemental_parent_order_tick':supplement_tick,'unmodified_plan_inputs':supplement_tick is None,'paired_ticks':TICKS,'active_players':ACTIVE_PLAYERS,'local_players':local_players,'samples':samples,'plan_lists_exhausted':complete,'full_match':False,'seeded_plan_indices':False,'initial_resources':100000,'real_unit_sprites':REAL_SPRITES,'sprite_assets':peers[0].sprite_report,'missing_sprites':getattr(peers[0],'missing_sprites',[]),'unit_states':[{'slot':slot,'kind':hex(struct.unpack('<H',peers[0].u.mem_read(c+12,2))[0]),'owner':peers[0].u.mem_read(c+0x3c,1)[0],'mode':peers[0].u.mem_read(c+0x464,1)[0],'hp':peers[0].r(c+0x9c4),'state48':peers[0].r(c+0x48),'queue750':peers[0].r(c+0x750),'queue85c':peers[0].r(c+0x85c),'target414':peers[0].r(c+0x414)} for slot,c in peers[0].children],'limitations':['flat synthetic map',('real unit SPR metadata' if REAL_SPRITES else 'synthetic sprite metadata'),'initial resources are generous; not a full economy test','no completed late-tech claim unless all plans finish']}
 report['paired_ticks']=tick
 report['ead_complete_tick']=ead_complete_tick
 report['post_completion_ticks']=tick-ead_complete_tick if ead_complete_tick is not None else 0
 report['tick_instruction_budget']=TICK_INSTRUCTIONS
 report['launcher_sha256']=hashlib.sha256(b.n.m.launcher.read_bytes()).hexdigest()
 report['original_sha256']=hashlib.sha256(b.n.m.original.read_bytes()).hexdigest()
 report['original_aai_inputs']=True
 report['external_plan_overrides']=supplement_tick is not None
 report['controlled_enemy_reinforcements']=os.environ.get('AMAGADON_LAB_COMBAT_PRESSURE')=='1'
 report['enemy_attack_commands']=getattr(peers[0],'pressure_events',[])
 report['controlled_enemy_wave_tick']=int(os.environ.get('AMAGADON_LAB_COMBAT_WAVE_TICK','200001'))
 report['enemy_attack_targets']=getattr(peers[0],'pressure_order_events',[])
 report['controlled_enemy_start_tick']=int(os.environ.get('AMAGADON_LAB_COMBAT_START_TICK','0'))
 report['crt_thread_seeds']=[local*101 for local in local_players]
 report.pop('unmodified_plan_inputs',None) # Installed runtime may normalize plans.
 (b.n.m.root/('.tools/'+RUN_NAME+'-results.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
 if os.environ.get('AMAGADON_LAB_VERIFY_EAD')=='1':
  assert complete,'EAD plan incomplete'
  assert ead_complete_tick is not None and tick>=ead_complete_tick+1000,'EAD completion plus 1000 subsequent ticks required'
  kinds={k for t,k,o in peers[0].produced if o==3}
  assert {0x226,0x227,0x228,0x229}<=kinds,('missing air production',sorted({0x226,0x227,0x228,0x229}-kinds))
  assert all(peers[0].r(b.n.m.MANAGER+0xacac+(3*110+k)*76)>0 and peers[0].r(b.n.m.MANAGER+0xacf4+(3*110+k)*76)==0 for k in peers[0].ead_research),'research incomplete'
 print('PLAN LISTS EXHAUSTED (not full match coverage)' if complete else 'INCOMPLETE: paired state matched, tech plans did not finish')
 return 0 if complete else 2
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:
  (b.n.m.root/('.tools/'+RUN_NAME+'-failure.json')).write_text(json.dumps({'progress':PROGRESS,'error':repr(exc)},indent=2),encoding='utf-8')
  raise
