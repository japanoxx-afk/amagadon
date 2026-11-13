"""Paired native projectile creation, update, damage and unit death; controlled firing."""
import importlib.util,pathlib,struct,json
s=importlib.util.spec_from_file_location('sprites',pathlib.Path(__file__).with_name('test-real-sprites.py'))
r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
n=r.n
from unicorn.x86_const import *
from unicorn import UC_HOOK_CODE

class BattlePeer(r.SpritePeer):
    def __init__(self,local,width):
        super().__init__(local,width)
        p=self
        p.u.mem_map(0x7300000,0x100000)
        for weapon in range(67):
            ptr=0x7300000+weapon*0x300;p.w(0x51a8ec+weapon*4,ptr)
            p.call(0x485690,(),ptr)
            if weapon:
                # Stop before sprite/renderer asset initialization. Preserve all
                # native stat calculations; this is deliberately a prefix test.
                p.u.mem_write(n.m.STACK,struct.pack('<4I',n.m.RETURN,0,weapon,0))
                p.u.reg_write(UC_X86_REG_ESP,n.m.STACK);p.u.reg_write(UC_X86_REG_ECX,ptr)
                n.m.run(p.u,0x4856e0,0x4857c1,100000)
        # USER32!SetRect imported at 0x4CB254. This OS seam writes four
        # signed coordinates and returns TRUE; it does not choose placement.
        self.u.mem_write(0x73f0000,bytes.fromhex('8b4c24048b44240889018b44240c8941048b4424108941088b44241489410cb801000000c21400'))
        self.w(0x4cb254,0x73f0000)
        assert self.call(0x73f0000,(0x73f0100,1,2,3,4),0,20)==1
        assert bytes(self.u.mem_read(0x73f0100,16))==struct.pack('<4I',1,2,3,4)
        self.u.mem_map(0x233a000,0x10000)
        self.w(0x51a8e8,0x7380000);self.call(0x48b120,(),0x7380000)
        self.w(0x57e2a0,0x70a0000)
        for i in range(4):self.w(0x70a0000+0x33a8+i*4,100)
        self.w(0x517000,0x7390000)
        for player in range(1,9):self.w(n.m.MANAGER+0x7158+player*4,player)
        self.hits=0
        def hit(u,address,size,data):self.hits+=1
        self.u.hook_add(UC_HOOK_CODE,hit,begin=0x488e10,end=0x488e10)
    def unit(self,kind,owner,x,y):
        self.sprite(0);self.sprite(kind)
        self.owner=owner;self.u.mem_write(n.m.PARENT+0x3c,bytes([owner]))
        slot,c=self.create(kind);self.place(c,x,y)
        index=self.call(0x476b60,(kind,))
        weapon=self.u.mem_read(0x4d2189+index*10,1)[0]+1
        self.w(c+0x1388,weapon);self.u.mem_write(c+0x9ec,bytes([weapon]))
        return slot,c
    def fire(self,source,target):
        # Execute original CALL site, not a replacement projectile implementation.
        self.u.reg_write(UC_X86_REG_ESP,n.m.STACK)
        self.u.reg_write(UC_X86_REG_ESI,source);self.u.reg_write(UC_X86_REG_EDI,target)
        saved=[self.u.reg_read(reg) for reg in n.m.REGS]
        n.m.run(self.u,0x43b69c,0x43b6a9,5000000)
        assert self.u.reg_read(UC_X86_REG_ESP)==n.m.STACK
        assert saved==[self.u.reg_read(reg) for reg in n.m.REGS]
    def projectiles(self,camera):
        self.w(0x5812e8,camera[0]);self.w(0x5812ec,camera[1])
        self.u.reg_write(UC_X86_REG_ESP,n.m.STACK);self.w(n.m.STACK+0x38,n.m.WORLD)
        saved=[self.u.reg_read(reg) for reg in n.m.REGS]
        n.m.run(self.u,0x48cc77,0x48cc94,5000000)
        assert self.u.reg_read(UC_X86_REG_ESP)==n.m.STACK
        assert saved==[self.u.reg_read(reg) for reg in n.m.REGS]
    def state(self):
        result=super().state()
        slots=bytes(self.u.mem_read(0x7380000,0x3520))
        result['projectile_slots']=slots
        result['projectiles']=[bytes(self.u.mem_read(ptr,0x88)) for ptr in struct.unpack('<3400I',slots) if ptr]
        return result

def main():
    cases=[]
    for kind in (0x119,0x1b,0x223):
        peers=[BattlePeer(1,800),BattlePeer(2,1024)];units=[]
        for p in peers:units.append((p.unit(kind,1,304,240),p.unit(0x223,2,368,240)))
        first_damage=None;death=None
        for tick in range(1,801):
            for p,pair in zip(peers,units):
                attacker,target=pair[0][1],pair[1][1]
                if tick%20==1 and p.u.mem_read(target+0x13b8,1)==b'\1':p.fire(attacker,target)
                p.scheduler_step(tick,(0,0) if p is peers[0] else (8,6))
                p.projectiles((0,0) if p is peers[0] else (8,6))
            n.l.compare(*peers)
            hp=peers[0].r(units[0][1][1]+0x9c4)
            if hp<120 and first_damage is None:first_damage=tick
            if peers[0].u.mem_read(units[0][1][1]+0x13b8,1)==b'\0':death=tick;break
        assert first_damage and death,(hex(kind),first_damage,death,hp)
        # Continue native updates after death to include in-flight projectiles
        # and corpse handling, rather than stopping on the first dead flag.
        for tick in range(death+1,death+61):
            for p in peers:
                p.scheduler_step(tick,(0,0) if p is peers[0] else (8,6))
                p.projectiles((0,0) if p is peers[0] else (8,6))
            n.l.compare(*peers)
            assert peers[0].u.mem_read(units[0][1][1]+0x13b8,1)==b'\0'
        assert peers[0].hits==peers[1].hits and peers[0].hits>0
        cases.append({'kind':hex(kind),'first_damage_tick':first_damage,'death_tick':death,'post_death_ticks':60,'damage_calls':peers[0].hits})
    report={'cases':cases,'full_match':False,'limitations':['periodic firing is test-driven','flat synthetic terrain','weapon visual assets are absent','not every special weapon branch']}
    (n.m.root/'.tools/battle-flow-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS',json.dumps(report))
if __name__=='__main__':main()
