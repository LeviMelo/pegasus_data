# Error channels per setting: the scope test

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage` (lake 2022
  with record keys).
- `scripts/link_scope_test.py sih_deaths_to_sim 2022 SE RR SP`. The national
  run is recomputed, then each state is linked against the nation.
- Artifact: `data/probes/linkage/scope_test_sih_deaths_to_sim_2022.json`.
- Logs: `data/logs/rebuild_and_link.done` (before), `data/logs/scope_setting.log`
  (after).

**What is counted and why.** The pairs a state's slice keeps, against the
national run's pairs for that state. Scope invariance (theory §3.2) is the
property that a record's link does not depend on which slice it is linked
in. Each disagreement is a record whose link depends on scope.

**Before: one national channel** (record keys, national run stored):

| slice | identical | only in the slice | only in the national run |
|---|---|---|---|
| SE | 4,764 of 4,767 | 6 | 3 |
| RR | 1,215 of 1,217 | 2 | 2 |
| SP | 133,481 of 134,059 | 3 | 578 |

**The 578, examined** (`sih_deaths_to_sim`, SP):
- **Not marginal.** National scores: median 25.6 bits, minimum 21.13, the
  threshold. Only 5 lie within 2 bits of it.
- **Not taken elsewhere.** No slice pair holds either record.
- **The slice's m differs from the nation's**, because SP has its own
  120,000 anchors:
  - a residence in the same state but another municipality: −1.07 bits
    against −0.05;
  - a different state: −7.90 against −6.45;
  - a different hospital: −6.26 against −5.27;
  - a birth year off by one: +2.53 against +3.88.
- **Confirmed by forcing the national m on the slice:** 134,059 of 134,059
  identical, plus 2 more pairs.

**After: channels per setting (ADR-0123).**
- m per state is shrunk toward the national m (200 pseudo-anchors); all 27
  states received their own channel.
- National run recomputed.

| slice | identical | only in the slice | only in the national run |
|---|---|---|---|
| SE | 4,770 of 4,770 | 0 | 0 |
| RR | 1,217 of 1,217 | 0 | 0 |
| SP | 133,476 of 133,476 | 2 | 0 |

**The national run itself:**

| | pairs | estimated FDR | upper 95% | threshold |
|---|---|---|---|---|
| one channel | 551,613 (91.09%) | 0.98% | 1.01% | 21.13 bits |
| per state | 551,181 (91.02%) | 1.00% | 1.03% | 21.34 bits |

- Held-out checks unchanged: residence agrees 93.88% (93.91%); died in
  hospital 98.48% (98.48%).
- 17.7 million real candidates and 8.2 million placebo candidates.
- The national run took 18.0 minutes, against 10.7 before. Every role
  table was rebuilt in the same run, because the `roles.yml` change
  invalidated the cache, and SIH ~ CIHA discovery ran beside it. The
  ADR-0121 relink, with cached roles, re-times it.
- Slices: SE 18.6 s, RR 14.9 s, SP 200 s.

**Reading.**
- **Scope invariance is now exact to the pair** in the three states
  tested, apart from two SP pairs that only the slice keeps. Why the
  national run did not keep them was not examined. A candidate explanation,
  unverified, is the national 1:1 rule: a record in another state competing
  for the same death certificate, which the slice cannot see.
- **The yield is the same.** The channels move pairs between scopes, not
  in number.
