# Impossibility as learned evidence; padded infant deaths

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`, with its
  lake rebuilt with `_record_key`.
- Script: `data/logs/impossibility_test.py GEO SPEC…`. It runs each spec
  twice:
  - with its current comparisons;
  - with the ADR-0121 additions, from a patched copy of `links.yml`.
- Artifact: `data/probes/linkage/impossibility_evidence_<geo>_2022.json`.

**What is counted and why.**
- **The bits each new level learned.** This is m from anchors against u from
  real candidates. It shows what a violation costs once measured, rather
  than assumed.
- **The pairs kept, dropped and added, and the FDR bound.** Impossibility
  evidence is worth adding only if it moves pairs, or tightens the false
  match rate.

**A first comparison was confounded.**
- The current spec matched the stored national digest, so it took the
  nation's u and threshold. The patched spec has a new digest and used its
  own.
- The thresholds differed (23.35 against 9.17 bits) for that reason alone.
- Rerun with both variants on their own parameters.

**Sergipe 2022, both variants on their own parameters.**

| spec | pairs, current → new | dropped / added | FDR upper bound |
|---|---|---|---|
| sih_deaths_to_sim | 4,610 → 4,608 | 9 / 7 | 1.13% → 1.01% |
| ciha_deaths_to_sim | 252 → 252 | 0 / 0 | 1.46% → 1.46% |
| sim_maternal_deaths_to_admission | 25 → 25 | 0 / 0 | 14.76% → 14.76% |
| sih_neonatal_admissions_to_sinasc | 524 → 524 | 0 / 0 | 2.23% → 2.23% |

**Learned bits, `sih_deaths_to_sim`, Sergipe** (3,825 anchors):
- **Place of death, given that the admission ended in death:**

  | place | m | u | bits |
  |---|---|---|---|
  | hospital | 0.9997 | 0.886 | +0.17 |
  | home | 0 | 0.089 | −9.41 |
  | street | 0 | 0.017 | −7.05 |
  | other | 0 | 0.005 | −5.34 |
  | other health facility | 0.0003 | 0.003 | −3.46 |

- **Death date relative to admission start:**
  - The death came before the stay began in no anchor. That level scores
    −3.7 (1–7 days), −4.8 (8–28 days) or −7.2 bits (29–365 days).
  - The plausible levels carry almost nothing (−0.7 to +0.2): the other
    dates already fix them.

**Reading.**
- **The deaths links gain evidence that is real and large where it applies.**
  But in Sergipe few pairs sit near the threshold, so few pairs move.
- **The CIHA and maternal anchors are too few in one state** (21 and 7) for
  the new levels to matter.
- **The neonatal spec gains nothing.** Its left filter already restricts the
  admission to 0–28 days after the birth, so only allowed bins occur. It
  gets no `order` comparison (ADR-0121).
- **National figures follow** when the national relink, with the specs
  applied, completes. Until then this entry rests on one state.

## National, 2022 (the ADR-0121 relink, per-state channels in both runs)

Stored runs compared pair by pair:
- `lake/links/sih_deaths_to_sim/probabilistic_BR_2022_1cf164a9304d` is the
  run without the new comparisons;
- `…_6407dac6e930` is the run with them.

| link | without | with | FDR upper 95% (with) |
|---|---|---|---|
| sih_deaths_to_sim | 551,181 | 548,033 | 1.03% |
| sim_maternal_deaths_to_admission | 870 | 1,058 | 1.61% |
| ciha_deaths_to_sim | 59,470 (one channel, before record numbering) | 60,720 | 1.03% |

**`sih_deaths_to_sim`, the pairs that changed:**

| | pairs | mean p_match | place of death; death against the stay |
|---|---|---|---|
| kept by both | 545,612 | 0.992 | 98.8% hospital; 95.4% on the discharge day |
| dropped | 5,569 | 0.788 | 3,857 hospital, 882 other health facility, 444 home, 111 street, 275 other; 3,279 on the discharge day, 1,053 before the admission, 895 during the stay, 342 after discharge |
| added | 2,421 | 0.410 | 2,365 hospital, 55 other health facility; 2,106 on the discharge day |

**Reading.**
- **The new evidence removes implausible links.** About 1,050 dropped
  pairs had the death before the admission began, and about 830 had a death
  outside any health facility after a stay that ended in death.
- **It also drops 3,279 pairs that look like true ones:** death in hospital
  on the discharge day. Only 36 of the dropped admissions found another
  partner.
  - The threshold moved from 21.34 to 18.19 bits, and the new levels
    rescale scores. These pairs probably fell under the threshold or the
    clear-best margin. Their scores under the new model were not stored, so
    this is not confirmed.
- **The added pairs are weak** (mean p_match 0.41).
- **Not settled for this spec.** The scores of the dropped pairs under the
  new model have to be examined before the order and place comparisons are
  kept in `sih_deaths_to_sim`.
- **For the maternal deaths the gain is clear in number** (+188 pairs). Its
  held-out check "admission ended in death" is no longer held out, because
  that field is now compared.

## The padded partner period, national 2022

- **`sim_infant_deaths_to_sinasc`, without its same-year filter, reading
  SINASC 2021–2022:** 25,982 pairs (81.0% of about 32,080 infant deaths; the share as reported), FDR
  upper 95% 0.79%.
  - Before: 23,845 pairs (84.5% of 28,217 deaths of babies born in the
    death's year), 0.17%.
  - 2,137 more deaths reach their birth record; they are the deaths the
    old filter excluded.
- **`sih_neonatal_admissions_to_sinasc`, padded, inheriting the delivery
  AIH:** 79,272 pairs (20.4%), FDR upper 95% 1.07%. Before: 67,340
  (17.3%), 1.07%.
- **Held-out checks:**
  - infant deaths: delivery type agrees 97.74% (97.89%), plurality 99.0%
    (98.96%), gestational weeks within 2: 87.08% (87.33%);
  - newborns: born in the admitting hospital 99.99%, perinatal diagnosis
    84.7%.
