# Decode memory: why a worker reached 4-9 GB, and machine-wide admission

2026-10-05, branch pegasus-core-fixes, shared `pegasus_core_data` home. Machine: 31.6 GB RAM, paging at 99%
with ten `pegasus_data.decode._worker` processes at 4-9 GB private each.

**Cause (`decode/_native/__init__.py`).** `explode()` returned `bytes(out[:n])` where `out` is a
`ctypes.c_ubyte` array: slicing a ctypes array builds a Python **list of n ints** (8 bytes each), so the
inflated DBF cost 8x its size, plus the zero-filled array, the `bytes` copy and `header + body` (about
10x in all). A 2 GB inflated SIH/SIM DBF is 16-20 GB. Every other step of the DBC path already streamed.

**Fix.** `dbc_file_to_dbf` inflates the DCL stream straight into a memory-mapped destination file (the C
engine is unchanged); `explode()` returns `ctypes.string_at`. Output is byte-identical (sha256 of the
inflated DBF, two SIH-RD blobs of 16 MB):

| 16.3 MB `.dbc` -> 148 MB DBF | before | after |
|---|---|---|
| time | 5.31 s | 1.55 s |
| peak working set / commit | 1541 / 1534 MB | 190 / 48 MB |
| decode worker peak RSS, full job through `DecoderPool` (221,477 rows) | - | 450 MB |

Regression run, same code: `query("SIM.DO", period=2022, geography="BR", select=[5 columns],
present="codes")`: 1,544,266 rows, 20 s, peak process-tree RSS 1.0 GB (artifact: `prof.py` scenario, scratch).

**Admission (`decode/admission.py`).** A job takes one of N slot files (OS locks under the temp dir; N =
`PEGASUS_DECODE_SLOTS`, else RAM // 8 GB + 1 clamped to 2..6: 4 here), then waits while available RAM is
under `PEGASUS_MIN_FREE_GB` (default max(4 GB, 15%)); bounded by `PEGASUS_ADMISSION_WAIT` (1800 s), then it
runs with a warning. Measured, three processes decoding the same blob: 1 slot 5.7 / 11.5 / 17.2 s
(serialised), 3 slots 6.3 / 6.1 / 6.2 s; under 6 GB free the same jobs waited (38-49 s). A worker that keeps
over 1.5 GB after a job is recycled.

**Disk, 2026-10-05 (C: 88 GB free).** `pegasus_data/pegasus_data_home` 36.3 GB: blobs 17.8, `catalog.sqlite`
12.0 (it was 0.2 GB as shipped; unexplained growth, to be examined), registries 6.2, lake 0.4.
`pegasus_core_data`: blobs 15.4, registries 3.5. `%TEMP%`: pytest-of-Galaxy 4.0, claude 3.6, about a dozen
0.2 GB `tmp*.sqlite`/`tmp*` seed copies from fresh-install runs. `pegasus_project/pegasus_home`: gateway 0.55.
Proposed retention: delete `%TEMP%/pytest-of-*` and `tmp*` older than a day; blobs LRU-pruned to a budget
(`pegasus-data` prune exists, ADR-0108-era storage entry); gateway cache keyed by data version, drop old versions.
