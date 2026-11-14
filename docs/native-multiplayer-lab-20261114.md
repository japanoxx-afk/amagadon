# Native two-instance test — 2026-11-14

## Update: one native IPX match observed; full gameplay regression incomplete

After the user created/joined the room and clicked OK, both actual game processes
entered mode=4, multiplayer=1. The folder called `guest` was the session host
(player 1); the folder called `host` was player 2. DirectPlay session IDs and peer
IDs agreed. Both owned UDP sockets through the IPX wrapper. At least 5 minutes
27 seconds of multiplayer samples were observed, from approximately 13:04:25 to
13:09:52 KST, with continued simulation-clock progress on both sides.

An intermediate aggregate compared **9,164 distinct common stable frames** in
the range 13–9487 (the range has capture gaps). All compared unit and order
hashes matched; no engine RNG difference, native sync error, first-divergence,
crash or exit event was found. Six command-bearing player/frame pairs appeared
with identical 64-byte command packets on both peers (key24 values 2, 4, 6).
The unit count remained 164, including map objects. This was a low-activity
connection/input test, not a production or combat stress test.

The agent exercised idle-worker selection, stop/hold-style keyboard commands,
F2 with no military units, and foreground switching. Mouse movement commands
were attempted but no byte0 movement command was confirmed in captured frames.
Local cursor-derived hidden-state Y fields differed on some keyboard-command
frames; the raw candidates are retained, not suppressed. They produced no
observed unit/order divergence in this run. Individual unit-trace sampling did
not have common frames in the initial capture; hash comparisons must not be
described as exhaustive per-field equality.

Raw paired ZIPs and the aggregate `native-result.json` remain local under
`.tools/native-multiplayer-20261114`. `capture-native-pair.py` makes repeatable
sequential snapshots and uses the existing sequence/generation validation. It
refuses existing output directories. Its live capture and overwrite refusal,
`test-native-session-summary.py`, and `test-sync-trace-reports.py` passed.

No Lost connection/DRAW cause was reproduced, so no product logic was changed.
The 31-snapshot timed collector completed at 13:10:43 KST; including the initial
capture, 32 snapshots compared 10,740 distinct common frames (range 13–11063,
with gaps). No snapshot showed a unit/order/engine-RNG divergence. The final
aggregate is saved locally as `final-comparison-summary.json`.
Multiple completed matches, productive movement/build/combat workloads and two
physical PCs remain unverified. The games were left running; none was forcibly
closed. A single same-PC low-activity pass does not establish the reported issue
as fixed.

## Earlier setup attempt: match not yet started

The native game ran in two isolated copies on this Windows PC. The original
installation and the user's other processes were not changed. The candidate
launcher was built from commit `5b5649a`, still displaying 0.3.74, with SHA256
`ab26ef43a1d804b0c8ed5d20965a435e3d3023376608754d02ca8538ac3e714b`.

The game normally rejects the second instance using the `ArmageddonIsRunning`
mutex. The development adapter verifies that exact string at 0x4D4F4C in the
suspended child and replaces its name with a process-specific test name. It
then uses normal NetworkGuard hooks and Diagnostics.Watch. It does not alter
simulation, RNG, synchronization checks, thresholds, or DirectPlay packets.

The IPX local-profile screen was reached. This is NOT proof of peer connection.
Automated absolute mouse input did not agree with the game's DirectInput cursor;
displayed buttons could not be operated reliably. Windowed 800 and 1024,
fullscreen, confinement, and the existing mouse-compatibility option were tried.
Keyboard menu shortcuts and local-name entry worked. No lobby pair or gameplay
was established. The current menu-only records correctly return
`NO_MATCH_VERIFIED`; zero mismatch counters in a menu are not a passing match.
Manual assistance with native lobby navigation was requested. The automation
limitation is not established as the cause of users' Lost connection reports.

## Repeatable isolated setup

`scripts/start-native-multiplayer-lab.ps1` takes GameDirectory, BuildDirectory,
and a NEW LabDirectory. It copies only the explicit game assets/audio/maps into
host/guest folders and compiles `native-multiplayer-session.cs` as x86. Without
`-Launch` it only prepares the copies. With `-Launch` it starts two games and
separate diagnostic watchers. Use a local ignored `.tools` directory. Never
commit the copied EXE/MFP/HED, logs, accounts, or reports.

The helper refuses an unmarked installation and an existing session directory.
It isolates Core.Home and Diagnostics.Home; existing user settings and logs are
not overwritten. Helper consoles are hidden; native game windows are visible.
The helper itself is not part of the release package. Current test configuration
is windowed GDI with confinement and MouseCompatibility=false; this is a lab
configuration, not a product default change. Both processes currently use the
existing singlecpu setting; CPU contention must be considered in latency results.

## Required evidence before a successful native validation

1. Observe host creation and guest joining the SAME DirectPlay session.
2. Observe both entering a native multiplayer match and advancing clocks.
3. Record actual transport/session and send/receive evidence; a nonzero
   DirectPlay object pointer alone is insufficient.
4. Issue gameplay commands from both clients and include production/movement/
   combat. Collect paired same-match traces, including before termination.
5. Compare matching simulation clocks with compare-sync-traces.py. Preserve the
   first divergence and distinguish user exits, crashes, DRAW and connection loss.
6. Repeat matches. Report duration and actions, not just number of processes.

`summarize-native-session.py SESSION` returns exit 2 for menu-only, single-player
or non-advancing runs. An advancing multiplayer run still says
`REQUIRES_PAIRED_TRACE_COMPARISON`, never automatic PASS. It does not replace
trace comparison or prove that two sessions are the same match.

## Checks performed

- Windows x86 CSC compiled the adapter.
- PowerShell setup script syntax parsed successfully.
- Unmarked-installation refusal tested: exit 1, no session directory created.
- Summary regression checks reject menu, single-player and stalled sessions.
- Native host/guest processes launched and diagnostics were collected.
- At that stage actual DirectPlay gameplay had not started. See the update above
  for the subsequent native match. Repeated-match and combat regressions remain
  incomplete. No new product fix or release is claimed by this work.
