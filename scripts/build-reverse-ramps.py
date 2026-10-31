"""Build isolated reverse-ramp candidates. Never edits the source installation.

This development tool is not a launcher installer. It writes a separate archive
copy under the repository's .tools folder for placement/rendering verification.
"""
from pathlib import Path
import importlib.util,struct,shutil,sys,hashlib,json

spec=importlib.util.spec_from_file_location('terrain',Path(__file__).with_name('inspect-earth-terrain.py'))
terrain=importlib.util.module_from_spec(spec);spec.loader.exec_module(terrain)

def build(ms,pi):
    records=terrain.decode(ms)
    for slot in (57,58):
        if records[slot]['name']!='이름 없음' or records[slot]['type']!=0:
            raise ValueError('Reserved terrain slot already occupied')
    if len(pi)<24 or struct.unpack_from('<3H',pi,8)!=(32,32,8):raise ValueError('Unknown tile format')
    count=struct.unpack_from('<H',pi,18)[0]
    if len(pi)!=24+count*1024:raise ValueError('Tile count/length mismatch')
    out=bytearray(ms);pixels=bytearray(pi);cache={}
    def reverse_tile(index):
        if index==65535:return index
        if not 0<=index<count:raise ValueError('Invalid source tile')
        if index not in cache:
            new=(len(pixels)-24)//1024
            if new>=10000:raise ValueError('ACE surface table capacity exceeded')
            cache[index]=new
            # Rotate the geometry and indexed texture together. Lighting/art is
            # separately inspected before this candidate can be shipped.
            pixels.extend(pi[24+index*1024:24+(index+1)*1024][::-1])
        return cache[index]
    for source,slot,name in [(15,57,'언덕경사-10시'),(14,58,'언덕경사-2시')]:
        off=terrain.HEADER+source*terrain.STRIDE
        src=ms[off:off+terrain.STRIDE];r=bytearray(src)
        for start in terrain.GRID_FIELDS.values():
            for x in range(8):
                for y in range(6):r[start+x*13+y]=src[start+(7-x)*13+5-y]
            # The remaining rows are auxiliary brush entries, not part of the
            # six-row connection footprint. Preserve rather than reinterpret.
        title=name.encode('cp949');r[0x1b2:0x1d0]=title+bytes(30-len(title))
        r[0x1d2],r[0x1d3]=src[0x1d3],src[0x1d2]
        for x in range(8):
            for y in range(6):
                for variant in range(15):
                    for frame in range(4):
                        a=0x1d4+((x*13+y)*15+variant)*8+frame*2
                        q=0x1d4+(((7-x)*13+5-y)*15+variant)*8+frame*2
                        struct.pack_into('<H',r,a,reverse_tile(struct.unpack_from('<H',src,q)[0]))
        dest=terrain.HEADER+slot*terrain.STRIDE;out[dest:dest+terrain.STRIDE]=r
    struct.pack_into('<H',pixels,18,(len(pixels)-24)//1024)
    return bytes(out),bytes(pixels)

def prepare(source,destination):
    source=source.resolve();destination=destination.resolve()
    lab=Path(__file__).resolve().parent.parent/'.tools'
    if lab not in destination.parents or destination==source:raise ValueError('Destination must be an isolated .tools subfolder')
    destination.mkdir(parents=True,exist_ok=True)
    ms=terrain.archive_entry(source,b'Data\\Earth.ms');pi=terrain.archive_entry(source,b'Data\\Earth.pi')
    patched_ms,patched_pi=build(ms,pi)
    hed=bytearray((source/'Armageddon.HED').read_bytes())
    shutil.copyfile(source/'Armageddon.MFP',destination/'Armageddon.MFP')
    with (destination/'Armageddon.MFP').open('ab') as f:
        for name,data in [(b'Data\\Earth.ms',patched_ms),(b'Data\\Earth.pi',patched_pi)]:
            hits=[8+i*72 for i in range(struct.unpack_from('<I',hed,4)[0]) if hed[12+i*72:12+i*72+len(name)].lower()==name.lower()]
            if len(hits)!=1:raise ValueError('Ambiguous archive entry')
            struct.pack_into('<I',hed,hits[0],f.tell());struct.pack_into('<I',hed,hits[0]+68,len(data));f.write(data)
    (destination/'Armageddon.HED').write_bytes(hed)
    for name in ('ACE.exe','Armageddon.exe','binkw32.dll','Mss32.dll','ArmaInfo.dat','option.dat'):
        if (source/name).exists():shutil.copyfile(source/name,destination/name)
    report={'candidateOnly':True,'msSHA256':hashlib.sha256(patched_ms).hexdigest(),'piSHA256':hashlib.sha256(patched_pi).hexdigest(),'addedTiles':(len(patched_pi)-len(pi))//1024}
    (destination/'terrain-candidate.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report)

if __name__=='__main__':prepare(Path(sys.argv[1]),Path(sys.argv[2]))
