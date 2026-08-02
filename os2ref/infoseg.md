# OS/2 Information Segments and DosQuerySysInfo

The read-only system and process state OS/2 publishes for applications to query: the **Global
Information Segment (GIS)**, the per-process **Local Information Segment (LIS)**, and the flat
**`DosQuerySysInfo`** surface. Established during kernel initialization (boot sequence Stage 2).

Provenance: **[DOC-IBM]** IBM DDK `infoseg.h` (`COMBASE/DDK/base/h/infoseg.h`, IBM 1992) for the
InfoSeg layouts; IBM Toolkit 4.5 `bsedos.h` for the `DosQuerySysInfo` indices and prototype. IBM
canonical field names.

Ratified (2026-07-26): checked field-by-field against IBM DDK `COMBASE/DDK/base/h/infoseg.h`
(`struct InfoSegGDT` lines 36-115, `struct InfoSegLDT` lines 183-222, `#ifdef SMP` `LIS_pTIB`/
`LIS_pPIB` lines 215-218, `LIS_PT_*`/`LIS_PS_EXITLIST`/`LF_LOG*` lines 254-282), IBM Toolkit 4.5
`bsedos.h` (`QSV_*` 2499-2531, `DosQuerySysInfo` prototype 2610-2613), and the IBM
Toolkit 4.5 import library `os2386.lib` (IMPDEF -> DOSCALLS ordinal 348). SMP-vs-UNI
split corroborated by the OS/2 for SMP book (section DosQuerySysInfo, `QSV_NUMPROCESSORS`
= "Number of processors in the machine"). Every GIS/LIS offset, both structure sizes (0x72 = 114,
36 UNI / 44 SMP), and all 31 QSV indices matched the IBM sources exactly; nothing was corrected.
No IBM primary was found in os2undoc for the InfoSeg (absent - the DDK header remains the source).

## Semantics [DOC-IBM]

- The **GIS** is kept in **two identical copies** - one in the tiled **shared arena** (user-mode
  readable, and therefore potentially overwritable from ring 2) and one in the **system arena**
  (kernel-only). All kernel code maintains both. The clock device driver obtains the read/write
  copy via the DevHlp `GetDOSVar`; all other requestors receive a read-only selector.
  `DosGetInfoSeg` returns a pointer/selector to the shared-arena copy.
- The **LIS** is per-process, in the private arena, **updated at context-switch time**; only the
  currently running process holds the live extra copy.

## Global Information Segment - `InfoSegGDT`, 114 bytes (0x72) [DOC-IBM]

| Off | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `SIS_BigTime` | ULONG | time in seconds since 1970-01-01 |
| 0x04 | `SIS_MsCount` | ULONG | free-running millisecond counter |
| 0x08 | `SIS_HrsTime` / `SIS_MinTime` / `SIS_SecTime` / `SIS_HunTime` | 4xUCHAR | hours / minutes / seconds / hundredths |
| 0x0C | `SIS_TimeZone` | USHORT | minutes from GMT (set to EST) |
| 0x0E | `SIS_ClkIntrvl` | USHORT | timer interval, units of 0.0001 s |
| 0x10 | `SIS_DayDate` / `SIS_MonDate` | 2xUCHAR | day (1-31) / month (1-12) |
| 0x12 | `SIS_YrsDate` | USHORT | year (>= 1980) |
| 0x14 | `SIS_DOWDate` | UCHAR | day of week (1-1-80 = Tue = 3) |
| 0x15 | `SIS_VerMajor` / `SIS_VerMinor` / `SIS_RevLettr` | 3xUCHAR | major / minor version, revision letter (20 / 45 = Warp 4.5) |
| 0x18 | `SIS_CurScrnGrp` | UCHAR | foreground screen-group number |
| 0x19 | `SIS_MaxScrnGrp` | UCHAR | maximum number of screen groups |
| 0x1A | `SIS_HugeShfCnt` | UCHAR | shift count for huge segments |
| 0x1B | `SIS_ProtMdOnly` | UCHAR | protect-mode-only indicator |
| 0x1C | `SIS_FgndPID` | USHORT | foreground process id |
| 0x1E | `SIS_Dynamic` | UCHAR | dynamic-priority-variation flag |
| 0x1F | `SIS_MaxWait` | UCHAR | maxwait (seconds) |
| 0x20 | `SIS_MinSlice` / `SIS_MaxSlice` | 2xUSHORT | minimum / maximum timeslice (ms) |
| 0x24 | `SIS_BootDrv` | USHORT | drive the system was booted from (1 = A) |
| 0x26 | `SIS_mec_table[32]` | 32 B | RAS Major Event Code table |
| 0x46 | `SIS_MaxVioWinSG` / `SIS_MaxPresMgrSG` | 2xUCHAR | max VIO-windowable / Presentation-Manager screen groups |
| 0x48 | `SIS_SysLog` | USHORT | error-logging status (`LF_LOGENABLE` 0x01, `LF_LOGAVAILABLE` 0x02) |
| 0x4A | `SIS_MMIOBase` | USHORT | memory-mapped-I/O selector |
| 0x4C | `SIS_MMIOAddr` | ULONG | memory-mapped-I/O address |
| 0x50 | `SIS_MaxVDMs` | UCHAR | max Virtual DOS Machines |
| 0x51 | `SIS_Reserved` | UCHAR | - |
| 0x52 | `SIS_perf_mec_table[32]` | 32 B | performance MEC table (added 1997) |

Total 0x72 = 114 bytes.

## Local Information Segment - `InfoSegLDT`; 36 bytes UNI, **44 bytes SMP** [DOC-IBM]

Per-process; the SMP kernel appends `LIS_pTIB` / `LIS_pPIB` (IBM DDK `infoseg.h`, `#ifdef SMP`).

| Off | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `LIS_CurProcID` / `LIS_ParProcID` | 2xUSHORT | current / parent process id |
| 0x04 | `LIS_CurThrdPri` / `LIS_CurThrdID` | 2xUSHORT | current thread priority / thread id |
| 0x08 | `LIS_CurScrnGrp` | USHORT | screen group |
| 0x0A | `LIS_ProcStatus` | UCHAR | process-status bits (`LIS_PS_EXITLIST` 0x01) |
| 0x0B | `LIS_fillbyte1` | UCHAR | filler |
| 0x0C | `LIS_Fgnd` | USHORT | process is in foreground |
| 0x0E | `LIS_ProcType` | UCHAR | 0 full-screen / 1 real-mode / 2 VIO-windowable / 3 Presentation Manager / 4 detached |
| 0x0F | `LIS_fillbyte2` | UCHAR | filler |
| 0x10 | `LIS_AX`...`LIS_DS` | 7xUSHORT | .EXE-derived: environment selector, command-line offset, data-segment length, STACKSIZE, HEAPSIZE, module handle, data-segment handle |
| 0x1E | `LIS_PackSel` / `LIS_PackShrSel` / `LIS_PackPckSel` | 3xUSHORT | first tiled / above-shared-arena / above-packed-arena selector |
| **0x24** | **`LIS_pTIB`** | ULONG | **[SMP] flat pointer to the current TIB** |
| **0x28** | **`LIS_pPIB`** | ULONG | **[SMP] flat pointer to the PIB** |

UNI ends at 0x24 (36); SMP ends at 0x2C (44).

## `DosQuerySysInfo` - QSV indices 1-31 [DOC-IBM]

`DosQuerySysInfo` - prototype `APIRET APIENTRY DosQuerySysInfo(ULONG iStart, ULONG iLast, PVOID
pBuf, ULONG cbBuf)` (IBM Toolkit 4.5 `bsedos.h:2610-2613`); imported by ordinal **348** from
module **DOSCALLS** (IBM Toolkit 4.5 `os2386.lib`, OMF IMPDEF record: internal name
`DosQuerySysInfo`, module `DOSCALLS`, import-by-ordinal 348). On Warp 4.5 `QSV_MAX =
QSV_INT10ENABLED = 31` (`bsedos.h:2530-2531`); the Warp-v3 Toolkit stops at 25.

| # | Name | Meaning / units |
|---|---|---|
| 1 | `QSV_MAX_PATH_LENGTH` | maximum path length |
| 2-4 | `QSV_MAX_TEXT_SESSIONS` / `MAX_PM_SESSIONS` / `MAX_VDM_SESSIONS` | session limits |
| 5 | `QSV_BOOT_DRIVE` | 1 = A, 2 = B, ... |
| 6 | `QSV_DYN_PRI_VARIATION` | 0 = absolute, 1 = dynamic |
| 7 | `QSV_MAX_WAIT` | seconds |
| 8-9 | `QSV_MIN_SLICE` / `MAX_SLICE` | milliseconds |
| 10 | `QSV_PAGE_SIZE` | bytes |
| 11-13 | `QSV_VERSION_MAJOR` / `_MINOR` / `_REVISION` | version, revision letter |
| 14 | `QSV_MS_COUNT` | free-running millisecond counter |
| 15-16 | `QSV_TIME_LOW` / `TIME_HIGH` | low / high dword of time in seconds |
| 17-19 | `QSV_TOTPHYSMEM` / `TOTRESMEM` / `TOTAVAILMEM` | physical / resident / available-for-all-processes memory |
| 20-21 | `QSV_MAXPRMEM` / `MAXSHMEM` | available private / shared memory for the calling process |
| 22 | `QSV_TIMER_INTERVAL` | **tenths of a millisecond** |
| 23 | `QSV_MAX_COMP_LENGTH` | max length of one path component |
| 24-25 | `QSV_FOREGROUND_FS_SESSION` / `FOREGROUND_PROCESS` | foreground session id / process id |
| 26 | `QSV_NUMPROCESSORS` | processor count (an SMP kernel on one CPU reports 1) |
| 27-28 | `QSV_MAXHPRMEM` / `MAXHSHMEM` | high (> 512 MB) private / shared memory |
| 29 | `QSV_MAXPROCESSES` | maximum processes |
| 30 | `QSV_VIRTUALADDRESSLIMIT` | virtual-address limit |
| 31 | `QSV_INT10ENABLED` | INT 10h (VGA BIOS) video enabled |

## See also
- `memory-model.md` - the arenas and selectors the InfoSegs live in; `boot-sequence.md` (Stage 2) - where they are published.
