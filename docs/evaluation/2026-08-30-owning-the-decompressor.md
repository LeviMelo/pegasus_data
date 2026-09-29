## 2026-08-30 — Owning the decompressor

*Split from docs/history/FINDINGS.md §3x on 2026-09-28; text unchanged.*

## 3x. Owning the decompressor (2026-08-30)

"Processing datasets takes minutes on a 13700H" was the right disbelief. The
national build's decode floor traced to a single native call:
`datasus_dbc.decompress`, a steady 5.3 seconds to inflate 3.5 MB — unbuffered
byte I/O in someone else's wheel. The first fix swapped in another wheel
(42x faster) and immediately needed an fd-redirect guard (its C code printf's
errors into what is an IPC pipe inside a decode worker), an output-arithmetic
check (it signals failure by silently writing a truncated file), and a
fallback chain. A working speedup wearing a pile.

The user called the pile what it was, and the pile is gone: `decode/_native`
is the project's own PKWare DCL "implode" — `pegasus_blast.c`, compiled on
demand against the ScopeCppSDK toolchain VS ships even without the C++
workload, memory to memory, no printf, output bounded by the DBF header's own
arithmetic; and `_explode_py`, the same algorithm line for line, the engine
where no compiler exists and the correctness twin in tests. Byte-identical to
the reference across all five systems' real files (a 64.7 MB dengue national
inflating to 458.1 MB included), with one instructive one-byte diff: the
container sometimes stores 0x00 where the DBF header terminator belongs, and
every reference implementation normalises it — found by the golden diff, now
documented in ours.

Numbers: explode ~83 MB/s native; state-year fetch 45.7 s → 4.4–6 s;
national SIH build 18.2 → 5.7 minutes under load; the full suite passes with
both third-party decompressors uninstalled from the environment.

The general lesson joins 3u and 3w: **guarding a dependency's failure modes
can cost more than owning the algorithm** — especially when the algorithm is
two hundred lines with a published specification and the guards have to
defend an IPC protocol from a printf. And scale followed the fix: with decode
at engine speed, ten SINAN agravos built nationally (2021–2023) in under ten
minutes total, and the recipe generator declared all 58 from the curation
that already knew them — 62 aggregates declared, 15 built, the frontend's
grouped picker showing exactly which is which.
