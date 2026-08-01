# Build hello-pm

A WINDOWAPI (Presentation Manager) app. Full flag detail: `../../recipes/build-pm-app.md`.

**OpenWatcom (Linux):** (verified with OpenWatcom 1.9)
```sh
export INCLUDE="$WATCOM/h;$WATCOM/h/os2"          # os2.h lives in h/os2/
wcl386 -bt=os2 -l=os2v2_pm hello.c -fe=hello.exe
```
Do **not** add `-bg` — the `os2v2_pm` system already builds a PM app; `-bg` pulls in the
default-windowing startup and breaks the entry point (`W1023: no starting address`).

**GCC/kLIBC (on the OS/2 VM):**
```sh
gcc -Zomf -O2 hello.c hello.def -o hello.exe
```

Run it on an OS/2 target with PM (`../../recipes/setup-test-vm.md`): launch `hello.exe` — a titled,
resizable window that paints a centered string. Add a `hello.rc` (menu/dialog/string resources) and
bind it with `wrc hello.res hello.exe` when you extend it; see
`../../os2ref/resources-and-dialogs.md`.
