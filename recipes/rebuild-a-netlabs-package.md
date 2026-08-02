# Rebuilding an installed OS/2 package from source

*"Fix the bug where it lives"* is a discipline, not a preference — see `../START-HERE.md` §3 and
`../os2-app-dev-guide.md` §8 for why the workaround is the expensive branch. **This recipe is the
mechanics**: the path from "installed RPM" to "patched DLL loaded by one process", without touching
the system copy. It is written from a real case (patching `readline`), and every step below is a
failure that actually happened, in the order it happened.

**Which machine each step runs on.** This is written for a **cross setup**: a Linux (or other Unix)
host for fetching and `autoreconf`, an OS/2 box for the actual build. Every section below is tagged
*(host)* or *(OS/2)*. Nothing here requires the host — you can do the lot on OS/2 if you install
autoconf/automake/libtool there — but the failures in §3 are OS/2's regardless of where the tarball
was unpacked, and §2 is the one step that is genuinely easier off-box.

## 1. Get the source *(OS/2 to fetch, host to unpack)*

`yumdownloader` fetches the SRPM, but it is a **python2** script while the default `python` is 3 —
running it directly dies with a `SyntaxError` on `except ... , e:`. (Observed on WSEB 4.50 with the
netlabs RPM userland: the shebang is `#!/usr/bin/python`, `python --version` reports 3.9, and
`python2.7.exe` is present alongside. Check your own box rather than assuming the versions.) Invoke
it explicitly:

```sh
python2.7 /@unixroot/usr/bin/yumdownloader --source readline --destdir=N:/somewhere
```

Unpack on the **Linux** side (faster, and the tools are there). `rpm2cpio` comes with the `rpm`
package; `bsdtar` also reads an SRPM if you'd rather not install it:

```sh
rpm2cpio readline-8.0-3.oc00.src.rpm | cpio -idm      # -> a .zip/.tar + the .spec
unzip readline-github-8.0-os2-3.zip
```

**Read the `.spec` before building** — it carries the port's real build flags (e.g.
`LDFLAGS="-Zhigh-mem -Zomf -Zargs-wild -Zargs-resp -lcx"`), the `%configure` options, and often a
comment explaining a workaround you are about to rediscover.

## 2. Generate `configure` on the host, not on OS/2 *(host)*

bitwiseworks' GitHub source zips ship **no generated `configure`** (the spec runs `autoreconf -fvi`
in `%prep`), and the OS/2 box typically has no autoconf/automake/libtool. Don't install them there —
autoconf output is portable shell, so generate it on the host:

```sh
cd readline-os2-8.0-os2-3 && autoreconf -fvi
```

`autoheader` may fail on a package that ships its own `config.h.in` (readline does). That is fine as
long as `configure` was produced — check for the file rather than trusting the exit status.

## 3. The four OS/2 configure failures, in the order you will hit them *(OS/2)*

> **Everything measured in this section was measured on one machine:** OS/2 Warp Server for
> e-business 4.50, Convenience Pack 2 (`SYSLEVEL.OS2` reports `XR04503`), with the netlabs/RPM
> userland, GCC 9.2.0 (kLIBC) and autoconf 2.71-generated `configure` scripts.
>
> **ArcaOS may not match, and none of this was tested there.** A distribution that preconfigures its
> own userland can differ in exactly the three facts this section leans on. Check your own box before
> assuming — each is one line:
>
> ```sh
> ls -d /bin && /bin/sh -c 'echo yes'      # a: is /bin/sh already there?  (absent here)
> ls -l /@unixroot/usr/bin/gcc             # b: extensionless, or only gcc.exe?  (only .exe here)
> rpm --eval '%{_prefix}'                  # config.site path  (/@unixroot/usr here)
> ```
>
> If `/bin/sh` already runs on your box, **a** is already solved for you and autoconf's separator
> probe in **b** will work by itself — leaving `ac_executable_extensions` as the only thing to set.
> The mechanisms below hold regardless; which remedies you need does not. `[unverified]` on ArcaOS.

**a. There is no `/bin/sh`.** Configure dies running `support/config.sub`:

```
configure: error: cannot run /bin/sh ././support/config.sub
```

On the box above there is no `/bin` **directory** at all, and kLIBC does not alias it to `/usr/bin`:
`test -d /bin` false, `ls -d /bin` "No such file", `/bin/sh -c …` "not found", and no `/bin`
special-casing in kLIBC's path resolution. **Check yours first** — a distribution that ships `/bin`
has already fixed this, and the rest of **a** does not apply. Two ways out. Per build:

```sh
SH=/@unixroot/usr/bin/sh.exe
export CONFIG_SHELL=$SH SHELL=$SH
$SH ./configure ...            # and pass SHELL=$SH to make as well
```

**Or give the machine the `/bin/sh` everything expects**, which is the better trade if you build
often — symlink it, so it does not go stale when the `ash`/`sh` package is updated:

```sh
mkdir -p /@unixroot/bin && ln -s /@unixroot/usr/bin/sh.exe /@unixroot/bin/sh.exe
```

The link is named `sh.exe`, not `sh` — `/bin/sh` then resolves because kLIBC appends `.exe` when
*executing*, even though it does not when calling `stat()` (see **b**.2). Tested: that makes explicit
`/bin/sh …` invocations work, makes `#!/bin/sh` shebang scripts run, and — see **b** — makes
autoconf's `PATH_SEPARATOR` detection start working, since `/bin/sh` is exactly what it probes for.

**b. Configure finds no tools at all** — first `no acceptable C compiler`, then `no acceptable grep`.

**Two** independent things are broken, and **both** must be fixed; neither alone gets you past the
compiler check (measured, table below).

1. **`PATH` is `;`-separated with drive letters.** Autoconf does try to detect this. It sets `:`, then
   runs two probes — it switches to `;` only if `(PATH='/bin;/bin'; FPATH=$PATH; sh -c :)` **succeeds**
   *and* `(PATH='/bin:/bin'; FPATH=$PATH; sh -c :)` **fails**. With no `/bin` (see **a**) the first
   probe fails, so the fallback `:` stands. Splitting `C:/usr/bin;C:/usr/local/bin;…` on `:` then
   yields elements like `C` and `/usr/bin;C`, none of which hold the compiler.
   `[SRC]` autoconf `lib/m4sugar/m4sh.m4`, `_AS_PATH_SEPARATOR_PREPARE`.
   Fix it **either** by presetting the variable — it is honoured when set, the branch is commented
   "The user is always right" — **or** by creating `/bin/sh` per **a**, which makes the probe answer
   `;` by itself. Both tested; either is sufficient.
2. **The tools are `.exe` and kLIBC's `stat()` does not pretend otherwise.** `test -f
   /@unixroot/usr/bin/gcc` is **false**; `gcc.exe` is true. Autoconf's program search only tries
   `$ac_word` followed by each entry of `$ac_executable_extensions` — a variable autoconf **never
   assigns anywhere**, so it is yours to set and an exported value survives into configure's shell.
   `[SRC]` autoconf `lib/autoconf/programs.m4:52,132,427,557,670` — the five `for ac_exec_ext in ''
   $ac_executable_extensions` loops, and the only occurrences in the tree. (It does not govern
   *every* search: `_AS_DETECT_BETTER_SHELL` in `lib/m4sugar/m4sh.m4` hardcodes its own `.exe` test
   when hunting for a shell.)

```sh
export PATH_SEPARATOR=';' ac_executable_extensions='.exe'
```

Better for repeated builds, put them in a **`config.site`** instead of the environment:

```sh
cat > /@unixroot/usr/share/config.site <<'EOF'
PATH_SEPARATOR=';'
ac_executable_extensions='.exe'
EOF
```

**Mind how configure picks that file, because the automatic path is conditional.** `CONFIG_SITE` is
checked *first and unconditionally*; only if it is unset does configure fall back to
`$prefix/share/config.site` — **and `$prefix` is `NONE` unless `--prefix` was passed**, in which case
it uses `$ac_default_prefix` instead (usually `/usr/local`, or whatever the package's
`AC_PREFIX_DEFAULT` says). So:

- Building **under `rpmbuild`/`%configure`**: the file above is found automatically. Verified with
  `rpm --eval '%configure'` on the netlabs stack — it passes `--prefix=/@unixroot/usr`, and
  `rpm --eval '%{_prefix}'` is `/@unixroot/usr`, not `/usr`.
- Running **`./configure` by hand** as in **a** above, with no `--prefix`: the file is **not read**,
  silently — no "loading site script" line, and you are back to `no acceptable C compiler` with no
  hint why. Point `CONFIG_SITE` at it instead, which always works:

```sh
export CONFIG_SITE=/@unixroot/usr/share/config.site
```

Measured on the box named at the top of this section, running a generated `configure` containing only
`AC_PROG_CC`, `AC_PROG_GREP`, `AC_PROG_SED`, `AC_PROG_AWK`:

| `PATH_SEPARATOR=';'` | `ac_executable_extensions='.exe'` | `/bin/sh` exists | result |
|---|---|---|---|
| — | — | no | `no acceptable C compiler found in $PATH` |
| yes | — | no | `no acceptable C compiler found in $PATH` |
| — | yes | no | `no acceptable C compiler found in $PATH` |
| — | — | **yes** | `no acceptable C compiler found in $PATH` |
| **yes** | **yes** | no | exit 0 — `gcc`, `C:/usr/bin/grep.exe`, `C:/usr/bin/sed` |
| — | **yes** | **yes** | exit 0 |

(Paths in the last two rows are as configure printed them; `C:` is this box's `%UNIXROOT%`.)

The last two rows are the two supported combinations: fix the separator with the variable, or fix it
by giving autoconf the `/bin/sh` its probe wants. `ac_executable_extensions` is required either way.
Both settings also work from a site file, with one catch worth its own paragraph.

**The `config.site` route still needs `CONFIG_SHELL`, and omitting it fails at the very last step.**
`configure` sets `SHELL=${CONFIG_SHELL-/bin/sh}` (an inherited `SHELL` is ignored) and runs
`config.status` through it. A site file is read far too late to matter, and `config.status` does not
read one at all. Measured, with a `configure` that actually generates a `Makefile`:

| route | result |
|---|---|
| `CONFIG_SITE` only, no `/bin/sh`, no `CONFIG_SHELL` | every check passes, then `./configure: /bin/sh: not found` — **exit 1, no Makefile** |
| `CONFIG_SITE` + `CONFIG_SHELL` | exit 0, `Makefile` created |
| **`/bin/sh` symlink + `ac_executable_extensions`, nothing else** | exit 0, `Makefile` created |

That failure is the nastiest one in this recipe: `checking for gcc… gcc` and every other probe
succeeds, `creating config.status` prints, and *then* it dies — so the instinct is to go hunting in
the compiler checks. **The `/bin/sh` symlink from a is the one fix that covers all of it**: it
satisfies the separator probe, `config.status`, and any `#!/bin/sh` sub-script, leaving
`ac_executable_extensions` as the only thing you must still set.

Note this was measured with **autoconf 2.71**. `ac_executable_extensions` is not a knob ancient
configure scripts know about `[unverified]` — netlabs packages ship a range of vintages, so if a
package's `configure` ignores it, fall back to naming the tools absolutely.

Naming every tool absolutely (`CC=/@unixroot/usr/bin/gcc.exe`, `GREP=…`, `SED=…`, and so on) also
works and is what you will see in older notes, but it is an ever-growing list, and it does nothing
for the `AC_PATH_PROG` searches inside macros you do not control. Prefer the two variables.

(Why `sed` resolves without the suffix in that table while `gcc` does not: `/usr/bin/sed` happens to
be a **symlink** to `sed.exe`. Which tools are symlinked is packaging accident — do not rely on it.)

**Do not "fix" this by prepending a `:`-style entry to `PATH`** — that merges into the first
`;`-separated element and destroys it. (Symptom: the shell suddenly cannot find `tail`.)

**c. A library that isn't there is reported under its _last-tried_ name, which reads like a demand
for `foo_s.a`.** It is not one:

```
weakld: cannot open library file '\@unixroot\usr\lib\curses_s.a'
```

`LDFLAGS=-Zomf` links via **emxomfld**, which searches **the current directory first**, then each
directory in `LIB`, trying every suffix below in order with the prefix `lib` and then no prefix as
the inner loop `[SRC]` `src/emx/src/emxomf/emxomfld.c:924-934` (the suffix and prefix arrays) and
`:976-981` (the `.\` pre-seed), all in `find_lib()`. It reads only the `LIB` environment variable
(`:982`) — `-L` still works as you expect, because gcc composes `LIB` from its `-L` list plus its own
defaults (`gcc -print-search-dirs`) and passes it down:

| emxomfld link mode | suffixes, in order |
|---|---|
| shared — the default | `_dll.lib` `_dll.a` `.lib` `.a` `_s.lib` `_s.a` |
| shared + dll — `-Zdll-search` | as above, with `.dll` inserted after `.a` |
| static — `-Bstatic`, `-static`, `-non_shared`, `-dn` | `_s.lib` `_s.a` `.lib` `.a` |

**Those are `emxomfld`'s options, and most of them do not survive being put in `LDFLAGS`**, because
`LDFLAGS` goes to `gcc` first. Measured — `gcc -Zomf <flag> t.c -L. -lzznothing`:

| flag | what actually happens |
|---|---|
| `-static` | **works** — reports `zznothing.a`, the last suffix of the static list |
| `-Bstatic` | links, but reports `zznothing_s.a` — **the shared order; static was not selected** |
| `-Zdll-search` | `gcc: error: unrecognized command line option` |
| `-Zno-autoconv` | `gcc: error: unrecognized command line option` |
| `-non_shared` | `gcc: error: unrecognized command line option` |
| `-dn` | silently misparsed by `cc1` as a debugging option |

So through gcc, `-static` is the one that selects the static order; pass the rest to the linker
directly (`-Wl,`) or invoke `emxomfld` yourself. `-Bstatic` is the trap — it neither errors nor works.

`_s.a` is merely the **last** candidate. On failure `find_lib()` leaves that last constructed name in
the buffer, and weakld prints it when it cannot open it `[SRC]`
`src/emx/src/emxomf/emxomfld.c:1151`, `src/emx/src/emxomf/weakld.c:2990`. So the message means
**nothing matching that library name was found in the build directory or any `LIB` directory** — it
is not a statement about formats. (The build directory being searched first also means a stray
`foo.lib` sitting in your tree silently outranks the packaged one.) Two consequences that follow from the table:

- **OMF import libraries resolve fine.** `.lib` is tried *before* `_s.a`, so `-lfoo` finds `foo.lib`,
  and `LDFLAGS="-Zomf" … -lmmpm2` works once the Toolkit import libraries are on the `LIB` path
  (packaged as `os2tk45-libs` `[unverified]` — the search behaviour is what was tested, not the
  package name). Measured four ways: with only `zztest.lib` present and no
  `.a` of any name, `gcc -Zomf t.c -L. -lzztest` links and the `.exe` runs; a *deliberately corrupt*
  `.lib` fails inside `emxomf` ("is not an a.out file"), proving the file is opened rather than
  skipped; a valid `.lib` beside a corrupt `_s.a` links; and a corrupt `.lib` beside a valid `_s.a`
  **fails on the `.lib`** — so `.lib` is genuinely tried first, not merely accepted.
- **a.out `.a` archives work too** — measured: a lone `foo.a` links under `-Zomf`. emxomfld converts
  them to OMF during the link unless you pass `-Zno-autoconv`
  `[SRC]` `src/emx/src/emxomf/emxomfld.c:178,1016-1022`. The same branch converts an
  **LX `.dll`** it opens. Note that conversion is *not* gated on `-Zdll-search`: that flag only adds
  `.dll` to the suffix list, so it governs whether a bare `-lfoo` will *find* `foo.dll`, not whether
  a `.dll` can be linked — naming one explicitly works either way `[SRC]` same file, `:959,965,1723`.

So the real diagnosis is almost always a **name**, not a format. `ls /@unixroot/usr/lib | grep -i
<name>` — in the readline case nothing named `curses*` was on the `LIB` path at all; the ncurses
packages provide `ncurses` and `tinfo`. Fix it by naming the libraries that exist (`-lncurses
-ltinfo`, and see **d** below),
and only override the make variable outright when the makefile hard-codes something you cannot reach
— e.g. readline's link libs come from `SHLIB_LIBS`:

```sh
make SHELL=$SH SHLIB_LIBS="/@unixroot/usr/lib/tinfo.lib /@unixroot/usr/lib/ncurses.lib"
```

**Two older copies of this list circulate, and both disagree with the code.** `[DOC]`
`doc/ReleaseNotes.os2:966-989` in the kLIBC tree gives the same three modes with `.a` suffixes only
(`libfoo_dll.a`, `libfoo.a`, `libfoo_s.a`, …) — note it sits under the **v3.2.2 Beta 4** heading,
even though the file ships in the GCC 3.3.5 doc directory, so grepping the 3.3.5 sections for it
finds nothing. And `find_lib()`'s **own header comment**
(`src/emx/src/emxomf/emxomfld.c:893-905`) gives a third, shorter order with no `.a` entries at all
and `.dll` in a different position. Where a comment and the arrays disagree, the arrays are what
runs. `[unverified]` when the `.lib` entries were added — they are already present in the oldest
commit touching those lines in this tree, so do not assume the release note was ever accurate.

**d. ncurses splits the termcap entry points into `tinfo.lib`.** Linking only `ncurses.lib` leaves
`tgetent`/`tgetstr`/`tgetflag`/`tgetnum`/`tputs`/`tgoto`/`PC`/`BC`/`UP` undefined. Link **both**.
(A cryptic `sed -i -e 's/tinfo//'` in a spec file is usually a hint that this bit the packager too.)

Install the devel packages first: `yum -y install ncurses-devel libcx-devel`.

## 4. Load the patched DLL for one process only

Never overwrite the system copy while testing. OS/2 supports per-process library paths:

```sh
SET LIBPATHSTRICT=T          # required: without it BEGINLIBPATH won't shadow a system DLL
SET BEGINLIBPATH=C:\mylibs
```

**`BEGINLIBPATH` is not an ordinary environment variable** — it is applied via `DosSetExtLIBPATH`,
so `env VAR=... prog` is silently ignored. Set it with `SET` inside a `.cmd` file (or call the API).

**Verify which copy actually loaded.** OS/2 keys loaded DLLs **by name in the shared arena**, so a
copy already resident in another process can win over your private one and you will test the wrong
binary. A ten-line probe settles it:

```c
#define INCL_DOSMODULEMGR
HMODULE h; char err[260], name[260];
DosLoadModule(err, sizeof err, "READLN8", &h);
DosQueryModuleName(h, sizeof name, name);      /* prints the path actually resolved */
```

Run it under the same environment as your program. Kill every process holding the DLL before
re-testing, or you are measuring the resident copy.

## 5. Deploy safely (the trap that invalidates test results)

**A running program locks its `.EXE` and its DLLs**, so a `cp` over them *fails* — and if your build
script filters output, the failure is invisible and every subsequent test measures the **old**
binary. This is `setup-test-vm.md`'s "running `.EXE` is locked" trap in its most expensive form.

```sh
ps | awk '$5=="myapp"'           # find holders (OS/2 ps: no .exe suffix, no `ax`)
# kill them, then deploy, then CHECK THE TIMESTAMP MOVED:
cp new.dll C:/mylibs/ && ls -l C:/mylibs/new.dll
```

Rules that follow, both learned the hard way:

- **Kill every holder before deploying**, then verify the size/timestamp changed.
- **Never filter build output down to a keyword.** `... | grep -iE "DEPLOYED|error:"` turned a failed
  deploy into *silence*, which reads as success. Print an unfiltered tail.
- If a process ignores `kill` (kLIBC programs commonly do — OS/2's `DosKillProcess` is
  **cooperative**), you need a ring-0 killer; see `setup-test-vm.md`.

## 6. Upstreaming the fix

If the bug is real, send it back — these ports are maintained and small fixes land.

- **Preserve line endings.** Many of these files are CRLF; editing them with a Unix tool silently
  converts the whole file and a 15-line change appears as a 135-line diff. `file <path>` before you
  edit; restore with `sed -i 's/$/\r/'` if you flattened it.
- Keep each logical fix a separate change — a reviewer can take three small correct patches far more
  easily than one large one, and partial acceptance still improves the tree.
- Cite the mechanism, not just the symptom: the maintainer can verify "this variable is assigned in
  two places and never read" from their own source without reproducing your setup.
