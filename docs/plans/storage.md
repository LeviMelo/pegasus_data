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

CNES-PF AL 2023 further, every step found by counting, not told (scratch `delta.py`, `fd.py`, rebuild checked row for row):
- **Key:** greedy distinct counting found `CPF_PROF, CNES, CBO, VINCULAC, PROF_SUS` unique in every month (97,646 posts).
- **Changes:** 4% of post-months differ from the month before, 1.23 cells each (`NOMEPROF`, `MICR_REG`, `CNS_PROF`).
  First versions, presence masks and changed cells: 3.64 MB, no better than runs (3.31): the bytes are in the
  entities, not in their changes. `xz -9e` of the same tables: 2.67 MB.
- **Dependencies:** 21 columns are fixed by `CNES` (the establishment's own fields, repeated on each professional's
  row), 3 by `CPF_PROF` (name, CNS, residence). Split into establishments 0.06 + persons 1.52 + posts 1.36 = 2.94 MB.
  The persons table, names and identifiers, is the floor.
- **Across years** (one month a year held, 2012-2025): 50-72% of rows are identical to the year before, 70-80% of
  posts persist. Year partitions store each persisting record again every year; a timeline across years would not.
  2014-2015: no row identical though 53% of posts persist (a column rewritten for every record; unexplained).

Every CNES dataset, AL, same procedure (scratch `floor.py`; all 22 forms rebuilt to the original rows). Factor =
lake size now / smallest form; "queryable" is the split stored as Parquet, "archival" the split as text under `xz -9e`
or `zstd --ultra -22`. Totals: measured whole histories (IN, RC, GM, EF, EE), else the 12-month factor of AL 2023 times
the repetition across annual snapshots (estimated, one month a year held). National now: server DBC × the measured
lake/DBC ratio.

| Dataset | National lake now | Within a year (queryable / archival) | Across years | Queryable floor | Archival floor |
|---|---|---|---|---|---|
| PF professionals | 25.9 GB | 8.6 / 10.7× | 2.08× | 1.46 GB | 1.17 GB |
| ST establishments | 1.80 GB | 2.6 / 4.1× | 2.83× | 248 MB | 156 MB |
| EQ equipment | 1.07 GB | 6.1 / 8.1× | 4.02× | 44 MB | 33 MB |
| SR services | 0.96 GB | 6.2 / 7.6× | 3.10× | 50 MB | 41 MB |
| EP teams | 0.67 GB | (annual only) | | 137 MB | 92 MB |
| LT beds | 0.22 GB | 2.5 / 6.2× | 2.70× | 33 MB | 13 MB |
| HB accreditations | 0.19 GB | 2.0 / 3.8× | 2.72× | 35 MB | 19 MB |
| DC, IN, RC, GM, EF, EE | 0.22 GB | | measured whole | 28 MB | 4 MB |
| **All CNES** | **31.0 GB** | | | **2.0 GB** | **1.5 GB** |

The small datasets are larger in the lake than as DBC (DC 4.1×, EP 1.17×, HB 1.07×, LT 1.05×): one Parquet file per
state-year, each with a footer and statistics for up to 207 columns, holding a few hundred rows. Partition size should
be chosen by row count (one file per dataset when small), whatever the dataset.

Per-row lineage columns (`_source_path`, `_blob_sha256` and the rest) cost 0.2% (CNES-ST SP 2023): not worth moving.

**The lake against its sources** (every DATASUS partition held, each file's blobs sized from `fetches`): 41.3 GB of
lake from 99.3 GB of DBC, 0.42. SIH 0.44, SIA 0.37, SIM 0.42, SINASC 0.39, SINAN 0.48, CIHA 0.42, CNES 0.61.

**The compact form served** (CNES-PF AL 2023, 913,623 rows; establishments, persons and posts as Parquet, 2.47 MB
against 24.9; scratch `m2build.py`, `m2q.py`, each query in its own process):

| Query | Lake: s, peak MB | Compact: s, peak MB |
|---|---|---|
| every row and column to Python | 1.39, 572 | 0.83, 463 |
| professionals per establishment-month | 0.11, 136 | 0.16, 142 (0.17 on the posts table alone) |
| one establishment's rows, all columns | 0.40, 142 | 0.26, 99 |

The rebuild joins the three tables on key and overlapping month intervals, then expands the overlap: 0 differences
both ways. A first version expanded every table to months before joining; DuckDB matched on the key alone and
spilled 43 GB in one query. The rebuild must be the interval join, under a test.
- **Row identity.** Each month is one file and one blob, `_row` dense 0..n-1, so path and blob derive from the month.
  The file order does not: 80-84% of adjacent rows follow a key sort, and storing it costs 1.9-2.1 MB, 80% of the
  compact form. `_row` is the record identity (`_blob_sha256:_row`) of linkage, extracts and version deltas; where a
  key is found unique in every month, identity becomes `_blob_sha256` with that key and the order is not kept; a
  dataset without such a key keeps `_row`.
- **Archives.** `xz -9e` of the compact tables: 2.32 MB (-6% against its Parquet, thawed in 0.2 s). Of a whole
  partition's data columns: SIH-RD AL 2023 5.11 to 4.16 MB (-19%), SIM-DO AL 2022 0.95 to 0.86 (-9%), each thawed in
  under 0.3 s. The one form below matches these sizes, so no archive tier.

**Reading.** Event datasets (SIH, SIM) hold values unique to each record (AIH number, postcode, birth date, amounts),
but SIH-SP repeats its AIH's fields on every act row, which Parquet's per-column pages cannot see and a dependency split
removes (below). The large gains are where records repeat: CNES across months (6-10×), SIH-SP across its acts (-29%),
and SIA, whose rows cluster by establishment and procedure once sorted.

**Plan, each step general and reversible value for value:**
1. **Repetition models found by measurement, for any dataset** (nothing declared): on a probe, count repetition
   along the publication month; find a key by greedy distinct counting and the columns each part of it fixes
   (functional dependencies); store the split tables with presence masks and changed cells, a violation of a found key
   or dependency kept as an exception row, so the form is lossless whatever later months hold. Kept only where it
   shrinks the probe. `Lake.read` gives back the rows, so every reader, `_row` and version deltas (ADR-0234) see what
   they see now. Then the same across years, as one timeline per dataset and state. The largest step.
2. **A cluster key per dataset, chosen by measurement** on a probe partition, as `raw_text.choose` chooses a render:
   candidates are the declared roles (establishment, competence, procedure), kept only if they shrink the probe; file
   order stays the default (SIH). It also prunes row groups for the commonest filter (an establishment).
3. **zstd 22, the dictionary chosen per column on a probe, 1M-row groups, for closed partitions** (no preliminary
   month), by `reencode-lake` in the background. ADR-0232 rejected level 15 at write time; a closed partition is
   written once, and level 22 reads at the speed of 9.
4. **Typed storage for DBF numeric fields** through the `raw_text` renders, the DBF header's declared width and
   decimals as the render: small on disk, but typed columns scan faster. Last.

Step 1's split applies to event datasets too: on SIH-SP it found by counting 14 columns fixed by the AIH number
(`SP_NAIH`: hospital, dates, diagnoses, main procedure), a parent table (rebuilt with 0 differences).

**One form, at the archive's size (2026-11-26).** Data columns of AL partitions, MB (scratch `maxpq.py`, `spsplit.py`):

| Partition | Now (zstd 9) | zstd 22, 1M rows | + dictionary per column | + dependency split | `xz -9e` of the text |
|---|---|---|---|---|---|
| SIH-SP AL 2023 (1.82 M acts) | 16.52 | 14.91 | 13.49 | 11.72 | 11.77 |
| SIH-RD AL 2023 | 5.09 | 4.85 | 4.59 | | 4.16 |
| SIM-DO AL 2022 | 0.95 | 0.91 | 0.84 | | 0.86 |

Parquet so written reaches `xz` (SIH-SP, SIM; SIH-RD within 10%): `xz` wins only by seeing a whole row's text at once,
and the split gives Parquet the same cross-column redundancy. Reading every row of SIH-SP AL at zstd 22: 1.43-1.50 s,
against 1.29-1.31 at 9; only writing is slower, once. So the lake keeps one storage form, queryable, and no archive
tier. Projected on the DATASUS lake held (41.3 GB): SIH-SP 19.2 to about 13.5 GB, SIH-RD about -10%, SIA about -20%
(sort measured -16-17%), SIM, SINASC, SINAN and CIHA about -12%, CNES 2-4× across years: about 11 GB off, a quarter.

Not pursued: a second file format (Vortex, Lance; FSST and ALP encodings) until DuckDB reads it as a stable extension;
an archive tier, which the one form matches.
