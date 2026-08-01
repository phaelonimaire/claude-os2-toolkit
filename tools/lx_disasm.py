#!/usr/bin/env python3
"""
lx_disasm.py - Symbol-annotated disassembly of OS/2 LX objects.

Static-RE starter kit. Reconstructs an LX object's in-memory image, disassembles
a VA range with ndisasm at the object's true bitness (from the LX BIG flag, NOT
the .SYM), and annotates with symbol labels resolved from the companion .SYM
file.

Usage:
    lx_disasm.py LXIMAGE [OBJECT:OFFSET] [--sym SYMFILE] [selector] [options]

  selector (pick one):
    OBJECT:OFFSET       positional; the form C:\\POPUPLOG.OS2 reports a fault in
    --sym-name NAME     disassemble starting at the symbol NAME (needs --sym)
    --va 0xADDR         disassemble starting at flat VA
    --obj N             disassemble (the start of) object N

  options:
    --sym SYMFILE       companion .SYM; optional - without it you get addresses
                        but no symbol labels
    --count N           number of instructions (default 64)
    --bytes N           disassemble N bytes instead of an instruction count
    --bits {16,32}      override bitness (default: from LX object BIG flag)

Examples:
    # triage a POPUPLOG.OS2 fault at "object 1, offset 0001a2b4" - no .SYM needed
    lx_disasm.py your.exe 1:0001a2b4 --count 20

    # with symbols, for labelled output
    lx_disasm.py /path/to/OS2/DLL/DOSCALL1.DLL --sym /path/to/doscall1.sym \\
                 --sym-name DOS32SEARCHPATH --count 40
"""
import argparse
import bisect
import os
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sym2map import LXImage, SymFile


def build_symbol_index(sf, lx):
    """Return sorted (va, name) list and the va->name dict, resolved via LX."""
    sf.resolve(lx)
    items = []
    for seg in sf.segments:
        for s in seg.symbols:
            if s.va is not None:
                items.append((s.va, s.name))
    items.sort()
    return items


def name_for(items, vas, va):
    """Nearest symbol at or below va -> 'name' or 'name+0xN'."""
    i = bisect.bisect_right(vas, va) - 1
    if i < 0:
        return None
    base_va, nm = items[i]
    d = va - base_va
    return nm if d == 0 else "%s+0x%x" % (nm, d)


def ndisasm(code, base, bits):
    if not shutil.which("ndisasm"):
        sys.exit("ndisasm not found (apt install nasm)")
    # ndisasm -o sets the origin so addresses print as flat VAs
    p = subprocess.run(
        ["ndisasm", "-b", str(bits), "-o", "0x%x" % base, "/dev/stdin"],
        input=code, capture_output=True)
    return p.stdout.decode("latin1")


def parse_location(spec):
    """'object:offset' (as POPUPLOG.OS2 prints it) -> (objnum, offset).

    POPUPLOG writes the offset as bare, zero-padded HEX ("0001a2b4"), so the
    offset is parsed base-16 by default; an explicit 0x prefix is also accepted.
    Parsing it base-10 would silently disassemble the wrong address, which is
    worse than rejecting it. The object number is decimal, as printed.

    Returns None if spec isn't in that form.
    """
    if ":" not in spec:
        return None
    obj_s, off_s = spec.split(":", 1)
    off_s = off_s.strip()
    try:
        # base 16 accepts both "1a2b4" and "0x1a2b4".
        return int(obj_s, 10), int(off_s, 16)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(
        description="Symbol-annotated disassembly of OS/2 LX objects. "
                    "A .SYM file is optional; without one you get addresses "
                    "but no symbol labels.")
    ap.add_argument("lximage")
    ap.add_argument("location", nargs="?",
                    help="start location as OBJECT:OFFSET, exactly as "
                         "C:\\POPUPLOG.OS2 reports a fault (e.g. 1:0001a2b4). "
                         "Alternative to --sym-name/--va/--obj.")
    ap.add_argument("--sym", help="companion .SYM file (optional; enables labels)")
    ap.add_argument("--sym-name")
    ap.add_argument("--va")
    ap.add_argument("--obj", type=int)
    ap.add_argument("--count", type=int, default=64)
    ap.add_argument("--bytes", type=int)
    ap.add_argument("--bits", type=int, choices=[16, 32])
    args = ap.parse_args()

    try:
        lx = LXImage(args.lximage)
    except (OSError, ValueError) as e:
        sys.exit("%s: %s" % (args.lximage, e))
    if args.sym:
        try:
            sf = SymFile(args.sym)
            items = build_symbol_index(sf, lx)
        except (OSError, ValueError) as e:
            sys.exit("%s: %s" % (args.sym, e))
    else:
        items = []
    vas = [v for v, _ in items]

    # Resolve the start VA + which object it lives in.
    start_va = None
    if args.location:
        loc = parse_location(args.location)
        if loc is None:
            sys.exit("bad location %r: expected OBJECT:OFFSET, e.g. 1:0001a2b4"
                     % args.location)
        objnum, off = loc
        o = lx.object_by_num(objnum)
        if o is None:
            sys.exit("no object %d in %s" % (objnum, args.lximage))
        start_va = o.base + off
    elif args.sym_name:
        if not items:
            sys.exit("--sym-name needs a symbol file: pass --sym FILE.SYM "
                     "(or use OBJECT:OFFSET / --va / --obj instead)")
        target = args.sym_name.lower()
        hits = [(v, n) for v, n in items if n.lower() == target]
        if not hits:
            # substring fallback
            hits = [(v, n) for v, n in items if target in n.lower()]
        if not hits:
            sys.exit("symbol not found: %s" % args.sym_name)
        if len(hits) > 1:
            print("; %d matches for %r, using first:" % (len(hits), args.sym_name))
            for v, n in hits[:8]:
                print(";   %08x  %s" % (v, n))
        start_va = hits[0][0]
    elif args.va:
        start_va = int(args.va, 0)
    elif args.obj is not None:
        o = lx.object_by_num(args.obj)
        if o is None:
            sys.exit("no object %d in %s" % (args.obj, args.lximage))
        start_va = o.base
    else:
        sys.exit("pick a start: OBJECT:OFFSET, --va, --obj, or --sym-name")

    # Find the object containing start_va.
    obj = None
    for o in lx.objects:
        if o.base <= start_va < o.base + o.vsize:
            obj = o
            break
    if obj is None:
        sys.exit("VA 0x%x not in any object" % start_va)

    bits = args.bits or (32 if obj.is_32bit else 16)
    image = lx.object_bytes(obj.num)
    start_off = start_va - obj.base

    # start_va can be inside the object's *virtual* size but past the bytes the
    # file actually backs (BSS-like tail). Stop honestly instead of feeding
    # ndisasm an empty buffer and printing nothing.
    if start_off >= len(image):
        sys.exit("VA 0x%x is at object %d offset 0x%x, past its %d bytes of "
                 "file-backed image (uninitialized tail — nothing to disassemble)"
                 % (start_va, obj.num, start_off, len(image)))

    # Decide how many bytes to feed ndisasm.
    if args.bytes is not None:
        nbytes = args.bytes
    else:
        nbytes = args.count * 8 + 16
    nbytes = min(nbytes, len(image) - start_off)
    chunk = image[start_off:start_off + nbytes]

    sname = name_for(items, vas, start_va)
    print("; image: %s  object %d (%s)  base=%08x  %s %s"
          % (os.path.basename(args.lximage), obj.num,
             "USE32" if obj.is_32bit else "USE16",
             obj.base, obj.perm(), obj.kind()))
    print("; start: %08x  %s   (%d-bit disasm)" % (start_va, sname or "?", bits))
    print(";" + "-" * 70)

    raw = ndisasm(chunk, start_va, bits)
    emitted = 0
    last_label = sname
    for line in raw.splitlines():
        # ndisasm line: "ADDR  HEX  MNEMONIC"
        parts = line.split(None, 1)
        if not parts:
            continue
        try:
            addr = int(parts[0], 16)
        except ValueError:
            continue
        lbl = name_for(items, vas, addr)
        # print a label header whenever we cross into a new symbol
        if lbl and lbl != last_label and "+" not in lbl:
            print("\n%s:" % lbl)
            last_label = lbl
        print(line)
        emitted += 1
        if not args.bytes and emitted >= args.count:
            break


if __name__ == "__main__":
    main()
