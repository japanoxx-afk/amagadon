"""Regression for the reported test-map gap, using isolated ACE map-object dumps.
Usage: verify-ramp-gap.py BEFORE_OBJECT AFTER_OBJECT
Dumps come from native 0x427010 terrain export, stopped before unit processing.
This tests the saved map's blocked bit, not merely the connection record ID.
"""
from pathlib import Path
from collections import deque
import struct,sys
before,after=[Path(p).read_bytes() for p in sys.argv[1:3]]
plane=2
for data in (before,after):assert len(data)==0x9d0000
base=0x1e2712+plane*136*264
assert before[base:base+128*264]==after[base:base+128*264], 'base hill shape changed'
def connected(data,start,end):
 def blocked(x,y):return struct.unpack_from('<H',data,0x11b6+((x+plane*272)*264+y)*2)[0]&4
 assert not blocked(*start) and not blocked(*end)
 seen={start};pending=deque([start])
 while pending:
  x,y=pending.popleft()
  for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
   n=(x+dx,y+dy)
   if 18<=n[0]<=27 and 5<=n[1]<=13 and n not in seen and not blocked(*n):seen.add(n);pending.append(n)
 return end in seen
for a,b in [((20,6),(25,12)),((25,12),(20,6))]:
 assert not connected(before,a,b),'fixture no longer reproduces blocked ramp'
 assert connected(after,a,b),'ramp must join the upper and lower terrain'
print('PASS: reported map gap reproduced; exported movement cells connected both ways after fix; base hill unchanged')
