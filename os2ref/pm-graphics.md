# OS/2 Presentation Manager - the Graphics Path

How the Presentation Manager draws: the DLL federation, the device-context / presentation-space
model, and the path from a `WM_PAINT` to pixels. Brought up at boot-sequence Stage 11.

Provenance: **[DOC-IBM]** IBM DDK DISPLAY / GRADD / PDR reference books; **[OBS-RE]** RE of the
shipped PM binaries (`PMMERGE` with symbols) for the internal object model and dispatch.

## PM is a federation of DLLs [OBS-RE]

The Presentation Manager is not an application - it is a set of DLLs that `PMSHELL.EXE` merely
fronts:

| DLL | Role |
|---|---|
| `PMWIN` | the `Win*` API surface (largely a forwarder into PMMERGE) |
| `PMGPI` | the `Gpi*` API surface |
| `PMMERGE` | the complete window manager + GPI engine + GRE dispatch |
| `DISPLAY` / `GENGRADD` | the base GRADD presentation driver (INIT / QUERY / SETMODE; answers drawing with `RC_SIMULATE`) |
| `VMAN` | the Video Manager - serializes the hardware, owns the pointer, dispatches the VMI command set |
| `SOFTDRAW` | the software rasterizer that executes `RC_SIMULATE` operations into the framebuffer |

The **roles** of the bottom three rows are **[DOC-IBM]** (the PM binary *names* and the
`PMMERGE`-internal split remain [OBS-RE]): DDK *Graphics Adapter Device Driver Reference* - VMAN
"binds the GRADD model components together ... synchronizes the communication between translation
layers and a GRADD and also manages the graphics pointer" (GRADD/00005); the mandatory GHI
functions are init / return-capabilities / return-mode-info / mode-set / palette
(`GHI_CMD_INIT`, `GHI_CMD_QUERYCAPS`, `GHI_CMD_QUERYMODES`, `GHI_CMD_SETMODE`, `GHI_CMD_PALETTE`;
GRADD/00004); SOFTDRAW "is the default for any simulated graphics functions ... exports the base
drawing functions (`SDBitBlt` and `SDLine`) used by VMAN to simulate graphics operations. Given a
pointer to a linear address (a VRAM bit map or system-memory bit map), SOFTDRAW can draw the bits
directly into the bit map" (GRADD/00005); and a GRADD "has the option of performing the requested
operation or returning the request to VMAN with a return code of `RC_SIMULATE`" (GRADD/00005;
`#define RC_SIMULATE 1` - DDK `video/src/video/pmvideo/s3tiger/vramman.h:45`; GENGRADD answers
`GHI_CMD_BITBLT`/`GHI_CMD_LINE`/pointer ops with `RC_SIMULATE` - `video/src/video/gengradd/gendata.c:67-71`).

## Device contexts and presentation spaces [DOC-IBM]

- A **device context (DC)** is **per-process** - a `DevOpenDC` instance seen internally as a dispatch
  table with driver-owned per-DC instance data. A process obtains its own screen DC by running
  per-process display enablement (`FillLogicalDeviceBlock` -> GRADD `GHI_CMD_INITPROC` / VMAN
  `VMI_CMD_INITPROC` -> `VMGlobalToProcess`, which returns that process's own VRAM aperture,
  `INITPROCOUT.ulVRAMVirt`). The DC is *produced* by the process, not handed to it.
  **[DOC-IBM]:** the display driver's `FillLdb()` ("Fill Logical Device Block") "is called by
  every process that attaches to the display driver's .DLL ... to perform any per-process
  initialization"; it calls `GetVRAMPointer()` (via `PMDD.SYS`) for the aperture, and because that
  pointer "is only valid in the context of the process that called it" - a foreign process using it
  "will generate an invalid address exception" - each attaching process makes it valid in its own
  context "via `VMGlobalToProcess`" (DDK *Display Device Driver Reference*, DISPLAY/01211).
  `GHI_CMD_INITPROC` "is mandatory and informs a GRADD that a new process is being initialized ...
  intends to be a client of the GRADD" with `pOut` a `INITPROCOUT` (GRADD/00346); `VMI_CMD_INITPROC`
  is the VMAN equivalent (GRADD/00129); `INITPROCOUT { ULONG ulLength; ULONG ulVRAMVirt; /* 32-bit
  virtual address of VRAM */ }` (GRADD/01220).
- A window's drawing surface is a **presentation space (PS)** bound to a DC via `GpiAssociate` and
  clipped to the window's visible region. `WinBeginPaint` returns a cached micro-PS. One screen DC
  per process serves all that process's windows through their PSs.

## What is shared, what is per-process [OBS-RE]

- **Shared, one physical copy system-wide:** PMMERGE's shared data objects - the desktop window, the
  `HWND -> PWND` handle table, the master message-queue list. These must be one copy so an HWND from
  one process resolves in another and cross-process `WinSendMsg` works.
- **Per-process:** the device context and the VRAM aperture. Each process maps its own aperture onto
  the one physical scanout.

## The draw path [DOC-IBM / OBS-RE]

```
application -> PMWIN / PMGPI -> PMMERGE (DC/PS, GPI, GRE dispatch)
            -> VMAN -> { GENGRADD | SOFTDRAW } -> the video aperture -> the scanout
```

A window paints when a `WM_PAINT` reaches its queue: `WinBeginPaint` (cached micro-PS) -> GPI
primitives -> **GRE** (the graphics engine; dispatched through the DC's table to the driver or to the
GRE simulation routines) -> VMAN -> the base driver, which either draws directly or, for `RC_SIMULATE`
operations, hands off to SOFTDRAW to rasterize into the framebuffer. Nobody blits the framebuffer
directly; the driver executes the primitives. **[DOC-IBM]** for the VMAN -> { GENGRADD | SOFTDRAW }
-> aperture tail: on the first `VMI_CMD_INIT`, "VMAN loads SOFTDRAW and all of the GRADDs specified
by the environment variables" (GRADD/00120); on a VMI command "VMAN either handles the request or
sends it down to the appropriate GRADD" (GRADD/00005). The GPI/GRE-engine -> VMI mapping above the
VMAN boundary is [OBS-RE] of `PMMERGE`.

## The GRE engine entry-point surface [DOC - EDM2]

Below the `Gpi*`/`Win*` API and above VMAN sits the **GRE** (graphics engine) entry-point set - the
`Gre*` handling routines dispatched through the DC's table. `Gpi*`/`Dev*` calls resolve to `Gre*`
handlers (e.g. `GpiBitBlt` -> `GreBitblt`, `GpiCreateLogColorTable` -> `GreCreateLogColorTable`,
`GpiQueryPel` -> `GreGetPel`, `DevEscape` -> `GreEscape`).

**Common calling contract** [DOC - EDM2 "GreBitblt", "GreLockDevice", "GreEscape", et al.]: every
`Gre*` routine takes a trailing `pInstance` (PVOID - pointer to the driver's per-DC instance data)
and `lFunction` (ULONG - high-order WORD = flags, low-order WORD = the `NGre<name>` function number
naming the dispatch slot). A routine reached through the dispatch table "can pass this function to
the graphics engine by using the original pointer copied from the dispatch table" (GreBitblt) - a
driver may handle a call or forward it to the engine's default handler. On any error the handling
routine "must call `WinSetErrorInfo` to post the condition"; return conventions are per-call (BOOL
`fSuccess` for most; `HRGN`/`RGN_ERROR`; bitmap handle/`GPI_ERROR`; color index/`CLR_NOINDEX`;
`DEV_OK`/`DEVESC_NOTIMPLEMENTED`/`DEVESC_ERROR`).

**Three support classes** [DOC - EDM2, per page's "Simulation support"]: (a) *mandatory in the
driver, no engine simulation* - `GreBitblt`, `GreCreateLogColorTable`, `GreDeviceCreateBitmap`,
`GreLockDevice`, `GreGetPel`; (b) *hookable by the driver but simulated by a handling routine in
the engine* - `GreCreateRectRegion`, `GreDeviceSetPaletteEntries`, `GreMultiplyXforms`,
`GreGetClipRects`; (c) *supported by the engine* - `GreInitializeAttributes`, `GreCreateLogicalFont`.

The surface groups into a small number of categories [DOC - EDM2, page named per row]:

| Category | Representative call | What it does / key contract |
|---|---|---|
| Bitblt / raster | `GreBitblt` | Modifies bitmap data in a target rect of the current DC; called by `GpiBitBlt`. `cPoints` 2/3/4 = raster-op / same-size copy / stretch-or-compress; `lRop` low byte = mix (must also support `ROP_GRAY` = `0x000080CA` for greying disabled-menu text); `flOptions` `BBO_OR/AND/IGNORE/TARGWORLD`. |
| Region / clip | `GreCreateRectRegion`, `GreGetClipRects` | Region = OR of an array of RECTLs -> `HRGN` (empty when `cRect`=0). `GreGetClipRects` enumerates the **DC region** = intersection of visible region, clip region, viewing limits, graphics field, and clip path; reports `RRGN_INSIDE/OUTSIDE/PARTIAL` and a per-rect list so a driver can clip line-by-line instead of paying the engine's heavier clipping. |
| Transform | `GreMultiplyXforms` | Multiplies the transform matrix; `lMode` = `SX_UNITY`/`SX_CAT_AFTER`/`SX_CAT_BEFORE`/`SX_OVERWRITE`. |
| Color / palette | `GreCreateLogColorTable`, `GreDeviceSetPaletteEntries` | Logical color table `lFormat` = `LCOLF_INDRGB`/`LCOLF_CONSECRGB`/`LCOLF_RGB`, options `LCOL_RESET`/`LCOL_REALIZABLE`/`LCOL_PURECOLOR`. `GreDeviceSetPaletteEntries` changes the device palette (`LCOLF_CONSECRGB`); changes become visible at `WinRealizePalette`. |
| Font | `GreCreateLogicalFont` | Assigns an `lcid` to a logical font from an 8-char name + `FATTRS` (face name, match number - negative = device font, positive = engine font - code page, selection flags). |
| Device lock | `GreLockDevice` | Locks the DC to one thread: lets current/pending draws finish, then blocks other threads' draws until `GreUnlockDevice` - serializes visible-region use/update across processes. `GreDeath` must not be called while locked (deadlock). |
| Attributes | `GreInitializeAttributes` | Resets attribute bundles, arc parameters, and viewing limits (`INAT_DEFAULTATTRIBUTES` / `INAT_CURRENTATTRIBUTES`). |
| Pel query | `GreGetPel` | Returns the color index of one pel (or `CLR_NOINDEX`); called by `GpiQueryPel`; must raise an error if the point is clipped. |
| Bitmap | `GreDeviceCreateBitmap` | Creates a device bitmap from a `BITMAPINFOHEADER(2)` -> `hbm`/`GPI_ERROR`; `CBM_INIT` initializes it from supplied bits. |
| Escape | `GreEscape` | Backs `DevEscape`; `DEVESC_QUERYESCSUPPORT` mandatory for all drivers, hardcopy adds `STARTDOC`/`ABORTDOC`/`NEXTFRAME`/`ENDDOC`; `lEscape` selects the code. |
| Device state / SG switch | `GreDeath` / `GreResurrection` | Background/foreground screen-group switch - see the Death/Resurrection note below. |

**The GRE<->VMAN bridge** [DOC - EDM2 "GRE2VMAN.DLL"]: the GRE-to-VMAN boundary is a translation
layer, `GRE2VMAN.DLL` - "the first translation layer that will be loaded" in a PM environment -
which "reports the GRADD modes and capabilities to the Graphic Engine." Its entry points include
`OS2_PM_DRV_ENABLE`, `OS2_PM_DRV_QUERYSCREENRESOLUTIONS`, `NotifyModeChange`, and
`SEAMLESSINITIALIZE`/`SEAMLESSTERMINATE`; it loads `VMAN.DLL`, `PMGRE.DLL`, and `PMWIN.DLL`. This
names the translation-layer edge that the `PMMERGE -> VMAN` arrow in the draw path abstracts over.

## One adapter, multi-writer, no compositor [DOC-IBM / OBS-RE]

There is **one adapter, one CRTC, one scanout** - no compositor. **Multiple PM processes write that
one shared VRAM:** each runs per-process display enablement and receives its own writable
`VMGlobalToProcess` aperture onto the same physical scanout (`DISPLAY/01211`, `GRADD/01220`
`INITPROCOUT.ulVRAMVirt`), writes only its window's clipped region, and **VMAN serializes** the
hardware so writes never collide. Multiple processes *mapping* the aperture is documented; the "one
writer at any instant" is VMAN serialization, not a single-writer restriction. Background full-screen
sessions are saved/restored across managed screen-group switches (Death/Resurrection through the same
driver stack).

**[DOC-IBM]** confirms the per-process writable aperture (`VMGlobalToProcess` / `INITPROCOUT.ulVRAMVirt`,
DISPLAY/01211 + GRADD/01220), VMAN serialization ("VMAN synchronizes the communication between
translation layers and a GRADD", GRADD/00005), and Death/Resurrection: the *Death and Resurrection*
mechanism (`eddm_Death` / `eddm_Resurrection`, `EDDMDEAD.C`) is "used when switching to and from
full-screen Windows, DOS, or OS/2 sessions ... `eddm_Death` handles the switch of the presentation
display driver into the background ... switches the display to text mode, sets the drawing mode to
software-drawing mode, and disables the bit-map cache; `eddm_Resurrection` performs the inverse task"
(DISPLAY/01236; GRE entry points `GreDeath`/`GreResurrection` in `GREMDEV.DLL`, DISPLAY/01185).
[DOC - EDM2 "GreDeath"] adds the driver-side contract: `GreDeath` informs the driver "the entire
screen is required by another screen group"; while dead the driver "must continue to accumulate
bounds and respond to queries but it might not actually draw to the display," and on
`GreResurrection` "the missing output will be re-created by the system sending a `WM_PAINT` message
to the application."
**[OBS-RE]** (not sourced to an IBM statement - the token "compositor" is absent from all of the DDK
reference): "one adapter, one CRTC, one scanout, no compositor" is an architectural characterization
of the single shared scanout, left [OBS-RE].

The message queue that drives `WM_PAINT`, and its kernel wake, are in `message-queue.md`.

## Below `VMGlobalToProcess`: the `SCREEN$`/`SCREENDD$` driver [OBS-RE]

`VMGlobalToProcess` (above) is a DevHlp-level primitive; the real device driver underneath it -
`SCREEN$`/`SCREENDD$`, IBM's Base Video Subsystem driver - is a single `Screen_Strategy` entry
point dispatching on two IOCtl categories, found by reading the real shipped driver source
directly (not a reconstruction):

- **Category `0x03` (`SCREEN$` proper)** - DOS-legacy-shaped: selector allocation onto *physical*
  video memory via `DevHlp_PhysToUVirt`, plus (function `0x74`) a direct **passthrough to ABIOS**
  (`DevHlp_ABIOSCall`, real entry contract `AX`=LID/`SI`=request-block offset/`DH`=entry point,
  independently documented in `kernel-services.md`) - the real mechanism behind video **mode**
  changes: the driver does not implement mode-switching logic itself, it hands the request to
  ABIOS, which reprograms the hardware (CRTC/sequencer registers) on the other side of the call.
- **Category `0x80` (`SCREENDD_CATEGORY`, the SVGA extension)** - bank get/set (dispatched through
  a real per-vendor-chipset table: ATI/Cirrus/IBM/S3/Trident/Tseng/Video7/WD/Weitek and others),
  chipset/VRAM info, and - the real primitive behind the multi-writer model above - **`GetGlobalAccess`**
  (function `0x0C`): validates a page-aligned per-process address + length, then calls
  **`DevHlp_VMProcessToGlobal`** ("create writable mapping") to produce the cross-process-visible
  address handed back to the caller. A **`GetLinearAccess`** function (`0x0B`) also exists
  specifically for configurations where a real linear mapping is available instead of bank
  switching - i.e. even the real driver prefers the linear path when it can get it, the same
  shortcut a modern reimplementation would take.

**`SCREEN$`/`SCREENDD$` has no session-switch notification of its own** - unlike the keyboard and
mouse drivers (`session-manager.md`, `vio-kbd-mou.md` section 3.6/section 4.5), which each independently
implement a Cat-B `SGControl`-style switch-aware IOCtl, `Screen_Strategy`'s own dispatch recognizes
only the two categories above, nothing else, checked directly in the driver's real code. This
makes architectural sense: keyboard and mouse are *leaf* input devices that must decide, per event,
whether to deliver to the now-current session, so each needs its own switch notification to know
when that changes. `SCREEN$`/`SCREENDD$` is a *passive* memory-mapping resource that never decides
anything on its own initiative - it is driven top-down by whatever orchestrates a session switch,
never a participant in the decision.

---

*Ratified (2026-07-26): checked against the IBM DDK - Graphics Adapter Device Driver Reference
(GRADD ref: 00004 GRADD model / mandatory GHI functions, 00005 model components / VMAN / SOFTDRAW /
`RC_SIMULATE`, 00120 VMAN loads SOFTDRAW+GRADDs, 00129 `VMI_CMD_INITPROC`, 00346 `GHI_CMD_INITPROC`,
01220 `INITPROCOUT`) and Display Device Driver Reference (DISPLAY ref: 01185 GRE entry table,
01211 `FillLdb`/`GetVRAMPointer`/`VMGlobalToProcess`, 01236 Death and Resurrection), plus DDK video
source (`video/src/video/gengradd/gendata.c`, `.../pmvideo/s3tiger/vramman.h`). Upgraded to
[DOC-IBM]: the VMAN/SOFTDRAW/GENGRADD roles + `RC_SIMULATE` handoff, the per-process display-enablement
chain (`FillLdb` -> `GHI_CMD_INITPROC`/`VMI_CMD_INITPROC` -> `VMGlobalToProcess` -> `INITPROCOUT.ulVRAMVirt`),
the VMAN->driver draw tail, VMAN serialization, and Death/Resurrection screen-group save/restore. No
factual discrepancies found. Left [OBS-RE] (no IBM source located): the PM binary names and the
`PMMERGE`-internal window-manager/GPI/GRE-dispatch split, and the "one CRTC / one scanout / no
compositor" characterization ("compositor" appears nowhere in the DDK reference).*

*Enriched (2026-07-27) from EDM2 (secondary/community source, tagged [DOC - EDM2 "<page>"], never
[DOC-IBM]): the GRE engine entry-point surface - the common `pInstance`/`lFunction` dispatch-slot
calling contract, the mandatory/hookable-but-simulated/engine-supported support classes, and the
category map (bitblt, region/clip, transform, color/palette, font, device-lock, attributes, pel
query, bitmap, escape, Death/Resurrection) - from the EDM2 `Gre*` pages (`GreBitblt`, `GreEscape`,
`GreInitializeAttributes`, `GreCreateLogColorTable`, `GreDeviceSetPaletteEntries`,
`GreCreateLogicalFont`, `GreCreateRectRegion`, `GreDeviceCreateBitmap`, `GreGetClipRects`,
`GreLockDevice`, `GreMultiplyXforms`, `GreGetPel`, `GreDeath`); plus the `GRE2VMAN.DLL`
translation-layer edge and entry points from the EDM2 `GRE2VMAN.DLL` page. No EDM2 page contradicted
an existing [DOC-IBM]/[OBS-RE] fact - the GreDeath addition complements DISPLAY/01236 (driver-side:
accumulate bounds / may not draw / WM_PAINT re-create on resurrection).*

*Enriched (2026-07-30) [OBS-RE]: the "Below `VMGlobalToProcess`" section, from reading the real
shipped `SCREEN$`/`SCREENDD$` driver source directly (`screen01.asm`/`screen02.asm` and the
category-`0x80` SVGA extension) - the single `Screen_Strategy` dispatch, the category `0x03`
(legacy `SCREEN$`, `DevHlp_PhysToUVirt`, ABIOS passthrough at function `0x74`) vs. category `0x80`
(`SCREENDD$` SVGA extension, per-chipset bank table, `GetLinearAccess`/`GetGlobalAccess`) split,
`GetGlobalAccess`'s use of `DevHlp_VMProcessToGlobal` as the real primitive under the multi-writer
model above, and the confirmed absence of any session-switch notification in this driver (contrast
keyboard/mouse in `vio-kbd-mou.md` section 3.6/section 4.5). One correction recorded in the process: `screen01.asm`'s
own header comment mislabels function `0x74` as "Allocate a Selector:Offset" with no backing code;
`screen02.asm`'s header and real code correctly identify it as the ABIOS passthrough - cross-checked
against this repo's own `kernel-services.md` `DevHlp_ABIOSCall` entry (independently EDM2-sourced),
which agrees.*
