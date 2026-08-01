# OS/2 16↔32-bit Thunking

OS/2 mixes 16-bit (16:16 segmented) and 32-bit (flat) code in the same process; calls that cross the
boundary go through **thunks** that convert pointers and switch stacks. Used throughout the system
(DOSCALLS, and the Presentation Manager at boot-sequence Stage 11).

Provenance: **[DOC-IBM]** IBM's `systhunk.inc` and `thk2asm.doc` (IBM Developer Connection toolkit,
`devtools/thk2asm/`, IBM 1994–95 — **not** the DDK) for the thunk macros, the
interpreter identities and ordinals, the register interface, the tiling algorithm, and the
parameter-descriptor grammar; **[OBS-RE]** RE of the real DOSCALL1 / kernel for the ECX/EDX
register-preservation contract of ordinary API calls (see the last section).

Ratified (2026-07-26): checked against the IBM DevCon `systhunk.inc` / `thk2asm.doc`
(`systhunk.inc`, `thk2asm.doc`) and Toolkit 4.5 `H/os2def.h`. The two thunk-interpreter identities,
their `DOSCALL1` ordinals (547 / 576), the EAX/EDX/ECX register interface, the tiling algorithm, and
the parameter-type alphabet were confirmed IBM-documented and upgraded to [DOC-IBM]. One earlier claim
— that the descriptor grammar had "no published spec" — was found wrong and corrected in place (it is
documented in `thk2asm.doc`). The API-level ECX/EDX-preservation contract could not be traced to any
IBM primary and was left [OBS-RE].

## The universal thunk

`systhunk.inc` defines the thunk-generation macros (emitting `THK32_<type>` symbols) [DOC-IBM]. The
work is done by two **Thunk Interpreters** that reside in `DOSCALL1.DLL` beginning in OS/2 3.0
[DOC-IBM: `thk2asm.doc`, "An Overview of Thunking"]: **`THK32_UNITHUNK` (= `DOSCALL1.547`)** is the
**32→16** interpreter and **`THK16_UNITHUNK` (= `DOSCALL1.576`)** is the **16→32** interpreter
(`thk2asm.doc` system-imports list). Each is a **register-call** primitive: the caller loads **EAX**
with the target routine to invoke and **EDX** with a descriptor of the parameter conversions required
[DOC-IBM: `thk2asm.doc` — "Both interpreters use EAX to identify the target routine for the thunk and
EDX to define the parameter conversions required"; matched by `systhunk.inc` `UniThunk3216` /
`UniThunk1632`, which load EAX (via `mov eax,OFFSET`/`DB 0B8h`) and `mov edx,&pTypes`]. The
interpreter then performs the ring/stack transition and the 16:16 ↔ flat pointer conversions.

> **Corrected (2026-07-26, Rule 1.7):** an earlier revision named a single "general 32↔16 thunk
> exported by DOSCALL1 (`THK32_UNITHUNK`)" tagged [OBS-RE]. There are in fact **two** direction-
> specific interpreters (32→16 = `THK32_UNITHUNK`, 16→32 = `THK16_UNITHUNK`), their DOSCALL1 residence
> and ordinals are IBM-documented, and the parenthetical `REGCALL` mnemonic (unsourced) was dropped.

## The parameter-descriptor grammar [DOC-IBM]

The descriptor is carried in **EDX**, with **ECX** holding an additional 32 bits for the 32→16
direction. The reason ECX is needed only one way: a 32→16 thunk must know the *size* of every
non-tiled pointer target to check for a 64 KB-boundary crossing — "this is extra information required
by the thunk interpreter, [so] the ECX register is used to hold an additional 32 bits of thunk
parameter descriptions, augmenting that already passed in EDX" (`thk2asm.doc`, "32->16 Thunks")
[DOC-IBM]. It encodes, per argument, how the argument is passed or converted between a 16:16 far
pointer and a 32-bit flat pointer (using the 64 KB tiling of `memory-model.md`).

The per-argument **type alphabet** is itself IBM-documented [DOC-IBM: `thk2asm.doc`, "Defining new
data types for THK2ASM"]: e.g. `L` = long (signed/unsigned), `P` = generic pointer, `I` = tiled
pointer that does not cross a 64 KB boundary (converted to `P` for 16→32), `S`/`U` = signed/unsigned
short, `Z` = input-only ASCII-Z string pointer, and the pointer-to-*N*-byte forms (`2`,`4`,`6`,`8`,
`0`,`Q`) whose identifier increments to its "output" variant when the target is written back.

> **Corrected (2026-07-26, Rule 1.7):** an earlier revision said this grammar "is read out of the
> real binaries rather than a published spec." That is wrong. The descriptor registers (EAX/EDX/ECX)
> and the full per-argument type alphabet are documented in IBM's `thk2asm.doc` (IBM 1994–95). What is
> *not* printed literally is the bit-level encoding THK2ASM emits into EDX/ECX — that is compiler-
> generated — but the grammar it expresses is published.

## Stack switch [DOC-IBM]

A 32→16 thunk switches from the flat 32-bit stack to a **16-bit (tiled) stack**, copies/converts the
arguments into a 16-bit Pascal-style frame, sets the segments to the 16-bit callee's, calls, then
restores. The flat 32-bit `SS:ESP` is pushed before the call and reloaded with `lss` after it
(`systhunk.inc` `BgnParms32` → `mov eax,esp / push ss / push eax`; the `R32_` return path →
`movzx esp,sp / lss esp,[esp]`, "Restore 32-bit stack") [DOC-IBM]. `SS` is set to the callee's 16-bit
stack selector **by the same tiling algorithm** used for pointers — the flat offset's high word is
shifted left 3 and the low 3 bits are taken from the current `CS` ring, because "the ring level of SS
must always match the ring level of CS" (`thk2asm.doc`, tiling section; `systhunk.inc` `ThunkCall32`)
[DOC-IBM]. `DS` is likewise the callee's 16-bit data segment during the call [OBS-RE — established by
the interpreter's `HT32_STARTUP` helper, which `systhunk.inc` only references (`EXTRN`), not the macros
shown here].

## The register-preservation contract [OBS-RE]

The `_System` (`APIENTRY`) convention — `APIENTRY` is `#define`d to `_System` in Toolkit 4.5
`H/os2def.h:45` [DOC-IBM] — marks `EAX`, `ECX`, `EDX` as volatile. **The real OS/2 kernel/DOSCALLS
preserve `ECX` and `EDX`** across the ring-transition thunk, and callers depend on it. Where the
documentation and the shipped binary disagree, the **binary is authoritative for behaviour** — a
correct thunk therefore saves and restores `ECX`/`EDX` (and fixes `DS`/`SS`), even though the spec
would permit clobbering them. `EAX` carries the return value and is genuinely volatile.

> **Not IBM-sourced (2026-07-26):** `APIENTRY` = `_System` is documented (`os2def.h:45`), but the
> claim that the shipped kernel/DOSCALLS actually *preserve* `ECX`/`EDX` **contrary to** the `_System`
> volatility rule could not be traced to any IBM primary (searched the Developer Connection toolkit and
> the DDK — a negative result). It rests on RE of the binaries and stays [OBS-RE].
