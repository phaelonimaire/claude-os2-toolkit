"""
Low-level connection handling for OS/2 Kernel Debugger.
"""

import socket
import select
import time
import os
import re
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class KDBResponse:
    """Represents a response from the kernel debugger."""
    raw: str           # Raw response text
    prompt: str        # The prompt that ended the response (## or **)
    at_breakpoint: bool  # True if we hit a breakpoint
    task_number: Optional[int] = None  # Current task number if shown


def parse_target(target: str) -> Tuple[str, object]:
    """Split a target spec into ('tcp', (host, port)) or ('unix', path).

    A spec with no path separators whose final ':'-field is numeric is
    host:port (e.g. 'localhost:5555', ':5555' = localhost); anything else
    is a Unix socket path. Use TCP (VBoxManage modifyvm <vm> --uartmode1
    tcpserver <port>) on Windows hosts, where VBox host pipes are named
    pipes Python sockets can't open.
    """
    if '/' not in target and '\\' not in target:
        host, sep, port = target.rpartition(':')
        if sep and port.isdigit():
            return 'tcp', (host or '127.0.0.1', int(port))
    return 'unix', target


class KDBConnection:
    """
    Low-level connection to OS/2 Kernel Debugger via Unix socket or TCP.

    Usage:
        conn = KDBConnection('/tmp/dbgport')       # Unix socket
        conn = KDBConnection('localhost:5555')     # VBox tcpserver mode
        conn.connect()
        response = conn.send_command('r')
        print(response.raw)
        conn.close()
    """

    # Prompt patterns
    PROMPT_NORMAL = b'##'      # Normal prompt
    PROMPT_BREAK = b'**'       # At breakpoint
    PROMPT_PATTERN = re.compile(rb'(\*\*|##)\s*$')

    # Breakpoint hit pattern
    BP_PATTERN = re.compile(r';br(\d+)')

    def __init__(self, socket_path: str = '/tmp/dbgport',
                 log_file: Optional[str] = None):
        self.socket_path = socket_path
        self.sock: Optional[socket.socket] = None
        self.log_file = log_file
        self._log_handle = None
        self._buffer = b''

    def connect(self, timeout: float = 30.0) -> bool:
        """
        Connect to the debugger target (Unix socket path or host:port).

        Args:
            timeout: How long to wait for the target to become connectable

        Returns:
            True if connected successfully
        """
        kind, addr = parse_target(self.socket_path)
        start = time.time()

        if kind == 'unix':
            if not hasattr(socket, 'AF_UNIX'):
                raise OSError(
                    "Unix sockets are unavailable on this platform. Configure "
                    "the VM serial port in TCP mode (VBoxManage modifyvm <vm> "
                    "--uartmode1 tcpserver <port>) and connect to 'host:port'")
            # Wait for socket file to appear
            while not os.path.exists(addr):
                if time.time() - start > timeout:
                    raise TimeoutError(f"Socket {addr} did not appear within {timeout}s")
                time.sleep(0.5)
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.connect(addr)
        else:
            # TCP: existence can only be probed by connecting - retry
            while True:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # Preserve per-character pacing on the wire
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                try:
                    sock.connect(addr)
                    self.sock = sock
                    break
                except OSError:
                    sock.close()
                    if time.time() - start > timeout:
                        raise TimeoutError(
                            f"Could not connect to {self.socket_path} within {timeout}s")
                    time.sleep(0.5)
        self.sock.setblocking(False)

        if self.log_file:
            self._log_handle = open(self.log_file, 'w')

        self._log(f"[Connected to {self.socket_path}]\n")
        return True

    def close(self):
        """Close the connection."""
        if self.sock:
            self.sock.close()
            self.sock = None
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None

    def _log(self, text: str):
        """Write to log file if enabled."""
        if self._log_handle:
            self._log_handle.write(text)
            self._log_handle.flush()

    # Per-character send delay. The KDB serial pipe drops characters if a
    # command is blasted in one write (matches kdb_cmd.py's CHAR_DELAY).
    CHAR_DELAY = 0.005

    def send_raw(self, data: bytes):
        """Send raw bytes to debugger, one char at a time to avoid drops."""
        if not self.sock:
            raise RuntimeError("Not connected")
        for i in range(len(data)):
            self.sock.sendall(data[i:i+1])
            time.sleep(self.CHAR_DELAY)
        self._log(f">>> {data!r}\n")

    def send_break(self):
        """Send Ctrl+C to break into debugger."""
        self.send_raw(b'\x03')

    def send_command(self, cmd: str, timeout: float = 10.0) -> KDBResponse:
        """
        Send a command and wait for response.

        Args:
            cmd: Command to send (without newline)
            timeout: How long to wait for response

        Returns:
            KDBResponse with the debugger's response
        """
        self.send_raw(f"{cmd}\r\n".encode())
        return self.read_until_prompt(timeout)

    def read_until_prompt(self, timeout: float = 10.0) -> KDBResponse:
        """
        Read until we see a debugger prompt (## or **).

        Args:
            timeout: Maximum time to wait

        Returns:
            KDBResponse with accumulated output
        """
        if not self.sock:
            raise RuntimeError("Not connected")

        start = time.time()

        while time.time() - start < timeout:
            ready, _, _ = select.select([self.sock], [], [], 0.1)
            if ready:
                try:
                    chunk = self.sock.recv(4096)
                    if chunk:
                        self._buffer += chunk
                        self._log(chunk.decode('latin-1', errors='replace'))
                except BlockingIOError:
                    pass

            # Pager pause: send CR to continue and drop the marker so it
            # neither stalls the read nor pollutes the response text
            more_pos = self._buffer.rfind(b'--More--')
            if more_pos != -1:
                self.sock.sendall(b'\r')
                self._buffer = (self._buffer[:more_pos] +
                                self._buffer[more_pos + len(b'--More--'):])

            # Check for prompt
            match = self.PROMPT_PATTERN.search(self._buffer)
            if match:
                # Extract response up to and including prompt
                end_pos = match.end()
                response_bytes = self._buffer[:end_pos]
                self._buffer = self._buffer[end_pos:]

                response_text = response_bytes.decode('latin-1', errors='replace')
                prompt = match.group(1).decode('latin-1')

                # Check if we hit a breakpoint
                at_breakpoint = prompt == '**' or bool(self.BP_PATTERN.search(response_text))

                return KDBResponse(
                    raw=response_text,
                    prompt=prompt,
                    at_breakpoint=at_breakpoint
                )

        # Timeout - return what we have
        response_text = self._buffer.decode('latin-1', errors='replace')
        self._buffer = b''
        return KDBResponse(
            raw=response_text,
            prompt='',
            at_breakpoint=False
        )

    def read_available(self, timeout: float = 0.5) -> str:
        """
        Read whatever is available without waiting for prompt.

        Args:
            timeout: How long to wait for data

        Returns:
            Available data as string
        """
        if not self.sock:
            raise RuntimeError("Not connected")

        start = time.time()

        while time.time() - start < timeout:
            ready, _, _ = select.select([self.sock], [], [], 0.1)
            if ready:
                try:
                    chunk = self.sock.recv(4096)
                    if chunk:
                        self._buffer += chunk
                        self._log(chunk.decode('latin-1', errors='replace'))
                except BlockingIOError:
                    pass

        result = self._buffer.decode('latin-1', errors='replace')
        self._buffer = b''
        return result

    def wait_for_boot(self, timeout: float = 120.0) -> bool:
        """
        Wait for OS/2 to boot and show debugger prompt.

        Args:
            timeout: Maximum time to wait for boot

        Returns:
            True if we got a prompt
        """
        print(f"Waiting for OS/2 to boot (up to {timeout}s)...")
        response = self.read_until_prompt(timeout)
        return bool(response.prompt)

    @property
    def is_connected(self) -> bool:
        return self.sock is not None
