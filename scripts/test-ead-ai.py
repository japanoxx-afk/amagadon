"""Installed EAD AI plan hooks and unchanged native production policy."""
import importlib.util,pathlib,struct
s=importlib.util.spec_from_file_location('n',pathlib.Path(__file__).with_name('test-native-scheduler.py'));n=importlib.util.module_from_spec(s);s.loader.exec_module(n)

def queue_case(patched,local,width,player=3,base_queue=8,other_queue=1):
 p=n.RealPeer(local,width);p.load_ai(0)
 brain=0x7080000+player*0x100
 race=(player-1)%3;worker=(0x12,0x113,0x21c)[race]
 combat=(0x17,0x119,0x223)[race]
 if race==2:
  slot=p.call(0x447400,(),n.m.MANAGER)
  assert p.call(0x4458b0,(slot,0x204,player,0),n.m.MANAGER,16)
  parent=p.r(n.m.MANAGER+8+slot*4);p.w(parent+0x85c,other_queue)
  for j in range(max(0,other_queue-1)):p.w(parent+0x75c+j*4,combat)
  p.call(0x450b30,(player,0x204),n.m.MANAGER,8)
 base=p.r(n.m.MANAGER+8+(player-1)*8);p.w(base+0x85c,base_queue)
 for j in range(base_queue-1):p.w(base+0x75c+j*4,worker)
 p.w(brain+0x28+(worker&255)*4,100);p.w(brain+0x28+(combat&255)*4,20)
 if not patched:p.u.mem_write(0x455e69,b'\xe8'+struct.pack('<i',0x4552a0-0x455e6e));p.u.ctl_flush_tb()
 # An earlier JGE targets 455E72. It must remain an instruction boundary,
 # not the middle of our patch. Execute the whole native function below.
 assert bytes(p.u.mem_read(0x455e72,3))==bytes.fromhex('83ff2a')
 orders=[]
 for _ in range(100):
  p.u.mem_write(0x504dd8+player*16,bytes(16))
  p.call(0x455830,(),brain)
  saved=[p.u.reg_read(r) for r in n.m.REGS]
  p.call(0x455c90,(),brain)
  assert [p.u.reg_read(r) for r in n.m.REGS]==saved
  if p.r(0x504dd8+player*16):orders.append(p.r(0x504ddc+player*16))
 return p,orders

def queue_regression():
 old,old_orders=queue_case(False,3,800)
 a,orders=queue_case(True,3,800);b,remote_orders=queue_case(True,1,1024)
 assert old_orders and set(old_orders)=={0x21c},old_orders
 assert orders and set(orders)=={0x223},orders
 assert orders==remote_orders
 n.l.compare(a,b)
 # At seven entries the original producer still has room: keep its priority.
 _,space=queue_case(True,3,800,base_queue=7)
 assert space and set(space)=={0x21c},space
 _,full=queue_case(True,3,800,other_queue=8)
 assert not full,full
 # The EAD-only hook leaves both other factions unchanged.
 for player,worker in ((1,0x12),(2,0x113)):
  original,left=queue_case(False,1,800,player=player)
  installed,right=queue_case(True,2,1024,player=player)
  assert left==right and left and set(left)=={worker}
  n.l.compare(original,installed)
 print('PASS full native replenishment: full queue starvation reproduced; next producer selected; capacity 7/8, all-full, incoming branch, non-EAD and paired state')

def population_regression():
 peers=[n.RealPeer(3,800),n.RealPeer(1,1024)]
 for p in peers:
  p.load_ai(0);brain=0x7080300
  p.w(brain+0x1c,p.r(brain+0x18)) # Isolate automatic housing from plan rows.
  base=p.r(n.m.MANAGER+8+16);p.w(base+0x85c,8)
  definition=p.r(p.catalogs[2][0]+4+0x29*4)
  cost=p.u.mem_read(definition+0x24c,1)[0];assert cost>1
  for kind,used,cap,expect in ((0x21c,99,100,False),(0x21c,100,100,True),(0x229,100-cost,100,False),(0x229,101-cost,100,True),(0x229,204,200,False)):
   p.w(base+0x75c,kind);p.w(n.m.MANAGER+0x24920+44,used);p.w(n.m.MANAGER+0x24998+44,cap)
   p.u.mem_write(0x504dd8+48,bytes(16));saved=[p.u.reg_read(r) for r in n.m.REGS]
   p.call(0x454ee0,(),brain)
   assert [p.u.reg_read(r) for r in n.m.REGS]==saved
   assert p.r(brain+0x1c)==p.r(brain+0x18)
   assert p.r(n.m.MANAGER+0x24998+44)==cap
   order=struct.unpack('<4I',p.u.mem_read(0x504dd8+48,16))
   assert order==((1,0x203,0,0) if expect else (0,0,0,0)),(kind,used,cap,order)
  p.w(n.m.MANAGER+0x24920+44,100);p.w(n.m.MANAGER+0x24998+44,100)
  type_index=p.call(0x476ad0,(0x203,))
  for offset in (0x23bdc,0x23e66):
   pending=n.m.MANAGER+offset+3*65+type_index
   p.u.mem_write(pending,b'\1');p.u.mem_write(0x504dd8+48,bytes(16))
   p.call(0x454ee0,(),brain)
   assert p.r(0x504dd8+48)==0,'duplicate pending housing request'
   p.u.mem_write(pending,b'\0')
  # Housing still needs its original resources; no free construction request.
  p.w(n.m.MANAGER+0xa8c0+12,0);p.w(n.m.MANAGER+0xa8e8+12,0)
  p.u.mem_write(0x504dd8+48,bytes(16));p.call(0x454ee0,(),brain)
  assert p.r(0x504dd8+48)==0,'unaffordable housing request'
 n.l.compare(*peers)
 print('PASS automatic EAD housing: actual ARO cost, exact/insufficient capacity, 200 cap, pending/construction deduplication, unchanged plan/capacity, stack/registers and paired state')

def main():
 queue_regression()
 population_regression()
 peers=[n.RealPeer(3,800),n.RealPeer(1,1024)]
 for p in peers:
  p.load_ai(0)
  table=p.r(0x504e9c)
  for index in range(9):
   ptr=p.r(table+index*4);count=p.r(0x504e78+index*4)
   if index==6:
    rows=[struct.unpack('<5I',p.u.mem_read(ptr+i*20,20)) for i in range(count)]
    assert count==98,(index,count)
    parents=addons=0
    for row in rows:
     if row[1]==1:
      assert row[3]!=0x210
      if 0x226<=row[2]<=0x229:assert row[3]==0x206
     if row[1]==0:
      parents+=row[2]==0x204;addons+=row[2] in (0x205,0x206)
      assert addons<=parents
    before=bytes(p.u.mem_read(ptr,count*20))
    p.call(0x456220,(0,),0x7080300,4)
    assert p.r(0x504e78+24)==count and bytes(p.u.mem_read(ptr,count*20))==before
  # EAD selectors must not alter any Earth/Elca plan payload or count.
  for index in range(6):
   name=('Earth','Elca')[index//3]+str(index%3+1)
   rows=[]
   for line in n.archive('AI\\'+name+'.AAI').splitlines():
    if line==b'\xff':break
    if not line.strip():continue
    worker,parent,race,action,qty=[int(line[70+j*4:74+j*4]) for j in range(5)]
    rows.append((race,action,worker,parent,qty))
   assert p.r(0x504e78+index*4)==len(rows)
   assert bytes(p.u.mem_read(p.r(table+index*4),len(rows)*20))==b''.join(struct.pack('<5I',*r) for r in rows)
  for variant in (1,2,0):
   p.call(0x456220,(variant,),0x7080300,4)
   ptr=p.r(0x70803fc);count=p.r(0x7080318)
   rows=[struct.unpack('<5I',p.u.mem_read(ptr+i*20,20)) for i in range(count)]
   assert all(r[3]!=0x210 for r in rows if r[1]==1)
   assert all(r[3]==0x206 for r in rows if r[1]==1 and 0x226<=r[2]<=0x229)
   parents=addons=0
   for row in rows:
    if row[1]==0:
     parents+=row[2]==0x204;addons+=row[2] in (0x205,0x206)
     assert addons<=parents
   before=bytes(p.u.mem_read(ptr,count*20))
   p.call(0x4561f0,(6+variant,),0x7080300,4)
   assert p.r(0x7080318)==count and bytes(p.u.mem_read(ptr,count*20))==before
  brain=0x7080300;plan=p.r(brain+0xfc)
  # Keep original best-effort requests: standing targets are maintained by
  # 455C90, so waiting for every queue admission can block later technology.
  assert bytes(p.u.mem_read(0x454fac,5))==b'\xe8'+struct.pack('<i',0x4558a0-0x454fb1)
  base=p.r(n.m.MANAGER+8+4*4)
  # Original first-row skip registers a standing target, later replenished
  # by 455C90 -> 4558D0. Preserve this native planning policy.
  p.w(base+0x85c,1);p.w(brain+0x1c,0);p.w(brain+0x20,0)
  p.w(brain+0x28+0x1c*4,0);p.w(plan+12,0x200);p.w(plan+16,4)
  assert bytes(p.u.mem_read(0x454f7d,5))==bytes.fromhex('8b4e2003d1')
  p.call(0x454ee0,(),brain)
  assert p.r(brain+0x1c)==1 and p.r(brain+0x28+0x1c*4)==4
  # The original replenishment producer is functional. Do not remap it
  # merely because its ID differs from an AAI producer.
  assert bytes(p.u.mem_read(0x455b0c,10))==bytes.fromhex('c782e04d500006020000')
  for kind in range(0x226,0x22a):
   saved=[p.u.reg_read(r) for r in n.m.REGS]
   p.call(0x4558d0,(kind,),brain,4)
   assert [p.u.reg_read(r) for r in n.m.REGS]==saved
   assert p.r(0x504ddc+48)==kind and p.r(0x504de0+48)==0x206
  for kind,parent in ((0x21c,0x200),(0x21f,0x204),(0x220,0x205),(0x221,0x205),(0x223,0x204)):
   p.call(0x4558d0,(kind,),brain,4)
   assert p.r(0x504ddc+48)==kind and p.r(0x504de0+48)==parent
 n.l.compare(*peers)
 print('PASS installed EAD normalization, native standing-target policy, preserved native replenishment parents, air/ground parent boundaries, original request policy, stack/registers and paired state')
if __name__=='__main__':main()
