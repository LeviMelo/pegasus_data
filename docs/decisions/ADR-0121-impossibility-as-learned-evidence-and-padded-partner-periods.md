## ADR-0121: Impossibility is learned evidence (event order, category pairs), and a partner side may be read over a padded period

**Date:** 2026-10-03. **Status:** active. **Part of:** ADR-0107; executes
docs/plans/linkage-theory.md §2.2 ("event relations") and §3.2 (the padded
partner period). Extends ADR-0111, ADR-0120.

**Context.**
- **Impossible pairs were measured but not used.** EVALUATION 2026-10-02
  "Impossible pairs" counted pairs that violate a physical order: a death
  before the admission began, or a death at home after a stay that ended in
  death. Nothing in the scores used those facts.
- **They must not be a hard veto.** Records carry typing errors, so an
  "impossible" combination happens to true pairs at some rate. That rate has
  to be measured, not assumed to be zero (the user, 2026-10-01: physically
  impossible or merely unlikely?).
- **One spec filtered for a scope artefact.** `sim_infant_deaths_to_sinasc`
  kept only deaths of children born in the death's own year. Without that
  filter, a baby born in December and dead in January had its birth in a file
  the link never read. The filter was a consequence of reading one year, not
  a fact about infants.

**Decisions.**

1. **Two evidence-only comparison kinds** (`linkage/levels.py`,
   `model.EVIDENCE_ONLY_KINDS`).
   - **`order`: where the right event falls relative to the left one, in day
     bins.** The bins are: before by more than a year, 29–365, 8–28 or 1–7
     days; the same day; after by 1–7, 8–28 or 29–365 days, or more than a
     year.
   - **`joint`: the pair of categories itself, one level per (left value,
     right value).** This is a confusion channel inside Fellegi–Sunter: SIH's
     "admission ended in death" against SIM's place of death.
   - **Both are learned like any comparison.**
     - m comes from the leave-one-field-out anchors.
     - u comes from the real candidates, as for the other evidence-only kinds
       (ADR-0120).
     - A level no anchor showed is floored and never counts for a match
       (ADR-0117).
   - So a violation costs what the data say it costs, and a common recording
     error costs little.
   - Neither kind can join records: they never form anchors or blocks.
   - The placebo shifts an `order` comparison's left date with the others.
2. **The specs carry them** where the event order or the category pair is
   informative:
   - **`sih_deaths_to_sim` and `ciha_deaths_to_sim`:**
     `[admission.start, death.date, order]` and
     `[admission.death, death.place, joint]`.
   - **`sim_maternal_deaths_to_admission`:**
     `[death.date, admission.start, order]` and
     `[death.place, admission.death, joint]`.
   - **Not `sih_neonatal_admissions_to_sinasc`.** Its left filter already
     restricts an admission to 0–28 days after the birth, so the order of
     events carries no evidence there. Sergipe showed only the bins the
     filter allows.
3. **A side may declare `pad_years: [before, after]`.**
   - That side is then read over the left period widened by those years
     (`engine.padded_period`; the run key records the widened period).
   - `sim_infant_deaths_to_sinasc` drops its same-year filter and reads
     SINASC one year back: `pad_years: [1, 0]`.
   - `sih_neonatal_admissions_to_sinasc` does the same, for a baby born in
     late December and admitted in January.
   - **Inherited evidence follows the padding.** A padded side's records
     inherit from the stored link of each year in the period: the scope's
     own, else the national one. A year with no stored link leaves its
     records without the inherited value, which is missing, not evidence.
   - For the 2022 deaths this needs SINASC 2021 in the lake. That is the
     national file only: 132 MB fetched, and the per-state copies are not
     read.

**Evidence.** EVALUATION 2026-10-03 "Impossibility as learned evidence; padded
infant deaths".
- **Sergipe, both variants on their own u and threshold.** A place of death
  "home", against an admission that ended in death, learned −9.4 bits; no
  anchor showed it. A death before the admission began learned −3.7 to
  −7.2 bits. `sih_deaths_to_sim` kept 4,608 pairs against 4,610, with an
  FDR upper bound of 1.01% against 1.13%; 9 pairs were dropped and 7 added.
- **The other specs were unchanged in Sergipe.** Their anchors there are too
  few (CIHA 21, maternal 7) for the new levels to matter before pooling.
- **National figures** are added to the evaluation when the national
  relink lands. The spec changes (`data/logs/apply_specs.py`) are applied
  only after the runs that read the current digests have finished: the
  scope test, entities and race by setting.

**Consequences.**
- **Impossibility now enters a pair's posterior with a measured rate.** The
  `validate` checks ("died in hospital") stay as held-out checks only for
  specs that do not compare those roles. A validation on a compared role is
  no longer held out, and is read as such.
- **A padded spec costs the extra year's partner records.** The national
  partner search reads them by key, so the run time grows with the candidates
  rather than with the file.
