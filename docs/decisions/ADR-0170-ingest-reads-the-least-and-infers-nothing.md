# ADR-0170: ingest reads the least, infers no type, and keeps its scratch where `work` says

**Date:** 2026-10-14. **Status:** accepted. **Origin:** the ingest review of 2026-10-14 (findings 4, 5, 16, 19, 22, 25).

**Context.** Four faults had one root: a layer produced a fact and the next layer re-derived or overwrote it.
`profile` fetched and fully inflated each stratum's file to read the header the census already held (57.5 GB of
sampled files of the 2,421 table-file strata in the local catalog; 331 files, 1.7 GB, needed). The CSV reader let Arrow infer types (`0301010072` an integer), the DBF
reader chose a codepage from the first 512 records (cp850 for a file whose accents start at record 1,501), and the last
container censused overwrote a signature's declared types with another container's `C`/0 (20,784 SIASUS DBCs).
Decoders made their temporary files on the system drive whatever `work` said.

**Decision.**
- The header census answers what a header can. `profile` reads one file per family still lacking value statistics
  (the smallest); the other strata of the family are recorded `ok` from the census once their family is profiled. A
  stratum whose file is an archive, that names a member, or whose signature repeats a field name, is read as before.
- Text is read as text. CSV columns are strings, whatever they look like; Parquet and CSV honour the column projection.
- A DBF has one codepage, scored on the records that carry a byte above 127, found by scanning the whole body (one
  comparison per block); recorded in the table's warnings as `encoding:<x>` when it mattered.
- A header fact declared by a real header is never replaced by one that declares nothing (width 0).
- Decoder scratch (inflated DBFs, spools, staged archives) goes to the `work` placement: `decode_source` exports it as
  `PEGASUS_WORK_DIR` for itself and its worker processes; the janitor also covers `pegasus_duck_`, `pegasus_arc_` and
  `pegasus_blast_`, and `BlobStore.sweep_staging` runs when a pipeline opens.

**Evidence.** `docs/evaluation/2026-10-14-ingest-review.md`.

**What would overturn it.** A family whose strata differ in value distribution enough that one sampled file misdescribes
them (the profile is per family already, so only if families prove too coarse); a DATASUS CSV whose numeric columns the
profiler needs typed (it reads strings; typing belongs to normalisation).
