# OS/2 Memory Model — Arenas and Selectors

The 32-bit OS/2 virtual address space, its arenas, and the segmented (selector:offset) addressing
the 16-bit ABI still uses. Established during kernel initialization (boot-sequence Stage 2).

Provenance: **[DOC-IBM]** IBM redbook GG24-3730 *OS/2 Version 2.0 Volume 1: Control Program*
(the arena map, the GDT/LDT split, the tiling algorithm); **[DOC-IBM]** IBM OS/2 Warp Server SMP
programming-reference addendum (the high-memory arenas); **[DOC-IBM]** IBM Toolkit `bsememf.h`
(`OBJ_TILE`).

Ratified (2026-07-26): checked against IBM redbook GG24-3730,
the OS/2 Warp Server SMP addendum, and the OS/2 Toolkit 4.5
header `bsememf.h`. The arena map, the 512 MB system/process split, the GDT-system/LDT-application
split, the 8192-entry tiled LDT, the 64 KB tile granularity, and the 16:16⇄0:32 conversion formula
were all confirmed in IBM primaries and upgraded to `[DOC-IBM]` (details at each site). The
`VIRTUALADDRESSLIMIT` range was corrected against the SMP addendum. The version-specific
shared-arena sub-region *hints* (0x14000000 etc.) were searched for but **not** found in any IBM
source and remain `[OBS-RE]`.

Added 2026-07-29, after that pass: §"Address space vs. committed storage". It restates claims
already sourced in this doc, `memory-api.md`, and `infoseg.md` and asserts nothing new against a
primary; its cites point at those sites.

## Virtual address space [DOC-IBM (redbook GG24-3730) / OBS-RE]

The 4 GB space splits at **512 MB (0x20000000)** into a **process region** (below) and the **system
region** (above): IBM redbook GG24-3730 §"Virtual Memory Management" — *"The system arena contains
all the memory objects that are in the system region. It maps the virtual address space between
512MB and 4GB."* (glossary "system region": *"the address region above 512MB, which is reserved for
operating system use"*; "compatibility region": the region below 512 MB). The process region holds
the per-process **private arena** (*"starts at the lowest address of the process region … and has a
minimum size of 64MB"*, grows up) and the **shared arena** (*"allocated starting at the top end of
the process region and moves down towards the private arena … minimum size of 64MB"*); their
internal boundary is dynamic — *"the upper limit of the private arena and the lower limit of the
shared move towards one another."* [DOC-IBM — GG24-3730 §"Virtual Memory Management",
IBM redbook GG24-3730 §"Virtual Memory Management".] The 512 MB / system-region split,
the min-64 MB arena sizes, and the grow-toward-each-other boundary are `[DOC-IBM]`; the specific
numeric internal sub-boundaries in the table below are `[OBS-RE]` (KDB observation on the real
kernel — not stated in IBM sources).

| Range | Region / arena | Contents |
|---|---|---|
| 0x00000000 – 0x00010000 | NULL-pointer guard | reserved |
| 0x00010000 – ~0x04000000 | **private arena** (grows up) | per-process: `.EXE`, heap, thread stacks (≥ 64 MB, expandable) |
| ~0x04000000 – 0x13000000 | expansion region | where the dynamic private/shared boundary moves |
| 0x13000000 – 0x20000000 | **shared arena** (grows down) | DLLs, named shared memory, system semaphores |
| 0x20000000 – 0xFFFC0000 | **system arena** | ring-0 (kernel) |
| 0xFFFC0000 – 0xFFFFFFFF | hardware reserved | BIOS / hardware |

> **High-memory arenas** (Warp Server SMP / for e-business; later Warp 4 fixpacks; eCS / ArcaOS):
> the process region is extended above 0x20000000 — *"a high private arena at the low end and a high
> shared arena at the high end … the high private arena grows up and the high shared arena grows
> down"* — up to the CONFIG.SYS `VIRTUALADDRESSLIMIT`, raising the system region accordingly.
> ~~"commonly 1024–3072 MB"~~ **corrected 2026-07-26 (Rule 1.7):** the SMP addendum gives the
> **default 2048** MB (2 GB) — a later fixpack lowered the shipped default to 1024 MB — and a
> **maximum 3072** MB (3 GB); values are rounded up to a 64 MB boundary, and *"no memory objects can
> span the 512 MB line."* Objects above 512 MB start on a 4 KB boundary and are **not** tileable
> (16-bit code cannot address them); objects below start on a 64 KB boundary and are tileable.
> [DOC-IBM — OS/2 Warp Server SMP programming-reference addendum, §"High Memory Support" /
> §"VIRTUALADDRESSLIMIT Parameter in CONFIG.SYS" / §"Implementation Details",
> OS/2 Warp Server SMP addendum §042–045. Also *Inside OS/2 Warp Server for e-business*,
> SG24-5393 (not held locally).]

### Shared-arena sub-regions [OBS-RE]
Version-specific (Warp 4 / V3 FP19) region hints, not a hard ABI: R/W-basing at 0x14000000,
global-shared (read-only) 0x18000000–0x1C000000, 16-bit packed code at 0x19000000, pre-based DLLs at
0x1A000000; the shared arena tops out at 0x1FFF0000 (512 MB − 64 KB).

## Address space vs. committed storage [DOC-IBM]

Two different ceilings are both called "memory", and the arena map above bounds only the first:

- **Address space** is a *per-process* limit fixed by the 32-bit architecture: the private arena,
  the shared arena, and — where high-memory support is present — the high arenas, up to
  `VIRTUALADDRESSLIMIT` (3072 MB maximum). No amount of installed RAM widens it; a 32-bit pointer
  cannot reach further.
- **Committed storage** is a *machine-wide* limit. Reserving address space costs no storage;
  committing a page guarantees backing for it out of one pool of physical memory plus swap that
  every process on the system draws from (`memory-api.md` §"The committed / reserved / decommitted
  model" `[DOC]`). It is indifferent to which process's arena the address came from.

The arena map is asymmetric between the two. Only the **private** arena is per-process; the
**shared** arena (DLLs, named shared memory, system semaphores) and the **system** arena above
512 MB are one instance for the whole machine — a shared object occupies the same linear address in
every process that maps it. So a process can exhaust shared address space with its private arena
nearly empty (many DLLs loaded system-wide), or exhaust its private arena on a machine with
gigabytes free. Neither failure is about installed RAM.

OS/2's own API keeps the two families apart. In `DosQuerySysInfo` (`infoseg.md`),
`QSV_TOTPHYSMEM` / `TOTRESMEM` / `TOTAVAILMEM` report **storage**, machine-wide — the last is
explicitly *available for all processes*; `QSV_MAXPRMEM` / `MAXSHMEM`, and their high-memory
counterparts `QSV_MAXHPRMEM` / `MAXHSHMEM`, report **address space** *for the calling process*.
Reading a per-process figure as a machine-wide one, or the reverse, is the usual source of
confusion.

`ERROR_NOT_ENOUGH_MEMORY` (`8`) is returned for **both** conditions — *"no address space / no
storage to commit"* (`memory-api.md` §"Error codes" `[DOC-IBM bseerr.h]`) — so the return code alone
does not distinguish them. An allocation that fails in the low hundreds of MB on a machine with RAM
to spare has hit an arena or tiling boundary (`OBJ_TILE` confines an allocation to the first 512 MB),
not a storage shortage; compare `QSV_MAXPRMEM` / `MAXSHMEM` against `QSV_TOTAVAILMEM` to tell which.

## Selectors — GDT for the system, LDT for applications [DOC-IBM / OBS-RE]

OS/2 uses the **GDT for system/kernel selectors** and a **per-process LDT for application, DLL, and
shared-memory selectors**. The split is documented: the GDT stores *"the segment base addresses of
all memory segments in the system … used by the operating system … not available to processes
executing in the system,"* while the LDT stores *"the segment base addresses for memory segments
used by the current process"* [DOC-IBM — GG24-3730 glossary "global descriptor table" / "local
descriptor table", IBM redbook GG24-3730 p.298, `314`]. *That the SAS and specific kernel
structures sit at particular GDT selectors is `[OBS-RE]` (KDB on the real kernel).* An
application/shared selector is an LDT, ring-3 selector, constructed as `(index << 3) | 7`
(TI = 1, RPL = 3), from a tiled LDT of **up to 8192 descriptors** [DOC-IBM — GG24-3730 §"Address
Conversion and Translation": *"A tiled LDT contains up to 8192 descriptors";* the `| 7` low bits
match IBM's `far16 = MAKEP(HIGH(near32) << 3 + 7, LOW(near32))`, IBM redbook GG24-3730 p.088].
Descriptors for shared objects are inserted downward from the top of the LDT and private-object
descriptors upward from the bottom, mirroring the arena layout [DOC-IBM — same page].

## Segmentation and tiling [DOC-IBM / OBS-RE]

16-bit code addresses memory as **selector:offset**. To let 16-bit and 32-bit code share the same
storage, 16-bit segments are **tiled at 64 KB granularity** — IBM: *"A tiled LDT contains up to 8192
descriptors, where the segment base address in each descriptor is a multiple of 64KB, and each
descriptor therefore points to a 64KB region of memory … each code or data selector reserves a full
64KB of linear address space."* A flat linear address `L` corresponds to the tiled selector whose
base is `L & ~0xFFFF` with offset `L & 0xFFFF`, i.e. the selector index is a function of the linear
address (`sel = ((L >> 16) << 3) | 7`). This is exactly IBM's arithmetic:
*`near32 = SEL(far16) >> 3 << 16 + OFFSET(far16)`* and
*`far16 = MAKEP(HIGH(near32) << 3 + 7, LOW(near32))`*. A 16:16 far pointer thus converts to a 32-bit
flat pointer, and vice-versa, deterministically; both the LDT entry (16:16) and the page-table entry
(0:32) translate to the same physical memory. The 0x10000 (64 KB) tile granularity is the recurring
unit of the 16-bit segment model. [DOC-IBM — GG24-3730 §"Address Conversion and Translation",
IBM redbook GG24-3730 p.088; glossary "tiled local descriptor table" `362`.]

`DosAllocMem` allocates page-granular memory in the private (or, with the shared flag, shared) arena;
`OBJ_TILE` (`0x00000040`, IBM Toolkit `bsememf.h:55`, in the default `fALLOC` mask) requests
placement in the first 512 MB so the region is addressable by a 16:16 tiled selector for 16-bit
callers — IBM: below the 512 MB line objects *"start on a 64 KB boundary … and the memory will be
tileable,"* above it they are 4 KB-granular and untileable. [DOC-IBM — `bsememf.h:55`; SMP addendum
§"New OBJ_ANY Memory Attribute", OS/2 Warp Server SMP addendum §044.]

## See also
- `memory-api.md` — the application-level `Dos*` memory API (`DosAllocMem`, `DosAllocSharedMem`, `DosSetMem`) that allocates within these arenas.
- `infoseg.md` — `DosQuerySysInfo`, whose `QSV_*` fields report the machine-wide storage figures and the per-process address-space figures separately.
