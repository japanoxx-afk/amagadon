"""Verify compiled runtime rally hooks against the original native exit scanner.

Usage: python scripts/test-rally-runtime.py [launcher.exe] [original Armageddon.exe]
Requires the local original test-game/Armageddon.exe, not an HD probe image.
"""
import hashlib, os, pathlib, struct, subprocess, sys, tempfile, textwrap
root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / '.tools'))
import pefile
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

launcher = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.tools/game-controls-build/AmagadonLauncher.exe').resolve()
original = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else root / 'test-game/Armageddon.exe'
assert hashlib.sha256(original.read_bytes()).hexdigest() == '34f0bf9ed99fbf3ab88c410a3a52a2f6904e7bc7f5b88fb4ebadc935c2e9b466'
pe = pefile.PE(str(original))
base = pe.OPTIONAL_HEADER.ImageBase
STACK, RETURN, CONTEXT = 0x400f000, 0x4001000, 0x3000000
ks = Ks(KS_ARCH_X86, KS_MODE_32)

def dword(u, a, v): u.mem_write(a, struct.pack('<I', v & 0xffffffff))
def read(u, a): return struct.unpack('<I', u.mem_read(a, 4))[0]
def run(u, start, stop, budget=1000000):
    u.emu_start(start, stop, count=budget)
    assert u.reg_read(UC_X86_REG_EIP) == stop, f'Instruction budget exhausted at {u.reg_read(UC_X86_REG_EIP):x}'

# Reflection loads the exact requested launcher, avoiding stale fixture DLLs.
fixture = r'''using System;using System.IO;using System.Reflection;using System.Collections.Generic;
class Dump {static void Main(string[] args){var a=Assembly.LoadFrom(args[0]);var t=a.GetType("Amagadon.RallySpawn",true);var edits=(Dictionary<int,byte[]>)t.GetMethod("Build").Invoke(null,new object[]{0x20000000});foreach(var e in edits)File.WriteAllBytes(Path.Combine(args[1],e.Key.ToString("x8")+".bin"),e.Value);}}'''
with tempfile.TemporaryDirectory(prefix='amagadon-rally-') as folder:
    folder = pathlib.Path(folder)
    source = folder / 'Dump.cs'; source.write_text(fixture)
    exe = folder / 'Dump.exe'
    compiler = pathlib.Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
    subprocess.run([str(compiler), '/nologo', '/platform:x86', '/out:' + str(exe), str(source)], check=True)
    subprocess.run([str(exe), str(launcher), str(folder)], check=True)
    edits = {int(p.stem, 16): p.read_bytes() for p in folder.glob('*.bin')}
assert set(edits) == {0x20000000, 0x44cf0a, 0x44cf5b}, 'Missing compiled hook payload'

def fresh():
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    u.mem_map(base, pe.OPTIONAL_HEADER.SizeOfImage)
    for section in pe.sections:
        u.mem_write(base + section.VirtualAddress, section.get_data())
    u.mem_map(0x3000000, 0x300000)
    u.mem_map(0x4000000, 0x100000)
    u.mem_map(0x20000000, 4096)
    u.reg_write(UC_X86_REG_ESP, STACK)
    for address, payload in edits.items(): u.mem_write(address, payload)
    return u

manager, parent = CONTEXT + 0x10000, CONTEXT + 0x14000
source = (root / 'scripts/verify-probe.py').read_text()
block = source[source.index('    for dx,dy,side,position in'):source.index('    assert (255-238)')]
checks = []
exec(compile(textwrap.dedent(block), __file__, 'exec'))
print('PASS: compiled 800x600 hooks; four rally directions, producer IDs, no-rally callers, actual output coordinates and blocked-side fallback')
