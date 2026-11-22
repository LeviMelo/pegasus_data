## ADR-0229: race at birth against race at death is read from a death's candidates, with the other sex's births as the control

**Date:** 2026-11-21. **Status:** active, amended by ADR-0233 (its errors; movers and twins). **Extends** ADR-0226. **Request:** the race research line (docs/plans/race.md, R2).

**Context.** After infancy a certificate shares with a birth record only the birth date, the sex and the municipality
(the mother's and the birth's fields are filled on 0.0% of the deaths at 1-14). A one-to-one link exists only where a
day's births of one sex are few, so ADR-0226's products see municipalities under 400 births a year and reach the rest
by a model, which failed there (the children's bridge put Branca above Parda nationally, against the linked truth),
and a matrix cannot be inverted for Preta (a quarter recorded as declared).

**Decision.**
1. For a group of deaths, the births that share each death's date, sex and municipality are counted by declared and
   recorded colour (`modelled_race.candidate_counts`). One candidate is the person where the family did not move; the
   others are chance.
2. The control is the births of the **other sex** on the same day in the same municipality, scaled by the
   municipality's births of the death's sex over the other's. A birth date moved by whole weeks is not a control: a
   day of many births makes many people and so many deaths, so a death's own day holds more chance candidates than a
   moved one (the person was "found" 1.4 to 6.2 times in the large municipalities with it, 0.61-0.74 with the other
   sex).
3. Candidates less control is t x the group's deaths by (declared, recorded) (`candidate_difference`), with standard
   errors from the counts; no false-link model, any municipality size; the unique link is the case of one candidate.
4. A rate by declared race is the difference's rows over the births of the same cohorts by declared colour, as a ratio
   between races (t cancels).
5. A declared class that is common among the chance candidates is lost in their noise in large municipalities (the
   old-form cohorts' Branca row above 1,600 births a year); the estimate is then given for the municipalities where its
   standard error allows, and said so.

**Evidence** (evaluation 2026-11-21-race-own-birth). Under 400 births a year it gives the unique link's figures
(Branca 0.81, Preta 0.22, Parda 0.60 for 0.81, 0.23, 0.62). Children born 2012-2023, deaths 2013-2024, every
municipality, rate relative to Parda: ages 1-4 Branca 0.66 ± 0.06, Preta 1.11 ± 0.16, Indígena 4.6 ± 0.3 (certificates:
1.43, 0.81, 6.0); ages 5-9 Branca 0.67 ± 0.11, Preta 1.05 ± 0.29, Indígena 2.0 ± 0.5.

**Not decided.** The model products of ADR-0226 rebuilt on this estimator (their pairs are the one-candidate case);
movers (not among their candidates); same-sex twins.
