"""
High-level session management for OS/2 Kernel Debugger.
"""

from typing import Optional, List, Callable, Dict, Any
from dataclasses import dataclass
from .connection import KDBConnection, KDBResponse
from .parser import KDBParser, Registers, Instruction, MemoryDump, ModuleInfo


@dataclass
class Breakpoint:
    """Represents a debugger breakpoint."""
    number: int
    address: int
    enabled: bool = True
    hit_count: int = 0
    condition: Optional[str] = None


@dataclass
class TraceResult:
    """Result of a trace/step operation."""
    registers: Registers
    instruction: Optional[Instruction]
    hit_breakpoint: Optional[int]
    raw_output: str


class KDBSession:
    """
    High-level session for interacting with OS/2 Kernel Debugger.

    Provides convenient methods for common debugging operations.

    Usage:
        session = KDBSession('/tmp/dbgport', log_file='/tmp/kdb.log')
        session.connect()
        session.wait_for_boot()

        # Set breakpoint (address is build-specific - resolve it for your
        # module first, e.g. with tools/lx_export.py or KDB symbol lookup)
        bp = session.set_breakpoint(0x00010000)

        # Continue and wait for breakpoint
        session.go()

        # When breakpoint hits, examine state
        regs = session.get_registers()
        print(f"EAX = {regs.eax:08x}")

        # Step through code
        for i in range(10):
            result = session.step()
            print(f"EIP = {result.registers.eip:08x}")

        session.close()
    """

    def __init__(self, socket_path: str = '/tmp/dbgport',
                 log_file: Optional[str] = None):
        self.conn = KDBConnection(socket_path, log_file)
        self.breakpoints: Dict[int, Breakpoint] = {}
        self._next_bp_num = 0
        self._current_regs: Optional[Registers] = None
        self._stopped = False
        self._callbacks: Dict[str, List[Callable]] = {
            'breakpoint': [],
            'step': [],
        }

    def connect(self, timeout: float = 30.0) -> bool:
        """Connect to the debugger socket."""
        return self.conn.connect(timeout)

    def close(self):
        """Close the session."""
        self.conn.close()

    def wait_for_boot(self, timeout: float = 120.0) -> bool:
        """Wait for OS/2 to boot."""
        return self.conn.wait_for_boot(timeout)

    def send_break(self) -> KDBResponse:
        """Send Ctrl+C to break into debugger."""
        self.conn.send_break()
        response = self.conn.read_until_prompt(timeout=5.0)
        self._stopped = True
        if response.raw:
            self._current_regs = KDBParser.parse_registers(response.raw)
        return response

    def command(self, cmd: str, timeout: float = 10.0) -> KDBResponse:
        """Send a raw command to the debugger."""
        return self.conn.send_command(cmd, timeout)

    # === Register Operations ===

    def get_registers(self) -> Registers:
        """Get current register state."""
        response = self.command('r')
        regs = KDBParser.parse_registers(response.raw)
        if regs:
            self._current_regs = regs
        return regs or Registers()

    def get_register(self, name: str) -> int:
        """Get a specific register value."""
        regs = self.get_registers()
        return getattr(regs, name.lower(), 0)

    # === Memory Operations ===

    def read_memory(self, address: int, length: int = 16) -> bytes:
        """
        Read memory at address.

        Args:
            address: Flat address to read
            length: Number of bytes to read

        Returns:
            Bytes read from memory
        """
        # Calculate how many 16-byte lines we need
        lines = (length + 15) // 16
        response = self.command(f'd %{address:08x} L{lines}')
        dumps = KDBParser.parse_memory_dump(response.raw)

        # Concatenate all data
        data = b''
        for dump in dumps:
            data += dump.data

        return data[:length]

    def read_dword(self, address: int) -> int:
        """Read a 32-bit value from memory."""
        data = self.read_memory(address, 4)
        if len(data) >= 4:
            return int.from_bytes(data[:4], 'little')
        return 0

    def read_word(self, address: int) -> int:
        """Read a 16-bit value from memory."""
        data = self.read_memory(address, 2)
        if len(data) >= 2:
            return int.from_bytes(data[:2], 'little')
        return 0

    def dump_stack(self, count: int = 8) -> List[tuple]:
        """
        Dump stack as list of (offset, value) tuples.

        Args:
            count: Number of DWORDs to dump

        Returns:
            List of (offset, value) tuples
        """
        response = self.command(f'dd ss:esp L{count}')
        dwords = KDBParser.extract_dwords(response.raw)

        # Convert to offset from ESP
        regs = self._current_regs or self.get_registers()
        esp = regs.esp

        return [(addr - esp, value) for addr, value in dwords]

    # === Disassembly ===

    def disassemble(self, address: Optional[int] = None,
                    count: int = 10) -> List[Instruction]:
        """
        Disassemble instructions.

        Args:
            address: Start address (None for current EIP)
            count: Number of instructions

        Returns:
            List of Instruction objects
        """
        if address is None:
            cmd = f'u L{count}'
        else:
            cmd = f'u %{address:08x} L{count}'

        response = self.command(cmd)
        return KDBParser.parse_disassembly(response.raw)

    def disassemble_at(self, address: int, count: int = 10) -> List[Instruction]:
        """Disassemble at specific flat address."""
        return self.disassemble(address, count)

    # === Breakpoint Operations ===

    def set_breakpoint(self, address: int) -> Breakpoint:
        """
        Set a breakpoint at address.

        Args:
            address: Flat address for breakpoint

        Returns:
            Breakpoint object
        """
        response = self.command(f'bp %{address:08x}')

        bp = Breakpoint(
            number=self._next_bp_num,
            address=address
        )
        self.breakpoints[self._next_bp_num] = bp
        self._next_bp_num += 1

        return bp

    def clear_breakpoint(self, bp_num: int):
        """Clear a breakpoint by number."""
        self.command(f'bc {bp_num}')
        if bp_num in self.breakpoints:
            del self.breakpoints[bp_num]

    def clear_all_breakpoints(self):
        """Clear all breakpoints."""
        self.command('bc *')
        self.breakpoints.clear()

    def list_breakpoints(self) -> str:
        """Get breakpoint list from debugger."""
        response = self.command('bl')
        return response.raw

    # === Execution Control ===

    def go(self, timeout: float = 60.0) -> TraceResult:
        """
        Continue execution until breakpoint or Ctrl+C.

        Args:
            timeout: How long to wait for breakpoint

        Returns:
            TraceResult with state when stopped
        """
        self._stopped = False
        response = self.command('g', timeout=timeout)

        regs = KDBParser.parse_registers(response.raw)
        bp_num = KDBParser.parse_breakpoint_hit(response.raw)

        if bp_num is not None and bp_num in self.breakpoints:
            self.breakpoints[bp_num].hit_count += 1
            self._fire_callbacks('breakpoint', self.breakpoints[bp_num], regs)

        self._stopped = True
        self._current_regs = regs

        return TraceResult(
            registers=regs or Registers(),
            instruction=None,
            hit_breakpoint=bp_num,
            raw_output=response.raw
        )

    def step(self) -> TraceResult:
        """
        Single step (step over calls).

        Returns:
            TraceResult with new state
        """
        response = self.command('p')

        regs = KDBParser.parse_registers(response.raw)
        instructions = KDBParser.parse_disassembly(response.raw)
        bp_num = KDBParser.parse_breakpoint_hit(response.raw)

        self._current_regs = regs
        self._fire_callbacks('step', regs)

        return TraceResult(
            registers=regs or Registers(),
            instruction=instructions[0] if instructions else None,
            hit_breakpoint=bp_num,
            raw_output=response.raw
        )

    def trace(self) -> TraceResult:
        """
        Trace (step into calls).

        Returns:
            TraceResult with new state
        """
        response = self.command('t')

        regs = KDBParser.parse_registers(response.raw)
        instructions = KDBParser.parse_disassembly(response.raw)
        bp_num = KDBParser.parse_breakpoint_hit(response.raw)

        self._current_regs = regs
        self._fire_callbacks('step', regs)

        return TraceResult(
            registers=regs or Registers(),
            instruction=instructions[0] if instructions else None,
            hit_breakpoint=bp_num,
            raw_output=response.raw
        )

    def step_n(self, count: int, trace_into: bool = False) -> List[TraceResult]:
        """
        Execute multiple steps.

        Args:
            count: Number of steps
            trace_into: If True, trace into calls; otherwise step over

        Returns:
            List of TraceResult for each step
        """
        results = []
        step_func = self.trace if trace_into else self.step

        for _ in range(count):
            result = step_func()
            results.append(result)

        return results

    # === Module Operations ===

    def list_modules(self) -> List[ModuleInfo]:
        """Get list of loaded modules."""
        response = self.command('.lm', timeout=30.0)
        return KDBParser.parse_module_list(response.raw)

    def find_module(self, name: str) -> Optional[ModuleInfo]:
        """Find a module by name (case-insensitive partial match)."""
        modules = self.list_modules()
        name_lower = name.lower()
        for mod in modules:
            if name_lower in mod.name.lower():
                return mod
        return None

    # === Callbacks ===

    def on_breakpoint(self, callback: Callable[[Breakpoint, Registers], None]):
        """Register callback for breakpoint hits."""
        self._callbacks['breakpoint'].append(callback)

    def on_step(self, callback: Callable[[Registers], None]):
        """Register callback for step operations."""
        self._callbacks['step'].append(callback)

    def _fire_callbacks(self, event: str, *args):
        """Fire callbacks for an event."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args)
            except Exception as e:
                print(f"Callback error: {e}")

    # === Utility ===

    @property
    def is_stopped(self) -> bool:
        """True if debugger is at a breakpoint or stopped."""
        return self._stopped

    @property
    def current_registers(self) -> Optional[Registers]:
        """Get last known register state without querying debugger."""
        return self._current_regs
