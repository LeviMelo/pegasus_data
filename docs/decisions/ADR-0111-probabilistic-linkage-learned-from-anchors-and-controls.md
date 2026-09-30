## ADR-0111: Probabilistic linkage learns each field's error channel from leave-one-field-out anchors and sets its threshold by measured false matches

**Date:** 2026-09-30. **Status:** active. **Part of:** ADR-0107 (plan phase A4).

**Context.**
- **Exact keys miss typos.** The deterministic engine (ADR-0110) accepts a
  pair only when a whole key agrees exactly. A birth date with one mistyped
  digit or a miscoded sex loses the pair.
- **The classic probabilistic model needs two probabilities per comparison
  level:**
  - *m*: how the level falls for the same person;
  - *u*: how it falls by coincidence.
  
  Usually *m* comes from hand-labelled pairs or from EM over assumptions,
  and the acceptance threshold is chosen by eye. The user asked for a
  general, systematic method that does not rest on hand-made heuristics.
- **Our data carries its own supervision.** Records linked by every *other*
  field are the same person with very high probability, and a key shifted
  far enough produces only different people.

**Decision.** `linkage/model.py` and `linkage/probabilistic.py`, driven by a
spec's `probabilistic` block (`compare`, `blocks`, `target_fdr`):
- **Levels by type, generic (no per-link tuning).**
  - date: equal · one digit, adjacent key · one digit, other key ·
    neighbouring digits swapped · day and month swapped · year off by one ·
    other;
  - municipality: equal · same state · different state;
  - integer: equal · within 1% · within 10% · digit dropped or added · other;
  - everything else: equal · different.

  Missing contributes nothing.
- **u** from random left × right pairs (2,000 × 100).
- **m** from **leave-one-field-out anchors**: for each compared field, the
  pairs linked 1:1 on all the other compared fields, their negative control
  (a date key shifted 7 days) reported beside them. Among those pairs, the
  left-out field's level distribution is its error channel.
- **Evidence** is `log2(m/u)` per field, summed. Unseen levels get a floor of
  half an observation: rare, not impossible.
- **Candidates** come from several blocks on intrinsic roles and event
  facts. Geography is only compared, never blocked on.
- **Control.** The same candidates and scoring with the left birth date
  shifted by **400 days**, not 7. A 7-day shift often changes a single digit
  (01→08, 12→19), which a typo-aware model half-credits, so true matches
  would leak into the control. Shifting a year, a month and a day makes a
  true match compare as "other".
- **Threshold.** The lowest score at which the estimated false-match rate
  (control pairs over real pairs above it, both resolved 1:1) is at most
  `target_fdr` (1%), scanning the whole range, because the ratio is not
  monotone. Pairs are then resolved 1:1 by descending score.
- **Verdict.** The same thresholds as the deterministic engine, with the
  estimated false-match rate as the chance rate.

**Result, SIH in-hospital deaths → SIM (fresh home).**

| scope | deterministic | probabilistic | both | probabilistic only | deterministic only |
|---|---|---|---|---|---|
| RR 2022 | 1,182 (88.2%), chance 0.08% | 1,245 (92.9%), est. FDR 0.72%, threshold 10.9 bits | 1,177 | 68 | 5 |
| AC 2023 | 1,386 (77.6%), 0.07% | 1,488 (83.3%), 0.40%, 11.8 bits | 1,369 | 119 | 17 |

- **The 68 RR pairs only the probabilistic engine found:**
  - 47 have a birth-date typo (29 one digit on an adjacent key, 14 on
    another key, 3 swapped neighbours, 1 day/month swap);
  - 18 have sex miscoded;
  - every other field agrees in each;
  - all 68 have place of death "hospital".
- **Learned channels (RR 2022).**
  - Birth date: equal in 93.7% of anchor pairs, one digit on an adjacent key
    1.4%, on another key 0.8%, otherwise 3.9%. An adjacent-key digit is
    worth +4.7 bits, another key +3.3, an unrelated date −4.7.
  - Sex: disagrees in 1.6% (−5.0 bits when it does).
  - Discharge date = death date: 97.1%.
  - Hospital: 95.5%.
  - Residence: same municipality 87.1%, same state 12.9%.
- **Validation holds.** Died in hospital 99.9% (RR) and 99.6% (AC); residence
  agrees 85.5% and 91.2%. Verdict: viable in both.

**Result, the two other spine links (RR and AC 2022).**

| link | scope | deterministic | probabilistic |
|---|---|---|---|
| SIM infant deaths → SINASC | RR | 117 (59.7%) | 152 (77.6%), est. FDR 0.0% (0 control pairs; 95% upper bound 2.4%), plurality agrees 98.7% |
| | AC | 132 (64.1%) | 173 (84.0%), 0.0% (0; upper bound 2.1%), plurality 100% |
| SINASC deliveries → SIH admission | RR | 8,846, chance 1.9% | 8,577 (66.2%), est. FDR 0.83% (71 control pairs; upper bound 1.04%), obstetric diagnosis 96.0% |
| | AC | 10,003, 0.55% | 10,035 (70.0%), 0.65%, obstetric 99.2% |

- **Infant deaths.** Every deterministic pair is kept. The learned weight
  channel explains the gain: the weight on the death certificate equals the
  birth record's in 74% of anchor pairs, is within 10% in 13.6%, and is a
  dropped or added digit in 2.5% (+5.3 bits). The anchors are few (81–112
  per field in RR), so these channels are estimates to be refined nationally.
- **Deliveries needed a comparison type.** A birth day against the
  admission's interval, with levels by where in the stay the birth falls. In
  RR a 1% false-match rate first proved infeasible: one maternity hospital
  and one city carry nearly no evidence, and the deterministic run's own
  control measures 1.9% there. The model then refused every threshold but
  the top one (3 pairs) rather than exceed its target: the refusal worked as
  designed.
  
  The position in the stay separates true from coincidental pairs. Births
  fall on the admission's first day in 61–65% of anchor pairs (u 0.3%), on
  the second in 22–26%, and later in 7–9%. With that evidence the target is
  met.

**Corrected the same day.** The first figures for infant deaths (RR 174,
AC 198) came from a u sample of 2,000 left × 100 right records, drawn
unseeded. Two draws of AC gave 198 and 173. u now comes from 200,000 random
pairs over up to 50,000 distinct records per side, seeded: repeatable, and
the figures above are from it. The SIH-death figures moved by less than one
pair per thousand (RR 1,245; threshold 11.1 bits, est. FDR 0.64%, 8 control
pairs, upper bound 1.27%). Every result now reports its control count above
the threshold and a 95% upper bound (Poisson) on the false-match rate,
because a small left side (a state's infant deaths) rests the estimate on
very few coincidences.

**Consequences.** The deterministic passes stay: they are the anchors'
source and the baseline. Next: the travel flows as evidence for residence ↔ facility, typo-variant
blocks from the measured channels, and national runs.
