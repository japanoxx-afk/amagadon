"""Summarize a native test session; menu-only runs must never count as matches."""
import argparse
import json
from pathlib import Path


def summarize(folder):
    path = Path(folder) / 'home/Diagnostics/match/events.jsonl'
    events = []
    incomplete = 0
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            incomplete += 1
    matches = [e for e in events if e['kind'] == 'match-state'
               and e['data'].get('mode') == 4 and e['data'].get('multiplayer') == 1]
    networks = [e['data'] for e in events if e['kind'] == 'network-state']
    errors = [e for e in events if e['kind'] in
              ('first-sync-divergence', 'network-at-crash', 'match-at-crash')]
    clocks = [e['data']['simulationClock'] for e in matches]
    progressed = len(set(clocks)) > 1
    return {
        'session': str(Path(folder).resolve()),
        'nativeMultiplayerProgressObserved': progressed,
        'multiplayerSamples': len(matches),
        'clockRange': [min(clocks), max(clocks)] if clocks else [],
        'firstMatchSample': matches[0]['time'] if matches else None,
        'lastMatchSample': matches[-1]['time'] if matches else None,
        'maxNativeSyncErrors': max((e['data'].get('nativeSyncErrors') or 0
                                   for e in matches), default=0),
        'diagnosticFailures': errors,
        'lastNetworkState': networks[-1] if networks else None,
        'incompleteJsonLines': incomplete,
        'verdict': 'REQUIRES_PAIRED_TRACE_COMPARISON' if progressed else 'NO_MATCH_VERIFIED',
        'note': 'Clock progression alone does not prove peer communication or synchronized state. '
                'Compare both sessions from the same match using compare-sync-traces.py; '
                'record observed session join, traffic, commands and termination separately.'
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    args = parser.parse_args()
    result = summarize(args.session)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['nativeMultiplayerProgressObserved'] else 2)
