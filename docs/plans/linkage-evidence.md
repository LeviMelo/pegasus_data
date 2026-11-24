# Plan: link evidence declared by the study, link quality as quantities (proposed, 2026-11-23)

**Why.** The ABNc papers (ten cohort studies, 2026-11) showed two gaps in how links serve research.
- **Which evidence a link may use is a scientific decision of the study, and pegasus_data fixes it in curation.** The
  author's example: a patient whose aneurysm was clipped who dies of a cerebral haemorrhage is far likelier to be the
  certificate's person than a random neighbour of the same birth date, sex and town. Using that cause as evidence
  rescues ambiguous pairs. It also conditions every analysis of cause, and undercounts deaths from other causes. The
  study weighs that cost within its scope. The library must let it, and make the choice visible.
- **Quality is reported as a verdict, and the figures studies need are computed by hand.**
  - "not viable" or "use with caution" are labels, not measurements.
  - The rate over all pairs was cited for the deaths only the link finds: 0.9-2.9% against 10-39% in t03.
  - Three studies wrote their own link-error code (`t07_link_error.py`, `t04_link_age.py`, t03's S3).

**What exists (read before changing anything).**
- `linkage/engine.py`: deterministic passes over keys, 1:1 over what is left, a negative control per pass
  (`placebo.py`), held-out validations, `judge`.
  - Cohort specs carry `params` (the caller's codes, and `match` variants mapped to roles, including partner roles)
    and `outcome` (origin, event).
  - The false-match rate and verdict are given per horizon (ADR-0194). A dropped pass makes every horizon not viable
    (849bc516).
- `linkage/followup.py`: `linked_deaths` and `linked_outcomes`, with a `p_match` per band of days (one minus the
  control's coincidences over the band's pairs).
- `linkage/probabilistic.py`: m and u per comparison, a pair-level `p_match`, scope invariance, channels per state
  (ADR-0111, 0120-0123).
- `linkage/uncertainty.py`: `p_match` weights, `link_draws`, Rubin's rules (linkage-theory §6).
- One spec already keys on cause: `sia_radiotherapy_to_sim` with `match: principal` takes the certificate's underlying
  cause in the treated codes. This is the author's idea as a hard restriction, with its consequence for outcomes
  stated nowhere a consumer reads.
- linkage-theory §5 says a field studied as an outcome is never identity evidence. This plan replaces that ban with a
  declared, recorded choice.

## Design

**1. Evidence is part of the run, declared by the consumer.**
- The default stays: a spec's curated identity evidence (birth date, sex, residence, dates, hospital numbers).
- A caller adds evidence: `link(..., evidence=[...])` and `linked_outcomes(..., evidence=[...])`.
  - An item compares a left role, or the caller's codes, with a partner role, at declared levels.
  - Example: `{compare: [codes, death.cause], levels: [same category, same block, other]}`.
- How each engine uses an item:
  - in the probabilistic engine, an item is one more comparison: m learned from anchors, u from the candidates;
  - in the deterministic engine, it is a key (a restriction, reported as one) or a held-out validation.

  `match` variants become declared evidence items of the spec, not a separate mechanism.
- The run records the evidence it used, and the store key includes it. A study's variant is stored beside the generic
  run, never in its place.
- **Open, with the consequence visible.** Nothing is refused.
  - Every reader that returns partner roles marks the roles that were evidence.
  - The table's metadata says what the evidence conditions: for example, "death.cause was evidence; its distribution
    among linked deaths is conditioned on it".
  - The study decides; the paper states it.
- **Both ways.** A reader asked for a run with study evidence also returns the generic run's events per horizon. The
  difference is the evidence's effect: a sensitivity analysis by construction.

**2. Quality as quantities** (GUILD, Gilbert et al. 2018; RECORD, Benchimol et al. 2015). For each run and each horizon:
- **Pairs found**, and the **events only the link finds**: the spec declares what the left side records itself
  (`outcome.known`, for example SIH's discharge by death), so those events are not counted as link-only.
- **Expected chance pairs**, with an interval: several control rotations instead of one, or a Poisson interval on the
  control count.
- **The false-match share** over all pairs, and **among link-only events**.
- **Sensitivity on a truth subset** the spec declares (`truth`: SIH in-hospital deaths for SIH to SIM), with its
  interval. The assumption that it transfers to the link-only events is stated in the report.
- **The corrected count**: known events + (link-only - expected chance) / sensitivity, with an interval.
- **Reach**: link rates by state, year, age band, sex and race; linked against unlinked characteristics on the truth
  subset.
- **The verdict** stays only as a label derived from these, with its thresholds printed. The 10% drop rule becomes a
  quantity a consumer reads, since keeping a pass and correcting may beat dropping it.

The studies' own link-error code is then deleted (replace, never add beside).

**3. One engine for cohorts: decided by measurement.** Run the deterministic and probabilistic engines on the same
cohort specs where a truth subset exists: SIH to SIM, several cohorts, national and by state. Compare four things:
- sensitivity;
- the false-match share among link-only events;
- the corrected estimates;
- time and memory.

The winner becomes the cohort readers' default (ADR). The other either generates the candidates or retires. Pair-level
`p_match` then reaches analyses through `link_draws`, the theory's §6 default for rare outcomes.

**4. Attribution is not linkage: excess mortality.**
- Linkage says whose certificate it is. Whether a death was caused by the procedure is a separate model.
- The established one is excess (relative) mortality: the cohort's deaths against those expected from population
  mortality of the same sex, age, place and year. The Pohar Perme estimator, from R's `relsurv`.
- This needs life tables from SIM deaths and the population series, both held. That is a library product: any cohort
  study needs it, and three ABNc studies wrote their own expected counts.
- Coded cause stays a secondary description, read with the certification quality the library already measures
  (garbage codes, ill-defined causes).

## Steps

| Step | Done when |
|---|---|
| Q1 quantities in the run's report and the readers' quality | on the stored t03, t07 and spine runs the library reproduces the studies' own link-only shares (t03 10-39% at 30 days by year) and the spine sensitivity (SP 2019, 56 of 58) |
| Q2 `evidence=` on `link` and the cohort readers, stored beside the generic run, roles flagged | an aneurysm cohort linked with and without cause evidence; events per horizon both ways; the cause distribution flagged as conditioned |
| Q3 the engine comparison | an evaluation entry with the four measures; an ADR naming the default |
| Q4 life tables and excess mortality | life tables by sex, age, state and year with their sources; one cohort's excess mortality against its all-cause linked mortality |
| Q5 consumers | PegaSUS and the skills read the quantities; the studies' own link-error code removed |

## Open questions

- **m for an evidence field.** The truth subset gives m for an evidence field (the share of in-hospital deaths with a
  congruent cause). But late deaths are less often procedure-related, so m should fall with the days since the
  procedure. Learn it by band, or bound it.
- **The population for excess mortality.** Whole-population life tables for a SUS cohort, or SUS-dependent ones (the
  modelled population by private coverage)?
- **Levels of congruence** (category, block, chapter, garbage code): learned from the data, never listed by hand.
