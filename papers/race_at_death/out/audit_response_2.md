# Response to audit report 2

Each point of `audit_report_2.md`, what was done in the generators (`analysis/*.py`, `text*.py`, `figures*.py`, `build.py`) and where
the result is. "Already fixed" means the build audited had already changed before this response; none was. Every
change below is asserted in the build where it is a verbal claim.

## 1. Errors

| point | action |
|---|---|
| E1 "same children" | Title, Figure 1 and Strengths rewritten: the family's classification is described in Methods as a population-level reference from the 2010 Census, other children of mothers of the same race, age and municipality, not a label on the deceased. Figure 1 redrawn as two levels (individual linkage; population reference). |
| E2 Fig 4C and "11 to 21" | The single-age statement is now computed: the ages at which natural minus assault exceeds 1.96 standard errors are derived from `youth.by_age` and printed; the figure plots natural against assault (not all external causes), ages 15-24 only; the confounding of age and birth cohort is stated in the caption and Methods. The age figure moved to the supplement. |
| E2b caption 1-12 vs 1-9 | The age figure plots ages 1-9; caption and Methods agree. |
| E3 certifier | "Certifier" removed from the Abstract, Conclusion and the third-reading paragraph; the text states that physicians and medical examiners did not differ beyond chance and that the certifier and the informant cannot be separated. The multilevel models add the certifier of each linked infant death and a crossed random effect of the establishment of death (Results, competing explanations). |
| E4 restrictions | The Abstract and Conclusion state the restriction to municipalities under 1,600 births a year (15-24) and under 25,600 (1-9). |
| E5 study population | Abstract Methods: deaths at 1-9 years (2013-2024) and at 15-24 years (born 2000-2009). |
| E6 family series | Text and figures use the age-0 family series with infant certificates and ages 1-4 with certificates at 1-9; the Black-category sentence quotes the range up to the 80-90% class and says the last class is imprecise. |
| E7 validation | "validated in infants, in municipalities with fewer than 25,600 births a year"; the found rates at 1-9 and 15-24 and the unverifiable assumptions are stated. |
| E8 "under five" | Replaced by the two estimates with their intervals. |
| E9 "no trend 1 to 9" | "no trend detectable given standard errors of 0.03 to 0.10"; the cross-sectional, co-residence-conditioned nature of the family's age gradient is stated; the Discussion no longer sets the two against each other. |
| E10 implications | Rewritten: no classification is treated as correct; the estimator's reach is stated per age (all but the largest municipalities at 1-9, under 1,600 births at 15-24). |

## 2. Points

| point | action |
|---|---|
| P1 conventional denominator | Added. Infants: certified deaths over births by mother's race is the Ministry's own indicator; over the population account's children under one the ratio is printed. 1-4 years, 2016-2024: certified deaths over the population account by race give a ratio near 1, between the mother's-race ratio and the births-denominator one. Abstract and Conclusion say "reversed with births as the denominator, compressed toward 1 with the census population". |
| P2 mixture model | Moved to the supplement (Table S16, Figure S3) with both references side by side, the circularity of the certified reference and the poor fit for Black mothers stated; its role in the thesis is taken by the spatial and multilevel models, which test composition against state and context directly. |
| P3 intervals | Main proportions carry a bootstrap over municipalities (400 resamples), whose errors are 5-10 times the binomial ones; Methods says what the intervals measure. |
| P4 linkage reporting | (a) linked share by certified race, size, year, region and age (Supplementary Table); it does not differ between White, Brown and Black certificates. (b) the 2,461 deaths: no sex (2,148) or no municipality (317). (c) blank race by mother's race and the certified ratio with blanks given the mother's race. (d) the linkage's keys are stated; its weights and threshold are in the package's link specification and are not printed (not done). (e) infants: flow in Supplementary Table S11; at 1-9 and 15-24 years the deaths entering and the share found are in Table 1 and the Results, without a per-step flow (not done). |
| P5 mother's race quality | Limitation added, with the share of 2012 births still on the old form. |
| P6 composition measure | Limitation added; the municipal models use the composition of the same municipality-years. |
| P7 intervals in counts | The state counts are gone with the tile map; states keep their intervals in Supplementary Table S9, and the regional statements of the main text now come from BYM2 models with credible intervals (immediate regions: ratios below 1 credibly in 157, above 1 credibly in 446, both reversed credibly in 114). |
| P8 Rebouças | Read in full (PMC9638038). The 1.30 is an adjusted hazard ratio; the comparison is now with the crude rates of their Table 2: 38.24 and 55.19 per 100,000 person-years at 1-4 years (ratio 0.69), 951 and 1,201 under one year (0.79). The causal sentence removed; the infant analysis (no estimator) is the argument. |
| P9 Black trend | Stated as description; alternative explanations listed; the trend is now analysed by intermediate region with random slopes. |
| P10 cohorts | Moved to the supplement with the method and its limits stated. |
| P11 triples | Kept in the supplement, labelled exploratory, with the caveats in the Discussion. |
| P12 census errors | How the standard errors are computed is stated, and that they ignore the sample design (understated); the partner sentence says "partner" not "father". |
| P13 Table 2 ages | The age-0 family row is in Table 2 and Figure 2; the Discussion says where the certificate agrees with the family (Brown to White in infants). |
| P14 5-9 years | Note on cohorts and pandemic years in Methods. |
| P15 alternatives for composition | Now tested, not only acknowledged: state fixed effects, border pairs, capital and metropolitan status, GDP, schooling, services and recording quality, individual characteristics (Results, competing explanations). |
| P16 multiplicity | Exploratory status in the Abstract and Conclusion. |
| P17 schooling | The 15-24 all-cause schooling row printed in Supplementary Table S5; the Discussion limits the within-composition claim to 15-24. |
| P18 hard-coded statements | "often without a relative present" removed; the exchanges sentence qualified by age; the homicide sentence restricted to people recorded White at birth in small municipalities. |
| P19 Telles, Santos | Telles 2002 abstract read ("consistent 79 per cent of the time"); Santos et al. printed 2020;65(1) (Crossref's 2019 is the online date). |
| P20 one estimability rule | Both suppression rules stated once in Methods and in every table note; the figure thresholds now use the same rule. |
| P21 family interval | "(no interval)" printed next to the family's ratio. |

## 3. Minor (M1-M20)

Portuguese category names defined once; ICD-10, DuckDB, RECORD expanded; S1 caption 2000-2024 and note on the mother's field;
Table 5 labels; Figure 1 redrawn; Figure 2 colour bar and no "-0.00"; age figure axes; Figure 5 panel labels and order; the
state tile map replaced by real geometries; Figure 7 legend placement; cohort figure in the supplement with legend in
every panel; S1-S4 labels; regions listed by state; development-history sentences removed from S1; Methods merged sentences;
"everyone" to "people"; the validation paragraph reordered; Table S6 subheaders.

## 4. Reporting completeness

Flow of records, linked against unlinked, missing data by variable, codes for natural causes and undetermined intent
(Y10-Y34 in "other external causes"), data and code location placeholder, generalisability, a quantitative bias
analysis for the equal-t assumption (the White to Brown ratio with t differing by race), and one estimability rule.
