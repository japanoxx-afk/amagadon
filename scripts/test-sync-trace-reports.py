"""Offline sync report comparison regression; no real user reports."""
import importlib.util,json,struct,tempfile,zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('compare',Path(__file__).with_name('compare-sync-traces.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
def report(path,different=False,torn=False,hidden=True,version='0.3.68',hidden_version=1,cursor=None,local=0):
 raw=bytearray(4096+1024*2048);rows=[]
 for seq,clock in ((1,10),(2,11)):
  o=4096+seq*2048;struct.pack_into('<I',raw,o,seq);struct.pack_into('<I',raw,o+76,seq if not torn else 0);struct.pack_into('<I',raw,o+88,1)
  changed=different and clock==11;hashes=[0]*10;hashes[2]=2 if changed else 1
  rows.append(dict(offset=o,sequence=seq,clock=clock,unitHash=2 if changed else 1,unitCount=3,playerHashes=hashes,engineRngIndex=5 if changed else 4,crtRng=9,fpuControl=0x27f,orderHash=2 if changed else 1,playerOrderHashes=[0,2 if changed else 1]+[0]*6))
  if hidden:
   struct.pack_into('<8I',raw,o+1536,0x31545348,hidden_version,16,16,512,1,0,0)
   if hidden_version>=2:struct.pack_into('<2I',raw,o+1536+448,local,0x205)
   for p in range(1,9):struct.pack_into('<i',raw,o+1568+(p-1)*44+20,p*7)
   if cursor and clock==11:
    struct.pack_into('<i',raw,o+1568+(cursor[0]-1)*44+24,cursor[1])
    if cursor[2]:raw[o+128+768+cursor[0]*64]=1
   struct.pack_into('<i',raw,o+1568+44,99 if changed else 100)
   struct.pack_into('<I',raw,o+1920+7*4,123 if changed else 122)
  if changed:raw[o+128+768+2*64+3]=1
 index=dict(format=1,frozen=True,generation=1,stableFrames=rows)
 unitraw=bytearray(4096+3*54464);unitrows=[]
 for seq,clock in ((1,10),(2,11)):
  o=4096+seq*54464;struct.pack_into('<6I',unitraw,o,seq,clock,1,1,0,seq)
  struct.pack_into('<iHBBiiiiiBBBB',unitraw,o+64,0,547,1,0 if different and clock==11 else 1,3110,569,120,220,1,13,0,0,0)
  unitrows.append(dict(sequence=seq,clock=clock,count=1,offset=o))
 with zipfile.ZipFile(path,'w') as z:
  z.writestr('Diagnostics/session/sync-trace.json',json.dumps(index));z.writestr('Diagnostics/session/sync-trace.dat',raw)
  if version:z.writestr('Diagnostics/session/events.jsonl','\ufeff'+json.dumps(dict(kind='start',data=dict(version=version)))+'\n')
  z.writestr('Diagnostics/session/unit-trace.json',json.dumps(dict(format=1,generation=1,frames=unitrows)));z.writestr('Diagnostics/session/unit-trace.dat',unitraw)
with tempfile.TemporaryDirectory() as d:
 a,b,c=[Path(d)/n for n in ('a.zip','b.zip','c.zip')];report(a);report(b,True);report(c,torn=True)
 r=mod.compare(a,a);assert r['commonFrames']==2 and r['firstStateDifference'] is None
 r=mod.compare(a,b);assert r['firstStateDifference']==dict(clock=11,leftHash=1,rightHash=2,players=[2]);assert r['firstOrderDifference']==dict(clock=11,leftHash=1,rightHash=2,players=[2]);assert r['firstRandomDifference']['clock']==11;assert r['firstPacketDifference']['players']==[dict(player=2,differentBytes=[3])]
 assert r['firstUnitDifference']['clock']==11 and r['firstUnitDifference']['units'][0]['id']==0 and r['firstUnitDifference']['units'][0]['left']['active']==1 and r['firstUnitDifference']['units'][0]['right']['active']==0
 assert r['firstEngineRandomDifference']['clock']==11
 assert [v['clock'] for v in r['unitTransitionHistory']]==[10,11]
 assert mod.compare(a,c)['commonFrames']==0
 assert r['hiddenStateCommonFrames']==2
 assert r['firstHiddenStateDifferences']=={'player2.ore':{'clock':11,'left':100,'right':99},'gridStripe7':{'clock':11,'left':122,'right':123}}
 report(c,hidden=False);assert mod.compare(a,c)['hiddenStateCommonFrames']==0
 assert r['versionWarning'] is None and r['launcherVersions']=={'left':'0.3.68','right':'0.3.68'}
 report(c,version='0.3.61');assert '0.3.61' in mod.compare(a,c)['versionWarning']
 # v1 (0.3.67) recorded player p+1's 0x51BC28 value under p: remapped, player 1 unknown.
 h=mod.load(a)[2][10][0]['hiddenState'];assert h['version']==1 and h['players']['1']['modeBc28'] is None and h['players']['3']['modeBc28']==14
 # Idle-frame cursor differences are separated; on a command frame they are candidates.
 d1,d2,d3,d4=[Path(d)/n for n in ('d1.zip','d2.zip','d3.zip','d4.zip')]
 report(d1,hidden_version=2,local=0);report(d2,hidden_version=2,cursor=(2,1,False),local=0x3c)
 r=mod.compare(d1,d2);assert r['firstHiddenStateDifferences']=={} and 'player2.cursorBcf4' in r['firstIdleCursorDifferences'] and r['idleCursorDifferenceFrames']==1,r
 assert r['localUiSample']['right']=={'localUiMode':0x3c,'localBuildingKind':0x205} and r['hiddenStateVersions']==[2]
 report(d3,hidden_version=2,cursor=(2,1,True));report(d4,hidden_version=2,cursor=(2,0,True))
 r=mod.compare(d3,d4);assert r['firstHiddenStateDifferences']=={'player2.cursorBcf4':{'clock':11,'left':1,'right':0}},r
print('PASS report comparison: common clocks, first unit/player/RNG/command differences, torn slots, v1 0x51BC28 remap, idle-cursor separation, local UI mirrors and launcher version warning')
