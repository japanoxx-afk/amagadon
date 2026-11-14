"""Archive one paired native diagnostic snapshot, then compare stable frames.

Use repeatedly during the SAME match; not a replacement for gameplay automation.
Local artifacts only. Sources are not altered and existing output is refused.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import zipfile

FILES = ('sync-trace.json', 'sync-trace.dat', 'unit-trace.json', 'unit-trace.dat',
         'events.jsonl', 'position-trace.json', 'sync-trace-status.json')


def capture(left, right, output):
    for session in (left, right):
        folder = session / 'home/Diagnostics/match'
        for name in FILES[:2]:
            if not (folder / name).is_file():
                raise ValueError('Missing trace: ' + str(folder / name))
    output.mkdir(parents=True, exist_ok=False)
    for label, session in (('left', left), ('right', right)):
        folder = session / 'home/Diagnostics/match'
        with zipfile.ZipFile(output / (label + '.zip'), 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in FILES:
                file = folder / name
                if file.is_file():
                    archive.writestr('Diagnostics/match/' + name, file.read_bytes())
    spec = importlib.util.spec_from_file_location('trace_compare', Path(__file__).with_name('compare-sync-traces.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The existing reader validates sequence/generation stamps against raw bytes.
    # Sequential snapshots are not simultaneous; only overlapping stable clocks count.
    result = module.compare(output / 'left.zip', output / 'right.zip')
    result['snapshotNote'] = 'Sequential snapshots; only stable overlapping frames are comparable. Verify same match manually.'
    (output / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('left', type=Path)
    parser.add_argument('right', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = capture(args.left, args.right, args.output)
    print(json.dumps({key: result[key] for key in ('commonFrames', 'range', 'firstStateDifference', 'firstOrderDifference', 'firstEngineRandomDifference', 'firstHiddenStateDifferences')}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['commonFrames'] else 2)
