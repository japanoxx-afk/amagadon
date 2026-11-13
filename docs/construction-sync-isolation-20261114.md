# Construction target isolation and offline regression

Original EXE SHA256: 34f0bf9ed99fbf3ab88c410a3a52a2f6904e7bc7f5b88fb4ebadc935c2e9b466.
Read directly with PE RVA translation and Capstone, not the HD disassembly.

The local input caller 407699 pushes command/player and CALLs 427530 at
40769B. Command 3C enters 427B75; 427BB0 writes packet word26 to
manager+2221C+player*4 before the local-player comparison. This changes shared
construction state before lockstep execution. Native 425299 compares a clicked
object to this field and branches to rejection at 425417 on mismatch.
The authoritative setter at 41F530 writes the same field during command execution.

Independent emulator states both start with target170. Only one state previews
new target171 through the actual native UI CALL. The old target170 comparison
then rejects on that state and accepts on the peer. This reproduces a possible
ordering defect, not a reconstruction of the unavailable paired November14 match.

The installed JMP at427BB0 skips only this write when multiplayer is nonzero AND
the native caller return address is4076A0. Other callers and singleplayer retain
the original write. pushfd/popfd preserves flags; no register or stack change.
UI mode/kind remain updated. The native lockstep setter is untouched.
This narrow guard avoids treating every use of427530 as necessarily UI-only.

Run from the repository with Python UTF-8 and the existing .tools dependencies:

    python scripts/build-selection-runtime.py
    python scripts/test-simulation-isolation.py
    python scripts/test-simulation-isolation.py dist/AmagadonLauncher.exe
    python scripts/test-selection-runtime.py dist/AmagadonLauncher.exe
    python scripts/test-selection-sync-isolation.py

The optional launcher argument extracts the actual compiled/rebased payload using
an x86 C# helper. The test verifies installed JMP bytes, original CALL/return,
arguments, stack, registers, flags, eight player indices, singleplayer, unknown
caller fallback and later synchronized setter. It requires the original local EXE
(AMAGADON_GAME_EXE can override the default); no game assets are distributed.

The native resource routine425090 and definition lookup40DDF0 execute across
160 combinations (8 players,5 balances,2 local identities,original/patched).
Both resources are unchanged on insufficient funds, otherwise exact debit occurs.
Only presentation leaves44E7E0 and471260/4712C0 are substituted. No construction
occupancy or full pathfinding result is asserted: target eligibility stops at the
real comparison branch before those checks. This is not a full game replay.

Remaining work: occupancy/pathfinding initialized-world execution, complete cursor
consumer audit, production and RNG interactions beyond existing AI/FPU tests.
manager+711A preview writes were observed but are NOT proven simulation defects.
Do not suppress those writes or claim all local UI differences are desync causes.

Single-command local suite after a build:

    powershell -File scripts/test-simulation-regressions.ps1 -Python <python.exe> -Launcher dist/AmagadonLauncher.exe

This invokes actual original-x86 execution against both pre-fix and installed code,
without requesting a new match or report. It fails if generated/compiled hook bytes
differ. Game/launcher/server processes are not started or terminated.
