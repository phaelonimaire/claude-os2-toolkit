# OS/2 Kernel Debugger (KDB) reference

The manual for the `tools/kdb_*` scripts — driving the OS/2 **kernel debugger** in a VM over a
serial pipe. For **driver / IFS / low-level** work; a normal app is debugged with
`debugging-an-app.md`. VM setup is in `setup-kdb-vm.md`.

## Boot sequence — *when* to break in
Understanding the boot phases is critical, because at the right moment you can set breakpoints on
addresses **before the code that uses them exists**:

1. **Kernel boot** — the debug kernel loads the *system* DLLs (`DOSCALL1`, NLS, `BVSCALLS`, …),
   printed in parentheses. No debugger prompt yet.
2. **CONFIG.SYS processing** — `RUN=C:\OS2\BREAK.EXE` fires an `INT3` and you get the `##`/`**`
   prompt. **This is the ideal investigation point:** system DLLs are loaded, but PM DLLs
   (`PMMERGE`, `PMWIN`, …) and `PMSHELL.EXE` are **not** — their memory isn't mapped. Set breakpoints
   here (including hardware write breakpoints to catch the *first* write to an address), then `g`.
3. **PM loading** (after `g`) — `PROTSHELL=PMSHELL.EXE` triggers PM-DLL loading and their
   `_DLL_InitTerm` entry points run; your breakpoints hit as the structures get populated.

## The tools
| Tool | Use |
|---|---|
| `kdb_cmd.py "<cmd>" …` | Send one or more debugger commands non-interactively (scripting). `--start-vm`/`--restart-vm`/`--stop-vm` control the VM. |
| `kdb_interactive.py` | Interactive session with convenience commands (`.regs`, `.stack`, `.modules`, `.find`, `.bp`, `.disasm`, `.trace`). |
| `kdb_connect.py` | Bare interactive terminal to the debugger. |
| `kdb_hang_triage.py` | Diagnose a **frozen** system — break in, census threads, find the blocking semaphore/owner. Never reboot a hang; run this. |
| `kdb_trace_dll_init.py` | Starting point for tracing DLL init order. Breakpoint addresses are **not** discovered automatically — the module-scan helper is a stub, so you supply entry-point addresses (resolve them with `lx_export.py`/`lx_disasm.py` first). Treat it as a scaffold, not a turnkey tool. |

Set the VM name once: `export KDB_VM_NAME="os2kdb"`.

## Debugger command reference
| Area | Commands |
|---|---|
| Execution | `g` go · `p` step over · `t` trace into · `gh` go-til-return · Ctrl+C break in |
| Breakpoints | `bp %<flataddr>` / `bp <seg>:<off>` · `bl` list · `bc <n>`/`bc *` clear · `bd`/`be` disable/enable |
| **Hardware BP** | `ba w4 <addr>` — break on a 4-byte **write** to an address. Only **4** exist (DR0–DR3); investigate addresses in batches across boots. Ideal for "who writes this?" |
| Memory | `d %<addr>` · `dd`/`dw`/`db %<addr> L<n>` (dwords/words/bytes) |
| Disassembly | `u` / `u %<addr> L<n>` |
| Registers | `r` all · `r eax` one · `r eax=<val>` set |
| Modules/symbols | `.lm` list modules · `.lmo <name>` module objects · `ln <sym>` symbol lookup · `x <mod>!<pat>` search symbols |
| LDT/selectors | `.dl <sel>` display an LDT entry |
| Page tables | `!pte <va>` physical page for a VA (detect aliasing: two VAs → same physical page) |

**Symbols:** `ln` resolves a user-DLL address only if the matching `.sym` file is installed next to
the DLL on the VM (KDB auto-loads it); otherwise you get an unhelpful `_end + <offset>`.

## Scripting your own
`tools/kdb/` is a reusable Python library — `KDBSession` (connect / `wait_for_boot` / `send_break` /
`get_registers` / `read_memory` / `set_breakpoint` / `go` / `step` / `list_modules`) plus parsers for
registers, disassembly, memory dumps, and module lists. Build custom investigations on it.
