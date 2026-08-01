#!/usr/bin/env python3
"""check-rc-ids.py - catch the two .RC mistakes that nothing else reports.

Neither failure below produces a diagnostic from wrc, the compiler, or the
linker, because in both cases every individual file is internally consistent.
They surface as a dialog that will not open, or a menu item that fires the
wrong command, on a machine you may not be sitting at.

1. A dialog the code loads but the .RC does not define.

   `WinLoadDlg(..., IDD_FIND, ...)` compiles as long as IDD_FIND is #defined -
   the compiler sees an integer and has no idea a resource is meant. If the
   DLGTEMPLATE is missing the link still succeeds, and the failure appears at
   run time as WinLoadDlg returning NULLHANDLE with WinGetLastError = 0x8100A
   (PMERR_RESOURCE_NOT_FOUND). This is easy to cause by rewriting a .RC as a
   whole file: nothing anywhere notices a template that was not carried across.

2. Two identifiers sharing one numeric value.

   A .RC is a flat list of numbers. Two menu items with the same id put the same
   value in WM_COMMAND, so one of them silently runs the other's code; a menu id
   colliding with a submenu anchor is the same bug. Ids for genuinely different
   namespaces - a DLGTEMPLATE id vs a command id - may legitimately coincide, so
   those are reported separately as warnings rather than errors.

    ./check-rc-ids.py np2.h np2.rc *.c        # both checks
    ./check-rc-ids.py np2.h np2.rc            # ids only, no source scan

Exits 1 if any error is found, so it can gate a build.
"""
import re
import sys
from collections import defaultdict

# #define IDD_FIND  521   (decimal or hex, trailing comment allowed)
DEFINE = re.compile(r'^\s*#\s*define\s+(ID[A-Z]*_[A-Za-z0-9_]+)\s+(0[xX][0-9a-fA-F]+|\d+)\s*(?:/\*|//|$)')
# DLGTEMPLATE IDD_FIND        /  DLGTEMPLATE 521
TEMPLATE = re.compile(r'^\s*DLGTEMPLATE\s+(\S+)')
# the calls that take a dialog resource id
LOADER = re.compile(r'\b(WinLoadDlg|WinDlgBox)\s*\(')


def defines(path):
    """{name: value} for every ID*_ macro in a header."""
    out = {}
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            m = DEFINE.match(line)
            if m:
                out[m.group(1)] = int(m.group(2), 0)
    return out


def templates(path):
    """The set of names/numbers given a DLGTEMPLATE in the .RC."""
    out = set()
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            m = TEMPLATE.match(line)
            if m:
                out.add(m.group(1))
    return out


def loaded_dialogs(paths):
    """{id_name: [file:line]} for each dialog id handed to WinLoadDlg/WinDlgBox.

    The id is the argument before the dialog procedure - conventionally the 4th
    of WinLoadDlg and the 5th of WinDlgBox - but rather than count commas across
    line breaks and macros, take any ID*_ token inside the call. Over-reporting
    a name that is defined AND has a template costs nothing, since only ids with
    no template are ever mentioned.
    """
    out = defaultdict(list)
    for path in paths:
        with open(path, encoding='utf-8', errors='replace') as fh:
            text = fh.read()
        for m in LOADER.finditer(text):
            # walk to the matching close paren so multi-line calls are covered
            depth, i = 0, m.end() - 1
            while i < len(text):
                if text[i] == '(':
                    depth += 1
                elif text[i] == ')':
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            call = text[m.end():i]
            line = text.count('\n', 0, m.start()) + 1
            for name in re.findall(r'\bID[A-Z]*_[A-Za-z0-9_]+', call):
                out[name].append('%s:%d' % (path, line))
    return out


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    header, rc, sources = argv[1], argv[2], argv[3:]

    ids = defines(header)
    tpls = templates(rc)
    errors = warnings = 0

    # ---- 1. dialogs loaded but never defined as a resource --------------------
    for name, sites in sorted(loaded_dialogs(sources).items()):
        if not name.startswith('IDD_'):
            continue          # a control id passed through the call, not a dialog
        if name in tpls:
            continue
        if name in ids and str(ids[name]) in tpls:
            continue          # template written with the literal number
        if name not in ids:
            print('ERROR: %s is loaded but not #defined' % name)
        else:
            print('ERROR: no DLGTEMPLATE for %s (= %d), loaded at %s'
                  % (name, ids[name], ', '.join(sites)))
        errors += 1

    # ---- 2. two identifiers sharing one value --------------------------------
    by_value = defaultdict(list)
    for name, value in ids.items():
        by_value[value].append(name)

    for value in sorted(by_value):
        names = sorted(by_value[value])
        if len(names) < 2:
            continue
        prefixes = {n.split('_')[0] for n in names}
        if len(prefixes) == 1:
            print('ERROR: %d is used by %s' % (value, ' and '.join(names)))
            errors += 1
        else:
            print('warning: %d is shared across namespaces by %s'
                  % (value, ' and '.join(names)))
            warnings += 1

    total = len(tpls)
    print('%d dialog template(s), %d id(s), %d error(s), %d warning(s)'
          % (total, len(ids), errors, warnings))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
