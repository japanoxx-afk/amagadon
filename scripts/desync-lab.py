"""Local repeatable regression runner. Never treats trace comparison as gameplay replay.

run: execute baseline/candidate argv without a shell in fresh per-run output folders.
compare: retain an offline desync evidence case from two report ZIPs.
All artifacts are private local files, not release assets.
"""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def comparator():
    spec = importlib.util.spec_from_file_location('sync_compare', ROOT/'scripts/compare-sync-traces.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare(left, right, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    result = comparator().compare(Path(left), Path(right))
    result['scope'] = 'recorded-evidence-only; no simulation executed'
    result['inputs'] = [{'path': str(Path(p).resolve()), 'sha256': digest(p)} for p in (left, right)]
    # An empty intersection is inconclusive, never a passing comparison.
    result['verdict'] = ('inconclusive' if not result['commonFrames'] or result['versionWarning'] or
                         not all(result['launcherVersions'].values()) else
                         'diverged' if result['firstStateDifference'] or result['firstOrderDifference'] else
                         'no-recorded-unit-or-order-divergence')
    write(output/'comparison.json', result)
    return result


def run(config, output):
    config = Path(config).resolve()
    c = json.loads(config.read_text(encoding='utf-8-sig'))
    repeat = c.get('repeat', 3)
    if not isinstance(repeat, int) or not 1 <= repeat <= 100:
        raise ValueError('repeat must be 1..100')
    cases = c['cases']
    if not cases or set(c['builds']) != {'baseline', 'candidate'}:
        raise ValueError('cases and baseline/candidate builds are required')
    for case in cases:
        if not case.get('argv') or not isinstance(case['argv'], list) or not all(isinstance(x, str) for x in case['argv']):
            raise ValueError('argv must be a nonempty string array')
        if case.get('timeout', 120) <= 0:
            raise ValueError('timeout must be positive')
    builds = {key: str(Path(value).resolve()) for key, value in c['builds'].items()}
    hashes = {key: digest(value) for key, value in builds.items()}
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'scope': c.get('scope', 'developer regression; not a two-PC match'),
              'configSha256': digest(config), 'buildHashes': hashes, 'runs': [], 'success': True}
    write(output/'config.json', c)
    try:
        # Sequential execution prevents a CPU-heavy test from distorting its peer's timing.
        for iteration in range(repeat):
            for case_id, case in enumerate(cases):
                for variant, build in builds.items():
                    folder = output/f'{iteration:03d}-{case_id:03d}-{variant}'
                    folder.mkdir()
                    values = {'build': build, 'python': sys.executable, 'root': str(ROOT), 'out': str(folder)}
                    argv = [arg.format_map(values) for arg in case['argv']]
                    row = {'iteration': iteration, 'case': case.get('name', str(case_id)),
                           'variant': variant, 'argv': argv, 'status': 'error'}
                    start = time.monotonic()
                    with (folder/'stdout.txt').open('wb') as stdout, (folder/'stderr.txt').open('wb') as stderr:
                        try:
                            p = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr,
                                               timeout=case.get('timeout', 120), shell=False)
                            row.update(exitCode=p.returncode, status='pass' if p.returncode == 0 else 'fail')
                        except subprocess.TimeoutExpired:
                            row['status'] = 'timeout'
                        except OSError as error:
                            row['error'] = str(error)
                    row['seconds'] = round(time.monotonic()-start, 3)
                    # Optional adapter output: a fresh pair of trace ZIPs from THIS run.
                    if case.get('tracePair') and row['status'] == 'pass':
                        try:
                            paths = [folder / name for name in case['tracePair']]
                            if len(paths) != 2 or any(not p.resolve().is_relative_to(folder) for p in paths):
                                raise ValueError('tracePair must contain two paths inside this run folder')
                            r = compare(*paths, folder/'comparison')
                            row['comparison'] = r['verdict']
                            row['firstStateDifference'] = r['firstStateDifference']
                            if r['verdict'] != 'no-recorded-unit-or-order-divergence':
                                row['status'] = 'fail'
                        except (OSError, ValueError, KeyError) as error:
                            row.update(status='error', error=str(error))
                    report['runs'].append(row)
                    if row['status'] != 'pass':
                        report['success'] = False
                    write(output/'results.json', report)
                    print(variant, row['case'], iteration+1, row['status'], flush=True)
        report['buildsUnchanged'] = all(digest(p) == hashes[k] for k, p in builds.items())
        report['success'] &= report['buildsUnchanged']
        report['caseAssessments'] = []
        for name in dict.fromkeys(row['case'] for row in report['runs']):
            outcomes = {v: [r['status'] for r in report['runs'] if r['case']==name and r['variant']==v]
                        for v in builds}
            stable = all(len(set(rows))==1 for rows in outcomes.values())
            a, b = (all(s=='pass' for s in outcomes[v]) for v in ('baseline', 'candidate'))
            verdict = ('unstable' if not stable else 'both-pass' if a and b else
                       'regression' if a else 'candidate-only-pass' if b else 'both-fail')
            report['caseAssessments'].append({'case': name, 'verdict': verdict, 'outcomes': outcomes})
    finally:
        write(output/'results.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('compare');p.add_argument('left');p.add_argument('right');p.add_argument('--out', required=True)
    p = sub.add_parser('run');p.add_argument('config');p.add_argument('--out', required=True)
    a = parser.parse_args()
    try:
        if a.command == 'compare':
            r = compare(a.left, a.right, a.out)
            print(r['verdict'], r['firstStateDifference'])
            return 0 if r['verdict'] == 'no-recorded-unit-or-order-divergence' else 1
        return 0 if run(a.config, a.out)['success'] else 1
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
