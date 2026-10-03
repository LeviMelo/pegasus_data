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
