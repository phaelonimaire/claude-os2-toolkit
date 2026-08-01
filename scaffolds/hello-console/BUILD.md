# Build hello-console

A WINDOWCOMPAT (VIO) app. Full flag detail: `../../recipes/build-pm-app.md`.

**OpenWatcom (Linux):**
```sh
wcl386 -bt=os2 -l=os2v2 hello.c -fe=hello.exe
```

**GCC/kLIBC (on the OS/2 VM):**
```sh
gcc -Zomf -O2 hello.c hello.def -o hello.exe
```

Run it on an OS/2 target (`../../recipes/setup-test-vm.md`): `hello.exe`.
