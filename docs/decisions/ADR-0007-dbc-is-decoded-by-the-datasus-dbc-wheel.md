## ADR-0007: `.dbc` files are decompressed by the third-party `datasus-dbc` wheel

**Date:** 2026-08-18. **Status:** superseded.
**Superseded by:** ADR-0059.

**Context.** A `.dbc` is a DBF whose payload is compressed with PKWare DCL
"implode", which no standard library reads. The first implementation
(`7b9488a`, 2026-08-18) declared `datasus-dbc>=0.1.0` and `dbfread>=2.0.7` as
runtime dependencies in `pyproject.toml` and decompressed through them.

**Decision.** Use the `datasus-dbc` wheel for DCL decompression and `dbfread`
for the DBF that results.

**Alternatives.** None recorded at the time.

**What would reverse it.** A decompressor that is slow, that prints into the
IPC pipe of a decode worker, or that fails silently. All three were later
measured (`docs/history/FINDINGS.md` §3x): `datasus_dbc.decompress` took a
steady 5.3 s to inflate 3.5 MB, and its replacement wheel printed errors from C
and signalled failure by writing a truncated file. ADR-0059 replaced both.
