# OS/2 Workplace Shell — Object Classes and Programming

The **Workplace Shell** (WPS) is OS/2's object-oriented desktop. Everything a user manipulates
on the desktop — folders, program references, data files, disk drives, shadows, the desktop
itself — is a **Workplace object**: a live instance of a C++-like class whose behaviour is
defined by *methods* and whose data survives reboots. The class machinery is not built into the
Workplace Shell; it is **SOM**, IBM's System Object Model — a language-neutral, binary object
runtime with single-rooted inheritance, metaclasses, and release-to-release binary
compatibility. The Workplace Shell is a large library of SOM classes rooted at `SOMObject`, and
a developer extends the desktop by writing a **SOM subclass** of an existing WPS class, compiling
it into a DLL, and registering that DLL with the shell.

This reference documents the WPS object model as a programming interface: the class hierarchy and
its three *storage* base classes; the `WPObject` programming model (instance data and the
`somSelf`/`somThis` convention, the method-dispatch macros, initialization, persistence, titles,
setup strings, context menus, the Settings notebook, drag/drop); and the class
registration/replacement API (`WinRegisterObjectClass`, `WinReplaceObjectClass`,
`WinCreateObject`) together with how a subclass is built with the SOM compiler. It documents a
*representative* set of `wp*` methods — the ones that define the model — not the full method
catalog of several hundred methods.

Provenance: **[DOC-IBM]** the OS/2 Toolkit Workplace headers — `pmwp.h` (the object-management
`Win*` API, `PAGEINFO`, `OBJCLASS`) and `wpobject.h` (the `WPObject` method declarations, method
tokens, dispatch macros, and constants), plus the class headers `wpabs.h`, `wpfsys.h`,
`wptrans.h`, `wpfolder.h`, `wpdataf.h`, `wppgm.h`, `wppgmf.h`, `wpshadow.h`, `wpdisk.h` (each fact
cited `file:line`); **[DOC-IBM]** the IBM *Workplace Shell Programming Reference* and *Programming
Guide* (extracted book text `wps1.txt`/`wps2.txt`/`wps3.txt`/`wpsguide.txt`) for method
*semantics* and the class model. Where a behavioural claim is stated only by a book it is cited to
that book; where a value or prototype is stated only by a header it is cited `file:line`. Facts a
source did not establish are marked `[unverified]`.

---

## 1. The object model: Workplace Shell classes on SOM [DOC-IBM]

All Workplace Shell classes descend from a single root, `WPObject`, which in turn descends from
the SOM root class `SOMObject` — "all SOM classes must be descended from `SOMObject`"
[DOC-IBM `wps1.txt`]. `WPObject` "is the fundamental class from which all Workplace objects are
derived, regardless of where they are actually stored" [DOC-IBM `wps1.txt`, WPObject class
description]. A Workplace object of class `WPObject` itself cannot be created; `WPObject` exists
only to define behaviour common to every desktop object.

Every SOM class also has a **metaclass** — a class whose *instances are classes*. A WPS class
`Foo` has a metaclass conventionally named `M_Foo` (`M_WPObject`, `M_WPAbstract`, …). Instance
methods, prefixed `wp`, act on an object; **class methods**, prefixed `wpcls`, act on the class
object (the single shared object representing the class) and are defined on the metaclass. So
`wpQueryTitle` returns *this object's* title, while `wpclsQueryTitle` returns the *default* title
for the whole class [DOC-IBM `wps2.txt`, wpQueryTitle — Usage].

Two constraints distinguish WPS classes from ordinary SOM classes: WPS classes are defined in
SOM's Object Interface Definition Language and built with the SOM compiler, and "applications
cannot call Workplace Shell methods" — the shell invokes the methods, on its own threads, in
response to user actions [DOC-IBM `wpsguide.txt`, "All Workplace Shell classes are derived from …
WPObject"]. A program participates by *subclassing and overriding*, not by calling `wp*` methods
directly.

### The three storage classes

The immediate descendants of `WPObject` are the **storage classes**: they "take responsibility
for storing the object information, typically in a persistent form" [DOC-IBM `wps1.txt`]. There
are three, and the choice of storage class is the first design decision for any new object
[DOC-IBM `wpsguide.txt`, storage-class table]:

| Storage class | Header | Where instance data lives | Persistent? |
|---|---|---|---|
| `WPAbstract` | `wpabs.h` | The user profile `OS2.INI` (object has a numeric handle, no file name) | Yes |
| `WPFileSystem` | `wpfsys.h` | The Extended Attributes (EAs) of a real file or directory | Yes |
| `WPTransient` | `wptrans.h` | Not saved — exists only while the system runs | No |

- **`WPAbstract`** is "the abstract object storage class … any object class derived from
  `WPAbstract` will have persistent storage for its instance variables in the INI file … An
  abstract object does not have a file name, just a numeric handle" [DOC-IBM `wps1.txt`]. It backs
  objects that are real desktop entities but not files (a printer, a program reference, a color
  palette).
- **`WPFileSystem`** is "the storage class that represents all file-system objects including
  directory (folder), data file, executable file, and root directory (drive) objects … Persistent
  data for instances of `WPFileSystem` subclasses are stored in the Extended Attributes (EAs) of
  the file or directory" [DOC-IBM `wps1.txt`].
- **`WPTransient`** stores nothing across shutdown; it backs objects that represent a transient
  runtime entity (a running program's window entry, a spooler job) [DOC-IBM `wpsguide.txt`].

None of `WPObject`, `WPAbstract`, `WPFileSystem`, `WPTransient` can be instantiated directly —
"these classes are provided as base classes which define common characteristics and behaviors for
descendant classes" [DOC-IBM `wpsguide.txt`].

---

## 2. The class hierarchy [DOC-IBM]

The concrete, user-visible classes are subclasses of the storage classes. Each class header
`#include`s exactly its parent's header, which fixes the hierarchy unambiguously:

```
SOMObject                                     (SOM root)
└── WPObject                                  wpobject.h   — root Workplace class
    ├── WPAbstract        wpabs.h  (→ wpobject.h)          — INI-backed
    │   ├── WPProgram     wppgm.h  (→ wpabs.h)             — a program reference
    │   ├── WPShadow      wpshadow.h (→ wpabs.h)           — a link/alias to another object
    │   ├── WPDisk        wpdisk.h (→ wpabs.h)             — a disk-drive object
    │   ├── WPPalette, WPPrinter, WPClock, …               (many more)
    ├── WPFileSystem      wpfsys.h (→ wpobject.h)          — EA-backed, real files
    │   ├── WPFolder      wpfolder.h (→ wpfsys.h)          — a directory
    │   │   ├── WPDesktop  wpdesk.h                        — the desktop (one instance, made by the system)
    │   │   └── WPRootFolder, WPDrives, …
    │   ├── WPDataFile    wpdataf.h (→ wpfsys.h)           — a data file
    │   │   └── WPProgramFile  wppgmf.h (→ wpdataf.h)      — an executable file
    └── WPTransient       wptrans.h (→ wpobject.h)         — not persisted
        └── WPJob, WPShadow-of-transient, …
```

Parent-chain evidence (each header pulls in its parent) [DOC-IBM]:
`wpabs.h`, `wpfsys.h`, `wptrans.h` all `#include <wpobject.h>`; `wpfolder.h` and `wpdataf.h`
`#include <wpfsys.h>`; `wppgm.h`, `wpshadow.h`, `wpdisk.h` `#include <wpabs.h>`; `wppgmf.h`
`#include <wpdataf.h>`.

Selected concrete classes [DOC-IBM `wps1.txt` class descriptions]:

| Class | Parent | Represents |
|---|---|---|
| `WPFolder` | `WPFileSystem` | A directory shown as a container of objects |
| `WPDesktop` | `WPFolder` | The desktop itself — "the Workplace desktop object class"; one instance is created by the system, titled "Desktop" |
| `WPDataFile` | `WPFileSystem` | A generic data file; the default class for any file with no more specific association |
| `WPProgramFile` | `WPDataFile` | An executable file (`.EXE`/`.COM`/`.CMD`) with launch metadata |
| `WPProgram` | `WPAbstract` | A *program reference* — a launchable pointer to an executable plus parameters/working dir, stored in `OS2.INI` |
| `WPShadow` | `WPAbstract` | A shadow (alias): a persistent reference that reroutes operations to the object it links to |
| `WPDisk` | `WPAbstract` | A disk-drive object (the drive icon in the Drives folder) |

Because `WPDataFile` is the fallback file-system class and `WPProgram`/`WPProgramFile` handle
launching, a new class for a document type is almost always a subclass of `WPDataFile`, and a new
non-file desktop widget is a subclass of `WPAbstract`.

---

## 3. The `WPObject` programming model [DOC-IBM]

### Instance data, `somSelf`, and `somThis`

Each object carries a block of **instance data** — the C struct of the class's instance
variables, allocated and zero-filled by SOM when the object is created. Every method receives the
object pointer as its first parameter, `somSelf` (typed as a pointer to the class, e.g.
`WPObject *somSelf`) [DOC-IBM `wpobject.h`, every `somTP_WPObject_*` prototype begins
`WPObject *somSelf`]. Inside a method body, the SOM compiler's generated `<Class>GetData(somSelf)`
macro yields a `somThis` pointer to *this class's* slice of the instance data, and the generated
`_<var>` accessors read/write individual instance variables through `somThis`:

```c
SOM_Scope void SOMLINK myf_wpInitData(MYFILE *somSelf)
{
    MYFILEData *somThis = MYFILEGetData(somSelf);   /* this class's instance vars   */
    parent_wpInitData(somSelf);                     /* ALWAYS call the parent first */
    /* ... initialize _myVar fields via somThis ... */
}
```

(pattern from [DOC-IBM `wps2.txt`, wpInitData — Example Code]). Instance variables are declared
in the class's IDL `implementation` block (see §11); a subclass never touches an ancestor class's
private instance data, only its own.

### Method dispatch: the `_wpMethod` macros

A method is invoked through a generated macro that resolves the method token at run time and
calls through SOM's dispatch, giving virtual (overridable) behaviour. `wpobject.h` defines, for
each instance method, both a fully-qualified form `WPObject_wpX` and the short form `_wpX`:

```c
#define WPObject_wpQueryTitle(somSelf) \
    (SOM_Resolve(somSelf, WPObject, wpQueryTitle)(somSelf))
    ...
#define _wpQueryTitle WPObject_wpQueryTitle
```

[DOC-IBM `wpobject.h:2471`, `:2479`]. So `_wpQueryTitle(somSelf)` in source expands to a
`SOM_Resolve`-dispatched call; overriding the method in a subclass changes what that call reaches
for every object of the subclass. The method *tokens* themselves are declared as `somMToken`
fields of the class-data structure — e.g. `wpInitData`, `wpSaveState`, `wpQueryTitle`,
`wpSetTitle`, `wpModifyPopupMenu`, `wpDrop`, `wpDragOver`, `wpAddSettingsPages`, `wpSetup` all
appear together as tokens in `wpobject.h` [DOC-IBM `wpobject.h:884-945`].

### Life-cycle: creation, awakening, and `wpInitData`

`wpInitData` "is called to allow the object to initialize its instance data" [DOC-IBM
`wps2.txt`, wpInitData — Syntax]:

```c
void wpInitData(WPObject *somSelf);   /* wpobject.h:1887 */
```

It runs "when the object is created or when it is awakened from the dormant state … By default,
memory allocated to instance variables is zerofilled." Critically, it runs "before the object's
state is known, so it is very important that the object does not try to process any other method
while processing this method" — extra initialization that needs other methods belongs in
`wpRestoreState`, and one-time-only setup belongs in `wpSetupOnce`. "The parent method must be
called before any processing is done by your overriding method." Any class with instance variables
overrides `wpInitData`, and if it does, it should also override `wpUnInitData` to free what it
allocated [DOC-IBM `wps2.txt`, wpInitData — Remarks / How to Override].

The distinction *created vs. awakened* is central: a persistent object exists on disk (INI or EA)
whether or not it is loaded. When first referenced it is **awakened** (SOM object reconstructed,
`wpInitData` then `wpRestoreState` run); when no longer needed it is made **dormant** (state saved,
SOM object freed) [DOC-IBM `wps2.txt`, wpInitData / wpSaveState — Usage].

---

## 4. Persistence: `wpSaveState` / `wpRestoreState` [DOC-IBM]

An object makes its instance data persistent by overriding a matched pair — `wpSaveState` to write
and `wpRestoreState` to read — and calling the storage-class-provided *save*/*restore* helpers
inside them. Overriding one without the other is a defect: "An override of the `wpSaveState`
method is a prerequisite if persistent instance data is desired" [DOC-IBM `wps2.txt`,
wpRestoreState — How to Override].

```c
BOOL wpSaveState(WPObject *somSelf);                     /* wpobject.h:2813 */
BOOL wpRestoreState(WPObject *somSelf, ULONG ulReserved);/* wpobject.h:2681; ulReserved must be 0 */
```

- `wpSaveState` "is called to allow the object to save its state"; it is invoked by the system
  during `wpClose` or `wpSaveImmediate` (deferred saving via `wpSaveDeferred` is preferred over an
  immediate save) [DOC-IBM `wps2.txt`, wpSaveState — Syntax / Usage].
- `wpRestoreState` "restores the state of the object which was saved during the processing of the
  `wpSaveState` method"; it is invoked by the system while processing `wpInitData` (i.e. at
  awaken time) [DOC-IBM `wps2.txt`, wpRestoreState — Syntax / Usage].

The body of each is a series of key-tagged save/restore calls. The storage class provides three
typed pairs [DOC-IBM `wps2.txt`, wpSaveState/wpRestoreState — Related Methods]:

| Save | Restore | Prototype (save form) | Purpose |
|---|---|---|---|
| `wpSaveLong` | `wpRestoreLong` | `BOOL wpSaveLong(WPObject*, PSZ pszClass, ULONG ulKey, ULONG ulValue)` [`wpobject.h:2790`] | one `ULONG` under a (class-name, key) pair |
| `wpSaveString` | `wpRestoreString` | `BOOL wpSaveString(WPObject*, PSZ pszClass, ULONG ulKey, PSZ pszValue)` [`wpobject.h:2833`] | a `\0`-terminated string |
| `wpSaveData` | `wpRestoreData` | (binary blob) | an arbitrary byte block |

The restore forms take an output buffer, e.g.
`BOOL wpRestoreLong(WPObject*, PSZ pszClass, ULONG ulKey, PULONG pulValue)` [`wpobject.h:2658`] and
`BOOL wpRestoreString(WPObject*, PSZ pszClass, ULONG ulKey, PSZ pszValue, PULONG pcbValue)`
[`wpobject.h:2702`]. The `pszClass`/`ulKey` pair namespaces each datum so a subclass cannot collide
with an ancestor's saved keys. The storage medium (INI vs. EA) is chosen by the object's storage
class, transparently — a `WPAbstract` subclass's `wpSaveLong` lands in `OS2.INI`, a `WPFileSystem`
subclass's lands in the file's EAs. Each returns a `BOOL` success flag.

Typical shape (condensed from [DOC-IBM `wps2.txt`, wpSaveState — Example Code]):

```c
SOM_Scope BOOL SOMLINK myf_wpSaveState(MYFILE *somSelf) {
    MYFILEData *somThis = MYFILEGetData(somSelf);
    _wpSaveString(somSelf, "MyClass", KEY_TITLE, _title);
    _wpSaveLong  (somSelf, "MyClass", KEY_FLAGS, _flags);
    return parent_wpSaveState(somSelf);      /* let ancestors save their slices too */
}
```

---

## 5. Titles: `wpQueryTitle` / `wpSetTitle` [DOC-IBM]

Every object has a **title** (the text under its icon). It is read and written through methods,
never stored directly:

```c
PSZ  wpQueryTitle(WPObject *somSelf);            /* wpobject.h:2466 */
BOOL wpSetTitle  (WPObject *somSelf, PSZ pszNewTitle); /* wpobject.h:3113 */
```

"The object's title may be altered by the user at any time. Objects should always use this method
to access the current title and never store the string pointer that is returned" [DOC-IBM
`wps2.txt`, wpQueryTitle — Remarks]. `wpQueryTitle` is generally *not* overridden. To obtain the
default title of the *class* (as used when a fresh instance is created), the metaclass method
`wpclsQueryTitle` is used instead — `PSZ wpclsQueryTitle(M_WPObject *somSelf)`
[DOC-IBM `wpobject.h:4163`; `wps2.txt`, wpQueryTitle — Usage].

---

## 6. Setup strings: `wpSetup` and object configuration [DOC-IBM]

A **setup string** is the text-based mechanism for configuring an object at creation time (or
later). `wpSetup` "is called to allow the newly created object to initialize itself based on an
input setup string" [DOC-IBM `wps2.txt`, wpSetup — Syntax]:

```c
BOOL wpSetup(WPObject *somSelf, PSZ pszSetupString);   /* wpobject.h:3134 */
```

The string is a semicolon-separated list of `keyname=value` pairs:

```
"KEY=value;KEY2=value1,value2;"
```

"Each object class documents the keynames and the parameters it expects … all parameters have safe
defaults, so it is never required to pass parameters." A literal semicolon inside a value is
escaped `^;`. If `wpSetup` returns `FALSE`, "the creation of the object is terminated." The system
calls `wpSetup` during `wpclsNew`/`wpSetupOnce`, and during the public API `WinCreateObject` and
`WinSetObjectData` (§10). A class introducing its own keynames overrides `wpSetup`, parses its keys
(the helper `wpScanSetupString` extracts one), and calls the parent for the rest [DOC-IBM
`wps2.txt`, wpSetup — Remarks / Usage / How to Override].

> Note on querying setup state: the inverse operation — asking an object to *emit* its current
> configuration as a setup string — is provided in later OS/2 releases as `wpQuerySetup`. It is
> not declared in this Toolkit's `wpobject.h`, so its prototype is `[unverified]` here.

---

## 7. Context (pop-up) menus [DOC-IBM]

An object's context menu is assembled by a cooperating pair of overrides, and item selection is
handled by a third:

```c
ULONG wpFilterPopupMenu(WPObject*, ULONG ulFlags, HWND hwndCnr, BOOL fMultiSelect); /* wpobject.h:1734 */
BOOL  wpModifyPopupMenu(WPObject*, HWND hwndMenu, HWND hwndCnr, ULONG iPosition);   /* wpobject.h:2022 */
BOOL  wpMenuItemSelected(WPObject*, HWND hwndFrame, ULONG ulMenuId);               /* wpobject.h:2000 */
```

- **`wpFilterPopupMenu`** returns a bit mask of which *standard* menu items to keep. The available
  standard items are the `CTXT_*` flags (two DWORDs' worth): `CTXT_OPEN` (`0x0002`),
  `CTXT_SETTINGS`/`CTXT_PROPERTIES` (`0x0010`), `CTXT_PRINT` (`0x0020`), `CTXT_DELETE` (`0x0080`),
  `CTXT_COPY` (`0x0100`), `CTXT_MOVE` (`0x0200`), `CTXT_SHADOW`/`CTXT_LINK` (`0x0400`), and many
  more [DOC-IBM `wpobject.h:126-198`]. A subclass ANDs out items it does not want.
- **`wpModifyPopupMenu`** "should be overridden in order to add class-specific actions to the
  object's pop-up menu" — it is called by the system right after `wpFilterPopupMenu`, and typically
  calls `wpInsertPopupMenuItems` to append the subclass's own items, then calls the parent
  [DOC-IBM `wps2.txt`, wpModifyPopupMenu — Remarks / How to Override / Example].
- **`wpMenuItemSelected`** is dispatched when the user picks an item; the override switches on
  `ulMenuId`, handles its own IDs, and calls the parent in the `default` case [DOC-IBM `wps2.txt`,
  wpMenuItemSelected — Example].

Menu-ID discipline: standard shell items use the reserved `WPMENUID_*` values
(`WPMENUID_OPEN`=1, `WPMENUID_HELP`=2, `WPMENUID_PRINT`=3, …) [DOC-IBM `wpobject.h:230-234`], and
"class-specific menu IDs should be above `WPMENUID_USER`" (`0x6500`) so a subclass never collides
with the shell's or an ancestor's IDs [DOC-IBM `wpobject.h:230`; `wps2.txt`, wpMenuItemSelected /
wpModifyPopupMenu — Remarks].

---

## 8. The Settings notebook: `wpAddSettingsPages` [DOC-IBM]

An object's **Settings notebook** (its property sheet) is populated by overriding
`wpAddSettingsPages`, and each page is inserted with `wpInsertSettingsPage`:

```c
BOOL  wpAddSettingsPages (WPObject*, HWND hwndNotebook);                 /* wpobject.h:1167 */
ULONG wpInsertSettingsPage(WPObject*, HWND hwndNotebook, PPAGEINFO ppageinfo); /* wpobject.h:1957 */
```

`wpAddSettingsPages` "is always overridden in order to add pages to or remove pages from the
Settings notebook." To add a page the override fills a `PAGEINFO` and calls `wpInsertSettingsPage`;
to *remove* an inherited page, the override that added it is overridden to return
`SETTINGS_PAGE_REMOVED` (`-1`) without calling its parent [DOC-IBM `wps2.txt`, wpAddSettingsPages —
How to Override; `wpobject.h:722` (`SETTINGS_PAGE_REMOVED`)]. **Ordering is controlled by when the
parent is called:** call the parent *first* to place the subclass's pages above the ancestors'
pages; call it *last* to place them below [DOC-IBM `wps2.txt`, wpAddSettingsPages — How to
Override].

Each page is described by a `PAGEINFO` [DOC-IBM `pmwp.h:203-222`]:

```c
typedef struct _PAGEINFO {
    ULONG   cb;                 /* structure size                         */
    HWND    hwndPage;           /* page window (or 0 if created from resid)*/
    PFNWP   pfnwp;              /* the page's dialog procedure            */
    ULONG   resid;              /* dialog-template resource id            */
    PVOID   pCreateParams;      /* passed to the page                     */
    USHORT  dlgid;
    USHORT  usPageStyleFlags;
    USHORT  usPageInsertFlags;  /* BKA_* insert position                  */
    USHORT  usSettingsFlags;
    PSZ     pszName;            /* tab / status text                      */
    USHORT  idDefaultHelpPanel;
    USHORT  usReserved2;
    PSZ     pszHelpLibraryName;
    PUSHORT pHelpSubtable;
    HMODULE hmodHelpSubtable;
    ULONG   ulPageInsertId;     /* returned insertion id                  */
} PAGEINFO;
```

`wpInsertSettingsPage` returns the notebook page-insertion id (0 on failure) [DOC-IBM
`wps2.txt`, wpAddSettingsPages — Example, `wpobject.h:1957`]. The notebook control itself is the
standard PM `WC_NOTEBOOK`; the WPS layer only feeds it pages.

---

## 9. Direct manipulation: `wpDragOver` / `wpDrop` [DOC-IBM]

An object is a drag/drop *target* by overriding two methods that mirror the PM direct-manipulation
message protocol:

```c
MRESULT wpDragOver(WPObject*, HWND hwndCnr, PDRAGINFO pdrgInfo);              /* wpobject.h:1646 */
MRESULT wpDrop    (WPObject*, HWND hwndCnr, PDRAGINFO pdrgInfo, PDRAGITEM pdrgItem); /* wpobject.h:1668 */
```

- **`wpDragOver`** is called as the pointer, carrying a drag set, moves over the object (the system
  routes the PM `DM_DRAGOVER` message to it). The override inspects the `DRAGINFO`/`DRAGITEM` and
  returns whether — and with what default operation — it will accept the drop, using the drag
  protocol's `DOR_*`/`DO_*` response codes packed into the `MRESULT` [DOC-IBM `wps2.txt`,
  wpDragOver — Remarks].
- **`wpDrop`** "is called when a `DM_DROP` message is received by the object"; it "should be
  overridden to process the action of the dragged object or objects being dropped on it" [DOC-IBM
  `wps2.txt`, wpDrop — Remarks / How to Override]. The override typically verifies the rendering
  mechanism/format with `DrgVerifyRMF`, reads the source names with `DrgQueryStrName`, performs the
  action, and returns one of the documented `wpDrop` return codes [DOC-IBM `wps2.txt`, wpDrop —
  Example]: `RC_DROP_DROPCOMPLETE` (`2`), `RC_DROP_ITEMCOMPLETE` (`1`), `RC_DROP_RENDERING` (`0`),
  `RC_DROP_ERROR` (`-1`) [DOC-IBM `wpobject.h:705-708`].

The `DRAGINFO`/`DRAGITEM`/RMF machinery is the general PM direct-manipulation model; the WPS
methods are the object-oriented entry points into it. Objects can also be the drag *source* and
implement rendering via further `wp*` methods (e.g. `wpFormatDragItem`) [DOC-IBM `wps2.txt`, wpDrop
— Related Methods].

---

## 10. Class registration, replacement, and object creation [DOC-IBM]

A WPS class lives in a DLL that must be **registered** with the shell before any of its objects can
exist. The object-management API is declared in `pmwp.h` (enabled by `#define INCL_WINWORKPLACE`,
which turns on `INCL_WPCLASS`) [DOC-IBM `pmwp.h:15,46-48`]. The `HOBJECT` handle type identifies a
live object [DOC-IBM `pmwp.h:52`].

| Symbol | Prototype (from `pmwp.h`) | Purpose |
|---|---|---|
| `WinRegisterObjectClass` | `BOOL WinRegisterObjectClass(PSZ pszClassName, PSZ pszModName)` [`:96-100`] | Register class `pszClassName` implemented in DLL `pszModName`. Class name is case-sensitive. |
| `WinDeregisterObjectClass` | `BOOL WinDeregisterObjectClass(PSZ pszClassName)` [`:104-106`] | Remove a registration. |
| `WinReplaceObjectClass` | `BOOL WinReplaceObjectClass(PSZ pszOldClassName, PSZ pszNewClassName, BOOL fReplace)` [`:110-114`] | Insert a subclass into an existing class's inheritance chain (or undo it), so a new class *becomes* an existing WPS class. |
| `WinEnumObjectClasses` | `BOOL WinEnumObjectClasses(POBJCLASS pObjClass, PULONG pulSize)` [`:119-120`] | Enumerate all registered classes (returns `OBJCLASS` records: name + module). |
| `WinCreateObject` | `HOBJECT WinCreateObject(PSZ pszClassName, PSZ pszTitle, PSZ pszSetupString, PSZ pszLocation, ULONG ulFlags)` [`:129-133`] | Instantiate an object of a class at a location, applying a setup string. |
| `WinSetObjectData` | `BOOL WinSetObjectData(HOBJECT hObject, PSZ pszSetupString)` [`:143-144`] | Apply a setup string to an existing object (drives `wpSetup`). |
| `WinCreateShadow` | `HOBJECT WinCreateShadow(HOBJECT, HOBJECT, ULONG)` [`:170-172`] | Create a shadow of an object. |
| `WinQueryObject` | `HOBJECT WinQueryObject(PSZ pszObjectID)` [`:150-152`] | Resolve an object-ID string (e.g. `"<WP_DESKTOP>"`) to a handle. |
| `WinDestroyObject` / `WinSaveObject` / `WinOpenObject` | see `pmwp.h:147/155/158` | Destroy / persist / open a view of an object. |

`WinCreateObject`'s `ulFlags` selects the collision policy: `CO_FAILIFEXISTS` (`0`),
`CO_REPLACEIFEXISTS` (`1`), `CO_UPDATEIFEXISTS` (`2`) [DOC-IBM `pmwp.h:135-137`]. The `pszLocation`
is a folder object ID or the special `LOCATION_DESKTOP` (`(PSZ)0xFFFF0001`) [DOC-IBM
`pmwp.h:70-72`]. When a class is registered, if it supports templating an object **template** is
automatically placed in the Templates folder, from which the user can tear off instances [DOC-IBM
`wpsguide.txt`, "Instantiating an object …"; template behaviour keyed off
`wpclsQueryStyle`/`CLSSTYLE_NEVERTEMPLATE`].

A minimal installation program registers the class DLL then optionally creates one instance
(condensed from [DOC-IBM `wpsguide.txt`, installation-program example]):

```c
#define INCL_WINWORKPLACE
#include <os2.h>

WinRegisterObjectClass("MyClass", "MYCLASS");        /* class name, DLL module */
WinCreateObject("MyClass",                           /* class name             */
                "My Object",                         /* title                  */
                "KEY=value;",                        /* setup string → wpSetup */
                LOCATION_DESKTOP,                     /* location               */
                CO_FAILIFEXISTS);                     /* flags                  */
```

The REXX shell exposes the same two operations as `SysRegisterObjectClass` (→
`WinRegisterObjectClass`) and `SysCreateObject` (→ `WinCreateObject`) for install scripts
[DOC-IBM `wpsguide.txt`, function-mapping list].

---

## 11. Building a subclass as a SOM class [DOC-IBM]

A new WPS class is authored in an **IDL** (`.idl`) file, compiled by the **SOM compiler** (`sc`)
into language bindings and a class skeleton, and the implementation is completed in C and built
into a DLL. The interface declares the class, its parent, its new methods, its overrides, and its
private instance variables. A representative header of an IDL file for a `WPAbstract` subclass
[DOC-IBM `wpsguide.txt`, WPStyler IDL]:

```idl
#include <wpabs.idl>

interface M_Styler;                       /* forward-declare the metaclass */

interface Styler : WPAbstract             /* Styler is a subclass of WPAbstract */
{
    ULONG InsertObjectStylePage(in HWND hwndDlg);   /* new methods … */
    ULONG QueryObjectStyle(in HWND hwndDlg);
    VOID  SetObjectStyle(in HWND hwndDlg);

#ifdef __SOMIDL__
    implementation
    {
        releaseorder: InsertObjectStylePage, QueryObjectStyle, SetObjectStyle;
        functionprefix = Sty_;            /* C function name prefix           */
        majorversion   = 1;               /* binary-compat version            */
        minorversion   = 2;
        filestem       = wpstyler;        /* generated file base name         */
        metaclass      = M_Styler;        /* this class's metaclass           */
        callstyle      = oidl;
        dllname        = "wpstyler.dll";  /* DLL the shell loads              */

        /* private instance variables — this class's slice of instance data */
        BOOL     fGeneralPage;
        ULONG    ulStyle;
        WPObject self;
    };
#endif
};
```

Salient IDL modifiers [DOC-IBM `wpsguide.txt`]:

- **`interface Styler : WPAbstract`** — single inheritance from the chosen storage class (or any
  WPS class). This is the whole hierarchy decision.
- **`releaseorder`** — fixes the method order in the class's method table so later versions can add
  methods without breaking already-compiled callers (SOM's release-to-release binary compatibility).
- **`functionprefix`** — the prefix on the generated C implementation function names (so
  `wpInitData` is implemented as `Sty_wpInitData`, etc.); recommended for kernel-debugger symbol
  clarity.
- **`dllname`** — the DLL the Workplace Shell loads for this class; it must match the module name
  passed to `WinRegisterObjectClass`.
- **`metaclass`** — names the metaclass (`M_Styler`), needed only when the class adds *class*
  (`wpcls*`) methods.
- Instance variables declared in the `implementation` block become the class's private data slice,
  reached via `somThis` (§3).

To **override** an inherited method, the IDL lists it (with an `override` modifier / comment) and
the C file supplies a body that does its work and delegates to the ancestor via the generated
`parent_<method>` call — e.g. `parent_wpInitData(somSelf)`, `parent_wpSaveState(somSelf)`,
`parent_wpModifyPopupMenu(somSelf, hwndMenu, hwndCnr, iPosition)` [DOC-IBM `wps2.txt`, method
Example-Code sections]. The rule for *when* to call the parent is method-specific and documented
per method's "How to Override" (parent-first for `wpInitData`; parent-first-or-last to order
`wpAddSettingsPages`; parent-last for `wpSaveState`).

The build chain, from the sample makefiles, is: `.idl` → (SOM compiler `sc`) → `.h`/`.ih`
bindings → compile the C implementation → link into the class `.dll`; then `WinRegisterObjectClass`
(or `SysRegisterObjectClass`) makes the class known [DOC-IBM `wpsguide.txt`, sample makefile
`$(b).ih: $(b).idl` / `$(SC) $(SCFLAGS) …`]. The shell instantiates and drives the object entirely
through the SOM method dispatch described in §3 — the developer never calls the `wp*` methods, only
overrides them and calls the `parent_*` forms.

---

## 12. Class-object (`wpcls*`) methods — the metaclass surface [DOC-IBM]

A handful of `wpcls*` class methods complete the model; they act on the class object, not on an
instance, and are overridden on the metaclass:

| Method | Prototype | Role |
|---|---|---|
| `wpclsNew` | `WPObject* wpclsNew(M_WPObject*, PSZ pszTitle, PSZ pszSetupEnv, WPFolder* Folder, BOOL fLock)` [`wpobject.h:3947`] | Create a new instance; the low-level target of `WinCreateObject`. It allocates the object, has SOM initialize it (`wpInitData`, `wpSetupOnce`), and creates the persistent image [DOC-IBM `wpsguide.txt`, "When an object is created … wpclsNew is called"]. |
| `wpclsQueryTitle` | `PSZ wpclsQueryTitle(M_WPObject*)` [`wpobject.h:4163`] | The default title for the class. |
| `wpclsQueryDefaultView` | `ULONG wpclsQueryDefaultView(M_WPObject*)` [`wpobject.h:3993`] | The view opened by default when an object is opened. |
| `wpclsInitData` / `wpclsUnInitData` | `void wpclsInitData(M_WPObject*)` | Initialize/clean up the class object's own (metaclass) instance data — "called immediately after the class object is first awakened" (when its first instance is created/awakened) [DOC-IBM `wps1.txt`, wpclsInitData — Remarks]. |

These parallel the instance methods: `wpclsInitData` is to the class object what `wpInitData` is to
an instance, and both require calling the parent (parent-first for the initializer) [DOC-IBM
`wps1.txt`, wpclsInitData — How to Override].

## See also
- `som.md` — the System Object Model (`SOMObject`, class objects, method resolution, IDL) that every WPS class is built on.
