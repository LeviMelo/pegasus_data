# Response to audit 1 - paper 2, `indicators/`

All five errors are fixed. New asserts in `text.py` hold the claims.

| Item | What was done |
|---|---|
| E1 census-based ratio | The mechanism ("the census, like the certificate, classes Brown children White") is removed. Results and the Abstract now say the value depends on the modelled population account. The values are 0.80 in infancy and 0.94 at 1-4 years, against 0.79 under the census's own household classification. None carries an interval, and the text says so. "As rates after infancy are usually computed" is removed. |
| E2 "general" reversal | The lead is now "by posterior means 400 of 510, credibly 115". The 446-against-159 asymmetry is given, with its cause: few White deaths and shrinkage to the national term (0.90 by the mother's race, 2.13 by certified race, both stated). "Credible" is defined in Methods. |
| E3 1-4 headline | After infancy, the main estimates are restricted to municipalities under 25,600 births, as in paper 1: 1-4 years 0.73 (0.67; 0.80), 5-9 years 0.72 (0.60; 0.85). All sizes are kept as a sensitivity analysis. Methods gives the validation numbers (0.79 against 0.79 at 1,600-6,399 births; 0.85 against 0.71 at 25,600 or more). [14] now cites the control only. |
| E4 two infant estimators | The infant row of Table 1, Figure 1A/1D and the rate sentence use the linked rates. `results.py` writes `infant_rates.rate_mother_linkage`: linked deaths scaled to every certificate, White 11.0, Brown 13.6, Black 15.6 per 1,000. An assert checks that the rates and the ratio agree. |
| E5 Black to Brown | Infant Black to Brown is in the Abstract, Results and Conclusion: 1.15 (1.09; 1.20) against 0.49 (0.48; 0.50). Indigenous is in Results. The 1-4 Black to Brown ratio is 1.07 (0.91; 1.24), and it is reported as such. |
| 2.1 rate definitions | New Methods paragraph "Rates": periods, cohorts (5-9 covers births of 2012-2019) and the exclusion of Yellow and blank births. The reason for 2016-2024 is given. |
| 2.2 BYM2 | Exposure, fixed term, graph (regions whose municipalities share a border), PC priors, INLA settings and the definition of credible. |
| 2.3 national vs regional | One sentence: class means average regional ratios, while the national ratio pools across composition. The national model terms are given. |
| 2.4 U-shaped | Replaced by "highest where White births are rare". The assert now holds only that. |
| 2.5 "pulled toward its mean" | Replaced by the shrinkage statement with the national term (2.2). |
| 2.6 mechanism | The Discussion now names all three flows: Brown to White 0.25, Black to Brown 0.55, White to Brown. A counterfactual through the flow matrix was not computed. |
| 2.7 mother's race as reference | The Limitations say that a reversal means a departure from the mother's declaration. "Misstatement" is removed from Figure 2C. |
| 2.8 unlinked deaths | The scaling assumption is stated in Methods. The Indigenous linked share (61.9%) is given. "Equal linkage" now reads "differed by less than one point". |
| 2.9 primary | A "Primary and secondary analyses" paragraph: the infant White to Brown contrast is primary, the rest exploratory. |
| 2.10 uncertainty | Stated: the intervals omit linkage and population-account error. The census-based and family ratios have no interval. |
| 2.11 not-estimable rule | One rule (standard error above 0.35 of the estimate) for Supplementary Table S2 and Figure S1. Paper 1's 0.15 is a proportion's absolute standard error, a different quantity. |
| 2.12 uncited intro | The first sentence cites Cardoso and Caldas. "The Ministry's infant indicator" is now "the usual infant indicator", defined in Methods as how the rate is computed from the two systems. |
| 2.13 "robust" | Now "the direction did not depend on the choices; their size moved within the intervals". The jackknife and t ranges are attached to the all-municipality estimate they belong to. |
| 2.14 colour scales | Figure 2 caption: the scales are censored at their ends; the largest values are in Table S1. |
| Minor | The "since 2011" note says nearly all records from 2012. Table 1 note: no census-based value at 5-9 years, and Yellow is not shown. Figure 1D caption: log scale. Table S1: "lowers it relative to the mother's race". Arias: "misclassify". Rebouças: "agrees". The 0.25 and 0.55 flows are given as numbers. |
| References | Fellegi-Sunter and the BYM2/INLA method papers stay cited for method only. The RECORD checklist is not yet attached; that is left for submission. |
