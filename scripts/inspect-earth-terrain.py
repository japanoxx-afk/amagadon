"""Read-only decoder for ACE Earth terrain definitions; emits no patched assets.

Usage: python scripts/inspect-earth-terrain.py GAME_DIRECTORY OUTPUT_JSON
The source game archive is never modified. Tile indices and traversal grids are
reported so a reverse-facing ramp can be implemented without guessing offsets.
"""
from pathlib import Path
import hashlib,json,struct,sys

HEADER=276
STRIDE=0x3384
COUNT=60
GRID_WIDTH,GRID_HEIGHT=8,13
# The two collision-related grids are kept under neutral names until each bit's
# semantics are verified in the game, rather than inferred from editor drawing.
GRID_FIELDS={'collision_a':0,'collision_b':0x68,'placement':0xd0,'auxiliary':0x138}

def archive_entry(folder,name):
    hed=(folder/'Armageddon.HED').read_bytes()
    count=struct.unpack_from('<I',hed,4)[0]
    if len(hed)!=8+72*count:raise ValueError('Unsupported archive header')
    matches=[]
    for i in range(count):
        record=hed[8+i*72:8+(i+1)*72]
        # Names have padding that is not necessarily zero terminated.
        if record[4:4+len(name)].lower()==name.lower():
            matches.append(struct.unpack_from('<I',record)[0:1]+struct.unpack_from('<I',record,68))
    if len(matches)!=1:raise ValueError('Archive name missing or ambiguous: '+repr(name))
    offset,size=matches[0]
    with (folder/'Armageddon.MFP').open('rb') as stream:
        if offset+size>stream.seek(0,2):raise ValueError('Archive extent out of bounds')
        stream.seek(offset);return stream.read(size)

def decode(data):
    if len(data)!=791560 or not data.startswith(b'Map Source 1.01'):
        raise ValueError('Unsupported Earth map-source layout')
    records=[]
    for index in range(COUNT):
        r=data[HEADER+index*STRIDE:HEADER+(index+1)*STRIDE]
        grid=lambda start:[[r[start+x*GRID_HEIGHT+y] for x in range(GRID_WIDTH)] for y in range(GRID_HEIGHT)]
        tiles=struct.unpack_from('<6240H',r,0x1d4)
        assert 0x1d4+len(tiles)*2+240==STRIDE
        records.append(dict(index=index,name=r[0x1b2:0x1d0].split(b'\0')[0].decode('cp949'),
            type=r[0x1d0],flags=r[0x1d1],terrainA=r[0x1d2],terrainB=r[0x1d3],
            grids={key:grid(start) for key,start in GRID_FIELDS.items()},
            tileIds=sorted(set(tiles)-{65535})))
    return records

if __name__=='__main__':
    data=archive_entry(Path(sys.argv[1]),b'Data\\Earth.ms')
    records=decode(data)
    result=dict(sourceSHA256=hashlib.sha256(data).hexdigest(),headerBytes=HEADER,recordBytes=STRIDE,
        gridWidth=GRID_WIDTH,gridHeight=GRID_HEIGHT,variantsPerCell=15,tilesPerVariant=4,
        records=records)
    Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Decoded 60 records; input archives unchanged; result:',sys.argv[2])
