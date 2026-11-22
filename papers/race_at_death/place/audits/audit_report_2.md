# Audit report 2: race at death (manuscript.txt, supplement.txt, figures, results.json)

Scope: numbers recomputed from results/results.json (est +/- 1.96 se; ratios exp(+/-1.96 se/est)); verbal claims checked against printed tables and JSON; figures fig1-8 and figS1-S4 viewed; generators text.py / text_discussion.py read where a sentence is hard-coded.
Locations: "Abstract", "Methods", "Results <heading>", "Discussion", "Table n", "Fig n", "S-" = supplement.

## 1. Errors (must fix)

E1. **"Same children" is not true for the family's classification** (Title; Fig 1; Discussion "Strengths": "compares the certificate with two other classifications of the same children").
Only the mother's race (birth record) and the certificate refer to the same child. The family's classification comes from other children, in the 2010 Census (born about 1991-2010, ages 0-24 in 2010), and is applied by mother's race and age. It is a reference distribution, not a second label on the same child. Fix the title, Fig 1 (which draws three boxes with arrows between them as if they were three labels on one person), and the Strengths sentence. State once, in Methods, that the family's classification is a population-level reference from a different cohort.

E2. **Fig 4C does not show what the sentence says** (Results "Ages 15 to 24": "by single year of age it was seen from 11 to 21 years (Figure 4C)").
(a) The range "11 to 21" is hard-coded (text.py l.301), not derived. In results.json (youth.by_age) at age 11: natural 0.70 (se 0.07) vs assault 0.81 (se 0.33), i.e. the difference is reversed and not estimable; at ages 22 and 23 natural-assault is 0.56-0.44 and 0.58-0.29, so the gap extends to 23 and the stated end point is wrong. A defensible statement would be "at each age from 13 to 24, with overlapping intervals at 22 and 24" after computing it.
(b) Fig 4C plots natural vs "external causes" (all non-natural: suicide, transport, assault) (figures.py l.115), while the sentence is about natural vs assault. The figure does not support the sentence.
(c) The figure shows ages 7-23, outside the stated study population (deaths at 15-24, Methods (c)); ages 7-14 are never described in Methods.
(d) Cohort and age are confounded here: born 2000-2009 and died 2015-2024 means age 24 comes only from the 2000 cohort, age 15 from 2000-2009. Say so.

E2b. **Fig 4 A/B caption and Methods disagree on age range.** Caption: "candidate estimator (1-12 years)"; Methods and Table 1: 1-9 years. Fig 4A/B plot ages 1-10 (and filter se < 0.12).

E3. **"Varied with the certifier" is not supported, and the build itself asserts the opposite** (Abstract Conclusion: "It varied with the racial composition of the municipality, the certifier and the cause of death"; Discussion: "The third reading ... the certified race varied with the place, the certifier and the cause"; Results paragraph on medical examiner).
Printed values: natural deaths, physician 0.69 (0.65; 0.74) vs medical examiner 0.58 (0.44; 0.73): intervals overlap broadly; text_discussion.py l.11 asserts `abs(ph_nat - me_nat) < 1.96*hypot(...)`, i.e. the code itself records that they do not differ. External not assault: physician 0.43 (0.34; 0.51) vs medical examiner 0.60 (0.57; 0.63): the medical examiner certifies White MORE often, opposite to the mechanism proposed ("violent deaths certified by medico-legal services ... the certifier"). Assault: physician 0.40 (0.24; 0.56) vs medical examiner 0.37 (0.34; 0.41): no difference. At 1-9 years (S6): Brown mother, child White, physician 0.31 vs medical examiner 0.29; no difference. Of the four contrasts, none shows the expected direction with non-overlapping intervals. The certifier claim must be removed from the Abstract, Conclusion and the "third reading" paragraph, or stated as "no consistent difference by type of certifier". The conclusion that the third reading "is the one the data support" also rests on place and cause, which equally fit an informant (family) effect that varies by place (certifier vs informant is not separable; limitation 9 says so, but the Discussion and Conclusion do not).

E4. **Abstract and Conclusion omit the restrictions that define the 15-24 and 1-4 estimates.**
Abstract Results: "At 15-24 years, people recorded as White at birth were certified White in 0.68 ... natural causes and 0.35 ... assaults by firearm". These come only from municipalities with fewer than 1,600 births a year: 80,326 of 170,575 deaths (47%); in the larger municipalities (where most capital-city homicides occur) the same quantity is "not estimable" (S5, last rows). The 0.24 for Black mothers at 1-4 years excludes municipalities of 25,600 or more births. Add the restriction to the Abstract Results/Methods and to the Conclusion.

E5. **Abstract Methods misdescribe the study population.** "Deaths at 1-24 years (2013-2024)": the study covers 1-9 years (2013-2024) and 15-24 years (2015-2024, people born 2000-2009); ages 10-14 are not analysed. Fix the sentence; compare also Table 1.

E6. **Text and Fig 3 use different "family" series.** Results "The racial composition": "The family's classification of children under one year moved in the same direction and less: 0.21 to 0.49 ... 0.23 to 0.02" are the age-0 census values (S4 column "Family, under 1 year"; results.json census.gradient['0']: 0.211 -> 0.490; 0.227 -> 0.023). Fig 3 and its caption plot "family (census, ages 1-4)" (Brown mother, child White: about 0.16 -> 0.39; White mother, child Brown: about 0.29 -> 0.02). Fig S3 uses age 0 again. The reader cannot find the quoted numbers in the figure. Use the same age band in text and Figures 3 and S3 (age 0 for infant certificates, 1-4 for 1-9).
Same paragraph: "the family's classification of them as Black did not vary with composition" is true of the 1-4 series (0.39-0.49) but not of the age-0 series quoted for the other cells (0.40, 0.39, 0.35, 0.41, 0.40, 0.41, 0.35, 0.45, 0.43, 0.23; last class 0.23). And "certified Black more often where White births were the majority (0.11 to 0.36)": the series is 0.11, 0.14, 0.14, 0.19, 0.21, 0.21, 0.22, 0.31, 0.36, 0.23; 0.36 is the 80-90% class, the 90-100% class is 0.23 (0.15; 0.32, 94 linked pairs). Say "from 0.11 to 0.36 in the 80-90% class" or describe it as rising up to 80-90% and the last class not estimable with confidence. The Discussion repeats "rose from 0.11 to 0.36" and "the family's was level".

E7. **Validation overstated** (Discussion Strengths: "validates the estimator used after infancy against a one-to-one linkage").
The validation is in infants (found rate 89.8%) only. The estimator is used at 1-9 (found 71.7%) and 15-24 (51.7%), where there is no linked reference, where chance candidates are many more, and where the Poisson-only variance and the "t equal across races" assumption cannot be checked. Within the infant validation, the class of 6,400-25,599 is compatible with the linkage only because intervals are wide (White 0.69 (0.61; 0.77) vs 0.72), and the largest class fails (White 0.85 (0.61; 1.09) vs 0.71). Reword: "validated in infants, in municipalities below 25,600 births".

E8. **"fewer than a quarter of the children under five of Black mothers"** (Conclusion). Printed: 0.18 (0.18; 0.19) under 1 year, 0.24 (0.20; 0.27) at 1-4. The 1-4 estimate has an interval that includes 0.25-0.27; and "under five" pools two estimates from different methods that were never pooled. Write "0.18 before age one and 0.24 at 1-4 years" or "about a quarter or fewer".

E9. **"no trend from 1 to 9 years"** (Results "Age": "the proportion recorded with the mother's race showed no trend from 1 to 9 years").
Table 2 shows Black mothers' children certified Black rising 0.18 (under 1) -> 0.24 (1-4) -> 0.29 (5-9); the single-year series (results.json children_by_age) is 0.24, 0.23, 0.20, 0.27, 0.39, 0.24, 0.30, 0.28, 0.23 with se 0.03-0.10. The honest statement is "no trend detectable given standard errors of 0.03-0.10", and it cannot be set against the family's rise (0.39 -> 0.55 -> 0.62) as a contrast, which the Discussion does ("compatible with a colour that is assigned to newborns provisionally"). Also that family age gradient is cross-sectional (age 0 = born 2010, age 19 = born 1991) and conditional on co-residence with the mother (97% at age 0 vs 76% at 15-19, 52% at 20-24): cohort and selection effects are not considered.

E10. **Implications contradict the closing caveat and the data.**
(a) "deaths classified by the mother's race ... measure a contrast that certified race does not": this treats the mother's race as the valid classification; the final paragraph says the design "does not establish which classification is correct".
(b) "can be estimated from public files without individual linkage in all but the largest municipalities": at 1-4 years the ratio by mother's race is 0.66 (0.54; 0.81) only with all municipalities included; excluding the largest the estimate moves to 0.73 (0.67; 0.80); by state it is "not estimable" in 17 of 27 states; at 15-24 years the estimator works only below 1,600 births a year (S5), so "all but the largest" is false for that age group.

## 2. Points to fix

P1. **The policy-relevant comparison is missing.** The "certified race" rate ratio divides certified deaths by births classified by the mother's race (Table 4 note), a hybrid that no statistics office computes. Official rates divide certified deaths by a census-based denominator. The family's classification column applies census proportions to BOTH deaths and births. Neither shows what the conventional rate (certified deaths over census-classified population) does. Without it, "reversed the direction of the White to Brown mortality rate ratio" is relative to the mother's-race denominators only; the family's version (0.79) is also below 1, so the claim of reversal depends on which denominator the reader considers conventional. Add that column or qualify the sentence in the Abstract and Conclusion.

P2. **Circularity of the mixture model (Table 3).** With "certified race of local deaths" as the reference, the reference distribution is made of the same certificates being modelled (and, in the class where a child lives, includes the child's own certificate); lambda is biased toward 1 in small cells. The "race of the mothers of local births" reference avoids this and gives different weights (infants: White 0.44 vs 0.55, Brown 0.75 vs 0.62, Black 0.41 vs 0.32; 1-9 years: Brown 0.85 vs 0.72, Black 0.59 vs 0.54), so the magnitudes depend on the reference (the ordering Brown > White > Black for infants, Brown > Black > White at 1-9 holds in both). The Discussion quotes only the deaths-reference set ("0.55, 0.62 and 0.32"); give both. The fit for Black mothers is poor (rms 0.087 and 0.074 with the model vs 0.126 family-only; 1-9 years 0.095 vs 0.167): lambda for Black mothers is not interpretable as a weight, and the Discussion's reading ("the Black category is used where the reference is White") is a post hoc description of the Fig S3 panel, not a model result. Lambda is also estimated from classes of composition that mix region, municipality size and period (confounding by place is the competing explanation for the whole gradient).

P3. **Confidence intervals of zero width mislead** (Abstract: "0.64 (95%CI 0.64; 0.64)", "0.76 (0.76; 0.77)"). These are complete registers, not samples; binomial intervals ignore that 19.5% of deaths were not linked and 4.1% of linked deaths (12,691 of 309,203) have no mother's race, that linkage success varies by municipality, and that pairs cluster by municipality. State what the intervals measure (sampling variation of linked pairs only) or widen them by a cluster (municipality) bootstrap.

P4. **Linkage and missing data not reported (RECORD 12.x, STROBE 12c/12d, 14).**
(a) No comparison of linked and unlinked infant deaths by race/size/year (Harron guidance, ref 35, is cited as followed; it is not). If linkage differs by mother's race, the proportions (and the infant rate ratios, which use the linked share for all 381,514 deaths) are biased in a known direction.
(b) 383,975 certificates (Methods, Table 1) vs 381,514 deaths in Table S2 and in the denominators of the rates: 2,461 deaths unexplained.
(c) Deaths with no race on the certificate are excluded from the certified rates (Table 4 note), but their share differs by mother's race (5.6% White, 8.8% Brown, 8.5% Black mothers on infant certificates): the certified rate ratio is biased by differential missingness; not discussed or quantified.
(d) No algorithm details: m/u or weights, threshold, expected false-link rate; no sensitivity analysis to the threshold.
(e) No flow of records for the 1-9 and 15-24 analyses (deaths in range, excluded for missing municipality/sex/birth date, born before 2012 or 2000, in municipalities beyond the size limit).

P5. **Mother's race on the birth record is taken as the reference without examining its quality.** SINASC field "mother's race" is completed by hospital/registry staff in practice (the manual's self-declaration is an instruction, as the paper itself says for the certificate in the Introduction). Place-dependent behaviour of the same kind as the one hypothesised for certifiers could also affect the birth record, in which case part of the "certificate departs from the mother" is noise or place effect in the reference. Limitation (7) covers only the pre-2012 form. Add the point, and the 7.3% of 2012 births still on the old form, to the limitations.

P6. **Unreported composition measure issues.** The municipal White share is computed from births of 2012-2023 (the same births that serve as denominator and as "mother's race"), and applied to people born 2000-2009 who died 2015-2024 (Methods Variables; Table 5). It is a different cohort, measured up to 23 years later and in places where migration and reclassification occurred. Limitation (10) mentions wide classes only. The standardisation (five classes) also removes only part of the place effect; the claim "present in every class of composition" is not demonstrated in the 80-100% class (natural 0.91 (0.81; 1.01) vs assault 0.79 (0.65; 0.93)) nor in the 0-20% class for external-not-assault vs assault (0.17 vs 0.17).

P7. **Statements "in every ..." and "below 1 in 8 of 10 states" ignore the intervals.** Results "Mortality under each classification": "By certified race the ratio exceeded 1 in 26 of 27 states": RS 1.06 (0.93; 1.20) and SC 0.95 (0.82; 1.10) include 1, so 25 of 27 are clearly above 1. "by the mother's race it was estimable in 10 states and below 1 in 8": only MG 0.73 (0.54; 0.99) excludes 1; the other nine intervals include 1 (PE 0.38-1.18, ES 0.40-1.25, SP 0.35-1.12, PR 0.62-1.12 ...). State "point estimates below 1 in 8 of 10 states, with an interval excluding 1 in one". In Centre-West the ratio by mother's race is 1.14 (0.77; 1.70), above 1; the sentence "The difference ... was largest where the certificate departed most from the mother's race" does not define or show that departure by region.

P8. **Rebouças et al. comparison** (Discussion). "hazard ratio of 1.30 for children of Brown mothers corresponds to 0.77" and "agrees" with 0.66 (0.54; 0.81): the study's outcome is mortality before age 5 (the infant ratio here is 0.79), the HR may be adjusted, cohorts and period differ; I could not verify 1.30 against the paper in this audit (the earlier reading report did not read it). Compare with the infant ratio (0.79, 0.75-0.84) and an under-5 pooled ratio, or drop the "agrees"; the sentence "is an effect of the certificate and not of the estimator" is causal; the infant analysis (no estimator, same reversal 0.79 vs 1.31) is the stronger argument and should be the one cited.

P9. **Discussion links an infant trend to census trends** ("The certified Black share of those infants rose from 0.15 in 2013 to 0.21 in 2023, in the period in which the Black share of the population grew between censuses"). The quantity is conditional on mother being Black; population growth of Black identification does not imply certification of Black mothers' children changed. Alternative: composition of Black mothers changed (Black share of births rose 5.6% to 7.9%, S1), plus changes in informant behaviour and in linkage. Not tested; label as speculation. Also the 2010-2022 census interval does not coincide with 2013-2023.

P10. **Cohort analysis (Fig 8, S7) is a result without a method.** Methods give one sentence on a "cohort-component population account constrained to official estimates [29]"; there is no description, no uncertainty, no data source for the 2000 and 2022 census microdata, and the account is not a published product. The conclusion "cohorts moved away from White" cannot separate reclassification from differential mortality, migration, coverage and the constraint itself; the Discussion treats it as reclassification and, via selection, as an explanation for the cause gradient. Either describe the method (inputs, assumptions) and limits in Methods and Limitations, or drop it. Also "fell in 26 of 27 intervals" counts the 2000-2004 cohort between the 2000 Census (aged 0-4) and 2010, where the base is a child cohort, as comparable with the 1940 cohort aged 60+ (mortality selection); the interval table is not shown.

P11. **Triples analysis (S2, S8) appears only in the Discussion.** Its data (Hospital Information System, 1,208,430 delivery admissions) are not in Methods "Data sources"; its numbers (0.55 (0.48; 0.63) for adult Black women) enter the Discussion as evidence ("three times the proportion found for the infants") with no Results subsection. Population differs (adult women who died in hospital, mothers in municipalities under 2,000 births), 28.2% false pairs removed "in expectation" under an assumed regional distribution; none of that is in the main paper's limitations. Add a Methods and Results paragraph, or state in the Discussion that it is exploratory and give the caveats.

P12. **Census standard errors and design.** Table 2 note: "standard errors below 0.005, not shown". Say how they were computed (replicate weights? Taylor linearisation with the sample design? simple weighted). Ignoring weighting areas understates them. Partner analysis: "partner being the man with whom she heads the household" excludes same-sex couples and stepfathers; "classification of the child followed both parents" over-reads this (the partner is not necessarily the father; partner identified for 73.8%).

P13. **Table 2 mixes ages.** Certificate "under 1 year" is set next to family "1-4 years", although the census gives age 0 (Brown mother, child White 0.28; Black mother, child Black 0.39; White mother, child White 0.88; Brown mother, child Brown 0.71). At matching age the infant certificate (0.25 White for Brown mothers' children; 0.64 Brown) is not further from the family than the family is from the mother's race: the contrast "departed further from the mother" is clear, but the claim that the certificate "does not record what the family would answer" rests on the Black category (0.18 vs 0.39) and on composition dependence, not on the Brown-to-White exchange (0.25 vs 0.28). Show the age-0 family row in Table 2 and Fig 2 for the infant column; the Discussion should say where the certificate agrees with the family.

P14. **Mortality cohorts for 5-9 years.** Deaths at 5-9 years of children born from 2012 exist only from 2017 onwards: 1,242 of 17,547 deaths are in 2013-2018 (by_period), the rest in 2019-2024, and with the smaller found rate (0.71). The age 5-9 estimates depend almost entirely on post-2019 births and deaths in the pandemic years. Note this in Methods or Table 4 notes.

P15. **Alternative explanations not acknowledged** for the composition gradient: heterogeneity of the mother's category within places (a Brown mother in the South differs from one in the North), place-dependent informant behaviour, and ecological confounding (composition covaries with region, income, municipality size, hospital vs home deaths). The census "family" series is national by class of composition, whereas the place-specific family classification is unobserved (the census can give it by composition class only for 2010 and the births defining composition are 2012-2023).

P16. **Multiplicity and exploratory status.** Abstract and Conclusion present subgroup contrasts (cause, composition, schooling) with the same weight as the registry-based primary comparison. The "exploratory" label is in Methods only. Add to the Conclusion; list the number of contrasts reported (Tables 5, S5, S6 contain hundreds of intervals).

P17. **Schooling result** (Results "Schooling, partner..."; Discussion). At 1-9 years the schooling gradient "within classes of composition ... was not consistent" yet the Discussion states the gradient "rose steeply ... within every class of municipal composition" without saying it holds only at 15-24. The 15-24 schooling analysis uses "colour at birth" (staff-classified) vs mother's schooling: higher-schooled mothers deliver in private hospitals where staff, and the family's self-presentation, differ; the "classification by social cues" and "selection" readings are two of several, and the confounding by cause (assault concentrates in low-schooling strata) and place is only partly handled (3 composition classes). The numbers "0.40 (0.36; 0.43) to 0.77 (0.68; 0.87)" for all causes are in no printed table (results.json context.youth.by_schooling.all; S5 gives them only by cause).

P18. **Hard-coded and unsupported statements.** "often without a relative present" (Discussion, certifier paragraph) has no reference or data; "the largest were exchanges between White and Brown" (Implications) is true for 15-24 firearm assault but the Black-to-Brown exchange is larger for infants (0.55); "whatever the mechanism, the numerator of a homicide rate by race is classified in a way that depends on the homicide itself": the data are for people recorded White at birth (a subset of one category), in municipalities under 1,600 births; the result concerns that exchange, not the homicide rate by race in general. Qualify.

P19. **Telles 2002 "agreed in 79% of cases"** (Introduction): not read in the earlier reading report; verify. Santos et al. is printed "2019;65(1)" in ref 24; Crossref gives volume 65 (2020) per the reading report.

P20. **Estimability rule differs between text and code.** Methods: "An estimate with a standard error above 0.15 is reported as not estimable". The code (`cc`) also suppresses when the estimate is below -2 se or above 1+2 se. Table 2 notes only the first rule; Table S5/S6 show values such as 1.01 (0.84; 1.19) and 0.87 (0.71; 1.03) next to "not estimable" cells. State both rules, and state that Table 2 shows impossible values deliberately.

P21. **Fig 5/Table 4: no interval for the family's counterfactual** (acknowledged); but Abstract quotes "0.79 under the family's classification" next to intervals for the other two, which invites reading it as equally precise. Add "(no interval)".

## 3. Minor

M1. Racial categories are given in English only (White, Black, Brown, Indigenous, Yellow); define once with the Portuguese terms and the census wording (branca, preta, parda, indigena, amarela). "Brown" and "Black" are not the same as the Brazilian grouping "negros (pretos e pardos)", mentioned only in the Implications.
M2. "ICD-10" and "DuckDB" not expanded; "RECORD" is only cited (spell out at first use).
M3. Table S1 caption says 2000-2024 births; Methods says births 2000-2023. S1 column "Mother's race filled, %" is 0.0% for 2000-2009 while the share columns for those years are colour at birth; add a note.
M4. Table 5: "Assault, other means" and "Assault, certified by physician/medical examiner" (which includes firearm, other means and legal intervention) are confusable; label "Assault (all, with legal intervention)". Column headers "Black certified Black" do not say "recorded Black at birth".
M5. Table 5 note repeats "Not estimable: standard error above 0.15" but cells with est outside 0-1 beyond 2 se are also suppressed.
M6. Fig 1: arrows (mother -> family -> certifier) read as a causal sequence; the labels "mother and child in one household" and "family's classification against the certifier's" are cryptic; the birth record box says "live births, from 2012" but the 15-24 analysis uses colour at birth of 2000-2009.
M7. Fig 2: panel D has no colour bar and mixes a diverging scale with annotations of "-0.00"; panel B (under 1) beside A (ages 1-4) invites the age mismatch of P13.
M8. Fig 4: y-axis label "Proportion classed with the mother's race" is applied to panel C, which shows proportion certified White among those recorded White at birth (a different quantity). Panel A certificate point at age 0 has no interval; panel A age 10 bar crosses 0 (clip). Natural series start at age 7, external at 11, unexplained.
M9. Fig 5: panels 1-3 share no y label beyond the first; panel 4 has no x-axis label ("rate ratio"), and "<1 y" placed at the bottom reverses the reading order of the table; Black is drawn with a black line over error bars of other groups.
M10. Fig 6: colour scale saturates at about 2 while values reach 4.13 (AL); panel A shows 17 grey cells, which is the main message but is not stated in the caption ("n.e." only).
M11. Fig 7B: legend text overlaps the data and error bars ("assault and legal intervention" overprinted by the natural-causes line at 0.7-0.8). Fig 7A: numbers on the right are both-sex estimates but are not labelled so.
M12. Fig 8: the dashed "birth record" markers are placed at 2002 and 2007 on an axis of census years and joined to census points with a dashed line, implying continuity; the legend appears only in panel C. Fourteen cohort lines in one hue ramp are not separable; colour bar label "first year" fine.
M13. Fig S1B: y label "Proportion certified with the mother's race" covers three different cells (White-White, Brown-Brown, Black-Black); say so. Fig S2: North 5-9 has no interval (not drawn) without a note; the certified squares carry no values. Fig S4B: legend overlaps the Brown error bar at 12 or more years; panel C legend uses "30-59%" while the text uses "30% to 60%".
M14. "Centre-West" vs "Midwest": fine, but "Southeast", "Northeast" etc. are used without the list of states.
M15. Development-history sentences in the supplement: S1 "A control that moves the birth date by whole weeks samples other days and undercounts E; with it the estimated t exceeded 1 in municipalities with 6,400 or more births per year" describes a rejected earlier method; S2 table note "All estimates are shown as obtained"; Methods "a bound chosen after inspecting the estimates" (honest, but belongs in Limitations only). Remove or recast the first two.
M16. The placeholder line "[Authors, affiliations, ORCID, funding, ... to be supplied by the authors; not part of the blinded text]" and "read in November 2026" are fine for a draft; check before submission (journal blinding rules).
M17. Methods: "Deaths of 2023 and 2024 are subject to revision" (stated twice, once in limitation 11) and "No hypothesis test was pre-registered" - merge.
M18. Discussion "everyone recorded White at birth is less often certified White" ("everyone" should be "people").
M19. Results opening "over all sizes, 0.78 against 0.76" follows a sentence about "fewer than 25,600"; "over all sizes" includes the largest class where the estimator fails; reorder.
M20. Table 3 has the mother's race ordering White, Brown, Black but Table 4 orders White, Brown, Black, Indigenous with Brown as reference; consistent. Table S6 "Class" column holds both the partner's race and the schooling class and "Mother's race" the next column: add subheaders.

## 4. Reporting completeness (RECORD/STROBE) not met

- Flow of records for each analysis (P4e); linked vs unlinked comparison (P4a); missing data by variable (certified race, mother's race, schooling, certifier "not recorded" 2,013 natural / 884 / 522 deaths are in denominators but not described).
- Linkage algorithm: parameters, threshold, quality evaluation (RECORD item 12.3, 12.2 on codes and algorithms; STROBE 12).
- Codes: ICD-10 groups given; the "assault by firearm X93-X95 / legal intervention Y35-Y36" ok; but "natural causes" definition (all non-V/W/X/Y?) and the handling of Y10-Y34 (undetermined intent, a large group in Brazil) is not stated ("other external causes" presumably).
- Funding, data access and code location (statement that code accompanies the article: give a repository).
- Generalisability: all 15-24 results are for municipalities under 1,600 births a year; infants and 1-9 for all but the largest; statement in Discussion limitation only.
- Bias section: no quantitative bias analysis for linkage error or for the candidate estimator's "t equal by race" assumption (a sensitivity analysis with t differing by race, e.g. 0.8 vs 0.9, would show how the 0.66 moves).
- Sample/precision: no information on the number of deaths per cell used for the intervals reported with "not estimable" cut-offs chosen after inspection (0.15, 0.12, 0.35, 0.6 are four different thresholds: Methods 0.15; Fig 7 0.12; Fig 6 0.35 of the estimate; Fig S2 0.6 of the estimate; give one rule).
- Ethics: the statement is adequate; add that linkage of records from separate public files remains non-identifying.

## 5. Numbers recomputed (location; printed; recomputed; status)

1. Abstract / Table 2 infants, White mother certified White; 0.76 (0.76; 0.77); 0.763 se 0.00141 -> 0.76 (0.76; 0.77); ok
2. Abstract, Brown mother certified Brown; 0.64 (0.64; 0.64); 0.6407 se 0.00113 -> 0.64 (0.64; 0.64); ok
3. Abstract, Black mother certified Black; 0.18 (0.18; 0.19); 0.1837 se 0.00259 -> 0.18 (0.18; 0.19); ok
4. Abstract, Black mother at 1-4 certified Black; 0.24 (0.20; 0.27); 0.2407 (se from JSON) -> 0.24 (0.20; 0.27); ok
5. Abstract, family Black 1-4 for Black mothers; 0.47; 0.4650 -> 0.47; ok
6. Abstract / Results composition, Brown mother child White 0.13 and 0.79; 0.1337, 0.791 (bins 0, 9); ok
7. Abstract, White mother child Brown 0.54 and 0.02; 0.545, 0.0233; ok
8. Abstract, White to Brown rate ratio 1-4 by mother 0.66 (0.54; 0.81); 0.6632, se 0.0676 -> 0.543; 0.810; ok
9. Abstract, family's 0.79 at 1-4; 0.7888; ok
10. Abstract, certified 1.43 (1.40; 1.45); 1.4271 se 0.01245 -> 1.40; 1.45; ok
11. Abstract, 15-24 natural White certified White 0.68 (0.64; 0.71); 0.6753 se 0.0197 -> 0.64; 0.71; ok
12. Abstract, firearm 0.35 (0.31; 0.39); S5 and Table 5; ok (as printed; derived from same cell structure)
13. Abstract, standardised 0.65 and 0.45; 0.65 (se 0.019), 0.45 (se 0.022); ok; but 0.45 is "assault" (all, with legal intervention), the Abstract pairs it with firearm assaults (label mismatch, see P/E)
14. Methods, 20,635,472 records, 190,755,799 persons; 20,635,472; 190,755,799.0; ok
15. Methods, 6,252,654 pair records; 6,252,654; ok
16. Methods, 94.1% (1-4) and 76.5% (15-19) with mother; 0.9413, 0.7645; ok
17. Methods, infant 383,975 / 309,203 (80.5%) / 296,512; 383,975; 309,203 (80.52%); 296,512; ok; but 381,514 in S2/rates (4,P4b)
18. Methods, field filled 2.5%, 55.0%, 92.7% (2010-2012); S1 matches; ok
19. Methods, 77,693 = 60,146 + 17,547; sums to 77,693; ok
20. Methods/Table 1, 80,326 deaths under 1,600; 23,780+5,925+16,115+7,391+5,052+20,795+1,268 = 80,326; ok
21. Results, 71.7% found at 1-9; 0.7173; ok. 51.7% natural 15-24; 0.5174; ok
22. Results, validation 0.78 vs 0.76, 0.64 vs 0.64, 0.18 vs 0.18; 0.779/0.763; 0.639/0.641; 0.176/0.184; ok. SE for White in largest class 0.12; (1.09-0.61)/2/1.96 = 0.122; ok
23. Results, Black mother: 0.55 (0.54; 0.56) Brown, 0.18 (0.18; 0.19) White; 0.5485 se 0.00333; 0.1816 se 0.00258; ok
24. Results, 1-4 certificates 0.80 (0.74; 0.86), 0.59 (0.56; 0.63); 0.80 (0.74; 0.86); 0.59 (0.56; 0.63); ok
25. Results, Indigenous 0.84 (0.83; 0.85) vs family 0.85; certificate 0.8434; family age 0 0.852; ok
26. Results, other category 8.8% (Brown) and 5.6% (White); 0.0880; 0.0565; ok
27. Results, family 1-4: 0.85, 0.77, 0.47, 0.21, 0.39; 0.847, 0.767, 0.465, 0.214, 0.388; ok
28. Results, region White certified White North 0.40, South 0.92; Brown certified Brown 0.76, 0.24 (S3); ok
29. Results, lambda Table 3 (12 rows, e.g. 0.55 (0.51; 0.59), 0.32 (0.23; 0.42), 0.85 (0.72; 0.98), 0.59 (0.53; 0.65)); recomputed all 12; ok
30. Results, family age series Black child Black 0.39, 0.55, 0.62; 0.393, 0.552, 0.619; ok
31. Results, Brown child White 0.28, 0.16, 0.16; 0.277, 0.164, 0.164; ok
32. Results, first week 0.21 / after 28 days 0.34 (S3); ok
33. Results, 2013 to 2023 Black 0.15 to 0.21; Brown 0.60 to 0.66; (S3) ok
34. Results, infant mortality rates 10.7, 13.5; 10.688, 13.454; ok
35. Results, ratio 0.79 (0.75; 0.84); 0.7944 se 0.0226 -> 0.751; 0.840; ok
36. Results, certified ratio 1.31 (1.30; 1.32); 1.3096 se 0.00456 -> 1.30; 1.32; ok
37. Results, 5-9: 0.67 (0.48; 0.93); 0.6657 se 0.1121 -> 0.478; 0.927; ok. 1.21 (1.18; 1.25); 1.2134 se 0.0195 -> 1.17; 1.26 vs printed 1.18; 1.25: the printed bounds use the exp formula: 1.2134*exp(+/-0.0315) = 1.176; 1.252; ok
38. Results, family 0.79 at 1-4 and 0.78 at 5-9; 0.7888; 0.7833; ok
39. Results, Black vs Brown 1.11 (0.83; 1.48) and 0.81 (0.78; 0.85); Indigenous 4.61 (3.58; 5.92) and 6.00 (5.77; 6.25); all recomputed; ok
40. Results, without the largest, 0.73 (0.67; 0.80); 0.7343 se 0.0336 -> 0.67; 0.80; ok. Leave-one-state-out 0.63 to 0.70; 0.635 to 0.701; ok (0.6349 prints 0.63)
41. Table 4 rate ratios from rates (10 ratios, e.g. 10.7/13.5 = 0.79; 14.0/10.7 = 1.31; 5.2/10.7 = 0.49; 63.0/56.8 = 1.11; 34.1/42.0 = 0.81; 24.7/23.6 = 1.05; 56.2/18.3 = 3.07); ok within rounding (Black infants 16.9/13.5 = 1.252 vs printed 1.26 from unrounded 1.2555)
42. Results, regional 1-9 ratios: North 2.66 / 0.66 (0.35; 1.26); Northeast 2.46 / 0.78 (0.61; 0.99); South 1.21 / 0.84 (0.67; 1.05); recomputed; ok
43. Results, 26 of 27 states above 1; count of ratio_certificate > 1 = 26; ok (but see P7: 2 intervals include 1)
44. Results, 10 states estimable, 8 below 1; 10 and 8; ok (see P7)
45. Results, Table 5 natural 0.68 (0.64; 0.71), Brown certified Brown 0.65 (0.61; 0.69), Brown certified White 0.21 (0.19; 0.24), Black certified Black 0.27 (0.21; 0.33); recomputed from JSON; ok
46. Results, medical examiner shares 9.1%, 83.1%, 90.5%; 2,163/23,780 = 9.10%; 24,463/29,431 = 83.12%; 24,530/27,115 = 90.47%; ok
47. Results, 0.39 (0.33; 0.45) / 0.17 (0.13; 0.20) (under 20%) and 0.91 (0.81; 1.01) / 0.79 (0.65; 0.93) (80%+); recomputed; ok
48. Results, schooling 0.40 (0.36; 0.43) -> 0.77 (0.68; 0.87); 0.40 se 0.017; 0.77 se 0.050; ok (not in any printed table)
49. Results, within-composition 0.20 (0.17; 0.23) -> 0.63 (0.46; 0.81); 0.72 (0.64; 0.80) -> 0.87 (0.71; 1.03) (S5); ok
50. Results, partner: 0.53, 0.11, 0.09 and 0.17, 0.21, 0.78; 73.8% identified; S6 and JSON (0.7384); ok. Instruction 0.18 and 0.28 (S6); ok
51. Results, cohorts 2000-2004: 53.4, 43.6, 39.1; 42.7, 48.8, 49.0; 2.7, 6.1, 10.7 (S7); ok. 26 of 27 intervals (cohort_falls); ok (exception 1940, 2010 to 2022: 54.8% to 54.9%)
52. Discussion, 0.55/0.18 = 3.06 ("three times"); ok. 0.18/0.39 = 0.46 and 0.24/0.47 = 0.51 ("about half"); ok
53. Discussion, Rebouças 1/1.30 = 0.769, inside 0.543; 0.810; ok (comparability: see P8)
54. S2, per-size deaths sum 381,514; linked pairs sum 296,512; S3 regions sum 296,512; ages sum 296,512; ok
55. S9, states with certified ratio below 1: SC 0.95 only; ok; mother's-race estimable: PE, BA, MG, ES, SP, PR, SC, RS, MT, GO; ok

Mismatches among recomputed numbers: none arithmetical. The defects are in verbal claims and hard-coded text (E2, E6, E9, E3 above) and in the unexplained 383,975 vs 381,514.
