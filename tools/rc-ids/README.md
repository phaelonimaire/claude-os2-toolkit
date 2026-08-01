# check-rc-ids.py — find missing dialog templates and colliding ids in an OS/2 `.RC`

```sh
./check-rc-ids.py myapp.h myapp.rc *.c   # both checks
./check-rc-ids.py myapp.h myapp.rc       # id collisions only
```

Exits non-zero when it finds an error, so it can gate a build.

## Why this needs a tool

Both failures below are invisible to every stage of the build, because each individual file is
internally consistent. A `.RC` is a flat list of numbers, and the compiler never learns that any of
those numbers is supposed to name a resource.

### A dialog the code loads but the `.RC` does not define

`WinLoadDlg(..., IDD_FIND, ...)` compiles as long as `IDD_FIND` is `#define`d — to the compiler it
is an integer. `wrc` compiles a `.RC` with no `DLGTEMPLATE IDD_FIND` just as happily, because
nothing in the `.RC` refers to it either. The link succeeds. The only symptom is at run time:

```
WinLoadDlg returns NULLHANDLE, WinGetLastError = 0x8100A   (PMERR_RESOURCE_NOT_FOUND)
```

and only if you check — which is the argument for always reporting `WinGetLastError` when
`WinLoadDlg` fails, rather than returning silently.

The usual cause is **rewriting a `.RC` as a whole file**. There is no link step that notices a
template which was not carried across, so anything dropped simply vanishes. Prefer targeted edits,
and count your templates afterwards.

### Two identifiers sharing one numeric value

Two menu items with the same id put the same value in `WM_COMMAND`, so one silently runs the other's
code. A command id colliding with a `SUBMENU` anchor is the same bug. Nothing warns, and it is easy
to cause by picking "the next free number" by eye in a header several hundred lines long.

Ids belonging to genuinely different namespaces — a `DLGTEMPLATE` id and a command id, or a dialog
control id and a menu id — may legitimately share a value, since they are resolved by different
lookups. Those are reported as **warnings**; a collision between two ids with the same prefix is an
**error**.

## Worked example

Run against the Notepad2 port at the commit before the bug was found:

```
ERROR: no DLGTEMPLATE for IDD_FIND (= 521), loaded at np2find.c:691
ERROR: no DLGTEMPLATE for IDD_REPLACE (= 522), loaded at np2find.c:691
warning: 100 is shared across namespaces by IDC_COLUMNWRAP and IDM_FILE
ERROR: 400 is used by IDM_RELOAD_UTF8 and IDM_SEARCH
warning: 550 is shared across namespaces by IDD_STYLECONFIG and IDM_HELP
```

The two missing templates had been dropped by a whole-file rewrite of the `.RC` that added ten other
dialogs. Find and Replace had worked for several sessions before that and were never re-tested, so
the regression sat unnoticed until someone pressed the Find button. `IDM_RELOAD_UTF8` sharing `400`
with the `IDM_SEARCH` submenu anchor was a second live bug found in the same pass.

See `os2ref/resources-and-dialogs.md` and the sibling `tools/rc-mnemonics/`.
