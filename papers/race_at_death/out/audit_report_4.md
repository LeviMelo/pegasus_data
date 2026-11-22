# Audit report 4: race at death (manuscript.txt, supplement.txt, figures, results.json, spatial.json, analysis code)

Scope: the built text against the JSON and the generators (`text*.py`), and the code that defines each quantity (`analysis/common.py`, `results.py`, `spatial.py`, `models.R`). Main figures 3-8 were viewed. 44 printed numbers were recomputed (section 5). Read-only, except for this file.

## 0. Verdict

The descriptive core is defensible and reproduces from the JSON. Three claims are: the certificate departs from both the mother's declaration and the family's classification; it varies strongly and in a spatially structured way across municipalities; and certified-race rate ratios over births reverse the mother's-race ratio. The interpretive layer does not yet hold as written. One headline number is labelled with the wrong estimator. The national infant ratio by mother's race (0.79) comes from the candidate estimator, not from the one-to-one linkage the Discussion invokes. The "who dies there" share of municipal variance includes the macro-region. The census-based denominator behind "0.94, compressed" is undocumented, and its reference is dangling. Counterfactual wording ("the same child is more often White where most people are White") assumes away a rival explanation, regional heterogeneity within the Brown category, that the design cannot exclude. "Associated with place" is supported. "A classification of place" (title) and "conditions of place that the other two do not share" (Conclusion) are not.

## 1. Errors (must fix)

E1. **The infant ratio by mother's race is not from the linkage.** `results.py` l.85-98 computes `infant_rates` from `diff("infants")`, the candidate estimator's counts over all municipalities. That includes those of 25,600+ births, where its SE for White reached 0.12. The one-to-one linkage is not used. Yet:
- Discussion: "infants, whose deaths were linked one-to-one, show it (0.79 by the mother's race…)".
- Abstract: the ratio follows "Among 296,512 linked infant deaths", which implies linkage.
- The Methods say national ratio SEs are "the larger of that and a delete-one-state jackknife". The jackknife is applied only to the 1-4 and 5-9 blocks (`results.py` l.69-80), so the infant interval 0.75-0.84 is Poisson-only.
- The regional Poisson BYM2 ratios use the linkage, scaled to all deaths (`spatial.py` l.114-116). The national and regional mother's-race ratios therefore come from different estimators, and this is not stated.

Fix: recompute the infant ratio from the linked pairs (or state the estimator and apply the jackknife), and rewrite the Discussion sentence.

E2. **"Who dies there" includes the macro-region.** `models.R` l.173: `IND` = `region + yc + certifier + …`. The full model shows region odds ratios of 0.53 (Northeast) to 1.30 (South) against the Southeast. The 74% for `individual_only` is therefore partly a place term.
- The Results hedge with "and where".
- Discussion ¶1 says "part of the variation between municipalities was who died there and of what". Limitation (5) says "the deaths' own characteristics explained much of the municipal variance". Neither is supported.

Fix: refit without region, or reword both sentences. Separately, PCV after adding individual-level covariates in a logistic model is not a variance share: the level-1 scale is fixed, so adding covariates rescales the municipal variance (Merlo 2006, already cited [50]). Say so.

E3. **The census-based population denominator is undocumented, and its citation is dangling.**
- Methods and Discussion rest "0.94 … compressed toward 1 rather than reversed" (in the Abstract) and "0.80" on "a census-based population account (Supplementary Text S3)" that "classifies children as households do".
- S3 describes only census-year shares. Children aged 1-4 in 2016-2024 were born in 2012-2023 and appear in no census before 2022. How the account assigns them a race between censuses (births by mother's race? interpolation to 2022? deaths by certified race?) is not stated anywhere in the package. `results.py` l.412 reads `population-account-9` as given.
- S3 cites `[58]` (`ibge_projections2024`). That number exists in no reference list: the manuscript's list ends at 57 and the supplement has none (`build_report.json`: 58 keys).
- Audit-3 response P6 says the account "is no longer cited to the IBGE projections". It still is.

Fix: document the intercensal race assignment, or drop "as households do" and qualify the 0.94 in the Abstract. Fix the reference.

E4. **Counterfactual and "do not share" wording beyond the design.**
- "The same child is more often White where most people are White" appears in the Discussion ¶2 and in Implications. "The classification of the same kind of child moved from 0.13 to 0.79" appears in Discussion ¶3.
- Brown mothers in the South and in the North are not the same population. Ancestry and appearance within the Brown category vary by region, and an observer classifying by appearance would produce the composition gradient without any "local norm". The family comparison does not exclude this: the family reports identity, the certifier observes.
- Only the border test (neighbours across a border) partly controls for it. The paper never names this rival.
- The Conclusion says the certificate is "made under conditions of place that the other two do not share". That contradicts the paper's own data and limitation (3): the family's classification also varies by place (0.10-0.36), and the birth record "may carry a place-dependent component".
- Implications says linkage to the mother's race "removes the dependence on place", which contradicts the same limitation.
- The title still reads "as a classification of place" (audit 3 E7 changed only the text).

Fix: name the within-category heterogeneity rival in the Discussion and limitations. Drop "same child". Soften the title and Conclusion.

E5. **"Continuous surface" persists.** Discussion ¶3: "The certificate shows this at the scale of the country and as a continuous surface … stepping at their borders." This is self-contradictory, and audit 3 E3 asked for its removal (the response says it was removed).

## 2. Points to fix

P1. **Border test.**
- (a) "The slope is a lower bound of the step" is too strong. Attenuation from error in the state effects pulls toward 0. A smooth spatial trend reaching the border, and the linear `dX` term in the pair regression against the 3-df spline used for the state effects (`spatial.py` l.308 vs l.322), can bias either way. Say "attenuated by measurement error", not "lower bound".
- (b) `spatial.py` computes, but the text omits, the within-state placebo. The weighted mean squared logit difference of neighbours is 0.555 across state borders against 0.488 within states (ratio 1.14; disagreement 0.395 vs 0.317). The step is real but small relative to the differences between neighbours, which the bare Abstract sentence "The certified race stepped at state borders" overstates. Report it and give the slope in the Abstract.

P2. **"The test at state borders, the residual Moran's I after composition and state, and the multilevel variances all point the same way"** (Discussion ¶2). The multilevel models contain no state term (Table 3 note), so they cannot bear on the state component, and "the same way" is undefined. Rephrase.

P3. **Variance ratio "5 times" (Abstract, Discussion).**
- It compares infants (certificate) with children aged 0-9 (family). The Abstract omits the age difference.
- The census "mother's race" is the household's report of the mother, not her birth-record declaration. Limitation (1) does not say this.
- Discussion ¶1 calls them "the same mothers' children", which is wrong: different mothers, different classification of the mother.

P4. **Regional rate ratios and the "misstatement".**
- (a) "Misstates" presumes the mother's race is the child's true race, while the Conclusion says "the design does not establish which classification is correct". Use "changes" or define the term as relative to the mother's race.
- (b) The regional log-RR SD is `sqrt(b_sd² + f2_sd²)` (`models.R` l.143), which ignores the posterior covariance of the fixed and random terms. Use linear combinations. This affects 157/446/114.
- (c) The ratio of ratios divides two separately smoothed models, whose different shrinkage can create pattern: the mother's-race White counts are small where White births are rare. In the <10% class the mother's RR mean is 0.93 against 0.79 nationally.
- (d) The offered mechanism explains only the low end of the U. The high end (2.19 at ≥60%) needs its own explanation: Brown deaths moved out of the Brown numerator. The 10-29% class (1.92) is omitted from the text.
- (e) `misstated_credibly_positive` = 469 of 510 is unreported and is the more direct result.

P5. **Census-composition sensitivity scope.** It was run only for the deviance models. Limitation (4) says "gave the same results for infants", and Discussion ¶2 says it "reproduced its explanatory power". Neither the multilevel models, the border test nor the 15-24 analyses were rerun. Narrow the claim.

P6. **Wealth at equal composition.** The composition classes are broad (<30%, ≥60%). Within <30%, richer municipalities may be whiter, so the 0.15→0.23 GDP contrast is confounded by residual composition. Test GDP with the composition spline as a covariate.
- "After infancy" picks non-parallel cells: "poorest … under 30%" against "middle-income … 60% or more".
- At 15-24, natural deaths in the <30% class also rise with wealth (0.40, 0.54, 0.62, from JSON). The text states the wealth effect only for assaults.

P7. **Linkage reporting (RECORD 12).**
- There are still no match weights, no threshold, no blocking and no false-match estimate (audit 2 P4(d)).
- Linkage is 61.9% for Indigenous, 64.9% after the first month, 76.2% in the North, and the proportions are conditional on linkage.
- The per-step flow at 1-9 and 15-24 is still absent.

P8. **Selection by municipality size.** The 15-24 results are restricted to municipalities under 1,600 births per year, and the bound was chosen after inspecting the estimates. Every statement about cause and certifier therefore describes small, mostly interior municipalities. The Abstract gives the restriction only in its Methods, not beside the 0.68/0.35.

P9. **Multilevel estimation.** nAGQ = 0 throughout. The JSON key `full_laplace` holds an nAGQ = 0 fit; rename it. AIC differences of 3,411 and 266 come from PIRLS approximations and are approximate. No sensitivity was run.

P10. **t-sensitivity.** The text reports 2 of 4 scenarios (0.77, 0.58). The four give 0.57-0.77. Report the range.

## 3. Minor

- The Figure 4E caption carries binomial error bars, while the text says "Intervals are not given for these proportions: binomial intervals understate…". Remove the bars or say what they are.
- Figure 3C's colour scale is clipped at ±0.30, while the South's mean difference is +0.37: the South saturates (audit 3 M2/M5 in a new form).
- The agreement slope prints "(95%CI -0.00; 0.12)". Write -0.0002, or "about 0 to 0.12".
- The Supplementary Table S15 note says "GDP tertiles of municipalities". The cut points are tertiles of linked infant deaths (`spatial.py` l.344), as the Methods say.
- Supplementary items are still cited out of numerical order (response M1: not done).
- Methods "Measures" points to Supplementary Text S3 for the population account. S3 is titled "Birth cohorts at three censuses" and does not describe the account's method (see E3).
- Discussion: "whether this follows the growth of Black identification seen between censuses [53,54] cannot be tested". Miranda [53] covers censuses to 2010, and [54] is a 2022 press release. The citations fit, but only as context.
- "The certificate agreed with neither the mother nor the family" (Conclusion). Agreement with the mother is 0.76 and 0.64 for White and Brown mothers. "Departed from both" is accurate.
- References not read in full or not at all, per `reading_report.md` (Crossref metadata only):
  - not in the report at all: Roth 2016 [9], Penner 2008 [15], Freeman 2011 [17], Saperstein 2010 [55], Keele and Titiunik [48];
  - abstract only: Telles 2002 [10];
  - not read: Fellegi and Sunter [31].
- The claim resting on [55] ("people who had been incarcerated were more often seen as Black by interviewers") and the specific claim on [10] ("79%") rest on unread text.
- Keele and Titiunik support the boundary logic, not the pair regression estimator.

## 4. Audit-3 fixes not actually made

| audit 3 | claimed | in built text |
|---|---|---|
| E3 | "continuous surface across borders" removed | "as a continuous surface" remains, Discussion ¶3 (E5) |
| E7 | "classification of place" became "associated with place" | text yes; title still "as a classification of place" |
| P6 | account no longer cited to IBGE projections | S3 still cites `ibge_projections2024`, printed as dangling [58] (E3) |
| P9 | binomial intervals removed from place/GDP proportions | removed from text; still drawn in Figure 4E |
| M1 | supplementary order | not done (admitted) |
| M2/M5 | scales | Fig 3C still clipped |
| E2, E4, E5, E6, P1, P2, P3, P4, P5, P7, P8, P10, M7, M8, M9, M10, M11 | — | present in the built text as described |
| E1 | slope label | fixed: North 0.19, South 0.99, computed from contrasts |

Audit-2 P4(d)/(e) (linkage weights, per-step flow) and P15 (mother's-race quality sensitivity) remain not done, as the response says.

## 5. Numbers recomputed (location; printed; recomputed; status)

1. Abstract/Results, White/White: 0.76 (0.75; 0.78); 0.763 (0.749; 0.778); ok
2. Brown/Brown: 0.64 (0.62; 0.66); 0.641 (0.621; 0.661); ok
3. Black/Black: 0.18 (0.17; 0.20); 0.184 (0.169; 0.198); ok
4. Brown→White: 0.25 (0.23; 0.27); 0.252 (0.231; 0.273); ok. Black→Brown 0.55 (0.53; 0.57); 0.549 (0.527; 0.570); ok
5. Abstract, 296,512 linked; 296,512; ok
6. Abstract, 0.09 to 0.76; p5 0.091, p95 0.760; ok. Family 0.10-0.36; 0.104, 0.365; ok
7. Variance ratio 5 / 4.9; 1.382/0.284 = 4.87; ok
8. Moran's I 0.77 (3,459); 0.770; ok. Disagree 0.45, Black 0.42; 0.450, 0.420; ok
9. Deviance explained 71/75/81/42; 0.711, 0.753, 0.806, 0.420; ok. Context added 1%: 0.815-0.806; ok
10. Census composition 69%/80%, correlation 0.94; 0.689, 0.803, 0.937; ok
11. Black 22%/37%, residual I 0.13; 0.220, 0.374, 0.126; ok
12. F 325 / 66.8; 324.96, 66.82; ok. Dispersion 8.4; 8.36; ok
13. Residual I 0.71, 0.29, 0.15; 0.712, 0.288, 0.154; ok. Field variance 1.38, 0.41, 0.09; ok
14. Border 0.46 (0.26; 0.65), 49 state pairs, 1,069 pairs; 0.455 ± 1.96·0.0993 = 0.261; 0.650; ok
15. Disagree border 0.35 (0.19; 0.52); 0.353 (0.191; 0.515); ok
16. Place 0.25/0.30/0.22; 0.253, 0.300, 0.223; ok. At 30-59%: 0.38/0.47/0.38; 0.375, 0.473, 0.385; ok
17. GDP 0.15/0.23, 0.64/0.66; 0.146, 0.235, 0.636, 0.658; ok
18. Multilevel: n 178,656, var 1.32, MOR 2.99, 87/55/43/89/74/91%, MOR 1.38; all ok
19. Abstract multilevel context 60%; `socioeconomic_services` 0.596; ok
20. Black multilevel 39/19/22/48/58; 0.394, 0.188, 0.221, 0.476, 0.581; ok
21. Establishment 7,429 levels; 0.29/0.03; 0.31/0.10; AIC 3,411 and 266; ok
22. ORs 1.58 (1.49; 1.68), 0.59 (0.47; 0.75), 0.65 (0.53; 0.81), 1.73 (1.67; 1.80), 0.72 (0.67; 0.77), 1.60 (1.54; 1.65), 0.69 (0.67; 0.70); recomputed 1.583 (1.490; 1.682), 0.591 (0.467; 0.748), 0.652 (0.526; 0.809), 1.734 (1.670; 1.802), 0.721 (0.674; 0.771), 1.596 (1.540; 1.655), 0.686 (0.668; 0.705); ok
23. Black trend 0.42 (0.20; 0.64); 0.420 (0.204; 0.637); ok. 0.15→0.21; 0.155, 0.212; ok
24. Brown +0.35, White -0.19; 0.346, -0.188; ok. SD 0.47, p 0.0004; ok
25. Regional slopes North 0.19, South 0.99; 0.192, 0.988 (SE 0.215, CW 0.557, NE 0.637); ok
26. Agreement 0.06 (-0.00; 0.12), corr -0.31; 0.062 (-0.0002; 0.124), -0.314; ok (format)
27. States SC 0.82, RS 0.77, GO 0.50, ES 0.54; 0.824, 0.775, 0.495, 0.541; ok
28. Infant rates 10.7/13.5; ratio 0.79 (0.75; 0.84); 0.794 (0.751; 0.840); ok numerically, wrong estimator label (E1)
29. Certified 1.31 (1.30; 1.32); 1.310 (1.301; 1.319); ok. Census-based 0.80; 0.801; ok. Blank as mother 1.22; ok
30. 1-4: 0.66 (0.54; 0.81), 1.43 (1.40; 1.45), 0.94; 0.663 (0.543; 0.810), 1.427 (1.403; 1.452), 0.944; ok
31. 5-9: 0.67 (0.48; 0.93), 1.21 (1.18; 1.25); 0.666 (0.479; 0.926), 1.213 (1.176; 1.252); ok. Household 0.79/0.78; ok
32. Black/Brown 1.11 (0.83; 1.48), 0.81 (0.78; 0.85); Indigenous 4.61 (3.58; 5.92), 6.00 (5.77; 6.25); ok
33. Without large 0.73 (0.67; 0.80); leave-one-state 0.63-0.70; t 0.77/0.58 (also 0.57, 0.76 unreported); ok
34. Rebouças 0.79/0.69; 0.792, 0.693; ok
35. Regions 400/510, 82%, 157, 446, 114; ok
36. Misstatement 3.15, 1.83, 2.19 (1.92 omitted); corr 0.65; R² 0.06; ok. 22 of 25 in North/Northeast (MG×2, SP outside); ok
37. 15-24 by cause: 0.68 (0.64; 0.71), 0.62 (0.55; 0.69), 0.58 (0.54; 0.61), 0.55 (0.48; 0.62), 0.47 (0.39; 0.55), 0.35 (0.31; 0.39), 0.32 (0.15; 0.49); all ok
38. Brown 0.29→0.61; Brown/Brown 0.65, 0.83; ok. Regional pairs (0.31/0.19 … 0.59/0.29); ok
39. Composition classes 0.39 (0.33; 0.45), 0.17 (0.13; 0.20), 0.91 (0.81; 1.01), 0.79 (0.65; 0.93); ok. Standardised 0.65 (0.62; 0.69), 0.55 (0.52; 0.58), 0.45 (0.40; 0.49); ok
40. Medical examiner share 9.1/83.1/90.5%; 2,163/23,780; 24,463/29,431; 24,530/27,115; ok. Physician 0.69 vs medical examiner 0.58 (0.44; 0.73); 0.37 (0.34; 0.41), 0.60 (0.57; 0.63), 0.43 (0.34; 0.51); ok
41. Facility 0.45 (0.36; 0.54), street 0.35 (0.30; 0.40); ok
42. 1-9: 0.23 (0.16; 0.29), 0.67 (0.54; 0.80); 15-24 0.40 (0.34; 0.45), 0.85 (0.77; 0.93), 0.16 (0.13; 0.19), 0.66 (0.57; 0.76), 0.34 (0.20; 0.49); ok
43. Census 0.88/0.71/0.39, 0.28, 0.41, 0.85; 1-4 0.85/0.77/0.47; certified 1-4 0.80 (0.74; 0.86), 0.59 (0.56; 0.63), 0.24 (0.20; 0.27); partner 0.53/0.11/0.09, 73.8%; instruction 0.18-0.28; 26 of 27; ok
44. Linkage 80.5%, 81.1/81.1/80.2/61.9, 64.9, 76.2, 89.0; flow 383,971, 2,148, 317; validation 0.78/0.76, 0.64/0.64, 0.18/0.18, SE 0.12; found 71.7/51.7/89.8%; median 8, 29.3%, 0, 50.3%, width 0.22; LISA 546/920; South +0.37, Northeast -0.05; 2012 earlier form 7.3%; Discussion 0.13→0.79, 0.55 vs 0.18 ("three times"); all ok

Mismatches: none numerical. One label error (row 28, E1) and one formatting defect (row 26).
