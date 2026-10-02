# Link discovery, national 2022: the data reveals the hand-written keys

**Date:** 2026-10-02.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage` (national
  2022, already fetched);
- `scripts/link_discovery.py 2022 BR` (`linkage/discover.py`, ADR-0119);
- each dataset's comparable roles cached under
  `data/probes/linkage/discovery/cache/`.

**Artifacts:**
- `data/probes/linkage/discovery/<left>__<right>_BR_2022.json`, every key,
  best first;
- RR 2022 runs beside them;
- the field inventory, `data/probes/linkage/inventory/`.

**Why these counts.** The question is whether a systematic method, given only
typed fields, finds the keys the hand-written specs assert.
- **`excess_mutual`.** Pairs a key isolates beyond a placebo in which the left
  dates are shifted a week. This says whether a key *identifies* shared
  people.
- **`z_right_meets`.** Whether two datasets *share* people at all.

The yardstick is the national probabilistic link of the same pair (EVALUATION
2026-09-30 "National linkage, 2022").

## Results

| pair | rows (left / right) | best discovered key | excess mutual (×placebo) | hand-written link |
|---|---|---|---|---|
| SINASC → SIH | 2.56M / 12.5M | birth inside the stay + mother's birth date + same hospital | 1,490,175, 59.2% of births (164×) | 1,505,192 (59.7%) |
| SINASC → CIHA | 2.56M / 20.5M | the same | 188,145 (90×) | 193,335 |
| SIM → SIH | 1.54M / 12.5M | birth date + death inside the stay + same hospital | 502,724 (66×) | 545,135 |
| SIM → CIHA | 1.54M / 20.5M | birth date + death inside the stay + sex + municipality | 55,492 (4.4×; 56,138 meet against 446) | 55,983 |
| SINASC → SIM, date/sex/place only | 2.56M / 1.54M | baby's birth date + sex + residence | 2,856 (1.7×); shares people at z 49.3 (27,291 meet against 20,268) | 23,848 infant deaths |
| SINASC → SIM, with attributes (2,016 keys) | 2.56M / 1.54M | baby's birth date + mother's residence + **birth weight** | 20,675 (52×) | 23,848 |
| SIH → CIHA | 12.5M / 20.5M | still running at commit | — | none declared |

**Roraima.** Births → SIH gave 8,604 excess against the hand-written link's
8,577 pairs, with the same key.

## Findings

- **Four of five keys are what the data reveals.**
  - The hand-written keys of deliveries (SIH and CIHA) and in-hospital
    deaths (SIH and CIHA) come first or near first among 72–240 measured
    keys.
  - Their yields are within 0.5–8% of the probabilistic links. Those run
    higher because they credit typing errors, which an exact key cannot.
- **"Inside the stay" matters.**
  - Equality with the admission date found deliveries at 44% of births
    (first national run). The interval found 59%: mothers are often
    admitted the day before they give birth.
  - For deaths the interval and "= discharge" are nearly equivalent, as
    expected: a death ends the stay.
- **Infant deaths need an attribute, and discovery finds which.**
  - With date, sex and place only, births and deaths share people (z 49),
    but a death cannot be told from the dozen same-day births that share
    its key.
  - With integer and label roles allowed as one attribute (weight, weeks,
    the mother's age, delivery type, plurality: 2,016 keys), the best key
    pairs the baby's weight in SINASC with the weight SIM records for an
    infant death. It isolates 20,675 deaths at 52× chance, against the
    hand-written link's 23,848.
  - Exact equality of grams suffices for most: SIM's weight is usually
    the birth declaration's.
- **Uniqueness must be mutual.** Counting it from one side was tried first
  and gave a meaningless ratio (1.1): every newborn of a city and day
  "met" its one infant death.
- **Cost.** 41 s to 92 min a pair; the heaviest is SIH's 12.5 million
  admissions expanded to one row per stay day.
  - Computing the three shifts in one pass halved the cost.
  - The first, three-pass version took 4.3 h for SINASC → CIHA, against
    30 min after.

## Not done

- **SIH → CIHA** was still running at commit. Earlier measurement found
  0.18% of CIHA admissions matching SIH (DATA_SOURCES).
- **Tolerance comparisons** (weight within grams, weeks within one) are not
  tried; exact equality already isolates most.
- **Impossibility rules and widest-scope linking** are ADR-0119's
  consequences, not built.

## Changed

- `linkage/discover.py` (integer and label roles as one optional attribute);
  `discover_links()` in the API;
  `pegasus-data link-discover`; `scripts/link_discovery.py`.
- Roles: SINASC `birth.municipality`, SIM `death.municipality`.
