# Deterministic arithmetic prevention (2026-11-04)

## Scope and evidence

This is a gameplay execution guard, not additional tracing and not a proven fix
for the 2026-11-03 match. Both recorded peers had x87 control word 0x027f;
their first unit-position difference still needs an explanation.

Supreme Commander developers describe enforcing precision/rounding and checking
it every tick because external APIs may change the floating-point environment:
https://gafferongames.com/post/floating_point_determinism/
We adopt the boundary-enforcement principle, **not** its 24-bit precision.
Armageddon's original EXE CRT at 0x4c669e and 0x4c66af explicitly compares against
0x027f; the paired runtime traces also show 0x027f (53-bit, nearest).
Those instructions were read directly from the original EXE using pefile/capstone.

## Implementation

At installed command entry 0x48bc82 and simulation barrier 0x45448c, in game mode
4, normalize only the x87 precision/rounding bits (mask 0x0f00) to 0x0200.
Preserve exception masks, status, live x87 values, CPU registers/flags and ESP.
No FINIT/FNCLEX, RNG reseeding, state overwrite, checksum bypass or error-limit
change. Runs with diagnostics OFF. Menus are untouched. Single-player and replay
use the same policy. Existing replay barrier CALL and +5 continuation stay intact.
The helper only issues FLDCW when correction is necessary.

This prevents a changed precision/rounding environment from carrying into these
boundaries. It does not guarantee restoration after arbitrary external calls
inside a tick, or address differences in pathfinding, UI state, or command data.
Both peers must use the same build. Existing recordings made with noncanonical
arithmetic may still diverge. No full-state resynchronization is attempted:
unit positions alone cannot restore hidden pathfinding/AI/occupancy state safely.

## Validation

- Windows build: dist/desync-prevention-dev.
- test-selection-runtime.py against compiled/relocated launcher payload: PASS.
  Includes 24 precision/rounding/mode cases via installed JMP/CALL/continuation,
  actual x87 conversion convergence, precision-sensitive arithmetic, live FPU
  value/status preservation, original registers/flags/stack and menus.
  Existing transport/HUD/AI (all 9 MFP variants) regression scenarios pass.
- test-sync-trace-reports.py: PASS.
- test-network-guard.py with freshly exported compiled NetworkGuard.Build: PASS;
  native disconnect threshold and flags/register preservation retained.
- test-replay.ps1 with explicit bundled Python: PASS (native fixture recording,
  playback, divergence fail-stop and cancellation). This is not a live match.
- Initial invocations omitted required Python/script arguments and failed;
  corrected invocations above passed without weakening tests.

No actual two-PC match or in-game performance measurement was performed.
No public release, no claim that the reported DRAW/disconnection is solved.
User game files and running processes were not modified/stopped.
