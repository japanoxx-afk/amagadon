"""Seeded native AI plan-entry sweep; NOT a completed tech-tree playthrough."""
import importlib.util,pathlib,json,time
s=importlib.util.spec_from_file_location('scheduler',pathlib.Path(__file__).with_name('test-native-scheduler.py'))
n=importlib.util.module_from_spec(s);s.loader.exec_module(n)

def main():
    started=time.perf_counter();results=[]
    for variant in range(3):
        a,b=n.RealPeer(1,800),n.RealPeer(2,1024)
        for p in (a,b):p.load_ai(variant)
        max_rows=max(x['rows'] for x in a.plan_metadata)
        changed=0;orders=0
        for stage in range(max_rows):
            for p in (a,b):
                for player in range(1,9):
                    race=(player-1)%3
                    rows=p.plan_metadata[race*3+variant]['rows']
                    p.w(0x7080000+player*0x100+28,min(stage,rows-1))
            for repetition in range(3):
                tick=stage*3+repetition+1
                a.scheduler_step(tick);b.scheduler_step(tick,(8,6))
                a.ai_step();b.ai_step();n.l.compare(a,b)
                assert bytes(a.u.mem_read(0x7080000,0x1000))==bytes(b.u.mem_read(0x7080000,0x1000))
                left=bytes(a.u.mem_read(0x504dd8,160))
                assert left==bytes(b.u.mem_read(0x504dd8,160))
                orders+=sum(left[player*16]!=0 for player in range(1,9))
                for player in range(1,9):
                    rows=a.plan_metadata[((player-1)%3)*3+variant]['rows']
                    changed+=a.r(0x7080000+player*0x100+28)!=min(stage,rows-1)
        results.append({'variant':variant,'seeded_indices':max_rows,'ticks':max_rows*3,'nonempty_orders':orders,'index_changes':changed})
    report={'cases':results,'seconds':time.perf_counter()-started,'natural_tech_progression':False,'prerequisites_seeded':False,'limitations':['plan index is explicitly seeded','later entries can reject missing prerequisites','not complete combat coverage']}
    (n.m.root/'.tools/ai-plan-stages-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS',json.dumps(report))
if __name__=='__main__':main()
