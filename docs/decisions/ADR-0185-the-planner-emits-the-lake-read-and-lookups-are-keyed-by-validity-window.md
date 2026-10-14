# ADR-0185: the planner emits the lake read and `load` executes it; reference lookups are keyed by validity window

**Date:** 2026-10-14. **Status:** active. **Amends:** ADR-0163 and ADR-0164 (where the files and the families of a read are decided).

**Context.** One question, "which lake files does this read open?", was answered in three places that could disagree:
`plan()` (the coverage decided which years the lake holds and which of their publications to read, then threw the files
away), `query()` (one `load` call per distinct geography group, each narrowing the catalog's list by `uf`/`years` again) and
`load`/`scan` (the same narrowing, and the national-or-states rule applied a third time on partitions). Two resolvers named a
dataset's families (`retrieve._families` for the coverage, `api._resolve_family` for the read; equal on the real catalog's 184
dataset spellings), two copies of the partition row (`LakePartition`, `_LakePart`), two copies of the missing-column rule
(`_read_generations`, `scan`), and a copy of `curation.system_spellings`. Separately, every cache of what a reference table
gives (code -> label map, contradictions, the merge of a field's tables) was keyed by the month asked: a year of a monthly
dataset derived the same table twelve times, and 12 months x 24 tables = 288 keys in a 256-entry LRU missed on every call
(0.34 s of a 0.84 s warm labelled SIH-RD state-year was `_contradictions_uncached`).

**Decision.**
- **The plan carries the read.** `RetrievalPlan.lake_partitions` is the exact list of lake files of one reading of each lake
  year (the national file or the states', never both), every one on disk when planned. `query` calls `load(partitions=...)`
  once; `load` opens those files. A caller with no plan (`load(uf=, years=)`, `scan`, `export(stream=True)`) gets the catalog's
  list narrowed by the same rule (`coverage.one_reading`). `_query_engine/readplan.py` holds `plan_lake_read` (families, axis
  refusal, schema census, files), `resolve_family` (the one family resolver; the coverage uses it, `curation.system_spellings`
  replaces the local copy), `require_known_columns` and `generation_columns` (the one missing-column rule of `load` and `scan`).
  `LakePartition` carries the sources it was built from (`listed_partitions`), replacing the coverage's own partition type.
- **Lookups are keyed by validity window.** `persist.reference.reference_vintage` maps a month to the first month answered with
  the same validity windows (`labelpack.select_windows`, the one rule of pack and warehouse) and `lookups` keys every derived
  value by it. The decisions a read records (a window not covering the month, a borrowed copy) are recorded on every call for
  the month asked, so a cached read reports what an uncached one does (a repeated `load` had lost them).

**Consequences.** One `load` per query whatever the mix of national and state years. The plan and the read cannot disagree on
the files. `fetch`'s own selection (`retrieve._select_files`, `retrieve._families`) is unchanged. Rendering still makes one group per
month; merging months whose windows are identical across every table a render consults is left (OPEN_QUESTIONS 80).
