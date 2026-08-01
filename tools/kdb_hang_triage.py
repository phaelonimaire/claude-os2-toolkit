#!/usr/bin/env python3
"""
Triage a hung (frozen) OS/2 system via the kernel debugger.

For "the desktop froze" situations: break into the live system, take a
thread census, resolve what each blocked thread is waiting on, chase
semaphore ownership, and emit a symbol-annotated hang report.

Typical WPS/PM hangs are NOT crashes - one thread blocks on a PM
semaphore (often while holding the single input queue) and the desktop
appears dead while the kernel runs fine underneath. This script finds
that thread and names the code it is sitting in.

Usage:
    1. Desktop freezes in the debug-kernel VM. Do NOT reboot.
    2. ./tools/kdb_hang_triage.py
    3. Read the report (default /tmp/kdb_hang_<timestamp>.txt)

Options:
    --socket TARGET   Debug target (default /tmp/dbgport or KDB_DBGPORT env)
    --focus REGEX     Thread names to prioritize (default: pmshell|wps|xfldr)
    --max-slots N     Max threads to detail (default 10)
    --stack-dwords N  Stack depth per thread (default 24)
    --no-modules      Skip the .lm module list (faster)
    --resume          Send 'g' when done (default: leave system stopped)
    --report FILE     Report path (default /tmp/kdb_hang_<timestamp>.txt)

The report always embeds the raw debugger output for every command, so
even where parsing falls short the evidence is preserved.
"""

import argparse
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kdb import KDBSession
from kdb.parser import KDBParser

DEFAULT_TARGET = os.environ.get('KDB_DBGPORT', '/tmp/dbgport')

# .p* census line:
#  Slot  Pid  Ppid Csid Ord  Sta Pri  pTSD     pPTDA    pTCB     Disp SG Name
# *0008# 0016 0013 0016 0001 blk 0500 7b7d3000 7b9f75d8 7b7d6e0c 0eac 14 pmshell
THREAD_RE = re.compile(
    r'^\s*([*+])?\s*([0-9a-f]{1,4})(#?)\s+'
    r'([0-9a-f]{1,4})\s+([0-9a-f]{1,4})\s+([0-9a-f]{1,4})\s+([0-9a-f]{1,4})\s+'
    r'([a-z]{2,4})\s+([0-9a-f]{2,4})\s+'
    r'([0-9a-f]{7,8})\s+([0-9a-f]{7,8})\s+([0-9a-f]{7,8})\s+'
    r'([0-9a-f]{3,4})\s+([0-9a-f]{1,2})\s+(\S.*?)\s*$',
    re.IGNORECASE)

# .pb line:
#  Slot  Sta BlockID  Name     Type        Addr    Symbol
#  0015  blk fdda5ba0 pmshell  Sem32     8001 0034 _end + 13e8b9c4
BLOCK_RE = re.compile(
    r'^\s*[*+]?\s*([0-9a-f]{1,4})#?\s+([a-z]{2,4})\s+([0-9a-f]{7,8})\s+'
    r'(\S+)(?:\s+(\S.*?))?\s*$',
    re.IGNORECASE)

BLOCK_TYPES = {'sem32', 'syssem', 'dossem', 'ramsem', 'muxwait', 'childwait',
               'sleep', 'delay'}

# Pseudo BlockID token prefixes (not memory addresses): MuxWait, RamSem,
# ChildWait use fffd:xxxx / fffe:xxxx / ffca:xxxx style encodings
PSEUDO_BID_HI = {0xfffd, 0xfffe, 0xffca, 0xffcb}

# ln output line: address followed by module!symbol (± offset text)
LN_RE = re.compile(r'^\s*%?([0-9a-f]{4,8}(?::[0-9a-f]{4,8})?)\s+(\S+!?\S*.*?)\s*$',
                   re.IGNORECASE)


class Thread:
    def __init__(self, slot, pid, ppid, ord_, sta, pri, name,
                 dispatched=False, debugger_slot=False):
        self.slot = slot
        self.pid = pid
        self.ppid = ppid
        self.ord = ord_
        self.sta = sta
        self.pri = pri
        self.name = name
        self.dispatched = dispatched
        self.debugger_slot = debugger_slot
        self.block_id = None      # from .pb
        self.block_type = ''      # Sem32/RamSem/MuxWait/... from .pb
        self.block_info = ''      # raw remainder of .pb line
        self.regs = None          # Registers from .r in slot context
        self.eip_symbol = ''
        self.stack_symbols = []   # list of (value, symbol_text)
        self.raw_detail = ''      # raw debugger output for the detail pass

    @property
    def is_system(self):
        return self.name.startswith('*')


class HangTriage:
    def __init__(self, args):
        self.args = args
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.report_path = args.report or f'/tmp/kdb_hang_{ts}.txt'
        self.session = KDBSession(args.socket, log_file='/tmp/kdb_hang_session.log')
        self.threads = {}         # slot -> Thread
        self.sections = []        # (title, text) report sections
        self.ln_cache = {}
        self.ksem_info = {}       # block_id -> dict(raw, owner_candidates, type_note)

    # --- infrastructure -------------------------------------------------

    def status(self, msg):
        print(msg, flush=True)

    def cmd(self, c, timeout=15.0):
        return self.session.command(c, timeout=timeout).raw

    def break_in(self):
        """Get to a debugger prompt, whether the system is running or not."""
        self.status(f"Connecting to {self.args.socket} ...")
        self.session.connect(timeout=10.0)
        for attempt in range(3):
            resp = self.session.send_break()
            if resp.prompt:
                self.status("At debugger prompt (break-in successful).")
                return True
            # Maybe we were already at a prompt: a bare CR should echo one
            probe = self.session.conn.send_command('', timeout=3.0)
            if probe.prompt:
                self.status("Debugger was already at a prompt.")
                return True
            self.status(f"No prompt yet, retrying break-in ({attempt + 1}/3)...")
        return False

    # --- census ---------------------------------------------------------

    def thread_census(self):
        # NB: plain '.p' lists ALL slots; '.p*' means only the current slot
        self.status("Taking thread census (.p)...")
        raw = self.cmd('.p', timeout=60.0)
        self.sections.append(('THREAD CENSUS (.p)', raw))
        for line in raw.split('\n'):
            m = THREAD_RE.match(line)
            if not m:
                continue
            slot = int(m.group(2), 16)
            self.threads[slot] = Thread(
                slot=slot,
                pid=int(m.group(4), 16),
                ppid=int(m.group(5), 16),
                ord_=int(m.group(7), 16),
                sta=m.group(8).lower(),
                pri=int(m.group(9), 16),
                name=m.group(15).strip(),
                dispatched=(m.group(1) == '*'),
                debugger_slot=(m.group(3) == '#'),
            )
        self.status(f"  {len(self.threads)} threads parsed.")

    def block_info(self):
        self.status("Reading block info (.pb)...")
        raw = self.cmd('.pb', timeout=60.0)
        self.sections.append(('BLOCK INFO (.pb)', raw))
        for line in raw.split('\n'):
            if 'BlockID' in line:   # repeated column headers
                continue
            m = BLOCK_RE.match(line)
            if not m:
                continue
            slot = int(m.group(1), 16)
            t = self.threads.get(slot)
            if t is None:
                # .pb is authoritative for blocked threads even when the .p
                # census parse missed a slot - synthesize a minimal entry
                t = Thread(slot=slot, pid=0, ppid=0, ord_=0,
                           sta=m.group(2).lower(), pri=0,
                           name=m.group(4).strip())
                self.threads[slot] = t
            t.block_id = int(m.group(3), 16)
            rest = (m.group(5) or '').strip()
            first = rest.split(None, 1)[0].lower() if rest else ''
            if first in BLOCK_TYPES:
                t.block_type = first
            t.block_info = rest

    # --- symbol resolution ----------------------------------------------

    def lookup(self, addr_expr):
        """Symbol lookup via ln; cached; returns short annotation text."""
        if addr_expr in self.ln_cache:
            return self.ln_cache[addr_expr]
        raw = self.cmd(f'ln {addr_expr}', timeout=8.0)
        result = ''
        for line in raw.split('\n'):
            line = line.strip()
            if not line or line.startswith(('ln ', '##', '**')):
                continue
            m = LN_RE.match(line)
            if not m:
                continue
            sym = m.group(2)
            # With no .sym loaded for the owning module, KDB falls back to
            # a distant anchor like "locale:DGROUP:_end + 1e92f149" - noise
            if '_end +' in sym or '+ ??' in sym or sym.startswith('%00000000'):
                continue
            if '!' in sym or ':' not in sym:
                result = f"{sym} (@{m.group(1)})"
                break
        self.ln_cache[addr_expr] = result
        return result

    def lookup_code_addr(self, value, cs=0):
        """Best-effort ln for a code address (flat or 16:16)."""
        if value >= 0x10000:
            return self.lookup(f'%{value:08x}')
        if cs:
            return self.lookup(f'{cs:04x}:{value & 0xffff:04x}')
        return ''

    # --- per-thread detail ----------------------------------------------

    def detail_thread(self, t):
        self.status(f"  Detailing slot {t.slot:04x} ({t.name}, {t.sta})...")
        parts = []
        parts.append(self.cmd(f'.s {t.slot:x}'))
        # User-mode registers for the slot; fall back to plain r
        raw_r = self.cmd('.r')
        regs = KDBParser.parse_registers(raw_r)
        if not regs or not regs.eip:
            raw_r2 = self.cmd('r')
            parts.append(raw_r)
            raw_r = raw_r2
            regs = KDBParser.parse_registers(raw_r)
        parts.append(raw_r)
        t.regs = regs

        if regs and (regs.eip or regs.cs):
            t.eip_symbol = self.lookup_code_addr(regs.eip, regs.cs)

        # Stack: flat 32-bit vs tiled 16-bit heuristic
        n = self.args.stack_dwords
        if regs and regs.esp >= 0x10000:
            raw_stack = self.cmd(f'dd ss:esp L{n}')
            parts.append(raw_stack)
            candidates = []
            for _, value in KDBParser.extract_dwords(raw_stack):
                if 0x10000 <= value < 0xe0000000 and abs(value - regs.esp) > 0x10000:
                    candidates.append(value)
            seen = set()
            for value in candidates:
                if value in seen or len(t.stack_symbols) >= 10:
                    continue
                seen.add(value)
                sym = self.lookup_code_addr(value)
                if sym:
                    t.stack_symbols.append((value, sym))
        elif regs:
            # 16-bit stack: dump words, try (offset, segment) return pairs
            raw_stack = self.cmd(f'dw ss:sp L{n}')
            parts.append(raw_stack)
            words = []
            for line in raw_stack.split('\n'):
                for tok in re.findall(r'\b[0-9a-f]{4}\b', line, re.I)[1:]:
                    words.append(int(tok, 16))
            for i in range(len(words) - 1):
                off, seg = words[i], words[i + 1]
                # ring-3 LDT code selector heuristic
                if seg & 7 == 7 and seg > 0xff and len(t.stack_symbols) < 8:
                    sym = self.lookup(f'{seg:04x}:{off:04x}')
                    if sym:
                        t.stack_symbols.append(((seg << 16) | off, sym))

        t.raw_detail = '\n'.join(parts)

    # --- blockid analysis -------------------------------------------------

    def analyze_blockids(self, focus):
        """Dump each unique BlockID; decode KSEM ownership heuristically."""
        live_slots = set(self.threads.keys())
        block_ids = {}
        for t in focus:
            bid = t.block_id
            if not bid or bid < 0x10000:
                continue
            # Skip token-style BlockIDs that aren't memory addresses
            # (MuxWait/RamSem/ChildWait encode fffd:xxxx-style handles)
            if (bid >> 16) in PSEUDO_BID_HI:
                continue
            if t.block_type in ('muxwait', 'childwait', 'ramsem'):
                continue
            block_ids.setdefault(bid, []).append(t.slot)

        lines = []
        for bid, waiters in sorted(block_ids.items()):
            self.status(f"  Analyzing BlockID {bid:08x} "
                        f"({len(waiters)} waiter(s))...")
            raw = self.cmd(f'db %{bid:08x} L20')
            data = b''
            for dump in KDBParser.parse_memory_dump(raw):
                data += dump.data
            info = {'raw': raw, 'owner_candidates': [], 'note': ''}
            if data[:4] == b'KSEM':
                info['note'] = ('KSEM kernel semaphore signature found; '
                                'owner decode is heuristic')
                # Scan the words after the signature for values matching a
                # live slot number - layout varies by kernel build, so this
                # flags candidates rather than asserting an owner
                for off in range(4, min(len(data) - 1, 16), 2):
                    w = int.from_bytes(data[off:off + 2], 'little')
                    if w in live_slots and w not in waiters:
                        info['owner_candidates'].append((off, w))
            self.ksem_info[bid] = info

            lines.append(f"BlockID {bid:08x}  waiters: " +
                         ', '.join(f'{s:04x}({self.threads[s].name})'
                                   for s in waiters))
            if info['note']:
                lines.append(f"  {info['note']}")
            for off, w in info['owner_candidates']:
                owner = self.threads[w]
                lines.append(f"  owner-slot candidate (word @+{off}): "
                             f"{w:04x} = {owner.name} [{owner.sta}]")
            lines.append(raw.strip())
            lines.append('')
        self.sections.append(('BLOCKID ANALYSIS', '\n'.join(lines) or
                              '(no user-space BlockIDs among focus threads)'))
        return block_ids

    # --- summary ----------------------------------------------------------

    def pick_focus(self):
        """Order threads for the detail pass: focus regex first, then other
        blocked user threads, capped at --max-slots."""
        focus_re = re.compile(self.args.focus, re.I)
        user = [t for t in self.threads.values() if not t.is_system]
        primary = [t for t in user if focus_re.search(t.name)]
        secondary = [t for t in user if t not in primary and t.sta == 'blk']
        ordered = primary + secondary
        return ordered[:self.args.max_slots]

    def summarize(self, focus, block_ids):
        lines = []
        lines.append(f"Triage of {self.args.socket} at "
                     f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Threads: {len(self.threads)} total, "
                     f"{sum(1 for t in self.threads.values() if t.sta == 'blk')} blocked, "
                     f"{sum(1 for t in self.threads.values() if not t.is_system)} user")
        lines.append('')
        lines.append("Focus threads:")
        for t in focus:
            bid = f'{t.block_id:08x}' if t.block_id else '--------'
            wait = t.block_info or ''
            lines.append(f"  slot {t.slot:04x} pid {t.pid:04x} [{t.sta:4s}] "
                         f"{t.name:12s} BlockID={bid} {wait:24s} {t.eip_symbol}")
        lines.append('')

        # Contention: multiple waiters on one BlockID
        for bid, waiters in block_ids.items():
            if len(waiters) > 1:
                names = ', '.join(f'{self.threads[s].name}({s:04x})'
                                  for s in waiters)
                lines.append(f"CONTENTION: {len(waiters)} threads wait on "
                             f"BlockID {bid:08x}: {names}")

        # Suspects: non-blocked focus threads (spinners), then owner candidates
        spinners = [t for t in focus if t.sta not in ('blk', 'frz', 'sus')]
        for t in spinners:
            lines.append(f"SUSPECT (not blocked - possible spin/livelock): "
                         f"slot {t.slot:04x} {t.name} [{t.sta}] {t.eip_symbol}")
        for bid, info in self.ksem_info.items():
            for off, w in info['owner_candidates']:
                owner = self.threads[w]
                chain = f" -> itself waits on {owner.block_id:08x}" \
                    if owner.block_id else ''
                lines.append(f"SUSPECT (owner candidate of {bid:08x}): "
                             f"slot {w:04x} {owner.name} [{owner.sta}]{chain}")
        if not spinners and not any(i['owner_candidates']
                                    for i in self.ksem_info.values()):
            lines.append("No single suspect identified automatically - "
                         "see per-thread stacks below for the wait sites.")
        return '\n'.join(lines)

    # --- report -----------------------------------------------------------

    def write_report(self, summary, focus):
        with open(self.report_path, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("OS/2 HANG TRIAGE REPORT\n")
            f.write("=" * 70 + "\n\n")
            f.write("SUMMARY\n" + "-" * 70 + "\n")
            f.write(summary + "\n\n")

            f.write("PER-THREAD DETAIL\n" + "-" * 70 + "\n")
            for t in focus:
                f.write(f"\n### Slot {t.slot:04x}  {t.name}  pid={t.pid:04x} "
                        f"tid-ord={t.ord} state={t.sta}\n")
                if t.block_id:
                    f.write(f"    BlockID: {t.block_id:08x}  {t.block_info}\n")
                if t.eip_symbol:
                    f.write(f"    EIP: {t.eip_symbol}\n")
                if t.stack_symbols:
                    f.write("    Stack return addresses (nearest symbols):\n")
                    for value, sym in t.stack_symbols:
                        f.write(f"      {value:08x}  {sym}\n")
                f.write("    --- raw ---\n")
                for line in t.raw_detail.split('\n'):
                    f.write(f"    {line}\n")

            for title, text in self.sections:
                f.write("\n" + title + "\n" + "-" * 70 + "\n")
                f.write(text.rstrip() + "\n")
        self.status(f"\nReport written to {self.report_path}")

    # --- main flow ----------------------------------------------------------

    def run(self):
        if not self.break_in():
            self.status("ERROR: could not reach a debugger prompt. Is the "
                        "debug-kernel VM running with the serial pipe at "
                        f"{self.args.socket}?")
            return 1

        self.thread_census()
        if not self.threads:
            self.status("ERROR: could not parse any threads from .p* - "
                        "see /tmp/kdb_hang_session.log for raw output.")
            return 1
        self.block_info()

        focus = self.pick_focus()
        self.status(f"Detailing {len(focus)} thread(s)...")
        for t in focus:
            self.detail_thread(t)

        self.status("Analyzing block IDs...")
        block_ids = self.analyze_blockids(focus)

        if not self.args.no_modules:
            self.status("Capturing module list (.lm)...")
            self.sections.append(('MODULES (.lm)', self.cmd('.lm', timeout=90.0)))

        summary = self.summarize(focus, block_ids)
        print("\n" + "=" * 70)
        print(summary)
        print("=" * 70)
        self.write_report(summary, focus)

        if self.args.resume:
            self.status("Resuming the system (g)...")
            self.session.conn.send_raw(b'g\r\n')
        else:
            self.status("System left STOPPED at the debugger prompt. "
                        "Send 'g' via kdb_cmd.py to resume.")
        self.session.close()
        return 0


def main():
    parser = argparse.ArgumentParser(
        description='Triage a hung OS/2 system via the kernel debugger')
    parser.add_argument('--socket', default=DEFAULT_TARGET,
                        help=f'Debug target (default: {DEFAULT_TARGET})')
    parser.add_argument('--focus', default='pmshell|wps|xfldr',
                        help='Regex of thread names to prioritize')
    parser.add_argument('--max-slots', type=int, default=10,
                        help='Max threads to detail (default 10)')
    parser.add_argument('--stack-dwords', type=int, default=24,
                        help='Stack depth per thread (default 24)')
    parser.add_argument('--no-modules', action='store_true',
                        help='Skip the .lm module list')
    parser.add_argument('--resume', action='store_true',
                        help="Send 'g' when done (default: leave stopped)")
    parser.add_argument('--report', help='Report file path')
    args = parser.parse_args()

    triage = HangTriage(args)
    try:
        return triage.run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == '__main__':
    sys.exit(main())
