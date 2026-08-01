# OS/2 Presentation Manager Message Queue

How the PM message queue delivers messages and how a thread blocked in `WinGetMsg` is woken. Part of
the Presentation Manager (boot-sequence Stage 11); it is what drives `WM_PAINT` and every other
window message.

Provenance: **[DOC-IBM]** the PM programming reference and the IBM Toolkit `pmwin.h` (the `Win*`
message APIs and the `QMSG` layout — see the exact citations in the section below);
**[OBS-RE]** RE of `PMMERGE` for the internal dispatch and the kernel wake path.

## The queue and messages [DOC-IBM]

Each PM thread that will process messages creates a queue with `WinCreateMsgQueue` (returning an
`HMQ`). A message is a `QMSG`: target window (`HWND`), message id, two message parameters
(`MPARAM mp1`, `mp2`), a timestamp, and the pointer position.

The `QMSG` layout is fixed by the ABI: `{ HWND hwnd; ULONG msg; MPARAM mp1; MPARAM mp2; ULONG time;
POINTL ptl; ULONG reserved; }` — `hwnd` is the target window, `msg` the message id, `mp1`/`mp2` the
two parameters, `time` the timestamp, and `ptl` the pointer position. [DOC-IBM] IBM Toolkit
`pmwin.h` `typedef struct _QMSG` (H/pmwin.h:900-911).

- **`WinPostMsg`** — post asynchronously onto the target window's queue and return immediately.
  `BOOL WinPostMsg(HWND hwnd, ULONG msg, MPARAM mp1, MPARAM mp2)`. [DOC-IBM] `pmwin.h:1070`.
- **`WinSendMsg`** — call the target window procedure synchronously (directly, not via the queue),
  returning its result; cross-thread sends are marshalled. `MRESULT WinSendMsg(HWND hwnd, ULONG msg,
  MPARAM mp1, MPARAM mp2)`. [DOC-IBM] `pmwin.h:1035`.
- **`WinGetMsg`** — retrieve and remove the next message, **blocking** until one is available.
  `BOOL WinGetMsg(HAB hab, PQMSG pqmsg, HWND hwndFilter, ULONG msgFilterFirst, ULONG msgFilterLast)`.
  [DOC-IBM] `pmwin.h:1054`.
- **`WinPeekMsg`** — the non-blocking form (with optional remove). `BOOL WinPeekMsg(HAB hab, PQMSG
  pqmsg, HWND hwndFilter, ULONG msgFilterFirst, ULONG msgFilterLast, ULONG fl)`, where `fl` is
  `PM_REMOVE` (0x0001) or `PM_NOREMOVE` (0x0000). [DOC-IBM] `pmwin.h:1060` (constants
  `pmwin.h:1101-1102`).
- **`WinDispatchMsg`** — invoke the target window's window procedure for the message.
  `MRESULT WinDispatchMsg(HAB hab, PQMSG pqmsg)`. [DOC-IBM] `pmwin.h:1067`.

`WinCreateMsgQueue` returns an `HMQ`: `HMQ WinCreateMsgQueue(HAB hab, LONG cmsg)`. [DOC-IBM]
`pmwin.h:1040`. `MPARAM` and the packing/unpacking macros (`MPFROMP`, `MPFROM2SHORT`, …) are in
`pmwin.h:170-181`.

## Block and wake [OBS-RE]

`WinGetMsg` on an empty queue parks the thread in PMMERGE's internal `SleepPmq`, which waits on the
per-queue event token through a 16-bit **kernel event primitive** reached via an LX-fixup **32→16
call gate** — surfaced as DOSCALL1 **ordinals 590 / 591** (`Dos32PMPostEventSem` /
`Dos32PMWaitEventSem`).

*Provenance of the ordinal names (2026-07-26):* DOSCALL1 exports 590/591 by **ordinal only** — the
IBM DOSCALL1.DLL EXEHDR export table names just ~32 resident entries and does **not** name these
(checked against an EXEHDR dump of IBM's DOSCALL1.DLL, negative). The names
`Dos32PMPostEventSem` (590) / `Dos32PMWaitEventSem` (591) are attested only by community RE (the
osFree/EDM2 DOSCALLS ordinal reference). No IBM primary was found that names ordinals 590/591, so
this stays **[OBS-RE]**. (The Toolkit `bseord.h` also uses 590/591, but as *GPI32* ordinals
`ORD_GPI32QUERYDEFATTRS`/`ORD_GPI32SETDEFATTRS` in a different DLL — unrelated, not a conflict.)

A cross-thread or cross-process `WinPostMsg` / `WinSendMsg` ORs a **wake bit** into the target queue
(`SetWakeBit`) and, **iff** the target thread is parked, posts the queue's event semaphore — waking
the correct blocked `SleepPmq`. This is the mechanism behind "the PM message queue is handled in the
kernel": the *queue container* is ring-3 (inside PMMERGE), but its **blocking/wake is a kernel
event-semaphore primitive**, so a post originating in one address space can wake a waiter in another.

## The periodic tick [OBS-RE]

`SleepPmq` also arms a **finite** timeout so a parked thread periodically re-checks its wake bits and
fires due `WM_TIMER` messages. Whether real OS/2's kernel **actively posts** the queue's event
semaphore on a periodic timer tick, versus `SleepPmq` simply timing out and re-checking, has not been
fingerprinted to a specific kernel symbol/ISR; it is an open question resolvable only by live
observation. Either way the observable effect is the same: parked message loops wake periodically to
service timers.

---

*Ratified (2026-07-26): checked against the IBM Toolkit 4.5 header `H/pmwin.h` and the IBM
DOSCALL1.DLL EXEHDR dumps. Confirmed and upgraded to [DOC-IBM]: the `QMSG` layout
(`pmwin.h:900-911`) and every `Win*` message-API prototype cited above (`WinSendMsg` :1035,
`WinCreateMsgQueue` :1040, `WinGetMsg` :1054, `WinPeekMsg` :1060 with `PM_REMOVE`/`PM_NOREMOVE`
:1101-1102, `WinDispatchMsg` :1067, `WinPostMsg` :1070). Left [OBS-RE] (no IBM primary found): the
DOSCALL1 590/591 ordinal names (EXEHDR names them by ordinal only; the names come from osFree/EDM2
RE), and the internal `SleepPmq`/`SetWakeBit`/event-semaphore block-wake mechanism and the periodic
tick — all still PMMERGE RE.*

## See also
- `pm-window-messaging.md` — the `Win*` message API layered on this queue; `pm-graphics.md` — the draw path `WM_PAINT` triggers.
