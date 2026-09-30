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

**Consequences.** The deterministic passes stay: they are the anchors'
source and the baseline. Next: comparison types for intervals (a birth inside
an admission), the travel flows as evidence for residence ↔ facility, and
typo-variant blocks from the measured channels.
