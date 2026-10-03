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
