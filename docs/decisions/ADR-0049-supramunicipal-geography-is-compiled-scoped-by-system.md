## ADR-0049: Supramunicipal geography is compiled from the label pack, keyed by system and window, and health macroregion is not shipped

**Date:** 2026-08-27. **Status:** active.

**Context.** `normalize/geo.py` canonicalised a municipality and stopped;
"which health region is this in" had no answer
(`docs/history/FINDINGS.md` §3n, second; its heading says 2026-08-23, the
commit is `e205236`, 2026-08-27). DATASUS publishes each supramunicipal
classification as a `.CNV` keyed on the six-digit municipality code, and 139
national ones already shipped: `CIRBRN` maps 5,680 municipalities to 478 health
regions. Grouped by municipality alone, `CIRBRN` contradicts itself on 295
municipalities and `RSAUDBR` on 2,612; adding the window changes nothing;
adding the **system** takes every one to zero. Of what survives, `CIRBRN` has
46 genuinely differently named regions; `RSAUDBR` carries two regionalisations
under one name (CIH and SINASC on the older DIRES scheme, SIA and SIH on named
regions). `BR_MACSAUD` conflicts on 66% of municipalities and `MSAUDBR` on 4%.
`joins.yml` had declared `CIRAC`, Acre's 24 rows, as the national roll-up.

**Decision.**
- `geography.py` compiles memberships (98,584 rows, 140 KB) keyed
  `(municipality, classification, system, window)`. `curation/geography.yml`
  says which codelist is which classification, with its measurement.
- A roll-up is not system-neutral: an aggregate over SIH rolls up through
  SIH's regionalisation, so its totals reconcile with TabNet.
  `MembershipSet.conflicts` names disagreements rather than averaging them.
- Health macroregion is not shipped; the exclusion is recorded with its
  measurement.
- Sentinels are members (`999999`, `120000`).

**Alternatives.** Picking one system's answer. Rejected: for macroregion it
would be one system's answer for two-thirds of Brazil. Sourcing all geography
from IBGE: rejected in part, since IBGE has no health regions (ADR-0052).

**What would reverse it.** A Ministry source for health macroregions, or for
historical regionalisations.
