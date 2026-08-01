#!/usr/bin/env python3
"""
Trace DLL initialization order in real OS/2 using the kernel debugger.

This script:
1. Connects to the OS/2 kernel debugger
2. Finds PM DLLs and their entry points
3. Sets breakpoints on DLL init entry points
4. Records the order they are called

Usage:
    1. Start the OS/2 VM (debug kernel, serial port to /tmp/dbgport)
    2. Run: python3 kdb_trace_dll_init.py
    3. Let OS/2 boot - script will catch init calls

Output saved to /tmp/dll_init_order.log
"""

import sys
import os
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kdb import KDBSession

# DLLs we want to trace init order for
# Format: (name, entry_offset_from_lx_header)
# Entry offsets determined by LX inspection - relative to object base
TARGET_DLLS = [
    'PMMERGE',
    'PMCTLS',
    'PMGPI',
    'PMSPL',
    'SOM',
    'PMWIN',
    'PMSHAPI',
    'PMVIOP',
    'HELPMGR',
    'PMDRAG',
]

class DLLInitTracer:
    def __init__(self, socket_path='/tmp/dbgport', log_file='/tmp/dll_init_order.log'):
        self.session = KDBSession(socket_path, log_file)
        self.log_file = log_file
        self.log_handle = open(log_file, 'w')
        self.modules = {}  # name -> {hmte, base, entry}
        self.breakpoints = {}  # bp_num -> module_name
        self.init_order = []  # List of (timestamp, module_name)

    def log(self, msg):
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        line = f"[{timestamp}] {msg}"
        print(line)
        self.log_handle.write(line + '\n')
        self.log_handle.flush()

    def connect(self):
        self.log("Connecting to kernel debugger...")
        self.session.connect()
        self.log("Connected!")

    def wait_for_boot(self, timeout=120):
        self.log(f"Waiting for OS/2 to boot (timeout={timeout}s)...")
        result = self.session.wait_for_boot(timeout)
        if result:
            self.log("OS/2 booted successfully")
        else:
            self.log("Boot timeout - continuing anyway")
        return result

    def find_modules(self):
        """Find loaded modules and their info."""
        self.log("Querying loaded modules...")
        modules = self.session.list_modules()

        for mod in modules:
            name_upper = mod.name.upper()
            # Extract just the module name from path
            if '\\' in name_upper:
                name_upper = name_upper.split('\\')[-1]
            if '.' in name_upper:
                name_upper = name_upper.split('.')[0]

            for target in TARGET_DLLS:
                if target.upper() == name_upper:
                    self.modules[target] = {
                        'hmte': mod.hmte,
                        'pmte': mod.pmte,
                        'mflags': mod.mflags,
                        'full_name': mod.name
                    }
                    self.log(f"  Found {target}: hmte={mod.hmte:04x} pmte={mod.pmte:08x}")

        self.log(f"Found {len(self.modules)} target modules")
        return len(self.modules) > 0

    def get_module_objects(self, module_name):
        """Get object info for a module to find entry point."""
        if module_name not in self.modules:
            return None

        # Use .lmo command to get detailed module info
        # Unfortunately .lmo with a parameter doesn't work well
        # We'll need to parse the full .lm output or use alternative method

        # Try using ln (list nearest) on common entry patterns
        # Or we can dump the MTE structure

        pmte = self.modules[module_name]['pmte']
        self.log(f"  Getting objects for {module_name} (pmte={pmte:08x})...")

        # Dump MTE structure to find entry point
        # MTE structure has entry point info
        response = self.session.command(f'd %{pmte:08x} L8')
        self.log(f"  MTE dump: {response.raw.strip()[:100]}...")

        return None

    def find_entry_points(self):
        """Find entry point addresses for target DLLs."""
        self.log("Finding DLL entry points...")

        for name, info in self.modules.items():
            # Method 1: Try to find symbol
            response = self.session.command(f'ln {name.lower()}!_DLL_InitTerm')
            if 'no symbols' not in response.raw.lower():
                # Parse address from response
                match = re.search(r'%([0-9a-f]+)', response.raw, re.I)
                if match:
                    info['entry'] = int(match.group(1), 16)
                    self.log(f"  {name}: entry=0x{info['entry']:08x} (from symbol)")
                    continue

            # Method 2: Parse MTE to find entry point
            # The MTE has the entry point at a known offset
            pmte = info['pmte']

            # In OS/2, the SMTE (swappable MTE) has entry point info
            # Let's try reading the entry point from the module structure
            # Offset varies by OS/2 version, but let's try common ones

            # Read potential entry point locations
            response = self.session.command(f'dd %{pmte:08x}+10 L1')
            match = re.search(r'([0-9a-f]{8})\s+([0-9a-f]{8})', response.raw, re.I)
            if match:
                potential_entry = int(match.group(2), 16)
                if potential_entry > 0x10000 and potential_entry < 0x80000000:
                    info['entry'] = potential_entry
                    self.log(f"  {name}: potential entry=0x{potential_entry:08x}")

    def find_entry_via_disasm(self, module_name):
        """Try to find entry by looking at module's first object."""
        if module_name not in self.modules:
            return None

        # This is a heuristic - entry is often near start of code object
        info = self.modules[module_name]

        # Try to find by searching for the module in .lm and getting object info
        response = self.session.command('.lm')

        # Look for lines with this module
        for line in response.raw.split('\n'):
            if module_name.lower() in line.lower():
                self.log(f"  .lm line: {line.strip()}")

        return None

    def set_breakpoints_interactive(self):
        """Interactively set breakpoints - ask user for addresses."""
        self.log("\n=== Interactive Breakpoint Setup ===")
        self.log("Please find entry points using kernel debugger commands:")
        self.log("  .lm              - List all modules")
        self.log("  .lmo <name>      - Show module objects (may not work)")
        self.log("  ln <module>!*    - List symbols")
        self.log("")
        self.log("For each DLL, find the entry point (usually _DLL_InitTerm)")
        self.log("Then enter addresses below.")
        self.log("")

        # First, let's get module info by examining .lm output more carefully
        response = self.session.command('.lm')
        self.log("Current modules:")

        # Parse the .lm output to show relevant modules
        for line in response.raw.split('\n'):
            line_upper = line.upper()
            for target in TARGET_DLLS:
                if target in line_upper:
                    self.log(f"  {line.strip()}")

        return {}

    def set_entry_breakpoints(self):
        """Set breakpoints on DLL entry points."""
        self.log("Setting breakpoints on DLL entry points...")

        bp_count = 0
        for name, info in self.modules.items():
            if 'entry' in info and info['entry']:
                addr = info['entry']
                bp = self.session.set_breakpoint(addr)
                self.breakpoints[bp.number] = name
                self.log(f"  BP {bp.number}: {name} at 0x{addr:08x}")
                bp_count += 1

        self.log(f"Set {bp_count} breakpoints")
        return bp_count > 0

    def trace_init_order(self, max_hits=20, timeout=300):
        """Continue execution and record init order."""
        self.log(f"\nTracing init order (max_hits={max_hits}, timeout={timeout}s)...")
        self.log("Continue OS/2 boot or start PMSHELL now.\n")

        hits = 0
        while hits < max_hits:
            self.log("Continuing execution...")
            result = self.session.go(timeout=timeout)

            if result.hit_breakpoint is not None:
                bp_num = result.hit_breakpoint
                if bp_num in self.breakpoints:
                    module_name = self.breakpoints[bp_num]
                    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    self.init_order.append((timestamp, module_name))

                    self.log(f"*** HIT #{hits+1}: {module_name} init called ***")
                    self.log(f"    EIP=0x{result.registers.eip:08x}")

                    # Show stack to see caller
                    stack = self.session.dump_stack(4)
                    for offset, value in stack:
                        self.log(f"    [ESP+{offset:02x}] = 0x{value:08x}")

                    hits += 1
                else:
                    self.log(f"Hit unknown breakpoint {bp_num}")
            else:
                self.log("Stopped without breakpoint hit (timeout or break)")
                break

        return hits

    def print_results(self):
        """Print the recorded init order."""
        self.log("\n" + "=" * 60)
        self.log("DLL INITIALIZATION ORDER")
        self.log("=" * 60)

        if not self.init_order:
            self.log("No init calls recorded!")
        else:
            for i, (timestamp, name) in enumerate(self.init_order, 1):
                self.log(f"  {i:2d}. [{timestamp}] {name}")

        self.log("=" * 60)
        self.log(f"Results saved to {self.log_file}")

    def close(self):
        self.session.close()
        self.log_handle.close()


def manual_mode(tracer):
    """Manual mode - user provides addresses."""
    print("\n=== MANUAL MODE ===")
    print("Enter DLL entry point addresses (hex, or 'skip' to skip, 'done' when finished)")
    print("")

    addresses = {}
    for name in TARGET_DLLS:
        while True:
            response = input(f"  {name} entry address (hex): ").strip().lower()
            if response == 'skip':
                break
            if response == 'done':
                return addresses
            try:
                addr = int(response.replace('0x', ''), 16)
                addresses[name] = addr
                break
            except ValueError:
                print("    Invalid hex address, try again")

    return addresses


def auto_find_entries(tracer):
    """Try to automatically find entry points."""
    tracer.log("\n=== AUTO-FINDING ENTRY POINTS ===")

    # For each module, try various methods to find entry
    for name in TARGET_DLLS:
        if name not in tracer.modules:
            continue

        info = tracer.modules[name]
        tracer.log(f"\nSearching for {name} entry point...")

        # Method 1: Symbol lookup
        for sym in ['_DLL_InitTerm', '_LibMain', 'LIBMAIN', '_init']:
            response = tracer.session.command(f'ln {name.lower()}!{sym}')
            if '%' in response.raw and 'error' not in response.raw.lower():
                match = re.search(r'%([0-9a-f]+)', response.raw, re.I)
                if match:
                    addr = int(match.group(1), 16)
                    info['entry'] = addr
                    tracer.log(f"  Found via symbol {sym}: 0x{addr:08x}")
                    break

        # Method 2: If we have symbols loaded, try broader search
        if 'entry' not in info:
            response = tracer.session.command(f'x {name.lower()}!*init*')
            tracer.log(f"  Symbol search: {response.raw[:200]}...")


def main():
    print("=" * 60)
    print("OS/2 DLL Initialization Order Tracer")
    print("=" * 60)
    print("")
    print("This script traces the order OS/2 calls DLL init functions.")
    print("Requires: OS/2 debug kernel with serial debugger at /tmp/dbgport")
    print("")

    tracer = DLLInitTracer()

    try:
        tracer.connect()
        tracer.wait_for_boot()

        # Break into debugger
        tracer.log("\nBreaking into debugger...")
        tracer.session.send_break()

        # Find modules
        if not tracer.find_modules():
            tracer.log("WARNING: No target modules found yet.")
            tracer.log("PM may not have started. Will set breakpoints anyway.")

        # Try to find entry points automatically
        auto_find_entries(tracer)

        # Check what we found
        found_entries = sum(1 for info in tracer.modules.values() if 'entry' in info)
        tracer.log(f"\nFound {found_entries} entry points automatically")

        if found_entries == 0:
            tracer.log("\nCould not find entry points automatically.")
            tracer.log("Entering manual mode - please provide addresses.")
            tracer.log("")
            tracer.log("HINT: In the kernel debugger, try:")
            tracer.log("  .lm                    - List modules")
            tracer.log("  dd <pmte>+10 L4        - Dump MTE entry area")
            tracer.log("  u <module_base>        - Disassemble module start")
            tracer.log("")

            # Enter interactive mode
            print("\nStarting interactive session. Type 'quit' when ready to set breakpoints.")
            print("Use kernel debugger to find entry points, then use manual mode.\n")

            while True:
                try:
                    cmd = input("kdb> ").strip()
                    if cmd.lower() == 'quit':
                        break
                    if cmd.lower() == 'manual':
                        addresses = manual_mode(tracer)
                        for name, addr in addresses.items():
                            if name in tracer.modules:
                                tracer.modules[name]['entry'] = addr
                        break
                    if cmd:
                        response = tracer.session.command(cmd)
                        print(response.raw)
                except EOFError:
                    break

        # Set breakpoints
        if tracer.set_entry_breakpoints():
            # Trace init order
            tracer.trace_init_order()
        else:
            tracer.log("No breakpoints set - cannot trace")

        # Print results
        tracer.print_results()

    except KeyboardInterrupt:
        tracer.log("\nInterrupted by user")
    except Exception as e:
        tracer.log(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        tracer.close()


if __name__ == '__main__':
    main()
