## ADR-0149: the adult race bridge is a women-only confusion matrix, measured through mothers; the infant matrix is not transported to adults

**Date:** 2026-10-05. **Status:** active. **Request:** ADR-0143 point 6 (adults are an explicit assumption), the plan in docs/evaluation/2026-10-05-race-bridge-model.md.

**Context.** Adult deaths have no birth record. A woman who died aged 15-49 may have given birth since 2012, and SINASC then holds her own declared race (`RACACORMAE`) with her birth date and residence (docs/evaluation/2026-10-05-race-bridge-adult.md).

**Decision.**
1. **Reference and link.** The adult reference is the mother's declaration at her latest birth. `sim_women_deaths_to_sinasc_mothers`: women's deaths 2015-2022 to one record per mother (birth date, residence), a death-after-birth filter, and the negative control read **per municipality size** (the number of mother groups), because the chance of a coincident birth date grows with it. Pairs are used only below 2,000 mother groups; the share of false links per year and class (control-based) enters the likelihood as `(1 - phi) C + phi r(state)`.
2. **Product.** `race_confusion_women` (v `race-confusion-women-1`): the infant model with age bands 15-24, 25-34, 35-49, same tier and layout (`modelled_race.py`, population `WOMEN`; `build` replaced `build_infant`).
3. **Transport.** The infant matrix is **not** transported to adults as a default: out of sample it is worse than a national women's matrix (log loss 0.89 against 0.88) and no better than recorded = declared on counts (15-18% against 14%); it keeps Branca and Indígena right and misses Preta (63% stay Preta in women against 21% in infants). The women's matrix is not transported to men or to ages above 49 either.
4. **Use.** For adult women in the product's population, `reclassify` with the women's draws; for other adults only as a labelled assumption with the sensitivity band between the two matrices.

**Evidence.** Fit on 2015-2018 predicting 2019-2022: log loss 0.851 against 0.882 (national women's matrix) and 0.876 (state-wise), count error 7.7% against 16.7% and 8.2%; 20,084 pairs of which 28% estimated false.

**Not decided.** Adult men; ages above 49; women who never gave birth (the link cannot see them); the sampler for this fit is weaker than the infant one (R-hat 1.023, ESS 53).
