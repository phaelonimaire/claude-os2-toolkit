# Build hello-pm-menu

A PM application with a **menu**, a **modal dialog**, an **accelerator table** and a
**string table** — i.e. the first program shape that needs a resource script. Full flag
detail: `../../recipes/build-pm-app.md`; the resource formats: `../../os2ref/resources-and-dialogs.md`.

**GCC/kLIBC (on the OS/2 VM):**
```sh
# -Zomf links through emxomfld, which defaults to IBM's ilink.exe. If your toolchain
# came from the netlabs/Arca RPMs you have Watcom's linker as wl.exe and no ilink:
export EMXOMFLD_TYPE=wlink
export EMXOMFLD_LINKER=wl.exe

# wrc does NOT inherit the compiler's include path; -i= is required for <os2.h>
wrc -r -i=C:/usr/include menu.rc        # menu.rc -> menu.res
gcc -Zomf -O2 menu.c menu.def -o menu.exe
wrc menu.res menu.exe                   # bind the resources into the .exe
```

**OpenWatcom (cross-building on Linux):**
```sh
export WATCOM=/path/to/watcom PATH=$WATCOM/binl:$PATH
export INCLUDE="$WATCOM/h;$WATCOM/h/os2"
wrc -r -i=$WATCOM/h/os2 menu.rc
wcl386 -bt=os2 -l=os2v2_pm menu.c -fe=menu.exe
wrc menu.res menu.exe
```

Run it on an OS/2 target (`../../recipes/setup-test-vm.md`): a window with File and Edit
menus. **File / Set Number…** opens the dialog; **Ctrl+Ins** and **Shift+Ins** (and
Ctrl+C / Ctrl+V) drive the accelerators.

## What this scaffold exists to get right

Four things that compile cleanly and fail *silently* if you carry a Win32 habit over.
Each is commented at its site in the source.

1. **`WM_INITDLG` returns the opposite of `WM_INITDIALOG`.** PM's return is a *focus-set
   indicator*: `TRUE` means "I already set the focus", `FALSE` means "PM, set the
   default". A ported `return TRUE;` leaves no control focused — the dialog renders
   perfectly and ignores the keyboard. Tell: the dialog's title bar stays in the
   *inactive* colour while its owner's stays active.

2. **Unhandled keys must reach `WinDefWindowProc`.** Its documented `WM_CHAR` behaviour
   is to send the message to the *owner* window, and that forwarding is how the frame
   ever sees a menu mnemonic. `return MRFROMLONG(FALSE)` short-circuits it and the menu
   bar goes inert.

3. **`wrc` does not inherit the compiler's include path** — `#include <os2.h>` fails with
   `E062` without `-i=`. And for anything past text and buttons (combo boxes, list boxes,
   containers, notebooks) prefer `CONTROL` with an explicit `WC_*` class: `wrc` compiles
   resources for Windows *and* OS/2, and the bare shorthand can yield a template PM
   rejects at `WinDlgBox` time with `PMERR_INVALID_HWND`.

4. **Coordinates are bottom-left origin, y upward** — in the window *and* in dialog
   units. The OK button at `y=10` is near the *bottom* of a 62-unit dialog.

Ship **both** accelerator conventions: the traditional OS/2 CUA keys
(`Ctrl+Ins` copy, `Shift+Ins` paste, `Shift+Del` cut) alongside `Ctrl+C`/`V`/`X`.
Users expect the OS/2 ones.
