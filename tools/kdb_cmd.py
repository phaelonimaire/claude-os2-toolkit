#!/usr/bin/env python3
"""
Send command to OS/2 kernel debugger, print output, exit on ## prompt.
Also supports VM control via VBoxManage.

Usage:
  kdb_cmd.py "command" [command2] ...   - send debugger commands
  kdb_cmd.py --stop-vm                  - power off the VM
  kdb_cmd.py --restart-vm               - restart VM and wait for debugger
"""

import socket
import select
import subprocess
import sys
import os
import time
import argparse

# Debug target: a Unix socket path (VBox --uartmode1 server <path>) or a
# host:port TCP endpoint (VBox --uartmode1 tcpserver <port> — required on
# Windows hosts, where VBox host pipes are named pipes Python can't open).
DEFAULT_TARGET = os.environ.get('KDB_DBGPORT', '/tmp/dbgport')
CHAR_DELAY = 0.005  # 5ms between characters
DEFAULT_VM_NAME = "os2kdb"


def parse_target(target):
    """Split a target spec into ('tcp', (host, port)) or ('unix', path).

    A spec with no path separators whose final ':'-field is numeric is
    host:port (e.g. 'localhost:5555', ':5555' = localhost); anything else
    is a Unix socket path.
    """
    if '/' not in target and '\\' not in target:
        host, sep, port = target.rpartition(':')
        if sep and port.isdigit():
            return 'tcp', (host or '127.0.0.1', int(port))
    return 'unix', target


def connect_target(target):
    """Open a connected, non-blocking socket to a Unix path or host:port."""
    kind, addr = parse_target(target)
    if kind == 'tcp':
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Preserve per-character pacing on the wire
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.connect(addr)
    else:
        if not hasattr(socket, 'AF_UNIX'):
            raise OSError(
                "Unix sockets are unavailable on this platform. Configure the "
                "VM serial port in TCP mode (VBoxManage modifyvm <vm> "
                "--uartmode1 tcpserver <port>) and use --socket localhost:<port>")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(addr)
    sock.setblocking(False)
    return sock


def get_vm_name(args):
    """Get VM name from args, env var, or default."""
    if args.vm_name:
        return args.vm_name
    return os.environ.get('KDB_VM_NAME', DEFAULT_VM_NAME)


def vm_stop(vm_name):
    """Power off the VM."""
    print(f"Stopping VM '{vm_name}'...", file=sys.stderr)
    result = subprocess.run(
        ['VBoxManage', 'controlvm', vm_name, 'poweroff'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        # Check if it's already off
        if 'not currently running' in result.stderr or 'is not running' in result.stderr:
            print(f"VM '{vm_name}' is not running.", file=sys.stderr)
            return True
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        return False
    print(f"VM '{vm_name}' stopped.", file=sys.stderr)
    return True


def vm_start(vm_name, headless=False):
    """Start the VM."""
    print(f"Starting VM '{vm_name}'...", file=sys.stderr)
    cmd = ['VBoxManage', 'startvm', vm_name]
    if headless:
        cmd.extend(['--type', 'headless'])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if 'already running' in result.stderr:
            print(f"VM '{vm_name}' is already running.", file=sys.stderr)
            return True
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        return False
    print(f"VM '{vm_name}' started.", file=sys.stderr)
    return True


def wait_for_socket(target, timeout=60):
    """Wait for the debug target to become connectable."""
    print(f"Waiting for debug target {target}...", file=sys.stderr)
    kind, addr = parse_target(target)
    start = time.time()
    while time.time() - start < timeout:
        if kind == 'unix':
            if os.path.exists(addr):
                return True
        else:
            try:
                connect_target(target).close()
                return True
            except OSError:
                pass
        time.sleep(0.5)
    print(f"ERROR: Debug target not available within {timeout}s", file=sys.stderr)
    return False


def wait_for_prompt(target, timeout=120):
    """Connect to the debug target and wait for ## prompt (boot complete)."""
    print("Waiting for debugger prompt...", file=sys.stderr)

    try:
        sock = connect_target(target)
    except Exception as e:
        print(f"ERROR: Cannot connect to {target}: {e}", file=sys.stderr)
        return False

    # Just connecting signals the debugger we're here
    # Send a newline to acknowledge early boot prompt
    sock.send(b'\r\n')
    time.sleep(CHAR_DELAY)

    buffer = b''
    last_data_time = time.time()
    start = time.time()

    while time.time() - start < timeout:
        ready, _, _ = select.select([sock], [], [], 0.5)
        if ready:
            try:
                chunk = sock.recv(4096)
                if chunk:
                    last_data_time = time.time()
                    text = chunk.decode('latin-1', errors='replace')
                    # Don't spam output with repeated > characters
                    if chunk != b'>' and chunk != b'>\r\n':
                        print(text, end='', flush=True)
                    buffer += chunk
                    # Keep buffer from growing too large
                    if len(buffer) > 8192:
                        buffer = buffer[-4096:]
                    if b'##' in buffer or b'**' in buffer:
                        sock.close()
                        print(file=sys.stderr)
                        print("Debugger ready.", file=sys.stderr)
                        return True
            except BlockingIOError:
                pass
        else:
            # No data for a while, try Ctrl+C to break in
            if time.time() - last_data_time > 5:
                sock.send(b'\x03')
                last_data_time = time.time()

    sock.close()
    print(f"\nERROR: Debugger prompt not seen within {timeout}s", file=sys.stderr)
    return False


def send_commands(target, commands):
    """Send commands to debugger and print output."""
    kind, addr = parse_target(target)
    if kind == 'unix' and not os.path.exists(addr):
        print(f"ERROR: Socket {addr} not found (is the VM running?)", file=sys.stderr)
        return False

    try:
        sock = connect_target(target)
    except OSError as e:
        print(f"ERROR: Cannot connect to {target}: {e}", file=sys.stderr)
        return False

    # Send each command
    for cmd in commands:
        # Send character by character with delay
        for ch in cmd:
            sock.send(ch.encode())
            time.sleep(CHAR_DELAY)
        # Send CR+LF
        sock.send(b'\r')
        time.sleep(CHAR_DELAY)
        sock.send(b'\n')
        time.sleep(CHAR_DELAY)

    # Read and print until we see the ## prompt. Bounded: a debugger that never
    # prompts (wrong port, VM not halted, kernel not a debug kernel) would
    # otherwise hang forever with no output and no error. The deadline resets on
    # every byte received, so a legitimately slow dump is not cut short.
    timeout = float(os.environ.get('KDB_READ_TIMEOUT', '30'))
    buffer = b''
    deadline = time.monotonic() + timeout
    while True:
        if time.monotonic() >= deadline:
            print(f"\nkdb_cmd: no debugger prompt for {timeout:g}s - giving up "
                  f"(raise KDB_READ_TIMEOUT to wait longer)", file=sys.stderr)
            sock.close()
            return False
        ready, _, _ = select.select([sock], [], [], 0.1)
        if ready:
            try:
                chunk = sock.recv(4096)
                if chunk:
                    deadline = time.monotonic() + timeout   # progress: extend
                    text = chunk.decode('latin-1', errors='replace')
                    print(text, end='', flush=True)
                    buffer += chunk
                    # Check for final prompt
                    if b'##' in buffer or b'**' in buffer:
                        break
                    # Handle --More-- prompt by sending CR to continue
                    if b'--More--' in buffer:
                        sock.send(b'\r')
                        time.sleep(CHAR_DELAY)
                        buffer = b''
            except BlockingIOError:
                pass

    sock.close()
    print()
    return True


def main():
    parser = argparse.ArgumentParser(
        description='OS/2 Kernel Debugger command tool with VM control'
    )
    parser.add_argument('commands', nargs='*', help='Debugger commands to send')
    parser.add_argument('--stop-vm', action='store_true', help='Power off the VM')
    parser.add_argument('--restart-vm', action='store_true', help='Restart VM and wait for debugger')
    parser.add_argument('--start-vm', action='store_true', help='Start VM and wait for debugger')
    parser.add_argument('--vm-name', help=f'VM name (default: {DEFAULT_VM_NAME}, or KDB_VM_NAME env)')
    parser.add_argument('--socket', metavar='TARGET',
                        help='Debug target: Unix socket path or host:port '
                             f'(default: {DEFAULT_TARGET}, or KDB_DBGPORT env)')
    parser.add_argument('--no-wait', action='store_true', help='Do not wait for debugger after start')
    parser.add_argument('--headless', action='store_true', help='Start VM in headless mode')
    parser.add_argument('--timeout', type=int, default=120, help='Timeout for waiting for debugger (default: 120s)')

    args = parser.parse_args()
    vm_name = get_vm_name(args)
    target = args.socket or DEFAULT_TARGET

    # Handle VM control
    if args.stop_vm:
        sys.exit(0 if vm_stop(vm_name) else 1)

    if args.restart_vm:
        if not vm_stop(vm_name):
            sys.exit(1)
        time.sleep(2)  # Give VBox time to clean up
        if not vm_start(vm_name, headless=args.headless):
            sys.exit(1)
        if not args.no_wait:
            if not wait_for_socket(target):
                sys.exit(1)
            if not wait_for_prompt(target, args.timeout):
                sys.exit(1)
        sys.exit(0)

    if args.start_vm:
        if not vm_start(vm_name, headless=args.headless):
            sys.exit(1)
        if not args.no_wait:
            if not wait_for_socket(target):
                sys.exit(1)
            if not wait_for_prompt(target, args.timeout):
                sys.exit(1)
        sys.exit(0)

    # Regular command mode
    if not args.commands:
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if send_commands(target, args.commands) else 1)


if __name__ == '__main__':
    main()
