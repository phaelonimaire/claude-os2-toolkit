# OS/2 MMPM/2 Multimedia API

The Multimedia Presentation Manager/2 (MMPM/2) subsystem is OS/2's device-independent
multimedia layer. An application does not talk to a sound card or a CD-ROM directly; it talks
to a **logical media device** through the **Media Control Interface (MCI)**, and it reads and
writes multimedia files through the **Multimedia I/O (MMIO)** file services. MCI has two faces
over the same engine: a binary command interface, `mciSendCommand`, that takes a numeric
message, a flag word, and a message-specific parameter block; and a textual interface,
`mciSendString`, that takes an English-like command string (`"open bell.wav alias wav1 wait"`)
which an internal parser converts into the equivalent `mciSendCommand` call. MMIO provides a
`DosOpen`-shaped file API (`mmioOpen`/`Read`/`Write`/`Seek`/`Close`) built around the RIFF
"chunk" model and a registered-`IOProc` plug-in mechanism, so that a file's storage format and
its data format are handled by installable procedures rather than by the application. Long
operations (playing, recording, seeking) run **asynchronously**: the application either blocks
with the `MCI_WAIT` flag or requests `MCI_NOTIFY` and receives a Presentation Manager message
(`MM_MCINOTIFY`) at a window when the operation finishes.

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 headers - `mcios2.h` (MCI messages, device types,
flags, all `MCI_*_PARMS` structures, `mciSendCommand`/`mciSendString`/`mciGetErrorString`
prototypes), `mmioos2.h` (MMIO prototypes, `MMIOINFO`, `MMCKINFO`, `FOURCC`, open/chunk flags,
`MMIOM_*` messages), `mciapi.h` (the `mciPlayFile` high-level convenience layer), `os2medef.h`
(`MMTIME`, `HMMIO` base types; `FOURCC` is `typedef ULONG` in `mmioos2.h:33`), `meerror.h` (`MCIERR_*` / `MMIOERR_*` codes), and the
Toolkit MM samples (`CAPTION/caption.c`, `DAUDIO/daudio.c`) for the observed notification-message
parameter layout; **[DOC]** EDM2 reference pages `mciSendCommand`, `mciSendString` for behavioural
remarks the headers do not carry.

---

## 1. The two interfaces at a glance [DOC-IBM - `mcios2.h`, `mmioos2.h`]

| Layer | Entry points | What it addresses |
|---|---|---|
| MCI (binary) | `mciSendCommand` | Logical media devices, by numeric device ID + numeric message |
| MCI (string) | `mciSendString` | Same devices, by English command string; parsed into a command internally |
| MCI helpers | `mciGetErrorString`, `mciGetDeviceID`, `mciMakeGroup`, `mciDeleteGroup`, `mciSetSysValue`, `mciQuerySysValue` | Error text, name->ID lookup, device grouping, system values |
| High-level | `mciPlayFile`, `mciPlayResource`, `mciRecordAudioFile` | One-call "just play this file" convenience (`mciapi.h`) |
| MMIO | `mmioOpen`/`Close`/`Read`/`Write`/`Seek`/`GetInfo`/`SetInfo` | Multimedia files (buffered I/O, RIFF chunks, format translation) |
| MMIO chunks | `mmioDescend`/`Ascend`/`CreateChunk`/`Advance` | Navigating and building the RIFF chunk hierarchy |
| MMIO plug-ins | `mmioInstallIOProc`, `mmioStringToFOURCC` | Registering storage/format handlers keyed by a four-character code |

MMPM/2 time is expressed in **`MMTIME`** units - `typedef ULONG MMTIME`, one unit = 1/3000
second [DOC-IBM `os2medef.h:53`]. Conversion macros (`MSECTOMM`, `MSECFROMMM`, `REDBOOKTOMM`,
`HMSTOMM`, ...) are provided in `mcios2.h` [DOC-IBM `mcios2.h:261-295`].

---

## 2. `mciSendCommand` - the binary command interface

```c
ULONG APIENTRY mciSendCommand(USHORT usDeviceID,   /* device ID from MCI_OPEN (ignored on MCI_OPEN) */
                              USHORT usMessage,    /* MCI_* command message */
                              ULONG  ulParam1,     /* flags for this message */
                              PVOID  pParam2,      /* pointer to the message's parameter block */
                              USHORT usUserParm);  /* echoed back in the notification */
```
[DOC-IBM `mcios2.h:2398`]

`usDeviceID` is the ID returned in `MCI_OPEN_PARMS.usDeviceID` from a prior `MCI_OPEN`; it is
ignored on the `MCI_OPEN` message itself, and the special value `MCI_ALL_DEVICE_ID` (`0xFFFF`)
addresses every open device [DOC-IBM `mcios2.h:108`]. `ulParam1` carries the flags that select
which fields of `pParam2` are valid - flag bits are defined **per message**, with a small set of
common flags (section 2.1) shared across all messages. `pParam2` points to the parameter block whose
type matches `usMessage` (section 4). The **return value** carries `MCIERR_SUCCESS` (0) or an error code
in its **low-order word**; if the error is device-dependent, the **high-order word holds the
device ID** [DOC - EDM2 `mciSendCommand`]. Every parameter block begins with an `HWND
hwndCallback` field used as the notification target (section 6).

### 2.1 Common message flags [DOC-IBM `mcios2.h:214-225`]

Available on all MCI messages unless a message description says otherwise. `MCI_NOTIFY` and
`MCI_WAIT` are mutually exclusive.

| Flag | Value | Meaning |
|---|---|---|
| `MCI_NOTIFY` | `0x00000001` | Return immediately; post `MM_MCINOTIFY` to `hwndCallback` on completion |
| `MCI_WAIT` | `0x00000002` | Do not return until the action completes (or errors) |
| `MCI_FROM` | `0x00000004` | The `ulFrom` field of the parameter block is valid |
| `MCI_TO` | `0x00000008` | The `ulTo` field of the parameter block is valid |
| `MCI_DOS_QUEUE` | `0x00000008` | (aliased value) DOS-queue notification target |
| `MCI_MILLISECONDS` | `0x00000010` | Positions in this command are in milliseconds |
| `MCI_TRACK` | `0x00000020` | The `ulTrack` field is valid |
| `MCI_OVER` | `0x00000040` | Vectored-change delay (`ulOver`) is valid |
| `MCI_TEST` | `0x00000080` | Test whether the command *could* be performed; do not perform it |
| `MCI_TO_BUFFER` | `0x00000100` | Operation targets an application buffer |
| `MCI_FROM_BUFFER` | `0x00000200` | Operation sources from an application buffer |
| `MCI_CONVERT_FORMAT` | `0x00000400` | Convert data format during the operation |

---

## 3. MCI command messages [DOC-IBM `mcios2.h:29-96`]

`usMessage` is a small integer. The core (device-independent) set:

| Message | Value | Purpose |
|---|---|---|
| `MCI_OPEN` | `1` | Open/initialize a device instance; returns a device ID |
| `MCI_CLOSE` | `2` | Close a device instance |
| `MCI_ESCAPE` | `3` | Send a device-specific escape command |
| `MCI_PLAY` | `4` | Begin playback |
| `MCI_SEEK` | `5` | Reposition without playing |
| `MCI_STOP` | `6` | Stop the current operation |
| `MCI_PAUSE` | `7` | Pause (resumable) |
| `MCI_INFO` | `8` | Return textual information (product name, file name, ...) |
| `MCI_GETDEVCAPS` | `9` | Query device capabilities |
| `MCI_STATUS` | `10` | Query current status (position, mode, length, ...) |
| `MCI_SPIN` | `11` | Spin the medium up/down (disc devices) |
| `MCI_SET` | `12` | Set device parameters (time format, volume, audio on/off, door, ...) |
| `MCI_STEP` | `13` | Step by frames |
| `MCI_RECORD` | `14` | Begin recording |
| `MCI_SYSINFO` | `15` | Query MMPM/2 system information (installed devices, counts) |
| `MCI_SAVE` | `16` | Save recorded data to a file |
| `MCI_CUE` | `17` | Pre-roll / cue for play or record |
| `MCI_UPDATE` | `18` | Repaint (video) |
| `MCI_SET_CUEPOINT` | `19` | Arm a cue-point notification |
| `MCI_SET_POSITION_ADVISE` | `20` | Arm periodic position-change notifications |
| `MCI_LOAD` | `22` | Load a media element (file) into an open device |
| `MCI_ACQUIREDEVICE` | `23` | Acquire exclusive/queued use of the device |
| `MCI_RELEASEDEVICE` | `24` | Release the device |
| `MCI_MASTERAUDIO` | `25` | Set the system master audio (volume, on/off) |
| `MCI_GETTOC` | `26` | Get the table of contents (CD audio) |
| `MCI_CONNECTOR` | `28` | Enable/disable/query a device connector |
| `MCI_RESUME` | `29` | Resume a paused device |
| `MCI_CONNECTORINFO` | `31` | Query connector information |
| `MCI_CONNECTION` | `33` | Query/establish a device-to-device connection |
| `MCI_GROUP` | `34` | Group operation |

Values `40`-`63` (`MCI_CAPTURE`, `MCI_FREEZE`, `MCI_PUT`, `MCI_WHERE`, `MCI_WINDOW`,
`MCI_CUT`/`COPY`/`PASTE`/`UNDO`, `MCI_MIXSETUP`, `MCI_BUFFER`, ...) are reserved for digital video,
video overlay, and the amp-mixer streaming path [DOC-IBM `mcios2.h:70-95`]. `MCI_MAX_COMMAND` is
`64`; messages at or above `MCI_USER_MESSAGES` (`2000`) are reserved for applications [DOC-IBM
`mcios2.h:96,103`].

---

## 4. MCI parameter blocks [DOC-IBM - `mcios2.h`]

`pParam2` points to a message-specific structure. Every block leads with `HWND hwndCallback`
(the notification window). The base block is `MCI_GENERIC_PARMS`, used by messages that need no
data beyond the callback (`MCI_STOP`, `MCI_PAUSE`, `MCI_RESUME`, `MCI_ACQUIREDEVICE`,
`MCI_CLOSE`, ...):

```c
typedef struct _MCI_GENERIC_PARMS {
    HWND hwndCallback;      /* PM window handle for MCI notify message */
} MCI_GENERIC_PARMS;                                        /* [DOC-IBM mcios2.h:346] */
```

| Structure | Message | Fields (after `hwndCallback`) |
|---|---|---|
| `MCI_OPEN_PARMS` | `MCI_OPEN` | `USHORT usDeviceID` (out), `USHORT usReserved0`, `PSZ pszDeviceType`, `PSZ pszElementName`, `PSZ pszAlias` |
| `MCI_PLAY_PARMS` | `MCI_PLAY` | `ULONG ulFrom`, `ULONG ulTo` |
| `MCI_RECORD_PARMS` | `MCI_RECORD` | `ULONG ulFrom`, `ULONG ulTo` |
| `MCI_SEEK_PARMS` | `MCI_SEEK` | `ULONG ulTo` |
| `MCI_SET_PARMS` | `MCI_SET` | `ULONG ulTimeFormat`, `ulSpeedFormat`, `ulAudio`, `ulLevel`, `ulOver`, `ulItem`, `ulValue` |
| `MCI_STATUS_PARMS` | `MCI_STATUS` | `ULONG ulReturn` (out), `ULONG ulItem`, `ULONG ulValue` |
| `MCI_INFO_PARMS` | `MCI_INFO` | `PSZ pszReturn`, `ULONG ulRetSize` |
| `MCI_LOAD_PARMS` | `MCI_LOAD` | `PSZ pszElementName` |
| `MCI_MASTERAUDIO_PARMS` | `MCI_MASTERAUDIO` | `ULONG ulReturn` (out), `ULONG ulMasterVolume` |
| `MCI_GETDEVCAPS_PARMS` | `MCI_GETDEVCAPS` | `HWND hwndCallback`, `ULONG ulReturn` (out), `ULONG ulItem`, `USHORT usMessage`, `USHORT usReserved0` |

[DOC-IBM `mcios2.h:1146-1155,1212-1217,1289-1294,1359-1363,1650-1662,2082-2092,1084-1089,1096-1099,1117-1122,826-833`]

Device-class variants extend the base blocks with extra fields - e.g. `MCI_AMP_OPEN_PARMS` adds
`PVOID pDevDataPtr`, and `MCI_VID_OPEN_PARMS` / `MCI_DGV_OPEN_PARMS` add `HWND hwndParent` for a
video device's display window [DOC-IBM `mcios2.h:1160-1191`]. `MCI_VD_PLAY_PARMS` /
`MCI_DGV_PLAY_PARMS` add a speed field (`ulFactor` / `ulSpeed`) [DOC-IBM `mcios2.h:1220-1236`].

### 4.1 `MCI_OPEN` in detail

`MCI_OPEN` is the entry to every device. `pszDeviceType` names the device (a device-type name
from section 5, or a system alias); `pszElementName` is typically a file name to associate, or `NULL`.
On success, `usDeviceID` receives the handle used for all subsequent messages. `MCI_OPEN` flags
[DOC-IBM `mcios2.h:1129-1136`]:

| Flag | Value | Meaning |
|---|---|---|
| `MCI_OPEN_ELEMENT` | `0x00000100` | `pszElementName` is a media-element (file) name |
| `MCI_OPEN_ALIAS` | `0x00000200` | `pszAlias` supplies a short name for later reference |
| `MCI_OPEN_ELEMENT_ID` | `0x00000400` | `pszElementName` is an element ID, not a name |
| `MCI_OPEN_PLAYLIST` | `0x00000800` | The element is an in-memory playlist |
| `MCI_OPEN_TYPE_ID` | `0x00001000` | `pszDeviceType` encodes a device-type ID + ordinal |
| `MCI_OPEN_SHAREABLE` | `0x00002000` | Open the device/element shareable |
| `MCI_OPEN_MMIO` | `0x00004000` | Element is an already-open MMIO handle |
| `MCI_READONLY` | `0x00008000` | Open the element read-only |

### 4.2 `MCI_SET`, `MCI_SEEK`, `MCI_STATUS` selected flags

- `MCI_SET` [DOC-IBM `mcios2.h:1370-1390`]: `MCI_SET_ITEM` (`0x0100`), `MCI_SET_ON`/`MCI_SET_OFF`
  (`0x0200`/`0x0400`), `MCI_SET_VIDEO`/`MCI_SET_AUDIO` (`0x0800`/`0x1000`),
  `MCI_SET_DOOR_OPEN`/`MCI_SET_DOOR_CLOSED` (`0x2000`/`0x4000`), `MCI_SET_TIME_FORMAT`
  (`0x00010000`). Audio channel selection: `MCI_SET_AUDIO_ALL`/`LEFT`/`RIGHT` (`0`/`1`/`2`).
- `MCI_SEEK` [DOC-IBM `mcios2.h:1345-1346`]: `MCI_TO_START` (`0x0100`), `MCI_TO_END` (`0x0200`);
  otherwise `ulTo` is a position in the current time format.
- `MCI_STATUS` [DOC-IBM `mcios2.h:1823-1835`]: `MCI_STATUS_ITEM` (`0x0100`) selects which item
  `ulItem` names; standard items include `MCI_STATUS_LENGTH` (`2`), `MCI_STATUS_MODE` (`3`),
  `MCI_STATUS_POSITION` (`5`). The returned `MCI_STATUS_MODE` value is one of `MCI_MODE_NOT_READY`
  (`1`), `MCI_MODE_PAUSE` (`2`), `MCI_MODE_PLAY` (`3`), `MCI_MODE_STOP` (`4`), `MCI_MODE_RECORD`
  (`5`), `MCI_MODE_SEEK` (`6`) [DOC-IBM `mcios2.h:2069-2074`].

### 4.3 Time formats [DOC-IBM `mcios2.h:231-247`]

`MCI_SET` with `MCI_SET_TIME_FORMAT` sets how positions are interpreted. Values include
`MCI_FORMAT_MILLISECONDS` (`1`), `MCI_FORMAT_MMTIME` (`2`), `MCI_FORMAT_MSF` (`5`, minute/second/
frame - CD "red book"), `MCI_FORMAT_TMSF` (`6`, track/min/sec/frame), `MCI_FORMAT_FRAMES` (`8`),
`MCI_FORMAT_HMS` (`9`), `MCI_FORMAT_TRACKS` (`0x0A`), `MCI_FORMAT_BYTES` (`0x0B`),
`MCI_FORMAT_SAMPLES` (`0x0C`), `MCI_FORMAT_HMSF` (`0x0D`).

---

## 5. MCI device types [DOC-IBM `mcios2.h:129-171`]

The device-type constant and the string name an application passes as `pszDeviceType`:

| Constant | Value | Type name string |
|---|---|---|
| `MCI_DEVTYPE_CD_AUDIO` | `3` | `"CDaudio"` |
| `MCI_DEVTYPE_WAVEFORM_AUDIO` | `7` | `"Waveaudio"` |
| `MCI_DEVTYPE_SEQUENCER` | `8` | `"Sequencer"` (MIDI) |
| `MCI_DEVTYPE_AUDIO_AMPMIX` | `9` | `"Ampmix"` (amplifier-mixer) |
| `MCI_DEVTYPE_OVERLAY` | `10` | `"Overlay"` (video overlay) |
| `MCI_DEVTYPE_ANIMATION` | `11` | `"Animation"` |
| `MCI_DEVTYPE_DIGITAL_VIDEO` | `12` | `"Digitalvideo"` |
| `MCI_DEVTYPE_CDXA` | `17` | `"CDXA"` (CD-ROM/XA) |
| `MCI_DEVTYPE_TTS` | `19` | `"Texttospeech"` |

Also defined: `MCI_DEVTYPE_VIDEOTAPE` (`1`), `MCI_DEVTYPE_VIDEODISC` (`2`), `MCI_DEVTYPE_DAT`
(`4`), `MCI_DEVTYPE_AUDIO_TAPE` (`5`), `MCI_DEVTYPE_OTHER` (`6`), `MCI_DEVTYPE_SPEAKER` (`13`),
`MCI_DEVTYPE_HEADPHONE` (`14`), `MCI_DEVTYPE_MICROPHONE` (`15`), `MCI_DEVTYPE_MONITOR` (`16`),
`MCI_DEVTYPE_FILTER` (`18`). Per-class capability/status item bases are grouped
(`MCI_AMP_ITEM_BASE` `0x1000`, `MCI_CD_ITEM_BASE` `0x2000`, `MCI_SEQ_ITEM_BASE` `0x5000`,
`MCI_WAVE_ITEM_BASE` `0x6000`, `MCI_DGV_ITEM_BASE` `0x8000`, ...) so each device type numbers its
own set/status items in a distinct range [DOC-IBM `mcios2.h:178-186`].

---

## 6. Asynchronous notification model [DOC-IBM - `mcios2.h`, Toolkit sample `CAPTION/caption.c`]

An MCI command either **blocks** (`MCI_WAIT`) or **returns immediately** (`MCI_NOTIFY`). With
`MCI_NOTIFY`, the device performs the operation on its own thread and, when the operation
completes, is superseded, aborted, or errors, **posts** a Presentation Manager message to the
`hwndCallback` window in the parameter block. The primary message is `MM_MCINOTIFY` (`0x0500`);
related device-posted messages are `MM_MCIPASSDEVICE` (`0x0501`, device use gained/lost),
`MM_MCIPOSITIONCHANGE` (`0x0502`), `MM_MCICUEPOINT` (`0x0503`), and `MM_MCIEVENT` (`0x0505`)
[DOC-IBM `mcios2.h:199-205`].

**`MM_MCINOTIFY` message parameters** [DOC-IBM - observed in Toolkit sample `caption.c:1261-1264`]:

| Field | Extractor | Meaning |
|---|---|---|
| notification code | `SHORT1FROMMP(mp1)` | `MCI_NOTIFY_SUCCESSFUL` (0), `MCI_NOTIFY_SUPERSEDED` (1), `MCI_NOTIFY_ABORTED` (2), `MCI_NOTIFY_ERROR` (3) |
| user parameter | `SHORT2FROMMP(mp1)` | The `usUserParm` passed to `mciSendCommand`/`mciSendString` |
| command message | `SHORT2FROMMP(mp2)` | The MCI message (`MCI_PLAY`, ...) that generated this notification |

The notification codes are `MCI_NOTIFY_SUCCESSFUL`/`SUPERSEDED`/`ABORTED`/`ERROR`
[DOC-IBM `mcios2.h:191-194`]. On an error notification the code word carries the error; the
handler dispatches on the command message to decide what completed. For `MM_MCIPASSDEVICE`,
`SHORT1FROMMP(mp2)` is `MCI_GAINING_USE` (`2`) or `MCI_LOSING_USE` (`1`) [DOC-IBM `mcios2.h:207-208`] - the mechanism by which a
non-shareable device (e.g. the amp-mixer) is handed between applications as their windows
activate [DOC-IBM `mcios2.h:207-208`; observed `daudio.c:690-697`].

---

## 7. `mciSendString` - the string command interface

```c
ULONG APIENTRY mciSendString(PSZ    pszCommandBuf,   /* "<command> <object> <keywords>" */
                             PSZ    pszReturnString, /* return buffer, or NULL */
                             USHORT usReturnLength,  /* size of return buffer */
                             HWND   hwndCallBack,    /* notify window (required if "notify" used) */
                             USHORT usUserParm);     /* echoed in the notification */
```
[DOC-IBM `mcios2.h:2404`; DOC - EDM2 `mciSendString`]

The command string has the form `<command> <object> <keywords>`, where the object is a device
type, file name, or alias (`"open bell.wav alias wav1 wait"`, `"play wav1 from 0 to 1000 wait"`,
`"status cdaudio mode"`). An internal parser converts the string into the equivalent
`mciSendCommand` parameter block and message, so the string and command interfaces are two views
of one engine [DOC - EDM2 `mciSendCommand` remarks]. Return data (for queries such as `status`)
is written as text into `pszReturnString`; if the application wants the parser to format the
return value it must use the `wait` keyword. As with the binary interface, the return code is
`MCIERR_SUCCESS` or an error code in the low-order word, with the device ID in the high-order word
for device-dependent errors; `mciGetErrorString` converts a code to text [DOC - EDM2
`mciSendString`]. The keywords `notify` and `wait` correspond to the `MCI_NOTIFY` / `MCI_WAIT`
flags.

### 7.1 Name/ID and helper calls [DOC-IBM `mcios2.h:2410-2431`]

| Function | Prototype | Purpose |
|---|---|---|
| `mciGetErrorString` | `(ULONG ulError, PSZ pszBuffer, USHORT usLength)` | Convert an MCI error code to a readable string |
| `mciGetDeviceID` | `(PSZ pszName)` | Look up the numeric device ID for an alias/name |
| `mciMakeGroup` | `(PUSHORT pusGroupID, USHORT usCount, PUSHORT pausList, ULONG ulFlags, ULONG ulMMTime)` | Combine devices into a synchronized group |
| `mciDeleteGroup` | `(USHORT usGroupID)` | Dissolve a group |
| `mciSetSysValue` / `mciQuerySysValue` | `(USHORT iSysValue, PVOID pValue)` | Set/query an MMPM/2 system value |

### 7.2 High-level convenience layer [DOC-IBM `mciapi.h:24-39`]

`mciapi.h` adds one-call helpers that wrap open/play/close: `mciPlayFile(hwndOwner, pszFile,
ulFlags, pszTitle, hwndViewport)`, `mciPlayResource(...)`, and `mciRecordAudioFile(...)`. Their
`ulFlags` control synchronization (`MCI_ASYNC` `0x0010`, `MCI_RENDEZVOUS` `0x0008`,
`MCI_ASYNCRENDEZVOUS` `0x0004`, `MCI_STOPACTIVE` `0x0002`, `MCI_REPEAT` `0x0020`) [DOC-IBM
`mciapi.h:60-68`].

---

## 8. MCI error codes [DOC-IBM `meerror.h`]

`MCIERR_SUCCESS` is `0`; error codes are based at `MCIERR_BASE` = `5000` [DOC-IBM
`meerror.h:30-31`]. Representative values:

| Constant | Value | Meaning |
|---|---|---|
| `MCIERR_INVALID_DEVICE_ID` | `5001` | Device ID does not refer to an open device |
| `MCIERR_UNRECOGNIZED_COMMAND` | `5005` | Command not understood by the device |
| `MCIERR_HARDWARE` | `5006` | Hardware error |
| `MCIERR_INVALID_DEVICE_NAME` | `5007` | Named device is not installed |
| `MCIERR_OUT_OF_MEMORY` | `5008` | Insufficient memory |
| `MCIERR_DEVICE_OPEN` | `5009` | Device already open / in use |
| `MCIERR_CANNOT_LOAD_DRIVER` | `5010` | MCI driver could not be loaded |
| `MCIERR_MISSING_PARAMETER` | `5017` | A required parameter/flag was not supplied |
| `MCIERR_UNSUPPORTED_FUNCTION` | `5018` | Device does not support this function |
| `MCIERR_FILE_NOT_FOUND` | `5019` | Media element file not found |
| `MCIERR_DEVICE_NOT_READY` | `5020` | Device not ready |
| `MCIERR_DEVICE_LOCKED` | `5032` | Device is locked by another user |
| `MCIERR_INSTANCE_INACTIVE` | `5034` | The device instance is inactive |
| `MCIERR_INVALID_FLAG` | `5054` | Invalid flag for this message |
| `MCIERR_UNSUPPORTED_FLAG` | `5065` | Flag not supported by this device |
| `MCIERR_INVALID_MODE` | `5067` | Command invalid in the device's current mode |

The stream-manager error space begins at `MEBASE` = `MCIERR_BASE + 500` (`5500`) [DOC-IBM
`meerror.h:194`].

---

## 9. MMIO - multimedia file I/O

MMIO is a buffered, format-aware file API. A handle is an **`HMMIO`** (`typedef ULONG HMMIO`)
[DOC-IBM `os2medef.h:56`]. Every file is read and written through an **IOProc** - an installable
procedure identified by a four-character code (`FOURCC`) that knows a storage system (e.g. DOS
file, in-memory buffer) and, layered on top, a file-format IOProc. This lets the same
`mmioRead`/`mmioWrite` calls transparently translate between a file's stored format and the
application's desired format.

### 9.1 Function map [DOC-IBM `mmioos2.h:843-912`]

| Function | Prototype | Purpose |
|---|---|---|
| `mmioOpen` | `HMMIO (PSZ pszFileName, PMMIOINFO pmmioinfo, ULONG ulOpenFlags)` | Open/create a media file; returns an `HMMIO` (0 on failure) |
| `mmioClose` | `USHORT (HMMIO hmmio, USHORT usFlags)` | Close a media file |
| `mmioRead` | `LONG (HMMIO hmmio, PCHAR pchBuffer, LONG cBytes)` | Read `cBytes`; returns bytes read (-1 = error, 0 = EOF) |
| `mmioWrite` | `LONG (HMMIO hmmio, PCHAR pchBuffer, LONG cBytes)` | Write `cBytes`; returns bytes written (-1 = error) |
| `mmioSeek` | `LONG (HMMIO hmmio, LONG lOffset, LONG lOrigin)` | Reposition; returns new offset (-1 = error) |
| `mmioGetInfo` | `USHORT (HMMIO hmmio, PMMIOINFO pmmioinfo, USHORT usFlags)` | Copy out the handle's `MMIOINFO` (e.g. for direct buffer access) |
| `mmioSetInfo` | `USHORT (HMMIO hmmio, PMMIOINFO pmmioinfo, USHORT usFlags)` | Write back a modified `MMIOINFO` |
| `mmioSetBuffer` | `USHORT (HMMIO hmmio, PCHAR pchBuffer, LONG cBytes, USHORT usFlags)` | Change/enable the I/O buffer |
| `mmioFlush` | `USHORT (HMMIO hmmio, USHORT usFlags)` | Flush buffered writes to the medium |
| `mmioGetLastError` | `ULONG (HMMIO hmmio)` | Extended error code for the last operation |
| `mmioDescend` | `USHORT (HMMIO hmmio, PMMCKINFO pckinfo, PMMCKINFO pckinfoParent, USHORT usFlags)` | Descend into a RIFF chunk (optionally searching) |
| `mmioAscend` | `USHORT (HMMIO hmmio, PMMCKINFO pckinfo, USHORT usFlags)` | Ascend out of a chunk (fills in its size on write) |
| `mmioCreateChunk` | `USHORT (HMMIO hmmio, PMMCKINFO pckinfo, USHORT usFlags)` | Create a new RIFF/LIST/data chunk |
| `mmioAdvance` | `USHORT (HMMIO hmmio, PMMIOINFO pmmioinfo, USHORT usFlags)` | Advance the direct-access buffer (fill on read / flush on write) |
| `mmioInstallIOProc` | `PMMIOPROC (FOURCC fccIOProc, PMMIOPROC pIOProc, ULONG ulFlags)` | Install/remove/find an IOProc by four-character code |
| `mmioSendMessage` | `LONG (HMMIO hmmio, USHORT usMsg, LONG lParam1, LONG lParam2)` | Send a message to the file's IOProc |
| `mmioStringToFOURCC` | `FOURCC (PSZ pszString, USHORT usFlags)` | Build a `FOURCC` from a string |
| `mmioGetHeader` / `mmioSetHeader` | `ULONG (HMMIO hmmio, PVOID, LONG, PLONG, ...)` | Get/set the format header (e.g. `MMAUDIOHEADER`) |
| `mmioQueryHeaderLength` | `ULONG (HMMIO hmmio, PLONG, ...)` | Query the header size for the current format |
| `mmioIdentifyFile` | `ULONG (PSZ pszFileName, ..., PFOURCC pfccStorageSystem, PFOURCC pfccIOProc, ...)` | Identify a file's storage system and format IOProc |

### 9.2 `MMIOINFO` [DOC-IBM `mmioos2.h:67-85`]

Passed to `mmioOpen` to override defaults (IOProc, buffer, translation) and returned by
`mmioGetInfo` to expose the buffer for direct access. `mmioOpen` may be given `NULL` for defaults.

| Field | Type | Meaning |
|---|---|---|
| `ulFlags` | `ULONG` | Open flags (section 9.3) |
| `fccIOProc` | `FOURCC` | Four-character code of the IOProc to use |
| `pIOProc` | `PMMIOPROC` | Explicit IOProc function pointer (in place of `fccIOProc`) |
| `ulErrorRet` | `ULONG` | Extended error return |
| `cchBuffer` | `LONG` | I/O buffer size (file size when a `MEM` file) |
| `pchBuffer` | `PCHAR` | Start of the I/O buffer |
| `pchNext` | `PCHAR` | Next byte to read/write in the buffer |
| `pchEndRead` | `PCHAR` | One past the last readable byte in the buffer |
| `pchEndWrite` | `PCHAR` | One past the last writable byte in the buffer |
| `lBufOffset` | `LONG` | Offset within the buffer of `pchNext` |
| `lDiskOffset` | `LONG` | File offset of the buffer's start |
| `aulInfo[4]` | `ULONG[4]` | IOProc-specific fields |
| `lLogicalFilePos` | `LONG` | Logical file position (buffered or not) |
| `ulTranslate` | `ULONG` | Translation field |
| `fccChildIOProc` | `FOURCC` | Four-character code of the child (format) IOProc |
| `pExtraInfoStruct` | `PVOID` | Pointer to related IOProc data |
| `hmmio` | `HMMIO` | Handle to the media element |

### 9.3 `mmioOpen` flags [DOC-IBM `mmioos2.h:442-468`]

| Flag | Value | Meaning |
|---|---|---|
| `MMIO_CREATE` | `0x00000001` | Create the file |
| `MMIO_READ` | `0x00000004` | Open for reading (default) |
| `MMIO_WRITE` | `0x00000008` | Open for writing |
| `MMIO_READWRITE` | `0x00000010` | Open for read/write |
| `MMIO_COMPAT` | `0x00000020` | Compatibility (share) mode |
| `MMIO_EXCLUSIVE` | `0x00000040` | Deny all other opens |
| `MMIO_DENYWRITE` | `0x00000080` | Deny other writers |
| `MMIO_DENYREAD` | `0x00000100` | Deny other readers |
| `MMIO_DENYNONE` | `0x00000200` | Deny nothing |
| `MMIO_ALLOCBUF` | `0x00000400` | Allocate an internal I/O buffer |
| `MMIO_DELETE` | `0x00000800` | Delete the file |
| `MMIO_APPEND` | `0x00020000` | Position at end for appending |
| `MMIO_NOIDENTIFY` | `0x00040000` | Do not run format identification on open |

Return codes: `mmioOpen` returns `0` on failure (extended error in `MMIOINFO.ulErrorRet`).
`MMIO_SUCCESS` is `0`, `MMIO_ERROR` is `0xFFFFFFFF` [DOC-IBM `mmioos2.h:672-674`].

### 9.4 `mmioSeek` origins

`lOrigin` uses the standard C stream origins `SEEK_SET` (start of file), `SEEK_CUR` (current
position), and `SEEK_END` (end of file); `mmioSeek` returns the resulting absolute offset, or -1
on error [DOC-IBM `mmioos2.h:889`; observed in Toolkit samples, e.g. `ULTIMOIO/ioseek.c`,
`mmioSeek(hmmio, lSeekValue, SEEK_SET)`].

---

## 10. The RIFF / FOURCC chunk model

### 10.1 `FOURCC` [DOC-IBM `mmioos2.h:33,680-693`]

A `FOURCC` (`typedef ULONG FOURCC`) packs four ASCII characters little-endian into a 32-bit
value. The macro is:

```c
#define mmioFOURCC(ch0, ch1, ch2, ch3)                       \
    ( (ULONG)(BYTE)(ch0)        | ((ULONG)(BYTE)(ch1) << 8)  \
    | ((ULONG)(BYTE)(ch2) << 16) | ((ULONG)(BYTE)(ch3) << 24) )
```

Predefined codes include `FOURCC_RIFF` (`'R','I','F','F'`), `FOURCC_LIST` (`'L','I','S','T'`),
`FOURCC_MEM` (`'M','E','M',' '` - an in-memory file), `FOURCC_DOS` (`'D','O','S',' '` - a DOS
file), and the compound-file codes `FOURCC_CTOC`, `FOURCC_CGRP`, `FOURCC_CF`. `mmioStringToFOURCC`
builds one from a string at runtime.

### 10.2 Chunks and `MMCKINFO` [DOC-IBM `mmioos2.h:46-52`]

A RIFF file is a tree of **chunks**. Every chunk has an 8-byte header - a `FOURCC` id and a
32-bit size - followed by its data; `RIFF` and `LIST` chunks are containers whose data begins with
a `FOURCC` *form type* and then holds nested chunks. `MMCKINFO` describes a chunk during
navigation or creation:

| Field | Type | Meaning |
|---|---|---|
| `ckid` | `FOURCC` | Chunk id |
| `ckSize` | `ULONG` | Chunk size in bytes (data only) |
| `fccType` | `FOURCC` | Form/list type (valid when `ckid` is `RIFF` or `LIST`) |
| `ulDataOffset` | `ULONG` | File offset of the chunk's data |
| `ulFlags` | `ULONG` | `MMIO_DIRTY` for a newly created chunk |

**Navigation:** `mmioDescend` moves into a chunk (with `MMIO_FINDCHUNK` `0x0004`,
`MMIO_FINDRIFF` `0x0008`, or `MMIO_FINDLIST` `0x0010` in `usFlags` it searches for a specific
`ckid`/`fccType`) [DOC-IBM `mmioos2.h:486-488`]. `mmioAscend` moves back out, and on a chunk
opened for writing it patches the chunk's size field. **Creation:** `mmioCreateChunk` writes a
new chunk header, using `MMIO_CREATERIFF` (`0x0001`) or `MMIO_CREATELIST` (`0x0002`) to make a
container [DOC-IBM `mmioos2.h:484-485`]. The typical read pattern is descend into the `RIFF` form,
descend/search for each data chunk, `mmioRead` it, then `mmioAscend`.

---

## 11. MMIO IOProcs and their message interface

An IOProc is a callback with the fixed signature `LONG APIENTRY MMIOPROC(PVOID pmmioinfo, USHORT
usMsg, LONG lParam1, LONG lParam2)` [DOC-IBM `mmioos2.h:57-61`]. `mmioInstallIOProc` registers one
under a `FOURCC`. The MMIO engine drives it with `MMIOM_*` messages (base `MMIOM_START` =
`0x0E00`) [DOC-IBM `mmioos2.h:549-577`]:

| Message | Purpose |
|---|---|
| `MMIOM_OPEN` | Open/create the element (the IOProc validates and initializes) |
| `MMIOM_CLOSE` | Close the element |
| `MMIOM_READ` | Read raw bytes (translating if a format IOProc) |
| `MMIOM_WRITE` | Write raw bytes |
| `MMIOM_SEEK` | Reposition |
| `MMIOM_IDENTIFYFILE` | Report whether this IOProc recognizes the file |
| `MMIOM_GETHEADER` / `MMIOM_SETHEADER` | Get/set the format header |
| `MMIOM_QUERYHEADERLENGTH` | Report the header size |
| `MMIOM_SEEKBYTIME` | Seek to a time position |
| `MMIOM_GETFORMATNAME` / `MMIOM_GETFORMATINFO` | Report the format's name/capabilities |

This is how MMIO stays format-independent: `mmioRead` on a `.WAV` file and on a compressed audio
file are the same call to the application; the difference is the IOProc chain (storage-system
IOProc plus optional format/CODEC IOProc) that the handle carries. IOProc capability flags
(`MMIO_CANREADTRANSLATED`, `MMIO_CANSEEKTRANSLATED`, ...) advertise what a given IOProc supports
[DOC-IBM `mmioos2.h:150-159`].

### 11.1 MMIO error codes [DOC-IBM `meerror.h:304-337`]

Based at `MMIOERR_BASE` = `MEBASE + 1000`. Examples: `MMIOERR_CHUNKNOTFOUND`,
`MMIOERR_INVALID_HANDLE`, `MMIOERR_INVALID_PARAMETER`, `MMIOERR_CANNOTWRITE`, `MMIOERR_READ_FAILED`,
`MMIOERR_WRITE_FAILED`, `MMIOERR_SEEK_FAILED`, `MMIOERR_EOF_SEEN`, `MMIOERR_READ_ONLY_FILE`,
`MMIOERR_INVALID_ACCESS_FLAG`.

---

## Sources opened
- `README.md`, `file-io.md` - house style.
- `os2me.h` - MMPM/2 top-level include (component gating).
- `mcios2.h` - MCI messages, device types, flags, `MCI_*_PARMS`
  structures, `mciSendCommand`/`mciSendString`/`mciGetErrorString`/`mciGetDeviceID` prototypes,
  `MM_MCI*` notification messages, time formats, mode values.
- `mciapi.h` - `mciPlayFile`/`mciPlayResource`/`mciRecordAudioFile`
  high-level layer and their flags.
- `mmioos2.h` - MMIO prototypes, `MMIOINFO`, `MMCKINFO`, `FOURCC`
  and `mmioFOURCC`, open/chunk flags, `MMIOM_*` IOProc messages, MMIO success/error sentinels.
- `os2medef.h` - `MMTIME`, `HMMIO`, `FOURCC` base typedefs.
- `meerror.h` - `MCIERR_*`, `MEBASE`, `MMIOERR_*` error values.
- `Toolkit sample MM/CAPTION/caption.c` - observed `MM_MCINOTIFY` mp1/mp2
  parameter breakdown; `.../DAUDIO/daudio.c` - observed `MM_MCIPASSDEVICE` / acquire-device usage;
  `.../ULTIMOIO/ioseek.c` - observed `mmioSeek` origin usage.
- EDM2 `MciSendCommand`, `MciSendString` - behavioural remarks
  (return-code word layout, string-parser relationship, notify semantics).

## See also
- `dive-video.md` - DIVE (Direct Interface Video Extensions), the fast-video/blitter path used by motion-video handlers.
