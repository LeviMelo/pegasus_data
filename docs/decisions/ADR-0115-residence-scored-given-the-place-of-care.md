## ADR-0115: Residence is scored given the place of care

**Date:** 2026-09-30. **Status:** active. **Part of:** ADR-0111; answers part of OQ-63.

**Context.**
- **Residence scored alone.** The probabilistic engine scored residence
  against residence as equal / same state / different state. Every agreement
  weighed the same, wherever the shared municipality was.
- **What "equal" means depends on where it is.** Two records agreeing on the
  hospital's own municipality is common by chance: most patients of a
  hospital live in its town. Two records agreeing on a municipality away from
  the hospital is rare by chance.
- **A true pair can disagree.** On linked deliveries, where SINASC places the
  mother elsewhere, CIHA records the hospital's municipality as residence in
  85–100% of cases (EVALUATION 2026-09-30, CIHA residence tested against
  SINASC). A pooled level cannot express any of this.

**Decision.**
- **A comparison may be conditioned on a right-side role.** It is written
  `[left, right, {given: role}]`.
- **For a municipality compared given the place of care,** the levels are:
  - equal, at the place of care;
  - equal, elsewhere;
  - right is the place of care (disagreeing, and the right residence is the
    hospital's municipality);
  - same state;
  - different state.
- **m and u are learned per level**, as for every other comparison
  (ADR-0111); nothing is weighted by hand.
- **Applied** to both delivery specs (`sinasc_births_to_delivery_admission`,
  `sinasc_births_to_ciha_delivery`). Their right side (SIH, CIHA) carries the
  hospital's municipality (`admission.facility_municipality`).
- **One definition of levels.** `linkage/levels.py` is now the only one; the
  unused scalar comparators and scorer in `linkage/model.py` were removed.

**Evidence** (2022, fresh home, `link(..., refresh=True)`):

| link | before | after |
|---|---|---|
| SIH deliveries, RR | 8,447 pairs, est. FDR 0.82% | **8,678**, 0.83% (upper 1.04%), viable |
| SIH deliveries, AC | 10,128, 1.0% | 10,103, 1.0% (upper 1.21%), viable |
| CIHA deliveries, SE | 718, 0.14% | 718, 0.14%, viable |
| CIHA deliveries, AC | 535, 0.75% | 535, 0.75%, viable |

- **Learned weights.**
  - RR: equal elsewhere +4.75 bits, equal at the place of care +0.75, right is
    the place of care −3.65.
  - AC: +4.74, +1.9 and −2.83.
  - CIHA SE has no "elsewhere" level at all: its residence is always the
    hospital's municipality there.
- **RR against the previous run.**
  - 8,435 pairs are kept; 96.1% carry an obstetric diagnosis.
  - 243 are added. 238 of them agree on a residence away from the hospital.
    89.3% are obstetric; the rest carry Z30.2 (sterilisation, 13) and Z03.9
    (observation, 12), codes that also occur among the kept pairs (Z30 222,
    Z03 89), plus one B55.1.
  - 12 are removed, all obstetric, all agreeing only on the hospital's own
    municipality.
  - The Z codes are more frequent among the added pairs (10.3% against 3.7%).
    Why is not established.

**Consequences.**
- Recall rises where mothers travel to deliver (RR +2.7%), at the same
  estimated false-match rate.
- Where residence is written as the hospital (CIHA SE), agreement on it
  counts for little (+0.68 bits) and disagreement barely counts against
  (−0.27).
- The death link (`sih_deaths_to_sim`) has the hospital on its *left* side.
  Conditioning on a left-side role is not implemented; OQ-63 keeps it.
