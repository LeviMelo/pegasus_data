# Performance pass: linkage 6.5x, role builds 1.9x, lake builds 1.9x, every output identical

**Date:** 2026-10-03.

**Regime:**
- branch `linkage` (commits `4831fff`, `6784bf9`, `ad4c4e3`, `c2e98e0`);
  data home `C:\Users\Galaxy\pegasus_linkage`.
- Other national jobs ran on the machine during every timing (20 logical
  cores, 32 GB). The times are comparable within a row, not as absolute
  benchmarks.

**Why.** The user found the near half-hour runs suspicious: they suspected
the code did not use its libraries' strengths. A Sonnet agent reviewed the
code. cProfile then measured where the time went, and the profile decided
the order of the fixes.

**Where the time went** (cProfile, `sih_deaths_to_sim`, SP slice against
the nation: 6.0 million candidates, 1.6 million placebo; 289 s under the
profiler):

| part | seconds | share |
|---|---|---|
| DuckDB queries | 166 | 57% |
| levels and bits on Python string arrays (`np.unique`, `astype(str)`) | about 54 | 19% |
| `_one_to_one`: a Python loop with four dicts | 26 | 9% |
| `_score_stream`: ids pulled into Python lists | 26 | 9% |

The SQL cost had three sources:
- the candidate join was built three times (u, scoring, placebo);
- every join was on 32-character record-key strings;
- every value fetch re-deduplicated the whole of each side
  (`SELECT DISTINCT ON (_id) * FROM L`).

**Changes, each verified against the previous code on the same data.**

1. **Linkage engine** (`linkage/probabilistic.py`):
   - each side is materialised once, with an integer `_id` (0..n-1);
   - the candidate tables `C` and `CS` (placebo) are built once;
   - the placebo side is a table, not a view;
   - levels are factorised (`pandas.factorize`) and scored by gather, with
     a bits matrix per setting;
   - `_one_to_one` is vectorised (`lexsort` per side);
   - ids stay as int64 arrays until the final pairs.
2. **Date levels** (`linkage/levels.py`): digits are computed once per
   distinct day, and equal dates skip the digit comparison. On 3 million
   synthetic pairs covering every level and missing values: identical,
   1.74 s → 0.51 s.
3. **Labelling** (`view.py`): six places walked every row to build sets
   and maps of a few dozen codes (width check, observed codes, bridges,
   labelled codes, hierarchy levels). They now work once per distinct value
   (`_per_distinct`, `_distinct`).
4. **Lake build** (`build.py`): partitions are built concurrently, as many
   as the decoder pool has processes (4). Each has its own counters
   (`BuildStats.merge`); the catalog serialises its own writes.

**Results.**

| measurement | before | after | identical? |
|---|---|---|---|
| `sih_deaths_to_sim`, SE slice | 57.9 s | 6.8 s | 4,770 pairs and bits, candidates 85,038 / 46,994, FDR bound, validations |
| `sih_deaths_to_sim`, SP slice | 274.5 s | 41.9 s | 133,478 pairs and bits, candidates 5,982,743 / 1,584,425, FDR bound, validations |
| `sih_deaths_to_sim`, national | 10.7 min (18.0 with a cold role cache) | 3.3 min | (ADR-0121 specs; not a like-for-like pair check) |
| cold role build, CIHA PR, all 16 roles | 26.2 s | 14.2 s | full table equal, 1,424,926 rows |
| full labelled `query("SIH-RD", 2022, "SE")` | 22.3 s | 17.1 s | 107,788 × 119 table equal |
| lake build, CIHA 2022 (26 partitions, 307 files) | 182.1 s | 96.3 s | per partition: rows, record keys, row order and an all-column hash equal |

The national 3.3 minutes ran on the first engine change (1) only. The
other national links of the ADR-0121 relink, on the same code, took
2.2–7.9 minutes; the 7.9 included rebuilding CIHA's role cache.

**Also measured.**
- **Discovery.** One SIH ~ CIHA key count takes 4.8 s on Arrow-registered
  tables and 4.5 s materialised, so materialising is not worth it. The 28
  minutes of SIH ~ CIHA discovery are about 200 keys at this cost, plus
  5.6 minutes of role rebuilding.
- **The role cache.** Its key includes the code of `roles.py`. Tonight's
  edits to record identity rebuilt every role table, which cost 336 s for
  SIH and CIHA. The key stays broad: a stale role table would be a silent
  error. The cold build is now 1.9x faster instead.

**What remains** (SP slice after the changes, about 40 s under the
profiler):
- levels 14 s, of which dates 7.4 s;
- SQL 7.8 s;
- `pandas.factorize` 5.5 s;
- 1:1 resolution 4.6 s.

The next step would be level functions returning integer codes instead of
strings, which removes the factorise and the object-array fills (about a
quarter of what is left).
