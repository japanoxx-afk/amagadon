"""Compare native sync traces from two logging-report ZIPs (stdlib only).
Usage: python scripts/compare-sync-traces.py player1.zip player2.zip
Reports evidence, not a proven cause. Does not upload or modify either ZIP.
"""
import argparse,json,struct,zipfile
from pathlib import Path

def load(path):
 with zipfile.ZipFile(path) as z:
  choices=[]
  for name in z.namelist():
   if name.endswith('/sync-trace.json'):
    index=json.loads(z.read(name).decode('utf-8-sig'))
    if index.get('format')==1:choices.append((index.get('frozen',False),name,index))
  if not choices:raise ValueError('No sync-trace.json in '+str(path))
  _,name,index=max(choices,key=lambda x:(x[0],x[1]));raw=z.read(name[:-4]+'dat');frames={}
  for row in index['stableFrames']:
   o=row['offset'];seq=row['sequence']
   if o<4096 or o+2048>len(raw):continue
   if struct.unpack_from('<I',raw,o)[0]!=seq or struct.unpack_from('<I',raw,o+76)[0]!=seq:continue
   if struct.unpack_from('<I',raw,o+88)[0]!=index['generation']:continue
   frames[row['clock']]=(row,raw[o+128:o+1536])
  return name,index,frames

def compare(a,b):
 an,ai,af=load(a);bn,bi,bf=load(b);common=sorted(af.keys()&bf.keys());result={'left':an,'right':bn,'commonFrames':len(common),'range':[common[0],common[-1]] if common else [],'firstStateDifference':None,'firstOrderDifference':None,'firstRandomDifference':None,'firstPacketDifference':None,'note':'Matches simulation clocks from selected sessions; verify both reports describe the same match. Differences are indicators, not proof of cause. Local input staging is deliberately excluded from packet comparison.'}
 for clock in common:
  x,xp=af[clock];y,yp=bf[clock]
  if result['firstStateDifference'] is None and (x['unitHash']!=y['unitHash'] or x['unitCount']!=y['unitCount']):result['firstStateDifference']={'clock':clock,'leftHash':x['unitHash'],'rightHash':y['unitHash'],'players':[p for p in range(10) if x['playerHashes'][p]!=y['playerHashes'][p]]}
  if result['firstOrderDifference'] is None and 'orderHash' in x and 'orderHash' in y and x['orderHash']!=y['orderHash']:result['firstOrderDifference']={'clock':clock,'leftHash':x['orderHash'],'rightHash':y['orderHash'],'players':[p+1 for p in range(8) if x['playerOrderHashes'][p]!=y['playerOrderHashes'][p]]}
  if result['firstRandomDifference'] is None and any(x[k]!=y[k] for k in ('engineRngIndex','crtRng','fpuControl')):result['firstRandomDifference']={'clock':clock,'left':{k:x[k] for k in ('engineRngIndex','crtRng','fpuControl')},'right':{k:y[k] for k in ('engineRngIndex','crtRng','fpuControl')}}
  if result['firstPacketDifference'] is None:
   players=[]
   for p in range(1,9):
    start=768+p*64;one=xp[start:start+64];two=yp[start:start+64]
    if one!=two:players.append({'player':p,'differentBytes':[i for i in range(64) if one[i]!=two[i]]})
   if players:result['firstPacketDifference']={'clock':clock,'players':players}
 return result
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('left',type=Path);parser.add_argument('right',type=Path);args=parser.parse_args()
 try:print(json.dumps(compare(args.left,args.right),ensure_ascii=False,indent=2))
 except (ValueError,KeyError,zipfile.BadZipFile,OSError) as e:parser.exit(1,str(e)+'\n')
