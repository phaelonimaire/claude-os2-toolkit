# OS/2 Profiles (INI Files) — the `Prf*` API

The mechanism an OS/2 application uses to store and retrieve persistent settings. A **profile**
(an *initialization file*, or *INI file*) is a structured binary key/value store organized in
three levels — **application → key → value** — accessed through the `Prf*` family of
Presentation Manager functions. Two profiles always exist, opened by the system at start-up: the
**user profile** (`OS2.INI`) and the **system profile** (`OS2SYS.INI`). An application may also
open profiles of its own. This reference covers the handle type (`HINI`), the model, the read /
write / enumerate / delete calls, the two well-known profile handles, and profile switching
(`PrfReset` / `PrfQueryProfile`).

Provenance: **[DOC-IBM]** the OS/2 Toolkit 4.5 header `pmshl.h` and the base error header
`pmerr.h` — every prototype, constant value, structure, and error value below is transcribed from
them with a `file:line` citation; **[DOC-IBM]** the OS/2 Toolkit 4.5 *Presentation Manager
Programming Reference* (`BOOK/pm1.inf`), from which the behavioural semantics (search, enumeration,
deletion, defaults, return values) are taken. **[DOC]** the EDM2 wiki, used only to cross-check
`PrfCloseProfile`. The `Prf*` functions are declared under `#define INCL_WINSHELLDATA` (or
`INCL_WIN` / `INCL_PM`) before `<os2.h>` [DOC-IBM — pm1.inf, per-function *Syntax* panels].

---

## 1. The profile model [DOC-IBM]

> **Think "registry", not "config file".** `OS2.INI` / `OS2SYS.INI` are the OS/2 equivalent of the
> Windows registry — the system-wide user and system settings store — and `Prf*` is the API for
> reaching them. An application may also create *its own* profile-format file with
> `PrfOpenProfile`. But plain text-style `.ini` files are also common and perfectly ordinary in
> OS/2 applications; those are just files, unrelated to any of this.
>
> **An OS/2 INI is not a Windows/Unix `.ini`.** The name is the only thing they share. There is no
> text, no `[Section]` headers, no `key=value` lines, and nothing to open with `fopen` or hand to a
> config parser — a profile is an **opaque binary database maintained by Presentation Manager**, and
> the `Prf*` API is the only supported way to touch it. Writing one as text corrupts it; parsing one
> as text finds nothing. **This applies to profiles, not to every file called `.ini`** — an
> application's own config file is its own business and may perfectly well be text; only
> `OS2.INI`/`OS2SYS.INI` and files opened with `PrfOpenProfile` are profiles in this sense. Note the
> consequences of a profile being a real database rather than a text file:
> values are **arbitrary binary** up to 64 KB (a struct can be stored directly, no serialization to
> text needed), and application/key names are matched **case-dependently**.

A profile is a binary file with a three-level structure:

- **Application** — a named section (heading). An application name is any ASCIIZ string; names
  beginning with the characters `"PM_"` are reserved for system use.
- **Key** — a named entry within an application. Key names are ASCIIZ strings.
- **Value** — the data associated with an (application, key) pair. The value is arbitrary binary
  data (not necessarily zero-terminated); its length is carried separately. **The maximum size of
  data that can be associated with a key name is 64 KB.**

Both the application name and the key name are matched **case-dependently** — searches compare the
stored name exactly, with no case-independent matching, deliberately avoiding any code-page
dependency. Any case-insensitive matching an application wants is its own responsibility.

No distinction is made in storage between a value written as a text string
(`PrfWriteProfileString`) and one written as binary data (`PrfWriteProfileData`); either write may
be read back with either query call, and enumeration returns names irrespective of which write
call produced the entry.

Provenance: **[DOC-IBM]** `pm1.inf` — `PrfQueryProfileString` / `PrfQueryProfileData` /
`PrfWriteProfileData` *Parameters* and *Remarks* panels.

---

## 2. The `HINI` handle and the two system profiles [DOC-IBM]

Every profile call takes an `HINI` — a *handle to an initialization file*. It is an `LHANDLE`:

```c
typedef LHANDLE HINI;    /* hini */    /* pmshl.h:66 */
typedef HINI   *PHINI;                  /* pmshl.h:67 */
```

Three of its values are predefined pseudo-handles that select the always-open system profiles
without an `PrfOpenProfile` call:

| Constant | Value | Selects | Definition |
|---|---|---|---|
| `HINI_PROFILE` | `(HINI)NULL` (0) | For a **query**: both the user profile and the system profile are searched. For a **write**: the user profile. | `pmshl.h:70` |
| `HINI_USERPROFILE` | `(HINI)-1L` | The user profile (`OS2.INI`). | `pmshl.h:71` |
| `HINI_SYSTEMPROFILE` | `(HINI)-2L` | The system profile (`OS2SYS.INI`). | `pmshl.h:72` |
| `HINI_USER` | = `HINI_USERPROFILE` | Alias. | `pmshl.h:73` |
| `HINI_SYSTEM` | = `HINI_SYSTEMPROFILE` | Alias. | `pmshl.h:74` |

The user profile and the system profile are opened by the system — either at start-up, or (for the
user profile) as the result of a `PrfReset` — and are always available; an application never has to
open or close them. Any other `HINI` value is a handle returned by `PrfOpenProfile`, and is valid
**only in the process that issued that `PrfOpenProfile`**.

The distinction between the three pseudo-handles on a query is: `HINI_PROFILE` searches the user
profile and then the system profile; `HINI_USERPROFILE` searches only the user profile;
`HINI_SYSTEMPROFILE` searches only the system profile.

Provenance: **[DOC-IBM]** constant values `pmshl.h:66-74`; search / write semantics `pm1.inf` —
`PrfQueryProfileString` *hini* parameter and `PrfWriteProfileData` *hini* parameter panels.

---

## 3. Opening and closing a profile [DOC-IBM]

| Symbol | Prototype (from `pmshl.h`) | Purpose |
|---|---|---|
| `PrfOpenProfile` | `HINI APIENTRY PrfOpenProfile(HAB hab, PSZ pszFileName)` | Make a file available for use as a profile and return its `HINI`. |
| `PrfCloseProfile` | `BOOL APIENTRY PrfCloseProfile(HINI hini)` | Release an `HINI` obtained from `PrfOpenProfile`. |

`PrfOpenProfile` (`pmshl.h:505-507`) takes an anchor-block handle (`hab`) and a profile file name
and returns an `HINI` used on subsequent calls, or `NULLHANDLE` on error. The file name **must not
be the same as the current user (`OS2.INI`) or system (`OS2SYS.INI`) initialization file**. The
returned handle is only valid for the process that issued the call. This call is how an
administrator's application creates or modifies a profile for a user, and how a back-up profile is
built (enumerate application names, then key names, then copy each value — see §6).

```c
HINI hini = PrfOpenProfile(hab, "PROFILE.INI");   /* NULLHANDLE on failure */
```

`PrfCloseProfile` (`pmshl.h:509`) invalidates the `HINI`; after it, the handle must not be used for
any further call. **The current user and system profiles cannot be closed** — passing
`HINI_PROFILE`, `HINI_USERPROFILE`, or `HINI_SYSTEMPROFILE` is rejected. Both calls return `TRUE`
on success and `FALSE` on failure; on failure the reason is retrievable with `WinGetLastError`.

`PrfOpenProfile` errors: `PMERR_OPENING_INI_FILE` (`0x1301`, unable to open — e.g. no disk space),
`PMERR_MEMORY_ALLOC` (`0x1309`), `PMERR_INI_FILE_IS_SYS_OR_USER` (`0x1124`).
`PrfCloseProfile` errors: `PMERR_INI_FILE_IS_SYS_OR_USER` (`0x1124`),
`PMERR_INVALID_INI_FILE_HANDLE` (`0x1115`).

Provenance: **[DOC-IBM]** prototypes `pmshl.h:505-509`; semantics + errors `pm1.inf`
(`PrfOpenProfile` / `PrfCloseProfile` *Parameters* / *Remarks* / *Errors* panels); error values
`pmerr.h:225,234,187,172`. Cross-check **[DOC]** EDM2 "PrfCloseProfile".

---

## 4. Reading a value [DOC-IBM]

| Symbol | Prototype (from `pmshl.h`) | Purpose |
|---|---|---|
| `PrfQueryProfileString` | `ULONG APIENTRY PrfQueryProfileString(HINI hini, PSZ pszApp, PSZ pszKey, PSZ pszDefault, PVOID pBuffer, ULONG cchBufferMax)` | Read a value as a string, or a default if absent. |
| `PrfQueryProfileInt` | `LONG APIENTRY PrfQueryProfileInt(HINI hini, PSZ pszApp, PSZ pszKey, LONG sDefault)` | Read a value and convert it to an integer, or a default if absent. |
| `PrfQueryProfileData` | `BOOL APIENTRY PrfQueryProfileData(HINI hini, PSZ pszApp, PSZ pszKey, PVOID pBuffer, PULONG pulBuffLen)` | Read a value as binary data. |
| `PrfQueryProfileSize` | `BOOL APIENTRY PrfQueryProfileSize(HINI hini, PSZ pszApp, PSZ pszKey, PULONG pulReqLen)` | Obtain the size in bytes of a value, without reading it. |

**`PrfQueryProfileString`** (`pmshl.h:441-446`) searches the profile for the key `pszKey` under
application `pszApp`. If found, the value string is copied into `pBuffer` (at most `cchBufferMax`
bytes; longer data is truncated). If the key does not exist, the default string `pszDefault` is
copied instead; if `pszDefault` is itself `NULL`, nothing is copied and the return is 0. The return
value is `ulLength` — the actual number of bytes placed in `pBuffer`, **including** the terminating
null.

**`PrfQueryProfileInt`** (`pmshl.h:427-430`) performs the same case-dependent search and converts
the stored string to a number (e.g. a value written as the text `"123"` reads back as `123`). It
returns `sDefault` if the (application, key) pair cannot be found. For a correct result the stored
string must be null-terminated.

**`PrfQueryProfileData`** (`pmshl.h:480-485`) returns the value as raw binary data. On entry
`*pulBuffLen` is the size of `pBuffer`; on return it is the number of bytes actually copied. It
reads back a value regardless of whether it was written with `PrfWriteProfileString` or
`PrfWriteProfileData`. It returns `TRUE` on success, `FALSE` on error.

**`PrfQueryProfileSize`** (`pmshl.h:467-470`) returns, through `*pulReqLen`, the size in bytes of
the value for the given (application, key) pair — used to allocate a buffer before a
`PrfQueryProfileString` / `PrfQueryProfileData` call. `pszApp` and `pszKey` are case-sensitive and
must match exactly. Returns `TRUE` / `FALSE`.

`PrfQueryProfileString` / `PrfQueryProfileData` errors: `PMERR_INVALID_PARM` (`0x1303`),
`PMERR_BUFFER_TOO_SMALL` (`0x110B`), `PMERR_NOT_IN_IDX` (`0x1304`, name not found),
`PMERR_INVALID_ASCIIZ` (`0x130C`), `PMERR_CAN_NOT_CALL_SPOOLER` (`0x130D`).

Provenance: **[DOC-IBM]** prototypes `pmshl.h:427-485`; semantics `pm1.inf`
(`PrfQueryProfileString` / `Int` / `Data` / `Size` *Parameters* / *Remarks* panels); error values
`pmerr.h:227,160,228,237,238`.

---

## 5. Enumeration — a null application or a null key [DOC-IBM]

The query calls double as enumerators: passing `NULL` for the application name lists all
applications, and passing `NULL` for the key name (with a real application) lists all keys under
that application. This is how a caller discovers a profile's contents. `PrfQueryProfileString` and
`PrfQueryProfileData` enumerate identically; `PrfQueryProfileSize` returns the size such a list
would occupy.

- **`pszApp == NULL`** — enumerate **application names**. The function builds, in `pBuffer`, a list
  of all application names in the profile. Each name is terminated with a single null character,
  and the last name in the list is terminated with **two** successive null characters. In this
  case `pszKey` is ignored.
- **`pszApp` valid, `pszKey == NULL`** — enumerate **key names** for that application. `pBuffer`
  receives the list of key names (the names only, not their values), in the same
  single-null-between / double-null-at-end layout.

The returned length (`ulLength` for `PrfQueryProfileString`) is the total length of the list **up
to but not including the final null**. If the list does not fit in the supplied buffer, the names
are truncated, the list is **not** terminated with the two trailing zero bytes, and the call
reports failure (`ulLength`/`*pulBuffLen` = the number of bytes actually copied; `PrfQueryProfile*`
returning `FALSE`). Enumeration does not distinguish values written with `PrfWriteProfileString`
from those written with `PrfWriteProfileData`.

The idiomatic enumerate-then-walk pattern (obtain size, allocate, enumerate, iterate the
null-separated list) [DOC-IBM — Toolkit sample `SAMPLES/PM/GRAPHICS/file.c:1378-1406,1592-1615`]:

```c
ULONG len;
PrfQueryProfileSize(HINI_PROFILE, pszApp, NULL, &len);      /* size of the key-name list */
PSZ names = malloc(len);
PrfQueryProfileString(HINI_PROFILE, pszApp, NULL, NULL, names, len);
for (PSZ p = names; *p; p += strlen(p) + 1) {              /* each null-terminated key name */
    /* PrfQueryProfileString(HINI_PROFILE, pszApp, p, ...) reads that key's value */
}
```

Provenance: **[DOC-IBM]** `pm1.inf` — `PrfQueryProfileString` *pszApp* / *pszKey* parameter panels
and *Remarks*, `PrfQueryProfileData` *Remarks*; the walk idiom is the Toolkit sample
`file.c:1378-1406,1592-1615`.

---

## 6. Writing and deleting a value [DOC-IBM]

| Symbol | Prototype (from `pmshl.h`) | Purpose |
|---|---|---|
| `PrfWriteProfileString` | `BOOL APIENTRY PrfWriteProfileString(HINI hini, PSZ pszApp, PSZ pszKey, PSZ pszData)` | Write (or delete) a string value. |
| `PrfWriteProfileData` | `BOOL APIENTRY PrfWriteProfileData(HINI hini, PSZ pszApp, PSZ pszKey, PVOID pData, ULONG cchDataLen)` | Write (or delete) a binary value of length `cchDataLen`. |

Both write the value of the (application, key) pair into the profile. If the application heading
does not yet exist it is created; if the key does not exist it is created; if the key already
exists its value is overwritten. For the string form the value is the ASCIIZ string `pszData`; for
the data form the value is `cchDataLen` bytes at `pData` and is **not** zero-terminated (the length
is the only record of its extent). The maximum value size is 64 KB. Both return `TRUE` / `FALSE`.

**Deletion is expressed through null parameters** — there is no separate delete call:

| To delete… | `PrfWriteProfileString` | `PrfWriteProfileData` |
|---|---|---|
| one key's value | `pszData = NULL` | `pData = NULL`, `cchDataLen = 0` |
| all keys of an application | `pszKey = NULL`, `pszData = NULL` | `pszKey = NULL`, `pData = NULL`, `cchDataLen = 0` |
| all data in the (user) profile | — | `pszApp = NULL`, `pszKey = NULL`, `pData = NULL`, `cchDataLen = 0` |

For `PrfWriteProfileString`, a non-`NULL` `pszData` is stored even if it is the empty string (only
`NULL` deletes). Write errors include `PMERR_INVALID_PARM` (`0x1303`) and
`PMERR_CAN_NOT_CALL_SPOOLER` (`0x130D`).

Provenance: **[DOC-IBM]** prototypes `pmshl.h:455-458,494-499`; write / create / delete semantics
`pm1.inf` (`PrfWriteProfileString` / `PrfWriteProfileData` *pszKey* / *pszData* / *pData* parameter
panels and *Remarks*); error values `pmerr.h:227,238`.

---

## 7. Switching profiles — `PRFPROFILE`, `PrfQueryProfile`, `PrfReset` [DOC-IBM]

The pair of files acting as the user and system profiles can be queried and changed at run time. A
`PRFPROFILE` structure names them:

```c
typedef struct _PRFPROFILE   /* prfpro */    /* pmshl.h:77-83 */
{
   ULONG  cchUserName;   /* length of the pszUserName buffer, in bytes */
   PSZ    pszUserName;   /* user-profile file name (ASCIIZ)            */
   ULONG  cchSysName;    /* length of the pszSysName buffer, in bytes  */
   PSZ    pszSysName;    /* system-profile file name (ASCIIZ)          */
} PRFPROFILE;
typedef PRFPROFILE *PPRFPROFILE;              /* pmshl.h:84 */
```

| Symbol | Prototype (from `pmshl.h`) | Purpose |
|---|---|---|
| `PrfQueryProfile` | `BOOL APIENTRY PrfQueryProfile(HAB hab, PPRFPROFILE pPrfProfile)` | Return a description (the file names) of the current user and system profiles. |
| `PrfReset` | `BOOL APIENTRY PrfReset(HAB hab, PPRFPROFILE pPrfProfile)` | Define which files are used as the user and system profiles. |

`PrfQueryProfile` (`pmshl.h:514-515`) fills `*pPrfProfile` with the current profile file names; the
caller supplies the buffers and their `cch*` lengths (the usual pattern is to let `PrfQueryProfile`
report the names first).

`PrfReset` (`pmshl.h:511-512`) causes the workstation to use a different set of profiles. At
initialization the user and system profile names come from the `PROTSHELL` statement in
`CONFIG.SYS`; `PrfReset` lets them change while the workstation is running (e.g. a logon
application serving successive users). The file names in `pPrfProfile` may be any valid names; a
name that is not fully qualified is taken relative to the current directory. If the named user
profile file does not exist it is created. **The system profile name cannot be changed** — it must
equal the current system profile name returned by `PrfQueryProfile`. After `PrfReset` the system
has a new set of preferences (screen colors, start-up list, spooler parameters, country
information). `PrfReset` **broadcasts the `PL_ALTERED` message** so that applications reading their
defaults from the profiles can re-read and apply the new settings; it **requires the calling thread
to have a message queue**.

```c
#define PL_ALTERED  0x008E   /* WM_SHELLFIRST + 0x0E, broadcast by PrfReset */    /* pmshl.h:518 */
```

Both return `TRUE` / `FALSE`.

Provenance: **[DOC-IBM]** structure `pmshl.h:77-84`; prototypes `pmshl.h:511-515`; `PL_ALTERED`
value `pmshl.h:518`; semantics `pm1.inf` (`PrfReset` / `PrfQueryProfile` *Parameters* / *Remarks*
panels). Field meanings cross-checked **[DOC]** EDM2 "PRFPROFILE".

---

## 8. Error codes [DOC-IBM]

On failure a `Prf*` call returns `NULLHANDLE` / `FALSE` / `0`; the specific cause is obtained with
`WinGetLastError`. The INI-related `PMERR_*` values (all confirmed in `pmerr.h`):

| Constant | Value | Meaning | `pmerr.h` |
|---|---|---|---|
| `PMERR_BUFFER_TOO_SMALL` | `0x110B` | Supplied buffer too small for the data to be returned. | `:160` |
| `PMERR_INVALID_INI_FILE_HANDLE` | `0x1115` | An invalid `HINI` was specified. | `:172` |
| `PMERR_INI_FILE_IS_SYS_OR_USER` | `0x1124` | Attempted to close the user or system profile (not permitted). | `:187` |
| `PMERR_OPENING_INI_FILE` | `0x1301` | Unable to open the initialization file (e.g. out of disk space). | `:225` |
| `PMERR_INI_FILE_CORRUPT` | `0x1302` | The initialization file is corrupt. | `:226` |
| `PMERR_INVALID_PARM` | `0x1303` | A parameter contained invalid data. | `:227` |
| `PMERR_NOT_IN_IDX` | `0x1304` | The application name, key name, or program handle was not found. | `:228` |
| `PMERR_INI_WRITE_FAIL` | `0x1306` | A write to the initialization file failed. | `:231` |
| `PMERR_INI_PROTECTED` | `0x1308` | The initialization file is protected. | `:233` |
| `PMERR_MEMORY_ALLOC` | `0x1309` | An error occurred during memory management. | `:234` |
| `PMERR_INVALID_ASCIIZ` | `0x130C` | The profile string is not a valid zero-terminated string. | `:237` |
| `PMERR_CAN_NOT_CALL_SPOOLER` | `0x130D` | Error calling the spooler validation routine (not raised if the spooler is not installed). | `:238` |

Provenance: **[DOC-IBM]** values `pmerr.h` at the lines shown; the meanings are from `pm1.inf`
per-function *Errors* panels (`PrfOpenProfile`, `PrfCloseProfile`, `PrfQueryProfileString`).

---

## See also
- `session-manager.md` / `config-and-environment.md` — the `PROTSHELL` statement in `CONFIG.SYS`
  that names the initial user and system profiles `PrfReset` can later replace.
- `pm-window-messaging.md` — the `HAB` anchor block passed to `PrfOpenProfile` / `PrfReset` /
  `PrfQueryProfile`, and the message queue `PrfReset` requires in order to broadcast `PL_ALTERED`.
- `error-codes.md` — the `WinGetLastError` mechanism and the `PMERR_*` space these calls report
  into.
