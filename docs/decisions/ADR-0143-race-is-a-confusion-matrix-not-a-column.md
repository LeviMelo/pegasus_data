## ADR-0143: race across systems is a modelled confusion matrix, anchored on the declaration at birth

**Date:** 2026-10-05. **Status:** active. **Request:** PegaSUS ARCHITECTURE §4.1 (groups with race), ADR-0139 (modelled tier).

**Context.** The same infant's race differs between SINASC and SIM: 63% agreement over 52,063 linked pairs; SIM records toward the regional majority; SIM Preta is 36% of SINASC Preta. A rate by race with its numerator from SIM and its denominator from SINASC or the Census is biased, in a direction that depends on the region (docs/evaluation/2026-10-05-race-bridge-model.md).

**Decision.**
1. **Reference.** The reference race is the declaration at birth (SINASC `RACACOR`, equal to the mother's `RACACORMAE` wherever both are known). It is the same self-declaration as the Census's, and it is the only reference with linked records. Nothing is called "true race".
2. **Product.** `race_confusion_infant`, written through `modelled.write_modelled`: `C(recorded in SIM | declared j, state, age band)`, with 5% and 95% posterior bounds and the parameter draws beside it (`draws.npz`). Model: multinomial logit with shrunk region and state effects, the municipality's racial composition and the age band at death, fitted on both years of the stored `sim_infant_deaths_to_sinasc` links, each pair weighted by the inverse probability of being linkable. Code: `modelled_race.py`.
3. **Settings, not records.** Covariates are those the PegaSUS lattice carries (place, age band). Ten other SIM fields add at most 0.01 nat per record and are not used.
4. **Uncertainty.** Prior scales are chosen on held-out data and then fixed; the posterior is sampled by NUTS. Predictive counts need their sd multiplied by `PREDICTIVE_DISPERSION` = 1.5 to cover out of sample.
5. **Use.** `reclassify` turns SIM deaths by recorded race into deaths by declared race (Poisson deconvolution with race-specific rate ratios). It is recommended for Branca, Preta and Parda. **Not for Indígena**: its raw rate is already close and the bridge does not improve it.
6. **Scope.** The matrix is for infants. It is not transported to adult deaths by default. Adults are an explicit, labelled assumption, and the identifying source is the plan in the evaluation entry.

**Evidence.**
- Fitted on one year and predicting the other by state: held-out log loss 0.796 and 0.822 against 0.888 and 0.907 for one national matrix and 0.823 and 0.848 for state-wise empirical rates; count error 6% against 27%.
- Rates of infant mortality by race, 2021 and 2022, against the linked truth: mean absolute regional error of Branca 70% → 6%, Preta 62% → 11%, Parda 22% → 4% (2022).

**Not decided.**
- Hyper-scale uncertainty is not propagated.
- No adult product exists.
