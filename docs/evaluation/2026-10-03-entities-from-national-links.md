# Entities from the national links: 2.39 million links merged into persons, 78 conflicts

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`;
- the seven stored national 2022 probabilistic links;
- `build_entities(period="2022", geography="BR")` (`linkage/entities.py`,
  docs/plans/linkage-theory.md §3.3, step T3).

**Why these counts.** The theory's step T3 replaces pairs with persons. Two
questions decide whether that is sound:
- **Do the links agree with each other?** A person may not have two birth
  records or two deaths, so a conflict is a link error that no single link's
  placebo can see.
- **Do routes through other links add pairs?**

## Results

**Merge.** 2,387,731 edges (stored pairs) over 4,759,478 nodes (record ×
person role) became 2,371,747 persons, in 42 s.

| persons by number of records | count |
|---|---|
| 1 | 73 |
| 2 | 2,356,150 |
| 3 | 14,991 |
| 4 | 533 |

**Edges by link:**

| link | edges | merged | already one person | refused |
|---|---|---|---|---|
| births → SIH delivery | 1,505,192 | 1,505,192 | 0 | 0 |
| births → CIHA delivery | 193,335 | 193,335 | 0 | 0 |
| SIH deaths → SIM | 545,135 | 544,643 | 489 | 3 |
| CIHA deaths → SIM | 55,983 | 55,983 | 0 | 0 |
| newborn admissions → SINASC | 67,340 | 65,242 | 2,043 | 55 |
| infant deaths → SINASC | 23,848 | 22,827 | 1,001 | 20 |
| maternal deaths → SIH | 845 | 509 | 336 | 0 |

**Refusals.** 78 in all, 0.003% of edges:
- 73 would have given one baby two birth records (55 newborn, 18 infant,
  3 SIH deaths);
- 2 would have given one person two death certificates.

**Routes.** An SIH admission and a SINASC baby belonging to one person:
**75,833** pairs, against 67,340 in the direct newborn link (+12.6%).
- 67,285 of the direct pairs survive; 55 were refused.
- The additions come through deaths: an admission that ended in death,
  its certificate, and the birth that certificate links to.

Of those triangles where both routes exist (measured 2026-10-02 on the same
links), 3,085 reach the same birth and 76 a different one (97.6% agreement).

## Findings

- **The seven links are nearly consistent with each other.** 78 conflicts
  in 2.39 million edges. The independent links rarely contradict each
  other, which no single link's placebo could show.
- **"Already one person" is redundancy, measured.**
  - 336 of the 845 maternal-death pairs were implied by the general
    SIH-deaths link: maternal deaths are a query on persons, as the theory
    proposed, not a link of their own.
  - 1,001 infant-death pairs were implied through admissions.
- **Routes through other links add 12.6% to the admission–baby pairs**, with
  no new scoring. Not all of them are newborn admissions (under 28 days):
  many are older infants whose admission ended in death, which the newborn
  spec does not cover. The split by age needs the lake (building).
- **The newborn spec's 1:1 rule was wrong on the admission side.** A baby can
  have several admissions (a transfer, a readmission), and the clear-best
  rule kept only one. Persons hold any number of admissions.

## Changed

- `linkage/entities.py`; `build_entities()`, `person_pairs()`;
  `pegasus-data link-entities`.
- `person:` declared on every spec in `curation/links.yml`.
- `linkage/store.py`: `person` is left out of a spec's digest, so declaring
  it orphans no stored run (all seven still served, checked).

## 2026-10-09: triangles as a function; sides counted through persons

- `entities.triangles(period, geography)`: each stored person link against the persons the other links make. Of its pairs whose left record another route also reaches a right record for, it counts how many reach the same record and how many another. 2021 (PegaSUS's root, 4 links stored): SIH deaths → SIM, 1,826 of 1,826 routed pairs agree; maternal deaths → SIH, 1,826 of 1,829 (99.84 %). The infant and delivery links have no second route in 2021, because the newborn-admission run is not stored. `build_entities(exclude=)` leaves links out.
- `side_counts(persons=)`: a side record the direct link missed counts as paired when its person reaches the other side's kind by another route. A record the link paired keeps its p_match, so merging whole edges does not turn p < 1 into 1. On infant deaths in 2021 it adds nothing yet (25,592.5 of 31,674), for the same reason.
- `sim_women_deaths_to_sinasc_mothers` declares `pad_years: [4, 0]`. Without it, a year's run read only that year's births, and PegaSUS's person links found 2010–2018 all not viable (one pass, 91 % chance agreement). The race bridge's own runs (scope 2012–Y) remain under their old digest.
- **One snapshot of the link specs per process.** A run's specs came from `load_links()`, cached at the first read,
  and its store digest from a fresh read of `links.yml` at save time. Editing the file while PegaSUS's links job ran
  stored unpadded women's-death runs under the padded spec's digest (`deterministic_BR_<year>_19e582a3254c`, 2,099,610
  mothers: one year's). Both now read `engine.raw_links()`, one snapshot per process. The mislabelled runs are keyed
  by the unpadded period, which no reader asks for any more.
