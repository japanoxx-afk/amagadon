"""Native SPR loader and frame metadata; uses local archive, never bundles assets."""
import importlib.util,pathlib,struct,json,hashlib,time
s=importlib.util.spec_from_file_location('scheduler',pathlib.Path(__file__).with_name('test-native-scheduler.py'))
n=importlib.util.module_from_spec(s);s.loader.exec_module(n)
from unicorn import *
from unicorn.x86_const import *

class SpritePeer(n.RealPeer):
    def __init__(self,local,width):
        super().__init__(local,width)
        self.u.mem_map(0x7200000,0x100000)
        self.w(0x2310228,0x7200018);self.w(0x230fe0c,256)
        self.u.mem_write(0x4c071e,b'\xe9'+struct.pack('<i',0x4bfad4-0x4c071e-5))
        self.u.mem_write(0x4c07aa,b'\xc3') # fixture allocator never reclaims
        self.sprite_report=[];self.loaded={}
    def sprite(self,kind):
        if kind in self.loaded:return self.loaded[kind]
        race,index=kind>>8,kind&255
        a=struct.unpack('<I',n.m.pe.get_data(0x4d9700+race*200+index*4-0x400000,4))[0]
        name=n.m.pe.get_data(a-0x400000,100).split(b'\0')[0].decode('cp949')
        blob=n.archive('pattern\\'+('Earth','Elca','Ead','Neutral')[race]+'\\'+name+'.spr')
        pos=[0]
        def io(u,address,size,data):
            sp=u.reg_read(UC_X86_REG_ESP)
            if address==0x494ac0:out=1
            elif address==0x494ad0:out=0
            elif address==0x494bf0:
                handle,offset,origin=struct.unpack('<3I',u.mem_read(sp+4,12))
                offset=struct.unpack('<i',struct.pack('<I',offset))[0]
                pos[0]=(0 if origin==0 else pos[0] if origin==1 else len(blob))+offset;out=0
            else:
                dest,sz,num=struct.unpack('<3I',u.mem_read(sp+4,12));amount=sz*num
                chunk=blob[pos[0]:pos[0]+amount];assert len(chunk)==amount,(pos[0],amount,len(blob))
                if chunk:u.mem_write(dest,chunk)
                pos[0]+=amount;out=num
            u.reg_write(UC_X86_REG_EAX,out);u.reg_write(UC_X86_REG_EIP,self.r(sp));u.reg_write(UC_X86_REG_ESP,sp+4)
        hooks=[self.u.hook_add(UC_HOOK_CODE,io,begin=a,end=a) for a in (0x494ac0,0x494ad0,0x494bf0,0x494b40)]
        try:
            slot=self.call(0x4bdea0,(0,0x72f0000,0x72f0004))
        finally:
            for h in hooks:self.u.hook_del(h)
        assert slot<256,(hex(kind),slot)
        handle=0x72e0000+kind*24;self.w(handle,slot);self.w(handle+4,self.r(0x72f0004))
        definition=self.r(self.catalogs[race][0]+4+index*4);self.w(definition+0x394,handle)
        frames=self.r(0x7200018+slot*24+8)
        assert frames>0
        assert pos[0]+4==len(blob)
        self.loaded[kind]=(slot,frames)
        self.sprite_report.append({'kind':hex(kind),'frames':frames,'sha256':hashlib.sha256(blob).hexdigest()})
        return slot,frames

def main():
    results=[];started=time.perf_counter()
    for kind in (0x12,0x113,0x21c,0x1b,0x119,0x11b,0x223,0x226):
        a,b=SpritePeer(1,800),SpritePeer(2,1024)
        frame_results=[]
        for p in (a,b):
            p.sprite(0);_,frames=p.sprite(kind)
            handle=0x72e0000+kind*24;metadata=[]
            for frame in range(frames):
                p.u.mem_write(0x72f1000,b'\0'*64)
                p.call(0x4bd140,(handle,frame,0x72f1000,0x72f1004))
                p.call(0x4bd2e0,(handle,frame,0x72f1010,0))
                metadata.append(bytes(p.u.mem_read(0x72f1000,64)))
            frame_results.append(metadata)
            p.w(0x57e2a0,0x70a0000)
            for i in range(3):p.w(0x70a0000+0x33a8+4*i,100)
            for j in range(4):
                _,c=p.create(kind);p.place(c,160,200+j*48)
                p.u.mem_write(c+0x464,b'\2');p.w(c+0xa4,500);p.w(c+0xf4,240)
                p.w(c+0x4a4,500);p.w(c+0x4a8,240)
        assert frame_results[0]==frame_results[1]
        initial=a.positions()
        for tick in range(1,301):
            a.scheduler_step(tick);b.scheduler_step(tick,(8,6));n.l.compare(a,b)
        assert a.positions()!=initial
        results.append({'kind':hex(kind),'frames':frames,'ticks':300,'positions':a.positions(),'rotations':a.rotation_calls,'assets':a.sprite_report})
    report={'cases':results,'seconds':time.perf_counter()-started,'real_sprite_loader':True,'rendering':False,'full_combat':False}
    (n.m.root/'.tools/real-sprites-results.json').write_text(json.dumps(report,indent=2))
    print('PASS',json.dumps(report))

if __name__=='__main__':main()
