# A unified theory of linkage for pegasus_data (proposed)

**Written 2026-10-02, at the user's request.** The ideas of the last sessions
were valuable but scattered:
- link discovery;
- scope dependence;
- evidence borrowed through other links;
- impossibility as evidence;
- race as the clerk's classification;
- checkbox versus handwriting errors;
- speed.

This document integrates them into one model. It is a **proposal for
discussion**: nothing here is decided until it becomes an ADR, and each part
names the measurement that would accept or refute it. What exists today is
ADR-0107 to ADR-0119 and `docs/plans/linkage.md`.

---

## 1. What linkage must deliver: goals and constraints

**Goals:**
- **G1. Meaning.** A person's records across systems, so that questions
  needing two systems can be asked. For example: mortality by birth weight,
  outcomes of a delivery admission, cause of death after an admission.
- **G2. Measured error.** Every link carries its probability of being wrong,
  and every analysis can carry that error forward. A wrong link is worse than
  no link (CLAUDE.md §3).
- **G3. Systematic.** No hand-asserted meaning beyond what the data cannot
  reveal; what can be measured is measured (ADR-0119).
- **G4. Scope invariance.** The same pair gets the same answer whether one
  links a state-year or the country over a decade.
- **G5. Bias made visible.** Race and other recorded attributes differ by
  setting (the clerk's classification, not self-declaration). Linkage must
  measure that difference, not hide it, and must report whom it fails to
  link.

**Constraints:**
- **C1.** A laptop: 32 GB RAM, about 177 GB of disk, one FTP connection.
  Nothing links all of DATASUS at once.
- **C2.** No personal identifier in the public files. Identity is inferred
  from attributes and shared events.
- **C3.** The fields are produced by two different processes:
  - paper forms with checkboxes and handwritten digits, later typed in;
  - software and exports that map codes between systems.

---

## 2. The objects

### 2.1 Entities and records

- **Entities are latent.** A *person* (a mother, a baby, a patient) and an
  *event* (a birth, an admission, a death) are never observed directly.
- **A record is an observation of an event by a setting.** A SINASC
  declaration observes a birth. An SIH AIH observes an admission. A SIM
  certificate observes a death.
- **A record names persons in roles:** a birth declaration names a baby and
  a mother; an AIH names a patient. Roles are typed by concept (`roles.yml`,
  the field inventory of 2026-10-01).
- **A setting** is whoever produced the record: system, hospital or
  registry, municipality, year, and the software in use.

Linkage is the inference of which records observe the same entities. Its
output is not pairs but a **partition of records into entities** (persons,
with their events), each assignment carrying a probability.

### 2.2 What a record says about its entities

For an entity with true attribute values `x*` (birth date, sex, residence,
race, …), a record from setting `s` reports

```
x_r = channel_{f,s}(x*)
```

The channel depends on the **field kind** `f` and on the **setting** `s`. The
channels are where all of the past sessions' findings live.

| field kind | process | channel |
|---|---|---|
| handwritten digits (dates, weight) | written on paper, typed later | typo channel: a digit substituted (adjacent keys more likely), neighbouring digits swapped, day and month swapped, year off by one, or missing |
| checkbox categories (sex, race, place, delivery type) | a box ticked, then codes mapped by software | a confusion matrix `C_s[i→j]` per setting. Errors are systematic, not random: a whole category can map to another when one system's codes are written into another's (the SIH "asian" hypothesis) |
| place fields subject to substitution | a field replaced by the place of care | with probability `π_s`, residence = the facility's municipality (CIHA, ADR-0115) |
| derived fields | copied or computed from another field | **no independent evidence.** SINASC's baby race is the mother's (100.0% in 2022); SIH `MORTE` derives from `COBRANCA`. Declared as dependencies, counted once |
| event relations | the order of a person's events | birth ≤ admission ≤ death, the birth inside the mother's stay. These are **soft** constraints: a violation has a measured probability (recording errors; EVALUATION 2026-10-02 "Impossible pairs") |

### 2.3 Hierarchical channel parameters

A channel's parameters (typo rates, the confusion matrices, substitution
rates) are **partially pooled**:

```
θ_setting ~ around θ_system ~ around θ_national
```

- **Large settings estimate their own parameters; small ones borrow
  strength.** A hospital with thousands of linked records gets its own
  confusion matrix, and a small one is shrunk toward its system's.
- **Differences survive where the data show them.** This is the standard
  multilevel (empirical-Bayes) estimate.
- **The parameters stop depending on the slice being linked** (G4), because
  they are estimated once, over everything linked so far, and refined as more
  is linked.

---

## 3. Deciding identity

### 3.1 The posterior of an assignment

For a record `r` and a candidate entity `E`:

```
P(r belongs to E | data)   ∝   prior(r, E)  ×  Π_f  likelihood_f(x_r,f | E)
```

**The likelihood.** Each field's likelihood is the channel probability of
what `r` reports, given what the entity's records say:
- **For a field the entity carries:** the channel (typo, confusion,
  substitution) of §2.2.
- **For a field it does not carry:** a factor of 1. No evidence either way.
- **The non-match alternative:** for a field value `v`, the chance a stranger
  shows it is the **frequency of `v` in the national population**. These are
  value-specific frequencies, counted once per dataset-year without linking
  anything. Agreeing on a rare birth date or a small municipality weighs more
  than agreeing on a common one.

**The prior** replaces today's implicit candidate-pool prior with a model of
the event:
- **The coverage model, P(r has an entity in dataset D').** Does this death
  have an SUS admission? That depends on the place of death, age, state and
  year. Does this admission's death have a certificate? Nearly always. It is
  learned from the record's own fields, hierarchically, and does not depend on
  the slice.
- **Given coverage, the prior on a particular candidate** is one over the
  number of people in the national population who share the blocking key.
  That is a frequency count, not the pool size of a run.

### 3.2 Scope invariance (G4)

Suppose that:
- the channel parameters come from §2.3;
- the non-match frequencies and the prior come from national counts;
- the partner side is searched nationally, over a period padded by a few
  months.

Then a record's posterior is **the same whether it is linked alone, in a state
slice, or in a national decade**. The national partner search only supplies
the competitors (the true partner and its look-alikes). It costs time
proportional to the slice, because candidates are looked up by key, not
scanned.

What remains scope-dependent:
- **The variance of estimates.** It shrinks as more is linked.
- **Records whose true partner lies outside the padded period.** They are
  rare and measurable.

### 3.3 Collective resolution: entities gain fields (the user's idea)

When a record joins an entity, the entity **gains that record's fields**, and
later comparisons are against the entity, not a single record.

**Example: the newborn.**
1. An SIH newborn admission carries a birth date, sex, hospital and the
   mother's municipality. About a dozen same-day births match it equally.
2. The mother's delivery admission links strongly to SINASC (59.7% of births
   at 0.49%) through the mother's birth date. The mother entity then holds a
   hospital and a stay window.
3. The baby born in that stay, in that hospital, is a far smaller set: one
   baby, or twins. The newborn admission can now be compared with the baby
   entity, which holds the birth weight, gestational weeks and the mother's
   identity.

The same mechanism gives a death certificate the residence an admission
recorded, or an admission the cause of death the certificate recorded.

**The algorithm.** Iterate:
1. Link the strongest relations first.
2. Merge each record into its entity with the posterior as its weight.
3. Recompute the entity's attribute posteriors (a field seen in three records
   is better known than one seen once).
4. Re-score the remaining records against the enriched entities.
5. Stop when nothing changes.

**The constraints that keep it sound:**
- **Entity structure.** One birth record per baby, one death per person, one
  delivery per mother and day, twins counted.
- **Transitivity.** If A~B and B~C then A~C. A triangle that will not close
  flags an error rather than being forced.
- **Only high-posterior links propagate fields.** A weak link must not lend
  weak evidence to the next link: error amplification is the main risk of
  collective methods.

### 3.4 Calibration of the whole pipeline (G2)

Today the placebo (a birth date shifted by 400 days) calibrates one pairwise
run. Under collective resolution the placebo must run **end to end**:
- shift the dates of one dataset;
- run every step, including propagation;
- count the entities that still form.

That is the false-link rate of the *system*, propagation included. Two more
checks are added:
- **Held-out fields.** Never used as evidence, compared on the result (died
  in hospital, perinatal diagnosis).
- **A gold standard.** A hand-reviewed sample of borderline assignments,
  plus external figures where a study with identified data reports the same
  quantity (CIDACS).

---

## 4. Which relations exist: discovery as structure learning

- **ADR-0119 measures which datasets share entities and through which
  fields.** It counts every key from type-compatible roles against a placebo,
  and it found every hand-written key.
- **In this theory discovery learns the schema graph.** Its nodes are record
  types; its edges are events two record types observe. It also says which
  fields are comparable evidence.
- **A person confirms the meaning of each edge** ("this is the same death"),
  the only judgement the data cannot make.
- **The seven link specs become edges of that graph.** "Maternal deaths" and
  "infant deaths" stop being links: they are queries on entities (a death of
  a woman with an obstetric cause; a death of a baby under one year).

---

## 5. Fields that must not be evidence

**A field studied as an outcome or an exposure is not identity evidence.**
If race were used to link, the links would favour people whose race agrees
across systems, and every race comparison on linked data would inherit that
selection.

So race, and any field under study, is held out of identity, and is instead
modelled by the channel of §2.2: per-setting confusion matrices, a
Dawid–Skene model across the settings that observed the same person. This
delivers G5:
- **Each setting's classification relative to the others.** "Hospital H
  records as brown people other settings record as black, by so much."
- **A consensus class per person.** The settings' agreement, net of each
  one's tendency. It is not self-declaration: under the premise that clerks
  classify, there is no self-declared record to recover.
- **Corrections or bounds** for race-stratified rates computed from any one
  system.

**Linkage selection is itself reported.** Every entity table carries link
rates by state, year, setting type and recorded race. An analysis on linked
data shows whom the linkage could not reach.

---

## 6. Carrying linkage error into analyses (G2)

Every assignment has a posterior. An analysis can:
- **restrict** to entities above a probability;
- **weight** by it;
- **multiply impute** the uncertain assignments (draw entity partitions from
  the posteriors, analyse each, combine).

The third is the honest default for estimates sensitive to a few hundred
links, such as small groups or rare outcomes.

---

## 7. Computation on a laptop (C1)

| store | what | size, order of magnitude |
|---|---|---|
| linking fields per dataset, year and state | the role columns as compact integers (dates as days, codes as ints), tied to the catalog's source files so a republished file invalidates them | hundreds of MB per year for the four systems |
| national value frequencies | counts per field value, per dataset-year | MB |
| partner index | the linking fields sorted by the blocking keys, for lookups | the same files, sorted |
| channel parameters | hierarchical estimates, versioned | KB–MB |
| entity store | record → entity, with posteriors and provenance; updated incrementally as data are added or republished | about one row per linked record |

**Costs:**
- **Linking a slice** is proportional to the slice: lookups into the partner
  index.
- **The first pass** (2026-10-02) already took the national SIH-deaths link
  from 58 to 9.2 minutes with identical pairs. The stores above remove most
  of what remains (reading and decoding).
- **Collective resolution** iterates over records not yet resolved, so
  later rounds are small.

---

## 8. What this replaces, and what it keeps

**Kept:**
- roles and the field inventory;
- the probabilistic comparison levels and their learned m/u (they become the
  channels);
- the placebo;
- held-out validations;
- the clear-best rule (it becomes the entity constraint);
- discovery;
- the CIHA residence finding (it becomes the substitution channel);
- impossibility as evidence.

**Replaced:**

| today | becomes |
|---|---|
| seven hand-written pairwise specs | edges of a discovered and confirmed schema graph |
| per-run m/u | hierarchical channel parameters |
| the pool-size prior | a coverage model plus national frequencies |
| pairs | entities |
| maternal and infant links | queries on entities |
| "equal / different" for categories | per-setting confusion matrices |

---

## 9. Path, each step accepted by a measurement

| step | builds | accepted when |
|---|---|---|
| T1 | stores (§7): compact linking fields tied to the catalog, national frequencies | the national SIH-deaths link gives the same pairs, faster |
| T2 | hierarchical channels and frequency-based non-match; coverage prior; national partner search | **scope test.** Sergipe linked alone, in its state slice and inside the national run gives the same assignments, within the measured variance |
| T3 | the entity store and collective resolution, starting with mother–baby: births, deliveries, newborn admissions, infant deaths | the newborn yield rises from 17.3% with the end-to-end placebo FDR still at or under 1%, triangles closing, held-out checks holding |
| T4 | categorical confusion channels (Dawid–Skene); race held out; link rates by group | per-setting matrices stable across years; the "asian" code-mixing hypothesis confirmed or refuted by setting |
| T5 | error propagation into analyses (weights, multiple imputation) | an analysis's interval widens by the linkage uncertainty it should carry |
| throughout | gold standard: a hand-reviewed sample, external benchmarks | the placebo FDR and the reviewed error agree |

## 10. Risks and open problems

- **Conditional independence.** Fields are not independent given identity:
  hospital and residence, dates within one record. The likelihood must model
  known dependencies (ADR-0115 did so for residence) or be calibrated as a
  whole by the placebo.
- **Error amplification in collective resolution.** Mitigated by propagating
  only from high-posterior links and by the end-to-end placebo. It must be
  measured, not assumed.
- **Identifiability of confusion matrices.** With two settings per person
  and no truth, a confusion matrix is identified only under assumptions
  (conditional independence of settings given the person, a dominant
  diagonal). Persons seen by three or more settings help; how many there are
  is measurable.
- **Entity clustering at national scale.** Exact clustering is hard in
  general. The structure here (few records per person, typed edges, strong
  one-to-one constraints) should allow greedy resolution in order of
  confidence. Its quality is measured by the placebo and the gold standard.
- **What a "setting" is.** Hospital, municipality, software, year: which
  level carries the systematic part is an empirical question, and the
  hierarchy lets the data choose.

---

## 11. What execution taught (2026-10-03; ADR-0120)

Measured while building T1–T5. Each item corrects or sharpens a section above.

- **§3.1, chance agreement.** u must be estimated on the population the
  scores are compared within. Three defects had this one cause:
  - **Value-specific u** from marginal frequencies double-counted what the
    blocks already conditioned on, and was worse nationally (removed; code
    kept in EVALUATION 2026-10-03).
  - **A slice's own u** was not the nation's.
  - **An evidence-only comparison's u** from random pairs (or from the
    placebo, which moves the day) was far too small.
  
  The rule now:
  - national u for a slice;
  - the real candidates' u for evidence the blocks do not use.
- **§3.4, the placebo.** It must break a pair on every identifying key.
  Shifting only the birth date left true pairs reachable through other blocks,
  and they sat at the threshold. Every left date is shifted now.
- **§3.2, scope invariance holds in measurement.** A slice against the
  national partner, with national u, pooled m and the national calibration,
  reproduces the national run's pairs for that slice: SP 99.97%, SE 99.9%,
  RR 99.9%.
- **§3.3, the newborn example was optimistic in its first form.** The mother's
  delivery admission carries no residence evidence beyond SINASC's. It does
  carry one real signal: the hospital issues the mother's and the newborn's
  AIHs close together (+4.2 bits within 10 numbers, +2.9 within 100). With
  it, Sergipe's newborn link went from 410 to 828 pairs at FDR 0.36%. Routes
  through deaths add a further 12.6% of admission–baby pairs nationally.
- **§2.1, record identity is not yet stable.** The same record read from two
  publications (SINASC's national and per-state files) has two identities
  (OQ-65). Entities across publications need a content-based key.
  Done 2026-10-03 (ADR-0124): `_record_key`, numbered for CIHA's exact
  duplicates.
- **§5, settings as annotators: identifiability is the binding limit.** With
  two settings per person, *which* system errs is not identified; contrasts
  between settings against a common reference are. The hospitals that code
  systematically (brown as asian; black as brown) are found robustly.

**Later the same night (ADR-0121 to ADR-0124):**

- **§2.3, channels per setting are needed for scope invariance, not only
  for accuracy.** With record keys, the SP slice disagreed with the
  national run on 578 of 134,059 pairs. Every one of them was a channel
  difference: with the national m forced, the slice reproduced all 134,059.
  - SP's recording differs from Brazil's. A residence in the same state
    but another municipality: −1.07 bits in SP, −0.05 nationally.
  - Both runs now estimate m per state, shrunk toward the national m
    (ADR-0123).
- **§2.2, impossibility as learned evidence works, and its weight is
  data-set.** Sergipe: a death at home after a stay that ended in death,
  −9.4 bits (no anchor showed it); a death before the stay began, −3.7 to
  −7.2 bits (ADR-0121).
- **§3.2, the padded partner period.** Infant deaths and newborn admissions
  read SINASC one year back, and inherited evidence follows per year
  (ADR-0121).
- **§5, the SIH "asian" is two mechanisms, both properties of the
  setting.** Some hospitals give 04 to everyone, which is a default, not a
  classification. One wrote SIM's code for brown until a fix in
  September–October 2022 (EVALUATION 2026-10-03). The annotator model must
  allow a setting whose output does not depend on the person.
- **Engineering.** Estimating u from the real candidates must count levels
  batch by batch: materialised, the newborn link's candidates took 40 GB.
- **§2.2, impossibility must not re-read a compared field.** The order
  comparison (admission start to death date) charged a second time for a
  death-date typo the date comparison had already scored. It dropped 3,859
  true SIH-death pairs to a runner-up inside the clear-best margin. Removed
  from the death specs (ADR-0121, amended). The place of death, compared
  nowhere else, stays.
- **§3.1, the coverage prior is not identified from link rates.** Strata
  with low link rates are mostly strata missing evidence: infant deaths
  without plurality also lack weight (88%) and mother's age (80%). A prior
  learned from link rates would penalise records twice for the same
  missing fields. Coverage has to be measured independently of the link,
  or not used (EVALUATION 2026-10-03 "Coverage by stratum").
- **§3.1, u for rare agreements must be estimated with care.**
  - 200,000 random pairs left "birth date equal" (u about 5e-5, a dozen
    occurrences) with 0.76 bits of noise between draws, enough to move
    thousands of national pairs.
  - u is now drawn over both whole sides by hashed index, deterministically,
    from 10 million pairs: 0.024–0.035 bits.
  - The exact alternative, u(equal) = Σ_v p_L(v) p_R(v) from marginal
    frequencies, is done (ADR-0132). It removes the sampling for equality
    levels; the typo levels still need pairs. National SIH deaths: 551,012
    pairs against 551,005.
