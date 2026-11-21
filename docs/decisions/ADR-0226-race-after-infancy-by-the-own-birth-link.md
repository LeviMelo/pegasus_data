## ADR-0226: race after infancy is measured by linking a death to the dead person's own birth; a false link is priced per pair, inside the municipality

**Date:** 2026-11-21. **Status:** active. **Extends** ADR-0143 (infants) and ADR-0149 (women through their births as
mothers; its "not decided": men, other ages). **Request:** the author's review of the race bridge, 2026-11-21.

**Context.** The infant link needs the birth weight or the mother's age, which a certificate carries only in the first
year; the women's link sees mothers aged 15-49. Nothing measured boys, girls after infancy, or men. A death at any age
still carries a birth date, a sex and a residence, and SINASC holds every birth since 1994.

**Decision.**
1. **Link** `sim_deaths_to_own_birth`: deaths at ages 1-24 to the birth with the same birth date, sex and residence
   (the mother's at the birth), unique on both sides. Another child of the same sex born the same day in the
   municipality is a chance partner, so the control is read by the municipality's births in that year and by age, and
   only municipalities under 400 births a year are used. The build runs the pass one birth cohort at a time.
2. **What the birth record declares changed in 2011.** `RACACORMAE` is filled on 2.5% of births in 2010, 55% in 2011
   and 93% from 2012, and equals `RACACOR` wherever both are; Preta is 1.6% of births in 2010 and 5.5% in 2012. From the
   2011 form the colour is the mother's own declaration; before it, the newborn's. The two are never pooled.
3. **Product** `race_confusion_child` (`race-confusion-child-1`): the infant model on deaths at ages 1-14 of children
   born from 2012, bands 1-4, 5-9, 10-14, both sexes, the infant product's reference. Its oldest age grows with the
   years read.
4. **Births before 2011** (the newborn's colour) give no product: that colour is not the census's. They are read as
   evidence on age and sex up to 24 (evaluation entry).
5. **A false link is priced per pair.** With c the chance rate of a death's cell (the control's pairs per death) and f
   the death's own fitted probability of being linked, the pair is false with probability c(1 - f) / ((1 - c) f)
   (`_false_share`): a group that links more often at the same chance rate holds fewer false pairs. Before, one share
   per class.
6. **An unrelated pair's recorded colour is its municipality's**, drawn toward the state by `kappa` deaths: the key
   holds the residence, so a false partner comes from the same municipality. Before, the state's, which took too
   little out of the diagonal where a municipality is unlike its state (the children's Indígena row came out at 1.09
   with the state's, 1.04 with the municipality's, 0.94-1.01 in the two smallest classes).
7. Items 5 and 6 are the model of both contaminated products; `race_confusion_women` is rebuilt under them as
   `race-confusion-women-2` (`-1` stays stored).
8. `held_out` (the validation every race product is scored by) and `reclassify` with a population at risk per age
   band are package functions.
9. **A 7-digit municipality code is placed** in a link's roles (`geography.place_six`; `ROLE_TABLE_VERSION` 2). SINASC
   wrote 7 digits to 2005 and the role read them as no municipality: a link on residence found nothing, silently.

**Evidence** (evaluation 2026-11-21-race-own-birth).
- Children, fit 2013-2020, scored on 2021-2024 (4,944 pairs): log loss 0.770 against 0.820 (one national matrix),
  0.815 (a matrix per state), 1.148 (recorded = declared); count error 8.9% against 19.5%, 10.8%, 20.0%. The infant
  matrix carried to children scores 0.778 and 12.0%.
- No difference between boys and girls under 10 (Preta stays Preta 0.22 and 0.23 at 1-4).
- Old-form cohorts (born 2000-2010, 22,528 pairs): the model with age x sex bands beats the model with age bands out of
  sample (0.763 against 0.776; count error 11.3% against 13.2%): from 15 on, a man is recorded darker than a woman of
  the same colour at birth (Branca stays Branca 0.54 against 0.66 at 15-19).

**Consequences.** The women's matrix is not carried to men: recording differs by sex from adolescence. Rates by race
at ages 1-14 take cohort births by the mother's colour as the population at risk (the reference of the numerator), not
the census.

**Not decided.** Men and women above 24, and 15-24 under a reference comparable with the census (the cohorts of the
2011 form reach 15 in 2026); the residual above 1 of the Indígena row in municipalities of 200-400 births (finer than
the municipality); hyper-scale uncertainty, as in ADR-0143.
