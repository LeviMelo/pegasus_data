# Storage: what is left to gain below the current encoding (2026-11-26, platform)

**Where the lake stands.** Every partition is Parquet, zstd 9, row groups of 262,144, dictionaries on every column but
`_row` (delta-encoded), ADR-0232. DATASUS columns are stored as the text filed in the DBF: amounts, dates, AIH numbers
and codes are strings. Intake sources already store typed values with a learned render and keep the text only where
the render fails (`raw_text`, ADR-0232); DBC datasets do not. A CNES partition holds each month's full snapshot.

**Measured on real partitions** (scratch rewrites, sizes in MB; sorting keeps `_row`, so file order is recoverable):

| Partition | Now | zstd 19, 1M-row groups | + rows sorted (crude key) | + typed numbers | Best |
|---|---|---|---|---|---|
| SIH-RD SP 2024 (2.86 M rows) | 100.9 | 95.3 (z19 only) | 102.6 (z9) | 93.2 | -8% |
| SIH-SP AL 2023 (1.82 M acts) | 16.7 | 15.0 | 17.2 | | -10% |
| SIA-PA (1.22 M rows) | 12.2 | 11.7 | 10.2 | | -16% |
| SIA-BI AL 2023 (5.09 M rows) | 108.9 | 100.4 | 90.4 | | -17% |
| CNES-PF SP 2023, one month | 41.3 | | 41.9 | 37.3 | -10% |

CNES as runs (each distinct record once, with a 12-bit mask of the months it appears in; read back row for row):

| AL 2023, 12 months | Rows | Distinct records | Now | Runs |
|---|---|---|---|---|
| CNES-PF | 913,623 | 127,693 (7.2×) | 24.9 | 3.3 (-87%) |
| CNES-ST | 48,749 | 8,086 (6.0×) | 0.53 | 0.22 (-58%) |
| CNES-EQ | 135,196 | 14,148 (9.6×) | 0.47 | 0.09 (-81%) |
| CNES-SR | 160,114 | 16,550 (9.7×) | 0.49 | 0.09 (-82%) |

Per-row lineage columns (`_source_path`, `_blob_sha256` and the rest) cost 0.2% (CNES-ST SP 2023): not worth moving.

**Reading.** SIH-RD and SIH-SP are near their floor: their bytes are values unique to each record (AIH number,
postcode, birth date, amounts), and their file order (by AIH) is already the best order. Typing numbers saves 2-3%
there. The gains are where records repeat: CNES across months (6-10×), and SIA, whose rows cluster by establishment and
procedure once sorted. Projected on the full holding (about 280 GB at today's encoding, the DBC-to-lake ratio of
2026-11-25): CNES-PF 28 to about 4 GB, SIA-PA and SIA-BI together about 30 GB less, the rest 8-10%: about 220 GB.

**Plan, each step general and reversible value for value:**
1. **Snapshot runs** for datasets that republish a whole register each month (CNES; any dataset declaring
   `snapshot: monthly`): a partition stores distinct records and their month mask; `Lake.read` expands them, so every
   reader, `_row` and version deltas (ADR-0234) see the rows they see now. The largest step.
2. **A cluster key per dataset, chosen by measurement** on a probe partition, as `raw_text.choose` chooses a render:
   candidates are the declared roles (establishment, competence, procedure), kept only if they shrink the probe; file
   order stays the default (SIH). It also prunes row groups for the commonest filter (an establishment).
3. **zstd 19 and 1M-row groups for closed partitions** (no preliminary month), by `reencode-lake` in the background:
   5-10%, decompression as fast as level 9. ADR-0232 rejected level 15 at write time; a closed partition is written
   once.
4. **Typed storage for DBF numeric fields** through the `raw_text` renders, the DBF header's declared width and
   decimals as the render: small on disk, but typed columns scan faster. Last.

Not pursued: a second file format (Vortex, Lance; FSST and ALP encodings) until DuckDB reads it as a stable extension;
whole-file archives of cold years (`xz`), which a query cannot read; splitting SIH-SP's AIH fields into a parent table,
which zstd already absorbs in file order.
