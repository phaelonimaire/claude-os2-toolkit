#!/usr/bin/env python3
"""
OS/2 Kernel Debugger interactive client.
Run this BEFORE starting the VM - the debug kernel waits for connection.

Usage: kdb_connect.py [target]
  target: Unix socket path or host:port (default: /tmp/dbgport, or
          KDB_DBGPORT env). Use host:port with VirtualBox TCP serial mode
          (--uartmode1 tcpserver <port>), e.g. on Windows hosts.
"""

import socket
import select
import sys
import os
import threading
import time

SOCKET_PATH = os.environ.get('KDB_DBGPORT', '/tmp/dbgport')
LOG_FILE = "/tmp/kdb_session.log"


def parse_target(target):
    """('tcp', (host, port)) for host:port specs, else ('unix', path)."""
    if '/' not in target and '\\' not in target:
        host, sep, port = target.rpartition(':')
        if sep and port.isdigit():
            return 'tcp', (host or '127.0.0.1', int(port))
    return 'unix', target


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else SOCKET_PATH
    kind, addr = parse_target(target)

    # Bounded wait. An unbounded one hangs forever when no VM is running,
    # which strands an unattended caller with no output and no error.
    timeout = float(os.environ.get('KDB_CONNECT_TIMEOUT', '30'))
    deadline = time.monotonic() + timeout

    if kind == 'unix':
        if not os.path.exists(addr):
            print(f"Waiting up to {timeout:g}s for {addr} to appear...")
            while not os.path.exists(addr):
                if time.monotonic() >= deadline:
                    sys.exit(f"kdb_connect: {addr} did not appear within "
                             f"{timeout:g}s - is the VM running with its serial "
                             f"port in host-pipe mode? (see recipes/setup-kdb-vm.md; "
                             f"raise KDB_CONNECT_TIMEOUT to wait longer)")
                time.sleep(0.5)
        print(f"Connecting to {addr}...")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(addr)
        except OSError as e:
            sys.exit(f"kdb_connect: cannot connect to {addr}: {e}")
    else:
        print(f"Connecting to {addr[0]}:{addr[1]} (up to {timeout:g}s)...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        while True:
            try:
                sock.connect(addr)
                break
            except OSError as e:
                if time.monotonic() >= deadline:
                    sys.exit(f"kdb_connect: could not connect to "
                             f"{addr[0]}:{addr[1]} within {timeout:g}s: {e} "
                             f"(is the VM up with --uartmode1 tcpserver? "
                             f"raise KDB_CONNECT_TIMEOUT to wait longer)")
                time.sleep(0.5)
    sock.setblocking(False)
    print("Connected! Waiting for OS/2 debug kernel...")
    print("(The VM will now boot. This takes about 60 seconds.)")
    print("Type 'quit' to exit, 'break' to send Ctrl+C")
    print("-" * 50)

    log = open(LOG_FILE, 'w')
    stop_event = threading.Event()

    def reader():
        while not stop_event.is_set():
            ready, _, _ = select.select([sock], [], [], 0.1)
            if ready:
                try:
                    data = sock.recv(4096)
                    if data:
                        text = data.decode('latin-1', errors='replace')
                        print(text, end='', flush=True)
                        log.write(text)
                        log.flush()
                except Exception as e:
                    if not stop_event.is_set():
                        print(f"\n[Connection error: {e}]")
                    break

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()

    try:
        while True:
            try:
                cmd = input()
                if cmd.lower() == 'quit':
                    break
                elif cmd.lower() == 'break':
                    print("[Sending Ctrl+C]")
                    sock.sendall(b'\x03')
                else:
                    sock.sendall(f"{cmd}\r\n".encode())
                    log.write(f">>> {cmd}\n")
            except EOFError:
                break
    except KeyboardInterrupt:
        print("\n[Interrupted]")
    finally:
        stop_event.set()
        sock.close()
        log.close()
        print(f"\nSession logged to {LOG_FILE}")

if __name__ == "__main__":
    main()
