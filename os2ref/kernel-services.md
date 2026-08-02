# OS/2 Kernel Services - DevHlp and the DOSCALLS Surface

The two kernel service planes: **DevHlp** (the API device drivers call) and the **DOSCALLS** kernel
entries behind the `Dos*` API. Available once the kernel is initialized (boot-sequence Stage 3).

Provenance: **[DOC-IBM]** IBM DDK `devhlp.inc` (DevHlp numbers) and `dhcalls.h` (prototypes), the PDD
reference book; **[OBS-RE]** the real debug kernel `os2krnl` + symbols (which services are
kernel-implemented, and the "secretly-kernel" wakes).

Ratified (2026-07-26): DevHlp names/numbers checked against the DDK `devhlp.inc`
(`base/inc/devhlp.inc`, 16-bit set = 102 `DevHlp_* EQU` defines; the SMP/32-bit
`base32/.../inc/devhlp.inc` + `video/.../inc/devhlp.inc` for the spinlock/`Port_IO` entries) and
`dhcalls.h` (`base/h/dhcalls.h`, C prototypes); the context-hook register/segment contract against
the PDD reference book (`DDK/HTML/REF/PDD/00226.HTM` AllocateCtxHook, `00230.HTM` ArmCtxHook); the
clock against Toolkit 4.5 `bsedos.h`. Every named DevHlp resolved to a real `EQU`; one name was
corrected (`AllocateGDTSelector`->`AllocGDTSelector`); the `DATETIME` layout was confirmed at 11
bytes. The `[OBS-RE]` sections (DOSCALLS entry count, forwarder rule, "secretly-kernel" wakes /
DOSCALL1 ordinals) were left `[OBS-RE]` - not sourced to an IBM primary this pass.

## DevHlp - the driver-facing API [DOC-IBM]

The kernel exports **~103 DevHlp routines** - named `DevHlp_*` in the DDK `devhlp.inc` (`DevHlp_*
EQU` defines), grouped by family (DevHlp code numbers below are the `EQU` values, [DOC-IBM]
`devhlp.inc`). ([DOC - EDM2 "Category_DevHlps"] enumerates **138** wiki pages under its DevHlps
category - a superset that also documents name variants and services without an `EQU` number; the
`devhlp.inc` count of ~103 numbered routines is retained here as the authority.)

- **Memory / selector** - `VirtToLin` (91), `PhysToVirt` (21), `VMAlloc` (87) / `VMFree` (88) /
  `VMLock` (85), `VMGlobalToProcess` (90) / `VMProcessToGlobal` (89) (the per-process aperture
  primitive), `AllocGDTSelector` (45) *(this doc previously said "AllocateGDTSelector"; the DDK
  canonical name is `DevHlp_AllocGDTSelector` / C `DevHelp_AllocGDTSelector` - `devhlp.inc:84`,
  `dhcalls.h:88`)*, `LinToGDTSelector` (92), `PhysToGDTSelector` (46), `GetDescInfo` (93),
  `VerifyAccess` (39).
- **Synchronization** - `SemRequest` (6) / `SemClear` (7), `OpenEventSem` (103) / `PostEventSem`
  (105) / `ResetEventSem` (106), `PMPostEventSem` (112, code 0x70), `CreateSpinLock` (121, 0x79) /
  `AcquireSpinLock` (113, 0x71) / `ReleaseSpinLock` (114, 0x72) (SMP; also `FreeSpinLock` 122).
- **Scheduling / deferral** - `Yield` (2), `ModifyPriority` (44), and the context-hook (DPC)
  primitive `AllocateCtxHook` (99) / `ArmCtxHook` (101) / `FreeCtxHook` (100) (defer work from
  interrupt to task time).
- **Timers** - `SetTimer` (29) / `ResetTimer` (30), `TickCount` (51), `RegisterTmrDD` (97).
- **Registration / IDC** - `AttachDD` (42), `RegisterPDD` (80), `RegisterDeviceClass` (67),
  `AllocReqPacket` (13).
- **Interrupt / hardware** - `SetIRQ` (27) / `EOI` (49), `Port_IO` (118, 0x76), `GetLIDEntry` (52),
  `ABIOSCall` (54).
- **Monitors** - `MonitorCreate` (31) / `MonWrite` (34) / `MonFlush` (35) (splice into an input
  stream, e.g. KBD).

### Per-service purpose and entry/exit contract [DOC - EDM2]

The DevHlp interface is a register ABI: the caller loads registers, sets `DL` to the DevHlp code,
and does `CALL [Device_Help]`. The assembler-level entry/exit contract for the services below is
recorded on their EDM2 pages (each service one-line purpose + register grammar). The carry flag
(`C`) is the pass/fail indicator throughout: `C` clear = success, `C` set = error, with the error
code returned in `EAX`/`AX`.

**Memory / selector** [DOC - EDM2 "DevHelp_VMAlloc", "DevHelp_VMFree", "DevHelp_VMLock",
"DevHelp_VMGlobalToProcess", "DevHelp_VMProcessToGlobal", "DevHelp_VirtToPhys", "DevHelp_VirtToLin",
"DevHelp_AllocGDTSelector"]:

| Service | Purpose | Entry | Exit (C clear) |
|---|---|---|---|
| `VMAlloc` | Allocate global Ring-0 virtual memory; commit physical storage, or map VM to a given physical address | `EAX`=Flags (`VMDHA_*`: 16MB/FIXED/SWAP/CONTIG/PHYS/PROCESS/SGSCONT/RESERVE/USEHIGHMEM), `ECX`=Size (bytes), `EDI`=offset of dword holding physaddr to map (-1 if unused) | `EAX`=linear address (error `ERROR_INVALID_PARAMETER`=87). Global address space unless `VMDHA_PROCESS`; process-space memory can only be swapped |
| `VMFree` | Free a `VMAlloc` region *or* a `VMGlobalToProcess`/`VMProcessToGlobal` mapping | `EAX`=linear address of region | - |
| `VMLock` | Verify accessibility and lock a region into physical memory (optionally blocking) | `EBX`=linear addr, `ECX`=length, `EDI`=offset of `PageList` array, `ESI`=offset of 12-byte lock handle, `EAX`=ActionFlags | `EAX`=`PageList` element count. Contiguous locks: length <= 64 KB; rounds to page boundaries |
| `VMGlobalToProcess` | Map a global (system-region) address into the current process's address space (the per-process aperture primitive) | `EBX`=global linear addr, `ECX`=length, `EAX`=ActionFlags | `EAX`=process linear addr. Release with `VMFree`; range must not cross object boundaries |
| `VMProcessToGlobal` | Convert a process-space address to a global system-region address for interrupt-time access independent of process context | `EBX`=process linear addr, `ECX`=length, `EAX`=ActionFlags | `EAX`=global offset. Range must be page-aligned and not cross object boundaries |
| `VirtToPhys` | Convert a `selector:offset` to a 32-bit physical address | `selector:offset` pair | `AX:BX`=physical address. Segment should be locked first (`DevHlp_Lock`) |
| `VirtToLin` | Convert a `selector:offset` to a linear address | `AX`=selector, `ESI`=offset | `EAX`=linear address |
| `AllocGDTSelector` | Allocate a set of GDT selectors (at driver INIT time only) | `ES:DI`=16:16 addr of selector array, `CX`=count | array filled; on error `AX`=error code. C: `DevHelp_AllocGDTSelector(PSEL Selectors, USHORT Count)` |

**Scheduling / deferral** [DOC - EDM2 "DevHelp_ProcRun", "DevHelp_TCYield", "DevHelp_AllocateCtxHook"]:

| Service | Purpose | Entry | Exit |
|---|---|---|---|
| `ProcRun` | Companion to `ProcBlock`; wake all threads blocked on an event id | `AX:BX`=event id (high:low) | `AX`=count of threads awakened |
| `TCYield` | Like `Yield`, but yield the CPU only to a time-critical thread if one is available | (none) | - |
| `AllocateCtxHook` | Allocate a context hook for task-time processing when no task-time thread is available | `EAX`=hook-handler 16-bit offset (zero-extended), `EBX`=0xFFFFFFFF | `EAX`=hook handle (passed to `ArmCtxHook`). Handler saves/restores its own registers (see below) |

**Interrupt / hardware** [DOC - EDM2 "DevHelp_SetIRQ", "DevHelp_UnSetIRQ", "DevHelp_ABIOSCall",
"DevHelp_Save_Message", "DevHelp_VideoPause", "DevHelp_ROMCritSection", "DevHelp_RegisterKrnlExit"]:

| Service | Purpose | Entry / notes |
|---|---|---|
| `SetIRQ` | Bind a hardware IRQ vector to the driver's interrupt handler | `AX`=handler offset (CS-relative), `BX`=IRQ level (0-Fh), `DH`=shared flag (0=not shared, 1=shared); `DS`=driver data segment. IRQ range-checked; `C` set if out of 0-Fh |
| `UnSetIRQ` | Remove the current handler for an IRQ | `BX`=IRQ number; `C` set if caller is not an owner of the IRQ *(not previously listed in this doc)* |
| `ABIOSCall` | Start an ABIOS function (Operating System Transfer Convention) | `AX`=LID, `SI`=request-block offset in data segment, `DH`=entry point; `DS`=driver data segment |
| `Save_Message` | Display a message from a base PDD on the system console | `DS:SI`=message table |
| `VideoPause` | On a DMA overrun, start/stop high-priority (video-transfer) threads so diskette DMA can terminate | `AL`=on/off flag |
| `ROMCritSection` | Flag a critical section in a PDD's DOS-mode software interrupt handler; prevents DOS-mode being suspended in the background | - |
| `RegisterKrnlExit` | Register a driver exit to handle NMIs, Trap 2 parity errors, and Ring-0 System Fatal Faults | `AX`=exit flags, `CX`=exit type, `BX:SI`=selector:offset of the user exit; exit must return control to the OS |

**Registration / IDC** [DOC - EDM2 "DevHelp_RegisterPDD", "DevHelp_RegisterDeviceClass"]:

| Service | Purpose | Entry | Exit |
|---|---|---|---|
| `RegisterPDD` | Register a 16:16 PDD name + communication entry point with the DOS Session Manager for PDD<->VDD communication (a VDD later opens it via `VDHOpenPDD`) | `DS:SI`=ASCIIZ PDD name, `ES:DI`=PDD's communication entry point | `AX`=0 on success. Re-register with a NULL function pointer to remove the registration |
| `RegisterDeviceClass` | At INIT, register the driver's direct-call command-handler entry point with the kernel | `AX:BX`=ptr to DirectCall handler, `DI`=device flags (0 for an ADD), `CX`=device class (1 for an ADD) | `AX`=device (ADD) handle; on error `AX`=`ERROR_NOT_ENOUGH_MEMORY`. EDM2's assembler label for this call is `DevHlp_RegisterADD` |

**Queues / events** [DOC - EDM2 "DevHelp_QueueInit", "DevHelp_SendEvent"]:

| Service | Purpose | Entry |
|---|---|---|
| `QueueInit` | Initialize a character-queue structure | `BX`=offset (in DS) of the queue structure |
| `SendEvent` | Called by a PDD to signal the occurrence of an event | `AH`=event type, `BX`=event argument |

### The virtual DevHlp (VDH*) plane [DOC - EDM2 "C_Language_Virtual_DevHlp_Services"]

Separate from the physical-driver DevHlp interface above, the kernel exposes a second service plane -
the **virtual DevHlp services (`VDH*`)** - for *virtual* device drivers (VDDs) running the
V8086/DOS-session environment. EDM2's *C Language Virtual DevHlp Services* reference groups them by
category: DMA, DOS Session Control, DOS Settings, DPMI, File/Device I/O, GDT Selector, Hook
Management, Idle DOS-Application Management, Inter-Device-Communication, Keyboard, Memory Management
(byte-granular / page-granular / memory-locking), Miscellaneous, Parallel-Port and Printer,
Semaphore, Timer, Virtual Interrupt, and V8086 Stack Manipulation. (`RegisterPDD` above is the
PDD-side half of the PDD<->VDD channel these services complete.)

### Context hooks (the DPC primitive) [DOC-IBM PDD ref - `HTML/REF/PDD/00226.HTM`, `00230.HTM`]
A driver in interrupt/callback context has no task-time thread. `AllocateCtxHook` registers a
handler; `ArmCtxHook(HookData, HookHandle)` (DevHlp code 0x65 = 101) arms it, and the kernel later
runs the handler **at task time** with `EAX = HookData`, `EBX = 0xFFFFFFFF`. The handler runs
non-preemptibly, must set DS to the driver's data segment, and must reside in the same segment as
the `AllocateCtxHook` call. All confirmed against the PDD reference: ArmCtxHook (`00230.HTM`) and the
Hook_Handler entry contract on AllocateCtxHook (`00226.HTM` - "EAX = Value passed on the ArmCtxHook
DevHelp call in EAX; EBX = 0FFFFFFFFH, reserved value; ... The Hook_Handler cannot be preempted. The
DS register must be set to the physical device driver's data segment ... must reside in the same
segment in which the AllocateCtxHook is made").

EDM2 corroborates this contract and adds the C-level shape: `DevHelp_AllocateCtxHook(NPFN
HookHandler, PULONG HookHandle)`, the handler is entered with `EAX` = the value passed to
`ArmCtxHook` and `EBX` = 0xFFFFFFFF, the handler **saves and restores its own registers** on
entry/exit, and the handler address is **zero-extended** when moved into `EAX`. [DOC - EDM2
"DevHelp_AllocateCtxHook"]

## DOSCALLS - the kernel side of the `Dos*` API [OBS-RE]

The kernel exports ~122 `DOS32*` entries. Note that many `*CALLS.DLL` modules are **thin
forwarders**: e.g. `QUECALLS.DLL` forwards the queue APIs into `DOSCALL1.DLL`, where they are
implemented at ring-3 on top of kernel shmem/sem primitives - the queue is *not* a kernel service.
The rule: **the kernel's own symbol table is the authority for "is this a kernel service,"** not the
DLL that exports the name.

## "Secretly kernel" services - cross-process wakes [OBS-RE]

A family of services one might assume are library code but which are kernel-implemented, identifiable
by the signature *a wake tied to an event originating in another address space*:

- **PM input wake** - `PMPostEventSem` / DOSCALL1 ordinals 590/591 (`Dos32PMPostEventSem` /
  `Dos32PMWaitEventSem`): the event-sem the PM input queue blocks on.
- **Change-notify** - `DosOpenChangeNotify` / `DosResetChangeNotify`: kernel-implemented directory
  watch; a filesystem change in one process wakes a waiter in another.
- **Hard-error / popup** - a driver/FS error is formatted by the kernel and wakes the
  session-manager hard-error thread (another process) to raise the popup.
- **Named pipes** - a write in one process wakes a blocked reader in another (a fully-kernel IPC,
  unlike the ring-3 queue).
- **Mux-wait semaphores** - wake when any of N constituent semaphores (possibly posted by another
  process) is posted.
- **Device monitors** - device data flows through a monitor chain living in other processes.

## The clock [DOC-IBM]

`DosGetDateTime` / `DosSetDateTime` (both `APIRET APIENTRY ...(PDATETIME pdt)`) operate on the 11-byte
`DATETIME`: `UCHAR hours, minutes, seconds, hundredths, day, month; USHORT year; SHORT timezone;
UCHAR weekday` (1+1+1+1+1+1+2+2+1 = 11). Confirmed against Toolkit 4.5 `bsedos.h` (`struct _DATETIME`
lines 2090-2101, prototypes lines 2104/2106). The InfoSeg time fields and `QSV_TIMER_INTERVAL`
(`bsedos.h:2521` - QSV #22, "Timer interval in tenths of ms") expose the periodic tick (see
`infoseg.md`).

## See also
- `timers.md` - the interval/async timer APIs (`DosSleep`, `DosAsyncTimer`, `DosStartTimer`) and the tick model built on the system clock above.
