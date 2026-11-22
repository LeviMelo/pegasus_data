# Response to review 3

- Admissions against the findable target (top change 1): fixed. Abstract, Results, Discussion and Conclusions now judge the admissions against the linked people whose certificate shares the key (mean difference 0.0010, 3 of 20 cells outside the model interval, z SD 1.43; 0.33-1.04 by size class). The whole-table departure (about 0.005) is named as the A1 selection. "Too narrow" is gone. Figure 2B-C caption says it shows the whole-table comparison and points to Table 2.
- Replicate counts (2): fixed. 200 replicates of eleven scenarios and 100 of the two pooled ones, in the abstract, Methods and Supplementary Table S1. Figure 3 does not draw pooled12 and application, and its caption says so; both are in Table 4 and S1.
- Coverage minima (3): fixed. The Discussion gives the worst coverage of all deaths where the assumptions break (selective, keyerr_k).
- Comparators where chance is low (4): fixed. A new Results paragraph says the unique-key link wins among infants under 400 births a year, and that the control does not help in admissions below 6,400 certificates. Asserts guard both.
- Infant adequacy by size class, and 25,600 chosen in-sample (5): fixed in the Discussion. The unfindable were not profiled. The "careless records, not movers" claim is softened to what was measured.
- Garbled dispersion sentence: fixed. phi is each sex's variance beyond Poisson over the mean squared, and psi the covariance of the sexes over the product of means (analysis/estimator.py:520). The review had the two reversed.
- Goodman multiple 8.7: kept. It comes from the unrounded values; the rounded Table 3 values give 9.75.
- A2 rate-ratio bias +0.065 against +0.045: these are different cells, the national one and the 6,400-25,599 one in Table 4. The text now says "national".
- Not done: the census check for ages 1-14 (needs microdata), the EM comparator, the A2 dose response by age band, the RECORD flow diagram.
