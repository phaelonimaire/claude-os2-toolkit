# Porting a Windows application to OS/2 Presentation Manager

Everything here was established by actually doing it - porting Scintilla and Notepad2 dialog code
to PM, building on OS/2, and running the result. Claims are tagged `[DOC-IBM]` where IBM states
them and `[OBS-RE]` where they were established by observation.

---

## 0. Start from the right prior: PM is a Win32 *cousin*, not an alien

The instinct to treat OS/2 as maximally foreign is wrong for PM and will make you over-scope the
work. The architecture is the same shape end to end:

| Win32 | PM |
|---|---|
| `RegisterClass` | `WinRegisterClass` |
| `CreateWindowEx` | `WinCreateWindow` / `WinCreateStdWindow` |
| `GetMessage` / `DispatchMessage` | `WinGetMsg` / `WinDispatchMsg` |
| `DefWindowProc` / `DefDlgProc` | `WinDefWindowProc` / `WinDefDlgProc` |
| `SendMessage` / `PostMessage` | `WinSendMsg` / `WinPostMsg` |
| `WNDPROC` switching on `WM_*` | identical, with `MPARAM`/`MRESULT` |

Standard controls exist natively too - `WC_BUTTON`, `WC_ENTRYFIELD`, `WC_LISTBOX`, `WC_COMBOBOX`,
`WC_MLE`, `WC_STATIC`, `WC_SCROLLBAR`, `WC_CONTAINER`, `WC_NOTEBOOK`, `WC_SLIDER`, `WC_VALUESET`
(`os2ref/pm-controls.md`).

**Before telling anyone a Windows concept has no OS/2 analogue, grep
`os2ref/pm-window-messaging.md` and `os2ref/pm-controls.md`.** It usually does.

A measured example: Notepad2's `Dialogs.c` (2,348 lines) uses 13 distinct Win32 dialog APIs; 12 map
one-to-one and the corpus documented all of them. The work is systematic renaming plus a few
helpers - *not* a rewrite.

---

## 1. The dialog mapping

| Win32 | PM | Note |
|---|---|---|
| `GetDlgItem` | `WinWindowFromID` | |
| `SendDlgItemMessage` | `WinSendDlgItemMsg` | |
| `SetDlgItemText` / `GetDlgItemText` | `WinSetDlgItemText` / `WinQueryDlgItemText` | |
| `SetDlgItemInt` | `WinSetDlgItemShort` | **`SHORT`, not `int`** |
| `GetDlgItemInt(&fTranslated)` | `WinQueryDlgItemShort` | the `BOOL` return **is** `fTranslated` |
| `CheckDlgButton` | `WinCheckButton` | |
| `IsDlgButtonChecked` | `WinQueryButtonCheckstate` | |
| `EnableWindow` | `WinEnableWindow` | |
| `ShowWindow` | `WinShowWindow` | |
| `EndDialog` | `WinDismissDlg` | |
| `DialogBoxParam` | `WinDlgBox` | |
| `CreateDialogParam` (modeless) | `WinLoadDlg` + `WinShowWindow` | **no `IsDialogMessage` needed - section 2.10** |
| `&` mnemonic in control text | `~` | **buttons and menus only - section 2.11** |
| `MessageBox` | `WinMessageBox` | |
| `MessageBeep` | `WinAlarm` | |
| `LoadIcon` / `LoadImage` | `WinLoadPointer` | |
| `LoadString` | `WinLoadString` | |
| `GetFocus` | `WinQueryFocus` | takes `HWND_DESKTOP` |
| `Get/SetWindowLongPtr` | `WinQuery/SetWindowPtr`, `...ULong` | window words, sized by `cbWindowData` |
| `DeferWindowPos` ... `EndDeferWindowPos` | `WinSetMultWindowPos` | one `SWP` array |
| `IDOK` / `IDCANCEL` | `DID_OK` (1) / `DID_CANCEL` (2) | |
| `WM_INITDIALOG` | `WM_INITDLG` (`0x003b`) | **return value is inverted - section 2** |
| `LOWORD(wParam)` | `SHORT1FROMMP(mp1)` | |
| `EM_LIMITTEXT` | `EM_SETTEXTLIMIT` (`0x0143`) | |

**No direct analogue - write a helper:**

- **`CheckRadioButton(hDlg, first, last, check)`** - PM checks buttons individually; loop the id
  range calling `WinCheckButton`.
- **`SetProp` / `GetProp`** - PM has no window-property atom table. Use window words
  (`cbWindowData` in `WinRegisterClass` + `WinSetWindowPtr`).
- **`PostMessage(WM_NEXTDLGCTL)`** - no such message; call `WinSetFocus` on the control directly.
- **`CenterWindow`** - do the arithmetic in bottom-left space throughout (see section 2, origin).
- **`CreateEvent`/`SetEvent`** - `DosCreateEventSem`/`DosPostEventSem`
  (`os2ref/ipc-synchronization.md`).
- **Theming/visual-styles calls** - no equivalent; make them no-ops.

---

## 2. The silent differences - these cost the most time

Every item here **compiles cleanly and fails invisibly**. None is catchable by checking prototypes
against a header, which is why they are listed separately from the mapping table.

### 2.1 `WM_INITDLG`'s return is inverted [DOC-IBM]

PM's return is a *focus-set indicator*: `TRUE` = "I set the focus myself", `FALSE` = "PM, set the
default". Win32's `WM_INITDIALOG` is the opposite. A mechanically-ported `return TRUE;` leaves **no
control focused**, so the dialog renders perfectly and ignores the keyboard entirely.

*Tell:* the dialog's title bar stays in the **inactive** colour while its owner's stays active.
Full detail: `os2ref/resources-and-dialogs.md` section 5.

### 2.2 The origin is bottom-left, y grows upward [DOC-IBM]

Inverted from Win32/X11, everywhere: window positions, mouse coordinates, drawing, dialog units.
Given a height `H`, `yBottom = H - rc.bottom`, `yTop = H - rc.top`. Both systems use half-open
intervals on their own increasing axis, so **no +/-1 correction is needed** - do not add one.

Note *which* height: a drawing surface flips against its own client height, a **window position
flips against its parent's** height. `os2ref/gpi-drawing.md` section "Coordinate origin".

### 2.3 A `RECTL` includes left/bottom, excludes right/top [DOC-IBM]

The same *shape* of rule as Win32's `RECT` (left/top inclusive), reflected through the flipped
axis. Width is `xRight - xLeft`, height `yTop - yBottom`, no correction.

### 2.4 `SWP`'s field order is not its argument order [DOC-IBM]

`WinSetWindowPos(x, y, cx, cy)` but `SWP { fl; cy; cx; y; x; ... }` - height before width, y before
x. A positional initialiser silently swaps both pairs. Assign by field name.

### 2.5 A presentation space starts in colour-INDEX mode [DOC-IBM]

`GpiSetColor`/`WinFillRect` take a palette *index*, so an RGB value is out of range and the
primitive **draws nothing**. Call
`GpiCreateLogColorTable(hps, LCOL_RESET, LCOLF_RGB, 0, 0, NULL)` after obtaining **every** PS.

*Tell:* coloured primitives vanish while raw-pel drawing (`GpiDrawBits`, `GpiBitBlt`) still works.

### 2.6 There are three independent code pages [DOC-IBM]

Process (`DosSetProcessCp`), message queue (`WinSetCp` - the code page text is *delivered* in), and
GPI (`GpiSetCp` - the one text is *drawn* in). Setting one does not set the others, and resource
code pages should match the queue's. `os2ref/unicode-conversion.md` section 9.1.

### 2.7 A control MUST pass keys it does not use to `WinDefWindowProc` [DOC-IBM]

If a child control handles `WM_CHAR` and returns `FALSE` for keys it does not want, **the frame's
menu mnemonics stop working**: the menu pulls down and then ignores every keystroke, and the letter
you pressed appears in the document instead.

This is a documented contract, not a quirk. `WM_CHAR` "is sent by controls to their owner window if
they do not process the key stroke themselves" [DOC-IBM - `pm3.txt`, *WM_CHAR (in Frame Controls)*],
and the mechanism is the default procedure: "The default window procedure **sends the message to the
owner window if it exists**" [DOC-IBM - `pm3.txt`, *WM_CHAR Default Processing*]. Returning `FALSE`
from your own window procedure never reaches `WinDefWindowProc`, so the forwarding never happens.

**Rule: consume a key only when you actually used it; otherwise fall through to
`WinDefWindowProc`.** Win32 tolerates sloppiness here because `TranslateAccelerator` sits in the
application's own message loop; PM routes through the owner chain instead.

Related trap: **Ctrl+letter arrives as `KC_CHAR` carrying the ASCII control code 1-26, not the
letter.** A handler that only inspects printable characters never sees `Ctrl+C`; recover it with
`'A' + (ch - 1)`.

### 2.7a Ship the traditional OS/2 editing keys, not just the Windows ones

OS/2's CUA bindings are **Ctrl+Insert = copy, Shift+Insert = paste, Shift+Delete = cut** - IBM
documents them for entry fields and MLEs [DOC-IBM - `pmv2base.txt`]. Users expect them; a port that
only wires Ctrl+C/V/X will feel wrong. Provide both, in an `ACCELTABLE` (form per IBM's own example
in `pmv2base.txt`, "Creating an Accelerator-Table Resource"):

```rc
ACCELTABLE IDD_MAIN
BEGIN
    "c",       IDM_COPY,  CHAR, CONTROL          /* the Windows-style set */
    "v",       IDM_PASTE, CHAR, CONTROL
    "x",       IDM_CUT,   CHAR, CONTROL
    VK_INSERT, IDM_COPY,  VIRTUALKEY, CONTROL    /* the traditional OS/2 set */
    VK_INSERT, IDM_PASTE, VIRTUALKEY, SHIFT
    VK_DELETE, IDM_CUT,   VIRTUALKEY, SHIFT
END
```

Add `FCF_ACCELTABLE` to the frame flags so `WinCreateStdWindow` loads the table whose id matches the
window id. Accelerators are processed by the frame before the focus window sees the key, which makes
them work regardless of what the focused control does with `WM_CHAR` - but they are *not* a
substitute for section 2.7; menu mnemonics still need the forwarding.

### 2.8 An OS/2 "INI file" is not a Windows INI file [DOC-IBM]

Same name, unrelated thing. A Windows `.ini` is a text file of `[Section]` / `key=value` lines that
any parser can read. An OS/2 profile is an **opaque binary database managed by PM**, reachable only
through the `Prf*` API - `PrfOpenProfile`, `PrfQueryProfileData`/`String`,
`PrfWriteProfileData`/`String`, with `HINI_USERPROFILE` (`OS2.INI`) and `HINI_SYSTEMPROFILE`
(`OS2SYS.INI`) always open [DOC-IBM - `os2ref/profiles-ini.md`].

**This matters only if you are touching a system profile.** Be precise about which case you are in:

| Your app... | Do |
|---|---|
| reads/writes **its own** config file (the usual `GetPrivateProfileString` case) | **Nothing.** It is your file. Keep the text format and the parser you already have, on ordinary file I/O. Converting it to a `Prf*` profile is a rewrite the platform does not ask for. |
| stores into **`OS2.INI` / `OS2SYS.INI`**, or wants a genuine OS/2 profile | Use `Prf*`. There is no alternative - the file is an opaque PM-managed database. |

Do not read or write a *system* profile directly: writing it as text corrupts it, reading it as
text finds nothing.

If you do end up using `Prf*`, two properties are worth knowing - values are **arbitrary binary up
to 64 KB** (a settings struct stores whole, no flattening to text), and application/key names match
**case-dependently**, unlike Windows INI lookups, so carried-over keys can silently miss.

> **Scope discipline.** This is the general case, not a special one: change what the platform
> *forces* you to change. An idiomatic rewrite of working, portable code is how a port turns into a
> rewrite, and every line you rewrite is a line that can newly break. "It would be more OS/2-ish" is
> not a reason on its own.

### 2.9 Handles are all the same type

`HAB`, `HPS`, `HDC`, `HWND`, `HMQ`, `HBITMAP` are all `typedef LHANDLE` (`unsigned long`). Passing
one where another belongs compiles fine and fails at run time as "nothing happened."

### 2.10 A modeless dialog needs no `IsDialogMessage` - but it does need `WinShowWindow`

In Win32, a modeless dialog works only because the message loop calls `IsDialogMessage` first; the
classic bug is a dialog that renders but ignores Tab and Enter. **PM's message loop needs no such
call** - the dialog is an ordinary window in the queue, and `WinDefDlgProc` supplies tabbing, the
default button and Esc-cancels once `WinDispatchMsg` delivers to it. Porting the loop is a
*deletion*, not a translation.

The trap moves elsewhere. `WinLoadDlg` creates the dialog **invisible** unless the template says
`WS_VISIBLE`, so the follow-up `WinShowWindow(hwndDlg, TRUE)` is load-bearing: omit it and the
dialog "never opens" even though every control in it was created and the dialog procedure ran.
And `WinDismissDlg` **hides without destroying**, so a Find dialog that "switches" to Replace by
reusing its handle leaks a window per toggle - destroy and reload instead. [DOC-IBM -
`os2ref/resources-and-dialogs.md` section 4; OBS-RE - Notepad2's Find/Replace dialog.]

### 2.11 `~` is a mnemonic in buttons and menus - and literal text in a label

Win32's `&` works in statics, and the mnemonic moves focus to the next control in the tab order.
PM's `~` does **not** work in `LTEXT`/`CTEXT`: `SS_TEXT` honours only the justification and
`DT_WORDBREAK` flags - not `DT_MNEMONIC` - and a static's `WM_MATCHMNEMONIC` always answers FALSE
[DOC-IBM - `pm3.txt` "Static Control Styles"]. So a mechanical `&`->`~` sweep leaves a label
reading `Search strin~g:` on screen. This one at least fails *visibly*, which makes it cheap -
provided you look at the dialog. It is invisible to the compiler and to `wrc`.

Either drop the tilde from labels, or take IBM's own suggestion in that section and use a
`BS_NOBORDER` button as the label. Checkboxes, push buttons and menu items all honour `~` normally.

Where they *do* work, check them as a **set**: a duplicated mnemonic silently gives the key to the
first item that claims it, so the second is simply dead [DOC-IBM - `pmv2base.txt`]. Nothing in the
toolchain warns, and the risk is highest exactly when a port reorganises a menu. Run
`tools/rc-mnemonics/check-mnemonics.py <file>.rc` after every menu edit - it exits non-zero on a
duplicate, so it can gate the build. Converting one Notepad2 menu produced six at once.

#### And `\n` is literal in a static too, but not in a message box [OBS-RE]

The same "the bytes are the text" rule applies to line breaks. A `WC_STATIC` draws `\n` as a
**glyph** and runs the text on in one line - so a multi-line string that looks right in a Win32
dialog comes out as one long line peppered with rubbish. **`WinMessageBox` does honour `\n`**, and
word-wraps as well, so the same string laid out correctly there.

Practical consequence when porting: a multi-line notice belongs in `WinMessageBox`, or in a
`WC_MLE` if it has to live in a dialog you built. Do not hand-align columns with spaces either -
the message box wraps to its own width and the alignment is lost.

### 2.12 The dialog *procedure* ports; the notification *routing* moves

`WM_COMMAND` in PM carries menu and push-button commands only. Everything a control tells its owner
- a Win32 `EN_CHANGE`, `CBN_SELCHANGE`, `LBN_SELCHANGE` arriving as `WM_COMMAND` with the code in
the high word - arrives in PM as a separate **`WM_CONTROL`**, with `SHORT1FROMMP(mp1)` the control
id and `SHORT2FROMMP(mp1)` the notification code. A ported `case IDC_FOO:` that expected a change
notification inside `WM_COMMAND` compiles, runs, and is never reached; the dialog simply feels
inert in one place. Move those cases to `WM_CONTROL` when converting, and check for them
deliberately - the OK/Cancel path keeps working, so nothing obvious breaks.

**Then be careful what you read out of `mp2`.** Win32 hands you a typed `NMHDR*` in `WM_NOTIFY`;
PM's `WM_CONTROL` gives you one message for every notification a control has, and each code decides
what `mp2` is - a structure pointer for one, a window handle for another, nothing for a third.
Dispatch on `SHORT2FROMMP(mp1)` *before* dereferencing. Getting this wrong faults rather than
returning nonsense, because a handle is a small integer and therefore a wild pointer, and it hides
until the notification you did not test for actually fires.

---

## 3. Type traps

- **`PSZ`, `PCH`, `BYTE` are conditionally `unsigned char`-based** depending on
  `OS2EMX_PLAIN_CHAR`. `const_cast<PCH>(s)` fails under one configuration; use
  `reinterpret_cast`. This hits every string-taking API.
- **`BOOL` is `unsigned long`**, not `int`.
- **`MPARAM`/`MRESULT` are `VOID *`** - always use the `MPFROM*` / `*FROMMP` macros; hand-rolled
  shifts get sign extension wrong on negative coordinates.

Full table and rules: `c-guide.md` section 0.5.

---

## 4. Building

```sh
# On the OS/2 box (GCC/kLIBC). -Zomf links through emxomfld, which defaults to a
# non-existent ilink.exe when the toolchain came from the netlabs/Arca RPMs:
export EMXOMFLD_TYPE=wlink
export EMXOMFLD_LINKER=wl.exe

wrc -r -i=C:/usr/include app.rc      # wrc does NOT inherit the compiler include path
gcc -Zomf -O2 app.c app.def -o app.exe
wrc app.res app.exe                  # bind resources
```

**Use `CONTROL` with an explicit `WC_*` class** for combo boxes, list boxes, containers and
notebooks. `wrc` targets Windows *and* OS/2, and a bare `COMBOBOX` statement compiles clean but
yields a template PM rejects at `WinDlgBox` time with `DID_ERROR` / `PMERR_INVALID_HWND` (0x1001).
Text and button shorthands (`LTEXT`, `CTEXT`, `ENTRYFIELD`, `PUSHBUTTON`, `DEFPUSHBUTTON`) are fine.

**Combo-box driving:** PM's `WC_COMBOBOX` is an entry field plus a list box and "accepts the `EM_*`
and `LM_*` messages of its parts" - so `CB_ADDSTRING`->`LM_INSERTITEM`, `CB_SETCURSEL`->
`LM_SELECTITEM`, `CB_GETCURSEL`->`LM_QUERYSELECTION`. `CB_SETEXTENDEDUI` has no equivalent; drop it.

`.RC` differences from a Windows resource script: `~` marks mnemonics (not `&`); `DLGTEMPLATE`
wraps an inner `DIALOG` statement; the slot before the frame flags is empty but required; dialog
coordinates are bottom-left. Verified example: `os2ref/resources-and-dialogs.md` section 2.1.

C++ works - GCC 9.2 on OS/2 handles C++11/14/17. Check what is installed with **`rpm -qa`**, not
`command -v` (which misses names containing `+`) and not `yum` (which needs live repo metadata).

---

## 5. Verification - compiling proves almost nothing

Every serious bug in this port compiled cleanly at `-Wall`. Budget for interaction testing, not
just building. What actually caught things:

1. **Render a test pattern with labelled expectations**, e.g. a red bar captioned "MUST BE AT TOP"
   and a 50%-red wash captioned "must look PINK". Orientation and byte-order bugs are obvious in a
   screenshot and invisible in a log.
2. **Drive real input.** The `WM_INITDLG` inversion is undetectable until something types into the
   dialog. Under VirtualBox, `VBoxManage controlvm <vm> keyboardputstring` /
   `keyboardputscancode` and `screenshotpng` automate this.
3. **Let asserts fire.** Implement `Platform::Assert`-style hooks to report and stop. A stub that
   leaves an object *uninitialised* gets caught precisely by the framework's own assertion; a stub
   that returns a plausible half-made object crashes somewhere innocent later.
4. **Read the failure's shape.** When only the code paths that bypass a subsystem work, the
   subsystem's state is the bug - that is how section 2.5 was diagnosed from a single screenshot.
5. **Put a number in the title bar.** A PM app has no console, so the cheapest instrument is
   `WinSetWindowText` on the frame: print the value you are reasoning about and read it off a
   screenshot. Three times in this port a plausible theory was wrong and one such number settled it
   in a single rebuild - a "why is only one match marked?" that turned out to be a selection five
   characters long instead of four, and a lexer that reported id `0` after being set to `3`.
   **Guessing costs a rebuild; measuring costs the same rebuild and is conclusive.** Delete the
   instrument afterwards, and delete any fix you added on a theory that measurement then disproved -
   an unnecessary guard left in "just in case" becomes folklore that the next reader has to disprove
   again.

### 5.0 A widget library's platform layer has *contracts*, not just entry points

Porting a library's platform layer means implementing an interface, and an interface is more than a
list of functions to fill in: some of them tell you something back, and ignoring the answer produces
bugs that look like they belong to entirely different subsystems.

The clearest example from this port: Scintilla's `Editor::Paint` can set
`paintState = paintAbandoned`, meaning *"the rectangle you gave me was not enough - repaint."* The
OS/2 layer reset the flag and returned. Everything outside the original update rectangle then kept
its previous contents, so replacing the document left the **first line correct and the rest of the
screen showing the old file**. That reads as a file-loading bug, and it is a painting one.

When filling in a platform interface, read what each entry point is allowed to *report* - a return
value, a state flag, a "call me again" - and handle it. Grep the reference implementation for the
flag you are ignoring; the platform layers that ship with the library are the specification.

### 5.1 A vendored library's build-time feature macros

If the port includes a third-party library, check what its features are *compile-guarded* on before
concluding one is broken. Scintilla gates all lexer support behind `#ifdef SCI_LEXER` in
`ScintillaBase.cxx`. Built without it, this port compiled and linked **106 lexer object files** plus
the lexer catalogue, accepted `SCI_SETLEXER` with a clean return, and highlighted nothing - every
file rendered in the default style with no diagnostic at any layer. There is no link error because
nothing is missing; the message handler simply is not compiled in.

The general shape: **a missing `-D` produces a subsystem that is present, linked, addressable, and
inert.** That is invisible to every check short of asking the library what it thinks its state is
(`SCI_GETLEXER` returned `0`). When a whole feature does nothing and the plumbing all looks right,
read the library's build documentation before reading your own code again. [OBS-RE]

---

## 6. Suggested order

1. **Build a trivial PM window first** (`scaffolds/hello-pm`) - proves toolchain, VM, and run loop.
2. **Compile one `.RC`** with a menu and a dialog and bind it - proves the resource path before
   thousands of lines depend on it.
3. **Port the drawing/platform layer**, if the app has one, and verify it with a labelled render
   test before wiring the rest.
4. **Port one representative dialog end to end** - including keyboard interaction - before
   converting the rest in bulk. One dialog surfaces the inversions that would otherwise be
   replicated across all of them.
5. **Then convert in bulk**, which by that point is mechanical.

---

## 7. What OS/2 does not have

Everything above maps. This section is the part that does **not**, so that a port stops looking for
an equivalent and makes a design decision instead. Nothing here is a gap in this kit's coverage -
these are absences in the platform.

### 7.1 OS/2 has exactly one seat

This is the single most useful fact for scoping a Win32 port, and no API reference states it,
because it is an assumption rather than a function. **The OS/2 desktop is always one person's.**
IBM LAN Server and HPFS386 carry multi-user *permissions* for file sharing, and multi-user add-ons
exist, but there is no interactive multi-user model, no per-user desktop, and no notion of "the
current user" distinct from "the machine".

A whole class of Win32 API therefore collapses to **not applicable** rather than to some OS/2
counterpart you have not found yet:

| Win32 | Status on OS/2 |
|---|---|
| `GetTokenInformation`, `OpenProcessToken`, privilege and elevation checks | N/A - no token model, no "run as" |
| `SHGetFolderPath(CSIDL_APPDATA / CSIDL_PERSONAL)` and per-user profile paths | N/A - no per-user application-data directory. Put the app's file beside the `.EXE` or behind an environment variable; ArcaOS *may* define some, do not rely on it |
| Per-user registry hives (`HKEY_CURRENT_USER` vs `HKEY_LOCAL_MACHINE`) | N/A - `OS2.INI` is the machine's, full stop (see `os2ref/profiles-ini.md`) |
| Roaming/user state, per-user "recent documents" | N/A |

The failure mode this prevents is real: a model reasoning from Win32 priors keeps searching for the
per-user path API, finds nothing, and reports "I could not determine the OS/2 equivalent" - when the
correct answer is that the question does not arise. [Confirmed by the kit's author.]

### 7.2 Absent, with the design decision each forces

| Win32 | OS/2 | What to do instead |
|---|---|---|
| `ChooseColor` | **No standard colour dialog.** `WinFileDlg` and `WinFontDlg` are the only two common dialogs in `os2emx.h` | Build one, or drop the feature |
| `FindFirstChangeNotification` family | **No file/directory change notification at any layer.** `*Notif*` across all of `/usr/include` yields only `WinSetVisibleRegionNotify` | Poll `DosQueryPathInfo` timestamps |
| `SHAutoComplete` | **No alternative.** | Hand-roll, or omit |
| `Shell_NotifyIcon`, `SHAppBarMessage` (tray) | **Not in the base system.** WarpCenter has no system tray; XWorkplace's taskbar does | An add-on dependency, not a platform feature - decide deliberately |
| `IsTextUnicode` | **No detection.** Conversion *is* covered - see 7.3 | Hand-write the heuristic |
| `GetMonitorInfo`, `MonitorFromRect` | **No app-level multi-monitor query.** The complete `QSV_*` set (31 entries) has no display geometry; multi-monitor exists only at the GRADD driver layer | Use the desktop: `WinQuerySysValue(HWND_DESKTOP, SV_CXSCREEN/SV_CYSCREEN)`. In practice these calls are almost always clamping a window to the work area, and one desktop answers that completely - the only difference is that `SV_CXSCREEN` is the full screen where Win32's `rcWork` excludes the taskbar |
| `CreateStatusWindow`, toolbar, rebar, `ImageList_*`, progress bar | **Not window classes.** The full `WC_*` set is 24 classes and contains none of them | Compose from `WC_STATIC` / owner-drawn buttons. `ImageList` has no analogue because `WC_CONTAINER` records carry `HPOINTER` icons directly |
| `GetLongPathName` / `GetShortPathName` | N/A - no 8.3/long-name duality on HPFS/JFS | Drop |
| `shlwapi` `Path*` helpers (`PathCanonicalize`, `PathRelativePathTo`, `PathMatchSpec`, `PathCompactPathEx`, ...) | No equivalent library | Hand-write. `DosQueryPathInfo`, `DosSearchPath`, `DosScanEnv` cover the parts that touch the filesystem |

`ListView_*` and `TreeView_*` are **not** on this list: `WC_CONTAINER` with `CV_ICON` / `CV_TREE` /
`CV_DETAIL` covers both.

### 7.2a Read what the original does with the API before you replace it

An absent API is not the same size as the feature built on it, and the gap is usually in your
favour. Before designing a replacement, read the calls: often the Win32 API is doing less work than
its name suggests.

**File change notification is the worked example.** OS/2 has none, at any layer - the one entry in
the table above with no route at all - so "the feature must poll" reads like a rewrite. It is not,
because **the Win32 original already polls.** Notepad2 runs a `SetTimer` tick, and
`FindFirstChangeNotification` only tells it that *something in the directory* moved; whether the
open file actually changed is decided by re-reading its timestamp and size and comparing them.
Win32 supplies a cheap gate in front of a comparison that works perfectly well without it. Deleting
the gate is the whole port:

| Win32 | OS/2 |
|---|---|
| `SetTimer(NULL, id, ms, proc)` | `WinStartTimer(hab, hwnd, id, ms)` + a `WM_TIMER` case |
| `FindFirstFile` -> `ftLastWriteTime` | `DosQueryPathInfo(FIL_STANDARD)` -> `FILESTATUS3` |
| `CompareFileTime`, `nFileSizeLow` | `fdateLastWrite` / `ftimeLastWrite` / `cbFile` |
| `PathFileExists` | `DosQueryPathInfo` returning `NO_ERROR` |
| `GetTickCount` | `WinGetCurrentTime(hab)` |
| `SetForegroundWindow` | `WinSetActiveWindow(HWND_DESKTOP, hwndFrame)` |

`FDATE` and `FTIME` are bitfield structs, so they compare with `memcmp`, not an operator - that is
the `CompareFileTime` equivalent. The cost is one `DosQueryPathInfo` per tick against **one file**,
not per file in the directory, which at the two-second interval the original itself uses is not
measurable.

Two details worth carrying across rather than reinventing, because both are load-bearing:

- **Keep the settle delay.** A program writing a large file is observed mid-write, and reloading
  immediately shows a truncated document. Hold the reload until the timestamp and size stop moving,
  and restart that clock on every further change - that is what makes auto-reload usable on a log
  file rather than a source of garbage.
- **Re-stamp on every path out**, including the one where the user declines to reload. Miss it and
  the same change is reported on every tick forever.

The general form: when the platform is missing an API, the question is not "how do I rebuild this
API" but "what did the caller actually need from it". Compare against section 7.3, where the trap runs the
other way - assuming absence that is not there.

### 7.3 Present, but easy to wrongly assume absent

Three that a Win32 porter tends to write off, and should not:

- **Unicode.** OS/2 ships `UCONV.DLL` with a full UCS-2 API - conversion, collation (`UniStrcoll`,
  `UniStrxfrm`), case mapping, and locale objects. See `os2ref/unicode-conversion.md`. Only
  *detection* is missing.
- **The shell namespace.** `IShellFolder`-style enumeration is `_wpQueryContent(somSelf, prev,
  QC_FIRST/QC_NEXT)`; per-file icons are `WinLoadFileIcon` / `WinFreeFileIcon`, whose `fPrivate`
  flag is the shared-vs-owned caching control. See `os2ref/wps-classes.md`.
- **Printing.** Fully covered by `DevOpenDC` + the `DevEscape` document/page brackets +
  `DevPostDeviceModes` for job properties. See `os2ref/printing-spooler.md`.

Each of those was *initially* reported as "no known equivalent" during the Notepad2 port, by a
session that had checked the headers but not this kit. That is the failure mode
`os2-app-dev-guide.md` section 3 describes, in its most expensive form: **grep this kit before concluding
a platform lacks something**, and see `sources.md` for the local mirrors to search after it.
