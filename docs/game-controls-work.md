# Extended selection implementation

The launcher installs SelectionRuntime in its own suspended game process. Both the audited original executable and current 1024x768 executable are supported; original files are not rewritten. Older replay formats can run without the selection extension.

- F2 selects owned, active military units; period selects owned idle workers using the original worker classifier and idle state. Chat, pause, dialogs and player input restrictions suppress these shortcuts.
- A per-player sidecar holds up to the engine pool limit of 1,700 IDs. Rectangle collection occurs before the original 16-item cap. The first 16 native HUD icons remain; all selected units receive selection rings and the HUD displays the full count. Control groups retain the complete list.
- Commands execute through the native right-click/explicit-order handlers in bounded 16-slot batches. Each batch receives the original command and packet. Native selection and packet buffers are restored, and the final native order completion state is retained. The command array is at 0x51bc50 + player*4 (not 0x51bc54 + player*4).
- F2/period use native packet key values 13/14. Rectangles use a tagged 12-bit selection payload and reconstruct the native rectangle selection at the simulation command boundary. The actual native DirectPlay writer/decoder preserve this marker. A separate application GUID prevents legacy selection clients joining these DirectPlay sessions.
- Replay archives preserve validated full selection/control-group state. Format 3 moves the command barrier after input processing and includes decoded click/order fields. Older archives retain their original barrier and validation; previously divergent recordings are not silently declared repaired.

Verification scripts:
- scripts/test-selection-runtime.py: installed original-code hooks, native worker classifier and rectangle selector, player isolation, input guards, control groups, native network codec round trips. Optional launcher path and allocation base test the actual compiled C# payload and relocations.
- scripts/test-selection-bridge.py: native ABI, bounds and command batches (handler observation seams).
- launcher --self-test: archive round trips, selection corruption/count/duplicate rejection, format binding.
- launcher --test-replay-process: real child-process event transport, recording/playback, divergence stop and cancellation.

The independent SelectionCommands.cs model is not used by the installed wire protocol. It must not be presented as live integration.
