# OS/2 Presentation Manager - GPI Drawing API

The Graphics Programming Interface (`Gpi*`) an application calls to draw: the device
context and presentation space it draws *through*, the coordinate/transform pipeline it draws
*in*, and the primitives - lines, boxes, areas, paths, text, bitmaps - it draws *with*. Every
drawing call takes a presentation-space handle (`HPS`) as its first argument; the presentation
space carries the current position, the current attributes (color, mix, line type, font), and
the transform chain, and is bound to a device context (`HDC`) that names the physical or logical
target (a window's screen, a memory bitmap, a print queue, a metafile). This reference documents
the developer-facing API surface; the internal engine that executes the primitives (GRE / VMAN /
the presentation driver) is described in `pm-graphics.md`.

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 headers - `pmgpi.h` (all `Gpi*` prototypes, `PU_*` /
`GPIF_*` / `GPIT_*` / `GPIA_*` / `DRO_*` / `BA_*` / `FPATH_*` / `LCOL*` / `CLR_*` / `ROP_*` /
`BBO_*` / `CVTC_*` / `TRANSFORM_*` constants, `SIZEL` / `SIZEF` / `KERNINGPAIRS`), `pmdev.h`
(`DevOpenDC` / `DevCloseDC` / `DevQueryCaps`, `OD_*` device types), `pmbitmap.h`
(`BITMAPINFOHEADER` / `BITMAPINFOHEADER2` and the compression/recording constants), `os2def.h`
(`POINTL`, `RECTL`, `FIXED`, `MATRIXLF`, `FATTRS`, `FONTMETRICS`, `DEVOPENSTRUC`, `DEVOPENDATA`),
`pmwin.h` (`WinGetPS` / `WinBeginPaint` / `WinOpenWindowDC`). **[DOC]** IBM *GPI Programming
Guide and Reference* for behavioural detail (drawing-mode semantics, the transform chain) the
headers state only as constants.

---

## 1. The model - presentation space <-> device context [DOC-IBM / DOC]

Drawing happens in two nested objects:

- A **device context (`HDC`)** is the connection to an output target. It is created by
  `DevOpenDC` (or implicitly, via `WinOpenWindowDC` / `WinGetPS` / `WinBeginPaint` for a window)
  and names *where* pixels go - a window's screen, an in-memory bitmap, a printer queue, or a
  metafile. The DC also answers device-capability queries (`DevQueryCaps`).
- A **presentation space (`HPS`)** is the drawing context. It holds the current position, the
  current graphics attributes, the loaded fonts/bitmaps set-IDs, and the coordinate transforms.
  All `Gpi*` primitives operate on an `HPS`.

A PS produces output only while it is **associated** with a DC. The binding is many-to-one over
time but one-at-a-time: a normal PS may be associated with at most one DC at once, and a DC with
at most one PS. `GpiCreatePS` can associate at creation (`GPIA_ASSOC`) or defer it
(`GPIA_NOASSOC`); `GpiAssociate` binds or unbinds later (passing `hdc = NULLHANDLE` dissociates).
A **micro-PS** (`GPIT_MICRO`) is permanently associated with the DC it is created against and
cannot be re-associated - it is the lightweight form used for windows.

```
application -- Gpi* -->  HPS  --(GpiAssociate)-->  HDC  -->  output target
                        (attrs,               (screen / memory
                         transforms,           bitmap / queue /
                         current pos)          metafile)
```

For windows, the PS is normally obtained from the window manager rather than built by hand
[DOC-IBM - `pmwin.h`]:

| Call | Purpose |
|---|---|
| `WinGetPS(HWND hwnd)` | Get a cached micro-PS for a window's whole client/frame area (returns `HPS`) |
| `WinReleasePS(HPS hps)` | Release a PS obtained from `WinGetPS` |
| `WinBeginPaint(HWND hwnd, HPS hps, PRECTL prclPaint)` | Begin `WM_PAINT` drawing; returns a PS clipped to the update region, reports the bounding rectangle in `*prclPaint` |
| `WinEndPaint(HPS hps)` | End the paint bracket, validate the update region |
| `WinOpenWindowDC(HWND hwnd)` | Open the (screen) DC for a window, for use with a `GpiCreatePS` micro-PS |

---

## 2. Device contexts - `DevOpenDC` [DOC-IBM - `pmdev.h`, `os2def.h`]

```c
HDC  APIENTRY DevOpenDC(HAB hab, LONG lType, PSZ pszToken, LONG lCount,
                        PDEVOPENDATA pdopData, HDC hdcComp);
HMF  APIENTRY DevCloseDC(HDC hdc);
BOOL APIENTRY DevQueryCaps(HDC hdc, LONG lStart, LONG lCount, PLONG alArray);
```

`lType` selects the class of target [DOC-IBM - `pmdev.h`]:

| `OD_*` | Value | Device-context type |
|---|---|---|
| `OD_SCREEN` | `0` | The display (a window's screen DC) |
| `OD_QUEUED` | `2` | A spooler print queue (output is queued) |
| `OD_DIRECT` | `5` | A printer/plotter addressed directly (unqueued) |
| `OD_INFO` | `6` | Information-only: query capabilities/metrics, no drawing |
| `OD_METAFILE` | `7` | A metafile being recorded |
| `OD_MEMORY` | `8` | An in-memory bitmap DC (off-screen drawing surface) |
| `OD_METAFILE_NOQUERY` | `9` | Metafile recording without query support |

`pdopData` is `PDEVOPENDATA`, i.e. `PSZ *` - an array of string pointers, or equivalently a
`DEVOPENSTRUC` (`os2def.h`) [DOC-IBM]:

```c
typedef PSZ *PDEVOPENDATA;              /* os2def.h */

typedef struct _DEVOPENSTRUC {          /* dop; os2def.h */
   PSZ        pszLogAddress;            /* array index ADDRESS         (0) */
   PSZ        pszDriverName;            /*             DRIVER_NAME     (1) */
   PDRIVDATA  pdriv;                    /*             DRIVER_DATA     (2) */
   PSZ        pszDataType;              /*             DATA_TYPE       (3) */
   PSZ        pszComment;               /*             COMMENT         (4) */
   PSZ        pszQueueProcName;         /*             PROC_NAME       (5) */
   PSZ        pszQueueProcParams;       /*             PROC_PARAMS     (6) */
   PSZ        pszSpoolerParams;         /*             SPL_PARAMS      (7) */
   PSZ        pszNetworkParams;         /*             NETWORK_PARAMS  (8) */
} DEVOPENSTRUC;
```

`lCount` is the number of leading array elements supplied; unsupplied trailing fields are
omitted. `hdcComp` is a compatible DC (used for `OD_MEMORY` to describe the format the bitmap
must match). `DevCloseDC` returns the metafile handle (`HMF`) for a metafile DC, `DEV_OK`
otherwise. `DevQueryCaps` returns adapter properties into `alArray` for `lCount` capability
indices starting at `lStart` (the `CAPS_*` indices are defined in `pmdev.h`, e.g.
`CAPS_RASTER_FLOOD_FILL`). [DOC-IBM]

---

## 3. Presentation spaces - `GpiCreatePS` / `GpiDestroyPS` / `GpiAssociate` [DOC-IBM - `pmgpi.h`]

```c
HPS  APIENTRY GpiCreatePS(HAB hab, HDC hdc, PSIZEL psizlSize, ULONG flOptions);
BOOL APIENTRY GpiDestroyPS(HPS hps);
BOOL APIENTRY GpiAssociate(HPS hps, HDC hdc);
BOOL APIENTRY GpiResetPS(HPS hps, ULONG flOptions);   /* GRES_ATTRS/SEGMENTS/ALL */
LONG APIENTRY GpiSavePS(HPS hps);                     /* push attribute state    */
BOOL APIENTRY GpiRestorePS(HPS hps, LONG lPSid);      /* pop attribute state      */
BOOL APIENTRY GpiErase(HPS hps);                      /* clear to background      */
```

`psizlSize` is a `SIZEL { LONG cx; LONG cy; }` [DOC-IBM - `pmgpi.h`] giving the page dimensions
(both zero = maximum device size). `flOptions` is an OR of one value from each of the following
groups [DOC-IBM - `pmgpi.h`]:

### Coordinate origin - y increases *upward* [DOC-IBM]

**PM and GPI place the origin at the BOTTOM-LEFT, with y increasing upward.** This is the single
most consequential difference from Win32/X11/GDI (top-left origin, y increasing *downward*), and it
is a *silent* difference: nothing returns an error, the drawing simply lands mirrored vertically.
Any code ported from a top-left system must flip y at the boundary.

The rule holds uniformly across window, presentation-space, and screen coordinates:

| Context | Statement | Source |
|---|---|---|
| Window coordinates | "The rectangle is in window coordinates relative to itself, so that the **bottom left corner is at the position (0,0)**" | `pm2.txt` - *WinQueryWindowRect*, Remarks |
| Presentation space | "The presentation space origin is established normally, that is, relative to the **lower left of the window itself**, not its parent" | `pm2.txt` - `CS_PARENTCLIP`, Remarks |
| Child position | *WinSetWindowPos* x/y are "in window coordinates relative to the **bottom left corner of its parent**" | `pm2.txt` - *WinSetWindowPos* |
| Screen coordinates | "`pptlPoint` must be relative to the **bottom left corner of the screen**" | `pm2.txt` - *WinWindowFromPoint* |

Consequences for a `RECTL`: `yBottom` is the edge *nearer the origin* and `yTop` the edge further
from it, so **`yBottom < yTop`** in a normalized rectangle - the opposite of the Win32 `RECT` sense
where `top < bottom`. A mechanical `RECT`->`RECTL` field rename is therefore wrong; the y pair must be
swapped *and* rebased against the parent height.

**`RECTL` field range** [DOC-IBM - `pm2.txt`, `RECTL` structure Note]: "The value of each field in
this structure must be in the range **-32 768 through 32 767**." Note this is narrower than the
`LONG` field type implies, and narrower than Win32's `RECT`; a port passing large coordinates through
unchanged is out of contract even though the struct would hold them.

### Rectangle boundary rule - left/bottom inclusive, right/top exclusive [DOC-IBM]

A `RECTL` **includes** its left and bottom edges and **excludes** its right and top edges - that is,
it is inclusive on the two *origin-side* edges. [DOC-IBM - `pm2.txt`, *WinFillRect*, Remarks]:

> "Points on the left and bottom boundaries of the rectangle are included in the fill, but points on
> the right and top boundaries are not, except where they are also on the left and bottom
> boundaries; that is, the top-left and bottom-right corners."

Note the corner exception: the top-left and bottom-right corner points *are* filled, because each
lies on one included edge. `WinDrawBorder` follows the same asymmetry from the other side [DOC-IBM -
`pm2.txt`, *WinDrawBorder*]: "Along the bottom and left edges of the rectangle, the edges of the
border coincide with the rectangle edges. Along the top and right edges, the border is drawn one
device unit inside the rectangle edges."

This is the *same shape of rule* as Win32 (`RECT` includes left/top, excludes right/bottom) reflected
through the flipped y axis - so a rectangle's width is `xRight - xLeft` and its height
`yTop - yBottom`, with no +/-1 correction. The trap is not the arithmetic but the pairing: porting
code that reasons about which edge is "the included one" must follow the origin, not the field name.

**Presentation-space unit** (`PU_*`, masked by `PS_UNITS = 0x00FC`) - the world/page coordinate unit:

| `PU_*` | Value | Unit |
|---|---|---|
| `PU_ARBITRARY` | `0x0004` | Application-defined (page units set via the viewport) |
| `PU_PELS` | `0x0008` | Device pels (pixels) |
| `PU_LOMETRIC` | `0x000C` | 0.1 mm |
| `PU_HIMETRIC` | `0x0010` | 0.01 mm |
| `PU_LOENGLISH` | `0x0014` | 0.01 inch |
| `PU_HIENGLISH` | `0x0018` | 0.001 inch |
| `PU_TWIPS` | `0x001C` | 1/1440 inch (twentieth of a point) |

**Coordinate format** (`GPIF_*`, masked by `PS_FORMAT = 0x0F00`):

| `GPIF_*` | Value | Meaning |
|---|---|---|
| `GPIF_DEFAULT` | `0` | Default format |
| `GPIF_SHORT` | `0x0100` | 16-bit coordinates in retained-segment data |
| `GPIF_LONG` | `0x0200` | 32-bit coordinates |

**PS type** (`GPIT_*`, masked by `PS_TYPE = 0x1000`):

| `GPIT_*` | Value | Meaning |
|---|---|---|
| `GPIT_NORMAL` | `0` | Full-function PS (re-associable, supports segments) |
| `GPIT_MICRO` | `0x1000` | Micro-PS: bound to one DC for life, no retained segments |
| `GPIT_INK` | `0x2000` | Ink PS |

**Implicit association** (`GPIA_*`, masked by `PS_ASSOCIATE = 0x4000`): `GPIA_NOASSOC` (`0`) or
`GPIA_ASSOC` (`0x4000`). `GPIM_AREAEXCL` (`0x8000`) selects the area-exclusive fill default.

`GpiResetPS` returns the PS to its initial state - `GRES_ATTRS` (attributes only),
`GRES_SEGMENTS`, or `GRES_ALL`. `GpiSavePS`/`GpiRestorePS` form a LIFO stack of attribute state.
The **drawing mode** (`GpiSetDrawingMode`, values `DM_DRAW = 1`, `DM_RETAIN = 2`,
`DM_DRAWANDRETAIN = 3`) selects whether primitives are drawn immediately, retained in segments, or
both. [DOC-IBM - `pmgpi.h`]

---

## 4. Coordinate spaces and the transform pipeline [DOC-IBM - `pmgpi.h`, `os2def.h` / DOC]

A primitive's coordinates pass through a chain of coordinate spaces before reaching device pels.
The `CVTC_*` constants (the source/target spaces of `GpiConvert`) name the chain in order
[DOC-IBM - `pmgpi.h`]:

| `CVTC_*` | Value | Coordinate space |
|---|---|---|
| `CVTC_WORLD` | `1` | World space - where primitives are specified |
| `CVTC_MODEL` | `2` | Model space - after the model (segment) transform |
| `CVTC_DEFAULTPAGE` | `3` | Default page space |
| `CVTC_PAGE` | `4` | Page space - after the default-view transform |
| `CVTC_DEVICE` | `5` | Device space - pels on the target |

The transforms between the spaces are all `MATRIXLF` matrices, applied in order:

```
WORLD --(model transform)--> MODEL --(default view)--> PAGE --(page viewport)--> DEVICE
```

| Transform | Set / query | Space edge |
|---|---|---|
| Model (segment) transform | `GpiSetModelTransformMatrix` / `GpiQueryModelTransformMatrix` | world -> model |
| Segment transform (retained) | `GpiSetSegmentTransformMatrix` / `GpiQuerySegmentTransformMatrix` | per-segment |
| Default view transform | `GpiSetDefaultViewMatrix` / `GpiQueryDefaultViewMatrix` | model -> page |
| Viewing transform | `GpiSetViewingTransformMatrix` / `GpiQueryViewingTransformMatrix` | page (dynamic) |
| Page viewport | `GpiSetPageViewport` / `GpiQueryPageViewport` (a `RECTL`) | page -> device |
| Point conversion | `GpiConvert` / `GpiConvertWithMatrix` | any -> any |

```c
BOOL APIENTRY GpiSetModelTransformMatrix(HPS hps, LONG lCount, PMATRIXLF pmatlfArray, LONG lOptions);
BOOL APIENTRY GpiSetDefaultViewMatrix   (HPS hps, LONG lCount, PMATRIXLF pmatlfarray, LONG lOptions);
BOOL APIENTRY GpiSetSegmentTransformMatrix(HPS hps, LONG lSegid, LONG lCount, PMATRIXLF pmatlfarray, LONG lOptions);
BOOL APIENTRY GpiSetPageViewport(HPS hps, PRECTL prclViewport);
BOOL APIENTRY GpiConvert(HPS hps, LONG lSrc, LONG lTarg, LONG lCount, PPOINTL aptlPoints);
BOOL APIENTRY GpiConvertWithMatrix(HPS hps, LONG lCountp, PPOINTL aptlPoints, LONG lCount, PMATRIXLF pmatlfArray);
```

`lOptions` on the `Set*Matrix` calls is a `TRANSFORM_*` combining rule [DOC-IBM - `pmgpi.h`]:
`TRANSFORM_REPLACE` (`0`), `TRANSFORM_ADD` (`1`, concatenate onto the existing transform),
`TRANSFORM_PREEMPT` (`2`).

### `MATRIXLF` - a 3x3 transform [DOC-IBM - `os2def.h`]

```c
typedef LONG FIXED;   /* fx - fixed point, implicit binary point between the 2nd and 3rd hex digit
                             from the low end: the low 16 bits are the fraction, high 16 the integer */

typedef struct _MATRIXLF {   /* matlf */
   FIXED fxM11;   /* [0]  scale/rotate x */
   FIXED fxM12;   /* [4]  shear         */
   LONG  lM13;    /* [8]  0 (projective row, integer) */
   FIXED fxM21;   /* [12] shear         */
   FIXED fxM22;   /* [16] scale/rotate y */
   LONG  lM23;    /* [20] 0             */
   LONG  lM31;    /* [24] x translation (integer) */
   LONG  lM32;    /* [28] y translation (integer) */
   LONG  lM33;    /* [32] 1             */
} MATRIXLF;                  /* 36 bytes */
```

The four scale/shear elements (`fxM11`, `fxM12`, `fxM21`, `fxM22`) are `FIXED` (fractional); the
translation and the bottom row (`lM13`, `lM23`, `lM31`, `lM32`, `lM33`) are plain `LONG`
integers. A point `(x, y)` transforms as `x' = x,M11 + y,M21 + M31`, `y' = x,M12 + y,M22 + M32`.
[DOC-IBM struct; DOC for the multiply convention]

---

## 5. Current position and line primitives [DOC-IBM - `pmgpi.h`, `os2def.h`]

The PS maintains a **current position**. Line primitives draw from it and (except `GpiMove`)
advance it to their end point.

```c
typedef struct _POINTL { LONG x; LONG y; } POINTL;   /* ptl; os2def.h */

BOOL APIENTRY GpiMove(HPS hps, PPOINTL pptlPoint);                    /* set current position, no draw */
LONG APIENTRY GpiLine(HPS hps, PPOINTL pptlEndPoint);                /* line from current pos to point */
LONG APIENTRY GpiPolyLine(HPS hps, LONG lCount, PPOINTL aptlPoints); /* connected lines through points */
LONG APIENTRY GpiPolyLineDisjoint(HPS hps, LONG lCount, PPOINTL aptlPoints); /* pairs = separate segments */
BOOL APIENTRY GpiSetCurrentPosition(HPS hps, PPOINTL pptlPoint);
BOOL APIENTRY GpiQueryCurrentPosition(HPS hps, PPOINTL pptlPoint);
```

The `LONG`-returning primitives return a **correlation/error code** [DOC-IBM - `pmgpi.h`]:
`GPI_OK` (`1`), `GPI_ERROR` (`0`), or `GPI_HITS` (`2`, a correlation hit was detected). `GpiMove`
and the `Set*` calls return `BOOL`. Related draw calls in the same family: `GpiPointArc`,
`GpiPolySpline`, `GpiFullArc`, `GpiPartialArc` (arc primitives, parameterized by
`GpiSetArcParams`). [DOC-IBM - `pmgpi.h`]

---

## 6. `GpiBox` [DOC-IBM - `pmgpi.h`]

```c
LONG APIENTRY GpiBox(HPS hps, LONG lControl, PPOINTL pptlPoint, LONG lHRound, LONG lVRound);
```

Draws a rectangle from the current position to `*pptlPoint`; `lHRound`/`lVRound` give the
horizontal/vertical diameters of rounded corners (0 = square). `lControl` selects outline/fill
[DOC-IBM - `pmgpi.h`, shared with `GpiFullArc`/`GpiOval`]:

| `DRO_*` | Value | Meaning |
|---|---|---|
| `DRO_FILL` | `1` | Interior only |
| `DRO_OUTLINE` | `2` | Boundary only |
| `DRO_OUTLINEFILL` | `3` | Both |
| `DRO_EXCLUSIVE` | `0x10000000` | Exclusive right/bottom edge in device space |

---

## 7. Area and path brackets [DOC-IBM - `pmgpi.h`]

An **area** is a filled region bracketed by `GpiBeginArea` ... `GpiEndArea`, with the enclosing
line primitives forming its boundary. A **path** is a stored geometry (built between
`GpiBeginPath` ... `GpiEndPath`) that can then be filled, stroked, converted to a clip path, or
turned into a region.

```c
BOOL APIENTRY GpiBeginArea(HPS hps, ULONG flOptions);
LONG APIENTRY GpiEndArea(HPS hps);

BOOL APIENTRY GpiBeginPath(HPS hps, LONG lPath);   /* lPath = path identifier, normally 1 */
BOOL APIENTRY GpiEndPath(HPS hps);
BOOL APIENTRY GpiCloseFigure(HPS hps);
LONG APIENTRY GpiFillPath(HPS hps, LONG lPath, LONG lOptions);
BOOL APIENTRY GpiModifyPath(HPS hps, LONG lPath, LONG lMode);       /* MPATH_STROKE = 6 (fat line) */
LONG APIENTRY GpiStrokePath(HPS hps, LONG lPath, ULONG flOptions);
LONG APIENTRY GpiOutlinePath(HPS hps, LONG lPath, LONG lOptions);
BOOL APIENTRY GpiSetClipPath(HPS hps, LONG lPath, LONG lOptions);   /* SCP_* */
HRGN APIENTRY GpiPathToRegion(HPS hps, LONG lPath, LONG lOptions);
```

`GpiBeginArea` options (`BA_*`, OR-combined) [DOC-IBM - `pmgpi.h`]:

| `BA_*` | Value | Meaning |
|---|---|---|
| `BA_NOBOUNDARY` | `0` | Do not draw the boundary line |
| `BA_BOUNDARY` | `0x0001` | Draw the boundary as well as filling |
| `BA_ALTERNATE` | `0` | Alternate (even-odd) fill rule |
| `BA_WINDING` | `0x0002` | Winding fill rule |
| `BA_INCL` / `BA_EXCL` | `0` / `8` | Include / exclude the boundary in device space |

`GpiFillPath` options (`FPATH_*`) [DOC-IBM - `pmgpi.h`]: `FPATH_ALTERNATE` (`0`) /
`FPATH_WINDING` (`2`) select the fill rule; `FPATH_INCL` (`0`) / `FPATH_EXCL` (`8`) the boundary
inclusion. `GpiSetClipPath` takes the parallel `SCP_*` set (`SCP_ALTERNATE`/`SCP_WINDING`,
`SCP_AND` to intersect with the current clip, `SCP_RESET`). [DOC-IBM - `pmgpi.h`]

A path or area converted to a region (`GpiPathToRegion`, `HRGN`) can be hit-tested point-by-point.
The region point-in test evaluates a point given **in device coordinates** and returns
`PRGN_INSIDE` (point is in the region), `PRGN_OUTSIDE` (not in the region), or `RGN_ERROR`; testing
the region that is *currently selected as the clip region* is an error
(`PMERR_REGION_IS_CLIP_REGION`), as are `PMERR_INV_HRGN` / `PMERR_HRGN_BUSY` /
`PMERR_INV_COORDINATE`. [DOC - EDM2 "GrePtInRegion"]

---

## 8. Color, mix, and color tables [DOC-IBM - `pmgpi.h`]

```c
BOOL APIENTRY GpiSetColor(HPS hps, LONG lColor);
LONG APIENTRY GpiQueryColor(HPS hps);
BOOL APIENTRY GpiSetBackColor(HPS hps, LONG lColor);
LONG APIENTRY GpiQueryBackColor(HPS hps);
BOOL APIENTRY GpiSetMix(HPS hps, LONG lMixMode);        /* foreground raster-op mix (FM_*) */
BOOL APIENTRY GpiSetBackMix(HPS hps, LONG lMixMode);    /* background mix                  */
BOOL APIENTRY GpiCreateLogColorTable(HPS hps, ULONG flOptions, LONG lFormat,
                                     LONG lStart, LONG lCount, PLONG alTable);
LONG APIENTRY GpiQueryColorIndex(HPS hps, ULONG flOptions, LONG lRgbColor);
LONG APIENTRY GpiQueryRGBColor  (HPS hps, ULONG flOptions, LONG lColorIndex);
LONG APIENTRY GpiQueryNearestColor(HPS hps, ULONG flOptions, LONG lRgbIn);
```

`lColor` is either an index into the logical color table or a `CLR_*` special value. The standard
indices [DOC-IBM - `pmgpi.h`]:

| `CLR_*` | Value | | `CLR_*` | Value |
|---|---|---|---|---|
| `CLR_ERROR` | `-255` | | `CLR_BACKGROUND` | `0` |
| `CLR_NOINDEX`| `-254` | | `CLR_BLUE` | `1` |
| `CLR_FALSE` | `-5` | | `CLR_RED` | `2` |
| `CLR_TRUE` | `-4` | | `CLR_PINK` | `3` |
| `CLR_DEFAULT`| `-3` | | `CLR_GREEN` | `4` |
| `CLR_WHITE` | `-2` | | `CLR_CYAN` | `5` |
| `CLR_BLACK` | `-1` | | `CLR_YELLOW` | `6` |
| | | | `CLR_NEUTRAL` | `7` |

> **`CLR_*` are reserved names, and they are INDICES.** `os2emx.h` already defines `CLR_BLACK`,
> `CLR_WHITE`, `CLR_RED`, `CLR_BLUE`, `CLR_GREEN` and the rest as the small signed values above.
> Code that ports an RGB palette in - a Scintilla or Win32 colour set, say - must not name its own
> constants `CLR_BLACK`/`CLR_BLUE`/...: it collides with the header, and where it does not collide it
> silently means something else, because `CLR_BLACK` is `-1` and not `0x000000`. Prefix your palette
> (`MYAPP_BLACK`) and keep the `CLR_*` spelling for the places that genuinely want an index - a
> `FONTDLG`'s `clrFore`/`clrBack`, for instance, takes an index, not an RGB. [OBS-RE - hit while
> porting Notepad2's syntax colours, where the two live a few lines apart in one file.]

### 8.1 Index mode is the DEFAULT - pass an RGB value and drawing silently vanishes [DOC-IBM]

A presentation space has two colour-table modes, and **a freshly obtained PS is in colour *index*
mode, not RGB** [DOC-IBM - `pm2.txt`, *WinGetPS* Remarks: "The initial state of the presentation
space is the same as that of a presentation space created using `GpiCreatePS`. **The color table is
in default color index mode**"]. The same applies to the cache PS returned by `WinBeginPaint`.

In index mode `lColor` is an *index*, so an RGB value like `0xFF0000` is read as index 16711680 -
out of range, and the primitive **draws nothing at all**. No error, no return code to check: the
call succeeds and the pixels never appear.

To use RGB values, put the PS into RGB mode first [DOC-IBM - `gpi2.txt`,
*GpiCreateLogColorTable*]:

```c
#define INCL_GPILOGCOLORTABLE
/* LCOL_RESET discards the current table; LCOLF_RGB selects RGB mode.       */
/* lStart/lCount/alTable are unused in RGB mode.                            */
GpiCreateLogColorTable(hps, LCOL_RESET, LCOLF_RGB, 0, 0, NULL);
```

Do this immediately after obtaining **every** PS - `WinGetPS`, `WinBeginPaint`, and each memory PS
from `GpiCreatePS` - or use the `CLR_*` indices instead and stay in index mode. Mixing the two is
what produces the bug.

**Recognising it:** everything that routes through `GpiSetColor` / `GpiSetBackColor` / `WinFillRect`
disappears, while anything that writes pels directly - `GpiDrawBits`, `GpiBitBlt` from a bitmap you
filled yourself - still appears. That asymmetry is diagnostic: if raw-pel drawing works and coloured
primitives don't, the PS is in index mode. [OBS-RE - observed porting Scintilla's `Surface` to PM;
the only primitive that rendered was the one bypassing the colour table.]

Indices `8`-`15` are the dark/pale variants (`CLR_DARKGRAY`=`8`, `CLR_DARKBLUE`=`9`,
`CLR_DARKRED`=`10`, `CLR_DARKPINK`=`11`, `CLR_DARKGREEN`=`12`, `CLR_DARKCYAN`=`13`,
`CLR_BROWN`=`14`, `CLR_PALEGRAY`=`15`). [DOC-IBM - `pmgpi.h`]

`GpiCreateLogColorTable` maps color indices to values. `lFormat` (`LCOLF_*`) [DOC-IBM]:

| `LCOLF_*` | Value | Table format |
|---|---|---|
| `LCOLF_DEFAULT` | `0` | Reset to the default table |
| `LCOLF_INDRGB` | `1` | `alTable` = (index, RGB) pairs starting at `lStart` |
| `LCOLF_CONSECRGB` | `2` | `alTable` = consecutive RGB values from index `lStart` |
| `LCOLF_RGB` | `3` | RGB mode - the "index" *is* the 24-bit RGB value (no table) |
| `LCOLF_PALETTE` | `4` | Palette mode |

`flOptions` (`LCOL_*`): `LCOL_RESET` (`0x0001`, clear the table first), `LCOL_REALIZABLE`
(`0x0002`), `LCOL_PURECOLOR` (`0x0004`, no dithering), `LCOL_OVERRIDE_DEFAULT_COLORS` (`0x0008`),
`LCOL_REALIZED` (`0x0010`). An RGB value is `0x00RRGGBB`. `CLR_NOINDEX` (`-254`) is returned when
a queried color has no table index. [DOC-IBM - `pmgpi.h`]

Flag and parameter semantics the header states only as constants [DOC - EDM2
"GreCreateLogColorTable"]: `LCOL_RESET` is *assumed automatically* when the table changes from RGB
mode (`LCOLF_RGB`) to index mode (`LCOLF_INDRGB` / `LCOLF_CONSECRGB`). `LCOL_REALIZABLE` merely
*permits* a later color-table realization; without it, realization has no effect and posts a
warning. For `LCOLF_INDRGB` the element count must be even (each entry is an `(index, RGB)` pair);
a count of `0` resets the table to the default (or to `LCOLF_RGB`). An RGB entry is the four-byte
value `(R*65536) + (G*256) + B`, each primary `0`-`255`.

`GpiCreateLogColorTable` return-code conditions (surfaced from the engine) [DOC - EDM2
"GreCreateLogColorTable"]: `PMERR_INV_COLOR_DATA`, `PMERR_INV_COLOR_FORMAT`,
`PMERR_INV_COLOR_INDEX`, `PMERR_INV_COLOR_START_INDEX`, `PMERR_INV_LENGTH_OR_COUNT`,
`PMERR_INV_HDC`, `PMERR_INSUFFICIENT_MEMORY`, `PMERR_REALIZE_NOT_SUPPORTED`.

When the color table is read back, the query path returns per-value sentinels [DOC - EDM2
"GreQueryLogColorTable"]: `QLCT_RGB` - the table is in RGB mode, so no index elements are
returned; `QLCT_NOTLOADED` - placeholder color for an index that is not loaded when the loaded
indices are non-contiguous; `QLCT_ERROR` on failure. The `LCOLOPT_INDEX` option asks for the
result as alternating `(index, value)` pairs rather than bare RGB values.

---

## 9. Text and fonts [DOC-IBM - `pmgpi.h`, `os2def.h`]

```c
LONG APIENTRY GpiCharString  (HPS hps, LONG lCount, PCH pchString);              /* at current pos */
LONG APIENTRY GpiCharStringAt(HPS hps, PPOINTL pptlPoint, LONG lCount, PCH pchString);

LONG APIENTRY GpiCreateLogFont(HPS hps, PSTR8 pName, LONG lLcid, PFATTRS pfatAttrs);
BOOL APIENTRY GpiSetCharSet   (HPS hps, LONG llcid);   /* select a loaded font by its lcid */
LONG APIENTRY GpiQueryCharSet (HPS hps);
BOOL APIENTRY GpiDeleteSetId  (HPS hps, LONG lLcid);   /* LCID_ALL = -1 deletes all         */
BOOL APIENTRY GpiSetCharBox   (HPS hps, PSIZEF psizfxBox);  /* scalable-font cell size       */
BOOL APIENTRY GpiSetCharAngle (HPS hps, PGRADIENTL pgradlAngle);
BOOL APIENTRY GpiSetCharShear (HPS hps, PPOINTL pptlAngle);
BOOL APIENTRY GpiSetTextAlignment(HPS hps, LONG lHoriz, LONG lVert);
BOOL APIENTRY GpiQueryFontMetrics(HPS hps, LONG lMetricsLength, PFONTMETRICS pfmMetrics);
```

`GpiCharString`/`GpiCharStringAt` return the `GPI_OK`/`GPI_ERROR`/`GPI_HITS` code and advance the
current position past the string. Fonts are loaded into a **local identifier (lcid)** and then
selected with `GpiSetCharSet`; `LCID_DEFAULT` (`0`) is the default system font,
`LCID_ERROR` = `-1`. `GpiCreateLogFont` returns `FONT_MATCH` (`2`) if a matching physical font was
found or `FONT_DEFAULT` (`1`) if it fell back to the default. [DOC-IBM - `pmgpi.h`]

### `FATTRS` - logical-font attributes for `GpiCreateLogFont` [DOC-IBM - `os2def.h`]

```c
#define FACESIZE 32

typedef struct _FATTRS {         /* fat */
   USHORT usRecordLength;        /* [0]  = sizeof(FATTRS)               */
   USHORT fsSelection;           /* [2]  italic/underscore/bold flags   */
   LONG   lMatch;                /* [4]  unique match number (0 = any)  */
   CHAR   szFacename[FACESIZE];  /* [8]  face name, e.g. "Helvetica"    */
   USHORT idRegistry;            /* [40] font registry identifier       */
   USHORT usCodePage;            /* [42] code page (0 = default)        */
   LONG   lMaxBaselineExt;       /* [44] char cell height (image fonts) */
   LONG   lAveCharWidth;         /* [48] char cell width  (image fonts) */
   USHORT fsType;                /* [52] type flags                     */
   USHORT fsFontUse;             /* [54] outline/transformable flags    */
} FATTRS;                        /* 56 bytes */
```

For **scalable (outline) fonts** the cell size is set by `GpiSetCharBox` with a `SIZEF`
(fixed-point) rather than by the `FATTRS` extent fields [DOC-IBM - `pmgpi.h`]:

```c
typedef struct _SIZEF { FIXED cx; FIXED cy; } SIZEF;   /* sizfx */
```

`FONTMETRICS` (`os2def.h`, tag `fm`) is the reported metrics record for a selected font, filled by
`GpiQueryFontMetrics`; kerning is reported as `KERNINGPAIRS { SHORT sFirstChar; SHORT sSecondChar;
LONG lKerningAmount; }`. [DOC-IBM - `os2def.h`, `pmgpi.h`]

---

## 10. Bitmaps and bit-block transfer [DOC-IBM - `pmgpi.h`, `pmbitmap.h`]

A bitmap (`HBITMAP`) is created against a memory or compatible DC, selected into a PS with
`GpiSetBitmap`, and transferred with `GpiBitBlt` (PS->PS) or `GpiWCBitBlt` (bitmap-handle->PS, in
world coordinates).

```c
HBITMAP APIENTRY GpiCreateBitmap(HPS hps, PBITMAPINFOHEADER2 pbmpNew, ULONG flOptions,
                                 PBYTE pbInitData, PBITMAPINFO2 pbmiInfoTable);
HBITMAP APIENTRY GpiSetBitmap(HPS hps, HBITMAP hbm);       /* select; returns previous, HBM_ERROR on fail */
BOOL    APIENTRY GpiDeleteBitmap(HBITMAP hbm);
HBITMAP APIENTRY GpiLoadBitmap(HPS hps, HMODULE Resource, ULONG idBitmap, LONG lWidth, LONG lHeight);
LONG    APIENTRY GpiBitBlt(HPS hpsTarget, HPS hpsSource, LONG lCount, PPOINTL aptlPoints,
                           LONG lRop, ULONG flOptions);
LONG    APIENTRY GpiWCBitBlt(HPS hpsTarget, HBITMAP hbmSource, LONG lCount, PPOINTL aptlPoints,
                             LONG lRop, ULONG flOptions);
LONG    APIENTRY GpiSetBitmapBits(HPS hps, LONG lScanStart, LONG lScans, PBYTE pbBuffer, PBITMAPINFO2 pbmi);
```

`lCount` on the blt calls is the number of points in `aptlPoints`: 2 for a source rectangle's two
corners plus the target's (a plain copy uses 3 or 4 depending on stretch), and `lRop` is the
raster operation. `flOptions` (`CBM_INIT` = `0x0004` on `GpiCreateBitmap` means "initialise from
`pbInitData`"). Blt return codes: `GPI_OK`/`GPI_ERROR`; `GpiSetBitmap` returns `HBM_ERROR`
(`(HBITMAP)-1`) on failure. [DOC-IBM - `pmgpi.h`]

Raster operations (`ROP_*`) [DOC-IBM - `pmgpi.h`]:

| `ROP_*` | Value | | `ROP_*` | Value |
|---|---|---|---|---|
| `ROP_SRCCOPY` | `0x00CC` | | `ROP_PATCOPY` | `0x00F0` |
| `ROP_SRCPAINT` | `0x00EE` | | `ROP_PATPAINT` | `0x00FB` |
| `ROP_SRCAND` | `0x0088` | | `ROP_PATINVERT` | `0x005A` |
| `ROP_SRCINVERT`| `0x0066` | | `ROP_DSTINVERT` | `0x0055` |
| `ROP_SRCERASE` | `0x0044` | | `ROP_MERGECOPY` | `0x00C0` |
| `ROP_NOTSRCCOPY`|`0x0033` | | `ROP_MERGEPAINT`| `0x00BB` |
| `ROP_NOTSRCERASE`|`0x0011`| | `ROP_ZERO` / `ROP_ONE` | `0x0000` / `0x00FF` |

Blt options (`BBO_*`, color-compression when stretching) [DOC-IBM - `pmgpi.h`]: `BBO_OR` (`0`),
`BBO_AND` (`1`), `BBO_IGNORE` (`2`), `BBO_PAL_COLORS` (`4`), `BBO_NO_COLOR_INFO` (`8`).

### Bitmap headers [DOC-IBM - `pmbitmap.h`]

The version-1 header (`bmp`, tag) is the compact form; the version-2 header (`bmp2`) that
`GpiCreateBitmap` takes adds compression, resolution, and color-encoding fields:

```c
typedef struct _BITMAPINFOHEADER {   /* bmp - 12 bytes */
   ULONG  cbFix;      /* [0]  length of this structure         */
   USHORT cx;         /* [4]  width in pels                    */
   USHORT cy;         /* [6]  height in pels                   */
   USHORT cPlanes;    /* [8]  number of bit planes             */
   USHORT cBitCount;  /* [10] bits per pel within a plane      */
} BITMAPINFOHEADER;

typedef struct _BITMAPINFOHEADER2 {  /* bmp2 */
   ULONG  cbFix;           /* [0]  length of structure          */
   ULONG  cx;              /* [4]  width in pels                */
   ULONG  cy;              /* [8]  height in pels               */
   USHORT cPlanes;         /* [12] number of bit planes         */
   USHORT cBitCount;       /* [14] bits per pel                 */
   ULONG  ulCompression;   /* [16] BCA_* compression scheme     */
   ULONG  cbImage;         /* [20] length of bitmap data bytes  */
   ULONG  cxResolution;    /* [24] x resolution of target       */
   ULONG  cyResolution;    /* [28] y resolution of target       */
   ULONG  cclrUsed;        /* [32] color indices used           */
   ULONG  cclrImportant;   /* [36] important color indices      */
   USHORT usUnits;         /* [40] units of measure (BRU_METRIC)*/
   USHORT usReserved;      /* [42]                              */
   USHORT usRecording;     /* [44] recording algorithm (BRA_*)  */
   USHORT usRendering;     /* [46] halftoning algorithm (BRH_*) */
   ULONG  cSize1;          /* [48] size value 1                 */
   ULONG  cSize2;          /* [52] size value 2                 */
   ULONG  ulColorEncoding; /* [56] color encoding (BCE_RGB/PALETTE) */
   ULONG  ulIdentifier;    /* [60] reserved for application use */
} BITMAPINFOHEADER2;        /* 64 bytes */
```

`cbFix` is the discriminator between the two forms - a caller sets it to the size of the header it
is passing, and the engine reads that many bytes. Compression schemes (`ulCompression`) [DOC-IBM
- `pmbitmap.h`]: `BCA_UNCOMP` (`0`), `BCA_RLE8` (`1`), `BCA_RLE4` (`2`), `BCA_HUFFMAN1D` (`3`),
`BCA_RLE24` (`4`). Recording order: `BRA_BOTTOMUP` (`0`, first scan = bottom row). Color encoding:
`BCE_RGB` (`0`) or `BCE_PALETTE` (`-1`). The color table follows the header as an array of `RGB {
BYTE bBlue; BYTE bGreen; BYTE bRed; }` (v1 `BITMAPINFO`) entries. [DOC-IBM - `pmbitmap.h`]

---

## 11. `Gpi*` -> `Gre*` engine mapping [DOC - EDM2]

Each `Gpi*` primitive above is executed by one (or several) `Gre*` entry point(s) in the graphics
engine / presentation driver; the `Gre*` layer is where the primitive actually reaches pels. The
mapping is not always 1:1 - a single `Gpi*` call may drive several `Gre*` calls - but the
correspondence below is the common case. The engine internals (which `Gre*` calls the driver
*must* support, which the engine *simulates*, and the GRE/VMAN/driver dispatch) are in
`pm-graphics.md`; this table only names the backing call so a reader can cross to it.

| `Gpi*` (this doc) | Backing `Gre*` call | What the engine call does |
|---|---|---|
| `GpiBitBlt` / `GpiWCBitBlt` (section 10) | `GreBitblt` | Modifies bit-map data at a target rectangle in the current DC [DOC - EDM2 "GreBitblt"] |
| `GpiBox` (section 6) | `GreBoxBoundary` | Draws a box from the current (X,Y) to the specified opposite corner [DOC - EDM2 "GreBoxBoundary"] |
| `GpiFullArc` (fill) (section 5) | `GreFullArcInterior` | Draws a filled full arc using the current pattern, centred at the current position [DOC - EDM2 "GreFullArcInterior"] |
| `GpiBeginArea`...`GpiEndArea` (section 7) | `GreAreaSetAttributes` | Sets the area/path fill attributes; engine-simulated, hooked by drivers that do their own area/path fill [DOC - EDM2 "GreAreaSetAttributes"] |
| `GpiModifyPath` (section 7) | `GreModifyPath` | Modifies a path; returns BOOLEAN success [DOC - EDM2 "GreModifyPath"] |
| `GpiPathToRegion` / region create (section 7) | `GreCreateRectRegion` | Creates a region as the OR of a series of rectangles [DOC - EDM2 "GreCreateRectRegion"] |
| region point test (section 7) | `GrePtInRegion` | Point-in-region hit test (see section 7) [DOC - EDM2 "GrePtInRegion"] |
| `GpiSet*TransformMatrix` concat (section 4) | `GreMultiplyXforms` | Concatenates/overwrites a transform matrix (`SX_CAT_AFTER`/`SX_CAT_BEFORE`/`SX_OVERWRITE`/`SX_UNITY`) [DOC - EDM2 "GreMultiplyXforms"] |
| `GpiCreateLogFont` (section 9) | `GreCreateLogicalFont` (+ `GreRealizeFont`) | Describes the logical font and returns the `FONT_MATCH`/`FONT_DEFAULT` match result; `GreRealizeFont` realizes it for the device [DOC - EDM2 "GreCreateLogicalFont", "GreRealizeFont"] |
| text extent / `GpiQueryTextBox` (section 9) | `GreQueryTextBox` | Processes a string as if it were drawn and returns its bounding box [DOC - EDM2 "GreQueryTextBox"] |
| `GpiCreateLogColorTable` (section 8) | `GreCreateLogColorTable` | Loads the logical color table (see section 8) [DOC - EDM2 "GreCreateLogColorTable"] |
| `GpiQueryLogColorTable` (section 8) | `GreQueryLogColorTable` | Reads back the logical color table (see section 8) [DOC - EDM2 "GreQueryLogColorTable"] |

---

## See also

- `pm-graphics.md` - the engine below this API: how `Gpi*` primitives reach pels through GRE /
  VMAN / the presentation driver, and the device-context / aperture model at the driver level.
- `message-queue.md` - how `WM_PAINT`, the message that drives window drawing, is delivered.
- `gpi-fonts-and-metafiles.md` - logical/physical fonts (`FATTRS`, `FONTMETRICS`), font loading and
  text metrics, and metafile recording/playback that build on this DC/PS and `GpiCharStringAt`.
