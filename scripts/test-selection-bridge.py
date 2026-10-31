"""Execute the batching prototype, with native dispatch replaced by an observer.

Verifies ABI, native array bounds and complete dispatch. Does NOT verify the
original movement/attack functions, their other globals, or live multiplayer.
"""
import importlib.util
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / '.tools'))
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
spec = importlib.util.spec_from_file_location('bridge', Path(__file__).with_name('build-selection-bridge.py'))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

STACK, RETURN = 0x400f000, 0x4001000
MANAGER, UNITS, IDS, PACKET = 0x3000000, 0x3100000, 0x3e00000, 0x3e01000

def dword(u, address, value): u.mem_write(address, struct.pack('<I', value & 0xffffffff))
def read(u, address): return struct.unpack('<I', u.mem_read(address, 4))[0]

def execute(player, count, handler, filtered=False, invalid=False):
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    for address, size in ((0x400000, 0x200000), (0x3000000, 0x1000000), (0x4000000, 0x100000), (bridge.BASE, 4096)):
        u.mem_map(address, size)
    u.mem_write(bridge.BASE, bridge.build())
    dword(u, 0x504a10, MANAGER)
    all_slots = bytes((i % 251 for i in range(9*64)))
    u.mem_write(MANAGER+0x7218, all_slots)
    old_packet = bytes(range(64))
    native_packet = 0x52f510+player*64
    u.mem_write(native_packet, old_packet)
    requested_packet = bytes(reversed(range(64)))
    u.mem_write(PACKET, requested_packet)
    dword(u, 0x51bc50+player*4, 0x1234)
    ids = list(range(min(count, 1700)))
    u.mem_write(IDS, struct.pack('<'+'H'*len(ids), *ids))
    expected = []
    for id in ids:
        unit = UNITS+id*0x1400
        dword(u, MANAGER+8+id*4, 0 if filtered and id % 7 == 0 else unit)
        alive = not(filtered and id % 5 == 0)
        owner = player if not(filtered and id % 3 == 0) else 0
        u.mem_write(unit+0x13b8, bytes([int(alive)]))
        u.mem_write(unit+0x3c, bytes([owner]))
        if alive and owner == player and not(filtered and id % 7 == 0): expected.append(id)
    observed = []
    def dispatch(emu, address, size, user):
        sp = emu.reg_read(UC_X86_REG_ESP)
        assert read(emu, sp+4) == player
        selected = struct.unpack('<16i', emu.mem_read(MANAGER+0x7218+player*64, 64))
        assert bytes(emu.mem_read(native_packet, 64)) == requested_packet
        assert read(emu, 0x51bc50+player*4) == 0x1234
        observed.extend(id for id in selected if id >= 0)
        # A native order handler may clear these; each subsequent batch must
        # receive the original order, and UI state must be restored afterward.
        emu.mem_write(native_packet, bytes([0xee])*64)
        dword(emu, 0x51bc50+player*4, 0)
    if not invalid:
        u.mem_write(handler, bytes.fromhex('b8efbeadde b911111111 ba22222222 c3'))
        u.hook_add(UC_HOOK_CODE, dispatch, begin=handler, end=handler)
    args = (RETURN, player, count, IDS, PACKET, handler)
    u.mem_write(STACK, struct.pack('<6I', *args))
    u.reg_write(UC_X86_REG_ESP, STACK)
    preserved = ((UC_X86_REG_EBP, 0x12345678), (UC_X86_REG_EBX, 0x23456789), (UC_X86_REG_ESI, 0x3456789a), (UC_X86_REG_EDI, 0x456789ab))
    for reg, value in preserved: u.reg_write(reg, value)
    u.emu_start(bridge.BASE, RETURN, count=500000)
    assert u.reg_read(UC_X86_REG_EIP) == RETURN
    assert u.reg_read(UC_X86_REG_ESP) == STACK+4
    for reg, value in preserved: assert u.reg_read(reg) == value
    assert bytes(u.mem_read(MANAGER+0x7218, len(all_slots))) == all_slots
    assert bytes(u.mem_read(native_packet, 64)) == old_packet
    assert read(u, 0x51bc50+player*4) == (0 if observed else 0x1234)
    assert bytes(u.mem_read(PACKET, 64)) == requested_packet
    if invalid:
        assert not observed and u.reg_read(UC_X86_REG_EAX) == 0xffffffff
    else:
        assert observed == expected, (len(observed), len(expected))
        assert u.reg_read(UC_X86_REG_EAX) == (len(expected)+15)//16

for player in (1,4,8):
    for count in (0,1,16,17,33,1700):
        for handler in (0x408390,0x420410):
            for filtered in (False,True): execute(player,count,handler,filtered)
execute(1,1,0x401000,invalid=True)
execute(1,1701,0x408390,invalid=True)
execute(0,1,0x408390,invalid=True)
execute(9,1,0x408390,invalid=True)
print('PASS: 72 x86 batching cases + 4 invalid inputs; all eligible IDs exactly once; player isolation; 16-slot bounds; packet/selection restoration and native final order state; cdecl registers/stack. Native order handlers are observer seams, not gameplay validation.')
