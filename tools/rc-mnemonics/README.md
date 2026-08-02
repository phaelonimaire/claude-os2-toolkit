# check-mnemonics.py - find dead menu mnemonics in an OS/2 `.RC`

```sh
./check-mnemonics.py myapp.rc                # every MENU in the file
./check-mnemonics.py myapp.rc IDR_MAINMENU   # one menu only
```

Exits non-zero when it finds a duplicate, so it can gate a build.

## Why this needs a tool

A duplicated `~` mnemonic is **not an error and not a cycle**. An alphabetic key
"selects the **first** menu item with the specified character as its mnemonic key"
[DOC-IBM - `pmv2base.txt`, menu keyboard behaviour], so the second item is simply unreachable from
the keyboard. Nothing warns:

- `wrc` compiles it happily - it is valid resource syntax.
- The compiler never sees menu text at all.
- The menu *renders correctly*, with both letters underlined.
- Mouse and accelerator both still work, so casual testing passes.

The only symptom is a keystroke that quietly activates the wrong item, and the risk peaks exactly
when a port reorganises a menu - a Windows `.RC` converted with a mechanical `&`->`~` sweep inherits
whatever letter assignment the original had, and Win32 *cycles* duplicates rather than ignoring
them, so the original was never wrong on its own platform.

Scope matters: the checker evaluates each `BEGIN`/`END` block separately, because PM resolves a
mnemonic within the menu currently open. Reusing a letter between different submenus is fine and is
not reported.

## Worked example

Converting Notepad2's Edit menu produced six duplicates at once, none of them visible in a
screenshot - including `Cu~t` versus `Insert HTML/XML ~Tag`, which only collided because a `Lines`
submenu had been added between them.

See `os2ref/resources-and-dialogs.md` section 2.1 and `recipes/porting-a-windows-app.md` section 7.
