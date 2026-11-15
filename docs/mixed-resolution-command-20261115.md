# Mixed-resolution command geometry (0.3.77)

## Evidence
Opponent report 2026-11-15 15:02 and matching local sessions contain two mixed 800x600 / 1024x768 matches. Both launchers were 0.3.76. First unit difference: frame 1317, P1 worker slot 81 (position); second: frame 2942, P2 worker slot 165 (idle vs moving). The preceding right-click commands at 1316 / 2941 were identical on both peers; their screen coordinates were (248,633) / (226,733). Hidden-state minimap classification was 0 on the 800 peer and 1 on the HD peer. Engine RNG did not differ. The later both-HD match's frozen window contains no unit/order/RNG differences; its three transient native comparison errors are not claimed to be explained by this fix.

## Native cause
0x4080A0 converts screen coordinates using local 0x4F9DD0..DC minimap bounds. 0x4203A0 and 0x408390 also classify against those bounds. The HD recipe translates them by (+112,+168). The right-command gate at 0x408401 rejects a non-viewport click unless classified as minimap. Hence identical received packets produce different acceptance and destinations with different HUD layouts.

## Fix
Multiplayer send call 0x483754 marks screen-X bit 15 for the supported 1024x768 layout before transmission. The existing 0x4851C0 encoder transports the complete X word, and 0x485280 masks it to ten coordinate bits when deriving world coordinates. Native mode uses bits 10..11 (0x48384A AND 3); the added bit does not alter it.

0x483837 captures the marker from each queued player command before native masking. At the installed 0x48BC9D CALL, the runtime saves the local minimap bounds, translates them to the sender layout, then enters the original 0x4080A0. This scope includes command preparation, right/orders, extended command batches and groups. The 0x48BD9F loop-exit detour restores the receiver bounds before UI/render processing. All register/flag state around the scope is preserved; original continuation instructions retain their flag effects. Singleplayer sending and geometry are unchanged. Idle/legacy packets default to native layout; all multiplayer participants must update together.

Allocation: code occupies checked unused offsets FC80/FD00/FD80/FE80 in the existing 64KiB executable page. Sender flags at +77500 (8 dwords), saved bounds +77540, active flag +77550. No executable allocation or packet length change.

## Validation scope
`test-command-layout.py` extracts the actual built runtime at relocated base 0x02340000, validates original hook bytes and executes installed CALL/JMP sites with the original codec and multiplayer flag extraction. Two incident coordinate cases reproduce the original acceptance disagreement; patched recipients agree. 112 paired combinations cover both sender layouts, eight slots, boundary and world-screen positions. A real ARO worker then runs through the installed right-command handler, native pathfinding and 120 native scheduler ticks; full unit/world state is compared. The headless fixture replaces OS allocation/render output, CRT TLS access and USER32 SetRect with documented seams; target resolution for an empty location is supplied explicitly. This is not a full DirectPlay network match or a reconstruction of every byte of the reported matches.

No reports, user identities, replay data or original assets are included in source control. Actual two-PC validation remains pending. Other desynchronization causes are not excluded.

## Completed checks (2026-11-15)
- Windows csc build, embedded relocated runtime, all seven package file hashes and ZIP checksum: PASS.
- New command-layout regression: 112 paired cases, 64 codec/flag combinations, singleplayer gate, exact loop-exit stack/register/flags (including DF), 120 real-worker scheduler ticks: PASS.
- Entire `test-simulation-regressions.ps1` suite (including real sprite, AI, construction, child production, collision, attack/projectile/death and EAD late-AI cases): PASS. These are offline fixtures, not full matches.
- Launcher `--self-test`: exit 0. `test-update.ps1`: PASS including current-version no-update, package integrity, locked-file rollback and restart handoff. `test-sync-trace-reports.py`: PASS.
- Existing input-recovery/replay/diagnostics standalone suites were not rerun for this patch; no full UI or two-PC match test was performed.
