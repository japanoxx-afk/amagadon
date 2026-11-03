"""Compare native sync traces from two logging-report ZIPs (stdlib only).
Usage: python scripts/compare-sync-traces.py player1.zip player2.zip
Reports evidence, not a proven cause. Does not upload or modify either ZIP.
"""
import argparse,json,struct,zipfile
from pathlib import Path

STATE_FIELDS=('ore','hydrogen','constructionTarget','pendingMode','buildingKind','placementFlag','modeBc28','cursorBcf4','cursorBd48X','cursorBd48Y','cursorBe00X','cursorBe00Y')
# Fields derived from the packet cursor: the local PC keeps its live cursor in idle
# frames while peers receive none, so they are only comparable on command frames.
CURSOR_FIELDS=('placementFlag','modeBc28','cursorBcf4','cursorBd48X','cursorBd48Y','cursorBe00X','cursorBe00Y')
# Local UI mirrors (0x51BC4C, 0x4FA62C): one value per PC, expected to differ.
LOCAL_FIELDS=('localUiMode','localBuildingKind')
def decode_hidden(raw):
 if len(raw)!=512:return None
 magic,version=struct.unpack_from('<2I',raw)
 if magic!=0x31545348 or version not in (1,2):return None
 h=dict(zip(('width','height','bytes','gridStatus','manager711a'),struct.unpack_from('<5I',raw,8)));h['version']=version
 h['players']={str(p+1):dict(zip(STATE_FIELDS,struct.unpack_from('<4i2H6i',raw,32+p*44))) for p in range(8)}
 if version==1:
  # 0.3.67 read 0x51BC28+p*4, i.e. player p+1's value (player 1 lives at offset 0).
  shifted={p:h['players'][str(p-1)]['modeBc28'] if p>1 else None for p in range(1,9)}
  for p in range(1,9):h['players'][str(p)]['modeBc28']=shifted[p]
 h['gridStripes']=list(struct.unpack_from('<16I',raw,384)) if h['gridStatus']==1 else None
 h['local']=dict(zip(LOCAL_FIELDS,struct.unpack_from('<2I',raw,448))) if version>=2 else None
 return h

def hidden_values(h):
 for k in ('width','height','bytes','gridStatus','manager711a'):yield k,h[k]
 for p,values in h['players'].items():
  for k,v in values.items():
   if v is not None:yield 'player'+p+'.'+k,v
 if h['gridStripes'] is not None:
  for i,v in enumerate(h['gridStripes']):yield 'gridStripe'+str(i),v

def command_players(packets):
 """Players whose slot carries a command this frame (byte0 or hotkey word24)."""
 result=set()
 for p in range(1,9):
  start=768+p*64
  if packets[start]!=0 or struct.unpack_from('<H',packets,start+24)[0]!=0:result.add(str(p))
 return result

def session_version(z,name):
 parts=name.split('/')
 if 'Diagnostics' not in parts:return None
 i=parts.index('Diagnostics')
 if i+1>=len(parts):return None
 events='/'.join(parts[:i+2])+'/events.jsonl'
 if events not in z.namelist():return None
 with z.open(events) as f:
  for line in f:
   try:e=json.loads(line.decode('utf-8-sig'))
   except ValueError:continue
   if e.get('kind')=='start':return (e.get('data') or {}).get('version')
 return None

def load(path):
 with zipfile.ZipFile(path) as z:
  choices=[]
  for name in z.namelist():
   if name.endswith('/sync-trace.json'):
    index=json.loads(z.read(name).decode('utf-8-sig'))
    if index.get('format')==1:choices.append((index.get('frozen',False),name,index))
  if not choices:raise ValueError('No sync-trace.json in '+str(path))
  _,name,index=max(choices,key=lambda x:(x[0],x[1]));raw=z.read(name[:-4]+'dat');frames={};index=dict(index);index['launcherVersion']=session_version(z,name)
  for row in index['stableFrames']:
   o=row['offset'];seq=row['sequence']
   if o<4096 or o+2048>len(raw):continue
   if struct.unpack_from('<I',raw,o)[0]!=seq or struct.unpack_from('<I',raw,o+76)[0]!=seq:continue
   if struct.unpack_from('<I',raw,o+88)[0]!=index['generation']:continue
   row=dict(row);row['hiddenState']=decode_hidden(raw[o+1536:o+2048])
   frames[row['clock']]=(row,raw[o+128:o+1536])
  return name,index,frames

def load_units(path,sync_name):
 with zipfile.ZipFile(path) as z:
  name=sync_name.replace('sync-trace.json','unit-trace.json')
  if name not in z.namelist():return {}
  index=json.loads(z.read(name).decode('utf-8-sig'));raw=z.read(name[:-4]+'dat');frames={}
  for row in index['frames']:
   o=row['offset'];seq=row['sequence'];count=row['count']
   if count>1700 or o<4096 or o+64+count*32>len(raw):continue
   if struct.unpack_from('<I',raw,o)[0]!=seq or struct.unpack_from('<I',raw,o+20)[0]!=seq or struct.unpack_from('<I',raw,o+8)[0]!=index['generation']:continue
   units={}
   for i in range(count):
    values=struct.unpack_from('<iHBBiiiiiBBBB',raw,o+64+i*32)
    if values[0]!=-1:units[values[0]]=dict(zip(('id','type','owner','active','x','y','health','target','timer','order','raw4d0','raw13b9','raw10'),values))
   frames[row['clock']]=units
  return frames

def position_history(path,record,unit,clock):
 # Position events live at the session root, including when sync records are frozen copies.
 parts=record.split('/');i=parts.index('Diagnostics') if 'Diagnostics' in parts else -1
 if i<0:return []
 name='/'.join(parts[:i+2])+'/position-trace.json'
 with zipfile.ZipFile(path) as z:
  if name not in z.namelist():return []
  if z.getinfo(name).file_size>16*1024*1024:raise ValueError('Oversize position trace')
  d=json.loads(z.read(name).decode('utf-8-sig'))
  if d.get('format')!=1:return []
  return sorted((r for r in d.get('records',[]) if r.get('unit')==unit and r.get('generation')==d.get('generation') and clock-2<=r.get('clock',-1)<=clock+2),key=lambda r:r['sequence'])

def compare(a,b):
 an,ai,af=load(a);bn,bi,bf=load(b);common=sorted(af.keys()&bf.keys());result={'left':an,'right':bn,'commonFrames':len(common),'range':[common[0],common[-1]] if common else [],'firstStateDifference':None,'firstOrderDifference':None,'firstRandomDifference':None,'firstPacketDifference':None,'note':'Matches simulation clocks from selected sessions; verify both reports describe the same match. Differences are indicators, not proof of cause. Local input staging is deliberately excluded from packet comparison. Idle cursor differences are expected; hidden-state differences are candidates, not automatically causal.'}
 result['hiddenStateCommonFrames']=0;result['firstHiddenStateDifferences']={};result['firstIdleCursorDifferences']={};result['idleCursorDifferenceFrames']=0;result['localUiSample']=None
 result['launcherVersions']={'left':ai.get('launcherVersion'),'right':bi.get('launcherVersion')}
 result['versionWarning']=None if ai.get('launcherVersion')==bi.get('launcherVersion') else '양측 런처 버전이 다릅니다 ('+str(ai.get('launcherVersion'))+' / '+str(bi.get('launcherVersion'))+'). 런타임 패치가 다를 수 있으므로 같은 버전 경기만 비교하세요.'
 result['hiddenStateVersions']=sorted({f[0]['hiddenState']['version'] for f in list(af.values())+list(bf.values()) if f[0].get('hiddenState')})
 for clock in common:
  x,xp=af[clock];y,yp=bf[clock]
  if x.get('hiddenState') and y.get('hiddenState'):
   result['hiddenStateCommonFrames']+=1
   xv=dict(hidden_values(x['hiddenState']));yv=dict(hidden_values(y['hiddenState']))
   active=command_players(xp)|command_players(yp)
   for key in sorted(xv.keys()&yv.keys()):
    if xv[key]==yv[key]:continue
    player,_,field=key.partition('.')
    if field in CURSOR_FIELDS and player[6:] not in active:
     result['idleCursorDifferenceFrames']+=1
     if key not in result['firstIdleCursorDifferences']:result['firstIdleCursorDifferences'][key]={'clock':clock,'left':xv[key],'right':yv[key]}
     continue
    if key not in result['firstHiddenStateDifferences']:result['firstHiddenStateDifferences'][key]={'clock':clock,'left':xv[key],'right':yv[key]}
   if x['hiddenState'].get('local') and y['hiddenState'].get('local') and result['localUiSample'] is None and x['hiddenState']['local']!=y['hiddenState']['local']:
    result['localUiSample']={'clock':clock,'left':x['hiddenState']['local'],'right':y['hiddenState']['local'],'note':'PC-local UI mirrors; differences are expected and not compared as candidates.'}
  if result['firstStateDifference'] is None and (x['unitHash']!=y['unitHash'] or x['unitCount']!=y['unitCount']):result['firstStateDifference']={'clock':clock,'leftHash':x['unitHash'],'rightHash':y['unitHash'],'players':[p for p in range(10) if x['playerHashes'][p]!=y['playerHashes'][p]]}
  if result['firstOrderDifference'] is None and 'orderHash' in x and 'orderHash' in y and x['orderHash']!=y['orderHash']:result['firstOrderDifference']={'clock':clock,'leftHash':x['orderHash'],'rightHash':y['orderHash'],'players':[p+1 for p in range(8) if x['playerOrderHashes'][p]!=y['playerOrderHashes'][p]]}
  if result['firstRandomDifference'] is None and any(x[k]!=y[k] for k in ('engineRngIndex','crtRng','fpuControl')):result['firstRandomDifference']={'clock':clock,'left':{k:x[k] for k in ('engineRngIndex','crtRng','fpuControl')},'right':{k:y[k] for k in ('engineRngIndex','crtRng','fpuControl')}}
  if result['firstPacketDifference'] is None:
   players=[]
   for p in range(1,9):
    start=768+p*64;one=xp[start:start+64];two=yp[start:start+64]
    if one!=two:players.append({'player':p,'differentBytes':[i for i in range(64) if one[i]!=two[i]]})
   if players:result['firstPacketDifference']={'clock':clock,'players':players}
 au=load_units(a,an);bu=load_units(b,bn);result['commonUnitFrames']=len(au.keys()&bu.keys());result['firstUnitDifference']=None
 for clock in sorted(au.keys()&bu.keys()):
  differences=[{'id':i,'left':au[clock].get(i),'right':bu[clock].get(i)} for i in sorted(au[clock].keys()|bu[clock].keys()) if au[clock].get(i)!=bu[clock].get(i)]
  if differences:result['firstUnitDifference']={'clock':clock,'count':len(differences),'units':differences[:16]};break
 result['firstEngineRandomDifference']=next(({'clock':c,'left':af[c][0]['engineRngIndex'],'right':bf[c][0]['engineRngIndex']} for c in common if af[c][0]['engineRngIndex']!=bf[c][0]['engineRngIndex']),None)
 result['unitTransitionHistory']=[]
 if result['firstUnitDifference']:
  first=result['firstUnitDifference'];ids=[v['id'] for v in first['units']]
  for clock in sorted(au.keys()&bu.keys()):
   if first['clock']-2<=clock<=first['clock']+2:
    result['unitTransitionHistory'].append({'clock':clock,'units':[{'id':i,'left':au[clock].get(i),'right':bu[clock].get(i)} for i in ids]})
 result['positionHistory']=[]
 if result['firstUnitDifference']:
  for unit in result['firstUnitDifference']['units']:
   result['positionHistory'].append({'unit':unit['id'],'left':position_history(a,an,unit['id'],result['firstUnitDifference']['clock']),'right':position_history(b,bn,unit['id'],result['firstUnitDifference']['clock'])})
 return result
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('left',type=Path);parser.add_argument('right',type=Path);args=parser.parse_args()
 try:print(json.dumps(compare(args.left,args.right),ensure_ascii=False,indent=2))
 except (ValueError,KeyError,zipfile.BadZipFile,OSError) as e:parser.exit(1,str(e)+'\n')
