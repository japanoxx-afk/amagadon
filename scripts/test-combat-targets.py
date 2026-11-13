"""Native weapon-stat initialization prefix and target eligibility matrix, not full combat."""
import importlib.util,pathlib,struct,json
s=importlib.util.spec_from_file_location('sprites',pathlib.Path(__file__).with_name('test-real-sprites.py'))
r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
n=r.n
from unicorn.x86_const import *
def main():
    peers=[r.SpritePeer(1,800),r.SpritePeer(2,1024)];units=[]
    for p in peers:
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
        p.sprite(0);p.sprite(0x119);p.sprite(0x223)
        pair=[]
        for owner,kind in ((1,0x119),(2,0x223)):
            p.owner=owner;p.u.mem_write(n.m.PARENT+0x3c,bytes([owner]))
            slot,c=p.create(kind);p.place(c,240+owner*64,240);pair.append((slot,c))
        p.w(pair[0][1]+0x9cc,10000);p.w(pair[0][1]+0x9d4,10000)
        for player in range(1,9):p.w(n.m.MANAGER+0x7158+player*4,player)
        units.append(pair)
    assert bytes(peers[0].u.mem_read(0x7300000,0x10000))==bytes(peers[1].u.mem_read(0x7300000,0x10000))
    outcomes=[]
    for weapon in range(67):
        for airborne in (0,1):
            values=[]
            for p,pair in zip(peers,units):
                p.w(pair[0][1]+0x1388,weapon);p.w(pair[1][1]+0x2c,airborne)
                values.append(p.call(0x445280,(pair[0][0],pair[1][0]),n.m.MANAGER,8))
            assert values[0]==values[1],(weapon,airborne,values)
            n.l.compare(*peers);outcomes.append(values[0])
    assert 0 in outcomes and 1 in outcomes,'fixture never reached both eligibility outcomes'
    report={'cases':len(outcomes),'accepted':outcomes.count(1),'rejected':outcomes.count(0),'full_combat':False,'limitations':['weapon stat prefix only','no projectile lifecycle or damage assertion','seeded weapon identifiers']}
    (n.m.root/'.tools/combat-targets-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS',json.dumps(report))
if __name__=='__main__':main()
