# 2026-11-04 DRAW: UI-time selection leaked into execution (launcher hook)

Status: cause reproduced in x86 emulation against the original EXE and the installed
hooks; fix implemented and covered by a regression test. **Not yet verified in a
real two-PC match.** Do not describe it as a confirmed fix for live games until then.

## Evidence from the paired reports (P1 local 38324, P2 opponent 3232)

P2 packets (identical on both PCs):

| Clock | Packet | Meaning |
|---|---|---|
| 12415/12416 | press, release + list `[265,269,272]` | P2 selects three workers |
| 12456 | right-click, target 60 | all three reset counter on both PCs |
| 12461 | right-click, target 60, **no list** (byte10=0) | uses current synchronized selection |
| 12470/12471 | press, release + list `[265]` | P2 selects only 265 |

Unit counters after 12461 (`unit+0x478`): 265 resets on both PCs. 269/272 reset on
P1's PC (6→2), but continue on P2's own PC (6→7). So at the 12461 execution P2's PC
acted on `[265]` and P1's PC on `[265,269,272]`. Nothing in the trace shows a packet,
RNG or coordinate-setter difference before this.

The `[265]` selection executes at 12470/12471. P2 made that click on its own PC before
12461 executed. This fits a command delay of at least 10 ticks; the trace records
sequence = clock − 12, but the exact delay is not yet recorded directly.

## Mechanism (original code vs installed hook)

- Original local input `0x407010` → `0x40b010` → `0x40bb22 call 0x44dbd0` selects at
  UI time. In multiplayer (`0x407b04`) the original backs up `mgr+0x7218[local]` and
  loads the UI mirror `0x7498` (`0x407b13`). After the call, it copies the result to
  `0x7498` and restores the synchronized slot (`0x407c41`). The original therefore
  never changes synchronized selection at UI time. It changes only when the
  transmitted list executes (`0x48bbff`).
- The installed `rectangle` hook on `0x44dbd0` also rewrote the extended sidecar
  `COUNTS/LISTS[local]` at that UI-time call. The original swap does not restore the
  sidecar.
- The installed `before` hook (`0x48bc82`, every execution) compares the sidecar with
  the native slot. When the first entries match it calls `prune` → `sync`, and `sync`
  **overwrites `mgr+0x7218[p]`** from the sidecar. On P2's PC the sidecar was already
  `[265]` (first entry matching `[265,269,272]`), so the 12461 right-click acted on
  `[265]` only. On P1's PC the sidecar for P2 was empty, so the native 3-unit list was
  used.
- The same leak lets a >16 drag in multiplayer batch all N units on the commanding PC.
  Peers do not have that sidecar and use 16 units. The multiplayer drag path
  `0x407b13` has no `wire` hook, so the extended rectangle is never transmitted.

## Reproduction (`scripts/test-selection-sync-isolation.py`)

The test executes, against the original EXE:

- the original swap loops;
- the installed `0x44dbd0` hook with the original selector (only the sprite-bounds and
  SetRect leaves are substituted);
- the original execution `0x48bbaf..0x48bc97`, including the installed `0x48bc82`
  hook;
- the installed `0x48bd48` call site. The native right-click handler is replaced by a
  probe that records the selection it would act on.

It uses the recorded 12416 and 12461 packet bytes. The only differences between the
two runs are the local player number, the later UI click, and the selection size.

Before the fix:

| Case | Peer PC acts on | Commanding PC acts on |
|---|---|---|
| 3 units + later UI click | `[5,6,7]` | `[5]` (the observed pattern) |
| 20 units + later UI click | 16 units | 1 unit |
| 20 units, no UI change | 16 units | 20 units (2 batches) |

After the fix, both PCs act on identical units in every case.

## Fix (`scripts/build-selection-runtime.py`, `rectangle`)

When `0x44dbd0` is reached in multiplayer from local input (not the execution-time
call, which sets `SUPPRESS`), the hook no longer sets `TRACK`, resets `COUNTS`, runs
`filter`, `STAMP` or `sync`. The original selector still produces its native 16-slot
result, the local UI mirrors (`0x7498`, `0x1a98`) and the original transmitted list.
The rectangle is still offered to `PENDING` for the existing wire path.

Unchanged:
- execution-time extended rectangles (marker 4095/0xa31);
- select-all hotkeys and control groups, which are applied at execution;
- single player;
- sync checks, error counters and thresholds.

Visible consequence: in multiplayer, a mouse drag of more than 16 units now commands
16 units on every PC. Before the fix it commanded all N only on the dragging PC, which
desynchronizes the match. Extended army/idle hotkeys still select more than 16 at
execution.

## Still candidates / not done

- Transmitting >16 drags in multiplayer would need a `wire` hook on the `0x407b13`
  path (`0x407cac`). That is a protocol and gameplay change, so it needs its own
  two-PC test.
- A drag on the `0x407b13` path can leave `PENDING` set. The next `0x407823`-path input
  then transmits that old rectangle. This is deterministic on all PCs, so it is not a
  desync, but it may select unexpected units. Not changed here.
- The 2026-11-03 0.3.70 divergence (P1 unit 236) is not re-analysed; it may share
  this cause.

## Confirmation record for the next real match (if needed)

At the `before` hook entry and exit, per player with a command that frame, record:
- clock;
- `COUNTS[p]` and the first 16 `LISTS[p]`;
- `mgr+0x7218[p]` before and after the hook.

At each `rectangle` hook call, record:
- clock, local player, `0x513ed4`, `SUPPRESS`, and the resulting count.

This is about 150 bytes per command frame, read-only and outside simulation state. It
separates "sidecar changed at UI time" from any remaining native difference in a
single match.
