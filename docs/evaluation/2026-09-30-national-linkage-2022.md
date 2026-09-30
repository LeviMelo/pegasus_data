# National linkage, 2022: all seven links under the current engine

**Date:** 2026-09-30.

**Regime:**
- branch `linkage` at 7ea8782 (ADR-0107 to ADR-0118, ADR-0114 amended);
- data home `C:\Users\Galaxy\pegasus_linkage` (national 2022 SINASC, SIM,
  SIH-RD, CIHA, fetched live);
- `pegasus-data link SPEC --period 2022 --geo BR --method … --refresh`;
- deterministic runs 02:34–04:16; probabilistic runs in the detached queues
  `data/logs/linkage_a5_{refresh,more,infant}.ps1`, 05:17–10:29.

**Artifacts:** `data/probes/linkage/national/*_BR_2022.{json,parquet}` (one
per spec and method); `data/probes/linkage/ciha_death_residence_SE_MG_SP.json`.

**Why these counts.** A link is only usable if its false-match rate is known
and low, and if the pairs agree on what the model never saw.
- **Candidates** measure blocking cost.
- **Pairs and linked share** measure yield.
- **The estimated FDR** comes from the negative control: pairs formed across
  shifted dates that cannot be true, scored under the same threshold. The
  95% upper bound is what the verdict uses (ADR-0113).
- **The held-out validations** are fields the model does not score.

This is A5's national step (`docs/plans/linkage.md`): each link run on small
states, then a large one, then nationally.

## Results

| link | left | pairs (share) | FDR est. (upper 95%) | held-out checks | verdict |
|---|---|---|---|---|---|
| SIH in-hospital deaths → SIM, probabilistic | 605,542 | 545,135 (90.0%) | 0.23% (0.24%) | died in hospital 98.7%; residence 94.0% | viable |
| same, deterministic | | 513,956 (84.9%) | — | 99.2%; 93.9% | viable |
| SINASC deliveries → SIH admission, probabilistic | 2,520,744 | 1,505,192 (59.7%) | 0.47% (0.49%) | obstetric diagnosis 98.0%; residence 98.3% | viable |
| same, deterministic | | 1,515,701 (60.1%) | — | 98.0%; 95.6% | viable |
| SIM infant deaths → SINASC, probabilistic | 28,217 | 23,848 (84.5%) | 0.12% (0.17%) | delivery type 97.9%; plurality 99.0%; weeks ±2 87.3% | viable |
| same, deterministic | | 20,909 (74.1%) | — | 98.1%; 99.0%; 88.2% | viable |
| SIH newborn admissions → SINASC, probabilistic | 389,471 | 67,340 (17.3%) | 1.00% (1.07%) | perinatal diagnosis 85.2%; born in the admitting hospital 99.9% | viable |
| SIM maternal deaths → SIH admission, probabilistic | 1,640 | 845 (51.5%) | 0.83% (1.71%) | admission ended in death 92.8%; residence 93.6%; obstetric diagnosis 42.3% | viable |
| CIHA deaths → SIM, probabilistic | 98,211 | 55,983 (57.0%) | 0.21% (0.25%) | died in hospital 99.7%; residence 76.0% | viable |
| SINASC births → CIHA delivery, probabilistic | 2,520,744 | 193,335 (7.7%) | 0.91% (0.95%) | obstetric diagnosis 92.4%; residence 68.4% | viable |

The deterministic SIH-deaths and deliveries rows and the infant deterministic
row come from the same session, before `--refresh`. The probabilistic
deliveries result was reproduced identically on refresh.

## Findings

- **Every link certifies nationally.**
  - **Maternal deaths.** Per state they were refused as too few
    (ADR-0113). Nationally they certify: 845 of 1,640, upper bound 1.71%,
    with only 7 control pairs above threshold.
  - **Newborn admissions** certify at 1.07%. The share is low by
    construction: birth date, sex and hospital are shared by every baby born
    that day in the same maternity. The engine links only where the ICD-10
    P07 codes (ADR-0117) or other evidence separate them, and refuses the
    rest.
- **The probabilistic engine links more than the deterministic one at a
  measured error.**
  - SIH deaths: +31,179 pairs (84.9% → 90.0%) at 0.23%.
  - Infant deaths: +2,939 (74.1% → 84.5%) at 0.12%.
  - Deliveries: 10,509 fewer than the deterministic run (59.7% against
    60.1%). The clear-best rule (ADR-0113) refuses ties the deterministic 1:1
    pass accepted, and residence agreement rises from 95.6% to 98.3%.
- **Maternal deaths: an obstetric admission diagnosis in only 42.3% of
  pairs.** This is not taken as a sign of false pairs:
  - 92.8% of the linked admissions ended in death;
  - residence agrees in 93.6%;
  - the control bound is 1.71%;
  - in RR and AC the same share was 8–33% (ADR-0112), where the admission
    is recorded under the complication, as omnisus also found.
  
  Which complications, nationally, was not tabulated here.
- **CIHA's residence field holds the hospital's municipality for deaths too.**
  CIHA deaths linked to SIM agree on residence in only 76.0% of pairs, so the
  morning's delivery test (EVALUATION "CIHA's residence field tested against
  SINASC") was repeated on these pairs. Where SIM places the deceased outside
  the hospital's municipality, CIHA records:

  | state | pairs | CIHA residence filled | SIM residence elsewhere | CIHA = hospital | CIHA = SIM |
  |---|---|---|---|---|---|
  | SE | 237 | 38 | 14 | 14 | 0 |
  | MG | 8,121 | 7,208 | 2,143 | 1,970 (91.9%) | 160 (7.5%) |
  | SP | 23,869 | 20,811 | 5,653 | 4,810 (85.1%) | 815 (14.4%) |

  SP's 85.1% matches SP deliveries (85.0%). The finding in `DATA_SOURCES.md`
  is widened from deliveries to deaths. Other admission types remain
  untested. The births → CIHA residence agreement of 68.4% is the same
  artefact.
- **Blocking cost is bounded at national scale.** The largest candidate set
  is SIH deaths → SIM at 15.6 million. The infant link failed in the refresh
  queue at 05:25 (exit 1: the DOB-only block ran out of memory). After the
  ADR-0114 amendment it ran at 10:16 with 10.0 million candidates in
  13 minutes.
- **Wall clock** (data already in the lake):
  - SIH deaths 58 min;
  - deliveries 62 min;
  - newborn admissions 2 h 7 min (peak ~13 GB);
  - maternal deaths 11 min;
  - CIHA deaths 16 min;
  - births → CIHA 15 min.
  
  These are national builds of a stored link, a planning figure; a query of
  a stored link reads it from `<lake>/links/` (ADR-0112).

## What was not checked

- **Row totals against an independent figure** (TabNet births and deaths,
  2022) were not compared in this run. The left and right record counts are
  as the roles read them.
- **The newborn link's remaining 82.7%** is refused, not wrong. Which of those
  admissions a mother-side key could separate is OQ-62.

## Changed

- `scripts/ciha_residence_check.py`: the `--deaths` mode, which reads a
  stored pairs file under the data home that produced it (record ids are
  blob-scoped).
- `DATA_SOURCES.md`: CIHA residence, deaths.
- `STATUS.md` and `docs/plans/linkage.md`: A5 national.
