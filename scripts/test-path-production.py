"""Offline paired original-x86 search, occupancy and production exit tests.
Usage: python scripts/test-path-production.py [launcher.exe] [original.exe]
Only native debug printf is substituted; no search/occupancy result is mocked.
Production begins at the extent boundary, not the timer/creation allocator.
"""
import hashlib, os, pathlib, struct, subprocess, sys, tempfile, textwrap
root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / '.tools'))
import pefile
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

launcher = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'dist/AmagadonLauncher.exe').resolve()
original = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else pathlib.Path(os.environ.get('AMAGADON_GAME_EXE', 'C:/Users/seo/Downloads/armaggeddon/armaggeddon/Armageddon.exe'))
assert hashlib.sha256(original.read_bytes()).hexdigest() == '34f0bf9ed99fbf3ab88c410a3a52a2f6904e7bc7f5b88fb4ebadc935c2e9b466'
pe = pefile.PE(str(original))
base = pe.OPTIONAL_HEADER.ImageBase
STACK, RETURN, CONTEXT = 0x400f000, 0x4001000, 0x3000000
ks = Ks(KS_ARCH_X86, KS_MODE_32)

def dword(u, a, v): u.mem_write(a, struct.pack('<I', v & 0xffffffff))
def read(u, a): return struct.unpack('<I', u.mem_read(a, 4))[0]
def run(u, start, stop, budget=1000000):
    u.emu_start(start, stop, count=budget)
    assert u.reg_read(UC_X86_REG_EIP) == stop, f'Instruction budget exhausted at {u.reg_read(UC_X86_REG_EIP):x}'

# Reflection loads the exact requested launcher, avoiding stale fixture DLLs.
fixture = r'''using System;using System.IO;using System.Reflection;using System.Collections.Generic;
class Dump {static void Main(string[] args){var a=Assembly.LoadFrom(args[0]);var t=a.GetType("Amagadon.RallySpawn",true);var edits=(Dictionary<int,byte[]>)t.GetMethod("Build").Invoke(null,new object[]{0x20000000});foreach(var e in edits)File.WriteAllBytes(Path.Combine(args[1],e.Key.ToString("x8")+".bin"),e.Value);}}'''
with tempfile.TemporaryDirectory(prefix='amagadon-rally-') as folder:
    folder = pathlib.Path(folder)
    source = folder / 'Dump.cs'; source.write_text(fixture)
    exe = folder / 'Dump.exe'
    compiler = pathlib.Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
    subprocess.run([str(compiler), '/nologo', '/platform:x86', '/out:' + str(exe), str(source)], check=True)
    subprocess.run([str(exe), str(launcher), str(folder)], check=True)
    edits = {int(p.stem, 16): p.read_bytes() for p in folder.glob('*.bin')}

import random, json, time
WORLD, MANAGER, PARENT, OUTPUT = 0x3000000,0x3400000,0x3420000,0x3700000
GRID=WORLD+0x12f808
REGS=(UC_X86_REG_EBX,UC_X86_REG_EBP,UC_X86_REG_ESI,UC_X86_REG_EDI)

def fresh(local,width,noise):
    u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(base,pe.OPTIONAL_HEADER.SizeOfImage)
    for sec in pe.sections:u.mem_write(base+sec.VirtualAddress,sec.get_data())
    u.mem_map(WORLD,0x800000);u.mem_map(0x4000000,0x100000);u.mem_map(0x20000000,24576)
    for a,b in edits.items():u.mem_write(a,b)
    dword(u,0x4f9de4,WORLD);dword(u,0x504a10,MANAGER)
    dword(u,0x5812e8,32);dword(u,0x5812ec,32)
    u.mem_write(WORLD+0xe6,struct.pack('<HH',32,32))
    u.mem_write(GRID,b'\xfe\x0f'*(1024*1024))
    u.mem_write(0x4e7270,bytes([local]));dword(u,0x513ed4,1);dword(u,0x4f75ec,width)
    # Exercise both axes: leaving height at the original 600 understated mixed-HD coverage.
    dword(u,0x4f75f0,768 if width==1024 else 600)
    u.mem_write(0x52f510+local*64+16,struct.pack('<4H',noise,noise+1,noise+2,noise+3))
    u.mem_write(0x492280,b'\xc3') # debug printf only; no simulation leaf mocked
    dword(u,STACK,RETURN);u.reg_write(UC_X86_REG_ESP,STACK)
    run(u,0x471760,RETURN,3000000) # native path table initialization
    assert u.reg_read(UC_X86_REG_ESP)==STACK+4
    return u

def grid(u,cells):
    u.mem_write(GRID,b'\xfe\x0f'*(1024*1024))
    for x,y in cells:u.mem_write(GRID+2*(y*1024+x),b'\xff\x0f')

def path(u,start,end,footprint=1,special=0,poison=0):
    u.mem_write(STACK-0x1000,bytes([poison])*0x1100)
    u.mem_write(OUTPUT,struct.pack('<4i',*start,*end));u.mem_write(OUTPUT+0x100,b'\xcc'*0x200)
    u.mem_write(STACK,struct.pack('<8I',RETURN,OUTPUT,OUTPUT+8,OUTPUT+0x100,OUTPUT+0x200,footprint,footprint,special))
    u.reg_write(UC_X86_REG_ESP,STACK)
    for r in REGS:u.reg_write(r,0xabc000+r)
    before=bytes(u.mem_read(GRID,0x200000))
    run(u,0x471790,RETURN,6000000)
    assert u.reg_read(UC_X86_REG_ESP)==STACK+4
    assert all(u.reg_read(r)==0xabc000+r for r in REGS)
    assert bytes(u.mem_read(GRID,0x200000))==before,'search mutated occupancy'
    axes=[]
    for a in (OUTPUT+0x100,OUTPUT+0x200):
        vals=list(struct.unpack('<50H',u.mem_read(a,100)))
        assert 65535 in vals,'missing native path terminator'
        axes.append(vals[:vals.index(65535)])
    assert len(axes[0])==len(axes[1])
    return {'scratch_sha256':hashlib.sha256(bytes(u.mem_read(0x4eb2b0,0x8300))).hexdigest(), 'success':u.reg_read(UC_X86_REG_EAX),'status':read(u,0x4eb2b4),'waypoints':list(zip(*axes))}

def spawn(u,dx,dy,producer=17):
    u.mem_write(STACK-0x100,bytes(0x200))
    dword(u,MANAGER+8+producer*4,PARENT)
    dword(u,PARENT+20,160);dword(u,PARENT+24,200)
    dword(u,PARENT+0x1398,160+dx);dword(u,PARENT+0x139c,200+dy)
    dword(u,STACK+92,0x41f97b);dword(u,STACK+100,producer)
    u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_EAX,2);u.reg_write(UC_X86_REG_ECX,0)
    run(u,0x44cf0a,0x44cf10)
    dword(u,STACK+60,21);dword(u,STACK+64,19);dword(u,STACK+96,OUTPUT)
    dword(u,STACK+0x6c,WORLD)
    for off,val in ((0x2c,-1),(0x30,-1),(0x34,1),(0x38,1)):dword(u,STACK+off,val)
    u.mem_write(STACK+19,b'\0');u.mem_write(STACK+0x12,b'\x01')
    for reg,val in ((UC_X86_REG_ECX,9),(UC_X86_REG_EBX,32),(UC_X86_REG_EDI,9),(UC_X86_REG_ESI,31)):
        u.reg_write(reg,val)
    run(u,0x44cf5b,0x41f97b,3000000)
    assert u.reg_read(UC_X86_REG_ESP)==STACK+116
    return (u.reg_read(UC_X86_REG_EAX),read(u,OUTPUT),read(u,OUTPUT+4))

LAST_CASE={}

def main():
    global LAST_CASE
    began=time.monotonic();seed=int(os.environ.get('AMAGADON_LAB_SEED','20261114'));rng=random.Random(seed);pairs=0
    layouts={'open':set(),'wall-gap':{(20,y) for y in range(5,40)},
             'closed-wall':{(20,y) for y in range(128)},
             'maze':{(x,y) for x in (20,40,60) for y in range(5,90) if not (x//20*17<=y<x//20*17+5)}}
    results=[]
    for name,cells in layouts.items():
        left=fresh(1,800,71);right=fresh(2,1024,900);grid(left,cells);grid(right,cells)
        for turn in range(140): # crosses the native 8-bit cache generation rollover
            start=(10,10) if turn==0 else (rng.randrange(2,18),rng.randrange(2,110))
            end=(30,30) if turn==0 else (rng.randrange(25,100),rng.randrange(2,110))
            LAST_CASE={'phase':'path','layout':name,'turn':turn,'start':start,'end':end,'footprint':1+turn%2}
            a=path(left,start,end,1+turn%2,0,0x55);b=path(right,start,end,1+turn%2,0,0xaa)
            assert a==b,(name,turn,start,end,a,b)
            if turn==0:results.append({'layout':name,**a})
            pairs+=1
        print('PASS path layout',name,flush=True)
    a=fresh(1,800,71);b=fresh(2,1024,900);grid(b,layouts['wall-gap'])
    assert path(a,(10,10),(30,30))['waypoints']!=path(b,(10,10),(30,30))['waypoints'],'grid difference not detected'
    spawn_pairs=0;spawn_results=[]
    for blocked in ('none','terrain','unit'):
        a=fresh(1,800,71);b=fresh(2,1024,900)
        cells={(x,y) for x in range(19,25) for y in range(15,35)} if blocked!='none' else set()
        grid(a,cells);grid(b,cells)
        if blocked=='unit':
            for u in (a,b):
                dword(u,MANAGER+8+5*4,0x3500000);u.mem_write(0x3500000+0x13b8,b'\1')
                for x,y in cells:u.mem_write(GRID+2*(y*1024+x),struct.pack('<H',5*2))
        for dx,dy in ((100,0),(-100,0),(0,100),(0,-100),(0,0)):
            for producer in (1,17,257,1699):
                LAST_CASE={'phase':'spawn','obstacle':blocked,'rally':[dx,dy],'producer':producer}
                left=spawn(a,dx,dy,producer);right=spawn(b,dx,dy,producer)
                assert left==right,(blocked,dx,dy,producer,left,right)
                spawn_pairs+=1
                if producer==17:spawn_results.append({'blocked':blocked,'rally':[dx,dy],'result':left})
    clear=next(x['result'] for x in spawn_results if x['blocked']=='none' and x['rally']==[100,0])
    blocked=next(x['result'] for x in spawn_results if x['blocked']=='terrain' and x['rally']==[100,0])
    assert clear!=blocked,'real production collision fallback not exercised'
    # Native free-slot chooser, including tombstones and capacity exhaustion.
    allocation_pairs=0
    for hole in (0,1,257,1699,None):
        for tombstone in (0,1):
            peers=[fresh(1,800,71),fresh(2,1024,900)];answers=[]
            for u in peers:
                live,dead=0x3500000,0x3502000
                u.mem_write(live+0x13b8,b'\1');u.mem_write(dead+0x13b9,bytes([tombstone]))
                for slot in range(1700):dword(u,MANAGER+8+slot*4,dead if slot==hole else live)
                dword(u,STACK,RETURN);u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ECX,MANAGER)
                run(u,0x447400,RETURN)
                assert u.reg_read(UC_X86_REG_ESP)==STACK+4
                answers.append((u.reg_read(UC_X86_REG_EAX),read(u,MANAGER+4)))
            assert answers[0]==answers[1]
            assert answers[0][0]==(hole if hole is not None and not tombstone else 0xffffffff)
            allocation_pairs+=1
    # Native production timer and completed-queue state transitions. Stop before
    # 41F830 child creation; that entire allocator is explicitly out of scope.
    timer_pairs=0;completion_pairs=0
    a=fresh(1,800,71);b=fresh(2,1024,900)
    for tick in range(420):
        states=[]
        for u in (a,b):
            u.reg_write(UC_X86_REG_ESI,PARENT);u.reg_write(UC_X86_REG_EDI,0)
            u.reg_write(UC_X86_REG_ESP,STACK)
            run(u,0x430ac9,0x430afa)
            states.append(tuple(read(u,PARENT+off) for off in (0x78c,0x7c0,0x7c4)))
        expected=((tick+1)//21,(tick+1)%21,20)
        assert states[0]==states[1]==expected,(tick,states,expected)
        timer_pairs+=1
    for kind in (0x12,0x113,0x116,0x21c):
        for variant in (0,0x1d):
            states=[]
            for u in (a,b):
                dword(u,PARENT+0x85c,3);dword(u,PARENT+0x78c,15);dword(u,PARENT+0x778,18)
                u.mem_write(PARENT+0x875,b'\1');u.mem_write(PARENT+14,struct.pack('<H',17))
                dword(u,OUTPUT,kind);u.mem_write(OUTPUT+8,bytes([variant]))
                u.reg_write(UC_X86_REG_ESI,PARENT);u.reg_write(UC_X86_REG_EDI,0)
                u.reg_write(UC_X86_REG_EBP,OUTPUT);u.reg_write(UC_X86_REG_EBX,OUTPUT+8)
                u.reg_write(UC_X86_REG_ESP,STACK);run(u,0x430bc6,0x430c08)
                assert u.reg_read(UC_X86_REG_ESP)==STACK-8
                states.append((read(u,PARENT+0x85c),read(u,PARENT+0x78c),read(u,PARENT+0x778),u.mem_read(PARENT+0x875,1)[0],read(u,STACK-8),read(u,STACK-4)&0xffff))
            assert states[0]==states[1]==(2,0,0,0,17,0x117 if kind==0x116 and variant==0x1d else kind)
            completion_pairs+=1
    report={'launcher_sha256':hashlib.sha256(launcher.read_bytes()).hexdigest(),'original_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'timer_pairs':timer_pairs,'completion_pairs':completion_pairs,'allocation_pairs':allocation_pairs,'seed':seed,'path_pairs':pairs,'spawn_pairs':spawn_pairs,'native_path_examples':results,
            'native_spawn_examples':spawn_results,'seconds':round(time.monotonic()-began,3),
            'full_match':False,'pathfinding_mocked':False,'occupancy_mocked':False}
    (root/'.tools/path-production-results.json').write_text(json.dumps(report,indent=2))
    (root/f'.tools/path-production-results-{seed}.json').write_text(json.dumps(report,indent=2))
    print('PASS path/production:',json.dumps({k:v for k,v in report.items() if k not in ('native_path_examples','native_spawn_examples')}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        (root/'.tools/path-production-failure.json').write_text(json.dumps({'seed':os.environ.get('AMAGADON_LAB_SEED','20261114'),'error':repr(exc),'last_case':LAST_CASE},indent=2))
        raise
