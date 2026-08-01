# OS/2 Session Manager — Sessions and Screen Groups

The protected-mode session manager governs **sessions** (also called screen groups): independent
console/PM contexts, exactly one of which holds the foreground at a time. Initialized during
boot-sequence Stage 9.

Provenance: **[DOC-IBM]** IBM Toolkit `bsedos.h` (the session control APIs and their structures),
`#ifdef INCL_DOSSESMGR` block (Toolkit 4.5 `H/bsedos.h:2681-2788`).

## Session control APIs [DOC-IBM `bsedos.h:2685-2788`]

- **`DosStartSession(PSTARTDATA psd, PULONG pidSession, PPID ppid)`** — starts a new session
  (prototype `bsedos.h:2768-2770`). The `STARTDATA` structure (`bsedos.h:2685-2708`) specifies the
  program and arguments (`PgmName` / `PgmInputs`), the session type (`SessionType`:
  `SSF_TYPE_FULLSCREEN` 1 / `SSF_TYPE_WINDOWABLEVIO` 2 / `SSF_TYPE_PM` 3 / `SSF_TYPE_VDM` 4, etc.,
  `bsedos.h:2725-2734`), foreground vs background (`FgBg`: `SSF_FGBG_FORE` 0 / `SSF_FGBG_BACK` 1,
  `:2714-2715`), whether the new session is related to the caller so the caller can control it
  (`Related`: `SSF_RELATED_INDEPENDENT` 0 / `SSF_RELATED_CHILD` 1, `:2711-2712`), inheritance
  (`InheritOpt`: `SSF_INHERTOPT_SHELL` 0 / `SSF_INHERTOPT_PARENT` 1, `:2721-2722`), and an optional
  icon (`IconFile`) / title (`PgmTitle`) / environment (`Environment`).
- **`DosStopSession(scope, idSession)`** — stops a session (prototype `bsedos.h:2777-2778`); `scope`
  is `STOP_SESSION_SPECIFIED` 0 (one) or `STOP_SESSION_ALL` 1 (all related) (`:2760-2761`).
- **`DosSelectSession(idSession)`** — brings a session to the foreground (prototype
  `bsedos.h:2775`).
- **`DosSetSession(idSession, PSTATUSDATA)`** — changes a session's status via the `STATUSDATA`
  structure (`bsedos.h:2744-2750`, prototype `:2772-2773`): selectability (`SelectInd`:
  `SET_SESSION_SELECTABLE` 1 / `SET_SESSION_NON_SELECTABLE` 2) and bond (`BondInd`:
  `SET_SESSION_BOND` 1 / `SET_SESSION_NO_BOND` 2) (`:2753-2757`).

### Session-control semantics and return codes [DOC — EDM2]

**`DosStartSession`** — the returned session id and process id are set **only when `Related` = 1**
(a child session); for an independent session they are not returned. A parent session establishes a
parent *session*/child *session* relationship, **not** a parent/child *process* relationship — the
returned process id therefore cannot be used on calls that require process parentage (e.g.
`DosSetPrty`). Child-session termination is reported through a **termination queue** the parent
creates (a queue named in `TermQ`) before its first `DosStartSession`; the queue receives a
`{session id, result code}` element per terminating child. [DOC — EDM2 "DosStartSession (OS/2 1.x)"]

| rc | Name | Meaning |
|----|------|---------|
| 0 | NO_ERROR | success |
| 370 | ERROR_SMG_NO_SESSIONS | no sessions available to start |
| 418 | ERROR_SMG_INVALID_CALL | call not valid |
| 453 | ERROR_SMG_INVALID_START_MODE | `FgBg` value not valid |
| 454 | ERROR_SMG_INVALID_RELATED_OPT | `Related` value not valid |
| 457 | ERROR_SMG_START_IN_BACKGROUND | foreground start requested but neither caller nor any descendant is in the foreground — session was started in the background |
| 460 | ERROR_SMG_PROCESS_NOT_PARENT | caller is not the parent session |
| 461 | ERROR_SMG_INVALID_DATA_LENGTH | `STARTDATA` `cb` (length) not valid |
| 478 | ERROR_SMG_INVALID_TRACE_OPTION | `TraceOpt` value not valid |
| 491 | ERROR_SMG_INVALID_PROGRAM_TYPE | program type not valid for the requested session |
| 492 | ERROR_SMG_INVALID_PGM_CONTROL | `PgmControl` value not valid |
| 493 | ERROR_SMG_INVALID_INHERIT_OPT | `InheritOpt` value not valid |
| 503 | ERROR_SMG_INVALID_DEBUG_PARMS | debug/trace parameters not valid |

Any error from `DosOpen`, `DosLoadModule`, or `DosExecPgm` may also be returned.
[DOC — EDM2 "DosStartSession (OS/2 1.x)"]

**`DosStopSession`** — may be issued by a parent only for a child session started with `Related` = 1;
independent sessions cannot be stopped this way, and stopping a session also terminates its
descendants. A normal return code does **not** guarantee termination — the target process may refuse
to exit; the only certain confirmation is the termination-queue notification. [DOC — EDM2
"DosStopSession (OS/2 1.x)"]

| rc | Name | Meaning |
|----|------|---------|
| 0 | NO_ERROR | success |
| 369 | ERROR_SMG_INVALID_SESSION_ID | `SessID` not valid (ignored when scope = all) |
| 418 | ERROR_SMG_INVALID_CALL | call not valid |
| 452 | ERROR_SMG_SESSION_NOT_PARENT | caller is not the parent of the target session |
| 458 | ERROR_SMG_INVALID_STOP_OPTION | scope/target option not valid |
| 459 | ERROR_SMG_BAD_RESERVE | reserved parameter was not a zeroed doubleword |

[DOC — EDM2 "DosStopSession (OS/2 1.x)"]

## Application type [DOC-IBM `bsedos.h:2781-2811`]

`DosQueryAppType(pszName, PULONG pFlags)` (prototype `bsedos.h:2781-2786`) reports an executable's
type via `FAPPTYP_*` bits (`bsedos.h:2795-2811`) — distinguishing Presentation Manager
(`FAPPTYP_WINDOWAPI` 0x0003), VIO-windowable (`FAPPTYP_WINDOWCOMPAT` 0x0002), full-screen
(`FAPPTYP_NOTWINDOWCOMPAT` 0x0001), and DOS/Windows programs (`FAPPTYP_DOS` 0x0020,
`FAPPTYP_WINDOWSREAL` 0x0200, `FAPPTYP_WINDOWSPROT` 0x0400) — which the session manager uses to
decide the session kind a program needs. (Also aliased `DosQAppType`, `bsedos.h:2765`.)

## Foreground and screen-group state [DOC-IBM]

The current foreground is observable through several surfaces (see `infoseg.md`):
- `DosQuerySysInfo(QSV_FOREGROUND_FS_SESSION)` — the foreground full-screen session id
  (`QSV_FOREGROUND_FS_SESSION` = 24, Toolkit `bsedos.h:2523`; there is also
  `QSV_FOREGROUND_PROCESS` = 25 for the foreground process id, `:2524`).
- The Global InfoSeg `SIS_CurScrnGrp` (foreground screen group) and `SIS_FgndPID` (foreground PID)
  (IBM DDK `base/h/infoseg.h:69,76`).
- The Local InfoSeg `LIS_CurScrnGrp` and `LIS_Fgnd` (whether this process is in the foreground)
  (IBM DDK `base/h/infoseg.h:194,200`).

## Process and session enumeration [DOC-IBM]

`DosQProcStatus` / `DosQuerySysState` return a snapshot of the process, thread, session, module, and
semaphore tables — used for task lists, "which session owns this process," and hung-application
detection. The 32-bit `DosQuerySysState(EntityList, EntityLevel, pid, tid, pDataBuf, cbBuf)` is
confirmed at Toolkit `bsedos.h:3589-3594`, with the `QS*REC` record structures for each table
threaded off `QSPTRREC` (`bsedos.h:3578-3587`): `QSGREC` global, `QSPREC` process, `QSTREC` thread,
`QSS16HEADREC`/`QSS32REC` semaphore, `QSMREC` shared-mem, `QSLREC` module/MTE, `QSFREC`
file-system. `DosQProcStatus` is the 16-bit predecessor and is **not present in the 4.5 Toolkit
32-bit header** — sourced only to its 32-bit successor here [OBS-RE for the 16-bit name].

## Internal mechanism: how a session is created and how the foreground switches [OBS-RE]

Everything above is the documented public contract. This section is the internal implementation
behind it — reverse-engineered from the real Warp 4.5 binaries (`SESMGR.DLL`, `DOSCALL1.DLL`,
`PMMERGE.DLL`) by static disassembly plus live confirmation on a running debug-kernel VM (KDB).
Provenance for this whole section is **[OBS-RE]** unless a line says otherwise; no IBM document
describing this mechanism is known to exist (checked: IBM's own DDK, the Toolkit 4.5 Control
Program Guide and Reference, and the EDM2 article corpus all cover only the public API surface
above, never the internals).

### `SESMGR.DLL` is a pure forwarder

`SESMGR.DLL` (the module `DosStartSession`/`Select`/`Set`/`StopSession` resolve to via `DOSCALLS`)
carries no code of its own — every one of its ~35 ordinals (`STARTSESSION`, `SELECTSESSION`,
`SETSESSION`, `STOPSESSION`, `SMSWITCH`, `SMSERVEAPPREQ`, `SMGETAPPREQ`, `SMSTART`, `SMSETTITLE`,
`SMPAUSE`, and others) forwards straight through to internal entry points inside `DOSCALL1.DLL`.
The real implementation — and the real complexity — lives there, not in `SESMGR.DLL` itself.

### The unified request-block object

All four public session-lifecycle calls (`DosStartSession`/`Select`/`Set`/`StopSession`) build the
**same kind of object**: a variable-sized "request-block," fresh per call, sized by operation (218
bytes for Start; smaller, ~38-44-byte records for Select/Set/Stop). Every block shares a small
universal header — a constant tag byte, an operation-code byte (`0`=Start/`1`=Select/`2`=Set/
`3`=Stop), and a few fields copied from the target screen group's control block at allocation time
— followed by an operation-specific payload (for Start: the `STARTDATA` fields, including four
packed, null-terminated strings — title, program name, command-line inputs, and the `TermQ` queue
name — laid out back to back with an offset table pointing at each).

Every operation is dispatched through **one single internal function**, keyed on the block's
operation-code byte. For a Start request specifically, that dispatcher calls the internal
`ExecPgm` entry point directly (mapping `STARTDATA`'s fields onto the real 7-parameter
`Dos16ExecPgm`-shaped signature: object name/length, exec flags, argument string, environment,
result buffer, and the program name), and — for every operation, not just Start — writes the
**entire request-block, unmodified, as the payload** of a queue-write to a well-known named queue,
`\QUEUES\SESMGR\APPREQQ`. That queue write is how the session-manager UI (the Window List) learns a
new session exists or a session's state changed; the queued packet *is* the request-block, not a
separately-assembled wire format.

### The persistent Screen Group Control Block (SGCB)

Separately from the transient request-block above, each screen group (session) has a **persistent,
218-byte control block**, allocated once and kept in a doubly-linked list, indexed by a fixed
groupId-keyed pointer table (25 slots at boot, confirmed to grow dynamically past that once more
sessions are created). Known fields, by byte offset:

| Offset | Field |
|---|---|
| `+0x2`/`+0x4` | forward list-link (segment/offset) |
| `+0x6`/`+0x8` | backward list-link (segment/offset) |
| `+0xa` | packed id: `(type << 8) \| sgid` |
| `+0x10` | type byte (repeats `+0xa`'s high byte) |
| `+0x12` | bound child session's sgid (0 = none) |
| `+0x26` | flag byte; bit 0 = "has a bound child" / parent-eligible |
| `+0x30` | `sgid * 0x20` |
| `+0x4c`/`+0x4e` | a far pointer, written when the session's screen buffer is saved — plausibly the session's LVB (Logical Video Buffer) location, not fully confirmed |
| `+0x88` | the session's registered keyboard-focus handle |

Most of the remaining ~150 bytes are unmapped (owned by other subsystems — video state, semaphore
handles — each would need that subsystem's own init code traced to identify). SGID numbering is a
single byte, with documented ranges: `0` = Hard Error Popups, `1` = Shell, `2` = Real Mode, `3` =
VioPopUp, `4`-`15` = FullScreen sessions, `16`-`31` = Windowable VIO sessions, `32`-`255` = PM
sessions. Two groups (`0` and `3`) are bootstrapped lazily on first access rather than created
through the normal session-creation path; every other SGCB is created on demand when a session
starts.

**Session creation does not set up screen/VIO buffer space — that is deferred.** The SGCB
constructor writes only bookkeeping at creation time: the id/type fields above, the related/bound-
parent linkage (populated directly from the caller's own "related" request, when given), the
`sgid`-derived offset, and a short (up to 30 bytes) null-terminated name string copied into a
separate table, almost certainly the session's Window List display name. **It never writes
`+0x4c`/`+0x4e`** (the likely LVB pointer above) — that field is only ever populated later, during
a foreground switch, by the screen-save mechanism described next. So the screen buffer itself is
set up lazily: either on the session's first foreground activation, or by the session's own
process once it starts running and first calls into VIO — not by the session-creation call itself.

### The foreground-switch mechanism

Switching which session is foreground (Ctrl-Esc/Alt-Esc, or a Window List selection) is a
**different operation from session creation/selection above** — a lower-level primitive the public
`DosSelectSession` API does not even call (confirmed: a real Window List switch, live-traced, never
touches `DosSelectSession`'s own entry point). The real chain, symbol-verified end to end on a live
Warp 4.5 system:

1. The Window List (part of the PM shell) resolves the internal switch entry point once, at PM
   init, and calls it through a stored function pointer thereafter — the call is never a static
   reference, which is why it cannot be found by disassembling call sites; only observing the live
   pointer value (or single-stepping into the call) reveals it.
2. That call reaches the session-manager's own switch dispatcher inside `DOSCALL1.DLL`, which
   acquires two locks (global session-manager state, shared across all processes), looks up the
   target SGCB, and dispatches to a mid-level orchestrator by request type (foreground switch,
   background switch, popup, child-exit, and others share this same entry point).
3. The mid-level orchestrator re-derives both the outgoing and incoming SGCB and type-dispatches
   to one of three handlers: **switch-to-foreground**, **switch-to-background**, or
   **switch-to-popup**.
4. All three handlers converge on the same two real operations: a **screen-buffer save/restore**
   call (which itself is mostly a gate — it checks whether the tracked "current" session already
   matches the target and no-ops if so, only actually invoking the restore machinery on a genuine
   change) and a **device-driver notify** call.
5. The device-driver notify call walks a registered-driver notify chain and — for the keyboard
   specifically — invokes the keyboard driver's own focus-switch entry point, which looks up the
   target session's registered focus handle (the SGCB `+0x88` field above) via a table-driven
   lookup and returns it as the new keyboard-focus owner. This is table-driven, per-session-handle
   dispatch, not a broadcast to every process.

**The switch-mechanism chain above has no mouse-equivalent of the keyboard-focus handoff** — every
function in that chain was read in full; the device-notify step only ever invokes the keyboard's
handler, never an analogous mouse one. **This is not because mouse has no switch-aware mechanism at
all** — the mouse driver has its own, reached through a different path (its own IOCtl category's
session-control notification, carrying explicit pre-switch/post-switch/creation/termination event
types, distinct from the notify chain above). It tracks which session is currently foreground and
does real work on a switch: transferring to a full-screen/DOS-compatibility session runs a real
begin/end-switch sequence through the legacy mouse-emulation interface; transferring to a
non-full-screen (windowed/PM) session instead **explicitly disables the driver's own mouse-data
processing** — a deliberate hand-off, not an omission. That's why PM's own input routing shows no
per-session mouse-focus table the way keyboard has one: mouse events there carry their own screen
coordinate and are delivered by ordinary hit-testing against whichever window is visible on top,
and the driver has already stepped out of the way by the time PM is foreground. Keyboard input
carries no spatial coordinate, so it needs the explicit per-session handle handoff described above
even while PM is running — the asymmetry is real, but it exists between "how PM handles mouse vs.
keyboard while it's foreground," not between "mouse has a switch mechanism and keyboard doesn't."

A separate, kernel-level mechanism propagates scheduling priority during a switch: every task
belonging to the outgoing screen group has its priority boost revoked, and every task belonging to
the incoming one has its priority boost applied, before the screen group's "current foreground"
tracking variable is updated. Whether/how this kernel-level priority mechanism is invoked from the
`DOSCALL1.DLL` chain above is not confirmed — both are independently observed real mechanisms; only
the link between them (if any) remains open.

### What actually triggers a switch: the hotkey path

A Ctrl-Esc/Alt-Esc keypress is not a special side-channel — it is recognized during **completely
ordinary keyboard-message processing** (the standard character-message a window receives for any
keystroke), gated on the message's own documented modifier-key bits (a "this is a scan-code event"
flag, together with the Alt or Ctrl modifier flag). A classifier function reads a value out of the
user's own `OS2.INI` profile (under a semaphore-protected profile-read, i.e. the session-switch
hotkey is a **user-configurable Desktop setting**, not a hardcoded key combination) and, on a match,
invokes the same lower-level primitives the Window List itself uses to request and then wait for a
switch — the wait step also boosts the requesting thread's own priority while it waits. Both the
request and the wait step are implemented as ordinary 32-bit PM code that thunks down into the
16-bit `DOSCALL1.DLL` switch primitives above via the universal 32-to-16 thunk interpreter
documented in `thunking.md` (`THK32_UNITHUNK`) — the packed "descriptor" a caller loads into `EAX`
before invoking the interpreter is, in this case, literally the target's own 16:16 far address,
confirmed by watching the interpreter unpack it and transfer control there. Below the PM level,
the same Ctrl-Esc/Alt-Esc combination is independently detected a second time, at the keyboard
driver's own interrupt handler (every keystroke, not just the ones that reach a message queue) —
see `vio-kbd-mou.md`'s device-driver section for that half of the chain, and for the mouse
driver's own separate switch-notification mechanism.

---

*Ratified (2026-07-26): checked against IBM Toolkit 4.5 `H/bsedos.h` (`INCL_DOSSESMGR` block,
lines 2681-2811; `DosQuerySysInfo`/QSV indices 2498-2610; `DosQuerySysState`/`QS*REC` 3130-3594)
and IBM DDK `base/h/infoseg.h` (foreground fields). All session-control prototypes, the `STARTDATA`
/ `STATUSDATA` layouts and their `SSF_*` / `SET_SESSION_*` / `STOP_SESSION_*` constants, the
`DosQueryAppType` `FAPPTYP_*` bits, `QSV_FOREGROUND_FS_SESSION` (=24), and the four InfoSeg
foreground fields matched IBM sources and were upgraded from a general `[DOC-IBM]` tag to
line-precise citations. Nothing in the original doc contradicted IBM sources. (The `QS*REC` record
names added here were taken directly from `QSPTRREC` at `bsedos.h:3578-3587`: `QSLREC` = module/MTE,
`QSMREC` = shared-mem, `QSS16HEADREC`/`QSS32REC` = semaphore — there is no `QSSREC`.) `DosQProcStatus`
(the 16-bit name) could not be sourced to the 4.5 Toolkit and is left noted as such.*

*Internal-mechanism section added 2026-07-30: reverse-engineered from `SESMGR.DLL`/`DOSCALL1.DLL`/
`PMMERGE.DLL` (static disassembly, symbol tables from matching debug-build `.SYM` files) with live
confirmation via KDB on a running Warp 4.5 debug-kernel VM, including single-stepping the hotkey
trigger chain through a genuine keypress to its real destination. No IBM document covering this
mechanism is known — everything here is [OBS-RE]. Two items remain open: the exact meaning of SGCB
`+0x4c`/`+0x4e`, and whether the kernel-level priority-propagation mechanism connects to the
`DOSCALL1.DLL` chain or runs in parallel to it. The mouse-focus paragraph reflects a same-day
correction: an earlier pass (checking only the `DOSCALL1.DLL`/`PMMERGE.DLL` switch chain) concluded
mouse had no switch-aware mechanism at all; reading the real mouse-driver source directly found a
genuine one reached through a different IOCtl path — the PM-routing conclusion (hit-testing, no
per-session table) still holds, now for a driver-confirmed reason instead of an inferred one.*
