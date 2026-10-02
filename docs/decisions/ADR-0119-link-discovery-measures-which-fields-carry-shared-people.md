## ADR-0119: Link discovery measures which fields carry shared people; a link spec is checked against it, not only asserted

**Date:** 2026-10-02. **Status:** active. **Part of:** ADR-0107; extends
ADR-0110, ADR-0111.

**Context.**
- **A link spec asserts meaning.** It names which event two datasets share
  (a death, a delivery) and which field on one side means which field on the
  other (`admission.end ~ death.date`). Seven specs were written by hand, one
  question at a time. The user asked for a systematic method (2026-10-01).
- **Some of those assertions were ad hoc.**
  - **The maternal-deaths spec** is a subset of SIH deaths → SIM, run in
    reverse.
  - **The infant spec** keeps only deaths of children born in the death's
    year, because links ran one year at a time.
- **The fields were not read in full.** A full inventory (2026-10-01,
  `data/probes/linkage/inventory/`, 343 columns, five datasets) found shared
  concepts no spec used:
  - place and municipality of death;
  - municipality of birth;
  - race;
  - SIH's discharge-reason codes.

**Decision.**
- **`linkage/discover.py` measures, for two datasets, every key built from
  type-compatible role pairings** (date, sex, facility, municipality,
  integer, label):
  - one or two date pairings;
  - with or without sex;
  - with or without one place pairing;
  - with or without one attribute pairing (an integer or a label: weight,
    weeks, age, delivery type).
- **Each key is counted against a placebo:**
  - every left date in the key shifted by ±7 days, which keeps the weekday;
  - a true partner then disagrees, while chance agreement keeps its rate.
- **Two measures, real minus placebo:**
  - `excess_mutual`: pairs the key isolates (the value occurs once on each
    side). The key *identifies* shared people.
  - `excess_right_meets`, ranked by z: records of one side meeting the
    other. The datasets *share* people through these fields, even where
    look-alikes keep the key from telling them apart.
  
  Counting uniqueness from one side only was tried first and rejected: every
  newborn of a city and day "met" its one infant death.
- **Intervals.** A right side with `<entity>.start` and `.end` also offers
  `<entity>.day`, one row per day of the stay (capped at 60). A key can then
  test "this date falls inside that stay". Without it, deliveries were found
  at 44% instead of 59%: mothers are often admitted the day before they give
  birth.
- **Aggregates only.** No record is filtered or joined; the counts are
  group-bys. Period and geography choose publications.
- **Use.**
  - A new pair of datasets is run through discovery before any spec is
    written.
  - An existing spec is checked against the best discovered key and yield;
    where they disagree, the spec is what has to justify itself.
  - `scripts/link_discovery.py` runs every pair, caching each dataset's
    roles.
- **Roles added:** SINASC `birth.municipality` (`CODMUNNASC`) and SIM
  `death.municipality` (`CODMUNOCOR`). Both are 100% filled and were unused.

**Evidence** (national 2022, EVALUATION 2026-10-02 "Link discovery"):

| pair | best discovered key | excess over placebo | hand-written link |
|---|---|---|---|
| SINASC → SIH | birth inside the stay + mother's birth date + same hospital | 1,490,175 (59.2%), 164× | 1,505,192 (59.7%) |
| SINASC → CIHA | the same | 188,145, 90× | 193,335 |
| SIM → SIH | birth date + death inside the stay + same hospital; "most shared": death = discharge + sex + hospital | 502,724 isolated; 508,886 meet (placebo 1,120) | 545,135 |
| SIM → CIHA | birth date + death inside the stay + sex + municipality | 55,492 isolated; 56,138 meet (placebo 446) | 55,983 |
| SINASC → SIM, date/sex/place | baby's birth date + sex + residence | shares people (z 49.3) but isolates 2,856 | 23,848 infant deaths |
| SINASC → SIM, with attributes | baby's birth date + mother's residence + birth weight | 20,675 (52×) | 23,848 |

- **In all five pairs** the hand-written key is the key the data reveals, at
  nearly the same yield. The probabilistic links run a little higher
  because they credit typing errors, which an exact key cannot.
- **Infant deaths** needed an attribute. Date, sex and place show that the
  datasets share people but cannot say which of a dozen same-day births a
  death is. Allowed integers and labels, discovery picks birth weight on its
  own.

**Consequences.**
- **Tolerance comparisons** (weight within grams) are a refinement; exact
  equality already isolates most infant deaths.
- **Hard impossibility rules before scoring.** Event order and the place of
  death (a home death cannot end an admission) are rules, not penalties.
- **One link per pair and event, at the widest scope.** Subpopulations
  (maternal, infant) become filters on it; the infant year restriction goes.
- **Held-out fields** (race first) are kept out of linking on purpose, to
  measure how systems disagree on them.
- **Cost.** A national pair takes 1–90 minutes; the stay-day expansion of SIH
  and CIHA is the heaviest part.
