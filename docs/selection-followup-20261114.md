# 2026-11-14 selection follow-up and 0.3.73

The user confirmed the local 0.3.72 session ending in process29944 is the reported
match; no opponent report is available. Native first comparison is clock2805,
sequence2793, reason1, fingerprints21 vs15. The observed counters reach61
fingerprint mismatches with zero missing histories. Exit code and first-chance
exception count are both zero. Thus the observed Lost connection follows a
simulation fingerprint failure; this does not establish the earliest differing
unit or instruction. It is not evidence that the network lost packets.

Two independent selection defects were reproduced on unmodified 0.3.72:
1. A multiplayer local rectangle leaves PENDING=1 although that input path never
   invokes the rectangle wire hook. A later invocation can transmit stale input.
2. A synchronized one-unit sidecar [5] survives an explicit native list [5,6,7]
   because the before hook compares only the old prefix, then sync overwrites
   native slots. The installed command-call probe consequently sees only [5].

Fixes:
- Multiplayer UI rectangles clear PENDING after native selection instead of
  enqueueing an untransmitted rectangle. Original 16-slot transmission remains.
- A received ordinary native selection list clears expanded counts at execution,
  before prefix/prune/sync. Explicit expanded markers and select-all handling
  retain their priority. This change is multiplayer-only.

Validation extends test-selection-sync-isolation.py: both PCs, earlier UI input,
three/20 units, marker-based execution, single-player preservation, later actual
wire-hook invocation, one-to-three replacement, 20-to16 replacement, and an
all-sentinel list. The latter retains the native first16 (original behavior),
while the stale expanded list is removed; verified against a native-only baseline.
The initial expectation that an all-sentinel packet deselects everything failed;
it was corrected by comparison with the original path, not by changing native
semantics. Python UTF-8 was also required during editing.

Generated runtime and installed/relocated compiled payload regressions passed,
including all nine original AI plan variants. Sync report tests and self-test
passed. Release uses the existing package and updater format.

These two bugs are established in emulator scenarios. Their contribution to this
particular match is NOT established without paired initial-divergence evidence.
Neither simulation checks nor thresholds/RNG were changed. No full match replay
or live two-PC test was performed. Multiplayer drag remains limited to16;
expanded army/idle hotkeys remain available. User reports are not committed.
