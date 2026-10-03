# Linkage speed, first pass: 58 → 9.2 minutes for the national SIH-deaths link, identical pairs

**Date:** 2026-10-02.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`;
- national 2022, data already in the lake.

**Why.** The user judged the linkage "obscenely slow" (2026-10-02). Measure
where the time goes before changing anything (CLAUDE.md §5), then check that
the faster code gives the same answer.

## Profile (Sergipe 2022, `sih_deaths_to_sim`, probabilistic, cProfile)

| step | seconds of 20.7 |
|---|---|
| reading both datasets (`role_table` → `query`) | 10.6, of which label rendering 6.2 |
| date comparison levels: dates formatted as text, row by row in Python | 7.0 |
| scoring the candidates | 1.9 |

A second profile, of a codes-only read of SIH for SP: 9.6 of 19.7 s went to
two Python loops in `_query_engine/filters.py` that attach source-file facts
row by row. There are 2.5 million rows but a dozen files.

## Changes (exact, no approximation)

- **`_query_engine/filters.py`.** Source-file facts (competence, year,
  resolution) are computed once per file and broadcast through the
  dictionary-encoded `_source_path`. The resolution backfill is vectorised.
  - Checked against the old code on SIH SE and SP, SIM SE and SINASC RR:
    every column identical except `_ingested_at`, a query timestamp that
    differs between any two runs.
  - Codes-only SIH read: SE 3.0 → 1.0 s, SP 17.7 → 9.7 s. Every query in the
    package benefits.
- **`linkage/levels.py`.** A date's DDMMYYYY digits come from calendar
  arithmetic on the whole array, not from text.
  - Identical digits and levels on 2,000,000 synthetic pairs (typos of every
    kind, nulls, swaps, century edges).
  - 22.7 → 1.2 s on them.

## Result

| run | before | after |
|---|---|---|
| SE `sih_deaths_to_sim` | 20.7 s | 9.1 s cold, 3.8 s warm; 4,579 pairs both times |
| national `sih_deaths_to_sim` | 58 min (2026-09-30) | **9.2 min**; 545,135 pairs, all 545,135 identical to the stored run; FDR 0.23% (upper 0.24%) |

## Not yet done

- **Label rendering in `role_table`** (6.2 of the SE profile's 10.6 s). The
  roles could read codes and decode only the few they need.
- **Stored role columns per dataset-year.**
- **Reuse of stored error rates and national frequencies.**
- **Pruned and sampled discovery.**
