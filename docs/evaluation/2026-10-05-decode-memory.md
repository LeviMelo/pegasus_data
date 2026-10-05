# Decode memory, machine-wide admission, and the label-pack build

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
12.0 (see below: legitimate), registries 6.2, lake 0.4.
`pegasus_core_data`: blobs 15.4, registries 3.5. `%TEMP%`: pytest-of-Galaxy 4.0, claude 3.6, about a dozen
0.2 GB `tmp*.sqlite`/`tmp*` seed copies from fresh-install runs. `pegasus_project/pegasus_home`: gateway 0.55.
Proposed retention: delete `%TEMP%/pytest-of-*` and `tmp*` older than a day; blobs LRU-pruned to a budget
(`pegasus-data` prune exists, ADR-0108-era storage entry); gateway cache keyed by data version, drop old versions.

**Catalog size is not a defect.** `catalog.sqlite` is 12 GB (3.1M pages, no free pages): `dictionary` 22.3M rows
(4.0 GB) + five indexes (4.8 GB), `code_tables` 12.7M rows (2.9 GB incl. its key), `dictionary_conflicts` 0.66M. Of the
22.3M dictionary rows, the 15.15M under a bound codelist are 15.15M distinct (system, codelist, code, window) keys: no
duplicated rows (the 18.9 -> 12.0 GB compaction already removed those, 2026-10-04 entry). The seed (0.2 GB) simply omits
this table. Optional further 3 GB: drop `ix_dict_group_label` (1.1 GB; no reader found) and `ix_dict_lookup` if a query
plan check shows `ix_dict_field` serves them; not done.

**Label-pack build memory.** `build_label_pack` streamed the cursor but accumulated every row in dicts keyed by
(codelist, code, window): about 1.2 KB per row, so 15M rows reached 10+ GB private. Now the normalised rows go to a
scratch SQLite file, the per-key collapse, the incoherent-kit drop and the run merge are sorted streams over it, and
the output runs are Arrow-encoded in 200k-run chunks. Equality: SINASC+SIM+SIHSUS subset (3.77M rows, 3.68M runs) gives
an identical pack (sorted compare of all columns), peak RSS 4.7 GB -> 1.5 GB, 369 -> 495 s. Full catalog: 27 min, RSS
1.95 GB when last sampled (12 min in), completed. Against the shipped pack: 4,219,910 -> 4,207,326 rows. SINASC
RACACOR loses the hybrid codes (5 "Preta", 6-8 "Ignorado": 8 -> 6 rows; `translate` of 5 is now null); SISCAN RACACOR loses
09 and a header fragment. The same minority-kit rule also removes 12,733 rows, mostly SIH `CIDX*` duplicates with an empty
window and 3,174 codes with no remaining label (UNISAUMG 432, UNISAUBA 241, BR_REGMETR 199 ...): a coverage cost of the rule,
for the owner of that rule to judge. 149 rows are new (SISPRENATAL CBO_02, CIHA TP_FINAN, EVODENG). The pack, the
manifest checksum and `translate()` were updated; the seed was not regenerated.

`scripts/profile_hotpaths.py {query|stream|narrow}` measures a national `query` (peak process-tree RSS), the per-UF
streaming alternative (same row/group checksum) and dictionary-encoding of the same columns. First reading, SIM.DO 2022,
5 columns: 61 MB plain -> 29 MB dictionary-encoded; whole run 1.0 GB, of which the table is 6%.