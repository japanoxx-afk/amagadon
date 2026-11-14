# Mixed resolution validation — 2026-11-14

Question: can 800x600 versus 1024x768 cause native multiplayer state divergence?
Candidate launcher SHA256: ab26ef43a1d804b0c8ed5d20965a435e3d3023376608754d02ca8538ac3e714b.

The earlier native IPX run used 1024x768 on BOTH clients. Its 10,740 matching
frames do not answer the mixed-resolution question.

## Test coverage correction

`test-path-production.py:fresh` previously set displayWidth but left displayHeight
at the PE's initial value. It now sets both axes (800x600 / 1024x768). Lifecycle
and native-scheduler tests inherit this setup. This changes the test harness,
not game behavior. The peers also use different local-player IDs and local
cursor/camera values. The test's original-PE image with runtime hooks is not a
complete HD-patched Windows process and must not be represented as one.

After the height correction, path/production passed 560 paired path cases,
60 spawn cases, 420 timer pairs, 8 completion pairs and 10 allocation pairs.
These are native x86 emulation results; they do not exercise DirectPlay or the
Windows message loop. The corrected-height native-scheduler rerun also passed
9 unit types x 600 paired ticks and 3 AI variants x 600 paired ticks. Native
unit processing order, creation events and simulated state matched. Deliberately
reversing one peer's unit order still produced a difference (positive control).
This uses real ARO definitions with synthetic sprite metadata and flat terrain;
it is not a Windows/DirectPlay match or exhaustive combat validation.

Static comparison of original and generated HD files found identical bytes in
0x4851C0–0x4854FF (network encode/decode region), 0x471790–0x47180F
(pathfinder entry), and 0x447B00–0x447B9F (scheduler entry). This is a bounded
comparison, NOT proof that every simulation path or runtime patch is identical.
RallySpawn.Apply explicitly installs the spawn/gather hooks on the original EXE;
the HD recipe already contains them. SelectionRuntime is installed on both.

## Native mixed pair

The previous processes had exited before setup. New isolated processes were
launched from the existing lab copies, with new `mixed-host` / `mixed-guest`
diagnostic directories. Their recorded dimensions are respectively 800x600 and
1024x768. The first runs original Armageddon.exe with launcher runtime hooks;
the second runs Armageddon.HD-preview.exe. They use the same candidate launcher.

`start-native-multiplayer-lab.ps1` now accepts separate Width and GuestWidth
values and records the width for each side in the manifest. Existing sessions
are not overwritten. Original user installation remains untouched.

Native session join/start requires user assistance because the available UI
automation sends absolute mouse coordinates that this game's relative input
does not handle reliably. Until both processes reach mode=4, multiplayer=1,
the mixed-resolution real-match result is **PENDING**, not PASS. No product fix,
release, or claim that resolution is excluded as a cause is made.

For the actual match, collect matching clocks using capture-native-pair.py,
especially commands issued in the HD-only region beyond x=799 or y=599,
camera scrolling, drag selection, construction and rally production. Repeat
with host/guest roles swapped. Rendering dimensions alone are not sufficient
to rule out command-coordinate or local-state leakage.
