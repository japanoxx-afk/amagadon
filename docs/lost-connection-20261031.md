# 2026-10-31 Lost connection investigation

Session: Diagnostics/20261031-151206-531-47520. User reports simultaneous failure on both clients during normal gameplay.

At 15:26:39 the native game entered dialog 14 with result 0. Crazy Zone remained connected; both clients answered server heartbeat opcode 89 at 15:26:39. The game process subsequently exited with code 0. This does not establish a lobby transport failure or an exception crash. Remote client diagnostics were not available.

Native lockstep paths 0x483b4a (unequal nonzero fingerprints) and 0x483baa (sequence absent from 50-entry peer history) share error byte 0x51a8e4 and disconnect threshold 60. Existing logs did not capture which condition caused this session's failure. Do not label either condition the proven cause, increase timeout blindly, or bypass desync validation.

Added process-only instrumentation preserving displaced comparisons, all registers and flags. Diagnostic network-state/network-at-transition entries now include separate mismatch/missing-history totals, last reason (1=mismatch, 2=missing history), peer, history index, simulation clock, native error count, local player and sequence. Fingerprints are meaningful only for reason 1. Counters are process lifetime; timestamps and match transitions delimit rounds. Sampling may coalesce events; this is not a packet trace. Reports already bundle these events.

Corrected MatchState.localPlayer from an unrelated dword to the native byte at 0x4e7270. Error-counter changes trigger transition sampling every 250 ms, in addition to five-second snapshots.

Validation: x86 emulation compares patched/unpatched registers, stack and flags at errors 0/59/60/61/70 on both paths. Existing provider failure regression tests retained. Suspended-process fixture validates installation and telemetry without modifying the game EXE. No two-PC reproduction or disconnect-prevention fix has been verified. The diagnostic build is separate from the published 0.3.47 release.
