"""
Parser for OS/2 Kernel Debugger output.
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class Registers:
    """CPU register state."""
    eax: int = 0
    ebx: int = 0
    ecx: int = 0
    edx: int = 0
    esi: int = 0
    edi: int = 0
    eip: int = 0
    esp: int = 0
    ebp: int = 0
    cs: int = 0
    ss: int = 0
    ds: int = 0
    es: int = 0
    fs: int = 0
    gs: int = 0
    iopl: int = 0
    flags: str = ""

    def __str__(self):
        return (
            f"eax={self.eax:08x} ebx={self.ebx:08x} ecx={self.ecx:08x} edx={self.edx:08x}\n"
            f"esi={self.esi:08x} edi={self.edi:08x} eip={self.eip:08x} esp={self.esp:08x}\n"
            f"ebp={self.ebp:08x} cs={self.cs:04x} ss={self.ss:04x} ds={self.ds:04x}\n"
            f"es={self.es:04x} fs={self.fs:04x} gs={self.gs:04x} iopl={self.iopl}"
        )


@dataclass
class Instruction:
    """A disassembled instruction."""
    address: int
    bytes: bytes
    mnemonic: str
    operands: str
    comment: str = ""

    def __str__(self):
        hex_bytes = self.bytes.hex()
        if self.comment:
            return f"{self.address:08x} {hex_bytes:20s} {self.mnemonic:10s} {self.operands:30s} ; {self.comment}"
        return f"{self.address:08x} {hex_bytes:20s} {self.mnemonic:10s} {self.operands}"


@dataclass
class MemoryDump:
    """A memory dump."""
    address: int
    data: bytes
    ascii_repr: str = ""

    def __str__(self):
        hex_data = ' '.join(f'{b:02x}' for b in self.data)
        return f"{self.address:08x}: {hex_data}  {self.ascii_repr}"


@dataclass
class ModuleInfo:
    """Information about a loaded module."""
    hmte: int
    pmte: int
    mflags: int
    name: str
    objects: List[Dict] = field(default_factory=list)


class KDBParser:
    """
    Parser for various OS/2 Kernel Debugger output formats.
    """

    # Register dump pattern (from 'r' command)
    # eax=fe5718b8 ebx=1c6fb810 ecx=00000000 edx=00000084 esi=1c6fb810 edi=1c6fef80
    REG_PATTERN = re.compile(
        r'eax=([0-9a-f]+)\s+ebx=([0-9a-f]+)\s+ecx=([0-9a-f]+)\s+edx=([0-9a-f]+)\s+'
        r'esi=([0-9a-f]+)\s+edi=([0-9a-f]+)',
        re.IGNORECASE
    )

    # Additional registers line
    # eip=1c02760c esp=0004f834 ebp=0004f880 iopl=2 -- -- -- nv up ei pl zr na pe nc
    REG_PATTERN2 = re.compile(
        r'eip=([0-9a-f]+)\s+esp=([0-9a-f]+)\s+ebp=([0-9a-f]+)\s+iopl=(\d+)',
        re.IGNORECASE
    )

    # Segment registers
    # cs=005b ss=0053 ds=0053 es=0053 fs=150b gs=0000
    SEG_PATTERN = re.compile(
        r'cs=([0-9a-f]+)\s+ss=([0-9a-f]+)\s+ds=([0-9a-f]+)\s+'
        r'es=([0-9a-f]+)\s+fs=([0-9a-f]+)\s+gs=([0-9a-f]+)',
        re.IGNORECASE
    )

    # Disassembly line pattern
    # %1c02760c 55                 push      ebp
    # 005b:1c02760c 55             push      ebp
    DISASM_PATTERN = re.compile(
        r'(?:%|[0-9a-f]{4}:)([0-9a-f]+)\s+([0-9a-f]+)\s+(\S+)(?:\s+(.*))?',
        re.IGNORECASE
    )

    # Memory dump pattern
    # 0053:0004f834 dd d5 93 1e 80 00 00 80-0c 00 00 00 73 02 16 00 ]U..........s...
    MEMDUMP_PATTERN = re.compile(
        r'(?:[0-9a-f]{4}:)?([0-9a-f]+)\s+'
        r'([0-9a-f]{2}(?:\s+[0-9a-f]{2})*(?:-[0-9a-f]{2}(?:\s+[0-9a-f]{2})*)?)\s+'
        r'(.{0,16})',
        re.IGNORECASE
    )

    # Module list pattern
    # hmte=00ca pmte=%fdbccfcc mflags=8498b594 c:\os2\dll\doscall1.dll
    MODULE_PATTERN = re.compile(
        r'hmte=([0-9a-f]+)\s+pmte=%([0-9a-f]+)\s+mflags=([0-9a-f]+)\s+(\S+)',
        re.IGNORECASE
    )

    # Module object pattern
    # obj   vsize    vbase    flags   ipagemap cpagemap hob  sel
    # 0001 00000360 1c010000 80009025 00000001 00000001 00d4 e00e r-x shr alias iopl
    OBJ_PATTERN = re.compile(
        r'([0-9a-f]{4})\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+'
        r'([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)',
        re.IGNORECASE
    )

    # Breakpoint hit pattern
    # ;br0
    BP_HIT_PATTERN = re.compile(r';br(\d+)')

    @classmethod
    def parse_registers(cls, text: str) -> Optional[Registers]:
        """
        Parse register dump from debugger output.

        Args:
            text: Output from 'r' command or breakpoint hit

        Returns:
            Registers object or None if parsing fails
        """
        regs = Registers()

        # Parse main registers
        match = cls.REG_PATTERN.search(text)
        if match:
            regs.eax = int(match.group(1), 16)
            regs.ebx = int(match.group(2), 16)
            regs.ecx = int(match.group(3), 16)
            regs.edx = int(match.group(4), 16)
            regs.esi = int(match.group(5), 16)
            regs.edi = int(match.group(6), 16)

        # Parse eip, esp, ebp, iopl
        match = cls.REG_PATTERN2.search(text)
        if match:
            regs.eip = int(match.group(1), 16)
            regs.esp = int(match.group(2), 16)
            regs.ebp = int(match.group(3), 16)
            regs.iopl = int(match.group(4))

        # Parse segment registers
        match = cls.SEG_PATTERN.search(text)
        if match:
            regs.cs = int(match.group(1), 16)
            regs.ss = int(match.group(2), 16)
            regs.ds = int(match.group(3), 16)
            regs.es = int(match.group(4), 16)
            regs.fs = int(match.group(5), 16)
            regs.gs = int(match.group(6), 16)

        return regs

    @classmethod
    def parse_disassembly(cls, text: str) -> List[Instruction]:
        """
        Parse disassembly output.

        Args:
            text: Output from 'u' command

        Returns:
            List of Instruction objects
        """
        instructions = []

        for line in text.split('\n'):
            match = cls.DISASM_PATTERN.match(line.strip())
            if match:
                addr = int(match.group(1), 16)
                hex_bytes = bytes.fromhex(match.group(2).replace(' ', ''))
                mnemonic = match.group(3)
                operands = match.group(4) or ""

                # Check for comment (after semicolon)
                comment = ""
                if ';' in operands:
                    operands, comment = operands.split(';', 1)
                    operands = operands.strip()
                    comment = comment.strip()

                instructions.append(Instruction(
                    address=addr,
                    bytes=hex_bytes,
                    mnemonic=mnemonic,
                    operands=operands,
                    comment=comment
                ))

        return instructions

    @classmethod
    def parse_memory_dump(cls, text: str) -> List[MemoryDump]:
        """
        Parse memory dump output.

        Args:
            text: Output from 'd' command

        Returns:
            List of MemoryDump objects
        """
        dumps = []

        for line in text.split('\n'):
            match = cls.MEMDUMP_PATTERN.match(line.strip())
            if match:
                addr = int(match.group(1), 16)
                hex_str = match.group(2).replace('-', ' ')
                data = bytes.fromhex(hex_str.replace(' ', ''))
                ascii_repr = match.group(3) if match.group(3) else ""

                dumps.append(MemoryDump(
                    address=addr,
                    data=data,
                    ascii_repr=ascii_repr
                ))

        return dumps

    @classmethod
    def parse_module_list(cls, text: str) -> List[ModuleInfo]:
        """
        Parse module list output.

        Args:
            text: Output from '.lm' command

        Returns:
            List of ModuleInfo objects
        """
        modules = []

        for line in text.split('\n'):
            match = cls.MODULE_PATTERN.match(line.strip())
            if match:
                modules.append(ModuleInfo(
                    hmte=int(match.group(1), 16),
                    pmte=int(match.group(2), 16),
                    mflags=int(match.group(3), 16),
                    name=match.group(4)
                ))

        return modules

    @classmethod
    def parse_breakpoint_hit(cls, text: str) -> Optional[int]:
        """
        Check if text indicates a breakpoint hit and return breakpoint number.

        Args:
            text: Debugger output

        Returns:
            Breakpoint number or None
        """
        match = cls.BP_HIT_PATTERN.search(text)
        if match:
            return int(match.group(1))
        return None

    @classmethod
    def extract_dwords(cls, text: str) -> List[Tuple[int, int]]:
        """
        Extract address-value pairs from memory dump.

        Args:
            text: Memory dump output

        Returns:
            List of (address, value) tuples for each DWORD
        """
        results = []
        dumps = cls.parse_memory_dump(text)

        for dump in dumps:
            addr = dump.address
            data = dump.data
            # Process as DWORDs (little-endian)
            for i in range(0, len(data) - 3, 4):
                value = int.from_bytes(data[i:i+4], 'little')
                results.append((addr + i, value))

        return results
