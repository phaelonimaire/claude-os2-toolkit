# Choosing a toolchain - OpenWatcom vs GCC/kLIBC

The first decision for an OS/2 app project, because it changes *where you compile* and *how you
test*. **Present this to the user and let them choose** - don't assume. Record the choice in the
project `CLAUDE.md`.

## The two options

### OpenWatcom (C/C++, `wcc386`/`wlink`/`wrc`)
- **Runs on Linux and cross-compiles** to OS/2 (LX/NE) - you build locally, no OS/2 needed to
  *compile*. Fast iteration.
- Native OS/2 target the platform was largely built with; handles 16-bit and 32-bit, and can build
  **device drivers**.
- **Downside: not full C99** (v1.9 in particular). Expect to avoid some modern C - e.g. declarations
  mid-block, some `<stdint.h>`/`<complex.h>` features, VLAs. Write conservative C89-ish code, or move
  to the maintained OpenWatcom v2 fork if a feature is missing.
- **Best when:** you want a local build loop, are writing conservative C/C++, or are targeting a
  driver. You still need an OS/2 target to *run* what you built.

### GCC + kLIBC (`gcc -Zomf`, `wlink` backend, `wrc`)
- **Runs inside OS/2** (over SSH to a VM). You cannot cross-build it from Linux the way you can
  Watcom - the compiler executes on the target.
- **Modern GCC** - full C99/C11, and the **kLIBC** runtime gives a large slice of POSIX (`fork`,
  `pipe`, `openpty`, sockets-as-fds, `/@unixroot` paths) plus familiar Unix tools on the box.
- **Pulls packages from RPM** (`yum`/`rpm` on ArcaOS/netlabs repos) - libraries and build deps come
  as packages instead of hand-assembly.
- **Downside: more setup ("cruft")** - you need a working OS/2 VM with GCC/kLIBC installed, SSH in,
  and the `/@unixroot` + LIBPATH plumbing right (build *and* run happen on the VM).
- **Best when:** you want modern C and POSIX-ish APIs, are porting Unix code, or already run an
  ArcaOS VM as your dev box.

## Quick decision

| If you want... | Choose |
|---|---|
| Build locally on Linux, fast loop, conservative C, or a **driver** | **OpenWatcom** |
| Modern C99/C11, POSIX (`fork`/`pipe`/`openpty`/sockets), RPM packages, porting Unix code | **GCC/kLIBC** |
| Lowest setup to *compile* | OpenWatcom (Linux-hosted) |
| A self-contained OS/2 dev box that also runs your builds | GCC/kLIBC on an ArcaOS VM |

You can use **both**: OpenWatcom locally for quick compiles, a GCC/kLIBC VM for POSIX-heavy pieces
and for *running* everything (both need an OS/2 target to run on - see `setup-test-vm.md`).

Install/build steps: `install-openwatcom.md` and `build-pm-app.md`. Get the toolchains from
`../sources.md` section 2.
