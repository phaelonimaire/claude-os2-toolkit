# OS/2 API Linkage and Calling Conventions

How an OS/2 program links to and calls the system API: the 32-bit `_System` convention every
`Dos*`/`Win*`/`Gpi*` entry point uses (register volatility, stack cleanup, the `APIRET` return),
how the `EXPENTRY` callback linkage and the 16-bit `_Far16 _Pascal` convention differ from it, and
how a module resolves those calls at link time - by ordinal or by name - through a module-definition
(`.DEF`) file. The 16<->32 thunking machinery that bridges the 32-bit and 16-bit conventions is
described in `thunking.md`; this reference covers the conventions themselves and points there.

Provenance: **[DOC-IBM]** the OS/2 Toolkit headers `os2def.h`, `bsedos.h`, `pmwin.h` (the linkage
macros, the `APIRET` types, the API prototypes) and the Toolkit sample `.DEF` files (the module
definition syntax); **[DOC]** the published x86 "System/syscall" and "Pascal" convention definitions
(register/stack semantics); **[OBS-RE]** the real DOSCALL1/kernel register-preservation behaviour
(cross-referenced to `thunking.md`).

## The two linkage keywords [DOC-IBM]

`os2def.h` defines the API linkage macros. Every OS/2 API is declared with one of these; the macro
selects the compiler's calling convention for that entry point:

| Macro | Expands to | Used for | Width |
|---|---|---|---|
| `APIENTRY` | `_System` | 32-bit API entry points (`DosOpen`, `WinCreateStdWindow`, ...) | 32-bit |
| `EXPENTRY` | `_System` | 32-bit exported callbacks (window procedures, hooks) | 32-bit |
| `APIENTRY16` | `_Far16 _Pascal` | 16-bit API entry points | 16-bit |
| `PASCAL16` | `_Far16 _Pascal` | 16-bit far-Pascal entry points | 16-bit |
| `CDECL16` | `_Far16 _Cdecl` | 16-bit far-C entry points | 16-bit |

Source: `os2def.h:45-50`. Note that `APIENTRY` and `EXPENTRY` are the **same** underlying convention
(`_System`); the distinction is documentary (see "EXPENTRY vs APIENTRY" below), not a difference in
ABI. `FAR` and `NEAR` expand to nothing in the 32-bit (flat) headers (`os2def.h:42-43`).

## The `_System` (32-bit) convention [DOC / OBS-RE]

`_System` (also called the "System" or "syscall" convention) is the standard linkage for the 32-bit
OS/2 API. Its rules:

| Aspect | Rule | Source |
|---|---|---|
| Argument passing | All arguments on the stack, pushed **right-to-left** | [DOC] |
| Stack cleanup | **Caller** removes the arguments after the call returns | [DOC] |
| Return value | `EAX` (an `APIRET`, i.e. `unsigned long`) | type [DOC-IBM] `os2def.h:55`; `EAX` placement [DOC] |
| Volatile (not preserved) | `EAX`, `ECX`, `EDX` | [DOC] |
| Preserved (callee-saved) | `EBX`, `ESI`, `EDI`, `EBP` | [DOC] |

Because arguments are all stack-passed and the **caller** cleans the stack, an OS/2 API can be called
with a variable-shaped frame and the compiler emits the pop on the caller side; a `_System` callee
returns with a plain `ret` (it does not itself remove the arguments). This is the opposite of the
16-bit Pascal convention below, where the callee cleans.

> **Observed refinement [OBS-RE].** The documented convention marks `EAX`, `ECX`, and `EDX` as
> volatile, but the **real** OS/2 kernel / DOSCALLS preserve `ECX` and `EDX` across the API call, and
> callers in the shipped system depend on it. Only `EAX` (the return value) is genuinely clobbered.
> Where the documentation and the shipped binary disagree, the binary is authoritative for behaviour.
> Detail and the thunk that honours it are in `thunking.md` (section "The register-preservation contract").

> **Argument-count note [DOC / unverified vs IBM].** The published "syscall" description also states
> that the size of the parameter list, in doublewords, is passed in `AL`. This detail is not confirmed
> from an IBM primary source and is noted for completeness only.

## The `APIRET` return type [DOC-IBM]

Most `Dos*` APIs return an `APIRET` - zero on success, a non-zero `ERROR_*` code otherwise. The three
width variants are defined in `os2def.h`:

| Type | Definition | Width | Source |
|---|---|---|---|
| `APIRET` | `unsigned long` | 32-bit | `os2def.h:55` |
| `APIRET16` | `unsigned short` | 16-bit (the 16-bit API return) | `os2def.h:56` |
| `APIRET32` | `unsigned long` | 32-bit (explicit alias) | `os2def.h:57` |

A few APIs do not return a code and are declared `VOID` - e.g. `VOID APIENTRY DosExit(ULONG action,
ULONG result)` (`bsedos.h:101`), which never returns to the caller. Presentation Manager APIs commonly
return other types (a `BOOL`, an `HWND`, an `HPS`, an `MRESULT`) rather than an `APIRET`; the linkage
(`APIENTRY`/`EXPENTRY` = `_System`) is unchanged.

## `EXPENTRY` vs `APIENTRY` [DOC-IBM]

`EXPENTRY` and `APIENTRY` both expand to `_System` (`os2def.h:45-46`), so they are identical at the
ABI level. The convention is which direction the call crosses the application/system boundary:

- **`APIENTRY`** marks a routine the application **calls** - an API the system exports.
- **`EXPENTRY`** marks a routine the application **exports** for the system to call back - most
  importantly a **window procedure**. The window-procedure type is
  `typedef MRESULT (EXPENTRY FNWP)(HWND, ULONG, MPARAM, MPARAM);` with `PFNWP` its pointer form
  (`pmwin.h:223-224`). A window procedure receives `(HWND, message, MPARAM mp1, MPARAM mp2)` and
  returns an `MRESULT`; `MPARAM` and `MRESULT` are both `VOID *` (`os2def.h:591-593`).

Because both are `_System`, a callback registered with the system (e.g. via `WinRegisterClass`) is
called with the same register/stack rules as any API.

## The 16-bit far-Pascal convention, at a glance [DOC-IBM / DOC]

The 16-bit API linkage is `APIENTRY16` / `PASCAL16` = `_Far16 _Pascal` (`os2def.h:48-49`). Two things
combine here:

- **`_Far16`** - the call is a **far** (16:16 segmented) call, and pointer parameters are 16:16 far
  pointers, not 32-bit flat pointers. `os2def.h` uses the related `_Seg16` qualifier for 16-bit
  pointer typedefs, e.g. `typedef UCHAR * _Seg16 PUCHAR16;` (`os2def.h:99-100`). [DOC-IBM]
- **`_Pascal`** - the Pascal convention: arguments are pushed **left-to-right**, the **callee** removes
  them from the stack (a far `ret n`), and an ordinal result is returned in `AL`/`AX` (8-/16-bit) or
  `DX:AX` (32-bit value on a 16-bit system). [DOC] The 16-bit API return type is `APIRET16`
  (`os2def.h:56`).

This is the mirror image of `_System` on both axes that matter: **left-to-right** vs right-to-left
argument order, and **callee-cleans** vs caller-cleans. That mismatch - plus the 16:16-vs-flat pointer
difference - is exactly why a call cannot cross the 16/32 boundary directly.

## Why 16<->32 thunking exists -> `thunking.md`

Because the 32-bit (`_System`, flat) and 16-bit (`_Far16 _Pascal`, segmented) conventions differ in
argument order, stack-cleanup responsibility, stack width, and pointer format, every call that crosses
the boundary must be adapted: convert 16:16 <-> flat pointers, rebuild the argument frame in the target's
order, switch stacks, and perform the ring/selector transition. That adaptation is the **thunk**.
`thunking.md` documents the thunk mechanism (the universal thunk, the control-word grammar, the stack
switch, and the register-preservation contract). This reference does not duplicate it.

## Selected API prototypes [DOC-IBM]

Concrete `_System` (`APIENTRY`) prototypes, transcribed from the Toolkit headers, to show the shape:

| Prototype | Source |
|---|---|
| `APIRET APIENTRY DosOpen(PCSZ pszFileName, PHFILE pHf, PULONG pulAction, ULONG cbFile, ULONG ulAttribute, ULONG fsOpenFlags, ULONG fsOpenMode, PEAOP2 peaop2);` | `bsedos.h:1255-1262` |
| `APIRET APIENTRY DosRead(HFILE hFile, PVOID pBuffer, ULONG cbRead, PULONG pcbActual);` | `bsedos.h:1345` |
| `APIRET APIENTRY DosWrite(HFILE hFile, ...);` | `bsedos.h:1356` |
| `APIRET APIENTRY DosClose(HFILE hFile);` | `bsedos.h:1340` |
| `APIRET APIENTRY DosAllocMem(PPVOID ppb, ...);` | `bsedos.h:1849` |
| `VOID APIENTRY DosExit(ULONG action, ULONG result);` | `bsedos.h:101` |
| `HWND APIENTRY WinCreateStdWindow(HWND hwndParent, ULONG flStyle, PULONG pflCreateFlags, PCSZ pszClientClass, PCSZ pszTitle, ULONG styleClient, HMODULE hmod, ULONG idResources, PHWND phwndClient);` | `pmwin.h:2762-2770` |

Handle types are defined in `os2def.h`: `HFILE` is `LHANDLE` (`unsigned long`) with `PHFILE` its
pointer (`os2def.h:235-236`); function-pointer types `PFN`/`NPFN` are `APIENTRY`-linkage pointers
(`os2def.h:111-114`).

## Ordinal vs by-name imports, and the `.DEF` module-definition file [DOC-IBM]

An executable or DLL resolves each imported API to a specific export of a specific module. An export
can be referenced two ways:

- **By ordinal** - a small integer assigned to the export by the providing module. The import binds to
  "export number *N* of module *M*". This is the compact, position-stable form and is how the core
  system DLLs (DOSCALLS, PMWIN, ...) are imported.
- **By name** - the import binds to a named export of module *M*, resolved by string match.

Both the exports a module provides and the imports it requires are declared in a **module-definition
file** (`.DEF`) that the linker consumes. The relevant statements (all transcribed from Toolkit sample
`.DEF` files):

| Statement | Meaning | Example (source) |
|---|---|---|
| `LIBRARY <name>` | This module is a DLL named `<name>` | `LIBRARY DLLIB` (`SAMPLES/OS2/DLLAPI/dllib.def`) |
| `NAME <name> [type]` | This module is a program; `type` e.g. `WINDOWAPI`, `WINDOWCOMPAT` | `NAME DLLAPI WINDOWAPI` (`SAMPLES/OS2/DLLAPI/dllapi.def`) |
| `EXPORTS` | Names (and optional ordinals) this module makes callable | see below |
| `IMPORTS` | Names this module imports from other modules | see below |
| `DATA` / `CODE` | Segment attributes (`MULTIPLE READWRITE`, `LOADONCALL`, ...) | `DATA MULTIPLE READWRITE LOADONCALL` (`dllib.def`) |
| `STACKSIZE` / `HEAPSIZE` | Stack / local-heap size in bytes | `STACKSIZE 8192` (`SAMPLES/MM/DIVE/show.def`) |
| `PROTMODE` | Protected-mode-only module | `PROTMODE` (`dllib.def`) |
| `DESCRIPTION '...'` | Text stamped into the module | `DESCRIPTION 'DLL Sample ...'` (`dllib.def`) |

### EXPORTS - assigning ordinals [DOC-IBM]

An `EXPORTS` entry names an exported symbol and may pin it to an explicit ordinal with `@N`:

```
EXPORTS     SearchFile    @1
            ReadFileProc  @2
            CalCulProc    @3
```

(`SAMPLES/OS2/DLLAPI/dllib.def`.) An export may also alias an external (exported) name to a different
internal name with `exportedname=internalname`:

```
EXPORTS
    _S_GETHOSTBYNAME=_s_gethostbyname
    _s_gethostbyname                          @1
```

(`SAMPLES/TCPIPTK/SAMPDLL/sampdllb.def`.)

### IMPORTS - by ordinal or by name [DOC-IBM]

An `IMPORTS` entry names the local symbol and the module it comes from. Referencing the module export
by **ordinal** uses `MODULE.N`; by **name** uses `MODULE.EXPORTNAME`:

```
IMPORTS     SearchFile   = DLLIB.1        ; by ordinal - export #1 of DLLIB
            ReadFileProc = DLLIB.2
            CalCulProc   = DLLIB.3
```

(`SAMPLES/OS2/DLLAPI/dllapi.def` - the importer side of the `dllib.def` exports above.)

```
IMPORTS
    ftpget    = FTPAPI.FTPGET              ; by name - export "FTPGET" of FTPAPI
    ftpput    = FTPAPI.FTPPUT
```

(`SAMPLES/TCPIPTK/RCOPY/rcopyb.def`.) A shorter form omits the local-name alias and imports the
export directly, e.g. `IMPORTS CAP.ccInitialize` (`SAMPLES/MM/CAPSAMP/capsamp.def`).

The calling convention (`_System` for 32-bit, `_Far16 _Pascal` for 16-bit) is a property of the
declared prototype, independent of whether the import was resolved by ordinal or by name - the resolved
target is the same code either way.
