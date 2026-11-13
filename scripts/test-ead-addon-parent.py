"""Native EAD add-on parent availability; this is not a full tech progression test."""
import importlib.util,pathlib,struct
s=importlib.util.spec_from_file_location('battle',pathlib.Path(__file__).with_name('test-battle-flow.py'));b=importlib.util.module_from_spec(s);s.loader.exec_module(b)

def main():
 peers=[b.BattlePeer(3,800),b.BattlePeer(1,1024)]
 for p in peers:
  for i,kind in enumerate((0x205,0x206,0x206)):
   parent=p.unit(0x204,3,240+i*128,240);child=p.unit(kind,3,294+i*128,266)
   p.w(parent[1]+0xa5c,child[0]);p.w(child[1]+0xa5c,parent[0])
  assert p.call(0x452d30,(3,0x204),b.n.m.MANAGER,8)==0xffffffff
 b.n.l.compare(*peers)
 for p in peers:
  parent=p.unit(0x204,3,624,240)
  assert p.call(0x452d30,(3,0x204),b.n.m.MANAGER,8)==parent[0]
 b.n.l.compare(*peers)
 print('PASS native EAD add-on rejects three occupied parents; accepts fourth free parent on both peers')
if __name__=='__main__':main()
