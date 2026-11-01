"""Offline sync report comparison regression; no real user reports."""
import importlib.util,json,struct,tempfile,zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('compare',Path(__file__).with_name('compare-sync-traces.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
def report(path,different=False,torn=False):
 raw=bytearray(4096+1024*2048);rows=[]
 for seq,clock in ((1,10),(2,11)):
  o=4096+seq*2048;struct.pack_into('<I',raw,o,seq);struct.pack_into('<I',raw,o+76,seq if not torn else 0);struct.pack_into('<I',raw,o+88,1)
  changed=different and clock==11;hashes=[0]*10;hashes[2]=2 if changed else 1
  rows.append(dict(offset=o,sequence=seq,clock=clock,unitHash=2 if changed else 1,unitCount=3,playerHashes=hashes,engineRngIndex=5 if changed else 4,crtRng=9,fpuControl=0x27f,orderHash=2 if changed else 1,playerOrderHashes=[0,2 if changed else 1]+[0]*6))
  if changed:raw[o+128+768+2*64+3]=1
 index=dict(format=1,frozen=True,generation=1,stableFrames=rows)
 with zipfile.ZipFile(path,'w') as z:z.writestr('Diagnostics/session/sync-trace.json',json.dumps(index));z.writestr('Diagnostics/session/sync-trace.dat',raw)
with tempfile.TemporaryDirectory() as d:
 a,b,c=[Path(d)/n for n in ('a.zip','b.zip','c.zip')];report(a);report(b,True);report(c,torn=True)
 r=mod.compare(a,a);assert r['commonFrames']==2 and r['firstStateDifference'] is None
 r=mod.compare(a,b);assert r['firstStateDifference']==dict(clock=11,leftHash=1,rightHash=2,players=[2]);assert r['firstOrderDifference']==dict(clock=11,leftHash=1,rightHash=2,players=[2]);assert r['firstRandomDifference']['clock']==11;assert r['firstPacketDifference']['players']==[dict(player=2,differentBytes=[3])]
 assert mod.compare(a,c)['commonFrames']==0
print('PASS report comparison: common clocks, first unit/player/RNG/command differences and torn slots')
