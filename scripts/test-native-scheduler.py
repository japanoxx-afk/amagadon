"""Paired native scheduler lab. Original ARO data stays local; render resources are a declared seam."""
import importlib.util,pathlib,struct,json,hashlib,time,functools,datetime
s=importlib.util.spec_from_file_location('life',pathlib.Path(__file__).with_name('test-unit-lifecycle.py'))
l=importlib.util.module_from_spec(s);s.loader.exec_module(l)
from unicorn import *
from unicorn.x86_const import *
m=l.m
CASE={}

@functools.lru_cache(maxsize=None)
def archive(name):
    h=(m.original.parent/'Armageddon.HED').read_bytes();key=name.encode('cp949').lower()
    for i in range(struct.unpack_from('<I',h,4)[0]):
        r=h[8+i*72:80+i*72]
        if r[4:4+len(key)].lower()==key:
            off,n=struct.unpack_from('<I',r)[0],struct.unpack_from('<I',r,68)[0]
            with (m.original.parent/'Armageddon.MFP').open('rb') as f:f.seek(off);return f.read(n)
    raise ValueError(name)

class RealPeer(l.Peer):
    def __init__(self,local,width):
        super().__init__(local,width)
        self.catalogs=[];self.assets=[];self.tick=0;self.order_log=[];self.ai_order=[];self.rotation_calls=0;self.created=0;self.creation_events=[]
        self.u.mem_map(0x7000000,0x200000)
        self.w(0x51a508,0x7100000)
        for i in range(700):self.w(0x7100000+i*4,0x7101000+i*0x80)
        self.w(0x504884,0x70b0000);self.w(0x504878,0x70b0000);self.w(0x504888,0x70b0000)
        for race,name in enumerate(('earth','elca','ead','neutral')):
            blob=archive('object\\'+name+'.aro');count=struct.unpack_from('<H',blob,2)[0]
            assert blob[:2]==b'\x99\xef' and len(blob)==1406+count*0x39dc
            cat=0x7000000+race*0x10000;self.w(0x5049fc+race*4,cat)
            self.u.mem_write(cat,b'\0'*0x4000);pos=[0]
            def io(u,a,size,data):
                sp=u.reg_read(UC_X86_REG_ESP)
                if a==0x494ac0:out=1
                elif a==0x494ad0:out=0
                else:
                    dest,sz,n=struct.unpack('<3I',u.mem_read(sp+4,12));amount=sz*n
                    chunk=blob[pos[0]:pos[0]+amount];assert len(chunk)==amount
                    u.mem_write(dest,chunk);pos[0]+=amount;out=n
                u.reg_write(UC_X86_REG_EAX,out);u.reg_write(UC_X86_REG_EIP,self.r(sp));u.reg_write(UC_X86_REG_ESP,sp+4)
            handles=[self.u.hook_add(UC_HOOK_CODE,io,begin=a,end=a) for a in (0x494ac0,0x494ad0,0x494b40)]
            assert self.call(0x40de10,(0,),cat,4)==1
            for h in handles:self.u.hook_del(h)
            assert pos[0]==len(blob)
            for i in range(count):
                d=self.r(cat+4+i*4)
                assert bytes(self.u.mem_read(d,0x39dc))==blob[1406+i*0x39dc:1406+(i+1)*0x39dc]
                # Serialized sprite pointer is process-specific. A single fixture sprite
                # is supplied; every other byte of the serialized definition is retained.
                self.w(d+0x394,0x3650000)
            self.catalogs.append((cat,count));self.assets.append({'name':name,'count':count,'sha256':hashlib.sha256(blob).hexdigest()})
        self.w(m.PARENT+8,self.r(self.catalogs[0][0]+4))
        self.u.mem_write(0x3640000+0x14,struct.pack('<HH',32,32))
        # Headless render-queue seam: graphics output is outside this fixture.
        # Rotation, movement, perception and AI functions remain native.
        for a in (0x4bd550,0x4bd640):self.u.mem_write(a,b'\xc3')
        def observe(u,address,size,data):
            if address==0x42cee0:self.order_log.append(self.r(u.reg_read(UC_X86_REG_ESP)+4))
            elif address==0x454ee0:self.ai_order.append(self.r(u.reg_read(UC_X86_REG_ECX)+20))
            elif address==0x42c910:self.rotation_calls+=1
            elif address==0x4458b0:
                self.created+=1
                self.creation_events.append((self.tick,self.r(u.reg_read(UC_X86_REG_ESP)+4)))
        for address in (0x42cee0,0x454ee0,0x42c910,0x4458b0):
            self.u.hook_add(UC_HOOK_CODE,observe,begin=address,end=address)
    def scheduler_step(self,tick,camera=(0,0),verify_order=True):
        self.order_log=[];self.tick=tick
        self.u.reg_write(UC_X86_REG_ESP,m.STACK)
        m.run(self.u,0x454482,0x454487,5000000)
        assert self.r(0x503c6c)==tick
        assert self.u.mem_read(0x503bcc,1)[0]==tick%16
        self.w(0x5812e8,camera[0]);self.w(0x5812ec,camera[1])
        self.u.reg_write(UC_X86_REG_ESP,m.STACK)
        # Execute the real caller argument setup, CALL, callee and return.
        saved=[self.u.reg_read(r) for r in m.REGS]
        m.run(self.u,0x48caef,0x48cb0e,5000000)
        assert [self.u.reg_read(r) for r in m.REGS]==saved
        assert self.u.reg_read(UC_X86_REG_ESP)==m.STACK
        if verify_order:assert self.order_log==sorted(set(self.order_log)),self.order_log
    def load_ai(self,variant):
        table=0x7090000;self.w(0x504e9c,table)
        self.plan_metadata=[]
        for race,name in enumerate(('Earth','Elca','Ead')):
            for level in range(3):
                raw=archive('AI\\'+name+str(level+1)+'.AAI');rows=[]
                for line in raw.splitlines():
                    if line==b'\xff':break
                    if not line.strip():continue
                    assert len(line)>=90 and not line[90:].strip(),repr(line)
                    # Native 4563a7 reads five fixed-width four-byte numbers.
                    worker,parent,faction,action,qty=(int(line[70+i*4:74+i*4]) for i in range(5))
                    rows.append((faction,action,worker,parent,qty))
                index=race*3+level;plan=0x70e0000+index*0x2000
                self.u.mem_write(plan,b''.join(struct.pack('<5I',*r) for r in rows))
                self.w(table+index*4,plan);self.w(0x504e78+index*4,len(rows))
                self.plan_metadata.append({'name':name+str(level+1),'rows':len(rows),'sha256':hashlib.sha256(raw).hexdigest()})
        for player in range(1,9):
            brain=0x7080000+player*0x100;race=(player-1)%3
            self.w(0x504ea0+player*4,brain);self.w(m.MANAGER+0x9128+player*4,race)
            self.call(0x455c00,(player,),brain,4)
            self.call(0x456220,(variant,),brain,4)
            self.u.mem_write(m.MANAGER+0x240f0+player,b'\1')
            self.u.mem_write(m.MANAGER+0x25137+player,b'\1')
            self.u.mem_write(0x513c63+player,b'\2')
            self.w(m.MANAGER+0xa8c0+player*4,1000)
            self.w(m.MANAGER+0xa8e8+player*4,1000)
            self.owner=player;self.u.mem_write(m.PARENT+0x3c,bytes([player]))
            _,base=self.create(race<<8);self.place(base,160+(player-1)*80,400)
            self.call(0x450b30,(player,race<<8),m.MANAGER,8)
            _,worker=self.create((0x12,0x113,0x21c)[race]);self.place(worker,160+(player-1)*80,480)
        self.w(m.MANAGER+8+17*4,0) # remove creation-only fixture parent
        self.w(0x57e2a0,0x70a0000)
        for i in range(3):self.w(0x70a0000+0x33a8+4*i,100)
    def ai_step(self):
        # Actual eight-player scheduler, including native AI/perception helpers.
        self.ai_order=[]
        self.u.reg_write(UC_X86_REG_ESP,m.STACK)
        m.run(self.u,0x48cc06,0x48cc63,5000000)
        assert self.ai_order==list(range(1,9))
        assert self.u.reg_read(UC_X86_REG_ESP)==m.STACK
    def state(self):
        count=self.r(m.MANAGER+4)
        assert 0<=count<=1700
        self.children=[(slot,self.r(m.MANAGER+8+slot*4)) for slot in range(count) if self.r(m.MANAGER+8+slot*4)]
        state=super().state()
        state['effects']=bytes(self.u.mem_read(0x7100000,0x18000))
        state['clock_phases']=bytes(self.u.mem_read(0x503bc8,0xb8))
        state['native_checksum']=bytes(self.u.mem_read(0x581177,1))
        return state


def main():
    global CASE
    started=time.perf_counter();cases=[]
    for kind in (0x12,0x113,0x21c,0x17,0x1b,0x119,0x11b,0x223,0x226):
        CASE={'phase':'unit-scheduler','kind':hex(kind),'tick':0}
        a,b=RealPeer(1,800),RealPeer(2,1024)
        for p in (a,b):
            p.w(0x57e2a0,0x70a0000)
            for i in range(3):p.w(0x70a0000+0x33a8+4*i,100)
            for j in range(4):
                _,c=p.create(kind);p.place(c,160,200+j*32)
                p.u.mem_write(c+0x464,b'\2');p.w(c+0xa4,400);p.w(c+0xf4,240);p.w(c+0x4a4,400);p.w(c+0x4a8,240)
        initial=a.positions()
        for tick in range(1,601):
            CASE['tick']=tick
            for p in (a,b):
                p.scheduler_step(tick,(0,0) if p is a else (8,6))
            assert a.order_log==b.order_log
            try:l.compare(a,b)
            except Exception:print('case',hex(kind),tick);raise
        assert a.positions()!=initial
        cases.append({'kind':hex(kind),'ticks':600,'positions':a.positions(),'rotation_calls':a.rotation_calls,'collision_branches':a.collision_hits})
    ai_cases=[];plan_metadata=[]
    for variant in range(3):
        CASE={'phase':'AI','variant':variant,'tick':0}
        a,b=RealPeer(1,800),RealPeer(2,1024)
        for p in (a,b):p.load_ai(variant)
        plan_metadata=a.plan_metadata
        issued=0;same_pass_new_slots=[]
        for tick in range(1,601):
            CASE['tick']=tick
            for p in (a,b):
                p.scheduler_step(tick,(0,0) if p is a else (8,6))
                p.ai_step()
            l.compare(a,b)
            assert a.order_log==b.order_log and a.creation_events==b.creation_events
            same_pass_new_slots.extend(slot for born,slot in a.creation_events if born==tick and slot in a.order_log)
            assert bytes(a.u.mem_read(0x7080000,0x1000))==bytes(b.u.mem_read(0x7080000,0x1000))
            left=bytes(a.u.mem_read(0x504dd8,160));right=bytes(b.u.mem_read(0x504dd8,160))
            assert left==right
            issued+=sum(left[player*16]!=0 for player in range(1,9))
        assert issued>0 and a.r(m.MANAGER+4)>16
        assert same_pass_new_slots,'production did not exercise same-pass higher-slot insertion'
        ai_cases.append({'variant':variant,'ticks':600,'nonempty_orders':issued,'unit_count':a.r(m.MANAGER+4),'native_factory_calls':a.created,'same_pass_new_slots':same_pass_new_slots,'plan_indices':[a.r(0x7080000+i*0x100+28) for i in range(1,9)]})
    CASE={'phase':'reversed-order-control','tick':0}
    # Deliberately reverse exactly one peer's native loop for a detector control.
    # The unmodified game is NOT alleged to use this reversed order.
    a,b=RealPeer(1,800),RealPeer(2,1024)
    for p in (a,b):
        p.w(0x57e2a0,0x70a0000)
        for i in range(3):p.w(0x70a0000+0x33a8+4*i,100)
        for j in range(4):
            _,c=p.create(0x12);p.place(c,160,200+j*32)
            p.u.mem_write(c+0x464,b'\2');p.w(c+0xa4,400);p.w(c+0xf4,240)
            p.w(c+0x4a4,400);p.w(c+0x4a8,240)
    ordinal=[0]
    def reverse(u,address,size,data):
        if address==0x447ba5:
            ordinal[0]=u.reg_read(UC_X86_REG_EDI)
            u.reg_write(UC_X86_REG_EDI,b.r(m.MANAGER+4)-1-ordinal[0])
        else:u.reg_write(UC_X86_REG_EDI,ordinal[0])
    for address in (0x447ba5,0x448c93):b.u.hook_add(UC_HOOK_CODE,reverse,begin=address,end=address)
    mismatch=None
    for tick in range(1,101):
        CASE['tick']=tick
        a.scheduler_step(tick);b.scheduler_step(tick,verify_order=False)
        assert a.order_log==list(reversed(b.order_log))
        if a.positions()!=b.positions():mismatch=tick;break
    assert mismatch is not None,'reversed-order control did not affect simulation'
    report={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'unit_cases':cases,'ai_cases':ai_cases,'reversed_order_first_position_difference_tick':mismatch,
            'assets':a.assets,'ai_plans':plan_metadata,
            'seconds':round(time.perf_counter()-started,3),
            'original_sha256':hashlib.sha256(m.original.read_bytes()).hexdigest(),
            'launcher_sha256':hashlib.sha256(m.launcher.read_bytes()).hexdigest(),
            'full_match':False,'real_aro_definitions':True,'real_sprite_metadata':False,
            'seams':['archive file I/O','CRT allocator','debug printf','single synthetic sprite metadata','headless renderer submission'],
            'limitations':['flat synthetic terrain','no network/Windows message loop','AI plans advance only through observed indices','not every combat/weapon/death branch']}
    (m.root/'.tools/native-scheduler-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS',json.dumps(report))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        frames=[];tb=exc.__traceback__
        while tb:
            context=tb.tb_frame.f_locals
            frames.append({'function':tb.tb_frame.f_code.co_name,'line':tb.tb_lineno,
                           'kind':context.get('kind'),'tick':context.get('tick'),'variant':context.get('variant')})
            tb=tb.tb_next
        (m.root/'.tools/native-scheduler-failure.json').write_text(json.dumps({'case':CASE,'error':repr(exc),'frames':frames},indent=2),encoding='utf-8')
        raise
