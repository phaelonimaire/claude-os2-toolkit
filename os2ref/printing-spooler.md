# OS/2 Printing and the Spooler

How an OS/2 Presentation Manager (PM) application prints. Printing in OS/2 is
*device-independent*: the same `Gpi*` drawing calls that render a picture on the screen
render it on a printer or plotter, because both are reached through a **device context**
(`HDC`). To print, an application opens a device context onto a printer with `DevOpenDC`,
associates a GPI presentation space with it, brackets its drawing with document/page
**device escapes** (`DevEscape`), and closes the context — at which point the **spooler**
holds the job in a queue and a **queue processor** feeds it, through the printer driver, to
the physical device. A lower layer, the `SplQm*` spooler API, lets an application (or a
printer driver) submit already-formatted data to a queue directly, bypassing the GPI. This
reference documents the queued/direct/info device-context model, the `DEVOPENSTRUC`
open data, the job-property and capability queries, the `DevEscape` document/page brackets,
and the spooler submission APIs.

Provenance: **[DOC-IBM]** the OS/2 Toolkit 4.5 headers `pmdev.h`, `pmspl.h`, and the base
header `os2def.h` (every prototype, structure, constant *value*, and message id below is
transcribed from them, cited `file:line`); **[DOC-IBM]** the IBM *OS/2 Presentation Manager
Programming Reference* (`pm1.txt`) and *Programming Guide — Graphics Programming Interface*
(`gpi4.txt`) for the API *semantics* and the print-job flow. Where a behavioural claim comes
from the book rather than a header it is tagged with the book. Canonical IBM names are used
throughout.

---

## 1. The printing model — two routes to a queue [DOC-IBM]

An application can put a print job into a spooler queue two ways:

- **Through the GPI (the normal route).** Open a *queued* device context with `DevOpenDC`
  (`lType = OD_QUEUED`), associate a presentation space, and draw with the ordinary `Gpi*`
  functions. The output is captured into a **spool file** in the printer driver's format and
  submitted to the queue when the document ends. This is the device-independent, WYSIWYG
  path and the one almost all applications use. [DOC-IBM — *GPI Programming Guide*, gpi4.txt]
- **Directly to the spooler (the special-purpose route).** Call `SplQmOpen` /
  `SplQmStartDoc` / `SplQmWrite` / `SplQmEndDoc` / `SplQmClose` to write **printer-specific
  data you have already formatted** straight into a spool file, bypassing the GPI
  presentation layer entirely. Normally only printer drivers or specialized applications do
  this, because the application must itself emit the printer's command stream.
  [DOC-IBM — *PM Programming Reference*, pm1.txt "SplQmOpen"]

A third variant, a **direct** device context (`OD_DIRECT`), still draws through the GPI but
sends the driver's output straight to a port (e.g. `LPT1`) instead of the spooler — used for
print-to-file and unspooled printing. An **information** context (`OD_INFO`) draws nothing;
it exists only to *query* a device (font metrics, hardcopy capabilities).

The queue itself is serviced by a **queue processor** (also called a queue driver) — the
default is **PMPRINT** (`PMPLOT` for vector plotters) — which reads the spool file and drives
the printer driver. [DOC-IBM — gpi4.txt "Opening a Queued Device Context"]

---

## 2. Opening a device context — `DevOpenDC` [DOC-IBM]

`DevOpenDC` creates a non-window device context and returns its `HDC`. (Screen windows use
`WinOpenWindowDC` instead — see `pm-window-messaging.md`.) A message queue must exist on the
calling thread before `DevOpenDC` is called. [DOC-IBM — pm1.txt "DevOpenDC - Remarks"]

```c
HDC APIENTRY DevOpenDC(HAB hab, LONG lType, PSZ pszToken,
                       LONG lCount, PDEVOPENDATA pdopData, HDC hdcComp);
```
Provenance: **[DOC-IBM]** `pmdev.h:213-226`.

| Parameter | Purpose |
|---|---|
| `hab` | Anchor-block handle from `WinInitialize`. |
| `lType` | Device-context type — one of the `OD_*` constants below. |
| `pszToken` | Device-information token naming a profile entry to seed the open data. The system behaves as if `"*"` (no profile info) is given; applications always pass `"*"` to force all device information to come from `pdopData`. [DOC-IBM — pm1.txt "DevOpenDC Parameter - pszToken"] |
| `lCount` | Number of elements supplied in `pdopData`. The minimum for a queued context is 4 (the first four `DEVOPENSTRUC` fields). |
| `pdopData` | Pointer to the open data — an array of `PSZ`, canonically the `DEVOPENSTRUC` structure (Section 3). |
| `hdcComp` | Compatible-DC handle; used only for `OD_MEMORY` (bitmap) contexts, else `NULLHANDLE`. For `OD_QUEUED` this must be `NULL`. |

**Return:** the `HDC` (`> 0`), or `DEV_ERROR` (`0`) on error. [DOC-IBM — pm1.txt "DevOpenDC
Return Value"; value `pmdev.h:68`]

### Device-context types (`OD_*`) [DOC-IBM `pmdev.h:76-83`]

| Constant | Value | Meaning |
|---|---|---|
| `OD_SCREEN` | `0` | Screen (opened via `WinOpenWindowDC`, not `DevOpenDC`). |
| `OD_QUEUED` | `2` | Printer/plotter whose output is **spooled** to a queue. |
| `OD_DIRECT` | `5` | Printer/plotter whose output is **not** queued (goes straight to a port/file). |
| `OD_INFO` | `6` | Query-only context: drawing is accepted but no medium is updated; used for capability/metric queries. |
| `OD_METAFILE` | `7` | Writes a metafile; the presentation page bounds the picture. |
| `OD_MEMORY` | `8` | An in-memory bitmap context (compatible with `hdcComp`). |
| `OD_METAFILE_NOQUERY` | `9` | Like `OD_METAFILE` but attribute queries are disallowed (faster; results of queries are undefined). |

The device context is **owned by the process** that opened it and cannot be used from another
process; it is deleted automatically at process exit if still open, but should be closed with
`DevCloseDC` (Section 7). Errors from `DevOpenDC` surface via `WinGetLastError`:
`PMERR_INV_DC_TYPE` (`0x2060`), `PMERR_INV_DC_DATA` (`0x205F`), `PMERR_INV_LENGTH_OR_COUNT`
(`0x2092`), `PMERR_INV_HDC` (`0x207C`). [DOC-IBM — pm1.txt "DevOpenDC - Errors"]

---

## 3. The open data — `DEVOPENSTRUC` and `DRIVDATA` [DOC-IBM]

`pdopData` is formally an array of `PSZ` values indexed by position; the named structure
`DEVOPENSTRUC` is the equivalent overlay and is what applications use. The positional indices
name each element for the array form:

| Index | Value | `DEVOPENSTRUC` field |
|---|---|---|
| `ADDRESS` | `0` | `pszLogAddress` |
| `DRIVER_NAME` | `1` | `pszDriverName` |
| `DRIVER_DATA` | `2` | `pdriv` |
| `DATA_TYPE` | `3` | `pszDataType` |
| `COMMENT` | `4` | `pszComment` |
| `PROC_NAME` | `5` | `pszQueueProcName` |
| `PROC_PARAMS` | `6` | `pszQueueProcParams` |
| `SPL_PARAMS` | `7` | `pszSpoolerParams` |
| `NETWORK_PARAMS` | `8` | `pszNetworkParams` |

Provenance: **[DOC-IBM]** `os2def.h:349-358`.

```c
typedef struct _DEVOPENSTRUC {   /* dop */
    PSZ        pszLogAddress;      /* queue name (OD_QUEUED) / port/file (OD_DIRECT) */
    PSZ        pszDriverName;      /* presentation-driver name, e.g. "LASERJET"      */
    PDRIVDATA  pdriv;              /* job-properties (driver data) block             */
    PSZ        pszDataType;        /* spool data type, e.g. "PM_Q_STD"               */
    PSZ        pszComment;         /* optional job comment shown to the user         */
    PSZ        pszQueueProcName;   /* optional queue processor, e.g. "PMPRINT"       */
    PSZ        pszQueueProcParams; /* optional queue-processor parameters (Section 6)*/
    PSZ        pszSpoolerParams;   /* optional spooler parameters (FORM=, PRTY=)      */
    PSZ        pszNetworkParams;   /* optional network parameters (USER=)            */
} DEVOPENSTRUC;
```
Provenance: **[DOC-IBM]** `os2def.h:362-374`.

Field semantics [DOC-IBM — gpi4.txt "Opening a Queued Device Context"]:

- **`pszLogAddress`** — for `OD_QUEUED`, the **queue name** (the `pszName` of the queue's
  `PRQINFO3`). For `OD_INFO` it is the **port** name. For `OD_DIRECT` it is the port or file
  name (`LPT1`, `C:\TMP\MYPRINT.DAT`, a UNC path, or a named pipe).
- **`pszDriverName`** — the presentation (printer) driver name up to the period, e.g.
  `LASERJET` (a queue's `pszDriverName` holds `driver.device`, such as
  `LASERJET.HP LaserJet IIID`).
- **`pdriv`** — a `DRIVDATA` block of **job properties** obtained from `DevPostDeviceModes`
  (Section 5) or the queue's default `pDriverData`. It is a **programming error to pass
  `NULL`**, because the `DRIVDATA` carries the specific device name.
- **`pszDataType`** — the spool-file data type; **`PM_Q_STD` is recommended** (Section 4).
- **`pszSpoolerParams`** — space-separated scheduling parameters: `FORM=A4,A5,ENV` (paper
  form names — the spooler holds the job until a matching form is installed) and `PRTY=nn`
  (job priority 1–99, default 50).

### `DRIVDATA` — the job-properties block [DOC-IBM `os2def.h:334-341`]

```c
typedef struct _DRIVDATA {   /* driv */
    LONG    cb;                 /* size of this block                       */
    LONG    lVersion;           /* driver-defined version                   */
    CHAR    szDeviceName[32];   /* device (model) name                      */
    CHAR    abGeneralData[1];   /* driver-private job properties, cb bytes  */
} DRIVDATA;
```

`abGeneralData` holds the printer driver's private job-property data (orientation,
resolution, form, bins). It is opaque to the application and **driver-specific**: job
properties from one driver must never be handed to another. [DOC-IBM — gpi4.txt "Job
Properties Considerations"]

For direct (`OD_DIRECT`) contexts, all `DEVOPENSTRUC` fields *after* `pdriv` are ignored, and
`pszLogAddress` is the destination port or file name. [DOC-IBM — gpi4.txt "Submitting a
Direct Presentation Manager Print Job"]

---

## 4. Spool data types — `PM_Q_STD` and `PM_Q_RAW` [DOC-IBM]

The `pszDataType` string names the format of the data stored in the spool file:

| Data type | Meaning |
|---|---|
| `"PM_Q_STD"` | **Standard** journalled GPI data — the queue processor replays the recorded drawing through the printer driver. This is the device-independent format and the recommended default. |
| `"PM_Q_RAW"` | **Raw** device-specific data — bytes already in the printer's own command language, passed through unchanged. Used with `DevEscape(DEVESC_RAWDATA)` or direct spooler submission. |

The strings are passed literally in `pszDataType`; they appear in the Toolkit header as the
documented data-type values (`pmspl.h:98`, `:117`, `:245`) and the maximum data-type name
length is `DTLEN` = 9 (`pmspl.h`, `INCL_SPLDOSPRINT`). A queue processor advertises the data
types it accepts via `SplQpQueryDt`. Provenance: **[DOC-IBM]** `pmspl.h:98,117,245`; semantics
**[DOC-IBM]** gpi4.txt "Opening a Queued Device Context" (recommends `PM_Q_STD`) and pm1.txt
`DevEscape` `DEVESC_RAWDATA`.

`PM_Q_RAW` jobs may bypass the queue processor entirely when it sets the `QP_RAWDATA_BYPASS`
(`0x00000001`) flag, allowing the job to print while still spooling. [DOC-IBM `pmspl.h:117`]

---

## 5. Preparing to print — device names, capabilities, and job properties [DOC-IBM]

Before opening the print DC, an application selects a printer (a queue), discovers its paper
forms, and (optionally) lets the user set job properties.

### 5.1 `DevQueryDeviceNames` — enumerate a driver's devices [DOC-IBM]

```c
BOOL APIENTRY DevQueryDeviceNames(HAB hab, PSZ pszDriverName,
                                  PLONG pldn, PSTR32 aDeviceName, PSTR64 aDeviceDesc,
                                  PLONG pldt, PSTR16 aDataType);
```
Provenance: **[DOC-IBM]** `pmdev.h:670-677`; semantics pm1.txt "DevQueryDeviceNames".

Asks a presentation driver (named by its fully-qualified `.DRV` file) for the device *models*
it supports and the data types it can produce. Called twice: with `*pldn`/`*pldt` = 0 it
returns the counts; with them non-zero it fills the arrays. `aDeviceName` (`STR32[]`) receives
model names, `aDeviceDesc` (`STR64[]`) their descriptions, `aDataType` (`STR16[]`) the
supported data-type strings (e.g. `PM_Q_STD`). Returns `TRUE`/`FALSE`. The `STR16`/`STR32`/
`STR64` array element types are the fixed-width string types `pmdev.h:604-610`.

### 5.2 `DevQueryHardcopyCaps` — paper forms and printable area [DOC-IBM]

```c
LONG APIENTRY DevQueryHardcopyCaps(HDC hdc, LONG lStartForm, LONG lForms, PHCINFO phciHcInfo);
```
Provenance: **[DOC-IBM]** `pmdev.h:679-682`; semantics pm1.txt "DevQueryHardcopyCaps".

Returns one `HCINFO` per supported **form** (paper size). With `lForms = 0` it returns the
*count* of forms; otherwise it fills `lForms` copies starting at form index `lStartForm`
(the first form is 0). Returns the number of forms (or `DQHC_ERROR` = `-1`, `pmdev.h:612`).
An application typically opens an `OD_INFO` context on the queue's driver just to make this
query, then closes it. [DOC-IBM — gpi4.txt example]

```c
typedef struct _HCINFO {   /* hci */
    CHAR   szFormname[32];  /* form name, e.g. "Letter"                     */
    LONG   cx;              /* paper width  (millimetres)                   */
    LONG   cy;              /* paper height (millimetres)                   */
    LONG   xLeftClip;       /* left clip limit                              */
    LONG   yBottomClip;     /* bottom clip limit                            */
    LONG   xRightClip;      /* right clip limit                             */
    LONG   yTopClip;        /* top clip limit                               */
    LONG   xPels;           /* pels across the printable (clip) area        */
    LONG   yPels;           /* pels down the printable area                 */
    LONG   flAttributes;    /* HCAPS_* form attributes                      */
} HCINFO;
```
Provenance: **[DOC-IBM]** `pmdev.h:619-632`.

`flAttributes` carries the form attribute bits [DOC-IBM `pmdev.h:616-617`]:

| Constant | Value | Meaning |
|---|---|---|
| `HCAPS_CURRENT` | `1` | This form is the one **currently installed** on the device. |
| `HCAPS_SELECTABLE` | `2` | This form is **selectable** (available from another paper bin). |

For the spooler to schedule a job, every form named in the `FORM=` spooler parameter must be
`HCAPS_CURRENT` or `HCAPS_SELECTABLE`, or the job is held with a *forms mismatch* error.
[DOC-IBM — pm1.txt "DevQueryHardcopyCaps"]

### 5.3 `DevPostDeviceModes` — the job-properties dialog [DOC-IBM]

```c
LONG APIENTRY DevPostDeviceModes(HAB hab, PDRIVDATA pdrivDriverData,
                                 PSZ pszDriverName, PSZ pszDeviceName,
                                 PSZ pszName, ULONG flOptions);
```
Provenance: **[DOC-IBM]** `pmdev.h:692-699`; semantics pm1.txt "DevPostDeviceModes".

Returns — and optionally lets the user set — the **job properties** for a device. The
returned data lands in `pdrivDriverData` (a `DRIVDATA` block) in exactly the format
`DevOpenDC` expects in `DEVOPENSTRUC.pdriv`. `pszDeviceName` (a 32-byte model name such as
`HP LaserJet IID`) overrides the `szDeviceName` in the passed `DRIVDATA`. `flOptions` selects
the action:

| Constant | Value | Action |
|---|---|---|
| `DPDM_POSTJOBPROP` | `0` | Display the driver's job-properties dialog and return the updated properties. |
| `DPDM_CHANGEPROP` | `1` | Change properties (without the interactive dialog). |
| `DPDM_QUERYJOBPROP` | `2` | Return the device's **default** job properties with no dialog. |

Provenance: **[DOC-IBM]** `pmdev.h:599-601`.

**Sizing convention:** passing `pdrivDriverData = NULL` makes the function *return the byte
size* required for the `DRIVDATA` block (so the caller can allocate it); a non-NULL pointer
makes it fill that block. Return values: `DPDM_ERROR` (`-1`), `DPDM_NONE` (`0`, no settable
options), a positive size (when `NULL` was passed), or `DEV_OK` (`1`). [DOC-IBM — pm1.txt
"DevPostDeviceModes Return Value"; values `pmdev.h:595-596,69`]

An application must **always store** the returned `DRIVDATA`, since it cannot tell whether the
user changed the properties or cancelled the dialog. The application is responsible for
persisting job properties (per-document or per-application). [DOC-IBM — pm1.txt]

---

## 6. Drawing the document — `DevEscape` document and page brackets [DOC-IBM]

Once a queued (or direct) DC is open and a presentation space is associated with it (via
`GpiAssociate`, or `GpiCreatePS` with `GPIA_ASSOC`), the application draws with ordinary
`Gpi*` calls, but must bracket the drawing with **device escapes** so the spooler and driver
know where documents and pages begin and end.

```c
LONG APIENTRY DevEscape(HDC hdc, LONG lCode, LONG lInCount, PBYTE pbInData,
                        PLONG plOutCount, PBYTE pbOutData);
```
Provenance: **[DOC-IBM]** `pmdev.h:654-659`.

`lCode` selects the escape; `pbInData`/`lInCount` pass input, `pbOutData`/`plOutCount` receive
output. The return is `DEVESC_ERROR` (`-1`), `DEVESC_NOTIMPLEMENTED` (`0`), or `DEV_OK`
(`1`). [DOC-IBM — pm1.txt "DevEscape Return Value"; values `pmdev.h:276-277,69`]

### The print-bracketing escapes [DOC-IBM `pmdev.h:280-329`; semantics pm1.txt "DevEscape - Remarks"]

| Escape | Value | Purpose / data |
|---|---|---|
| `DEVESC_STARTDOC` | `8150` | **Start a print job.** `pbInData` = null-terminated document name; all subsequent output is spooled under one job id until `DEVESC_ENDDOC`. `GpiAssociate` must already have been done. Any GPI calls made *before* it are ignored. |
| `DEVESC_ENDDOC` | `8151` | **End the job** started by `DEVESC_STARTDOC`. On return `pbOutData` receives a `USHORT` job identifier (`plOutCount` set to 2) if a spooler job was created. |
| `DEVESC_NEWFRAME` | `16300` | **Eject to a new page.** Resets attributes, bounds, and clip regions (like `GpiErase` for the screen); the driver always issues a page eject. |
| `DEVESC_ABORTDOC` | `8153` | **Abort the current job**, discarding everything written since (and including) the last `DEVESC_STARTDOC`; no queue job is created. Used when the user cancels. |
| `DEVESC_RAWDATA` | `16303` | **Send device-specific bytes** straight to the driver (`pbInData` = the raw printer data stream). Should not be mixed with GPI data on the same page — use a separate page (`DEVESC_NEWFRAME`) or document. |
| `DEVESC_QUERYESCSUPPORT` | `0` | Ask whether a given escape (its code in `pbInData`) is supported; the return value is the answer. |
| `DEVESC_GETSCALINGFACTOR` | `1` | Return x/y scaling factors (as powers of two) in an `SFACTORS` struct, for devices that cannot draw at full device resolution. |
| `DEVESC_SETMODE` | `16304` | Set a printer mode (code page / built-in font selection) via an `ESCMODE` struct (`pmdev.h:332`; "ESCSETMODE" is the PM-Reference name for the escape). Optional for drivers. |
| `DEVESC_QUERYVIOCELLSIZES` | `2` | Return the VIO cell sizes the driver supports (`VIOSIZECOUNT` + `VIOFONTCELLSIZE[]`). |

Other defined codes include `DEVESC_NEXTBAND` (`8152`), `DEVESC_GETJOBID` (`8160`),
`DEVESC_DRAFTMODE` (`16301`), `DEVESC_FLUSHOUTPUT` (`16302`), and the dynamic-job-property
variants `DEVESC_STARTDOC_WPROP` (`49150`) / `DEVESC_NEWFRAME_WPROP` (`49151`)
[DOC-IBM `pmdev.h:291-329`].

**Recording behaviour** depends on the DC type and data type. For an `OD_QUEUED` DC with a
`PM_Q_STD` spool file, some escapes are *sent to the driver* and some are *recorded in the
spool file* (each escape's description states which); for `OD_METAFILE` all escapes are
metafiled; for other DC types all escapes go straight to the driver. Application-defined
escape codes fall in ranges 32768–65535 whose sent/metafiled/recorded disposition is fixed by
the sub-range. `DEVESC_STARTDOC`/`ENDDOC`/`ABORTDOC` are *metafiled but not recorded*;
`DEVESC_NEWFRAME`/`RAWDATA`/`SETMODE` are *metafiled and recorded*. [DOC-IBM — pm1.txt
"DevEscape Parameter - lCode"]

`DevEscape` errors (via `WinGetLastError`): `PMERR_INV_ESC_CODE` (`0x206D`),
`PMERR_ESC_CODE_NOT_SUPPORTED` (`0x202B`), `PMERR_INV_ESCAPE_DATA` (`0x206E`),
`PMERR_INV_HDC` (`0x207C`), `PMERR_INV_LENGTH_OR_COUNT` (`0x2092`). [DOC-IBM — pm1.txt
"DevEscape - Errors"]

### Queue-processor parameters (`pszQueueProcParams`) [DOC-IBM — gpi4.txt "PMPRINT/PMPLOT Queue Processor Parameters"]

The optional space-separated parameters passed to the PMPRINT/PMPLOT queue processor control
how a `PM_Q_STD` job is rendered onto the page:

| Parameter | Meaning |
|---|---|
| `COP=n` | Number of copies (1–999; default 1). The only parameter valid for all data types. |
| `ARE=C` \| `w,h,l,t` | Output area: whole page (`C`, default) or width/height/left/top as percentages of the maximum printable area. |
| `FIT=S` \| `l,t` | Picture fit: scale-to-fit preserving aspect ratio (`S`, default) or position actual-size at a point given as percentages. |
| `XFM=0` \| `1` | Override (`0`) or honour (`1`, default) the `ARE`/`FIT` positioning. |
| `COL=M` \| `C` | Monochrome (`M`) or colour (`C`) output. |
| `MAP=N` \| `A` | Neutral-colour mapping: normal (`N`, white ground/black foreground) or reversed (`A`). |

---

## 7. The complete queued-print sequence [DOC-IBM — gpi4.txt "Submitting a Queued Presentation Manager Print Job"]

Printing is done on a **separate thread** (to keep the UI responsive). The canonical sequence:

```
DevOpenDC(hab, OD_QUEUED, "*", 4, &dop, NULL)   -> hdc
GpiAssociate(hps, hdc)          /* or GpiCreatePS with GPIA_ASSOC */
DevEscape(hdc, DEVESC_STARTDOC, ..., "MyDocument", ...)
    /* Gpi* drawing for page 1 */
DevEscape(hdc, DEVESC_NEWFRAME, ...)     /* eject; draw page 2; repeat */
    /* Gpi* drawing for page N */
DevEscape(hdc, DEVESC_ENDDOC, ...)       /* -> USHORT job id */
GpiAssociate(hps, NULLHANDLE)            /* disassociate */
DevCloseDC(hdc)
```

A **`DEVESC_STARTDOC`…`DEVESC_ENDDOC` pair creates exactly one queue job.** To create several
jobs from one open DC, repeat the STARTDOC…ENDDOC bracket before closing:
`DevOpenDC` → `GpiCreatePS` → (`STARTDOC` … `ENDDOC`) × N → `DevCloseDC`. If the user cancels,
call `DevEscape(DEVESC_ABORTDOC)` instead of `ENDDOC` — no job is created. Close the DC with:

```c
HMF APIENTRY DevCloseDC(HDC hdc);
```
Provenance: **[DOC-IBM]** `pmdev.h:228`; sequence gpi4.txt "Starting a Print Job"…"Closing
the Device Context". (`DevCloseDC` returns a metafile handle only for `OD_METAFILE` contexts;
otherwise `DEV_OK`/`DEV_ERROR`.) A DC opened with `DevOpenDC` must be closed with `DevCloseDC`
— never a `WinOpenWindowDC` context, which the system closes when the window dies.

The typical *setup* preceding this (from the print dialog) is: enumerate queues with
`SplEnumQueue` (each is a `PRQINFO3`), let the user pick one, obtain job properties with
`DevPostDeviceModes`, query forms with `DevQueryHardcopyCaps` on an `OD_INFO` context, then
open the `OD_QUEUED` context using the selected queue's name and driver. The default queue can
be read from the profile: `PrfQueryProfileString` with application `PM_SPOOLER`, key `QUEUE`.
[DOC-IBM — gpi4.txt "Printer Setup Dialog"]

---

## 8. The spooler API — direct job submission (`SplQm*`) [DOC-IBM]

The `SplQm*` ("spooler queue manager") family writes data **directly into a spool file**,
mirroring the DC/escape sequence but bypassing the GPI. A printer driver uses it to spool the
data it produces; an application uses it only when it emits printer-specific data itself.
Each `SplQm*` call corresponds to a step of the GPI path. [DOC-IBM — gpi4.txt "Submitting a
Print Job Directly to the Spooler"; pm1.txt "SplQmOpen"]

| Symbol | Prototype (`pmspl.h`) | Corresponds to | Purpose |
|---|---|---|---|
| `SplQmOpen` | `HSPL SplQmOpen(PSZ pszToken, LONG lCount, PQMOPENDATA pqmdopData)` | `DevOpenDC` | Open a spool file. `pqmdopData` is a `PQMOPENDATA` (= `PSZ *`, an array of ASCIIZ strings — queue name, app/document name, queue-processor params, …); `lCount` = the number of strings supplied. Returns an `HSPL` (or `SPL_ERROR`). |
| `SplQmStartDoc` | `BOOL SplQmStartDoc(HSPL hspl, PSZ pszDocName)` | `DevEscape(DEVESC_STARTDOC)` | Start a print job named `pszDocName`. |
| `SplQmWrite` | `BOOL SplQmWrite(HSPL hspl, LONG lCount, PVOID pData)` | — | Write `lCount` bytes of data into the spool file. |
| `SplQmNewPage` | `BOOL SplQmNewPage(HSPL hspl, ULONG ulPageNumber)` | `DevEscape(DEVESC_NEWFRAME)` | Mark the start of a new page. |
| `SplQmEndDoc` | `BOOL SplQmEndDoc(HSPL hspl)` | `DevEscape(DEVESC_ENDDOC)` | End the job; returns `ulJob`, a job id 1–65535 (or `SPL_ERROR`). |
| `SplQmAbortDoc` | `BOOL SplQmAbortDoc(HSPL hspl)` | `DevEscape(DEVESC_ABORTDOC)` | End (abort) the current print job. |
| `SplQmAbort` | `BOOL SplQmAbort(HSPL hspl)` | — | Stop generating the spool file; also closes it. |
| `SplQmClose` | `BOOL SplQmClose(HSPL hspl)` | `DevCloseDC` | Close the spool file. |
| `SplQmGetJobID` | `ULONG SplQmGetJobID(HSPL hspl, ULONG ulLevel, PVOID pBuf, ULONG cbBuf, PULONG pcbNeeded)` | — | Query the job identity/info for the open handle. |

Provenance: **[DOC-IBM]** `pmspl.h:684-733`; semantics pm1.txt "SplQmOpen/StartDoc/Write/
EndDoc/Close/Abort/AbortDoc/NewPage". `HSPL` = `LHANDLE` (`pmspl.h:96`). Return convention:
`BOOL` functions give `SPL_OK`/`SPL_ERROR` = `1`/`0` (`pmspl.h:92-93`).

The direct-submission sequence is therefore: `SplQmOpen` → `SplQmStartDoc` → `SplQmWrite`… →
`SplQmEndDoc` → `SplQmClose`. The logical-address element (`pszLogAddress`) names the target
queue. [DOC-IBM — gpi4.txt] Note that if the spooler is not active, directly submitted jobs
are never printed. [DOC-IBM — gpi4.txt]

The `SQPOPENDATA`/`PQPOPENDATA` block and the `QPDAT_*` indices (`pmspl.h:172-183`) are the
*queue processor's* view of the same open data — used inside a queue-processor DLL's
`SplQpOpen`, not by the printing application.

---

## 9. Recording `PM_Q_STD` data — the `SplStd*` family [DOC-IBM `pmspl.h:790-805`]

The `SplStd*` calls record `PM_Q_STD` (journalled GPI) data through a device context — the
mechanism a driver/queue-processor uses to capture or replay standard-format spool data. Unlike
`SplQm*` (which take an `HSPL`), these operate on an `HDC` and yield an `HSTD` metafile-style
handle.

| Symbol | Prototype | Purpose |
|---|---|---|
| `SplStdOpen` | `BOOL SplStdOpen(HDC hdc)` | Begin recording `PM_Q_STD` data on `hdc`. |
| `SplStdStart` | `BOOL SplStdStart(HDC hdc)` | Start a recording segment. |
| `SplStdStop` | `HSTD SplStdStop(HDC hdc)` | Stop recording; return the recorded-data handle (`HSTD`). |
| `SplStdGetBits` | `BOOL SplStdGetBits(HSTD h, LONG offData, LONG cbData, PCH pchData)` | Copy `cbData` bytes at `offData` out of the recorded data. |
| `SplStdQueryLength` | `LONG SplStdQueryLength(HSTD h)` | Total length of the recorded data (or `SSQL_ERROR` = `-1`). |
| `SplStdDelete` | `BOOL SplStdDelete(HSTD h)` | Free the recorded-data handle. |
| `SplStdClose` | `BOOL SplStdClose(HDC hdc)` | End recording on `hdc`. |

Provenance: **[DOC-IBM]** `pmspl.h:790-805`; `HSTD` = `LHANDLE` (`pmspl.h:99`), `SSQL_ERROR`
(`pmspl.h:229`). (These functions are declared in the Toolkit header but not given reference
pages in the PM Programming Reference; the recording purpose is per the header comment,
`pmspl.h:98`.)

---

## 10. Print destinations and drag-and-drop [DOC-IBM]

When a data file is dropped on a printer object (a queue), a running application can be sent a
**`DM_PRINTOBJECT`** message (`0x0320`, `pmstddlg.h:657`). Its parameters carry a `DRAGITEM`
(the dropped object) and a **`PRINTDEST`** structure holding everything needed to call
`DevPostDeviceModes` and `DevOpenDC`:

```c
typedef struct _PRINTDEST {   /* prntdst */
    ULONG        cb;          /* structure size                                  */
    LONG         lType;       /* DevOpenDC lType (OD_QUEUED, ...)                 */
    PSZ          pszToken;    /* DevOpenDC pszToken                               */
    LONG         lCount;      /* DevOpenDC lCount                                 */
    PDEVOPENDATA pdopData;    /* DevOpenDC open data                             */
    ULONG        fl;          /* flags (PD_JOB_PROPERTY)                          */
    PSZ          pszPrinter;  /* target printer/queue name                       */
} PRINTDEST;
```
Provenance: **[DOC-IBM]** `os2def.h:379-389`.

The `fl` flag `PD_JOB_PROPERTY` (`0x0001`, `os2def.h:391`) tells the application the user has
requested a job-properties dialog before printing; if it is **clear**, the application must
*not* show the dialog and must use the properties passed in the `PRINTDEST`. After this, the
application prints with the ordinary queued sequence (Section 7). [DOC-IBM — gpi4.txt
"Drag/Drop Protocol Considerations"]

**Print-to-file** is offered three ways: the user selects "print to file" on the printer
object (preferred — transparent to the application); the application opens an `OD_DIRECT`
context with `pszLogAddress` set to a file/port/pipe name; or the application formats the
printer data itself and writes it with `DosOpen`. [DOC-IBM — gpi4.txt "Print-to-File
Considerations"]

**Network printing** requires a locally installed printer driver (to answer
`DevQueryHardcopyCaps` and show job properties via `DevPostDeviceModes`); the spooler reroutes
jobs from a local *shadow* queue to the remote queue automatically. [DOC-IBM — gpi4.txt
"Network Printing Considerations"]

---

## 11. Handle and status summary [DOC-IBM]

| Type / constant | Value | Definition | Meaning |
|---|---|---|---|
| `HDC` | — | `os2def.h:266` | Device context (`LHANDLE`). |
| `HMF` | — | `os2def.h:275` | Metafile handle (returned by `DevCloseDC` for metafile DCs). |
| `HSPL` | — | `pmspl.h:96` | Spooler (spool-file) handle. |
| `HSTD` | — | `pmspl.h:99` | Recorded `PM_Q_STD` data handle. |
| `DEV_ERROR` / `DEV_OK` | `0` / `1` | `pmdev.h:68-69` | `Dev*` generic error / success. |
| `DEVESC_ERROR` / `DEVESC_NOTIMPLEMENTED` | `-1` / `0` | `pmdev.h:276-277` | `DevEscape` failure / unsupported. |
| `DPDM_ERROR` / `DPDM_NONE` | `-1` / `0` | `pmdev.h:595-596` | `DevPostDeviceModes` error / no settable options. |
| `DQHC_ERROR` | `-1` | `pmdev.h:612` | `DevQueryHardcopyCaps` error. |
| `SPL_ERROR` / `SPL_OK` | `0` / `1` | `pmspl.h:92-93` | Spooler error / success. |
| `PD_JOB_PROPERTY` | `0x0001` | `os2def.h:391` | `PRINTDEST.fl`: show job-properties dialog. |

---

## See also
- `gpi-drawing.md` — the `Gpi*` drawing API and presentation spaces whose output a queued DC
  captures; `GpiAssociate`/`GpiCreatePS` associate a PS with the print DC.
- `pm-window-messaging.md` — `WinInitialize`/`WinCreateMsgQueue` (a message queue must exist
  before `DevOpenDC`), and `WinOpenWindowDC` for screen DCs.
- `session-manager.md` / `config-and-environment.md` — the `OS2SYS.INI`/`OS2.INI` profile the
  spooler stores queue and printer configuration in (`PM_SPOOLER`, `PM_SPOOLER_QP`).
