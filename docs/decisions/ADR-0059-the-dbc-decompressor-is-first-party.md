## ADR-0059: The DBC decompressor is first-party: a PKWare DCL "explode" in C and in Python

**Date:** 2026-08-30. **Status:** active. **Supersedes:** ADR-0007.

**Context.** The national SIH build's decode floor traced to one native call:
`datasus_dbc.decompress`, a steady 5.3 s to inflate 3.5 MB, unbuffered byte I/O
in a third-party wheel (`docs/history/FINDINGS.md` §3x). The first fix swapped
in another wheel (42× faster), which then needed an fd-redirect guard (its C
code printed errors into what is an IPC pipe inside a decode worker,
ADR-0039), an output-arithmetic check (it signalled failure by writing a
truncated file), and a fallback chain. Replaced in `fb37d1c` (2026-08-30).

**Decision.**
- `decode/_native` is the project's own DCL decompressor: `pegasus_blast.c`,
  compiled on demand against the ScopeCppSDK toolchain that Visual Studio
  ships even without the C++ workload; memory to memory, no printf, output
  bounded by the DBF header's own arithmetic.
- `_explode_py` is the same algorithm line for line: the engine where no
  compiler exists, and the correctness twin in tests.
- `datasus-dbc` is no longer a dependency (`pyproject.toml`), and the full suite
  passes with both third-party decompressors uninstalled.

Verified byte-identical to the reference across all five systems' real files,
including a 64.7 MB dengue national file inflating to 458.1 MB. One one-byte
difference is documented: the container sometimes stores 0x00 where the DBF
header terminator belongs, and every reference implementation normalises it.
Measured: explode about 83 MB/s native; a state-year fetch 45.7 s → 4.4–6 s; the
national SIH build 18.2 → 5.7 minutes under load.

**Alternatives.** The faster third-party wheel with guards. Rejected: guarding
a dependency's failure modes cost more than owning a two-hundred-line
algorithm with a published specification.

**What would reverse it.** Nothing foreseen.
