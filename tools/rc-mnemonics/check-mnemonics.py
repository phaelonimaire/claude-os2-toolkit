#!/usr/bin/env python3
"""check-mnemonics.py - find duplicate '~' mnemonics in an OS/2 .RC menu.

A duplicated mnemonic is not an error and not a cycle: an alphabetic key
"selects the FIRST menu item with the specified character as its mnemonic key"
[DOC-IBM - pmv2base.txt, menu keyboard behaviour], so the second item is simply
unreachable from the keyboard. Neither wrc nor the compiler warns, and the risk
peaks exactly when a port reorganises a menu or adds a submenu.

Checks each BEGIN/END scope separately, which is the right granularity: PM
resolves a mnemonic within the menu currently open, so the same letter may be
reused freely between different submenus.

    ./check-mnemonics.py np2.rc                # every MENU in the file
    ./check-mnemonics.py np2.rc IDD_NP2MAIN    # just one

Exits 1 if any duplicate is found, so it can gate a build.
"""
import re
import sys


def scopes(lines, menu_id=None):
    """Yield {mnemonic: [labels]} for each BEGIN/END scope inside a MENU."""
    stack = []
    in_menu = False
    for raw in lines:
        t = raw.strip()

        m = re.match(r'MENU\s+(\S+)', t)
        if m and not t.startswith('SUBMENU'):
            in_menu = (menu_id is None or m.group(1) == menu_id)
            continue
        if not in_menu:
            continue

        if t == 'BEGIN':
            stack.append({})
            continue
        if t == 'END':
            if stack:
                yield stack.pop()
            if not stack:
                in_menu = False
            continue

        m = re.match(r'(?:MENUITEM|SUBMENU)\s+"([^"]*)"', t)
        if m and stack:
            mn = re.search(r'~(.)', m.group(1))
            if mn:
                stack[-1].setdefault(mn.group(1).lower(), []).append(m.group(1))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    menu_id = sys.argv[2] if len(sys.argv) > 2 else None

    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.read().split('\n')

    bad = 0
    for scope in scopes(lines, menu_id):
        for key, labels in sorted(scope.items()):
            if len(labels) > 1:
                bad += 1
                print("duplicate mnemonic '%s':" % key)
                for lab in labels:
                    print("    %s" % lab)

    if bad:
        print("\n%d duplicate mnemonic(s). The second item in each pair is dead." % bad)
        return 1
    print("no duplicate mnemonics")
    return 0


if __name__ == '__main__':
    sys.exit(main())
