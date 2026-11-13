"""Isolated special-weapon branches: seeded loadout and gauges, native command.
This does not claim natural acquisition/casting of every special ability.
"""
import importlib.util,pathlib,json
s=importlib.util.spec_from_file_location('attack',pathlib.Path(__file__).with_name('test-attack-command-flow.py'));a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
def main():
 results=[];failures=[]
 for weapon,target in ((5,0x223),(9,0x1b),(16,0x223),(29,0x223),(30,0x223),(33,0x223),(34,0x223),(35,0x223),(38,0x1b),(39,0x1b),(47,0x223),(49,0x1b),(65,0x223)):
  try:
   r=a.case(0x223,target,weapon,target_hp=20 if weapon==65 else None);results.append(r);print('PASS SPECIAL',r,flush=True)
  except Exception as e:failures.append({'weapon':weapon,'error':repr(e)});print('FAIL SPECIAL',failures[-1],flush=True)
 report={'seeded_weapon_state':True,'source_gauges':{'0x9cc':10000,'0x9d4':10000},'cases':results,'failures':failures,'full_match':False,'limitations':['special ability acquisition not tested','weapon visual resources omitted','weapon 53 healing tested with its real unit in attack-command-flow']}
 (a.b.n.m.root/'.tools/special-attack-branches-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 assert not failures,failures
if __name__=='__main__':main()
