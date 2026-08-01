#!/usr/bin/env python3
"""
Interactive OS/2 Kernel Debugger client using the KDB framework.

This provides a simple interactive interface with some convenience commands.

Usage:
    python3 kdb_interactive.py [--socket /tmp/dbgport] [--log /tmp/kdb.log]

Special commands (in addition to debugger commands):
    .help       - Show this help
    .regs       - Pretty-print registers
    .stack [n]  - Dump n DWORDs from stack (default 8)
    .modules    - List loaded modules
    .find <name> - Find module by name
    .bp <addr>  - Set breakpoint (hex address)
    .trace <n>  - Step n times with trace output
    .quit       - Exit

Debugger commands are passed through directly (r, d, u, p, g, etc.)
"""

import sys
import os
import argparse
try:
    import readline  # For command history (absent on native Windows Python)
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kdb import KDBSession


def print_help():
    print("""
Interactive KDB Commands:
    .help       - Show this help
    .regs       - Pretty-print current registers
    .stack [n]  - Dump n DWORDs from stack (default 8)
    .modules    - List all loaded modules
    .find <name> - Find module by name (partial match)
    .bp <addr>  - Set breakpoint at hex address
    .bpc <n>    - Clear breakpoint n (or 'all')
    .trace <n>  - Step n times with output
    .disasm [addr] [n] - Disassemble (default: current EIP, 10 instructions)
    .quit       - Exit

Standard debugger commands (passed through):
    r           - Show registers
    p           - Step over
    t           - Trace into
    g           - Continue execution
    bp %addr    - Set breakpoint
    bc n        - Clear breakpoint
    bl          - List breakpoints
    d %addr     - Dump memory
    u %addr     - Disassemble
    .lm         - List modules

Use 'break' to send Ctrl+C to stop execution.
""")


def main():
    parser = argparse.ArgumentParser(description='Interactive OS/2 Kernel Debugger client')
    parser.add_argument('--socket', '-s', default='/tmp/dbgport',
                        help='Path to debugger socket')
    parser.add_argument('--log', '-l', default='/tmp/kdb_session.log',
                        help='Log file path')
    parser.add_argument('--no-wait', action='store_true',
                        help="Don't wait for boot, assume already connected")
    args = parser.parse_args()

    print("OS/2 Kernel Debugger Interactive Client")
    print("=" * 40)
    print(f"Socket: {args.socket}")
    print(f"Log: {args.log}")
    print("Type .help for commands")
    print()

    session = KDBSession(args.socket, args.log)

    try:
        session.connect()
        print("Connected to debugger socket")

        if not args.no_wait:
            print("Waiting for OS/2 to boot (start the VM now)...")
            if not session.wait_for_boot(timeout=120.0):
                print("Boot timeout - continuing anyway")

        print("\nReady. Type commands or .help for help.\n")

        while True:
            try:
                cmd = input("kdb> ").strip()
            except EOFError:
                break

            if not cmd:
                continue

            # Handle special commands
            if cmd == '.quit' or cmd == '.exit':
                break

            elif cmd == '.help':
                print_help()

            elif cmd == '.regs':
                regs = session.get_registers()
                print(regs)

            elif cmd.startswith('.stack'):
                parts = cmd.split()
                count = int(parts[1]) if len(parts) > 1 else 8
                stack = session.dump_stack(count)
                for offset, value in stack:
                    print(f"  [ESP+{offset:02x}] = 0x{value:08x}")

            elif cmd == '.modules':
                modules = session.list_modules()
                for mod in modules[:50]:  # Limit output
                    print(f"  {mod.hmte:04x} {mod.name}")
                if len(modules) > 50:
                    print(f"  ... and {len(modules) - 50} more")

            elif cmd.startswith('.find '):
                name = cmd[6:].strip()
                mod = session.find_module(name)
                if mod:
                    print(f"  Found: hmte={mod.hmte:04x} mflags={mod.mflags:08x}")
                    print(f"         {mod.name}")
                else:
                    print(f"  Module '{name}' not found")

            elif cmd.startswith('.bp '):
                try:
                    addr = int(cmd[4:].strip(), 16)
                    bp = session.set_breakpoint(addr)
                    print(f"  Breakpoint {bp.number} set at 0x{addr:08x}")
                except ValueError:
                    print("  Invalid address (use hex)")

            elif cmd.startswith('.bpc '):
                arg = cmd[5:].strip()
                if arg == 'all':
                    session.clear_all_breakpoints()
                    print("  All breakpoints cleared")
                else:
                    try:
                        bp_num = int(arg)
                        session.clear_breakpoint(bp_num)
                        print(f"  Breakpoint {bp_num} cleared")
                    except ValueError:
                        print("  Invalid breakpoint number")

            elif cmd.startswith('.trace '):
                try:
                    count = int(cmd[7:].strip())
                    for i in range(count):
                        result = session.step()
                        instr = result.instruction
                        if instr:
                            print(f"  {i:3d}: {result.registers.eip:08x} "
                                  f"{instr.mnemonic} {instr.operands}")
                        else:
                            print(f"  {i:3d}: {result.registers.eip:08x}")
                except ValueError:
                    print("  Invalid count")

            elif cmd.startswith('.disasm'):
                parts = cmd.split()
                addr = None
                count = 10
                if len(parts) > 1:
                    try:
                        addr = int(parts[1], 16)
                    except ValueError:
                        pass
                if len(parts) > 2:
                    try:
                        count = int(parts[2])
                    except ValueError:
                        pass
                instructions = session.disassemble(addr, count)
                for instr in instructions:
                    print(f"  {instr}")

            elif cmd == 'break':
                print("  Sending break...")
                session.send_break()

            else:
                # Pass through to debugger
                response = session.command(cmd)
                print(response.raw)

    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()
        print(f"\nSession logged to {args.log}")


if __name__ == '__main__':
    main()
