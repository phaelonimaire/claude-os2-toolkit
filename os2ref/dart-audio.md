# OS/2 DART - Direct Audio RouTines

**DART** (Direct Audio RouTines) is MMPM/2's low-latency PCM streaming path. Ordinary MCI playback
hands a *file* to a device and lets the subsystem do the work; DART instead lets an application
hand the amp-mixer **raw PCM buffers it fills itself**, which is what real-time audio - games,
synthesis, softphones, anything mixing its own output - actually needs.

The mechanism is unusual enough to be worth stating up front, because it is not how the rest of MCI
works. DART is set up through two ordinary `mciSendCommand` messages (`MCI_MIXSETUP` and
`MCI_BUFFER`), but **the streaming path itself does not go through `mciSendCommand` at all**.
`MCI_MIXSETUP` *returns function pointers* - `pmixWrite` and `pmixRead` - which are the mixer's
direct entry points, and the application calls them itself. In the other direction the application
supplies `pmixEvent`, a callback the mixer invokes each time a buffer completes. So the steady state
is a pointer-to-function handshake with a completion callback: setup is message-based, playback is
direct-call. That is where the latency saving comes from, and it is why DART is described as
"direct".

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 header `mcios2.h` (message numbers, all flags,
`MCI_MIX_BUFFER` / `MCI_MIXSETUP_PARMS` / `MCI_BUFFER_PARMS`, the `MIXERPROC` / `MIXEREVENT`
function types), `os2medef.h` (`DATATYPE_WAVEFORM`), `meerror.h` (`MCIERR_*`, `ERROR_DEVICE_UNDERRUN`);
**[DOC-IBM]** the IBM *MMPM/2 Programming Reference* (`MCI_BUFFER` and `MCI_MIXSETUP` entries) for
behavioural remarks the headers do not carry; **[DOC-IBM]** the Toolkit MM sample
`SAMPLES/MM/DAUDIO/daudio.c` for the observed call sequence, the event-callback shape, and the
stream-priming pattern. Anything below marked **[OBS]** is inferred from that sample's behaviour
rather than stated by IBM, and is flagged individually.

See also `mmpm2-multimedia.md` for `mciSendCommand`, `MCI_OPEN`/`MCI_CLOSE`, MMIO file reading, and
the general MCI model that DART sits inside.

---

## 1. The shape of a DART session

| Step | Mechanism |
|---|---|
| 1. Open the **amp-mixer** device | `mciSendCommand(MCI_OPEN)` |
| 2. Describe the PCM format, get entry points | `mciSendCommand(MCI_MIXSETUP, MCI_MIXSETUP_INIT)` |
| 3. Allocate device buffers | `mciSendCommand(MCI_BUFFER, MCI_ALLOCATE_MEMORY)` |
| 4. Fill buffers, prime the stream | **direct call** `pmixWrite(...)` |
| 5. Steady state: refill on completion | **callback** `pmixEvent` -> **direct call** `pmixWrite` |
| 6. Free buffers | `mciSendCommand(MCI_BUFFER, MCI_DEALLOCATE_MEMORY)` |
| 7. Tear down the mixer | `mciSendCommand(MCI_MIXSETUP, MCI_MIXSETUP_DEINIT)` |
| 8. Close the device | `mciSendCommand(MCI_CLOSE)` |

**The device you open is the amp-mixer, not the waveaudio device.** This is the single easiest thing
to get wrong. `daudio.c` opens `MCI_DEVTYPE_AUDIO_AMPMIX` (`9`, name `"Ampmix"`)
[DOC-IBM `mcios2.h:137,160`] with `MCI_OPEN_TYPE_ID | MCI_OPEN_SHAREABLE`
[DOC-IBM `mcios2.h:1133-1134`]. `MCI_DEVTYPE_WAVEFORM_AUDIO` (`7`) [DOC-IBM `mcios2.h:135`] appears
only later, in `MCI_MIXSETUP_PARMS.ulDeviceType`, where it describes **the data being streamed**, not
the device being driven.

---

## 2. `MCI_MIXSETUP` - message `63` [DOC-IBM - `mcios2.h:94`]

Negotiates the PCM format and exchanges entry points.

```c
typedef struct _MCI_MIXSETUP_PARMS
{
   HWND         hwndCallback;     /* PM window handle for MCI notify message      */
   ULONG        ulBitsPerSample;  /* IN  Number of Bits per Sample                */
   ULONG        ulFormatTag;      /* IN  Format Tag                               */
   ULONG        ulSamplesPerSec;  /* IN  Sampling Rate                            */
   ULONG        ulChannels;       /* IN  Number of channels                       */
   ULONG        ulFormatMode;     /* IN  Either MCI_RECORD or MCI_PLAY            */
   ULONG        ulDeviceType;     /* IN  MCI_DEVTYPE (i.e. DEVTYPE_WAVEFORM etc.) */
   ULONG        ulMixHandle;      /* OUT mixer returns handle for write/read      */
   PMIXERPROC   pmixWrite;        /* OUT Mixer Write Routine entry point          */
   PMIXERPROC   pmixRead;         /* OUT Mixer Read Routine entry point           */
   PMIXEREVENT  pmixEvent;        /* IN  application's completion callback        */
   PVOID        pExtendedInfo;    /* Ptr to extended wave information             */
   ULONG        ulBufferSize;     /* OUT suggested buffer size for current mode   */
   ULONG        ulNumBuffers;     /* OUT suggested # of buffers for current mode  */
} MCI_MIXSETUP_PARMS;
```
[DOC-IBM `mcios2.h:524-542`]

Note the header's own comment on `pmixEvent` reads `/* IN--Mixer Read Routine entry point */`,
which is **wrong** - it is the application's event callback, as the field's type (`PMIXEREVENT`, not
`PMIXERPROC`) and the reference text both confirm. A copy-paste slip in IBM's header; do not be led
by it.

### Flags for `ulParam1` [DOC-IBM - `mcios2.h:465-467`]

| Flag | Value | Meaning |
|---|---|---|
| `MCI_MIXSETUP_INIT` | `0x00010000L` | Initialise the mixer for the mode in `ulFormatMode` |
| `MCI_MIXSETUP_DEINIT` | `0x00020000L` | Tear the mixer setup down |
| `MCI_MIXSETUP_QUERYMODE` | `0x00040000L` | Ask whether a given mode is supported, without initialising |

Combine with `MCI_WAIT` (`0x00000002L`) [DOC-IBM `mcios2.h:215`] or `MCI_NOTIFY` as for any MCI message.

`ulFormatMode` is `MCI_PLAY` (`4`) or `MCI_RECORD` (`14`) [DOC-IBM `mcios2.h:32,42`].
`ulFormatTag` for linear PCM is `MCI_WAVE_FORMAT_PCM`, which is `DATATYPE_WAVEFORM` = `0x0001L`
[DOC-IBM `mcios2.h:1599`, `os2medef.h:159`].

### Semantics [DOC-IBM - *MMPM/2 Programming Reference*, `MCI_MIXSETUP` Remarks]

- The application must fill in `ulDeviceType` and must supply `pmixEvent` before the call.
- On success the mixer fills in `pmixWrite`, `pmixRead`, and `ulMixHandle` - **that handle is the
  first argument to every subsequent direct call**, not the MCI device ID.
- The mixer also fills in `ulBufferSize` and `ulNumBuffers` as **suggestions**. IBM is explicit that
  "the application does not have to use these suggested values as they are simply recommendations."
- **Calling `MCI_MIXSETUP` a second time while already initialised returns `MCIERR_INVALID_MODE`**
  (`5067`) [DOC-IBM `meerror.h:97`, `MCIERR_BASE` = `5000` at `meerror.h:30`]. Deinit first.

---

## 3. `MCI_BUFFER` - message `62` [DOC-IBM - `mcios2.h:93`]

Allocates (or releases) the device buffers the mixer will stream from.

```c
typedef struct _MCI_BUFFER_PARMS
{
   HWND       hwndCallback;     /* PM window handle for MCI notify message    */
   ULONG      ulStructLength;   /* Length of the MCI Buffer command           */
   ULONG      ulNumBuffers;     /* Number of buffers MCI driver should use    */
   ULONG      ulBufferSize;     /* Size of buffers MCI driver should use      */
   ULONG      ulMinToStart;     /* Min number of buffers to create a stream.  */
   ULONG      ulSrcStart;       /* # of EMPTY buffers required to start Source*/
   ULONG      ulTgtStart;       /* # of FULL buffers required to start Target */
   PVOID      pBufList;         /* Pointer to a list of buffers               */
} MCI_BUFFER_PARMS;
```
[DOC-IBM `mcios2.h:559-572`]

### Flags for `ulParam1` [DOC-IBM - `mcios2.h:552-553`]

| Flag | Value |
|---|---|
| `MCI_ALLOCATE_MEMORY` | `0x00040000L` |
| `MCI_DEALLOCATE_MEMORY` | `0x00080000L` |

### Semantics [DOC-IBM - *MMPM/2 Programming Reference*, `MCI_BUFFER`]

- On input, supply `ulNumBuffers`, `ulBufferSize`, and `pBufList` pointing at an array of
  `MCI_MIX_BUFFER` (one per buffer).
- **Buffers are limited to 64 KB on Intel machines.** A segmented-architecture constraint, stated
  outright by IBM - size your ring accordingly.
- **The mixer may allocate fewer buffers than requested.** If it cannot satisfy the whole request it
  updates `ulNumBuffers` with what it managed. **Read the field back** and drive every subsequent
  loop from that value, never from what you asked for.
- Allocating when memory is already allocated returns `MCIERR_INVALID_MODE`; total failure returns
  `MCIERR_OUT_OF_MEMORY` (`5008`) [DOC-IBM `meerror.h:39`]; a bad `pBufList` gives
  `MCIERR_INVALID_BUFFER` (`5050`) [DOC-IBM `meerror.h:80`].

> **Documentation defect, do not be misled.** The reference's Remarks paragraph names a flag
> `MCI_ALLOCATE_BUFFER`. **No such symbol exists in `mcios2.h`** - the flag is `MCI_ALLOCATE_MEMORY`.
> Verified by grep against the Toolkit 4.5 header with a positive control.

---

## 4. `MCI_MIX_BUFFER` - the buffer descriptor [DOC-IBM - `mcios2.h:473-485`]

```c
typedef struct _MCI_MIX_BUFFER
{
   ULONG      ulStructLength;   /* Length of the structure          */
   PVOID      pBuffer;          /* Pointer to a buffer              */
   ULONG      ulBufferLength;   /* Length of the buffer             */
   ULONG      ulFlags;          /* Flags                            */
   ULONG      ulUserParm;       /* Caller parameter                 */
   ULONG      ulTime;           /* OUT--Current time in MS          */
   ULONG      ulReserved1;      /* Unused.                          */
   ULONG      ulReserved2;      /* Unused.                          */
} MCI_MIX_BUFFER;
```

`pBuffer` is filled in **by the mixer** during `MCI_BUFFER` allocation - the application does not
allocate the audio memory itself, it writes into what it is given. `ulUserParm` is an opaque
application cookie carried through to the completion callback; it is the natural place to put a ring
index. `ulTime` is an output field, current time in milliseconds.

The only defined `ulFlags` value is `MIX_BUFFER_EOS` (`0x00000001L`) [DOC-IBM `mcios2.h:493`] -
end-of-stream, set by the application on the final buffer of a finite stream.

**[OBS]** `daudio.c` never assigns `ulStructLength` on either `MCI_MIX_BUFFER` or
`MCI_BUFFER_PARMS`; it `memset`s the parameter block and sets only the fields above. It does set
`ulBufferLength` on each buffer after allocation, to `BufferParms.ulBufferSize`. Treat "length
fields need not be initialised" as observed-from-sample, not as a documented contract.

---

## 5. The direct entry points [DOC-IBM - `mcios2.h:497-517`]

```c
typedef LONG (APIENTRY MIXERPROC)  (ULONG ulHandle, PMCI_MIX_BUFFER pBuffer, ULONG ulFlags);
typedef LONG (APIENTRY MIXEREVENT) (ULONG ulStatus, PMCI_MIX_BUFFER pBuffer, ULONG ulFlags);
```

`pmixWrite`/`pmixRead` are `MIXERPROC`. The first argument is `ulMixHandle` - **not** the MCI device
ID - and the second is a pointer to an `MCI_MIX_BUFFER`.

**[OBS] The third parameter is a buffer *count*, despite being named `ulFlags`.** `daudio.c` primes
the stream with `pmixWrite(handle, MixBuffers, 8)` - passing the array base and the number of
buffers - and re-arms a single buffer with `pmixWrite(handle, &MixBuffers[n], 1)`. So the second
argument is the *first* buffer of a run and the third is how many consecutive buffers follow. The
`ulFlags` name is inherited from the typedef and is misleading here. This reading is inferred from
the sample's usage; IBM's reference does not document the parameter's meaning in this position.

`pmixEvent` is `MIXEREVENT`, called by the mixer on completion. Its `ulFlags` values
[DOC-IBM `mcios2.h:515-517`]:

| Flag | Value | Meaning |
|---|---|---|
| `MIX_READ_COMPLETE` | `0x00000001L` | A record buffer has been filled |
| `MIX_WRITE_COMPLETE` | `0x00000002L` | A playback buffer has been consumed |
| `MIX_STREAM_ERROR` | `0x00000080L` | OR-ed with the above; inspect `ulStatus` |

On `MIX_STREAM_ERROR`, `ulStatus` carries the cause - notably `ERROR_DEVICE_UNDERRUN`
(`MEBASE + 127` = `5627`, where `MEBASE` = `MCIERR_BASE + 500` = `5500`)
[DOC-IBM `meerror.h:242,194,30`].

---

## 6. Traps

**The flag values collide across messages.** `MCI_MIXSETUP_QUERYMODE` and `MCI_ALLOCATE_MEMORY` are
*both* `0x00040000L`. This is not a bug - MCI flags are scoped per message - but it means a flag
pasted into the wrong `mciSendCommand` call will be silently misread as a different, valid operation
rather than rejected. Check flags against the message you are actually sending.

**IBM's own sample switches on the exact flag value, not on bits.** `daudio.c` uses
`switch(ulFlags)` with case labels `MIX_STREAM_ERROR | MIX_READ_COMPLETE` and
`MIX_STREAM_ERROR | MIX_WRITE_COMPLETE` - i.e. it matches `0x81`/`0x82` exactly. Writing the
seemingly-equivalent `if (ulFlags & MIX_WRITE_COMPLETE)` **changes behaviour**, because the error
cases would then also match the success branch. Pick one discipline deliberately.

**Read `ulNumBuffers` back after `MCI_BUFFER`.** The mixer is permitted to give you fewer buffers
than you asked for, and it reports that by rewriting your parameter block rather than by failing.

**64 KB per buffer, Intel.** Segmented-memory heritage; not negotiable.

**[OBS] The completion callback runs in the mixer's context and must be brief.** `daudio.c` does
only two things in `MyEvent`: it re-arms the stream with a direct `pmixWrite`, and - when signalling
the UI - it uses **`WinPostMsg`, not `WinSendMsg`**. Posting rather than sending is the tell that the
callback must not block on another thread's message queue. IBM does not state a rule here; this is
inferred from the sample and should be treated as a strong hint rather than a documented contract.

**Error-code checking is inconsistent in IBM's own material.** The reference's `MCI_BUFFER` example
tests `ULONG_LOWD(rc) != MCIERR_SUCCESS` while its `MCI_MIXSETUP` example tests
`rc != MCIERR_SUCCESS`. `daudio.c` uses both forms in different places. Prefer `ULONG_LOWD(rc)` -
the low word carries the MCI error, and the high word is not always zero.

---

## 7. Applying this to a continuous stream (games, synthesis)

**The IBM sample is not the shape a game wants**, and copying it directly will mislead. `daudio.c`
plays a *finite file*: it computes `ulNumBuffers = fileLength / ulBufferSize + 1`, allocates one
buffer per chunk of the entire file, fills them all up front, and stops when the count is exhausted.

A continuous generator wants the opposite: **a small fixed ring** - the mixer's suggested
`ulNumBuffers` is a reasonable starting point - where each completion callback refills the buffer it
was just handed back and immediately re-queues it, forever. `ulUserParm` is the natural carrier for
the ring index. There is no end-of-stream, so `MIX_BUFFER_EOS` is never set, and `ERROR_DEVICE_UNDERRUN`
becomes a real operational signal (the generator did not keep up) rather than a normal end condition.

The port that motivated this document has exactly that shape: its mixer emits float PCM through a
`mixer_generate(buffer, frames)` call, and the platform backend converts to 16-bit shorts and
pushes. Under DART, `mixer_generate` is called from inside the `pmixEvent` callback, converting into
the returned `MCI_MIX_BUFFER.pBuffer`, followed by a `pmixWrite` of that single buffer - which maps
onto the sample's re-arm pattern exactly, with the file read replaced by generation.

**Unverified.** The continuous-ring usage above is a reading of the documented primitives, not
something IBM documents or `daudio.c` demonstrates. It has **not** been run on hardware. Confirm
against a real device before trusting the latency and underrun behaviour, and update this section
with what is observed.
