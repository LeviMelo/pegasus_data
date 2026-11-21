## ADR-0231: the record key is computed on read, not stored in the lake

**Date:** 2026-11-21. **Status:** active. **Amends** OQ-65's stamped content key (`normalize.engine.record_keys`);
resolves OQ #99.

**Context.** A record's identity is `_record_key`, the MD5 of its own fields in name order (a null hashed as a
marker), numbered for exact duplicates within a file (`linkage.identity`). The build stamped it on every row and the
lake stored it as 32 hex characters: random, so incompressible. On 2026-11-21 it was 15.9 GB of the 36.2 GB of lake
files that carried it (44%; 34% of an SIH-RD partition, 57% of a CIHA one), and 51% of each role table under
`<lake>/roles/` (13 GB). Every byte of it is a function of the other columns of the same row.

**Evidence.** Recomputed from each partition file's own fields, the key equals the stored one on every file of the
lake: 3,639 files checked on a 3,000-row sample, no stored key null, and every row of the files rewritten
(`reencode_lake` compares all rows before it rewrites a file). The 13 SINAN dengue and chikungunya national files
that seemed to differ did not: they carry a field `UF`, and DuckDB's Hive detection, matching names without case,
reads it as the partition's `uf` ("BR"). Read without it, all rows reproduce. Through `Lake.read`, SIH-RD Sergipe
and Alagoas 2019 (272,603 rows) and the role tables of SIM-DO 2013 and SINASC-DN 2012-2013 (7.0 M rows) came back with
identical keys after the rewrite. Cost: about 7 µs a row with the read (SIH-RD: about 80 s more for a national year's
role table, which is built once and cached).

**Decision.**

1. The lake stores no `_record_key`. The writer drops it, and the build no longer computes it. `Lake.read` computes it
   when a reader asks for it (`query(provenance="all")`, a role table): file by file, over that file's own fields
   (`key_fields`, `record_key_sql`, one definition shared with the decoder), batch by batch. A file that still stores
   a key gives it as stored.
2. A role table keeps the key as its 16 bytes (`roles.stored_form`). It holds role columns only and cannot recompute
   it; it reads the key back as the same lower-case hex.
3. `pegasus-data reencode-lake` rewrites the files of a home that store a key, value for value. A file is rewritten
   only when its key reproduces on every row. The role tables and stored runs that were current stay current
   (`store.carried_currency`): their keys hash the lake files' sizes and times, which a rewrite changes and no record
   does.
4. DuckDB reads of partition files take the partition keys from the path, never by Hive detection (`persist.duck`
   views, `drop_redundant_partitions`). A partition key that a file's own field already names is
   `partition_<key>` in the views.

**Rejected.** A 16-byte key in the lake: still 18% of it, for a value that can be computed. A shorter hash: it changes
every stored identity and widens the collision space.

**Consequences.** The stored link ids are unchanged. A raw read of a partition file has no key, and
`api.scan` gives none: identity is read through `load`/`query`.
