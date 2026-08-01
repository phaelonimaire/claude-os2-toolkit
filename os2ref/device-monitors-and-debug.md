# OS/2 Device Monitors and the DosDebug Interface

Two specialized Control Program facilities that reach inside the running system: **device
monitors**, by which an application inserts itself into a character device's data stream to
filter it (keystrokes, mouse packets, printer output) as the data flows through the driver; and
**DosDebug**, by which one process controls the execution of another — reads and writes its
memory and registers, sets breakpoints and watchpoints, single-steps it, and receives a stream of
event notifications. Both are cooperative, kernel-mediated mechanisms: the monitor rides a chain
managed by the *monitor dispatcher* inside the character device driver, and the debugger drives a
debuggee that the loader has marked as debug-controlled.

Provenance: **[DOC-IBM]** the IBM OS/2 *Control Program Programming Reference* (the `DosDebug`
chapter and the `MONITORPOSITION` structure), the IBM *Physical Device Driver Reference* (the
"OS/2 Monitor Mechanism" chapter — monitor chains, the dispatcher, DosMon\* semantics), and the
device-driver reference's Category 10/11 monitor IOCtls. Symbols, constant values, struct fields
and prototypes are confirmed against the version-correct Toolkit 4.5 header `bsedos.h`
(the `uDB` structure and the `DBG_C_*` / `DBG_N_*` constants) and against the IBM DDK 16-bit
include `BSEDOS.INC` (the `DosMon*` prototypes, the `MONITOR_*` placement flags, `HMONITOR`,
`MONIN`/`MONOUT`) and `bseord.h` (MONCALLS ordinals). Cited inline as `file:line`.

The `DosMon*` family is a **16-bit family API** (library `MONCALLS`, loaded at privilege level 2);
it is absent from the 32-bit Toolkit 4.5 `bsedos.h` and is documented here from the IBM books plus
the DDK 16-bit include. `DosDebug` is a 32-bit Control Program API.

---

## Part 1 — Device Monitors

### The model [DOC-IBM]

A **device monitor** is an application that intercepts and filters the data passing through a
character device (keyboard `KBD$`, mouse `MOUSE$`, parallel port). It does not replace the driver;
it splices itself into the driver's **data stream** so that every data record flows *through* the
monitor before reaching (input devices) or after leaving (output devices) the device's normal API
buffers.

Monitors intercepting the same data stream are linked into a **monitor chain**. The first monitor
in the chain receives data directly from the physical device driver, filters it, and passes it to
the next monitor; the last monitor returns the filtered data to the driver. The driver defines its
own data streams and decides how monitors chain onto them — the keyboard and mouse drivers keep a
separate monitor chain **per OS/2 session**; the parallel-port driver keeps two chains per printer
(pddref.txt:962, :1061, :1063). Presentation Manager sessions are special: PM manages keystrokes
and mouse clicks itself and does **not** create monitor chains for its sessions, so an application
cannot register a keystroke or mouse monitor against a PM session (pddref.txt:1068-1070).

The mechanism has two halves that meet inside the kernel-resident **monitor dispatcher**
(pddref.txt:1108-1130):

| Half | Who calls it | The five entry points |
| --- | --- | --- |
| **MONCALLS** monitor dispatcher functions | the monitor application (ring 2/3) | `DosMonOpen`, `DosMonReg`, `DosMonRead`, `DosMonWrite`, `DosMonClose` |
| **Monitor Dispatcher DevHlp** services | the character device driver (ring 0) | `MonitorCreate`, `Register`, `DeRegister`, `MonWrite`, `MonFlush` |

The application never talks to the driver directly; the dispatcher relays registration and
termination to the driver through the file system and the IOCtl interface, and moves data records
between adjacent monitors on the chain transparently (pddref.txt:1130-1138, :1214).

```
   Application X address space
   ┌───────────────────────────┐
   │  Monitor Y                 │
   │   private data area        │
   └──▲───────────────┬─────────┘
      │ DosMonRead(3) │ DosMonWrite(4)          ring 2/3
 ─────┼───────────────┼───────────────────────────────────
      │               │                          ring 0
   ┌──┴───────────────▼─────────┐
   │     Monitor Dispatcher      │
   │      (Device Helper)        │
   └──▲───────────────┬─────────┘
 MonWrite(2)          │(5)
      │               │
   ┌──┴──────────┐ ┌──▼──────────────┐
   │ Char Device │ │  Monitor Chain   │
   │  Driver Z   │ │     Buffer       │
   └─────────────┘ └──────────────────┘
    INT(1) write        read(6)
```
*(pddref.txt:1266-1310 — data flow through a one-monitor chain)*

### The application's five calls {DosMon\* -> purpose} [DOC-IBM]

| Function | Purpose |
| --- | --- |
| `DosMonOpen` | Obtain an `HMONITOR` handle to a named character device for monitoring. Internally issues a `DosOpen` distinguished by an `08h` value in the request-packet Status field; the driver may create its monitor chain here (pddref.txt:1339). One call per device — repeated opens of the same device return the same handle (pddref.txt:1350). |
| `DosMonReg` | Register a monitor's input/output buffer pair onto a chain, given the handle, a **placement flag**, and an **index** selecting which chain (e.g. session number). Until this returns, no data enters the monitor's input buffer (pddref.txt:1370). |
| `DosMonRead` | Take one data record from the data stream into a private data area for filtering, optionally waiting for the dispatcher's "data available" signal (pddref.txt:1375-1379). |
| `DosMonWrite` | Return one filtered data record from the private area to the data stream, waiting if the stream is full (pddref.txt:1418-1424). |
| `DosMonClose` | Close the device handle (via `DosClose`); the driver de-registers **all** the application's monitors from every chain. Implicit on process exit even without an explicit call (pddref.txt:1442-1461). |

Prototypes and the placement-flag constants, confirmed in the DDK 16-bit include
(IBM DDK `BSEDOS.INC`):

```c
/* MONCALLS — 16-bit FAR PASCAL; guarded by INCL_DOSMONITORS.  BSEDOS.INC:1240-1275 */
USHORT DosMonOpen (PSZ pszDevName, PHMONITOR phmon);                       /* ord 4 */
USHORT DosMonClose(HMONITOR hmon);                                        /* ord 3 */
USHORT DosMonReg  (HMONITOR hmon, PBYTE pbInBuf, PBYTE pbOutBuf,
                   USHORT fPosition, USHORT usIndex);                     /* ord 5 */
USHORT DosMonRead (PBYTE pbInBuf,  USHORT fWaitFor, PBYTE pbDataBuf, PUSHORT pcbData); /* ord 2 */
USHORT DosMonWrite(PBYTE pbOutBuf, PBYTE pbDataBuf, USHORT cbData);       /* ord 1 */
```
*(Ordinals within MONCALLS from `bseord.h`: `ORD_DOSMONWRITE 1`, `ORD_DOSMONREAD 2`,
`ORD_DOSMONCLOSE 3`, `ORD_DOSMONOPEN 4`, `ORD_DOSMONREG 5` — bseord.h:170-176.)*

`HMONITOR` is a `WORD` handle (BSEDOS.INC:1245).

### Placement flags {constant -> value} [DOC-IBM]

`DosMonReg`'s `fPosition` selects where the monitor's buffers sit on the chain, relative to
monitors already registered (BSEDOS.INC:1241-1243):

| Constant | Value | Effect |
| --- | --- | --- |
| `MONITOR_DEFAULT` | `0x0000` | No positional preference; placed relative to existing monitors. |
| `MONITOR_BEGIN` | `0x0001` | Toward the **head** of the chain (nearest the device / raw data). |
| `MONITOR_END` | `0x0002` | Toward the **tail** of the chain (nearest the driver's API buffers). |

The PDD reference names these DEFAULT / FIRST / LAST and describes the stacking rule: the first
monitor registered FIRST is at the head; the next FIRST registration follows it; symmetrically for
LAST (pddref.txt:1495-1520). That reference also lists values 3, 4, 5 as further DEFAULT/FIRST/LAST
encodings carrying special dispatcher-processing requirements (pddref.txt:1500-1503); the base
symbolic constants above (0/1/2) are what the DDK header defines.

### Monitor buffers and data records [DOC-IBM]

The application allocates the **input buffer** (used by `DosMonRead`) and **output buffer** (used
by `DosMonWrite`) from the *same* data segment. The **first WORD of each buffer** must hold the
length of the private data area **plus 20 bytes**, that length WORD inclusive; the minimum is the
driver's monitor-chain-buffer length plus 20 (pddref.txt:1363, :1477-1481). The dispatcher does not
retain these buffers after registration — their addresses thereafter serve only as the **handle**
identifying which monitor is calling `DosMonRead`/`DosMonWrite` (pddref.txt:1481). If the buffer is
too small, `DosMonReg` returns `ERROR_MON_BUFFER_TOO_SMALL` and places the driver's required buffer
size in the **second WORD**; the documented idiom is to register once with a 4-byte buffer to learn
the size, then re-register with a correctly sized one (pddref.txt:1475, :1487).

A **monitor data record** is built by the physical device driver and is variable length: a **flag
WORD**, optionally followed by device data. The flag WORD tells the monitor the record's data type
and the action expected of it; because drivers have specific requirements for returning records,
**a monitor must not indiscriminately consume records** (pddref.txt:1394-1398). Maximum record
length is the driver's monitor-chain-buffer length minus 2 bytes.

A **flush record** — a single flag WORD with the third bit of its first byte set — is the only
record the *dispatcher itself* injects, on the driver's behalf, to guarantee the stream is drained.
It must pass through every monitor: a monitor that receives it must return it via `DosMonWrite`
after acting on it. **If a flush record is not returned, the data stream is severely and permanently
affected** (pddref.txt:1400-1404). While a flush record is in flight, the dispatcher blocks the
driver from adding new data until the flush has traversed the whole chain.

Thread-safety within one process is provided by the dispatcher: only one thread of a process at a
time may read from (or write to) a data stream, so an application need not serialize its own
`DosMonRead`/`DosMonWrite` calls (pddref.txt:1406, :1430). During termination, a thread blocked in
`DosMonRead`/`DosMonWrite` is awakened with an error return that the application must handle.

### The driver side and the IOCtl bridge [DOC-IBM]

To support monitors a character device driver must, per data stream, create a **monitor chain**
(`DevHlp_MonitorCreate`), define a **monitor chain buffer** in its first data segment (where fully
filtered data lands), and define a **notification routine** in its first code segment (called by
the dispatcher when filtered data reaches the chain buffer) (pddref.txt:1193). Registration and
termination arrive at the driver as **Category 10 (Character Device Monitor)** and Category 11
IOCtls relayed by the dispatcher through the file system:

| IOCtl | Meaning |
| --- | --- |
| Category 0Ah, Function 40h — Register Monitor (`MON_REGISTERMONITOR`) | Sent when the app calls `DosMonReg`. The driver reads the data packet — **Placement Flag** (WORD), **Index** (WORD), **Address of Input Buffer** (DWORD), **Offset of Output Buffer** (WORD) — puts them in registers and calls `DevHlp_Register` (cpgref.txt:41952-42024). |
| Category 11h, Function 60h — Query Monitor Support | Reports whether the device supports monitors (cpgref.txt:42045). |

The register data packet is the `MONITORPOSITION` structure on the application side
(cp2.txt:10913):

```c
typedef struct _MONITORPOSITION {
  USHORT  fPosition;   /* Placement flag (see MONITOR_* above)             */
  USHORT  index;       /* Which monitor chain — driver-defined (e.g. session#) */
  ULONG   pbInBuf;     /* Address of the input buffer                       */
  USHORT  offOutBuf;   /* Offset of the output buffer (same segment as input)*/
} MONITORPOSITION;
```

The driver may return `NO_MONITOR_SUPPORT` (`0x8112`), `BAD_COMMAND` (`0x8103`) or
`GENERAL_FAILURE` (`0x810C`) in the request-packet status when registration fails
(cpgref.txt:42011-42017). On `DosMonClose` (or process exit) the file system sends a monitor-close
request — distinguished, like open, by the `08h` Status value — and the driver calls
`DevHlp_DeRegister` for each of its chains (pddref.txt:1448-1454).

---

## Part 2 — DosDebug

### The controlling/debuggee model [DOC-IBM]

`DosDebug` lets one process (the **debugger**) control the execution of another (the **debuggee**)
and examine or modify its memory, registers, and threads. A process is marked debug-controlled
**when it is started**: `DosExecPgm` and `DosStartSession` each carry a flag requesting that the
child be controlled by the caller (cp2.txt:14709-14717). A debugger can also `DBG_C_Connect` to a
child it started, or `DBG_C_Attach` to an already-running task. The debugger can reach specific
threads within the debuggee and specific processes within a controlled session, and can use the
ordinary session/process controls (`DosSelectSession`, etc.) to move itself or the debuggee to the
foreground.

The whole interface is a single call taking one buffer:

```c
APIRET APIENTRY DosDebug(PVOID pDbgBuf);   /* bsedos.h:538 */
```

The buffer's **`Cmd` field is bidirectional**: on entry it holds a **command** (`DBG_C_*`); on a
successful return it holds a **notification** (`DBG_N_*`) describing the event that occurred.
Not every field is meaningful for every command, and the same field carries different meanings for
different commands (cp2.txt:14819-14823). A `DosDebug` that returns `APIRET` 0 still may report a
per-command failure by returning `Cmd = DBG_N_Error` with an `ERROR_*` code in `Value`
(cp2.txt:14916).

### The debug buffer (`uDB`) [DOC-IBM]

The sole parameter. Its front carries command operands; its back is a full 80386 register/segment
snapshot filled by `DBG_C_ReadReg` and consumed by `DBG_C_WriteReg`. Confirmed field-for-field in
`bsedos.h:230-280` (`struct _uDB`) and cp2.txt:8444-8497.

```c
typedef struct _uDB {
    ULONG  Pid;      /* debuggee process id                    */
    ULONG  Tid;      /* debuggee thread id                     */
    LONG   Cmd;      /* command in / notification out          */
    LONG   Value;    /* generic data value (word for ReadMem/WriteMem, chance code, error) */
    ULONG  Addr;     /* debuggee linear address                */
    ULONG  Buffer;   /* debugger-side buffer address           */
    ULONG  Len;      /* length of a range / buffer             */
    ULONG  Index;    /* generic identifier / object number     */
    ULONG  MTE;      /* module table entry handle              */
    ULONG  EAX,ECX,EDX,EBX,ESP,EBP,ESI,EDI,EFlags,EIP;  /* register set */
    /* per segment: byte-granular Lim, byte-granular Base, Acc byte, Atr byte, selector */
    ULONG  CSLim; ULONG CSBase; UCHAR CSAcc; UCHAR CSAtr; USHORT CS;
    ULONG  DSLim; ULONG DSBase; UCHAR DSAcc; UCHAR DSAtr; USHORT DS;
    ULONG  ESLim; ULONG ESBase; UCHAR ESAcc; UCHAR ESAtr; USHORT ES;
    ULONG  FSLim; ULONG FSBase; UCHAR FSAcc; UCHAR FSAtr; USHORT FS;
    ULONG  GSLim; ULONG GSBase; UCHAR GSAcc; UCHAR GSAtr; USHORT GS;
    ULONG  SSLim; ULONG SSBase; UCHAR SSAcc; UCHAR SSAtr; USHORT SS;
} uDB_t;
```

The book also names it `DosDebug Buffer` / `DBUGBUF` and shows it inlined as `struct debug_buffer`
in the worked example (cp2.txt:8446, :14742).

### Commands {DBG_C_\* -> value / action} [DOC-IBM]

Placed in `Cmd` on entry. Values from `bsedos.h:292-330`.

| Command | Value | Action |
| --- | --- | --- |
| `DBG_C_Null` | 0 | No operation. |
| `DBG_C_ReadMem` / `_ReadMem_I` | 1 | Read a word from the debuggee at `Addr` into `Value`. |
| `DBG_C_ReadMem_D` | 2 | Read a word (data-space form of 1). |
| `DBG_C_ReadReg` | 3 | Read the debuggee thread's full register/segment set into the `uDB`. |
| `DBG_C_WriteMem` / `_WriteMem_I` | 4 | Write the word in `Value` to the debuggee at `Addr`. |
| `DBG_C_WriteMem_D` | 5 | Write a word (data-space form of 4). |
| `DBG_C_WriteReg` | 6 | Write the register/segment set from the `uDB` into the thread. |
| `DBG_C_Go` | 7 | Resume execution until an event; returns a notification. |
| `DBG_C_Term` | 8 | Terminate the debuggee. |
| `DBG_C_SStep` | 9 | Single-step one instruction. |
| `DBG_C_Stop` | 10 | Stop; also drains one pending notification (returns `DBG_N_Success` when none remain). |
| `DBG_C_Freeze` / `DBG_C_Resume` | 11 / 12 | Freeze / thaw a specific thread (`Tid`). |
| `DBG_C_NumToAddr` / `DBG_C_AddrToObject` | 13 / 28 | Object number ↔ address / address → object (returns `MTE`; `DBG_O_OBJMTE` flags MTE validity). |
| `DBG_C_ReadCoRegs` / `DBG_C_WriteCoRegs` | 14 / 15 | Read / write coprocessor (387) registers (`DBG_CO_387`, buffer `DBG_LEN_387` = 108). |
| `DBG_C_ThrdStat` | 17 | Get thread status (`TStat`: `DbgState`, `TState`, `TPriority`). |
| `DBG_C_MapROAlias` / `DBG_C_MapRWAlias` / `DBG_C_UnMapAlias` | 18 / 19 / 20 | Map a read-only / read-write alias of debuggee memory into the debugger, and unmap it. |
| `DBG_C_Connect` | 21 | Connect to a debuggee started under debug control (`Value = DBG_L_386`, =1). |
| `DBG_C_ReadMemBuf` / `DBG_C_WriteMemBuf` | 22 / 23 | Read / write a range (`Len` bytes at `Addr` ↔ debugger `Buffer`). |
| `DBG_C_SetWatch` / `DBG_C_ClearWatch` | 24 / 25 | Set / clear a watchpoint (scope+type in `Value`). |
| `DBG_C_RangeStep` | 26 | Step until execution leaves an address range. |
| `DBG_C_Continue` | 27 | Acknowledge an exception/notification and continue (with an `XCPT_CONTINUE_*` disposition). |
| `DBG_C_XchgOpcode` | 29 | Exchange an opcode (software breakpoint) and go. |
| `DBG_C_LinToSel` / `DBG_C_SelToLin` | 30 / 31 | 32-bit linear ↔ 16-bit selector:offset conversion. |
| `DBG_C_Attach` / `DBG_C_Detach` | 33 / 34 | Attach to an already-running task / cleanly detach and resume it. |
| `DBG_C_RegDebug` / `DBG_C_QueryDebug` | 35 / 36 | Register / query the per-process or global JIT debugger (`JIT_REG_*`, `DBGQ_JIT_*`). |

(`DBG_C_RegisterSemList` = 32 is marked internal-use-only in the header.)

### Notifications {DBG_N_\* -> value} [DOC-IBM]

Returned in `Cmd` on a successful `DosDebug`. Values from `bsedos.h:369-382`.

| Notification | Value | Meaning |
| --- | --- | --- |
| `DBG_N_Success` | 0 | Command completed; also "no more pending notifications." |
| `DBG_N_Error` | -1 | Error during command (see `Value` for the `ERROR_*` code). |
| `DBG_N_ProcTerm` | -6 | Debuggee process exiting — exit-list already run. |
| `DBG_N_Exception` | -7 | Exception in the debuggee (faulting `Tid` in `Tid`; chance in `Value`). |
| `DBG_N_ModuleLoad` | -8 | A module was loaded (`MTE` handle supplied). |
| `DBG_N_CoError` | -9 | Coprocessor not in use. |
| `DBG_N_ThreadTerm` | -10 | A thread is exiting (exit-list soon). |
| `DBG_N_AsyncStop` | -11 | Asynchronous stop detected. |
| `DBG_N_NewProc` | -12 | A new (descendant) process started under control. |
| `DBG_N_AliasFree` | -13 | An alias needs to be freed. |
| `DBG_N_Watchpoint` | -14 | A watchpoint fired. |
| `DBG_N_ThreadCreate` | -15 | A new thread was created. |
| `DBG_N_ModuleFree` | -16 | A module was freed. |
| `DBG_N_RangeStep` | -17 | A range step completed. |

### Watchpoints and exception "chances" [DOC-IBM]

`DBG_C_SetWatch` takes a combined **scope** + **type** value in `Value` (bsedos.h:477-486):

| Group | Constant → value |
| --- | --- |
| Scope | `DBG_W_Global` 0x1, `DBG_W_Local` 0x2 |
| Type | `DBG_W_Execute` 0x10000, `DBG_W_Write` 0x20000, `DBG_W_ReadWrite` 0x30000 |

A `DBG_N_Exception` is delivered under one of four **chance** dispositions, reported in `Value`
(bsedos.h:531-534): `DBG_X_PRE_FIRST_CHANCE` (0 — the debugger's own breakpoint/single-step, before
the debuggee sees it), `DBG_X_FIRST_CHANCE` (1), `DBG_X_LAST_CHANCE` (2), `DBG_X_STACK_INVALID` (3).
For the pre-first-chance cases `Addr` holds the breakpoint/next-instruction address and `Buffer`
holds `XCPT_BREAKPOINT` or `XCPT_SINGLE_STEP`; for first/last chance, `Buffer` and `Len` point at
the exception report and context records in the debuggee's own address space (bsedos.h:504-528).

### Serialization protocol [DOC-IBM]

The command/notification exchange is a strict handshake (cp2.txt:14825-14834, :14912):

- Some events (`DBG_N_ModuleLoad`, `DBG_N_NewProc`, `DBG_N_ThreadCreate`, …) can be **pending in
  bulk**; they are delivered before the debuggee runs any more user code and are drained one per
  return on `DBG_C_Go`, `DBG_C_SStep`, or `DBG_C_Stop`.
- Every notification **other than** `DBG_N_Success` / `DBG_N_Error` must be **acknowledged with
  `DBG_C_Continue`** before execution can resume or the next notification can be retrieved. A
  `DBG_C_Go` issued while notifications are pending fails; the debugger loops `Continue` + `Go`
  until it sees the event it wants.
- Per task, all `DosDebug` subcommands are serialized; a multithreaded debugger may drive
  *different* tasks concurrently.

Worked idiom — drain all pending notifications after connecting (cp2.txt:14923-14933):

```
DBG_C_Connect
DBG_C_Stop
while (uDB.Cmd != DBG_N_Success) {   /* Stop returns Success when none remain */
    DBG_C_Continue with XCPT_CONTINUE_STOP
    DBG_C_Stop
}
```

### `DBG_C_Attach` vs `DBG_C_Connect` [DOC-IBM]

`DBG_C_Connect` is for a task the debugger *started* (parent/child); it yields the full startup
notification sequence including per-module init events. `DBG_C_Attach` grabs an **already-running**
task: no `DBG_C_Connect` is needed (Attach performs the connection), there is no parent/child
relationship, and the debuggee gets `DBG_N_ModuleLoad` for every already-loaded module plus
`DBG_N_ThreadCreate` for every active thread — but **no module-init notifications**, since the task
is already past `_main` (cp2.txt:14847-14877). `DBG_C_Detach` is the only command that cleanly turns
debugging off and resumes the task; `DBG_C_Term` kills it (cp2.txt:14893).

### Worked example — write a word into a debuggee [DOC-IBM]

With `Pid`, `Addr`, and `Value` already set up so the caller controls the target
(cp2.txt:14795-14817):

```c
DbgBuf.Cmd   = DBG_C_WriteMem;   /* command */
DbgBuf.Pid   = ulPID;            /* which debuggee   */
DbgBuf.Addr  = ulAddr;           /* where            */
DbgBuf.Value = lValue;           /* the word to write*/
ulrc = DosDebug(&DbgBuf);
if (ulrc != 0) { /* API-level failure */ }
/* else inspect DbgBuf.Cmd for the DBG_N_* notification returned */
```

---

## Sources

- **[DOC-IBM]** IBM OS/2 *Control Program Programming Reference* — extracted book text
  `cp2.txt`: the `DosDebug` chapter ("About/Using Debugging", the worked example, the
  serialization and Attach/Connect protocol, the `DosDebug Buffer` field reference) at
  `:8444-8710` and `:14700-14975`; the `MONITORPOSITION` structure at `:10913-10965`.
- **[DOC-IBM]** IBM *Physical Device Driver Reference* — extracted book text `pddref.txt`:
  "The OS/2 Monitor Mechanism" and the `DosMon*` semantics, `:930-1620`.
- **[DOC-IBM]** IBM device-driver reference — `cpgref.txt`: Category 10 Function 40h (Register
  Monitor) data packet and return codes, `:41940-42045`.
- Confirmation of symbols/values/prototypes:
  - Toolkit 4.5 `bsedos.h` — `struct _uDB` (`:230-280`),
    `DBG_C_*` (`:292-330`), `DBG_N_*` (`:369-382`), `TStat`, `DBG_W_*` / `DBG_X_*` / `DBG_O_*` /
    `DBG_CO_387` / `DBG_LEN_387` (`:409-534`), `DosDebug` prototype (`:538`).
  - 16-bit include IBM DDK `BSEDOS.INC` —
    `MONITOR_DEFAULT/BEGIN/END`, `HMONITOR`, `MONIN`/`MONOUT`, and the five `DosMon*` prototypes
    (`:1240-1275`).
  - DDK IBM DDK `bseord.h` (16-bit) — MONCALLS
    ordinals (`:170-176`).

## See also
- `kernel-services.md` — the `DevHlp` monitor services on the driver side; `drivers.md` — the device drivers a monitor attaches into.
