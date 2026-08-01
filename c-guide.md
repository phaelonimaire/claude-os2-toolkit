# C Guide — writing correct OS/2 C

> **About this guide (toolkit note).** A C-writing discipline for OS/2 work, where correctness is
> everything and every ABI fact is expensive. Its **principles are universal for any OS/2 C work**
> (apps included): cite where facts come from, never originate an ABI fact, assert every ABI
> struct's size, fail honestly, know whose memory you're touching, and explain load-bearing
> weirdness. Read it alongside `os2-app-dev-guide.md` (the workflow) — that guide is *what to do*;
> this one is *how to write the C*.
>
> The examples are **illustrative war stories** — each rule is one somebody paid for — not files in
> this kit and not code you have. Where a rule says "the codebase," read it as "the codebase you are
> writing." A few rules assume a low-level context (thunks, shared mappings, debug channels); if you
> are writing an ordinary application, take the principle and ignore the mechanism.

This guide explains why OS/2 C is written the way it is, and what to do when you add to it. It is
written for anyone touching the code — contributors, reviewers, and AI assistants, which are often
the most prolific contributors.

## How to read this guide

Each rule is a **trigger** (a condition you can detect while writing code) and
an **action** (what to do when it fires). This is deliberate. Aspirational
rules ("write clean code") do not survive contact with a stuck boot at 2am.
Trigger/action rules survive because they are mechanical: check the trigger,
take the action, move on.

Every rule carries its **why**, and that is load-bearing:

- **Descriptive, not aspirational.** A guide that asserts things the code
  doesn't do teaches readers to "fix" working code to match a document. If a
  rule is not honoured somewhere, that is a bug in the guide, not necessarily
  in the code — say so.
- **The why is the rule.** A rule you understand, you keep when it is
  inconvenient. A rule you merely obey, you route around the first time it
  costs you an afternoon. Most of the whys below were paid for with real
  debugging time; they are recorded so nobody buys them twice.

If an explicit instruction from a maintainer conflicts with a rule here,
follow the maintainer.

---

## Section 0 — Why OS/2 C looks the way it does

OS/2 work is not a greenfield C project, and a lot of general C advice
mis-fires here. A few facts drive nearly every rule that follows.

**Correctness is discovered, not chosen.** OS/2's behaviour was frozen by IBM
decades ago. Nobody gets a vote on what `TIB` looks like, what a given ordinal's
signature is, or what `DosRead` returns on a bad handle. In a normal project the
programmer decides what is correct; here, correctness is a fact to be found, and
the code's job is to establish it and prove it.

**A run achieved by lying costs more than a clean abort.** When something is
unimplemented, an honest failure stops execution at the *cause*. A dishonest
success relocates the bug ten thousand instructions away, into a subsystem that
did nothing wrong, where it looks like a genuine OS/2 fault. A worked example:
a `DosPMMuxSemWait` stub that returned 0 unconditionally — someone made it
"work" — manufactured a phantom **System Error** dialog on every PM wakeup,
because the hard-error thread then read a zeroed `PMHDERR.DAT`. Nothing stopped.
It just lied, and the lie cost days in the wrong place. The goal is never "it
runs." It is "it runs for the right reasons."

**You may own only some of the bytes.** A normal C program owns all of its
memory. OS/2 code frequently does not: structures cross into other processes,
into shared memory, into the system's own segments, or into code compiled in
1995 that cannot be changed. Rules about encapsulation assume an ownership you
may not have.

**Knowledge is the scarce resource, not code.** In low-level OS/2 work every
fact costs a kernel-debugger session, a disassembly, or a DDK read. The C is
cheap to retype; the week that produced one struct offset is not. So the work
gets recorded — findings, artifacts, dead ends and all — because the alternative
is not losing the code, it is buying the same fact twice without knowing it
(Rules 1.6 and 1.7).

There is one more fact worth stating plainly, because it looks like a defect
until you know it: **a lot of correct OS/2 C is weird on purpose.** Raw
`write(2)` in register-critical paths, `-fno-stack-protector`, `-no-pie`,
`#pragma pack`, `APIENTRY` expanding to nothing, deliberately-fatal stubs — each
can be load-bearing, and each looks exactly like something to clean up. See
Section 4.

---

## Section 0.5 — The OS/2 type vocabulary

OS/2 headers define their own scalar, pointer, and handle types. Using them is not
optional style — the API prototypes are written in them, and getting one wrong is a
compile error at best and a silent aliasing bug at worst. All line references below are
`os2emx.h` from the kLIBC/GCC toolchain (the IBM Toolkit's `os2def.h` agrees).

| Type | Definition | Note |
|---|---|---|
| `CHAR` / `PCHAR` | `char` / `char *` | :218 — **always signed-plain `char`**, unlike `BYTE` |
| `BYTE` / `PBYTE` | `unsigned char` **or** `char` | :223 / :231 — see the trap below |
| `PCH`, `PSZ` | `unsigned char *` **or** `char *` | :224-225 / :232-233 — same trap |
| `PCCH`, `PCSZ` | the `__const__` forms | :226-227 / :234-235 |
| `SHORT` / `USHORT` | `short` / `unsigned short` | :244, :247 |
| `LONG` / `ULONG` | `long` / `unsigned long` | :250, :253 |
| `BOOL` | `unsigned long` | :212 — **not `int`**; differs from Win32's `BOOL` |
| `APIRET` | `unsigned long` | :210 — the Control Program return code (`0` = success) |
| `LHANDLE` | `unsigned long` | :298 — the base of every PM handle |
| `HAB`,`HPS`,`HDC`,`HWND`,`HMQ`,… | `LHANDLE` | :5379-5391 — see "handles are not typed" |
| `MPARAM` / `MRESULT` | `VOID *` | :5365, :5368 — pointer-sized, never `int` |
| `FIXED` | `LONG` | :8863 — 16.16 fixed point; build with `MAKEFIXED` |
| `APIENTRY` / `EXPENTRY` | `_System` (or empty) | :162-166 — the calling convention |

### Rule 0.5.1: Never cast to `PSZ`/`PCH`/`BYTE*` with `const_cast` alone

**Trigger:** You are passing a `const char *` (or a `char` buffer) to any OS/2 API.

**Action:** Use `reinterpret_cast` — through a helper if you do it more than twice:

```c
/* PSZ/PCH are conditionally `unsigned char *`, so const_cast alone will not compile. */
static inline PSZ AsPSZ(const char *s) {
    return (PSZ)(char *)s;              /* C */
}
/* C++: reinterpret_cast<PSZ>(const_cast<char *>(s)) */
```

**Why:** `BYTE`, `PCH`, `PSZ`, `PCCH` and `PCSZ` are defined **two different ways**
depending on whether **`OS2EMX_PLAIN_CHAR`** is defined [DOC-IBM — `os2emx.h:220-237`]:
without it they are `unsigned char`-based, with it `char`-based. So
`const_cast<PCH>(s)` compiles under one configuration and fails under the other with
*"invalid const_cast from `const char*` to `PCH` {aka `unsigned char*`}"*. A
`reinterpret_cast` is correct under both. This bites on every string-taking API —
`GpiCharStringPosAt`, `GpiQueryTextBox`, `WinSetWindowText`, `DosLoadModule`'s error
buffer — and it is the single most common first compile error when porting C or C++ to
OS/2. [OBS-RE — hit three separate times in one afternoon porting Scintilla.]

Corollary: **do not assume `BYTE` is unsigned.** If you need a 0..255 pel or byte value,
say `unsigned char` explicitly rather than relying on `BYTE`.

### Rule 0.5.2: Handles are not typed — the compiler will not save you

**Trigger:** You are passing a handle to any PM API.

**Action:** Check the parameter name against the prototype. Do not rely on the type.

**Why:** `HAB`, `HPS`, `HDC`, `HWND`, `HMQ`, `HBITMAP`, `HPOINTER` and the rest are all
`typedef LHANDLE` — the *same* `unsigned long` [`os2emx.h:298, 5379-5391`]. Passing an
`HWND` where an `HPS` belongs compiles silently and fails at run time, usually as
"nothing drew." Where a function takes several handles (`WinPopupMenu` takes three
`HWND`s; `GpiBitBlt` takes two `HPS`es), argument order is unenforced by the type system.

### Rule 0.5.3: Message parameters go through the `MPFROM*` / `*FROMMP` macros

**Trigger:** You are building or unpacking an `MPARAM`.

**Action:** Use the macros (`MPFROMSHORT`, `MPFROM2SHORT`, `MPFROMP`, `MPFROMLONG`,
`SHORT1FROMMP`, `SHORT2FROMMP`, `LONGFROMMP`, `MPFROMHWND`, …), never a manual cast or
shift.

**Why:** `MPARAM` and `MRESULT` are `VOID *` [`os2emx.h:5365, 5368`], so they are
pointer-sized and their packing is a contract, not arithmetic you should reproduce.
`SHORT1FROMMP`/`SHORT2FROMMP` extract the low and high halves respectively; hand-rolled
shifts get the sign extension wrong for negative coordinates. The macro table is in
`os2ref/pm-window-messaging.md`.

---

## Section 1 — Provenance

This is the spine of the guide. OS/2 code is largely a pile of facts about
OS/2, and a fact whose origin is unrecorded is a fact nobody can check.

### Rule 1.1: A new constant gets a name and a cited source

**Trigger:** You are about to write a literal — a struct offset, a size, an
ordinal, an error code, a magic address, a flag bit — that encodes something
about OS/2.

**Action:** Give it a name, and cite where the value came from, at the site.

**Why:** Low-level OS/2 code accumulates thousands of bare hex constants.
`0x10000` alone can appear hundreds of times: that is not a number, it is a
*concept* (16-bit segment / tile granularity) retyped hundreds of times. But
naming alone is not enough. The question that matters at 2am is not "what is
this called" — it is **"did IBM require this, did someone observe it, or did
someone guess?"** Those three have identical syntax and wildly different trust,
and only a citation separates them. A real instance: a block of six consecutive
ordinals carried plausible names (`FlatDS`, `ABIOS`, `EnumAttribute`) attached
to the *wrong* ordinals; nothing about those rows looked wrong, and they blocked
a WPS launch until somebody went and checked.

The shape to copy:

```c
_Static_assert(sizeof(struct InfoSegGDT) == 0x72, "GIS must be 114 bytes");
```

…with the source (`DDK infoseg.h`) cited in the declaring header. Value, name,
source, and a compiler-enforced test, in one line. That is what a fact should
look like.

### Rule 1.2: Name the *kind* of source, not just the source

**Trigger:** You are citing where a value came from.

**Action:** Make it clear which kind of source it is, because the kind
determines how the next reader re-checks it:

- **Documented** — a published DDK header, a Toolkit header, the osFree
  reference, a redbook. The reader's next move is *go read it*. Authoritative
  for **meaning**: error semantics, what a field's zero means, who pops the
  args, what a call returns on bad input.
- **Observed** — KDB on a machine you own, a runtime dump, a disassembly. The
  reader's next move is *go re-run it*. Authoritative for **shape**: offsets,
  sizes, addresses, call order. A debugger shows you state; it cannot show you
  meaning, so an "observed" citation on a semantic claim is a guess wearing a
  costume.
- **Inferred** — derived by reasoning from the other two. Mark it. Inference is
  where the guesses live, and it is the category that looks identical to
  knowledge.

(This is the same three-way split `os2ref/` tags as `[DOC-IBM]` / `[OBS-RE]` /
`[DOC]`. Preserve the distinction when you quote it.)

**Why:** A source's kind records *which question it is competent to answer*.
This is not pedantry — the categories cover different failure modes. Where
documentation and implementation **conflict**, the implementation wins for
behaviour, because the binaries you have to interoperate with were compiled
against it. Worked example: `os2def.h` declares `APIENTRY = _System`, which
makes EAX/ECX/EDX volatile — and the real kernel preserves ECX/EDX anyway. Code
that saves them is right, and that fix needs its observed-source citation
*loudly*, or a future reader "corrects" it back to the documented ABI and
reintroduces the bug.

### Rule 1.3: Never be the origin of an ABI fact

**Trigger:** You need a value — an offset, a size, a signature, an ordinal —
and you find you already "know" it.

**Action:** Stop. Go look it up: `os2ref/`, the Toolkit headers, the DDK, an
IBM `.INF` via `tools/inf2txt`. The authoritative answer is usually a grep away.
If you cannot find a source, the honest move is to say the fact is
unestablished — not to supply it.

**Why:** This applies to everyone, and it applies to AI assistants absolutely.
A confident, plausible, unsourced value is the single most expensive thing that
can enter an OS/2 codebase, because it is indistinguishable from a real one and
leaves no seam for anyone to notice. Human contributors guess and are sometimes
wrong; a model guesses *fluently*, at scale, in the house style. "I knew it" is
not a source — not because it is often wrong, but because it is
**unfalsifiable**. You can re-read `infoseg.h`. You can re-run KDB. You cannot
re-run anyone's memory.

This is not hypothetical. One DDK read turned up four ordinal rows whose
declared argument-byte count was 0 while the implementation read arguments —
each one leaking the caller's 16-bit stack on every call — and a
`WinCreateConsole` call with three of four parameters misidentified, built by
inferring a signature rather than reading the header that declares it. All of
them were plausible. All of them linked. All of them ran.

### Rule 1.4: A file that encodes ABI facts says so in its header

**Trigger:** You are creating a header or file whose contents are facts about
OS/2 rather than your own design.

**Action:** Open it with a header stating what it is, where its facts came
from, and any convention a reader needs:

```c
/*
 * os2api.h — OS/2 API constants and types.
 *
 * What this file is: a transcription of OS/2 ABI facts — constants, types and
 * layouts — read out of IBM's DDK/Toolkit headers and published API
 * documentation. Each fact cites its source at the site (Rules 1.1/1.2).
 *
 * Naming: all names are prefixed OS2_ to avoid colliding with host system
 * headers.
 */
```

**Why:** It tells a reader — including a reviewer who has never met you —
whether they are looking at a transcription or an invention, and where to check.

A cautionary case: a header that opened by describing itself as deriving its
values from "publicly documented specifications" — while citing a DDK header in
a `_Static_assert` 560 lines below, and after its layouts had been fixed by
reading IBM's headers directly. A file's self-description is a fact like any
other: it needs a source, and it needs to match what the file actually does.
Where it doesn't, fix it under Rule 1.7 rather than quietly. Describe your
sources as they are — "transcribed from IBM's Toolkit headers" is accurate and
checkable; a vaguer claim that sounds better is the same unsourced assertion
Rule 1.3 exists to stop.

### Rule 1.5: Every ABI struct asserts its size

**Trigger:** You are defining or editing a struct that must match an OS/2
layout — anything wrapped in `#pragma pack(push, 1)` or carrying
`__attribute__((packed))`.

**Action:** Add `_Static_assert(sizeof(T) == N, "...")` with the size and its
source. Put the byte offset in a comment on each field.

**Why:** A packed struct is a wire format; being one byte wrong is a silent,
system-wide corruption that manifests far away. The compiler will check this for
free, forever, at zero runtime cost — and it is the only rule here that catches
a bug *before* it can happen rather than after. The model:

```c
_Static_assert(sizeof(TIB2) == 16, "TIB2 size must be 16 bytes");
_Static_assert(sizeof(TIB)  == 24, "TIB size must be 24 bytes");
_Static_assert(sizeof(PIB)  == 28, "PIB size must be 28 bytes");
```

Two real bugs this would have caught: truncated `InfoSeg` structs, and a
truncated `GDDMODEINFO` that had every video mode written at the wrong stride —
which is why PM fell back to 640x480 instead of the configured resolution. Both
were eventually found by reading IBM's headers, not by debugging. An assertion
would have caught either at compile time.

### Rule 1.6: Findings are artifacts — record them, negative ones included

**Trigger:** You just learned something — from a disassembly, a KDB session, a
DDK read, a runtime dump, an experiment — whether or not it produced a working
change.

**Action:** Write it down where the next person will look, and keep the
artifact. A disassembly you ran gets saved, not just its conclusion. A search
that found nothing gets recorded as *"searched X, absent — stop looking."* An
experiment that failed gets recorded as failed, with what it ruled out.
Findings about a subsystem go in your docs next to that subsystem's other
notes; findings about a specific line go in a comment at that line.

**Why:** **The expensive thing is not the code — it is the knowledge.** Every
fact costs a KDB session, a disassembly, or a DDK read to produce. Unrecorded,
it costs that again, and nobody knows it is being bought twice. The code is
cheap to retype; the week that produced one offset is not.

The receipts are severe. A subsystem-contract document was once written on the
premise that two DDK `.inc` files are not shipped — they are, in three places —
and that single unrecorded check sent months of debugger work at questions IBM
answers in a header. Elsewhere, an audit checklist was written against the exact
call that was crashing, two days before anyone looked at the crash, and nobody
ran it. On the other side of the ledger: a DDK sweep that established a
particular protocol is **absent from the entire DDK** is a genuinely valuable
result, and its entire value is in being written down, because it converts an
open search into a closed question.

**Negative results are findings.** "We looked and it is not there" is expensive
to produce and free to record. So is "we tried this and it did not work,
because X." Both prevent the same work being done again by someone who has no
way to know it was already done.

### Rule 1.7: Supersede in place — never delete a claim, mark it

**Trigger:** You have discovered that something recorded — a comment, a contract
document, an offset table, a hypothesis — is wrong.

**Action:** Leave the wrong claim visible, mark it wrong, and put the evidence
next to it. Do not quietly delete it and write the right answer in its place.

**Why:** A deleted wrong claim takes two things with it: the knowledge that
someone once believed it, and the reason they were wrong. Both are exactly what
stops the next reader — who will have the same plausible thought — from
re-deriving it. "This says X; the obvious reading is Y; here is why Y is wrong
and how we know" is worth far more than a bare corrected value.

The shape that works is a retraction block at the top of the document, keeping
every wrong claim, marking it, citing the source that overturned it, and
explaining the correct reading. For example, a field at `+0x1a` recorded as
*"we read this as an AVIO-PS far pointer; it is `CellByteSize`; here is why the
misread was natural"* — because the next person to see a zero there will
otherwise reach the same conclusion.

This applies to code comments too. If a comment records a belief that turned out
wrong, correct it *and say it was wrong*. A comment is a record of what was
known, not just an instruction to the compiler.

---

## Section 2 — Honest failure

### Rule 2.1: A stub fails honestly

**Trigger:** You are writing a function you have not implemented.

**Action:** Route it through one piece of stub machinery that logs, applies the
central policy, and returns a real error:

```c
#define DOSCALL_STUB(name) \
    uint32_t name(void) { \
        ldebug("WARNING: %s() not implemented", #name); \
        stub_handler(__FILE__, __LINE__, __func__, STUB_ERROR_FATAL); \
        return ERROR_INVALID_FUNCTION; \
    }
```

Never return 0/success from something you did not do. Never invent a plausible
return value to keep a caller happy.

**Why:** See Section 0. A stub that lies does not stop the run; it corrupts it
quietly. Fatal stub sites are not scaffolding to be embarrassed about — they are
the mechanism that makes "the desktop paints" a claim you can defend, rather
than a screenshot.

### Rule 2.1a: The test harness must fail as honestly as the code

**Trigger:** You are writing the reporting side of a test — printing a result, a status line, or a
pass/fail.

**Action:** Report the *actual* return value and error code. Never collapse "an error happened" into
a benign-looking outcome.

**Why:** A harness that says `if (rc == OK) ... else "cancelled"` will report a hard failure as a
user action, and you will debug the wrong thing. This happened here: `WinDlgBox` was returning
`DID_ERROR` (`0xFFFF`) because a control class in the template was rejected, and the harness
displayed "Cancelled — settings unchanged" for several rounds. Printing the raw `rc` **and**
`WinGetLastError` surfaced `PMERR_INVALID_HWND` immediately, and the real bug with it. The
honest-failure discipline in Rule 2.1 applies to the scaffolding, not just the product —
scaffolding is where a lie is least likely to be noticed.

### Rule 2.2: Guards are data — do not route around them

**Trigger:** Execution stops at a fatal stub, an assertion, an `abort()`, or a
breakpoint, and you want to get past it.

**Action:** The legitimate responses are: **implement the thing**, **report it
and stop**, or **use an explicit bring-up mode** (Rule 2.3). Not: make the stub
return 0, add a bypass flag, catch the signal, or delete the guard.

**Why:** The guard is not in your way — it is the most useful output the system
has produced. It is telling you exactly which fact is unestablished, at the
moment it is needed, with a stack that points at the caller. That information is
expensive to get any other way, and routing around it destroys it *and*
reintroduces the bug class in Section 0. This is the most-violated rule in the
guide, because the workaround is always available and always looks reasonable
when you are stuck and the fix is five minutes away. Worth remembering that
"make it run" is not the goal, and that the last person who took this shortcut
spent the following week chasing a System Error dialog that did not exist.

### Rule 2.3: A relaxation is a named, logged mode with a written reason

**Trigger:** You genuinely need unimplemented calls to soft-fail rather than
abort — a bring-up where a flag-day swap would die on first touch.

**Action:** Make it a named environment variable, off by default, that logs
**every** call it lets through, with the rationale in the source explaining why
the mode exists and what it is for.

**Why:** The difference between engineering and cheating is whether the
relaxation is visible. A named mode is reviewable, greppable, defaults to
honest, and turns the soft-fails into a worklist. An inline edit that makes one
stub return 0 is invisible forever.

### Rule 2.4: The error policy lives in one place

**Trigger:** You are about to write the same error-handling tail at several
call sites.

**Action:** Move the policy into one function. A `stub_handler()`-style
function owns severity, bring-up behaviour, and the fatal banner; call sites
pass only `__FILE__`, `__LINE__`, `__func__`, and a severity.

**Why:** When policy lives at every call site, changing it means editing every
call site, so it never changes. In one place, it is one edit.

---

## Section 3 — Ownership

### Rule 3.1: Before you write through a pointer, know whose memory it is

**Trigger:** You are about to write, zero, free, realloc, or cache a pointer to
memory you did not just allocate.

**Action:** Establish which it is — **yours**, another **process's**, or a
**shared/server-backed** mapping — because the answer decides what you are
allowed to do. Can you zero it? Can you assume it still exists after `DosExit`?
Is another process mapping the same page right now?

**Why:** This is the rule that catches the real bugs, and the one general C
advice does not have. A receipt, from a module loader:

```c
// Zero the memory - but NEVER through a shared mapping that another
// process already owns. "Ready" here means another process's LIVE
// content: this memset zeroed a live pool descriptor system-wide
// (the spooler mapping a ready PMMERGE object) -> a divide fault in
// WinMspPoolInit in every process started afterwards ...
if (!obj_shared_state || obj_shared_state[i] == STATE_UNOWNED)
    memset(addr, 0, vsize);
```

A `memset` that is obviously correct in a normal program wiped another
process's live data system-wide.

### Rule 3.2: Do not encapsulate a wire format

**Trigger:** You are about to add an accessor to "protect" a struct field, or
you feel bad about reading `something->field` across a file boundary.

**Action:** If the struct is an ABI layout — packed, shared, or read by code
you don't control — leave it alone. Read the field.

**Why:** You cannot encapsulate a wire format. `TIB` is 24 bytes because OS/2
says so, and other code reads `FS:[0]` with a raw pointer and will never call
your accessor. The struct is not *behind* an interface; the struct **is** the
interface, byte for byte, shared with code you did not write and cannot change.
The same applies to shared memory generally: a getter in one process guards
nothing about what another process does to the same page. And in
register-critical paths a function call is not free — it costs stack you may not
have and touches registers under contract.

### Rule 3.3: Accessors are for state you own

**Trigger:** You need a global, or file-scope mutable state that other files
must reach.

**Action:** Make it `static` and expose it through accessors:

```c
int  dosthunk_get_depth(void)      { return dosthunk_depth; }
void dosthunk_set_depth(int depth) { dosthunk_depth = depth; }
```

**Why:** For state you genuinely own, the usual reasons apply and cost nothing:
the owning file can change its representation, and `grep` shows every reader.
This is the *complement* of Rule 3.2, not a contradiction of it — the line is
"do we own the layout," not "is it a struct."

### Rule 3.4: Two definitions of one shared structure need a cross-assert

**Trigger:** A struct is defined in more than one place, or two definitions map
the same shared-memory page.

**Action:** Prefer one canonical definition. Where that is genuinely
impractical, assert the sizes against each other so a one-sided edit fails the
build instead of corrupting the page.

**Why:** Structs that "agree today" with nothing enforcing it are one edit away
from a system-wide corruption of exactly the kind Rule 3.1 documents, and the
symptom appears in a different process from the change.

---

## Section 4 — Load-bearing weirdness

### Rule 4.1: Weirdness gets its reason at the site

**Trigger:** You are writing something that looks wrong and isn't — a raw
syscall where a helper exists, a disabled compiler feature, a magic
re-invocation, an empty macro.

**Action:** Write the reason next to it, in one line, at the site.

**Why:** This is the cheapest, highest-leverage rule in the guide, and the one
that decides how the code reads to a stranger. **Weirdness without a why is a
liability; weirdness with a why is a credential.** `-fno-stack-protector` bare
reads as "they disabled security features." `-fno-stack-protector` with a line
explaining that the canary probe writes below ESP, where the OS/2 stack in that
path has no guard page, reads as "these people know exactly what they are
doing" — same flag, opposite reception, and the drive-by critic has nothing to
post. The reason costs a comment; not having it costs the argument.

The model is the comment in Rule 3.1: it explains the mechanism *and* names the
bug it prevents.

### Rule 4.2: Do not normalize what you have not understood

**Trigger:** You are cleaning up code that looks non-idiomatic.

**Action:** Find out why it is like that first. If there is no comment and no
obvious reason, ask — do not assume it is an accident.

**Why:** This is the same reflex as routing around a guard (Rule 2.2), wearing
better clothes: making the code *look* right instead of *be* right. Low-level
OS/2 code is full of oddities that are load-bearing, and the failure they cause
when "fixed" shows up somewhere unrelated, a week later. If the code is
genuinely just untidy, cleaning it up is welcome — but the burden is on the
cleaner to establish that.

---

## Section 5 — File organization

### Rule 5.1: A `.c` file owns one thing

**Trigger:** You are creating a `.c` file, or adding a function to one.

**Action:** Decide what the file owns — a type, or a well-defined surface — and
keep it to that. A good target: each file in a device or driver family exports
**exactly one** symbol, `<family>_<name>_register()`, with everything else
`static`.

**Why:** The translation unit is the only encapsulation boundary C enforces.
A file with one export has an interface you can hold in your head.

### Rule 5.2: Your functions carry the file prefix; IBM's names win

**Trigger:** You are writing a non-`static` function.

**Action:** If it is your code, prefix it with the file (`vfs_`, `os2_sem32_`,
`bridge16_`, `dosthunk_`, …). If it is an OS/2 ABI entry point, use IBM's exact
spelling — `MouOpen`, `VioWrtTTY`, `DosRead` — with no prefix.

**Why:** The prefix is C's only namespacing, and it is what makes a symbol
greppable. But the ABI name is not yours to change: ordinal tables, `.DEF`
exports, and LX fixups need the exact spelling, so a file exporting a couple of
dozen unprefixed `Mou*` symbols is correct, not drift. The rule is "prefix your
code," not "prefix everything."

### Rule 5.3: Internal helpers are `static` and carry no prefix

**Trigger:** A function is only called from within its file.

**Action:** Mark it `static`, keep it out of the header, and name it for what
it does — not where it lives.

**Why:** `static` is C's `private`. The prefix identifies *exported* names, so
a prefix on a static one is a lie that makes the file's public surface
unreadable.

### Rule 5.4: Never hand-copy an `extern` declaration

**Trigger:** You need a function from another file and you are about to write
`extern <sig>;` locally instead of including a header.

**Action:** Put the declaration in a header and include it. If there is no
appropriate header, that is the thing to fix.

**Why:** This is the highest-consequence style rule in the guide, because it is
how wrong signatures enter a codebase — C links them happily, and the corruption
surfaces far away. A real one: an ordinal implemented 2-argument when the real
entry point is 3-argument; the shim false-zeroed on timeout and sent
`PrfEnterSem` into an infinite retry, which is why a wait-clock never went away.
The same class killed four more ordinal rows whose stack-cleanup byte count was
wrong. And the compiler already catches this — turn on
`-Werror=implicit-function-declaration` and
`-Werror=builtin-declaration-mismatch`, so the bug class is fatal while the
merely-untidy warnings stay advisory.

### Rule 5.5: Headers declare; three kinds are legitimate

**Trigger:** You are about to create a header, or put a function body in one.

**Action:** Headers hold type definitions, `#define`s, and `extern`
declarations — no function bodies (except genuinely tiny `static inline`), no
non-`extern` variable definitions, always an include guard (`FILENAME_H`, and
keep it 100% consistent).

Three header shapes are all correct, and only the first is the classic:

1. **A `.c` file's interface** — `foo.h` declares `foo.c`'s `foo_*` functions.
2. **A pure ABI/type header with no `.c` at all** — an `os2types.h`, an
   `os2api.h`, a `gradd.h`. These are transcriptions of OS/2 layouts; there is
   nothing to implement.
3. **A framework-internal header** serving several files of one subsystem.

**Why:** The 1:1 rule is good advice for your own modules and simply wrong for
the other two categories. Applying it mechanically would flag most of an OS/2
tree, which is how a guide teaches people to ignore it.

---

## Section 6 — Helpers and reuse

### Rule 6.1: Build the missing primitive

**Trigger:** Your task would be easy if C had something it doesn't, and you are
about to work around the gap inline.

**Action:** Build the primitive once, in a shared place, and use it
everywhere. Check first — a mature OS/2 codebase usually already has a layer of
them (a VFS wrapper, semaphore helpers, a debug macro, a tiled allocator).

**Why:** C's standard library is small, and every serious C project needs a
layer of its own primitives. The choice is between building that layer once and
reinventing it badly at every call site forever. Note the failure mode to avoid:
a trap-handler file containing exactly the async-signal-safe primitives the rest
of the tree needs — `safe_write()`, `format_hex32()`, `format_hex16()` — trapped
as `static`, which is why other paths reinvented them. A primitive nobody can
reach is not a primitive.

### Rule 6.2: No unbounded copies, and always terminate

**Trigger:** You are copying a string.

**Action:** Use a bounded copy, and make sure the result is terminated.
`snprintf(dst, sizeof(dst), "%s", src)` has the right semantics **where libc is
available**. `strcpy`/`sprintf`/`gets` never are.

Note the trap: `strncpy(dst, src, sizeof(dst))` does **not** terminate when the
source fills the buffer. If you use `strncpy`, the size argument is
`sizeof(dst) - 1` and the buffer must start zeroed — or use something else.

**Why:** Two independent reasons, which is usually how you know a rule is real.
It is a genuine bug class: a non-terminated buffer feeding a `for (p = buf; *p;
p++)` loop runs off the end. And it is the first thing a hostile reader greps
for — `strcpy` in a public repo is a free headline, and arguing about context
after the fact never works.

**But do not reach for `snprintf` reflexively.** In trap handlers, thunk paths,
and anything running on a small (8–64 KB) OS/2 stack, libc is not available or
not safe: `snprintf` is not async-signal-safe, and glibc's `vfprintf` has a
stack footprint you cannot afford. That is why such code hand-rolls its
formatting. In those contexts, the answer is Rule 6.1 — the primitive — not the
libc call.

### Rule 6.3: The third instance is a helper

**Trigger:** You are about to write the same 4+ line block for the third time.

**Action:** Extract a helper and migrate all three call sites in the same
change.

**Why:** Two could be coincidence; three is a pattern. Waiting for the tenth
means nine call sites you will not migrate.

### Rule 6.4: Migrate the call sites in the same change

**Trigger:** You just wrote a helper that replaces an inline pattern.

**Action:** Grep for the pattern and migrate every occurrence now.

**Why:** A helper nobody calls is dead code, and the duplication you meant to
remove quietly survives. This is the most common refactoring failure in
long-lived C.

### Rule 6.5: Multiple return values use out-pointers

**Trigger:** You need to return more than one value.

**Action:** Return the status normally (for OS/2 API surfaces: `APIRET`/
`uint32_t`, 0 = success, non-zero = `ERROR_*`) and use out-pointers for the
rest, after the inputs, named for their role (`out_id`, `pcbActual`).

**Why:** Out-pointers have no ownership ambiguity and let the caller keep the
result on the stack. Wrapper structs leak allocation decisions into return
types.

> **Convention note.** Pick one return-type convention for OS/2 API surfaces and
> hold it. One that works: bare `uint32_t` with the original IBM prototype in a
> comment above the function —
> ```c
> // APIRET APIENTRY DosRead(HFILE hFile, PVOID pBuffer, ULONG cbRead, PULONG pcbActual);
> ```
> — with framework functions that are *not* OS/2 APIs using `int` and 0/-1.
> Whatever you pick, don't have a second convention that is "defined but unused"
> and don't start using it in one file.

---

## Section 7 — Tables

### Rule 7.1: Three or more cases sharing a signature is a table

**Trigger:** You are about to write a `switch` or `if/else` ladder with 3+
cases that share a signature — handlers, ordinals, commands, devices.

**Action:** Define a `static const` table whose rows carry the discriminator,
the function pointer, and any per-case metadata. Write one small dispatcher
that walks it.

**Why:** A switch couples dispatch to behaviour; a table separates them, so
cross-cutting behaviour is one edit and growth is one row. In OS/2 work there is
a second reason that matters more: **the table is the specification.** Seven
hundred rows of `{ordinal, func, name, type, arg_bytes}` *is* the DOSCALLS ABI,
in a form you can read, diff against IBM's headers, and generate documentation
from. The same knowledge spread across 45 `switch` statements is the same facts
in a form nobody can ever check. Prefer the shape that reads out as a
specification.

Note the row carrying `name` "for debugging" — the table then answers `_name()`
queries for free rather than needing a parallel list (Rule 7.4).

### Rule 7.2: Function pointers are polymorphism

**Trigger:** You have N kinds of thing that share an interface and differ in
behaviour.

**Action:** Make the interface a struct of function pointers and each kind an
instance:

```c
static const vdev_ops_t nul_ops = {
    .name = "NUL", .type = VDEV_TYPE_NUL, .ioctl_category = 0,
    .open = nul_open, .close = nul_close, .ioctl = nul_ioctl,
    .read = nul_read, .write = nul_write
};
```

**Why:** This is C's vtable — zero runtime cost, and new types need no change
to the core dispatch. Use a tagged union and a switch only when the variants
differ in *data shape*, not just behaviour.

### Rule 7.3: A constant→string or cascading-unit chain is a lookup table

**Trigger:** You are writing `if (x == K1) ... else if (x == K2) ...` mapping
constants to strings, or a cascade of `if (n > UNIT)` blocks.

**Action:** Define a `{key, name}` (or `{divisor, suffix}`) array and loop.
Use designated indices where the space is dense:

```c
static const char *trap_names[] = { /* ... */ [0x0D] = "General Protection Fault", /* ... */ };
```

**Why:** Cascades multiply combinatorially when a second axis appears; tables
grow by a nested loop.

### Rule 7.4: Every enum gets a `_name()`

**Trigger:** You just defined an enum or a family of `#define`s whose values get
logged.

**Action:** Write `<type>_name(value)` returning the symbolic name, from a
table, with a fallback — including the bounds check and an `"Unknown …"`
default. Converge on one naming shape and keep it.

**Why:** `"got packet 27 in state 4"` tells you nothing without grepping
headers. `"got PACKET_AUTHENTICATE in STATE_LOGIN"` tells you everything. The
cost is one table and five lines, once, and it pays back on every log line
forever.

---

## Section 8 — Logging and debug

### Rule 8.1: Pick the channel by context, not by preference

**Trigger:** You want to emit a debug message.

**Action:** In ordinary application code, one logger is fine. In low-level work
there are three channels and the context forces the choice:

| Context | Channel |
|---|---|
| Normal code: real stack, valid TLS, transport up | the rich logger (`ldebug()`) |
| Signal / trap handler | an async-signal-safe raw sender |
| Thunk / foreign stack / register-critical | raw `write(2, ...)`, preformatted, no libc |

**Why:** The rich logger is the right default and the wrong tool in the hardest
places. It typically needs `__thread` TLS, a real stack, and a live transport —
and in 16-bit thunk context the segment registers belong to other code and none
of that holds. Raw `write(2)` calls in those paths are not laziness; they are
the only thing that works when everything else is on fire. **Do not "clean them
up" into a rich logger.** (For the app-level debug loop, see
`recipes/debugging-an-app.md`.)

### Rule 8.2: `MODULE_NAME` carries the tag; don't wrap the logger

**Trigger:** You are adding debug output to a file.

**Action:** Define `MODULE_NAME` before including the debug header, then call
the logger directly:

```c
#define MODULE_NAME "vfs"
#include "os2debug.h"
```

Do not define a per-file alias (`FOO_LOG`) that only renames `ldebug` —
`MODULE_NAME` already tags the line. A wrapper is only worth it if it adds
something real, such as a second runtime flag gating a noisy subsystem.

**Why:** The logger already injects module, file, and function via
`MODULE_NAME`/`__FILE__`/`__func__`, so nothing needs passing by hand and
nothing goes stale when a function is renamed. Aliases that add nothing just
make the tree harder to grep.

### Rule 8.3: Context you can compute, never type

**Trigger:** You are about to type a function name, file, or line into a
message.

**Action:** Let the macro inject it — `__func__`, `__FILE__`, `__LINE__`.

**Why:** Hand-typed context is stale the moment anyone renames a function or
inserts a line above the call.

---

## Section 9 — The meta-rule

### Rule 9.1: One extra pass, before you move on

**Trigger:** You just finished a change.

**Action:** Re-read it and ask:

- Did I add a constant without a name and a cited source?
- Did I write down where a fact came from — and what *kind* of source it was?
- Is there anything here I "just knew"?
- **Did I learn anything that isn't written down yet — including something
  that turned out to be absent, or an idea that didn't work?**
- **Did I delete a claim I should have marked wrong instead?**
- If I touched an ABI struct, does it assert its size?
- Did I make anything succeed that did not actually happen?
- Did I route around a guard instead of reporting it?
- Whose memory did I write through?
- Did I leave something weird without its reason?
- Did I hand-copy an `extern`?
- Did I reinvent a primitive that already exists?

Fix it now, while the code is fresh.

**Why:** Every codebase that ages well does this on every change; every one
that ages badly defers it forever. The compiler checks almost none of it. There
is no other forcing function.

---

## Closing

The rules above come down to four habits.

**Say where facts came from.** OS/2 code is a pile of facts about someone
else's operating system held together by C. A fact with a source can be
checked, re-derived, and trusted by a reader who has never met you. A fact
without one is a guess that will be believed.

**Write down what you learn.** The code is the cheap part; the knowledge —
bought a KDB session and a disassembly at a time — is the expensive part. Record
it, keep the artifacts, and include the results that produced no code: the
search that came back empty, the theory that was refuted, the claim that turned
out wrong. Work that isn't recorded gets done twice, and the second person has
no way of knowing.

**Fail honestly.** You are working against a system whose behaviour you do not
fully know. The only thing worse than not knowing is pretending. A fatal stub is
the code declining to lie about what works.

**Explain the strange parts.** Most of what looks wrong in good OS/2 C is
load-bearing. The reason costs one line, and it is the difference between a
codebase that looks reckless and one that is obviously deliberate.

None of this is enforced by the compiler, which is the whole reason the guide
exists. C assumes the programmer enforces it. Most C code does not, and rots.
The payoff for doing it compounds — and in a project whose product is hard-won
knowledge about someone else's operating system, it compounds faster than usual.
