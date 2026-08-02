# DIVE - Direct Interface Video Extensions

**DIVE** (Direct Interface Video Extensions) is the OS/2 multimedia system's fast-video
interface: a single stand-alone DLL that gives motion-video decoders, interactive games, and
3-D graphics libraries an optimized path to the screen. Its purpose is to consolidate the
awkward, device-specific work of writing straight into video memory - the "direct access" or
"black hole" path - into one API that handles clipping to the visible region, image scaling,
color-space (pel-format) conversion, and bank switching on banked displays. An application can
either hand pixels to the **DIVE blitter** (which uses acceleration hardware where present) and
let DIVE do the clipping/conversion, or take a raw pointer to the frame buffer and do that work
itself. DIVE is what OS/2's software motion-video path (video stream handlers / CODECs) uses to
reach the screen, and it is equally usable directly by an application.

Provenance: structures, prototypes, constant values, and error codes are confirmed against
the OS/2 Toolkit 4.5 headers `dive.h` and `fourcc.h`; semantics and the usage model are from the
IBM *Multimedia Application Programming Guide*. Per-fact tags: **[DOC-IBM]** = IBM documentation
(the header, cited `file:line`, or the programming guide); **[unverified]** = a semantic the
sources examined do not state. No fact here is originated; where the header is silent it is
marked.

---

## 1. Architecture and model

DIVE is a display **engine** implemented as one DLL. It sits above the low-level device-driver
DIVE interface, abstracting it to a higher level and adding software emulation for operations
(scaling, color conversion) that video CODECs previously had to perform themselves. [DOC-IBM,
mmapg.txt "DIVE Display Engine Functional Characteristics"]

An application obtains a **DIVE instance handle** (`HDIVE`) from `DiveOpen` and releases it with
`DiveClose`. There are up to `MAX_DIVE_INSTANCES` (64) instances. [DOC-IBM, dive.h:19]
`HDIVE` and `FOURCC` are both `ULONG`. [DOC-IBM, dive.h:21-22]

Two ways to use an instance: [DOC-IBM, mmapg.txt "Using Dive"]

- **The DIVE blitter.** The application fills *image buffers* (identified by small integer
  buffer numbers), describes the source and destination with `DiveSetupBlitter`, then calls
  `DiveBlitImage` to transfer buffer->screen or buffer->buffer. DIVE performs the clipping,
  scaling, and color conversion.
- **Direct frame-buffer access.** `DiveOpen` (with `fNonScreenInstance = FALSE`) returns a
  pointer to the frame buffer; the application does its own clipping, color conversion, and bank
  switching, bracketing writes with `DiveAcquireFrameBuffer` / `DiveDeacquireFrameBuffer` and
  using `DiveSwitchBank` / `DiveCalcFrameBufferAddress` as needed.

Because DIVE writes to the screen while bypassing Presentation Manager, a screen-target DIVE
application must keep DIVE informed of its window's **visible region** so output is clipped to
what PM currently shows. The application requests visible-region notification at window init,
and thereafter responds to `WM_VRNDISABLED` (call `DiveSetupBlitter(hDiveInst, 0)` to suspend
blitting) and `WM_VRNENABLED` (re-query the region with `WinQueryVisibleRegion` and pass the new
rectangles via `DiveSetupBlitter`). Rectangles are passed in window coordinates with the window
position in desktop coordinates. [DOC-IBM, mmapg.txt lines 4994-5008]

> **The screen cannot be used as a *source* for blitting.** [DOC-IBM, mmapg.txt line 5069]

### Buffer numbers and planes

Allocated/associated image buffers are numbered starting at `0x00000010`. [DOC-IBM, dive.h:63]
Three well-known destination "buffer" identifiers select a screen plane in `DiveBlitImage`:

| Constant | Value | Meaning |
|---|---|---|
| `DIVE_BUFFER_SCREEN` | `0x00000000` | Let DIVE pick graphics vs. alternate plane (and paint the overlay key on the graphics plane if it chooses the alternate). [DOC-IBM, dive.h:55,70-75] |
| `DIVE_BUFFER_GRAPHICS_PLANE` | `0x00000001` | Transfer to the graphics plane. [DOC-IBM, dive.h:56,65] |
| `DIVE_BUFFER_ALTERNATE_PLANE` | `0x00000002` | Transfer to the alternate (overlay) plane; an error if the hardware has none. [DOC-IBM, dive.h:57,67] |

`DIVE_FULLY_VISIBLE` (`0xffffffff`) is a sentinel for `ulNumDstRects` meaning "the whole
destination is visible" - usable when the application knows there is no clipping (e.g. a
non-screen destination) rather than constructing a visible-region array. [DOC-IBM,
dive.h:59,156-158]

---

## 2. Function surface

{symbol -> purpose}

| Function | Purpose |
|---|---|
| `DiveQueryCaps` | Query display capabilities and supported input/output color formats (fills `DIVE_CAPS`). [DOC-IBM, dive.h:169] |
| `DiveOpen` | Create a DIVE instance; return `HDIVE` and (for a screen instance) a frame-buffer pointer. [DOC-IBM, dive.h:172] |
| `DiveClose` | Destroy a DIVE instance. [DOC-IBM, dive.h:192] |
| `DiveSetupBlitter` | Describe source/destination formats, sizes, positions, and the visible-region rectangles for subsequent blits. [DOC-IBM, dive.h:176] |
| `DiveBlitImage` | Transfer a source buffer to a destination buffer/screen plane using the current blitter setup. [DOC-IBM, dive.h:179] |
| `DiveBlitImageLines` | Same as `DiveBlitImage` with a per-line change mask (`INCL_MM_OS2`). [DOC-IBM, dive.h:186] |
| `DiveAllocImageBuffer` | Allocate a DIVE image buffer, or *associate* a user-supplied buffer, of a given color format and geometry. [DOC-IBM, dive.h:222] |
| `DiveFreeImageBuffer` | Free/release an image buffer or buffer association. [DOC-IBM, dive.h:230] |
| `DiveBeginImageBufferAccess` | Lock a buffer for CPU access; return its address and scan-line geometry. [DOC-IBM, dive.h:233] |
| `DiveEndImageBufferAccess` | Release CPU access to a buffer. [DOC-IBM, dive.h:239] |
| `DiveSetSourcePalette` | Give DIVE the source image's 8-bit CLUT palette entries. [DOC-IBM, dive.h:284] |
| `DiveSetDestinationPalette` | Give DIVE the destination palette entries. [DOC-IBM, dive.h:279] |
| `DiveSetTransparentBlitMode` | Set the transparency/color-key mode for the blitter (`INCL_MM_OS2`). [DOC-IBM, dive.h:290] |
| `DiveAcquireFrameBuffer` | Acquire the frame buffer for direct writes to a destination rectangle. [DOC-IBM, dive.h:194] |
| `DiveDeacquireFrameBuffer` | Release the frame buffer after direct writes. [DOC-IBM, dive.h:200] |
| `DiveSwitchBank` | Select a VRAM bank on a bank-switched display. [DOC-IBM, dive.h:197] |
| `DiveCalcFrameBufferAddress` | Compute the frame-buffer address (and bank / remaining-lines) for a desktop rectangle. [DOC-IBM, dive.h:202] |

Every entry point returns `ULONG` (`DIVE_SUCCESS` = `0`, or a `DIVE_ERR_*`/`DIVE_WARN_*` code)
and uses `APIENTRY` linkage. [DOC-IBM, dive.h:24-53,169-240]

> Secondary sources sometimes name a `DiveSetDestinationColorKey`; no such symbol exists in the
> Toolkit's `dive.h`. The color-key/transparency mechanism is `DiveSetTransparentBlitMode` plus
> destination color-key handling implied by the alternate-plane "key color" note (dive.h:75).
> Treat a distinct `DiveSetDestinationColorKey` entry point as **[unverified]** - not present in
> the source examined.

### Lifecycle: open and close

```c
ULONG APIENTRY DiveOpen ( HDIVE *phDiveInst, BOOL fNonScreenInstance, PVOID ppFrameBuffer );
ULONG APIENTRY DiveClose ( HDIVE hDiveInst );
```
[DOC-IBM, dive.h:172-174,192]

`fNonScreenInstance = FALSE` opens a screen instance and returns a frame-buffer pointer in
`ppFrameBuffer`; `TRUE` opens a non-screen instance (off-screen sizing or color conversion only),
and no frame-buffer pointer is meaningful. A matching `DiveClose` must be made at termination.
[DOC-IBM, mmapg.txt line 4949]

---

## 3. `DiveQueryCaps` and `DIVE_CAPS`

`DiveQueryCaps(PDIVE_CAPS pDiveCaps, ULONG ulPlaneBufNum)` reports what the display can do - depth,
resolution, scan-line size, whether the plane is directly addressable and/or bank-switched, its
color encoding, and the set of supported input/output FOURCC formats. [DOC-IBM, dive.h:169]

```c
typedef struct _DIVE_CAPS {
   ULONG  ulStructLen;            /* = sizeof(DIVE_CAPS)                 */
   ULONG  ulPlaneCount;           /* number of defined planes            */
   BOOL   fScreenDirect;          /* TRUE if VRAM is directly addressable*/
   BOOL   fBankSwitched;          /* TRUE if VRAM is bank-switched        */
   ULONG  ulDepth;                /* bits per pixel                       */
   ULONG  ulHorizontalResolution; /* screen width, pixels                 */
   ULONG  ulVerticalResolution;   /* screen height, pixels                */
   ULONG  ulScanLineBytes;        /* screen scan-line size, bytes         */
   FOURCC fccColorEncoding;       /* screen colorspace encoding           */
   ULONG  ulApertureSize;         /* VRAM aperture size, bytes            */
   ULONG  ulInputFormats;         /* count of input color formats         */
   ULONG  ulOutputFormats;        /* count of output color formats        */
   ULONG  ulFormatLength;         /* length of format buffer              */
   PVOID  pFormatData;            /* -> array of FOURCC's                 */
} DIVE_CAPS;
```
[DOC-IBM, dive.h:82-103] The caller sets `ulStructLen`; `pFormatData` points at a caller buffer
into which DIVE writes the supported-format FOURCCs. [DOC-IBM, dive.h:84,99-100]

---

## 4. The blitter setup - `SETUP_BLITTER`

`DiveSetupBlitter(HDIVE hDiveInst, PSETUP_BLITTER pSetupBlitter)` establishes everything a
subsequent `DiveBlitImage` needs: the source and destination color formats and geometry, the
sub-rectangle to display, screen position, and the visible-region clip list. It must be called
again whenever the visible region, source color format, or source/destination size changes.
[DOC-IBM, dive.h:176; mmapg.txt line 5008] Calling `DiveSetupBlitter(hDiveInst, 0)` (a NULL setup
pointer) suspends blitting - used in response to `WM_VRNDISABLED`. [DOC-IBM, mmapg.txt line 5002]

```c
typedef struct _SETUP_BLITTER {
   ULONG  ulStructLen;        /* bytes of the struct actually used        */
   ULONG  fInvert;            /* b0001 flip horizontal, b0010 flip vertical*/

   FOURCC fccSrcColorFormat;  /* source pel format (see FOURCC below)      */
   ULONG  ulSrcWidth;         /* source image width, pixels                */
   ULONG  ulSrcHeight;        /* source image height, pixels               */
   ULONG  ulSrcPosX;          /* source sub-rect X origin                  */
   ULONG  ulSrcPosY;          /* source sub-rect Y origin                  */

   ULONG  ulDitherType;       /* 0 = none, 1 = 2x2 (direct-color -> LUT8) */

   FOURCC fccDstColorFormat;  /* destination pel format                    */
   ULONG  ulDstWidth;         /* destination width, pixels                 */
   ULONG  ulDstHeight;        /* destination height, pixels                */
   LONG   lDstPosX;           /* destination sub-rect X                    */
   LONG   lDstPosY;           /* destination sub-rect Y                    */

   LONG   lScreenPosX;        /* window X in desktop coords (screen dst)   */
   LONG   lScreenPosY;        /* window Y in desktop coords, 0 = bottom    */

   ULONG  ulNumDstRects;      /* count of visible rects, or DIVE_FULLY_VISIBLE */
   PRECTL pVisDstRects;       /* -> array of visible rectangles            */
} SETUP_BLITTER;
```
[DOC-IBM, dive.h:108-165]

Notes on the fields, from the header: [DOC-IBM, dive.h:110-162]

- **`ulStructLen`** is set to the number of bytes actually used; the header marks the legal
  partial sizes 8, 28, 32, 52, 60, or 68 - so a caller may fill only a prefix of the struct.
- **`fInvert`** flips the image: bit 0 horizontal, bit 1 vertical; other bits ignored.
- **Source vs. destination geometry.** A width/height mismatch between source and destination is
  how scaling is requested. `ulSrcPosX/Y` and `lDstPosX/Y` select sub-rectangles. Destination
  positions are signed (`LONG`); source positions are unsigned.
- **`ulDitherType`** - `0` no dither, `1` a 2x2 dither; dithering applies only to direct-color ->
  `LUT8` conversion.
- **`lScreenPosX/lScreenPosY`** - the window's position in world/desktop coordinates, with Y
  measured from the bottom (`0` = bottom). Ignored unless the destination is the screen.
- **`ulNumDstRects` / `pVisDstRects`** - the visible-region rectangle list (window coordinates),
  ignored for non-screen destinations; use `DIVE_FULLY_VISIBLE` when there is no clipping.

For a non-screen (buffer->buffer) blit, the destination is described purely by
`fccDstColorFormat` / `ulDstWidth` / `ulDstHeight`, with `ulNumDstRects = 1` and a single
rectangle `(0, 0, ulDstWidth, ulDstHeight)`. [DOC-IBM, mmapg.txt line 5062]

---

## 5. Image buffers

DIVE prefers to allocate source buffers itself, because it can place them in off-screen VRAM to
accelerate blits. [DOC-IBM, mmapg.txt line 4952] The buffer lifecycle is
**allocate -> begin-access -> fill -> end-access -> blit -> free**.

```c
ULONG APIENTRY DiveAllocImageBuffer ( HDIVE hDiveInst, PULONG pulBufferNumber,
                                      FOURCC fccColorSpace, ULONG ulWidth, ULONG ulHeight,
                                      ULONG ulLineSizeBytes, PBYTE pbImageBuffer );
ULONG APIENTRY DiveFreeImageBuffer ( HDIVE hDiveInst, ULONG ulBufferNumber );

ULONG APIENTRY DiveBeginImageBufferAccess ( HDIVE hDiveInst, ULONG ulBufferNumber,
                                            PBYTE *ppbImageBuffer,
                                            PULONG pulBufferScanLineBytes,
                                            PULONG pulBufferScanLines );
ULONG APIENTRY DiveEndImageBufferAccess ( HDIVE hDiveInst, ULONG ulBufferNumber );
```
[DOC-IBM, dive.h:222-240]

- **`DiveAllocImageBuffer`** returns the new buffer number in `*pulBufferNumber`. If
  `pbImageBuffer` is non-NULL the call *associates* a caller-owned buffer instead of allocating
  one; if additionally `*pulBufferNumber` is non-zero, a new pointer is associated with that
  existing buffer number. Associated (user) buffers still require `DiveFreeImageBuffer` to
  release the buffer-index association even though no DIVE memory was allocated. If
  `ulLineSizeBytes` is 0, the allocated line size is rounded up to the next DWORD boundary.
  [DOC-IBM, dive.h:208-228]
- **`DiveBeginImageBufferAccess`** locks the buffer for CPU access and returns its base address
  in `*ppbImageBuffer` and its geometry in `*pulBufferScanLineBytes` (bytes per scan line, which
  DIVE computes from the color format) and `*pulBufferScanLines`. The application writes pixel
  data using the returned scan-line stride - a line at a time - then calls
  `DiveEndImageBufferAccess` before blitting. [DOC-IBM, dive.h:233-240; mmapg.txt lines 4973-4979]

### Blitting

```c
ULONG APIENTRY DiveBlitImage ( HDIVE hDiveInst, ULONG ulSrcBufNumber, ULONG ulDstBufNumber );
ULONG APIENTRY DiveBlitImageLines ( HDIVE hDiveInst, ULONG ulSrcBufNumber,
                                    ULONG ulDstBufNumber, PBYTE pbLineMask ); /* INCL_MM_OS2 */
```
[DOC-IBM, dive.h:179-189]

`DiveBlitImage` transfers `ulSrcBufNumber` to `ulDstBufNumber`, where the destination may be an
allocated buffer number or one of the `DIVE_BUFFER_*` screen-plane identifiers (section 1). The current
`DiveSetupBlitter` settings govern conversion, scaling, inversion, and clipping.
`DiveBlitImageLines` is identical but takes `pbLineMask`, one byte per source line - `0` means
the line is unchanged (skip it), `0xFF` means changed - for partial-frame updates. [DOC-IBM,
dive.h:179-189]

---

## 6. Palettes

For 8-bit CLUT (`LUT8`) work, DIVE must be told both the *physical* palette state and the
image's own palette. [DOC-IBM, mmapg.txt lines 4981-4992]

```c
ULONG APIENTRY DiveSetSourcePalette      ( HDIVE hDiveInst, ULONG ulStartIndex,
                                           ULONG ulNumEntries, PBYTE pbRGB2Entries );
ULONG APIENTRY DiveSetDestinationPalette ( HDIVE hDiveInst, ULONG ulStartIndex,
                                           ULONG ulNumEntries, PBYTE pbRGB2Entries );
```
[DOC-IBM, dive.h:279-287]

`pbRGB2Entries` points at an array of `ulNumEntries` palette entries (`RGB2`-format), starting at
palette index `ulStartIndex`. Two sentinel pointer values ask DIVE to query and use a
system-defined table: [DOC-IBM, dive.h:273-277]

| Constant | Value | Meaning |
|---|---|---|
| `DIVE_PALETTE_PHYSICAL` | `(PBYTE)0x00000000` | Use the current physical palette. |
| `DIVE_PALETTE_DEFAULT` | `(PBYTE)0xffffffff` | Use the default palette. |

**Neither** palette call sets the *physical* hardware palette - they only inform DIVE of what a
palette is for conversion. [DOC-IBM, dive.h:245] The header cautions that an application which
must set the physical palette should confine itself to the middle 236 entries (10-245, leaving 10
at each end for the Workplace Shell), or run full-screen if it needs all 256; and that doing so
sends no `WM_REALIZEPALETTE` to other applications, so their colors will be wrong - the practice
is discouraged. The physical palette is set via a PM sequence
(`GpiCreateLogColorTable` + `Gre32EntrY3(hdc, 0, 0x000060C6)`), not through DIVE. [DOC-IBM,
dive.h:244-270] Applications must call `DiveSetSourcePalette` at init and again on each
`WM_REALIZEPALETTE`; for an animation whose palette is constant across frames, one call before
the first frame suffices. [DOC-IBM, mmapg.txt lines 4982-4992]

---

## 7. Direct frame-buffer access

The `ppFrameBuffer` returned by `DiveOpen` gives direct addressability to VRAM. When writing
directly, the application performs its own clipping, color conversion, and bank switching.
[DOC-IBM, mmapg.txt line 5093]

```c
ULONG APIENTRY DiveAcquireFrameBuffer     ( HDIVE hDiveInst, PRECTL prectlDst );
ULONG APIENTRY DiveDeacquireFrameBuffer   ( HDIVE hDiveInst );
ULONG APIENTRY DiveSwitchBank             ( HDIVE hDiveInst, ULONG ulBankNumber );
ULONG APIENTRY DiveCalcFrameBufferAddress ( HDIVE hDiveInst, PRECTL prectlDest,
                                            PBYTE *ppDestinationAddress,
                                            PULONG pulBankNumber, PULONG pulRemLinesInBank );
```
[DOC-IBM, dive.h:194-206]

`DiveCalcFrameBufferAddress` maps a desktop-coordinate rectangle to a frame-buffer address plus
the bank number and the count of remaining scan lines in that bank. `prectlDest` must lie within
the window's visible region for correct clipping. On a bank-switched display the application must
not write more than `*pulRemLinesInBank` lines before calling `DiveSwitchBank`. Data written
directly must already be in the screen's color-encoding (from `DiveQueryCaps`) and, at 256
colors, match the current physical palette - DIVE's blitter can be used beforehand to convert
into a same-encoding destination buffer. [DOC-IBM, mmapg.txt lines 5095-5106]

---

## 8. Transparent (color-key) blitting - `INCL_MM_OS2`

`DiveSetTransparentBlitMode` composites graphics and image data using a transparency key: a
destination pixel is left unchanged where the corresponding source pixel is "transparent"
according to the selected mode. [DOC-IBM, dive.h:290-330]

```c
ULONG APIENTRY DiveSetTransparentBlitMode ( HDIVE hDiveInst, ULONG ulTransBlitMode,
                                            ULONG ulValue1, ULONG ulValue2 );
```
[DOC-IBM, dive.h:290-293]

| Mode | Value | Meaning |
|---|---|---|
| `DIVE_TBM_NONE` | `0x0` | No transparency; all pixels transferred (default). [DOC-IBM, dive.h:297] |
| `DIVE_TBM_EXCLUDE_SOURCE_VALUE` | `0x01` | Skip source pixels exactly equal to `ulValue1`. [DOC-IBM, dive.h:300] |
| `DIVE_TBM_EXCLUDE_SOURCE_RGB_RANGE` | `0x02` | Skip source pixels inside the RGB range `[ulValue1..ulValue2]`. [DOC-IBM, dive.h:304] |
| `DIVE_TBM_INCLUDE_SOURCE_RGB_RANGE` | `0x03` | Skip source pixels outside the RGB range. [DOC-IBM, dive.h:309] |
| `DIVE_TBM_EXCLUDE_SOURCE_YUV_RANGE` | `0x04` | Skip source pixels inside the YUV range. [DOC-IBM, dive.h:314] |
| `DIVE_TBM_INCLUDE_SOURCE_YUV_RANGE` | `0x05` | Skip source pixels outside the YUV range. [DOC-IBM, dive.h:319] |

The `ulValue1`/`ulValue2` encoding depends on the source format: for `FOURCC_LUT8` the key is the
low 8 bits; for YUV formats it is packed `23:8 = Y, 15:8 = U, 7:8 = V`; for RGB formats
`23:8 = R, 15:8 = G, 7:8 = B` with 8-bit significance regardless of the source depth. Range tests
compare the three components independently (`min <= value <= max`). When the range color space
differs from the source's, DIVE converts using standard CCIR601 equations. Transparent blitting
is supported only for the LUT8/RGB/YUV source formats listed in the header; other source formats
are not supported. [DOC-IBM, dive.h:324-376]

---

## 9. Color formats (FOURCC)

DIVE identifies every pel format by a **FOURCC** (a `ULONG` built from four characters via
`mmioFOURCC`), defined in `fourcc.h`. `FOURCC_SCRN` (value `0`) is the special "use the screen's
own format" code. [DOC-IBM, fourcc.h:20-42]

{symbol -> format}

| FOURCC | Value (chars) | Description |
|---|---|---|
| `FOURCC_SCRN` | `0` | Use the screen's native format (typically LUT8, R565, or BGR3). [DOC-IBM, fourcc.h:20,51] |
| `FOURCC_LUT8` | `'LUT8'` | 8-bit CLUT, 1 byte/pixel; a 256-entry BGR4 palette is the lookup table. [DOC-IBM, fourcc.h:28,95-98] |
| `FOURCC_LT12` | `'LT12'` | 12-bit CLUT, 2 bytes/pixel; 4096-entry BGR4 palette. [DOC-IBM, fourcc.h:29,100-103] |
| `FOURCC_R565` | `'R565'` | RGB 16-bit, 5-6-5, 2 bytes/pixel. [DOC-IBM, fourcc.h:21,53-57] |
| `FOURCC_R555` | `'R555'` | RGB 16-bit, 5-5-5 (1 unused), 2 bytes/pixel. [DOC-IBM, fourcc.h:22,59-63] |
| `FOURCC_R664` | `'R664'` | RGB 16-bit, 6-6-4, 2 bytes/pixel. [DOC-IBM, fourcc.h:23,65-69] |
| `FOURCC_RGB3` | `'RGB3'` | 24-bit, 3 bytes/pixel, memory order R,G,B. [DOC-IBM, fourcc.h:24,71-75] |
| `FOURCC_BGR3` | `'BGR3'` | 24-bit, 3 bytes/pixel, memory order B,G,R. [DOC-IBM, fourcc.h:25,77-81] |
| `FOURCC_RGB4` | `'RGB4'` | 32-bit, 4 bytes/pixel, memory order R,G,B,x. [DOC-IBM, fourcc.h:26,83-87] |
| `FOURCC_BGR4` | `'BGR4'` | 32-bit, 4 bytes/pixel, memory order B,G,R,x. [DOC-IBM, fourcc.h:27,89-93] |
| `FOURCC_GREY` | `'GREY'` | 8-bit greyscale. [DOC-IBM, fourcc.h:30] |
| `FOURCC_GY16` | `'GY16'` | 16-bit greyscale. [DOC-IBM, fourcc.h:31] |
| `FOURCC_MONO` | `'MONO'` | 1 bit/pixel, 0 = black / 1 = white. [DOC-IBM, fourcc.h:37,160-164] |
| `FOURCC_VGA` | `'VGA '` | 16-color VGA, two 4-bit pixels per byte. [DOC-IBM, fourcc.h:42,206-210] |
| `FOURCC_Y888` | `'Y888'` | YUV, three full-size planes (CCIR601). [DOC-IBM, fourcc.h:32,105-123] |
| `FOURCC_Y2X2` | `'Y2X2'` | YUV, three planes, chroma 2x2 subsampled. [DOC-IBM, fourcc.h:33,125-135] |
| `FOURCC_Y4X4` | `'Y4X4'` | YUV, three planes, chroma 4x4 subsampled. [DOC-IBM, fourcc.h:34,137-145] |
| `FOURCC_YUV9` | `'YUV9'` | DVI/Indeo three-plane 4x4-subsampled (same as Y4X4). [DOC-IBM, fourcc.h:35,147-148] |
| `FOURCC_Y644` | `'Y644'` | Two-plane; Y plane + 4x4-subsampled combined UV plane. [DOC-IBM, fourcc.h:36,150-158] |
| `FOURCC_Y422` | `'Y422'` | Single-plane interleaved Y-U-Y-V (2x1 subsampled). [DOC-IBM, fourcc.h:38,166-174] |
| `FOURCC_Y42B` | `'Y42B'` | Y422 byte-swapped within words. [DOC-IBM, fourcc.h:39,176-180] |
| `FOURCC_Y42D` | `'Y42D'` | Y422 byte-swapped within DWORDs. [DOC-IBM, fourcc.h:40,182-186] |
| `FOURCC_Y411` | `'Y411'` | Single-plane interleaved, 4x1 subsampled. [DOC-IBM, fourcc.h:41,188-204] |

The RGB bit layouts (e.g. `R565` = `rrrrr gggggg bbbbb` in a USHORT) and the CCIR601 conversion
equations for the YUV formats are given field-by-field in `fourcc.h`. [DOC-IBM, fourcc.h:53-204]
A **conversion support matrix** in the same header shows which (input -> output) format pairs the
DIVE blitter converts; broadly, the RGB/`LUT8` output rows and `Y422` accept nearly all listed
inputs, while most YUV planar formats are inputs only. [DOC-IBM, fourcc.h:215-241] The programming
guide lists the engine's supported input formats (`LUT8`, `GREY`, `R565`/`R555`/`R664`,
`RGB3`/`BGR3`, `RGB4`/`BGR4`, `YUV9`, `Y422`, `Y2X2`, `Y4X4`) and output formats (CLUT8, RGB 16
in 5-6-5/5-5-5/6-6-4, RGB 24, RGB 32, and `Y422`). [DOC-IBM, mmapg.txt "DIVE Display Engine
Functional Characteristics"]

---

## 10. Return codes

All DIVE functions return `DIVE_SUCCESS` (`0`) or one of these. [DOC-IBM, dive.h:24-53]

| Code | Value | Meaning (name-derived) |
|---|---|---|
| `DIVE_SUCCESS` | `0x00000000` | Success. |
| `DIVE_ERR_INVALID_INSTANCE` | `0x00001000` | Bad `HDIVE`. |
| `DIVE_ERR_SOURCE_FORMAT` | `0x00001001` | Unsupported/invalid source format. |
| `DIVE_ERR_DESTINATION_FORMAT` | `0x00001002` | Unsupported/invalid destination format. |
| `DIVE_ERR_BLITTER_NOT_SETUP` | `0x00001003` | Blit attempted before `DiveSetupBlitter`. |
| `DIVE_ERR_INSUFFICIENT_LENGTH` | `0x00001004` | Buffer/struct length too small. |
| `DIVE_ERR_TOO_MANY_INSTANCES` | `0x00001005` | `MAX_DIVE_INSTANCES` exceeded. |
| `DIVE_ERR_NO_DIRECT_ACCESS` | `0x00001006` | Direct VRAM access unavailable. |
| `DIVE_ERR_NOT_BANK_SWITCHED` | `0x00001007` | Bank op on a non-banked display. |
| `DIVE_ERR_INVALID_BANK_NUMBER` | `0x00001008` | Bad bank number. |
| `DIVE_ERR_FB_NOT_ACQUIRED` | `0x00001009` | Frame buffer not acquired. |
| `DIVE_ERR_FB_ALREADY_ACQUIRED` | `0x0000100a` | Frame buffer already acquired. |
| `DIVE_ERR_ACQUIRE_FAILED` | `0x0000100b` | Acquire failed. |
| `DIVE_ERR_BANK_SWITCH_FAILED` | `0x0000100c` | Bank switch failed. |
| `DIVE_ERR_DEACQUIRE_FAILED` | `0x0000100d` | Deacquire failed. |
| `DIVE_ERR_INVALID_PALETTE` | `0x0000100e` | Bad palette. |
| `DIVE_ERR_INVALID_DESTINATION_RECTL` | `0x0000100f` | Bad destination rectangle. |
| `DIVE_ERR_INVALID_BUFFER_NUMBER` | `0x00001010` | Bad buffer number. |
| `DIVE_ERR_SSMDD_NOT_INSTALLED` | `0x00001011` | Screen support module/device driver absent. |
| `DIVE_ERR_BUFFER_ALREADY_ACCESSED` | `0x00001012` | Begin-access called twice. |
| `DIVE_ERR_BUFFER_NOT_ACCESSED` | `0x00001013` | End-access without begin. |
| `DIVE_ERR_TOO_MANY_BUFFERS` | `0x00001014` | Buffer index space exhausted. |
| `DIVE_ERR_ALLOCATION_ERROR` | `0x00001015` | Allocation failed. |
| `DIVE_ERR_INVALID_LINESIZE` | `0x00001016` | Bad scan-line size. |
| `DIVE_ERR_FATAL_EXCEPTION` | `0x00001017` | Fatal exception. |
| `DIVE_ERR_INVALID_CONVERSION` | `0x00001018` | Unsupported format conversion. |
| `DIVE_ERR_VSD_ERROR` | `0x00001019` | Video-support-driver error. |
| `DIVE_ERR_COLOR_SUPPORT` | `0x0000101a` | Color support error. |
| `DIVE_ERR_OUT_OF_RANGE` | `0x0000101b` | Value out of range. |
| `DIVE_WARN_NO_SIZE` | `0x00001100` | Warning: no size. |

The one-line meanings above are derived from the constant names; the header gives the values but
no per-code prose. Where a name is ambiguous (e.g. `DIVE_ERR_SSMDD_NOT_INSTALLED`,
`DIVE_ERR_VSD_ERROR`, `DIVE_WARN_NO_SIZE`) the precise trigger is **[unverified]**. [DOC-IBM,
dive.h:24-53]

---

## 11. Constants summary

| Constant | Value | Source |
|---|---|---|
| `MAX_DIVE_INSTANCES` | `64` | dive.h:19 |
| `FOURCC` / `HDIVE` typedefs | `ULONG` | dive.h:21-22 |
| `DIVE_BUFFER_SCREEN` | `0x00000000` | dive.h:55 |
| `DIVE_BUFFER_GRAPHICS_PLANE` | `0x00000001` | dive.h:56 |
| `DIVE_BUFFER_ALTERNATE_PLANE` | `0x00000002` | dive.h:57 |
| `DIVE_FULLY_VISIBLE` | `0xffffffff` | dive.h:59 |
| First allocated buffer number | `0x00000010` | dive.h:63 |
| `DIVE_PALETTE_PHYSICAL` | `(PBYTE)0x00000000` | dive.h:276 |
| `DIVE_PALETTE_DEFAULT` | `(PBYTE)0xffffffff` | dive.h:277 |
| `DIVE_TBM_*` | `0x0`-`0x05` | dive.h:297-319 |

## See also
- `mmpm2-multimedia.md` - the surrounding MMOS2 MCI/MMIO subsystem and the `FOURCC`/`mmioFOURCC` codes DIVE shares.
