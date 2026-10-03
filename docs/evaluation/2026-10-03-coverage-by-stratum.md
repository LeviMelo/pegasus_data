# Coverage by stratum: link rates vary, but mostly with the evidence, not with coverage

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`.
- `scripts/link_coverage.py 2022 BR`, run twice: before the ADR-0121 relink
  (`data/probes/linkage/coverage_BR_2022_before_adr0121.json`) and after it
  (`coverage_BR_2022.json`).
- Each stratum's expected true-partner share is sum(p_match) / records, for
  strata of at least 200 records.

**Why.** Theory §3.1 proposed a coverage prior, P(record has a partner),
learned from the record's own fields. It is worth building only if coverage
differs between strata beyond what the comparisons already see.

**The widest spreads (after the relink):**

| link | field | stratum shares |
|---|---|---|
| infant deaths → SINASC | plurality | single 0.87, twins 0.83, triplets 0.83, **missing 0.13** |
| infant deaths → SINASC | delivery | cesarean 0.87, vaginal 0.86, **missing 0.18** |
| births → SIH delivery | place of birth | hospital 0.61, other facility 0.35, home 0.27, indigenous village 0.001 |
| CIHA deaths → SIM | payer | 0.41 to 0.80 |
| SIH deaths → SIM | state of the hospital | 0.84 to 0.93 |

**A rival explanation, tested.**
- Every live-born baby has a SINASC record, so 13% cannot be the coverage
  of infant deaths with plurality missing.
- Those certificates lack the perinatal block as a whole:

  | infant deaths | count | weight missing | mother's age missing |
  |---|---|---|---|
  | plurality missing | 2,706 | 88.1% | 79.7% |
  | plurality recorded | 29,525 | 4.1% | 3.3% |

- Their low share is **missing evidence**, which the likelihood already
  handles as "no evidence". It is not missing partners.

**Where coverage does differ** (a home birth or one in an indigenous
village has no delivery admission), the blocks already exclude the record:
it has no hospital to block on. A prior would move `p_match` but not the
decisions.

**Decision.** No coverage prior is built.
- A prior learned from link rates would mistake evidence gaps for coverage
  gaps and lower the posterior of exactly the records already short of
  evidence.
- A sound version needs coverage measured independently of the link, for
  example SINASC's own count of births by place against SIH's deliveries.
  That is noted under theory §3.1, not done.
