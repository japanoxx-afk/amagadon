"""The native lab must not report a menu-only run as multiplayer verification."""
import importlib.util
import json
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('summary', Path(__file__).with_name('summarize-native-session.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    events = root / 'home/Diagnostics/match/events.jsonl'
    events.parent.mkdir(parents=True)
    def write(mode, multiplayer, clocks):
        records = [{'time': str(i), 'kind': 'match-state', 'data': {
            'mode': mode, 'multiplayer': multiplayer, 'simulationClock': clock,
            'nativeSyncErrors': 0}} for i, clock in enumerate(clocks)]
        events.write_text('\n'.join(map(json.dumps, records)), encoding='utf-8')
    for mode, multiplayer, clocks in [(2, 0, [1, 100]), (4, 0, [1, 100]), (4, 1, [1, 1])]:
        write(mode, multiplayer, clocks)
        assert module.summarize(root)['verdict'] == 'NO_MATCH_VERIFIED'
    write(4, 1, [1, 100])
    assert module.summarize(root)['verdict'] == 'REQUIRES_PAIRED_TRACE_COMPARISON'
print('PASS: menu, single-player and stalled sessions are not multiplayer passes; advancing sessions still require paired evidence')
