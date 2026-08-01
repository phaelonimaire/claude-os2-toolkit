# Rebuilding an installed OS/2 package from source

*"Fix the bug where it lives"* is a discipline, not a preference — see `../START-HERE.md` §3 and
`../os2-app-dev-guide.md` §8 for why the workaround is the expensive branch. **This recipe is the
mechanics**: the path from "installed RPM" to "patched DLL loaded by one process", without touching
the system copy. It is written from a real case (patching `readline`), and every step below is a
failure that actually happened, in the order it happened.

## 1. Get the source

`yumdownloader` fetches the SRPM, but on ArcaOS it is a **python2** script and the default `python`
is 3 — running it directly dies with a `SyntaxError` on `except ... , e:`. Invoke it explicitly:

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

## 2. Generate `configure` on Linux, not on OS/2

bitwiseworks' GitHub source zips ship **no generated `configure`** (the spec runs `autoreconf -fvi`
in `%prep`), and the OS/2 box typically has no autoconf/automake/libtool. Don't install them there —
autoconf output is portable shell, so generate it on the host:

```sh
cd readline-os2-8.0-os2-3 && autoreconf -fvi
```

`autoheader` may fail on a package that ships its own `config.h.in` (readline does). That is fine as
long as `configure` was produced — check for the file rather than trusting the exit status.

## 3. The four OS/2 configure failures, in the order you will hit them

**a. There is no `/bin/sh`.** Configure dies running `support/config.sub`:

```
configure: error: cannot run /bin/sh ././support/config.sub
```

```sh
SH=/@unixroot/usr/bin/sh.exe
export CONFIG_SHELL=$SH SHELL=$SH
$SH ./configure ...            # and pass SHELL=$SH to make as well
```

**b. `PATH` is `;`-separated with drive letters; configure splits on `:`.** So it finds *nothing* —
first `no acceptable C compiler`, then `no acceptable grep`. Name every tool absolutely:

```sh
export CC=/@unixroot/usr/bin/gcc.exe AR=/@unixroot/usr/bin/ar.exe RANLIB=/@unixroot/usr/bin/ranlib.exe
export GREP=/@unixroot/usr/bin/grep.exe SED=/@unixroot/usr/bin/sed.exe AWK=/@unixroot/usr/bin/gawk.exe
export EGREP="/@unixroot/usr/bin/grep.exe -E" FGREP="/@unixroot/usr/bin/grep.exe -F"
```

**Do not "fix" this by prepending a `:`-style entry to `PATH`** — that merges into the first
`;`-separated element and destroys it. (Symptom: the shell suddenly cannot find `tail`.)

**c. `-Zomf` resolves `-lfoo` to `foo_s.a`, which many devel packages don't ship.** They ship OMF
**import libraries** (`.lib`) instead:

```
weakld: cannot open library file '\@unixroot\usr\lib\curses_s.a'
```

`ls /@unixroot/usr/lib | grep -i <name>` to see what exists, then either drop the flag (if the
package doesn't actually use that library) or override the make variable with the real path —
e.g. readline's link libs come from `SHLIB_LIBS`:

```sh
make SHELL=$SH SHLIB_LIBS="/@unixroot/usr/lib/tinfo.lib /@unixroot/usr/lib/ncurses.lib"
```

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
