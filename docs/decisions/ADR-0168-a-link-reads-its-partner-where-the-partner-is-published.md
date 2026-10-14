# ADR-0168: a link reads its partner where the partner is published, and the Federal District is one municipality

**Date:** 2026-10-14. **Status:** accepted. Extends ADR-0109.

**Context.** (1) `link()` read the right side for the left's geography: `link("sih_deaths_to_sim", geography="AL")` could not
find the certificate of a Sergipe resident who died in an Alagoas hospital, because SIH is filed by the hospital's state
and SIM by residence, and the result did not say its partner side was truncated. (2) SIH-RD writes Federal District
residents with administrative-region codes (530020 ... 530180) up to 2017-12 (2017: 140,876 of 151,901 DF rows,
DATA_SOURCES), so the linkage role `patient.residence` never agreed with SIM or SINASC (530010) for DF residents of
2008-2017: the residence key of three passes could not pair them and the probabilistic residence level read "same state".

**Decision.**
- A state call reads the right side nationally unless both datasets declare the same ``setting`` property (residence or
  facility municipality, `roles.yml`); a dataset without a declared setting counts as different. The scope read is stored in
  the run's report (`scope.right_geography`) and in its key.
- Any six-digit municipality code starting 53 is Brasília, 530010, in every `municipality` role (`roles._normalise`), as the
  `MUNIC_RES_municipio` recipe and pegasus_core's `_residence_sql` already have it.

**Consequences.** State slices of SIH/CIHA links cost the nation's partner side (as PegaSUS, which always passes `BR`, already
did). The DF rule changes every cached role table (they are keyed by the role code and block, so they rebuild) and the stored
SIH links of 2008-2017 (stale until re-run, as all stored runs are, ADR-0167).
