# Toxoplasmosis links: which records find each other

**Date:** 2026-10-10.

**Regime:**
- branch `links` on top of `b3900d7`;
- data home `C:/Users/Galaxy/pegasus_core_data`;
- deterministic national links (`linkage.engine.link`, `refresh=True`) with the declarations in `curation/links.yml`;
- artefacts under `lake/links/<link>/deterministic_BR_*`.

**What was counted, and why.** A link is used only when its pairs are well beyond what chance would produce. Each
link has a negative control: the left birth date (or birth year) is shifted by 7 days (or by one year) and the
pairs are counted again. `chance` is the control's pairs as a share of the real pairs. Held-out checks are fields
that are not used in the key, such as the notifying municipality and the dates.

## The birth date SINAN does not carry

SINAN has published no birth date since the LGPD rewrite. TOXC (congenital toxoplasmosis) codes the age as a unit
and a count, NU_IDADE_N. In 2019–2025, of 35,650 records:

| unit | records |
|---|---|
| days | 30,478 (85.5%) |
| months | 4,520 |
| years | 598 |
| hours | 54 |

The age in days could have been counted from one of two dates, and they were tested against each other. Counted
back from the date of first symptoms or diagnosis (DT_SIN_PRI), it gives the published birth year (ANO_NASC) in
99.7% of records. Counted back from the notification date, it gives that year in 91.8%. In 7.9% of records only
DT_SIN_PRI agrees, and in 0.04% only the notification date does. The age was therefore computed from DT_SIN_PRI,
and `birth_from_age` (`linkage/roles.py`) rebuilds the birth date from it. A record whose age is not in days has
no key.

## Measured

| link | left × right | pairs kept | chance (upper 95%) | held-out checks | verdict |
|---|---|---|---|---|---|
| TOXC 2022–23 → SIH admission (P37.1, or B58 under 2 years) 2021–23 | 11,176 × 6,295 children | 1,444 (12.9%) on birth date, sex, residence | 5.75% (7.13%) | notified where admitted 93.8%; within a year 98.1% | use with caution |
| TOXC 2019–23 → SIM certificate naming P37.1 or B58 | 20,968 × 726 | 101 (0.48%) | 6.93% (14.3%) | SINAN's own death date is the certificate's in 36 of 37; death after onset 99.0% | use with caution |
| SIH toxoplasmosis admissions 2021–23 → SIM | 6,295 × 448 | 29 | 13.8% (35.3%) | admission ended in death 37.9% | not viable |
| TOXC 2022 → SINASC 2021–22 | 4,583 × 5.24 M | 0 | 36.9% with the facility key, 52.2% without | — | not viable |
| TOXG 2022 → SINASC 2022–23 (mother's birth year, residence) | 12,447 × 5.10 M | 0 | 156% | — | not viable |

In every link, the pass on birth date and sex alone ran at 70–127% chance and was dropped.

## What this means

- **SINAN and SIH meet.** About one congenital notification in eight is found as an admission for the disease.
  - Roughly 83 of the 1,444 pairs are expected by chance.
  - Notifying and admitting municipalities agree in 94%, a check that was not used to make the pairs.
- **SINAN and SIM meet in only a few deaths.** Only 726 certificates name the disease in five years.
- **SINASC cannot be reached.** Neither side carries a name, the mother's birth date or the birth weight. Birth date,
  sex and municipality do not single out one birth among 2.6 million a year, and adding the birth facility did not
  help. The gestational form gives the mother's birth year only.
- **Capture estimation.** Of the three sources that name the disease, only one pair links (SINAN × SIH). The
  SIH–SIM link is not viable, so a three-source model cannot be fitted.
  - A two-source estimate assumes the lists are independent.
  - That fails here: a child admitted to hospital is more likely to be notified, so the estimate could only be a
    lower bound.
  - The windows above also differ (notifications 2022–23 against admissions 2021–23).
  - The estimate is left to the capture product (PegaSUS BACKLOG 2.7/6.4) on aligned years.

## Changes that made the runs possible

- `roles.yml`:
  - TOXC and TOXG roles;
  - the role types `birth_from_age` and `year`;
  - SINASC's `mother.birth_year`.
- `linkage/engine.py`:
  - an integer key shifts by units for the control;
  - a national side with a `where` filter is read one cached year at a time with the filter applied. A TOXC→SIH
    run had held 15 GB; it now stays within the 3 GB DuckDB limit.

## Stored runs named records two ways (found 2026-10-10, fixed)

The national probabilistic runs stored before the lake stamped `_record_key` (OQ-65) name their records
`<_blob_sha256>:<_row>`. Every reader since then names records by the content key (`identity.record_ids`). Each
such run therefore matched none of its side's records. PegaSUS's linked shares read k = 0 with no error: SIM 2019
gave 0 of 1,345,912 deaths paired with a birth, against 28,669 pairs. The cohort outcomes over persons were affected
the same way.

- **The fix.** `store.load` renames such a run's pairs once, to the current identity, read from the lake rows of the
  blobs it names (`_relabel`). The report then records how many names were left unmapped. `entities` now reads runs
  through `load` rather than opening the files itself.
- **Checked against the source records.** A sample of 2,000 relabelled SIM 2019 → SINASC pairs found every record on
  both sides. Birth date agrees in 99.35% and sex in 98.85%. SIM 2019 now has 28,069 expected paired deaths, and
  54.9 of the 61 P37 deaths.
- **A stale run.** CIHA 2011's file was republished after its run. All 52,461 of its CIHA names are unmapped, so it
  must be rerun. PegaSUS refuses a run whose pairs name none of a side's records (`linked_counts`), so it can no
  longer read as zero.
