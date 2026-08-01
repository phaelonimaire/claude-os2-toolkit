"""
Scripting support for OS/2 Kernel Debugger automation.
"""

from typing import Optional, List, Callable, Dict, Any
from dataclasses import dataclass, field
from .session import KDBSession, TraceResult, Breakpoint
from .parser import Registers, Instruction


@dataclass
class TraceRecord:
    """Record of a traced instruction."""
    step_num: int
    eip: int
    instruction: Optional[Instruction]
    registers: Registers
    stack_top: List[tuple] = field(default_factory=list)  # (offset, value) pairs
    custom_data: Dict[str, Any] = field(default_factory=dict)


class KDBScript:
    """
    Scripting interface for automated debugging sessions.

    Usage:
        script = KDBScript('/tmp/dbgport', log_file='/tmp/trace.log')

        # Addresses are build-specific: resolve the entry point and the
        # containing object's bounds for YOUR module first (e.g. with
        # tools/lx_export.py, or KDB's own symbol lookup). The literals
        # below stand in for whatever those resolve to.
        ENTRY, OBJ_LO, OBJ_HI = 0x00010000, 0x00010000, 0x00020000

        # Define what to do when the target function is hit
        def on_entry(script, regs):
            print(f"entry hit: EAX={regs.eax:08x} EDX={regs.edx:08x}")

            # Single-step until execution leaves the object
            script.trace_until(lambda r: r.eip < OBJ_LO or r.eip > OBJ_HI,
                               max_steps=500)

        script.run(
            breakpoints=[ENTRY],
            on_break=on_entry,
            timeout=300
        )
    """

    def __init__(self, socket_path: str = '/tmp/dbgport',
                 log_file: Optional[str] = None):
        self.session = KDBSession(socket_path, log_file)
        self.trace_log: List[TraceRecord] = []
        self._step_count = 0

    def connect_and_wait(self, boot_timeout: float = 120.0) -> bool:
        """Connect to debugger and wait for OS/2 to boot."""
        print(f"Connecting to {self.session.conn.socket_path}...")
        self.session.connect()
        print("Connected. Waiting for OS/2 to boot...")
        result = self.session.wait_for_boot(boot_timeout)
        if result:
            print("OS/2 booted successfully.")
        return result

    def close(self):
        """Close the session."""
        self.session.close()

    def run(self, breakpoints: List[int],
            on_break: Callable[['KDBScript', Registers], None],
            timeout: float = 300.0,
            max_hits: int = 0):
        """
        Run with breakpoints and call handler on each hit.

        Args:
            breakpoints: List of addresses to break on
            on_break: Function called when breakpoint hit
            timeout: Total timeout for run
            max_hits: Max breakpoint hits (0 = unlimited)
        """
        # Set breakpoints
        for addr in breakpoints:
            bp = self.session.set_breakpoint(addr)
            print(f"Set breakpoint {bp.number} at {addr:08x}")

        hits = 0
        while max_hits == 0 or hits < max_hits:
            print("Continuing...")
            result = self.session.go(timeout=timeout)

            if result.hit_breakpoint is not None:
                hits += 1
                print(f"Hit breakpoint {result.hit_breakpoint}")
                on_break(self, result.registers)
            else:
                print("Stopped (no breakpoint hit)")
                break

    def step(self, record: bool = True) -> TraceResult:
        """
        Single step, optionally recording to trace log.

        Args:
            record: If True, add to trace log

        Returns:
            TraceResult
        """
        result = self.session.step()
        self._step_count += 1

        if record:
            stack = self.session.dump_stack(4)
            self.trace_log.append(TraceRecord(
                step_num=self._step_count,
                eip=result.registers.eip,
                instruction=result.instruction,
                registers=result.registers,
                stack_top=stack
            ))

        return result

    def trace_into(self, record: bool = True) -> TraceResult:
        """Single step with trace into calls."""
        result = self.session.trace()
        self._step_count += 1

        if record:
            stack = self.session.dump_stack(4)
            self.trace_log.append(TraceRecord(
                step_num=self._step_count,
                eip=result.registers.eip,
                instruction=result.instruction,
                registers=result.registers,
                stack_top=stack
            ))

        return result

    def trace_until(self, condition: Callable[[Registers], bool],
                    max_steps: int = 1000,
                    trace_into: bool = False,
                    record: bool = True,
                    verbose: bool = False) -> List[TraceRecord]:
        """
        Trace until condition is met.

        Args:
            condition: Function that returns True when tracing should stop
            max_steps: Maximum steps before giving up
            trace_into: If True, trace into calls
            record: If True, record all steps
            verbose: If True, print each step

        Returns:
            List of TraceRecords
        """
        records = []
        step_func = self.trace_into if trace_into else self.step

        for i in range(max_steps):
            result = step_func(record=record)

            if record:
                records.append(self.trace_log[-1])

            if verbose:
                instr = result.instruction
                if instr:
                    print(f"{i:4d}: {result.registers.eip:08x} {instr.mnemonic} {instr.operands}")
                else:
                    print(f"{i:4d}: {result.registers.eip:08x}")

            if condition(result.registers):
                break

        return records

    def trace_function(self, entry_addr: int, max_steps: int = 1000,
                       verbose: bool = False) -> List[TraceRecord]:
        """
        Trace a function from entry to return.

        Assumes we're stopped at the function entry.

        Args:
            entry_addr: Function entry address (for reference)
            max_steps: Maximum steps
            verbose: Print each step

        Returns:
            List of TraceRecords for the function execution
        """
        regs = self.session.get_registers()
        initial_esp = regs.esp

        def at_return(r: Registers) -> bool:
            # Function returns when ESP > initial (stack cleaned up)
            # and we're not inside the function anymore
            return r.esp > initial_esp

        return self.trace_until(at_return, max_steps=max_steps, verbose=verbose)

    def trace_to_address(self, target: int, max_steps: int = 1000,
                         verbose: bool = False) -> List[TraceRecord]:
        """
        Trace until we reach a specific address.

        Args:
            target: Target EIP address
            max_steps: Maximum steps
            verbose: Print each step

        Returns:
            List of TraceRecords
        """
        return self.trace_until(
            lambda r: r.eip == target,
            max_steps=max_steps,
            verbose=verbose
        )

    def dump_trace_log(self, filename: str):
        """
        Dump trace log to file.

        Args:
            filename: Output file path
        """
        with open(filename, 'w') as f:
            f.write("# OS/2 Kernel Debugger Trace Log\n")
            f.write(f"# {len(self.trace_log)} steps recorded\n\n")

            for rec in self.trace_log:
                f.write(f"Step {rec.step_num}: EIP={rec.eip:08x}\n")
                if rec.instruction:
                    f.write(f"  {rec.instruction.mnemonic} {rec.instruction.operands}\n")
                f.write(f"  EAX={rec.registers.eax:08x} EBX={rec.registers.ebx:08x} "
                        f"ECX={rec.registers.ecx:08x} EDX={rec.registers.edx:08x}\n")
                f.write(f"  ESI={rec.registers.esi:08x} EDI={rec.registers.edi:08x} "
                        f"ESP={rec.registers.esp:08x} EBP={rec.registers.ebp:08x}\n")
                if rec.stack_top:
                    f.write("  Stack: " + " ".join(f"[+{off:02x}]={val:08x}"
                                                   for off, val in rec.stack_top) + "\n")
                f.write("\n")

        print(f"Trace log saved to {filename}")

    def clear_trace_log(self):
        """Clear the trace log."""
        self.trace_log.clear()
        self._step_count = 0

    # === Convenience Methods ===

    def read_dword(self, addr: int) -> int:
        """Read a DWORD from memory."""
        return self.session.read_dword(addr)

    def read_memory(self, addr: int, length: int = 16) -> bytes:
        """Read memory."""
        return self.session.read_memory(addr, length)

    def get_registers(self) -> Registers:
        """Get current registers."""
        return self.session.get_registers()

    def disassemble(self, addr: Optional[int] = None, count: int = 10) -> List[Instruction]:
        """Disassemble at address."""
        return self.session.disassemble(addr, count)

    def go(self, timeout: float = 60.0) -> TraceResult:
        """Continue execution."""
        return self.session.go(timeout)

    def send_break(self):
        """Break into debugger."""
        return self.session.send_break()

    def command(self, cmd: str, timeout: float = 10.0):
        """Send raw command."""
        return self.session.command(cmd, timeout)
