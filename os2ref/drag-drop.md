# OS/2 Presentation Manager - Direct Manipulation (Drag and Drop)

**Direct manipulation** is the Presentation Manager protocol by which a user picks up one or
more objects with the pointing device, drags them across the screen, and drops them on another
window to perform an operation (copy, move, link, print, ...). It is a *distributed* protocol
between two window procedures - a **source** window that starts the drag and describes the
objects, and a **target** window under the pointer that decides whether it will accept them -
who agree, at drop time, on a **rendering mechanism and format (RMF)** and then hold a
message-driven **conversation** to actually transfer the data. This reference documents the
structures the two sides exchange (`DRAGINFO`, `DRAGITEM`, `DRAGIMAGE`, `DRAGTRANSFER`), the
RMF/type string convention, the `Drg*` API, the `DM_*` message flow with its `DOR_*`/`DO_*`
responses, and the target-emphasis and post-drop conversation model.

Provenance: **[DOC-IBM]** the OS/2 Toolkit header `pmstddlg.h` (the drag-and-drop declarations
live in its `INCL_WINSTDDRAG` section - every prototype, structure, constant *value*, and
message id below is transcribed from it), the base type header `os2def.h`, and the error header
`pmerr.h`; **[DOC-IBM]** the IBM OS/2 Presentation Manager Programming Guide and Reference (the
extracted book text `pm1.txt`/`pm3.txt`/`pm4.txt`) for API and message *semantics*. Where a
behavioural claim is stated only by the book it is cited to that book; where a value is stated
only by the header it is cited `file:line`. Facts a source did not establish are marked
`[unverified]`.

---

## 1. The two roles and the object model [DOC-IBM]

A direct-manipulation operation always has a **source** and, once the pointer is over an
acceptable window, a **target**:

- The **source** starts the drag. It allocates and fills a `DRAGINFO` describing the **drag
  set** - one `DRAGITEM` per object being dragged - plus one or more `DRAGIMAGE` structures
  describing the visual feedback, then calls `DrgDrag`. For each object the source makes known:
  its **type**, the **rendering mechanisms and formats** it can supply, a suggested target
  name, the source container name, and the source object name. [DOC-IBM - pm4.txt, "Responsibilities
  of a Source Application"]
- The **target** is the window directly under the pointer hot spot. It decides whether the drag
  set can be dropped (by inspecting each `DRAGITEM`'s type and RMF), provides **target emphasis**
  (visible feedback), defines the default operation, and - after the drop - initiates the
  conversation that transfers the data. A drop can succeed only if source and target share at
  least one rendering mechanism *and* format. [DOC-IBM - pm4.txt, "Responsibilities of a Target
  Application"]

The whole facility is enabled by `#define INCL_WINSTDDRAG` before including the PM headers
[DOC-IBM - pm1.txt, function synopses]. Two general error codes bound the facility:
`PMERR_NOT_DRAGGING` (`0x1f00`) and `PMERR_ALREADY_DRAGGING` (`0x1f01`) [DOC-IBM
`pmstddlg.h:634-635`]. `MSGF_DRAG` (`0x0010`) is the message-filter identifier for the drag
message loop [DOC-IBM `pmstddlg.h:637`].

---

## 2. The core structures [DOC-IBM]

### `DRAGINFO` - the drag set [DOC-IBM `pmstddlg.h:763-774`]

Allocated by the source (with `DrgAllocDraginfo`), passed to the target in every drag message,
and freed at the end of the operation. It is a header followed by `cditem` `DRAGITEM` records.

```c
typedef struct _DRAGINFO {   /* dinfo */
    ULONG    cbDraginfo;     /* size of DRAGINFO plus all its DRAGITEMs */
    USHORT   cbDragitem;     /* size of one DRAGITEM                    */
    USHORT   usOperation;    /* current drag operation (DO_*)           */
    HWND     hwndSource;     /* window handle of the drag source        */
    SHORT    xDrop;          /* x of drop position (desktop coords)     */
    SHORT    yDrop;          /* y of drop position (desktop coords)     */
    USHORT   cditem;         /* count of DRAGITEMs in the drag set      */
    USHORT   usReserved;
} DRAGINFO;
typedef DRAGINFO *PDRAGINFO;
```

`usOperation` carries the operation the user is currently requesting (modified by the
augmentation keys); the source may seed a default into it before `DrgDrag`, and thereafter it is
the value delivered to the target unless the pointer's default resolves it differently
(Section 5). [DOC-IBM - pm1.txt, `DrgAllocDraginfo`/`DrgDrag` Remarks]

### `DRAGITEM` - one dragged object [DOC-IBM `pmstddlg.h:745-761`]

```c
typedef struct _DRAGITEM {   /* ditem */
    HWND    hwndItem;          /* conversation partner (the source's window) */
    ULONG   ulItemID;          /* source-defined id of this item             */
    HSTR    hstrType;          /* type string handle (see Section 3)         */
    HSTR    hstrRMF;           /* rendering mechanism+format handle (Sec. 3)  */
    HSTR    hstrContainerName; /* name of the source container/folder        */
    HSTR    hstrSourceName;    /* name of the item at the source             */
    HSTR    hstrTargetName;    /* suggested name of the item at the target    */
    SHORT   cxOffset;          /* x offset of image origin from pointer hotspot */
    SHORT   cyOffset;          /* y offset of image origin from pointer hotspot */
    USHORT  fsControl;         /* source item control flags (DC_*)           */
    USHORT  fsSupportedOps;    /* operations the source supports (DO_*ABLE)   */
} DRAGITEM;
typedef DRAGITEM *PDRAGITEM;
```

`hwndItem` is the window the target addresses its `DM_RENDER`/conversation messages to.
`cxOffset`/`cyOffset` are copied from the `DRAGIMAGE` by `DrgDrag` and let the target place the
dropped object relative to the drop point, preserving the objects' relative layout. [DOC-IBM -
pm4.txt, `DRAGITEM` field descriptions]

**`fsControl`** - source item control flags [DOC-IBM `pmstddlg.h:691-696`]:

| Flag | Value | Meaning |
|---|---|---|
| `DC_OPEN` | `0x0001` | The source object is open. |
| `DC_REF` | `0x0002` | The item is a reference/shadow, not the object itself. |
| `DC_GROUP` | `0x0004` | The item is a group. |
| `DC_CONTAINER` | `0x0008` | The item is a container. |
| `DC_PREPARE` | `0x0010` | Target should send `DM_RENDERPREPARE` before `DM_RENDER`. |
| `DC_REMOVEABLEMEDIA` | `0x0020` | The source resides on removable media. |

**`fsSupportedOps`** - operations the source can perform for this item [DOC-IBM `pmstddlg.h:685-689`]:

| Flag | Value | Meaning |
|---|---|---|
| `DO_COPYABLE` | `0x0001` | Item can be copied. |
| `DO_MOVEABLE` | `0x0002` | Item can be moved. |
| `DO_LINKABLE` | `0x0004` | Item can be linked. |
| `DO_CREATEABLE` | `0x0008` | Item can be created (from a template). |
| `DO_CREATEPROGRAMOBJECTABLE` | `0x0010` | Item can create a program object. |

### `DRAGIMAGE` - drag-time visual feedback [DOC-IBM `pmstddlg.h:776-788`]

An array of these (one per object, or one shared image) is passed to `DrgDrag`; it defines what
is dragged under the pointer.

```c
typedef struct _DRAGIMAGE {   /* dimg */
    USHORT  cb;            /* size of this control block                */
    USHORT  cptl;          /* count of points, if fl has DRG_POLYGON    */
    LHANDLE hImage;        /* icon/bitmap/polygon handle (per fl)       */
    SIZEL   sizlStretch;   /* size to stretch the icon/bitmap to        */
    ULONG   fl;            /* DRG_* image flags                         */
    SHORT   cxOffset;      /* x offset of image origin from pointer hotspot */
    SHORT   cyOffset;      /* y offset of image origin from pointer hotspot */
} DRAGIMAGE;
typedef DRAGIMAGE *PDRAGIMAGE;
```

**`fl`** - drag-image flags [DOC-IBM `pmstddlg.h:717-723`]:

| Flag | Value | Meaning |
|---|---|---|
| `DRG_ICON` | `0x00000001` | `hImage` is an icon (`HPOINTER`). |
| `DRG_BITMAP` | `0x00000002` | `hImage` is a bitmap (`HBITMAP`). |
| `DRG_POLYGON` | `0x00000004` | `hImage` is a polygon of `cptl` points. |
| `DRG_STRETCH` | `0x00000008` | Stretch the icon/bitmap to `sizlStretch`. |
| `DRG_TRANSPARENT` | `0x00000010` | Draw transparently. |
| `DRG_CLOSED` | `0x00000020` | Polygon is closed. |
| `DRG_MINIBITMAP` | `0x00000040` | Use the mini (small) bitmap. |

### `DRAGTRANSFER` - one rendering conversation [DOC-IBM `pmstddlg.h:790-801`]

Allocated by the target (with `DrgAllocDragtransfer`), one per object it wants rendered; carried
in the `DM_RENDER` conversation.

```c
typedef struct _DRAGTRANSFER {   /* dxfer */
    ULONG      cb;               /* size of this control block           */
    HWND       hwndClient;       /* the target window                    */
    PDRAGITEM  pditem;           /* the DRAGITEM being transferred        */
    HSTR       hstrSelectedRMF;  /* the RMF the target chose for this xfer */
    HSTR       hstrRenderToName; /* the name the source should render to   */
    ULONG      ulTargetInfo;     /* reserved for the target's own use     */
    USHORT     usOperation;      /* operation being performed (DO_*)      */
    USHORT     fsReply;          /* reply flags (DMFL_*), set by source    */
} DRAGTRANSFER;
typedef DRAGTRANSFER *PDRAGTRANSFER;
```

`hstrSelectedRMF` is the single mechanism/format pair (chosen from the source's `hstrRMF` set)
that both sides will use for this transfer; the target owns and deletes this handle when the
conversation ends. `fsReply` is cleared by `DrgSendTransferMsg` before a `DM_RENDER` is sent and
filled by the source on a `FALSE` return (Section 4/6). [DOC-IBM - pm4.txt, `DRAGTRANSFER` field
descriptions; pm1.txt, `DrgSendTransferMsg` Remarks]

### `RENDERFILE` - the file-drag helper conversation [DOC-IBM `pmstddlg.h:803-811`]

Used by the `DrgDragFiles`/`DM_RENDERFILE` file-move/copy helper protocol.

```c
typedef struct _RENDERFILE {   /* rndf */
    HWND   hwndDragFiles;   /* the conversation window                    */
    HSTR   hstrSource;      /* handle to the source file name             */
    HSTR   hstrTarget;      /* handle to the target file name             */
    USHORT fMove;           /* TRUE = move, FALSE = copy                  */
    USHORT usRsvd;
} RENDERFILE;
typedef RENDERFILE *PRENDERFILE;
```

### String handles

Every string in the structures above is an **`HSTR`** - a handle, not a pointer:
`typedef LHANDLE HSTR;` [DOC-IBM `pmstddlg.h:743`] (`LHANDLE` is `unsigned long`, `os2def.h`).
An `HSTR` is created from a C string with `DrgAddStrHandle` and read back with `DrgQueryStrName`
(Section 4). Handles, rather than pointers, are used because a `DRAGINFO` crosses a process
boundary between two unrelated applications, so the strings must be referenceable by any process
[DOC-IBM - pm1.txt, `DrgAddStrHandle` Remarks].

---

## 3. Type and rendering-mechanism-and-format (RMF) strings [DOC-IBM]

Two of the `DRAGITEM` `HSTR`s carry structured strings that are the heart of the negotiation.

### The type string (`hstrType`)

A comma-separated list `type[,type...]`; **the first entry is the object's true type**. The
following standard type names are used by the OS/2 shell and are `#define`d as their literal
strings [DOC-IBM `pmstddlg.h:661-678`; pm4.txt type list]:

| Constant | String | Constant | String |
|---|---|---|---|
| `DRT_ASM` | `"Assembler Code"` | `DRT_LIB` | `"Library"` |
| `DRT_BASIC` | `"BASIC Code"` | `DRT_METAFILE` | `"Metafile"` |
| `DRT_BINDATA` | `"Binary Data"` | `DRT_OS2CMD` | `"OS/2 Command File"` |
| `DRT_BITMAP` | `"Bitmap"` | `DRT_PASCAL` | `"Pascal Code"` |
| `DRT_C` | `"C Code"` | `DRT_RESOURCE` | `"Resource File"` |
| `DRT_COBOL` | `"COBOL Code"` | `DRT_TEXT` | `"Plain Text"` |
| `DRT_DLL` | `"Dynamic Link Library"` | `DRT_UNKNOWN` | `"Unknown"` |
| `DRT_DOSCMD` | `"DOS Command File"` | `DRT_EXE` | `"Executable"` |
| `DRT_FORTRAN` | `"FORTRAN Code"` | `DRT_ICON` | `"Icon"` |

(The book's type table also lists `DRT_FONT` "Font"; the header's `INCL_WINSTDDRAG` block does
not `#define` `DRT_FONT` [DOC-IBM - pm4.txt vs `pmstddlg.h:661-678`].)

### The RMF string (`hstrRMF`)

The **rendering mechanism** is *how* the data is exchanged (e.g. via an OS/2 file, or DDE); the
**rendering format** is *what* the data is - its true type (e.g. text) [DOC-IBM - pm4.txt,
"Rendering Mechanisms and Formats"]. `hstrRMF` is a list `mechfmt[,mechfmt...]` where each
`mechfmt` is either an explicit ordered pair or a cross product:

```
<mechanism,format>
(mechanism1[,mechanismN...]) x (format1[,formatN...])
```

The cross-product form expands to every mechanism paired with every format. **The first
mechanism/format pair (or the first pair produced by a cross product) must be the object's
*native* RMF** - the mechanism/format that most completely conveys the data [DOC-IBM -
pm4.txt, `hstrRMF` description; pm1.txt, `DrgQueryNativeRMF` Remarks]. An application supports
some, all, or none of the standard mechanisms and may define its own private ones; supporting the
standard set widens the range of applications it can exchange with [DOC-IBM - pm4.txt,
"Non-Standard Rendering Mechanisms"].

Standard **mechanism** names (string literals) [DOC-IBM - pm4.txt, "Valid mechanisms"]:

| Name | Meaning |
|---|---|
| `DRM_DDE` | Dynamic Data Exchange (an ongoing, live conversation). |
| `DRM_OBJECT` | The item is a Workplace Shell object. |
| `DRM_OS2FILE` | Exchange as an OS/2 file (a snapshot of the data). |
| `DRM_PRINT` | Object can be printed by direct manipulation. |

Standard **format** names (string literals) [DOC-IBM - pm4.txt, "Valid formats"]:

| Name | Meaning | Name | Meaning |
|---|---|---|---|
| `DRF_BITMAP` | OS/2 bitmap | `DRF_PTRPICT` | Printer picture |
| `DRF_DIB` | Device-independent bitmap | `DRF_RTF` | Rich text |
| `DRF_DIF` | DIF | `DRF_SYLK` | SYLK |
| `DRF_DSPBITMAP` | Stream of bitmap bits | `DRF_TEXT` | Null-terminated string |
| `DRF_METAFILE` | Metafile | `DRF_TIFF` | TIFF |
| `DRF_OEMTEXT` | OEM text | `DRF_UNKNOWN` | Unknown format |
| `DRF_OWNERDISPLAY` | Bit stream | | |

A typical file drag advertises the single pair `<DRM_OS2FILE,DRF_UNKNOWN>`; a Workplace object
advertises `<DRM_OBJECT,DRF_OBJECT>` [DOC-IBM - Toolkit samples `dragdrag.c`,
`wsfolder.c`]. Unlike the `DRT_*`/`DRG_*`/`DM_*` families, the `DRM_*` and `DRF_*` names are
**not `#define`d in `pmstddlg.h`**: they are string literals an application writes directly (or
concatenates) into an RMF string [DOC-IBM - observed absent from `pmstddlg.h`; used as literals
in the Toolkit samples].

---

## 4. The API [DOC-IBM]

All entry points are `APIENTRY`-linked. Prototypes are transcribed from
`pmstddlg.h:814-1032`; semantics from `pm1.txt`.

### Source-side setup and the drag

| Symbol | Prototype | Purpose |
|---|---|---|
| `DrgAllocDraginfo` | `PDRAGINFO APIENTRY DrgAllocDraginfo(ULONG cditem)` | Allocate a `DRAGINFO` with room for `cditem` `DRAGITEM`s (in shareable memory). Must be called before `DrgDrag`. Returns `NULL` on failure. |
| `DrgSetDragitem` | `BOOL APIENTRY DrgSetDragitem(PDRAGINFO pdinfo, PDRAGITEM pditem, ULONG cbBuffer, ULONG iItem)` | Copy a filled `DRAGITEM` into slot `iItem` of the drag set. |
| `DrgSetDragImage` | `BOOL APIENTRY DrgSetDragImage(PDRAGINFO pdinfo, PDRAGIMAGE pdimg, ULONG cdimg, PVOID pRsvd)` | Set the drag image(s) recorded in the `DRAGINFO`. |
| `DrgDrag` | `HWND APIENTRY DrgDrag(HWND hwndSource, PDRAGINFO pdinfo, PDRAGIMAGE pdimg, ULONG cdimg, LONG vkTerminate, PVOID pRsvd)` | Run the (modal) drag: capture the mouse, draw `pdimg`, send `DM_DRAGOVER`/`DM_DRAGLEAVE` as the pointer crosses windows, and on drop send `DM_DROP` to the target. **Returns the target window handle** the set was dropped on (`NULLHANDLE` if not dropped / on failure). `vkTerminate` is the virtual key (`VK_*`) whose *up* transition ends the drag (typically the drag button). |

`DrgDrag` fails if it cannot capture the mouse (e.g. another window on the thread already holds
the capture). Before calling it the source must have obtained the `DRAGINFO` with
`DrgAllocDraginfo` and initialized every `DRAGITEM` with `DrgSetDragitem`. It does not return
until the drop occurs. [DOC-IBM - pm1.txt, `DrgDrag` Remarks]

### Target-side access and rendering

| Symbol | Prototype | Purpose |
|---|---|---|
| `DrgAccessDraginfo` | `BOOL APIENTRY DrgAccessDraginfo(PDRAGINFO pdinfo)` | Gain access, in the *target* process, to a `DRAGINFO` whose address arrived in a drag message. Paired with `DrgFreeDraginfo`. |
| `DrgAllocDragtransfer` | `PDRAGTRANSFER APIENTRY DrgAllocDragtransfer(ULONG cdxfer)` | Allocate `cdxfer` `DRAGTRANSFER` control blocks for the conversation. |
| `DrgSendTransferMsg` | `MRESULT APIENTRY DrgSendTransferMsg(HWND hwnd, ULONG msg, MPARAM mp1, MPARAM mp2)` | Send a conversation message (`DM_RENDER`, `DM_RENDERCOMPLETE`, ...) to the source window `hwnd`, arranging cross-process access to the `DRAGTRANSFER`. |
| `DrgPostTransferMsg` | `BOOL APIENTRY DrgPostTransferMsg(HWND hwnd, ULONG msg, PDRAGTRANSFER pdxfer, ULONG fl, ULONG ulRsvd, BOOL fRetry)` | Post (rather than send) a transfer message. |
| `DrgQueryDragitem` | `BOOL APIENTRY DrgQueryDragitem(PDRAGINFO pdinfo, ULONG cbBuffer, PDRAGITEM pditem, ULONG iItem)` | Copy item `iItem` out of the drag set into `*pditem`. |
| `DrgQueryDragitemCount` | `ULONG APIENTRY DrgQueryDragitemCount(PDRAGINFO pdinfo)` | Number of items in the drag set (`cditem`). |
| `DrgQueryDragitemPtr` | `PDRAGITEM APIENTRY DrgQueryDragitemPtr(PDRAGINFO pdinfo, ULONG i)` | A direct pointer to item `i` inside the shared `DRAGINFO`. |

On `DM_RENDER`, `DrgSendTransferMsg` clears `fsReply` first and, because the message conveys the
`DRAGTRANSFER` to another process, calls `DosGiveSeg` to grant that process access and increments
the segment use count; the receiving process must call `DrgFreeDragtransfer` before the segment
can be released. [DOC-IBM - pm1.txt, `DrgSendTransferMsg` Remarks]

### RMF / type verification and queries

| Symbol | Prototype | Purpose |
|---|---|---|
| `DrgVerifyRMF` | `BOOL APIENTRY DrgVerifyRMF(PDRAGITEM pditem, PSZ pszMech, PSZ pszFmt)` | `TRUE` if the mechanism/format pair (`pszMech`,`pszFmt`) is present in the item's `hstrRMF` set. A `NULL` mechanism or format matches any. The core target-acceptance test. |
| `DrgVerifyNativeRMF` | `BOOL APIENTRY DrgVerifyNativeRMF(PDRAGITEM pditem, PSZ pszRMF)` | `TRUE` if `pszRMF` matches the item's native RMF. |
| `DrgQueryNativeRMF` | `BOOL APIENTRY DrgQueryNativeRMF(PDRAGITEM pditem, ULONG cbBuffer, PCHAR pBuffer)` | Return the item's native (first) RMF pair as a `<mech,fmt>` string. |
| `DrgQueryNativeRMFLen` | `ULONG APIENTRY DrgQueryNativeRMFLen(PDRAGITEM pditem)` | Buffer length needed for the above. |
| `DrgVerifyType` / `DrgVerifyTypeSet` | `BOOL APIENTRY DrgVerifyType(PDRAGITEM, PSZ)` / `DrgVerifyTypeSet(PDRAGITEM, PSZ, ULONG, PSZ)` | Test the item's type list against a type / return the matching type. |
| `DrgQueryTrueType` / `DrgQueryTrueTypeLen` | `BOOL APIENTRY DrgQueryTrueType(PDRAGITEM, ULONG, PSZ)` / `ULONG DrgQueryTrueTypeLen(PDRAGITEM)` | The item's true type (first type in the list) / its length. |
| `DrgVerifyTrueType` | `BOOL APIENTRY DrgVerifyTrueType(PDRAGITEM pditem, PSZ pszType)` | `TRUE` if the item's true type is `pszType`. |
| `DrgQueryFormat` | `ULONG APIENTRY DrgQueryFormat(PDRAGITEM, PSZ pszAppMech, ULONG, PSZ, ULONG ulFMTIndex)` | Enumerate the formats the source offers for a given mechanism. |

### String handles

| Symbol | Prototype | Purpose |
|---|---|---|
| `DrgAddStrHandle` | `HSTR APIENTRY DrgAddStrHandle(PSZ psz)` | Create an `HSTR` for a string; the handle is referenceable by any process. The source must use it for every string placed in a `DRAGINFO`. |
| `DrgQueryStrName` | `ULONG APIENTRY DrgQueryStrName(HSTR hstr, ULONG cbBuffer, PSZ pBuffer)` | Copy the string named by `hstr` into `pBuffer`; returns the length copied. |
| `DrgQueryStrNameLen` | `ULONG APIENTRY DrgQueryStrNameLen(HSTR hstr)` | Length of that string (for buffer sizing). |
| `DrgDeleteStrHandle` | `BOOL APIENTRY DrgDeleteStrHandle(HSTR hstr)` | Release one string handle. |
| `DrgDeleteDraginfoStrHandles` | `BOOL APIENTRY DrgDeleteDraginfoStrHandles(PDRAGINFO pdinfo)` | Release every string handle referenced by a `DRAGINFO`. |

### Lifetime, presentation space, and the file helper

| Symbol | Prototype | Purpose |
|---|---|---|
| `DrgFreeDraginfo` | `BOOL APIENTRY DrgFreeDraginfo(PDRAGINFO pdinfo)` | Free a `DRAGINFO`. Fails with `PMERR_SOURCE_SAME_AS_TARGET` (`0x1502`) if the process that called `DrgDrag` calls it before `DrgDrag` returns - this stops the source freeing the block while its own target window is still using it. |
| `DrgFreeDragtransfer` | `BOOL APIENTRY DrgFreeDragtransfer(PDRAGTRANSFER pdxfer)` | Free a `DRAGTRANSFER`. |
| `DrgGetPS` / `DrgReleasePS` | `HPS APIENTRY DrgGetPS(HWND hwnd)` / `BOOL DrgReleasePS(HPS hps)` | Obtain / release a presentation space over a window *unlocked* for drawing target emphasis while a drag is in progress. |
| `DrgSetDragPointer` | `BOOL APIENTRY DrgSetDragPointer(PDRAGINFO pdinfo, HPOINTER hptr)` | Change the drag pointer/image while the object is over a target. |
| `DrgPushDraginfo` | `BOOL APIENTRY DrgPushDraginfo(PDRAGINFO pdinfo, HWND hwndDest)` | Grant a specific window access to the `DRAGINFO`. |
| `DrgAcceptDroppedFiles` | `BOOL APIENTRY DrgAcceptDroppedFiles(HWND hwnd, PSZ pszPath, PSZ pszTypes, ULONG ulDefaultOp, ULONG ulRsvd)` | Turn a window into a ready-made file-drop target: it auto-answers `DM_DRAGOVER` with `DOR_DROP` for items whose type matches `pszTypes` and whose RMF is `<DRM_OS2FILE,DRF_UNKNOWN>`, then runs the whole post-drop file conversation, sending the caller `DM_DRAGFILECOMPLETE` per file and `DM_DRAGERROR` on failure. |
| `DrgDragFiles` | `BOOL APIENTRY DrgDragFiles(HWND hwnd, PSZ *apszFiles, PSZ *apszTypes, PSZ *apszTargets, ULONG cFiles, HPOINTER hptrDrag, ULONG vkTerm, BOOL fSourceRender, ULONG ulRsvd)` | Source-side counterpart: drag a list of files; an internally created object window handles the conversation, sending `DM_RENDERFILE`/`DM_FILERENDERED` to render each file. |

### Lazy (pickup-and-drop) drag [DOC-IBM `pmstddlg.h:997-1018`]

A non-modal alternative: the user picks objects up, and drops them later. `DrgLazyDrag` starts
it, `DrgCancelLazyDrag` aborts it, `DrgLazyDrop` performs the drop, and `DrgQueryDragStatus`
returns the current status (`DGS_DRAGINPROGRESS` `0x0001`, `DGS_LAZYDRAGINPROGRESS` `0x0002`
[DOC-IBM `pmstddlg.h:707-708`]). Because it is non-modal, the drop is reported to the source by a
posted `DM_DROPNOTIFY` rather than by a `DrgDrag` return value; `DM_DROPHELP` is not supported for
lazy drag. [DOC-IBM - pm3.txt, `DM_DROP`/`DM_DROPNOTIFY`/`DM_DROPHELP` Remarks]

---

## 5. The message flow [DOC-IBM]

Drag-and-drop messages occupy the range `WM_DRAGFIRST` (`0x0310`) ... `WM_DRAGLAST` (`0x032f`)
[DOC-IBM `pmstddlg.h:639-640`]. Message ids [DOC-IBM `pmstddlg.h:642-659`]:

| Message | Value | Direction | Delivered when / carries |
|---|---|---|---|
| `DM_DRAGOVER` | `0x032e` | -> target | Pointer is over the window; `mp1` = `PDRAGINFO`, `mp2` = drop point (`sxDrop`,`syDrop` as two `SHORT`s, desktop coords). Target *returns* `MRFROM2SHORT(usDrop, usDefaultOp)`. |
| `DM_DRAGLEAVE` | `0x032d` | -> target | Pointer left a window it had been dragged over; `mp1` = `PDRAGINFO`. Remove target emphasis. Not sent on a drop. |
| `DM_DRAGOVERNOTIFY` | `0x0321` | -> source | Sent to the source immediately after each `DM_DRAGOVER`; `mp2` = the target's (`usDrop`,`usDefaultOp`) reply, so the source can adapt its feedback. |
| `DM_DROP` | `0x032f` | -> target | The set was dropped (only if the target had answered `DOR_DROP`); `mp1` = `PDRAGINFO`. Target must remove emphasis and start the conversation. |
| `DM_DROPNOTIFY` | `0x031e` | -> source | Posted to the source after a drop; `mp1` = `PDRAGINFO`, `mp2` = `hwndTarget` (0 => drag cancelled). Tells the source whether it or the target must free the `DRAGINFO`. |
| `DM_DROPHELP` | `0x032c` | -> target | F1 pressed during the drag; the drag is cancelled and help is requested. `mp1` = `PDRAGINFO`. |
| `DM_RENDER` | `0x0329` | target -> source | Target requests the source render an object; `mp1` = `PDRAGTRANSFER`. Source returns `TRUE` (will render) or `FALSE` (see `fsReply`). |
| `DM_RENDERCOMPLETE` | `0x0328` | source -> target | Source posts this when rendering finished; `mp1` = `PDRAGTRANSFER` (same pointer), `mp2` = `usFS` (`DMFL_RENDEROK`/`DMFL_RENDERFAIL`/`DMFL_RENDERRETRY`). |
| `DM_RENDERPREPARE` | `0x0327` | target -> source | Sent before `DM_RENDER` when the item has `DC_PREPARE`; `mp1` = `PDRAGTRANSFER`. |
| `DM_ENDCONVERSATION` | `0x032b` | target -> source | Target ends the conversation for one item; `mp1` = `ulItemID`, `mp2` = `ulFlags` (`DMFL_TARGETSUCCESSFUL`/`DMFL_TARGETFAIL`). Lets the source release its resources. |
| `DM_EMPHASIZETARGET` | `0x0325` | -> target | Request to apply/remove target emphasis; `mp1` = (`sx`,`sy`) window coords, `mp2` low = `usEmphasis` (TRUE apply / FALSE remove). |
| `DM_RENDERFILE` | `0x0322` | -> `DrgDragFiles` caller | Render one file; `mp1` = `PRENDERFILE`. Return `TRUE` (handled) or `FALSE` (let `DrgDragFiles` do it). |
| `DM_FILERENDERED` | `0x0323` | -> `hwndDragFiles` | A file's render completed. |
| `DM_DRAGFILECOMPLETE` | `0x0326` | -> `DrgAcceptDroppedFiles` caller | One file's move/copy completed; `mp2` low = flags (`DF_MOVE 0x0001`, `DF_SOURCE 0x0002`, `DF_SUCCESSFUL 0x0004` [DOC-IBM `pmstddlg.h:730-732`]). |
| `DM_DRAGERROR` | `0x0324` | -> caller | Error during a file move/copy; the caller returns `DME_IGNOREABORT`(1)/`DME_IGNORECONTINUE`(2)/`DME_REPLACE`(3)/`DME_RETRY`(4) [DOC-IBM `pmstddlg.h:725-728`]. |
| `DM_PRINT` / `DM_PRINTOBJECT` | `0x032a` / `0x0320` | -> target | Print-mechanism drop. |
| `DM_DISCARDOBJECT` | `0x031f` | -> target | Object dropped on a shredder/discard target. |

### `DM_DRAGOVER` responses [DOC-IBM `pmstddlg.h:680-683`; pm3.txt]

The target's `MRESULT` packs a **drop indicator** (`usDrop`) and, when it accepts, a **default
operation** (`usDefaultOp`):

| `usDrop` | Value | Meaning |
|---|---|---|
| `DOR_NODROP` | `0x0000` | Not droppable *right now*; the target could accept this type/format/op but its current state forbids it - state may change, so `DM_DRAGOVER` keeps coming. |
| `DOR_DROP` | `0x0001` | Droppable. `usDefaultOp` must be set to the operation a drop would perform here. |
| `DOR_NODROPOP` | `0x0002` | Type/format acceptable but the *operation* is not; a different operation might be accepted - no further `DM_DRAGOVER` until the drag state changes. |
| `DOR_NEVERDROP` | `0x0003` | Never acceptable; no further `DM_DRAGOVER` until the pointer leaves and re-enters the window. This is what `WinDefWindowProc` returns. |

The **operation** (`usDefaultOp`, and `DRAGINFO.usOperation`) values [DOC-IBM `pmstddlg.h:698-704`]:

| Constant | Value | Meaning |
|---|---|---|
| `DO_COPY` | `0x0010` | Copy. |
| `DO_LINK` | `0x0018` | Link. |
| `DO_MOVE` | `0x0020` | Move. |
| `DO_CREATE` | `0x0040` | Create (from a template). |
| `DO_CREATEPROGRAMOBJECT` | `0x0080` | Create a program object. |
| `DO_DEFAULT` | `0xBFFE` | Use the target-defined default (target fills `usDefaultOp`). |
| `DO_UNKNOWN` | `0xBFFF` | Operation not known. Application-defined operations use values `>= DO_UNKNOWN`. |

The book additionally documents `DO_NEW` ("create another"), to be treated as `DO_UNKNOWN+3`
where the toolkit level does not recognize it; it is not `#define`d in this header
[DOC-IBM - pm3.txt, `DM_DRAGOVER` `usDefaultOp`; absent from `pmstddlg.h`]. When
`DRAGINFO.usOperation` is `DO_DEFAULT` or `DO_UNKNOWN` and the target returns `DOR_DROP`, the
`usDefaultOp` it supplies becomes the `usOperation` delivered in the subsequent `DM_DROP`;
otherwise `usDefaultOp` is ignored. [DOC-IBM - pm3.txt, `DM_DRAGOVER` Remarks]

### When `DM_DRAGOVER` is sent [DOC-IBM - pm3.txt, `DM_DRAGOVER` Remarks]

`DM_DRAGOVER` is sent to the window under the pointer hot spot each time the mouse moves, each
time a key is pressed or released, and on the terminating button-up (only if the mouse moved
since the last one). To accept, the target must be able to accept **all** items in the drag set;
it inspects each via `DrgAccessDraginfo` + `DrgQueryDragitem`/`DrgVerifyRMF`. The target draws
its own emphasis and may call `DrgSetDragPointer`; a later `DM_DRAGLEAVE` or `DM_DROP` is its cue
to remove it.

---

## 6. The post-drop conversation and rendering [DOC-IBM]

The drop does **not** transfer data. On `DM_DROP` the target must first remove target emphasis
and *post a private message to itself* to start the transfer - data must not be moved while
still inside the `DM_DROP` handler. [DOC-IBM - pm3.txt, `DM_DROP` Remarks] The conversation then
proceeds per object:

1. The target picks an RMF pair supported by both sides (`DrgVerifyRMF`), records it in a
   `DRAGTRANSFER` (`hstrSelectedRMF`, `hstrRenderToName`), and sends **`DM_RENDER`** to the
   source (`DrgSendTransferMsg`). If the item's `fsControl` has `DC_PREPARE`, a
   `DM_RENDERPREPARE` precedes it.
2. The **source** returns `TRUE` to accept the render (it will do the work and post
   `DM_RENDERCOMPLETE` when done), or `FALSE`. On `FALSE` it sets `DRAGTRANSFER.fsReply` to tell
   the target what to do next [DOC-IBM `pmstddlg.h:710-715`]:

   | `fsReply` flag | Value | Meaning |
   |---|---|---|
   | `DMFL_NATIVERENDER` | `0x0004` | Source will not render itself, but the target may render on its own using the source's data. |
   | `DMFL_RENDERRETRY` | `0x0008` | Target may retry with a different RMF (`DM_RENDER` again). |

   If no flag is set, the source refuses to render the object.
3. When the source finishes it posts **`DM_RENDERCOMPLETE`** with `usFS` = `DMFL_RENDEROK`
   (success), `DMFL_RENDERFAIL` (failed - target may retry), and/or `DMFL_RENDERRETRY` (source
   will allow a retry). After success or failure the source returns to its pre-drop state so a
   retry is possible.
4. The **target** ends each object's conversation with **`DM_ENDCONVERSATION`**
   (`ulFlags` = `DMFL_TARGETSUCCESSFUL` or `DMFL_TARGETFAIL`), which releases the source's
   dedicated resources. The target must send it when it will not retry a failed render, when it
   completes the render without the source, when it aborts, or when it declines a dropped object.
5. Ownership of the `DRAGINFO`: from `DM_DROPNOTIFY`/the `DrgDrag` return the source learns
   `hwndTarget`. If source and target are **different processes**, the source frees the
   `DRAGINFO` (its target has finished with it); if source and target are the **same**, the
   target frees it after the conversation completes. `DrgFreeDraginfo` from the drag-initiating
   process before `DrgDrag` returns fails with `PMERR_SOURCE_SAME_AS_TARGET`. [DOC-IBM - pm3.txt
   `DM_DROP`/`DM_DROPNOTIFY` Remarks; pm1.txt `DrgFreeDraginfo` Remarks]

`WinDefWindowProc` default handling matters here: for `DM_DROP` and `DM_DROPHELP` it calls
`DrgDeleteDraginfoStrHandles` + `DrgFreeDraginfo` and returns 0; for `DM_DRAGOVER` it returns
`DOR_NEVERDROP`; for `DM_RENDERCOMPLETE` it sends a failing `DM_ENDCONVERSATION` back to
`hwndItem` so the source can release resources. A window that means to participate in drag-and-
drop must therefore handle these messages itself rather than defer to the default. [DOC-IBM -
pm3.txt, per-message "Default Processing"]

---

## 7. Target emphasis [DOC-IBM]

**Target emphasis** is the visual feedback a target draws to show a drop is possible and where it
would land. Because the source holds the mouse capture and the window is otherwise locked during a
drag, a target draws emphasis on a presentation space obtained from **`DrgGetPS`** (and released
with **`DrgReleasePS`**), which unlocks the window for this drawing; it must not use an ordinary
`WinGetPS` [DOC-IBM - pm1.txt, `DrgGetPS`; pm4.txt "In order to draw target emphasis, an
application must use DrgGetPS and DrgReleasePS to unlock its window"]. Emphasis is applied on
`DM_DRAGOVER`/`DM_EMPHASIZETARGET` and removed on `DM_DRAGLEAVE` or `DM_DROP`.

The container control (`WC_CONTAINER`) implements richer emphasis automatically and forwards drag
activity to its owner as `WM_CONTROL` notifications - `CN_DRAGOVER` (103), `CN_DRAGAFTER` (101),
`CN_DRAGLEAVE` (102), `CN_DROP`, `CN_DROPHELP` - carrying a `CNRDRAGINFO`; whether it draws
record-surrounding, ordered (a line between items), or mixed emphasis depends on the
`CA_ORDEREDTARGETEMPH` / `CA_MIXEDTARGETEMPH` container attributes and the current view. [DOC-IBM
`pmstddlg.h:1379-1381, 1489-1493`; pm3.txt/pm4.txt container sections] The container drag surface
is documented in the container control reference.

---

## 8. Constant summary [DOC-IBM]

All values from `pmstddlg.h` unless noted.

| Family | Constants (value) |
|---|---|
| Message range | `WM_DRAGFIRST 0x0310`, `WM_DRAGLAST 0x032f` |
| Messages | `DM_DISCARDOBJECT 0x031f`, `DM_DROPNOTIFY 0x031e`, `DM_PRINTOBJECT 0x0320`, `DM_DRAGOVERNOTIFY 0x0321`, `DM_RENDERFILE 0x0322`, `DM_FILERENDERED 0x0323`, `DM_DRAGERROR 0x0324`, `DM_EMPHASIZETARGET 0x0325`, `DM_DRAGFILECOMPLETE 0x0326`, `DM_RENDERPREPARE 0x0327`, `DM_RENDERCOMPLETE 0x0328`, `DM_RENDER 0x0329`, `DM_PRINT 0x032a`, `DM_ENDCONVERSATION 0x032b`, `DM_DROPHELP 0x032c`, `DM_DRAGLEAVE 0x032d`, `DM_DRAGOVER 0x032e`, `DM_DROP 0x032f` (`:642-659`) |
| Drop response `DOR_*` | `DOR_NODROP 0`, `DOR_DROP 1`, `DOR_NODROPOP 2`, `DOR_NEVERDROP 3` (`:680-683`) |
| Operation `DO_*` | `DO_COPY 0x10`, `DO_LINK 0x18`, `DO_MOVE 0x20`, `DO_CREATE 0x40`, `DO_CREATEPROGRAMOBJECT 0x80`, `DO_DEFAULT 0xBFFE`, `DO_UNKNOWN 0xBFFF` (`:698-704`) |
| Supported-op `DO_*ABLE` | `DO_COPYABLE 0x01`, `DO_MOVEABLE 0x02`, `DO_LINKABLE 0x04`, `DO_CREATEABLE 0x08`, `DO_CREATEPROGRAMOBJECTABLE 0x10` (`:685-689`) |
| Control `DC_*` | `DC_OPEN 0x01`, `DC_REF 0x02`, `DC_GROUP 0x04`, `DC_CONTAINER 0x08`, `DC_PREPARE 0x10`, `DC_REMOVEABLEMEDIA 0x20` (`:691-696`) |
| Reply `DMFL_*` | `DMFL_TARGETSUCCESSFUL 0x01`, `DMFL_TARGETFAIL 0x02`, `DMFL_NATIVERENDER 0x04`, `DMFL_RENDERRETRY 0x08`, `DMFL_RENDEROK 0x10`, `DMFL_RENDERFAIL 0x20` (`:710-715`) |
| Image `DRG_*` | `DRG_ICON 0x01`, `DRG_BITMAP 0x02`, `DRG_POLYGON 0x04`, `DRG_STRETCH 0x08`, `DRG_TRANSPARENT 0x10`, `DRG_CLOSED 0x20`, `DRG_MINIBITMAP 0x40` (`:717-723`) |
| Status `DGS_*` | `DGS_DRAGINPROGRESS 0x01`, `DGS_LAZYDRAGINPROGRESS 0x02` (`:707-708`) |
| Error return `DME_*` | `DME_IGNOREABORT 1`, `DME_IGNORECONTINUE 2`, `DME_REPLACE 3`, `DME_RETRY 4` (`:725-728`) |
| File flags | `DF_MOVE 0x01`, `DF_SOURCE 0x02`, `DF_SUCCESSFUL 0x04` (`:730-732`); `DFF_MOVE 1`, `DFF_COPY 2`, `DFF_DELETE 3` (`:738-740`); `DRR_SOURCE 1`, `DRR_TARGET 2`, `DRR_ABORT 3` (`:734-736`) |
| Errors | `PMERR_NOT_DRAGGING 0x1f00`, `PMERR_ALREADY_DRAGGING 0x1f01` (`:634-635`); `PMERR_SOURCE_SAME_AS_TARGET 0x1502` (`pmerr.h:257`) |
| Filter | `MSGF_DRAG 0x0010` (`:637`) |

---

## See also
- `pm-window-messaging.md` - the window/message model these `DM_*` messages ride on; `WM_BEGINDRAG`
  (`0x0420`), the mouse message that conventionally starts a drag.
- `pm-controls.md` - the container control (`WC_CONTAINER`) and its `CN_DRAG*`/`CN_DROP`
  notifications and ordered/mixed target emphasis.
- `memory-api.md` - `DosGiveSharedMem` / `OBJ_GIVEABLE`, the giveable shared-memory object (the
  32-bit equivalent of the 16-bit `DosGiveSeg`) that a source uses to hand `DRAGTRANSFER` data to
  another process.
