"""Original child factory and multi-unit collision execution on independent peers.
Synthetic definitions with real footprint lookup; only allocation and debug printf
are external seams. Rendering/animation scheduler is not a complete match loop.
"""
import importlib.util, struct, json, hashlib, pathlib, os, subprocess, tempfile
s=importlib.util.spec_from_file_location('path_lab',pathlib.Path(__file__).with_name('test-path-production.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
from unicorn import *
from unicorn.x86_const import *

# Extract actual installed selection/position/FPU hooks from the compiled launcher.
source='''using System;using System.IO;using System.Reflection;using System.Collections.Generic;class Dump{static void Main(string[] a){foreach(var e in (Dictionary<int,byte[]>)Assembly.LoadFrom(a[0]).GetType("Amagadon.SelectionRuntime").GetMethod("Build").Invoke(null,new object[]{0x21000000}))File.WriteAllBytes(Path.Combine(a[1],e.Key.ToString("x8")+".bin"),e.Value);}}'''
with tempfile.TemporaryDirectory(prefix='amagadon-lifecycle-') as folder:
    folder=pathlib.Path(folder);(folder/'Dump.cs').write_text(source)
    subprocess.run([str(m.compiler),'/nologo','/platform:x86','/out:'+str(folder/'Dump.exe'),str(folder/'Dump.cs')],check=True)
    subprocess.run([str(folder/'Dump.exe'),str(m.launcher),str(folder)],check=True)
    selection={int(p.stem,16):p.read_bytes() for p in folder.glob('*.bin')}

CAT,DEF,HEAP=0x3600000,0x3610000,0x5000000
LAST_CASE={}
class Peer:
    def __init__(self,local,width,owner=1,poison=0):
        self.u=m.fresh(local,width,local*101);u=self.u
        u.mem_map(0,4096);u.mem_map(HEAP,0x1000000);u.mem_map(0x21000000,0x700000)
        for a,b in selection.items():u.mem_write(a,b)
        self.owner=owner;self.heap=HEAP;self.heap_limit=HEAP+0x1000000;self.allocations=[];self.children=[];self.collision_hits=0
        self.w(0x2310228,0x3630018)
        for race in range(4):self.w(0x5049fc+race*4,CAT)
        for i in range(100):self.w(CAT+4+i*4,DEF)
        u.mem_write(DEF+0x23d,b'\2');u.mem_write(DEF+0x239,b'\x08')
        for off,val in ((0x258,100),(0x25c,100),(0x278,1),(0x27c,1)):self.w(DEF+off,val)
        self.w(DEF+0x394,0x3650000);self.w(0x3650000,0)
        self.w(0x3630018+8,1);self.w(0x3630018+20,0x3640000);self.w(0x3640000+0x24,0x3641000)
        u.mem_write(0x3641000,struct.pack('<4i',-8,-8,16,16))
        self.w(m.MANAGER+8+17*4,m.PARENT);u.mem_write(m.PARENT+0x13b8,b'\1');u.mem_write(m.PARENT+0x3c,bytes([owner]))
        self.w(m.PARENT+8,DEF)
        for off,val in ((20,160),(24,200),(0x100,160),(0x104,200),(0x1398,300),(0x139c,200)):self.w(m.PARENT+off,val)
        def allocate(uc,a,size,data):
            sp=uc.reg_read(UC_X86_REG_ESP);n=self.r(sp+4)
            assert 0<n<0x100000 and self.heap+n<self.heap_limit
            out=self.heap;self.heap+=(n+15)&~15;self.allocations.append((out,n))
            uc.mem_write(out,bytes([poison])*n)
            uc.reg_write(UC_X86_REG_EAX,out);uc.reg_write(UC_X86_REG_EIP,self.r(sp));uc.reg_write(UC_X86_REG_ESP,sp+4)
        u.hook_add(UC_HOOK_CODE,allocate,begin=0x4bfad4,end=0x4bfad4)
        def collision(uc,a,size,data):self.collision_hits+=1
        u.hook_add(UC_HOOK_CODE,collision,begin=0x44239e,end=0x44239e)
        u.hook_add(UC_HOOK_CODE,collision,begin=0x442b44,end=0x442b44)
    def w(self,a,v):m.dword(self.u,a,v)
    def r(self,a):return m.read(self.u,a)
    def call(self,a,args=(),this=0,stdcall=0):
        u=self.u;u.mem_write(m.STACK-0x1000,bytes([0x55 if u.mem_read(0x4e7270,1)[0]==1 else 0xaa])*0x1100)
        u.mem_write(m.STACK,struct.pack('<'+'I'*(len(args)+1),m.RETURN,*args))
        u.reg_write(UC_X86_REG_ESP,m.STACK);u.reg_write(UC_X86_REG_ECX,this)
        m.run(u,a,m.RETURN,5000000)
        assert u.reg_read(UC_X86_REG_ESP)==m.STACK+4+stdcall,(hex(a),hex(u.reg_read(UC_X86_REG_ESP)))
        return u.reg_read(UC_X86_REG_EAX)
    def create(self,kind):
        slot=self.call(0x41f830,(17,kind))
        assert slot!=0xffffffff
        child=self.r(m.MANAGER+8+slot*4)
        assert self.u.mem_read(child+0x13b8,1)==b'\1'
        assert self.u.mem_read(child+0x3c,1)==bytes([self.owner])
        assert struct.unpack('<H',self.u.mem_read(child+12,2))[0]==kind
        self.children=[item for item in self.children if item[0]!=slot]
        self.children.append((slot,child));self.children.sort();return slot,child
    def place(self,child,x,y):
        self.call(0x471d60,(m.WORLD,child))
        self.call(0x4416c0,(x,),child,4);self.call(0x441710,(y,),child,4)
        self.call(0x471be0,(m.WORLD,child))
    def order(self,child,x,y):
        self.call(0x441c40,(x,y,m.WORLD,m.MANAGER,0),child,20)
        # Fixture starts after heading alignment, in an active movement state.
        # Movement/collision/path replan below remain native, not mocked.
        self.w(child+0x1b0,self.r(child+0x50));self.call(0x441ab0,(self.r(child+0x50),),child,4)
        self.u.mem_write(child+0x4d0,b'\2')
    def step(self,speed=4):
        for slot,child in self.children:
            self.call(0x471d60,(m.WORLD,child))
            self.call(0x442080,(speed,0,m.WORLD,m.MANAGER),child,16)
            self.call(0x471be0,(m.WORLD,child))
    def state(self):
        # Same virtual addresses on both peers; includes every child byte, not just positions.
        return {'units':[bytes(self.u.mem_read(c,0x13e0)) for _,c in self.children],
                'world':bytes(self.u.mem_read(m.WORLD,0x32f808)),
                'manager':bytes(self.u.mem_read(m.MANAGER,0x28000)),
                'rng':bytes(self.u.mem_read(0x581158,4))}
    def positions(self):return [(self.r(c+20),self.r(c+24)) for _,c in self.children]

def compare(a,b):
    left,right=a.state(),b.state()
    for field in left:
        if left[field]!=right[field]:
            if field=='units':
                for i,(x,y) in enumerate(zip(left[field],right[field])):
                    if x!=y:raise AssertionError(('unit',i,[(hex(j),x[j],y[j]) for j in range(len(x)) if x[j]!=y[j]][:20]))
            x,y=left[field],right[field]
            raise AssertionError((field,[(hex(j),x[j],y[j]) for j in range(len(x)) if x[j]!=y[j]][:20]))

def main():
    global LAST_CASE
    creation=0;ticks=0;scenarios=[]
    for owner in (1,2,8):
        a,b=Peer(1,800,owner),Peer(2,1024,owner)
        for kind in (0x12,0x113,0x21c)*4:
            LAST_CASE={'phase':'create','owner':owner,'kind':kind,'number':creation}
            assert a.create(kind)==b.create(kind);compare(a,b);creation+=1
        assert len(a.allocations)==12 and bytes(a.u.mem_read(m.GRID,0x200000))!=b'\xfe\x0f'*(1024*1024)
    for name,starts,ends in (
        ('opposing',[(160,240),(320,240)],[(320,240),(160,240)]),
        ('crossing',[(160,240),(240,160),(320,240),(240,320)],[(320,240),(240,320),(160,240),(240,160)]),
        ('crowded',[(160,200+i*24) for i in range(8)],[(320,280)]*8)):
        a,b=Peer(1,800),Peer(2,1024)
        for i,(start,end) in enumerate(zip(starts,ends)):
            for peer in (a,b):
                _,child=peer.create(0x113);peer.place(child,*start);peer.order(child,*end)
        compare(a,b);initial=a.positions()
        for tick in range(100):
            LAST_CASE={'phase':'move','scenario':name,'tick':tick}
            a.step();b.step();compare(a,b);ticks+=1
        assert a.positions()!=initial,'stationary fixture falsely passed'
        scenarios.append({'name':name,'ticks':100,'collision_branches':a.collision_hits,'positions':a.positions()})
    assert sum(s['collision_branches'] for s in scenarios)>0,'collision rejection/replan never executed'
    # Reusable native slot, with its old instance/data still allocated.
    reused=0;a,b=Peer(1,800),Peer(2,1024)
    for kind in (0x12,0x113,0x21c)*8:
        LAST_CASE={'phase':'reused-slot','iteration':reused,'kind':kind}
        for peer in (a,b):
            if peer.children:
                child=peer.children[0][1];peer.call(0x471d60,(m.WORLD,child))
                peer.u.mem_write(child+0x13b8,b'\0\0')
            assert peer.create(kind)[0]==0
        compare(a,b);reused+=1
    assert len(a.allocations)==len(b.allocations)==1
    # Poisoned fresh memory: record untouched bytes, then prove they are not read
    # by this movement scenario. Never label raw padding differences a desync.
    LAST_CASE={'phase':'poisoned-heap'}
    a,b=Peer(1,800,poison=0),Peer(2,1024,poison=165)
    a.create(0x113);b.create(0x113)
    x,y=a.state()['units'][0],b.state()['units'][0]
    untouched={i for i in range(len(x)) if x[i]!=y[i]};reads=set()
    def uninitialized_read(u,access,address,size,value,data):
        offset=address-HEAP
        if any(i in untouched for i in range(offset,offset+size)):
            reads.add((hex(u.reg_read(UC_X86_REG_EIP)),hex(offset),size))
    for peer in (a,b):
        peer.u.hook_add(UC_HOOK_MEM_READ,uninitialized_read,begin=HEAP,end=HEAP+0x13df)
        peer.order(peer.children[0][1],400,240)
    for tick in range(100):
        a.step();b.step();left,right=a.state(),b.state()
        assert all(left[k]==right[k] for k in ('world','manager','rng'))
        x,y=left['units'][0],right['units'][0]
        assert not any(x[i]!=y[i] for i in range(len(x)) if i not in untouched)
    assert not reads,('uninitialized bytes consumed',reads)
    # Positive control: reversing authoritative unit order changes collision results.
    # This is deliberate invalid input, not evidence of an ordering bug in the game.
    a,b=Peer(1,800),Peer(2,1024)
    for i in range(4):
        for peer in (a,b):
            _,child=peer.create(0x113);peer.place(child,160,200+i*24);peer.order(child,320,240)
    LAST_CASE={'phase':'reversed-order-positive-control'}
    b.children.reverse();control_tick=None
    for tick in range(80):
        a.step();b.step()
        left={slot:(a.r(c+20),a.r(c+24)) for slot,c in a.children}
        right={slot:(b.r(c+20),b.r(c+24)) for slot,c in b.children}
        if left!=right:control_tick=tick;break
    assert control_tick is not None,'test cannot detect changed collision processing order'
    report={'reversed_order_control_first_tick':control_tick,'reused_slot_creations':reused,'poisoned_heap_untouched_bytes':len(untouched),'poisoned_heap_reads':len(reads),'poisoned_heap_movement_ticks':100,'child_creations':creation,'paired_movement_ticks':ticks,'scenarios':scenarios,
            'original_sha256':hashlib.sha256(m.original.read_bytes()).hexdigest(),
            'launcher_sha256':hashlib.sha256(m.launcher.read_bytes()).hexdigest(),
            'full_match':False,'synthetic_definitions':True,'external_seams':['CRT operator new','debug printf']}
    (m.root/'.tools/unit-lifecycle-results.json').write_text(json.dumps(report,indent=2))
    print('PASS',json.dumps(report))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        (m.root/'.tools/unit-lifecycle-failure.json').write_text(json.dumps({'case':LAST_CASE,'error':repr(exc)},indent=2));raise
