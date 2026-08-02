# REXX - the SAA Application Programming Interface

REXX (the REstructured eXtended eXecutor) is OS/2's built-in procedures language, and it ships
with a C-callable programming interface - the **SAA** (Systems Application Architecture) API,
declared in `rexxsaa.h` - that lets a compiled application do two complementary things: **embed**
the interpreter (run a REXX program from inside a C program and exchange data with it) and
**extend** it (contribute native routines the REXX program can call, and interpose on the
interpreter's behaviour). The interpreter itself lives in a DLL (`REXX`/`REXXAPI`), is fully
re-entrant, and supports REXX procedures running on multiple threads of one process.

Everything crosses the boundary as an **`RXSTRING`** - a length-plus-pointer descriptor for a
byte string that is content-insensitive (may contain embedded nulls) with a theoretical maximum
length of 4 GB. There are four extension surfaces, all sharing the same registration model (a
named handler, packaged in an EXE or a DLL, registered before use): **subcommand handlers** (the
target of the REXX `ADDRESS` instruction / a "host command environment"), **external functions**
(routines the REXX program calls by name, entered in the *Available Function Table*, AFT),
**system exits** (callbacks that interpose on interpreter events - I/O, function/command
dispatch, queue access, halt/trace polling, init/termination), and the **variable pool**
(`RexxVariablePool`, by which native code reads and writes the running procedure's REXX
variables). A program embeds the interpreter with the single entry point **`RexxStart`**.

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 header
`rexxsaa.h` (all prototypes, the `RXSTRING` / `RXSYSEXIT` / `SHVBLOCK` /
`RXFNCCAL_PARM` / `RXCMDHST_PARM` / `RX*_PARM` structures, the handler `typedef`s, and every
constant value cited below - line numbers given per section). **[DOC-IBM]** IBM *Object REXX
Programming Guide* (OS/2), the "REXX Application Programming Interfaces" appendix material -
`RexxStart`, the subcommand / external-function / system-exit / variable-pool interfaces, handler
characteristics, and the `RXSTRING` conventions (behavioural meaning: call types, exit
default/handled/error semantics, `RXSHV_*` request semantics, return-code composition). The
companion IBM *Procedures Language 2/REXX User's Guide* (OS/2 2.0 Technical Library) documents the
language itself; only the API is covered here. All constant *values* were confirmed against
`rexxsaa.h`; where the book and header spellings differ, the header's spelling is authoritative
(e.g. the header field `strlength` precedes `strptr`; see section 2).

---

## 1. Interface map [DOC-IBM - `rexxsaa.h`]

The API is partitioned by `#define INCL_*` include switches, each gating a group of declarations.

| Include switch | Surface | Key entry points |
|---|---|---|
| (always) | Embed the interpreter | `RexxStart` |
| `INCL_RXSUBCOM` | Subcommand (host command) handlers | `RexxRegisterSubcomExe`, `RexxRegisterSubcomDll`, `RexxDeregisterSubcom`, `RexxQuerySubcom` |
| `INCL_RXFUNC` | External functions (AFT) | `RexxRegisterFunctionExe`, `RexxRegisterFunctionDll`, `RexxDeregisterFunction`, `RexxQueryFunction` |
| `INCL_RXSYSEXIT` | System exits + `RXSYSEXIT` list | `RexxRegisterExitExe`, `RexxRegisterExitDll`, `RexxDeregisterExit`, `RexxQueryExit` |
| `INCL_RXSHV` | Variable pool | `RexxVariablePool` (+ `SHVBLOCK`) |
| `INCL_RXMACRO` | Macrospace (pre-tokenized functions) | `RexxAddMacro`, `RexxLoadMacroSpace`, ... |
| `INCL_RXARI` | Asynchronous request (halt/trace) | `RexxSetHalt`, `RexxSetTrace`, ... |

`INCL_REXXSAA` enables the six sub-switches `RXSUBCOM`, `RXSHV`, `RXFUNC`, `RXSYSEXIT`, `RXMACRO`,
`RXARI` (`rexxsaa.h:55-62`); the external-data-queue (`RXQUEUE`) API is a separate surface, not
declared in `rexxsaa.h`. The three extension surfaces plus the
variable pool are the model this reference covers; the queue, macrospace, and async surfaces are
noted for completeness but not detailed.

All entry points use **`APIENTRY`** linkage (the OS/2 `_System` convention) and, being SAA names,
carry no library prefix - they are spelled exactly as IBM defines them. Each has an uppercase
alias macro (`REXXSTART`, `REXXVARIABLEPOOL`, ...) for languages that fold case.

---

## 2. `RXSTRING` - the string descriptor  [DOC-IBM - `rexxsaa.h:65-95`]

Every string that crosses the API is described by an `RXSTRING`:

```c
typedef struct _RXSTRING {   /* rxstr */
    ULONG  strlength;        /* length of string  (bytes)      */
    PCH    strptr;           /* pointer to string              */
} RXSTRING;
typedef RXSTRING *PRXSTRING;
```

An `RXSTRING` is a flat-model, content-insensitive byte string: `strlength` is the exact byte
count and the data may contain embedded null bytes, so the length - not a terminator - is
authoritative. An `RXSTRING` is in one of three states, distinguished by macros:

| State | Condition | Macro (`rexxsaa.h:90-92`) | Meaning |
|---|---|---|---|
| **Empty / null** | `strptr == NULL` | `RXNULLSTRING(r)` -> TRUE | no value at all (e.g. an omitted argument, or "no result returned") |
| **Zero-length** | `strptr != NULL && strlength == 0` | `RXZEROLENSTRING(r)` -> TRUE | the REXX null string `""` |
| **Valued** | `strptr != NULL && strlength != 0` | `RXVALIDSTRING(r)` -> TRUE | a normal non-empty value |

Note the distinction the two non-null cases draw: a **NULL `strptr`** means "there is no string",
whereas a non-NULL `strptr` with `strlength == 0` is the genuine empty string `""`.

Other macros (`rexxsaa.h:93-95`): `RXSTRLEN(r)` yields 0 for a null string else `strlength`;
`RXSTRPTR(r)` yields the pointer; and `MAKERXSTRING(r,p,l)` populates both fields in one
statement - the idiomatic way to build an argument or a default result buffer.

**Interpreter-side conventions the handler must rely on:**

- **When the interpreter passes an `RXSTRING` *into* a handler** (subcommand command string,
  external-function argument, most exit parameters), it appends a null byte just past the data as
  a convenience, so C string functions can be used *when nulls are not expected* - but that null
  is **not** counted in `strlength`, and the data itself may contain nulls, so length remains the
  authority.
- **When a handler returns an `RXSTRING`** (a subcommand `RC` string, a function result, an exit
  result), the interpreter provides a **default 256-byte buffer**. If the result fits, the
  handler copies into that buffer and sets `strlength`. If it does not fit, the handler allocates
  a new buffer with `DosAllocMem`, points `strptr` at it, and sets `strlength`; **the interpreter
  then frees that storage with `DosFreeMem`** on the handler's behalf. (`RXAUTOBUFLEN` = 256,
  `rexxsaa.h:74`.)

---

## 3. Embedding the interpreter - `RexxStart`  [DOC-IBM - `rexxsaa.h:316-338`]

```c
LONG APIENTRY RexxStart(
    LONG        ArgCount,     /* number of RXSTRINGs in ArgList          */
    PRXSTRING   ArgList,      /* argument array (== the ARG() the REXX sees) */
    PSZ         ProgramName,  /* ASCIIZ procedure name / PARSE SOURCE name */
    PRXSTRING   Instore,      /* NULL = load from disk; else in-storage  */
    PSZ         EnvName,      /* ASCIIZ initial ADDRESS environment      */
    LONG        CallType,     /* RXCOMMAND | RXSUBROUTINE | RXFUNCTION    */
    PRXSYSEXIT  Exits,        /* array of RXSYSEXIT, RXENDLST-terminated; or NULL */
    PSHORT      ReturnCode,   /* out: integer form of the result, if numeric */
    PRXSTRING   Result);      /* out: the RETURN/EXIT string             */
```

`RexxStart` runs one REXX procedure to completion and returns.

- **`ArgCount` / `ArgList`** - the arguments visible to the procedure through `ARG()`. `ArgCount`
  counts omitted arguments too; an omitted argument is a null `RXSTRING` (`strptr == NULL`).
- **`ProgramName`** - when loading from disk (`Instore == NULL`), at minimum the file name
  (drive/path/extension optional; default extension `.CMD`, then the usual current-directory ->
  `PATH` search). When running from storage or the macrospace, this is instead the name reported
  by `PARSE SOURCE`.
- **`CallType`** (`rexxsaa.h:100-102`) selects the invocation model and the `PARSE SOURCE` second
  token:

  | Constant | Value | Meaning | `PARSE SOURCE` token |
  |---|---|---|---|
  | `RXCOMMAND` | 0 | a system/application command; usually a single argument string | `COMMAND` |
  | `RXSUBROUTINE` | 1 | a subroutine; may take multiple arguments, need not return a result | `SUBROUTINE` |
  | `RXFUNCTION` | 2 | a function; may take multiple arguments, **must** return a result | `FUNCTION` |

- **`EnvName`** - the initial `ADDRESS` host-command environment (a registered subcommand handler
  name; <= 250 chars). If NULL, the file extension is used.
- **`Exits`** - an array of `RXSYSEXIT` descriptors terminated by an `RXENDLST` code, enabling
  system exits for this run (section 6); NULL if none.
- **`ReturnCode`** - if the returned result is a whole number in the 16-bit signed range, its
  integer value is also delivered here.
- **`Result`** - receives the procedure's `RETURN`/`EXIT` string. The caller may supply a default
  buffer (via `MAKERXSTRING`); if absent or too small, the interpreter allocates one with
  `DosAllocMem` and the **caller must free it with `DosFreeMem`**. No terminating null is added.

### The in-storage form - `Instore`

`Instore` is an array of **two** `RXSTRING`s that lets a program run a procedure from memory and
cache its tokenized ("translated") image:

- `Instore[0]` - a buffer holding the REXX **source** (an exact image of a disk `.CMD`, complete
  with CR/LF and EOF), used for `SOURCELINE`.
- `Instore[1]` - the **translated image**. If empty on entry, the interpreter fills it in on
  completion so subsequent `RexxStart` calls can rerun the tokenized form directly (source in
  `[0]` then needed only for `SOURCELINE`). The translated-image format is *not* a programming
  interface - it is interpreter-version-specific and must not be persisted or moved between
  systems; the caller frees `Instore[1]` with `DosFreeMem`.

If both `strptr` fields are NULL, the interpreter looks the procedure up in the **macrospace** by
`ProgramName`. If `Instore` is NULL, the procedure is loaded from disk.

### Return value  [DOC-IBM]

`RexxStart` returns a `LONG`: **0** = ran normally; **negative** = a REXX interpreter error (the
negated REXX error number; e.g. -3 = "Program is unreadable", returned when a macrospace
procedure is not loaded); **positive** = a system error locating or loading the interpreter DLL
(the return codes of `DosLoadModule` / `DosQueryProcAddr`).

---

## 4. Subcommand (host command) handlers  [`INCL_RXSUBCOM`]

A subcommand handler is the target of the REXX `ADDRESS` instruction - the "host command
environment" a REXX program sends commands to. It is registered under an environment name, then
named as `RexxStart`'s `EnvName` or via `ADDRESS`.

### The handler ABI  [DOC-IBM - `rexxsaa.h:349-351`]

```c
typedef ULONG APIENTRY RexxSubcomHandler(
    PRXSTRING Command,   /* the command string (null-terminated RXSTRING) */
    PUSHORT   Flags,     /* out: completion status (RXSUBCOM_OK/ERROR/FAILURE) */
    PRXSTRING Retstr);   /* out: RC string returned to REXX               */
```

The handler receives the issued `Command`, does the work, and sets `*Flags` to one of
(`rexxsaa.h:116-118`):

| Flag | Value | Effect in REXX |
|---|---|---|
| `RXSUBCOM_OK` | `0` | normal completion; procedure continues |
| `RXSUBCOM_ERROR` | `0x01` | raise the `ERROR` condition (traps `SIGNAL/CALL ON ERROR`; `TRACE ERRORS`) |
| `RXSUBCOM_FAILURE` | `0x02` | raise the `FAILURE` condition (traps `SIGNAL/CALL ON FAILURE`); typical for unknown commands |

(`RXSUBCOM_OK` = 0 is the "function complete" value; the header also defines the *query* flag
`RXSUBCOM_ISREG` = `0x01`, distinct from the handler-completion flags above.) The `Retstr` string
is assigned to the REXX special variable **`RC`**; an empty `Retstr`
(NULL `strptr`) makes `RC` = `"0"`. The default `Retstr` buffer is 256 bytes (section 2 allocation rule
applies).

### Registration  [DOC-IBM - `rexxsaa.h:357-388`]

```c
APIRET APIENTRY RexxRegisterSubcomExe(PSZ EnvName, PFN EntryPoint, PUCHAR UserArea);
APIRET APIENTRY RexxRegisterSubcomDll(PSZ EnvName, PSZ ModuleName, PSZ ProcName,
                                      PUCHAR UserArea, ULONG DropAuth);
```

- **Exe** registration takes the in-process entry-point address; the handler is **local to the
  registering process** (only REXX programs in that process can reach it).
- **Dll** registration names the DLL and exported routine; the handler is **global to the
  system** (any process's REXX program can address it).
- `UserArea` is an optional 8-byte cookie stored with the registration and retrievable via
  `RexxQuerySubcom`; NULL if unused.
- `DropAuth` (Dll form) is the drop authority: `RXSUBCOM_DROPPABLE` (0) = any process may drop it;
  `RXSUBCOM_NONDROP` (1) = only a process with the registrant's PID may drop it
  (`rexxsaa.h:110-111`).

`RexxDeregisterSubcom` drops a registration; `RexxQuerySubcom` reports whether an environment is
registered (`RXSUBCOM_OK` = registered, `RXSUBCOM_NOTREG` = not) and returns the saved `UserArea`.

### Registration return codes  [DOC-IBM - `rexxsaa.h:116-131`]

`0` `RXSUBCOM_OK`, `10` `RXSUBCOM_DUP` (a same-named handler exists elsewhere; **not an error** -
registration still succeeded), `20` `RXSUBCOM_MAXREG` (too many handlers), `30` `RXSUBCOM_NOTREG`
, `40` `RXSUBCOM_NOCANDROP`, `50` `RXSUBCOM_LOADERR`, `127` `RXSUBCOM_NOPROC` ,
`1001` `RXSUBCOM_BADENTRY`, `1002` `RXSUBCOM_NOEMEM`, `1003` `RXSUBCOM_BADTYPE` ,
`1004` `RXSUBCOM_NOTINIT`.

---

## 5. External functions - the Available Function Table  [`INCL_RXFUNC`]

An external function is a native routine a REXX program calls **by name**, either as a function
(`x = MYFUNC(a,b)`) or with the `CALL` instruction. Registering it enters it in the interpreter's
**Available Function Table (AFT)**.

### The handler ABI  [DOC-IBM - `rexxsaa.h:454-458`]

```c
typedef ULONG APIENTRY RexxFunctionHandler(
    PUCHAR    Name,       /* ASCIIZ name used to call the function */
    ULONG     Argc,       /* number of argument RXSTRINGs          */
    PRXSTRING Argv,       /* array of Argc argument RXSTRINGs       */
    PSZ       Queuename,  /* current external data queue name       */
    PRXSTRING Retstr);    /* out: result string                    */
```

The handler reads its `Argc` arguments from `Argv` (each a null-terminated `RXSTRING`; an omitted
trailing argument is a null `RXSTRING`) and returns its value in `Retstr` (default 256-byte
buffer, section 2 allocation rule). Its **`ULONG` return value** is the outcome:

- **0** - success; `Retstr` holds the result. When called as a function the value is used in the
  expression; when called via `CALL` it is assigned to the special variable `RESULT`.
- **non-zero** - the interpreter raises REXX **error 40** ("Incorrect call to routine") and
  ignores `Retstr`.
- If the routine has **no** value to return, it sets `Retstr` to an empty `RXSTRING` (NULL
  `strptr`): called as a function this raises **error 44** ("Function or message did not return data");
  called via `CALL` it simply drops `RESULT`.

### Registration  [DOC-IBM - `rexxsaa.h:463-487`]

```c
APIRET APIENTRY RexxRegisterFunctionExe(PSZ FuncName, PFN EntryPoint);
APIRET APIENTRY RexxRegisterFunctionDll(PSZ FuncName, PSZ ModuleName, PSZ EntryPoint);
```

- **Exe** functions are **local to the registering process**; the same name may be registered
  independently by different processes.
- **Dll** functions are **available to all processes**; a given function name may not be
  duplicated across DLLs. The two registration-type identifiers are `RXFUNC_DYNALINK` (1) and
  `RXFUNC_CALLENTRY` (2) (`rexxsaa.h:186-187`).

`RexxDeregisterFunction` removes a name from the AFT; `RexxQueryFunction` reports whether a name is
present (`RXFUNC_OK` present, `RXFUNC_NOTREG` absent).

### Return codes  [DOC-IBM - `rexxsaa.h:193-200`]

`0` `RXFUNC_OK`, `10` `RXFUNC_DEFINED` (name already registered), `20` `RXFUNC_NOMEM` ,
`30` `RXFUNC_NOTREG`, `40` `RXFUNC_MODNOTFND` (DLL not found), `50` `RXFUNC_ENTNOTFND` (entry
point not found), `60` `RXFUNC_NOTINIT`, `70` `RXFUNC_BADTYPE`.

---

## 6. System exits  [`INCL_RXSYSEXIT`]

A system exit is a callback that **interposes** on an interpreter event, letting an embedding
application customize the REXX environment - redirect I/O, take over function/command dispatch,
supply a queue, poll halt/trace, or hook init/termination. Exits are registered by name like the
other handlers, then **enabled per-run** through `RexxStart`'s `Exits` array.

### Enabling exits - `RXSYSEXIT`  [DOC-IBM - `rexxsaa.h:79-84`]

```c
typedef struct _RXSYSEXIT {   /* syse */
    PSZ   sysexit_name;       /* ASCIIZ name of a registered exit handler */
    LONG  sysexit_code;       /* which exit (RXFNC, RXCMD, RXSIO, ...)      */
} RXSYSEXIT;
```

The `Exits` array pairs a handler name with the major exit code it services; an entry whose code
is **`RXENDLST` (0)** marks the end of the list. One handler may service several codes (repeat its
name with different codes).

### The exit-handler ABI  [DOC-IBM - `rexxsaa.h:688-690`]

```c
typedef LONG APIENTRY RexxExitHandler(
    LONG  ExitNumber,    /* major function code (RXFNC/RXCMD/RXMSQ/RXSIO/...) */
    LONG  Subfunction,   /* subfunction code (RXFNCCAL, RXSIOSAY, ...)        */
    PEXIT ParmBlock);    /* subfunction-specific parameter block (PUCHAR)   */
```

`PEXIT` is `PUCHAR` (`rexxsaa.h:269`); the handler casts it to the subfunction's `*_PARM` struct.
Some subfunctions have no parameters, in which case `ParmBlock` is NULL. The handler's `LONG`
return signals one of three actions (`rexxsaa.h:215-217`):

| Return | Value | Meaning |
|---|---|---|
| `RXEXIT_HANDLED` | 0 | the exit did the work (and filled in the parameter block); the interpreter does not perform its default |
| `RXEXIT_NOT_HANDLED` | 1 | the exit declined; the interpreter proceeds as if no exit were registered |
| `RXEXIT_RAISE_ERROR` | -1 | fatal error in the exit; the interpreter raises REXX error 48 ("Failure in system service") |

### The exit codes and their subfunctions  [DOC-IBM - `rexxsaa.h:242-267`]

| Major code | Value | Purpose | Subfunctions (subcode) |
|---|---|---|---|
| `RXFNC` | 2 | external function/subroutine dispatch | `RXFNCCAL` (1) |
| `RXCMD` | 3 | host-command (subcommand) dispatch | `RXCMDHST` (1) |
| `RXMSQ` | 4 | external data queue | `RXMSQPLL` (1) pull, `RXMSQPSH` (2) push, `RXMSQSIZ` (3) size, `RXMSQNAM` (20) set name |
| `RXSIO` | 5 | standard I/O | `RXSIOSAY` (1) `SAY`, `RXSIOTRC` (2) trace/error out, `RXSIOTRD` (3) `PULL` read, `RXSIODTR` (4) debug read, `RXSIOTLL` (5) linelength (N/A on OS/2) |
| `RXHLT` | 7 | halt polling | `RXHLTCLR` (1), `RXHLTTST` (2) |
| `RXTRC` | 8 | external trace polling | `RXTRCTST` (1) |
| `RXINI` | 9 | initialization (last init step) | `RXINIEXT` (1) |
| `RXTER` | 10 | termination (first term step) | `RXTEREXT` (1) |

(`RXENDLST` = 0 list terminator; `RXNOOFEXITS` = 11 is one past the largest code.) `RXHLT` and
`RXTRC` are called after every REXX instruction, so enabling them slows execution - the async
`RexxSetHalt` / `RexxSetTrace` functions avoid between-instruction polling.

### Representative parameter blocks  [DOC-IBM - `rexxsaa.h:542-660`]

**`RXFNCCAL_PARM`** (external-function dispatch, `RXFNC`/`RXFNCCAL`, `rexxsaa.h:542-554`) - packed:

```c
typedef struct _RXFNCCAL_PARM {
    RXFNC_FLAGS rxfnc_flags;   /* bitfield: rxfferr, rxffnfnd, rxffsub */
    PUCHAR      rxfnc_name;    USHORT rxfnc_namel;   /* function name + len */
    PUCHAR      rxfnc_que;     USHORT rxfnc_quel;    /* current queue + len */
    USHORT      rxfnc_argc;    PRXSTRING rxfnc_argv; /* argument array       */
    RXSTRING    rxfnc_retc;    /* return value the exit fills in            */
} RXFNCCAL_PARM;
```

The flags (`rexxsaa.h:532-539`) are set by the handler on return: `rxffsub` is TRUE on entry if
the routine was invoked via `CALL` (result optional) rather than as a function (result required);
the handler sets `rxffnfnd` if it could not locate the function (-> error 43, "Routine not found")
or `rxfferr` if the function ran but failed (-> error 40). Absent a result for a function call, the
interpreter raises error 44.

**`RXCMDHST_PARM`** (subcommand dispatch, `RXCMD`/`RXCMDHST`, `rexxsaa.h:569-580`) - packed;
carries `rxcmd_flags` (`rxfcfail`/`rxfcerr` -> raise `FAILURE`/`ERROR`), the current `ADDRESS`
name (`rxcmd_address`/`rxcmd_addressl`) and DLL (`rxcmd_dll`/`rxcmd_dll_len`, 0 => EXE), the issued
`rxcmd_command` string, and `rxcmd_retc` (the `RC` value).

**`RXSIO*_PARM`** (standard I/O, `rexxsaa.h:637-660`) - each a single `RXSTRING`:
`RXSIOSAY_PARM.rxsio_string` / `RXSIOTRC_PARM.rxsio_string` carry the line to write (any length -
the exit truncates/splits as needed); `RXSIOTRD_PARM.rxsiotrd_retc` / `RXSIODTR_PARM.rxsiodtr_retc`
receive the line the exit read back. When an `RXSIO` exit returns `RXEXIT_NOT_HANDLED`, the
interpreter performs the default (`SAY`->STDOUT, trace->`.ERROR`, read<-STDIN); `RXEXIT_HANDLED`
suppresses it.

**`RXMSQ*_PARM`** - `RXMSQPSH_PARM` carries `rxmsq_flags.rxfmlifo` (LIFO vs FIFO) and the pushed
`rxmsq_value`; `RXMSQPLL_PARM.rxmsq_retc` returns a pulled line; `RXMSQSIZ_PARM.rxmsq_size`
returns the queue depth; `RXMSQNAM_PARM.rxmsq_name` sets the active queue name.

### Registration  [DOC-IBM - `rexxsaa.h:695-725`]

```c
APIRET APIENTRY RexxRegisterExitExe(PSZ ExitName, PFN EntryPoint, PUCHAR UserArea);
APIRET APIENTRY RexxRegisterExitDll(PSZ ExitName, PSZ ModuleName, PSZ ProcName,
                                    PUCHAR UserArea, ULONG DropAuth);
```

Exe/Dll scoping, the 8-byte `UserArea`, and the drop-authority values (`RXEXIT_DROPPABLE` 0 /
`RXEXIT_NONDROP` 1, `rexxsaa.h:208-209`) mirror the subcommand model exactly.
`RexxDeregisterExit` / `RexxQueryExit` complete the set. Return codes parallel the subcommand set:
`0` `RXEXIT_OK`, `10` `RXEXIT_DUP` (not an error), `20` `RXEXIT_MAXREG`, `30` `RXEXIT_NOTREG` ,
`40` `RXEXIT_NOCANDROP`, `50` `RXEXIT_LOADERR`, `127` `RXEXIT_NOPROC`, `1001-1004`
`RXEXIT_BADENTRY`/`NOEMEM`/`BADTYPE`/`NOTINIT` (`rexxsaa.h:221-236`).

---

## 7. The variable pool - `RexxVariablePool`  [`INCL_RXSHV`]

The variable pool interface lets native code read, write, drop, and enumerate the variables of
the **currently active** REXX procedure. It is available from subcommand handlers, external
functions, and exit handlers - and **only from the same thread that called `RexxStart`** (a new
thread, or an EXE spawned as a separate process, cannot use it).

### `SHVBLOCK` - the shared-variable request block  [DOC-IBM - `rexxsaa.h:167-177`]

```c
typedef struct _SHVBLOCK {   /* shvb */
    struct _SHVBLOCK *shvnext;      /* next request in the chain (NULL = last) */
    RXSTRING          shvname;      /* variable name                           */
    RXSTRING          shvvalue;     /* variable value                          */
    ULONG             shvnamelen;   /* size of the name buffer                 */
    ULONG             shvvaluelen;  /* size of the value buffer                */
    UCHAR             shvcode;      /* request code (RXSHV_*)                  */
    UCHAR             shvret;       /* per-request return flags (RXSHV_*)      */
} SHVBLOCK;
```

```c
APIRET APIENTRY RexxVariablePool(PSHVBLOCK RequestBlockList);
```

`RexxVariablePool` takes a **linked list** of `SHVBLOCK`s (chained by `shvnext`) and processes
each in order, stopping after the last or on a severe error (e.g. out of memory). Each block is one
operation, selected by `shvcode`.

### Request codes  [DOC-IBM - `rexxsaa.h:140-148`]

| `shvcode` | Value | Operation | Name interpretation |
|---|---|---|---|
| `RXSHV_SET` | 0x00 | set variable = `shvvalue` | **direct** (no substitution/case-folding) |
| `RXSHV_FETCH` | 0x01 | copy variable value into `shvvalue` | direct |
| `RXSHV_DROPV` | 0x02 | drop (unassign) the variable | direct |
| `RXSHV_SYSET` | 0x03 | set | **symbolic** (normal REXX rules: case, tail substitution) |
| `RXSHV_SYFET` | 0x04 | fetch | symbolic |
| `RXSHV_SYDRO` | 0x05 | drop | symbolic |
| `RXSHV_NEXTV` | 0x06 | fetch "next" variable (enumerate) | returns both name and value |
| `RXSHV_PRIV` | 0x07 | fetch private interpreter info by name | see below |
| `RXSHV_EXIT` | 0x08 | set the function/exit return value | name unused |

The **symbolic** interface (`SY*`) applies ordinary REXX symbol rules, including compound-symbol
tail substitution; the **direct** interface performs no substitution or case translation and
requires already-valid REXX variable names (simple, or a fully derived compound name). Enumeration
via `RXSHV_NEXTV` walks the current variable generation (excluding names hidden by `PROCEDURE`) in
no defined order; the interpreter resets its internal cursor whenever a set/fetch/drop request runs
or control returns to it, and sets `RXSHV_LVAR` when no variables remain.

`RXSHV_PRIV` retrieves interpreter state by placing a keyword in `shvname`: `PARM` (argument count),
`PARM.n` (the nth argument string), `QUENAME` (current queue), `SOURCE` and `VERSION` (the `PARSE
SOURCE`/version strings), and `EXITNAME` (the current exit handler for this thread).

For fetch and enumerate, if the caller passes an **empty** `shvvalue`/`shvname` (`strptr == NULL`),
the interpreter **allocates** the buffer with `DosAllocMem` (no truncation possible, but
`RXSHV_MEMFL` possible) and the caller must free it with `DosFreeMem`; otherwise the caller's
buffer is used and `RXSHV_TRUNC` is flagged if the value/name did not fit. No terminating null is
added to returned names or values.

### Per-request status flags - `shvret`  [DOC-IBM - `rexxsaa.h:156-162`]

`shvret` is a byte of OR-able flags for that one block: `RXSHV_OK` (0x00, all clear) ,
`RXSHV_NEWV` (0x01, the variable was uninitialized), `RXSHV_LVAR` (0x02, no more variables on
`RXSHV_NEXTV`), `RXSHV_TRUNC` (0x04, value/name truncated), `RXSHV_BADN` (0x08, invalid name) ,
`RXSHV_MEMFL` (0x10, out of memory), `RXSHV_BADF` (0x80, invalid function code).

### Return value  [DOC-IBM]

`RexxVariablePool` returns a **composite** code: the **low-order 6 bits** of every block's `shvret`
are ORed together (so a value in 0-127 reflects the aggregate outcome across the whole list; the
individual per-block detail stays in each `shvret`). The distinct value **`RXSHV_NOAVL` (144)**
(`rexxsaa.h:152`) means the variable pool was not enabled when the call was made (e.g. no REXX
procedure active on this thread).

---

## 8. Return-code conventions - summary

- **`RexxStart`** returns a `LONG`: 0 normal, negative = REXX error (negated error number),
  positive = a `DosLoadModule`/`DosQueryProcAddr` system code.
- **Handler ABIs**: subcommand and external-function handlers return `ULONG` (0 = success;
  non-zero from a function -> REXX error 40). Exit handlers return `LONG` chosen from
  `RXEXIT_HANDLED` / `RXEXIT_NOT_HANDLED` / `RXEXIT_RAISE_ERROR`. A subcommand additionally reports
  success/error/failure through its `*Flags` out-parameter, not its return value.
- **Registration/query functions** return `APIRET` from the family-specific set
  (`RXSUBCOM_*` / `RXFUNC_*` / `RXEXIT_*`), where each family shares the pattern *low value = normal
  or benign-duplicate (`*_DUP` = 10 is not an error), mid values = not-registered / can't-drop /
  load / no-proc, and 1001-1004 = bad-entry / no-memory / bad-type / not-initialized*.
- **`RexxVariablePool`** returns the OR-composite of the low 6 bits of all `shvret` fields, or the
  sentinel `RXSHV_NOAVL` (144) when the pool is unavailable.

All values in this section were taken from `rexxsaa.h` at the lines cited in each section above; no
value has been supplied from any other source.

## See also
- `module-dll.md` - how a REXX function/subcommand DLL is packaged and loaded; `file-io.md` - the I/O a native handler typically performs.
