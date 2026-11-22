# Review 1 - Paper 4 (family): "The race of a child in the household ..." (Censuses 2010, 2022)

Reviewer and numerical auditor. Read only. Not run: build.py, analysis scripts. Note: `family/out/manuscript.txt` and `supplement.txt` do not exist; the .docx files were read (text extracted, scratch copy only). Recomputation used `pairs_*.parquet` with independent code (scratchpad), plus a refit of the Brown-mother logistic model.

## 0 Overall judgement

**Major revision** (Demography / ERS / SSR standard).

Descriptive core is sound and the numbers are reproducible: every Table 1 cell, the counts, partner shares, standardisations and the main logistic ORs recompute exactly (section 7). The pairing script reads the right layout positions in both censuses.

What fails is inference, not arithmetic. The headline reading, "households classify a child by the partner, not by the mother alone", is stated as a rule of classification. The data fit at least two rivals equally well, and the paper's own data contradict the rule form:

1. **Ancestry or phenotype.** A child of a White father and Brown mother is on average lighter. This is not testable with "partner" lumped, and the file allows the test (relation 04 vs 05/06). The test gives the partner effect about three times larger for the father than for a stepfather.
2. **Sibling discordance.** In Brown-mother, White-partner households with at least two children aged 0-9, 41-42% classify siblings differently (White vs not). A household rule cannot do that.

The informant section's headline ("hardly depended on who answered") is an average of opposite-signed within-partner effects. The "same children darker as they grow" claim rests on a comparison that cannot identify aging. Category drift between censuses (White -4.2 pp, Black +2.7 pp, Yellow -0.7 pp of the population; Black mothers' schooling profile transformed) is acknowledged in one sentence and never tested.

Fixable with the data already held, plus one re-run of pairs.py to add informant order numbers. Rewording of Abstract, Discussion and Conclusion is mandatory.

## 1 Errors (code, number, claim contradicted)

| # | Location | Evidence | Fix |
|---|---|---|---|
| E1 | Results "The partner": "the rise was concentrated with White partners (census by White partner interaction 0.15, SE 0.01)" | family.json `brown\|is_white\|interaction`: White 0.146 (SE 0.011), **Black partner 0.182 (SE 0.023)**, other -0.26, no partner 0.026 (ns). The census change is in non-Brown partners (White and Black), not "concentrated with White". On the probability scale the White-partner rise is larger (+5.2 pp vs +2.1 pp), a scale artefact of the base rate. | Say "in households with a White or a Black partner (log-odds +0.15 and +0.18), not with a Brown partner or none". Report the Black-partner row. |
| E2 | Methods: "this rule kept 88% of the pairs the order number identifies" | 88% (6,141,796 / 7,008,474) is **all ages 0-24**. For the analysed 0-9: Brown 1,201,189 / 1,466,314 = **82%**, Black 191,631 / 234,232 = **82%**, White 84%. | Report 0-9 (and by mother's race) coverage; state 18% of co-resident children are outside the rule. |
| E3 | Methods and Strengths: rule "reproduced the mother's order number in 2010" | Checked only in Brown/White 0-9 (0.2095 vs 0.2106). The assert threshold is 0.005 and tests the one easy cell. For **Black mothers, child Black 0-9: 0.476 (rule) vs 0.483 (order)**, 0.7 pp, above the threshold used. No pair-level check (that V0605 points at the couple's woman) is made. pairs.py docstring says the 2010 rule requires "V0605 pointing at her", but the code uses only V0604 = 1 (`couple_pairs(2010, ..., "c.mother_here = '1'")`). | Fix the docstring, or implement the check and report pair-level concordance. Show the full 3x3 matrix by rule. |
| E4 | Discussion para 3: selection "can explain the older ages but not the change between 0-4 and 10-14, when most children still live with the mother" | The wrong quantity. `with_mother` (93% at 0-4, 86% at 10-14) is not the selection operating on the pairs. Pairs also require child of the couple (relation 04/05/06): Black mothers' children **0.728 at 0-4, 0.797 at 10-14 (2010)**, i.e. a different 20-27% excluded at each age. Also V0604 (2010, mother) and P0300 (2022, "mother or stepmother") are non-equivalent, so the 94%/95% and 50%/51% co-residence comparisons across censuses are not like-for-like. | Argue with `child_of_couple` and with the order-rule curve. The conclusion survives: 2010 Black mothers' child Black by age, order rule 0.447/0.517/0.565/0.601/0.622 vs couple rule 0.437/0.509/0.560/0.597/0.618. Add this. Footnote the V0604/P0300 mismatch. |
| E5 | Results "Age and cohort" and Discussion para 3: "the gradient with age is the same children reported darker as they grow, not a cohort lighter at birth" | The "same children" point is just 2022's own 10-14 value (0.504) against 2010's 0-4 value (0.437): +0.067. The 2010 cross-section gradient 0-4 to 10-14 is **+0.123** (0.437 to 0.560); 2022's is +0.071. So about half the cross-sectional gradient is not individual aging, and the paper itself shows a period shift at ages 5+ (0.560 vs 0.504 at 10-14) while ages 0-4 are equal. A period shift at older ages only means the gradient is not a stable age rule. "Same children" is false even in principle: the 2010 0-4 children (born about 2005.6-2010.6) and 2022 10-14 children (born about 2007.6-2012.6) overlap in about 3 of 5 birth years; mothers are different survivors of co-residence; mothers' own classification drifted. | Reword to "consistent with part of the gradient being age-related; the two-census pseudo-cohort shows 0.067 of the 0.123 cross-sectional gradient". Remove "not a cohort lighter at birth": equal 0-4 shares in two censuses say nothing about the cohorts born 1995-2000 whose 10-14 value (0.56) is the 2010 comparator. |
| E6 | Abstract, Results, Discussion para 4, Conclusion: "hardly depended on whether the mother or another resident answered"; "household, not the individual informant, holds the classification" | Pooled OR 0.97 averages opposite effects. Brown mother, White partner, child 0-9 White: **mother answers 0.574, other resident 0.639** (+6.5 pp, n = 140,256 / 51,396). Black mother, Brown partner, Black: 0.203 vs 0.172; Black partner: 0.762 vs 0.791. Brown/Brown: 0.122 vs 0.117. "Other resident" is the partner in most mixed-couple households (95% of "other resident" children have a partner; 87.5% are relation 04). Non-residents differ markedly (OR 1.26, 1.34), so informant does matter. | Replace by an informant x partner interaction. See 3.1. Drop the household-holds-the-classification inference or label it unsupported. |
| E7 | Results, Figure 4, abstract: "five-year birth cohorts of 1940-2009 ... 26 of 27 intervals" | Cohort 2000 at Census 2000 holds **3.42M people** (births Jan-Aug 2000 only; a full five-year cohort has about 16-17M). One of the 27 intervals compares a one-year slice with a five-year cohort. Cohorts 1940-1995 x 2 + cohort 2000 x 2 + cohort 2005 x 1 = 27 recomputed. The single exception is 1940, 2010 to 2022 (0.5477 to 0.5490). | Drop partial cohort 2000 at census 2000, or label it; recount (26 of 26 becomes 25 of 26, or similar). |
| E8 | Reference [9] used for "census counts by single year of age and race" | The list contains Tables 202, 3149 (literate persons, preliminary universe), 3578 (household income) and 9605. None gives race by single year of age. 2000 is not covered at all. The Supplement says the series is a cohort-component account built from registers; Methods says census counts. These descriptions conflict. | State the actual source of the 2000, 2010, 2022 age x race counts and cite it; make Methods and S1 say the same thing. |
| E9 | Discussion para 2: cohorts' "move out of the White category, which the present series confirms [4,5]" | reading_report.md: Carvalho, Wood and Andrade 1950-1980 found a 38% **deficit in Black** and a 34% **gain in Brown**; that is movement out of Black, not out of White. The report records Marteleto only as "both structural change and shifts in classification contribute", with no direction. The Introduction's "toward Brown and Black [5,6]" is unverified for [5]. | Cite [4] only for "cohorts move between categories". Cite a source for the direction, or drop it. |
| E10 | Discussion: "the mother's race is itself the household's report, given by her in most cases" | Never computed. The mother's own informant is not in pairs.py. | Compute from raw 2022 (P1210/P1220 on the mother's record), or delete. |
| E11 | Abstract / Conclusion: "mixed unions with White men whitened children more in 2022 than in 2010" | The within-partner rate comparison ignores that "Brown mother" and "White partner" are themselves categories that drifted (3, 4.1). No composition-adjusted statement is made in the abstract beyond the logistic adjustment. The 0-4 vs 0-9 mixing: Black-child share for Black mothers 0-9 fell 0.476 to 0.459 (-1.7 pp), within-partner part -1.0 pp, whereas the abstract says "did not darken" (0-4 figure, CI -0.010 to +0.002). | Say 0-4 or 0-9 consistently; give the CI of the 0-9 change. |
| E12 | Results informant paragraph: "mother answered for 61% ... another resident 28%" | Shares computed over all pairs aged 0-24 and include "self" 8.2%. For 0-14 (the modelled ages): 65 / 29 / 3.8%. | State the base (age), or restrict to 0-14. |

## 2 Does the design answer the question?

**Pairing rule in 2022 without the order number.**
- Logic is sound for the two-parent structures. Relation 04, 05 with a woman head, and 06 with a woman spouse imply the couple's woman is the mother. P0300 "mother or stepmother" then only confirms co-residence.
- Positions verified: 2010 V0502 54-55, V0504 56-57 (the logical order the mother's pointer refers to), V0601 58, V6036 62-64, V0606 68, V6400 158, V0604 399, V0605 400-401. 2022 P0170 40-41, P0180 42-43, P0210 45, P0300 54, P0770 116, P1210 184, P1220 185-188. Informant matching is not broken: mother 61% recovered.
- The rule is **not validated in 2022 at all**, and in 2010 only at the aggregate. Report pair-level concordance in 2010 (the order pair's mother = the couple's woman, by relation).
- It excludes 18% of co-resident children aged 0-9: those in households headed by the mother's parents, by a lone mother who is not head, or with a convivente couple. Likely selected on race and income.
- Coverage differs between censuses: child of couple among 0-4 Brown 0.75 (2010) vs 0.80 (2022). Relation mix among Brown 0-9: 04 / 05 / 06 = 80.5 / 15.4 / 4.0% (2010) vs **74.8 / 22.6 / 2.6% (2022)**. The 2022 couple pairs have far more "child of the responsible only" (stepfather) structures. This composition shift is never mentioned and bears directly on the "partner" comparison across censuses.

**Partner is not the father.**
- Only relation 04 makes him the father. Among 05/06 he is a stepfather or a non-parent.
- Brown mother, child 0-9 White, White partner (rate): relation 04 **0.559 / 0.614** (2010 / 2022), 05 0.355 / 0.390, 06 **0.295 / 0.315**. With a Brown partner: 04 0.109 / 0.116, 06 0.160 / 0.155. The father-minus-Brown gap is about 0.45-0.50; for the stepfather about 0.14-0.16.
- Hence the partner effect is mostly a father (ancestry, appearance, father's own race) effect. The "household classifies by the partner" reading is only the stepfather residual (about one third).
- The 2022 rise persists inside relation 04 (0.559 to 0.614), so the rise is not a stepfather artefact.
- "No partner" mothers' children are White at 0.205 / 0.216, equal to the partner-mix average (about 0.21). This is what ancestry mixing predicts (absent fathers distributed like partners), and is the unexplained OR 2.05 in Table S1.

**Co-residence selection.** See E4. Age curves are robust to the couple rule in 2010 (order rule shown above), but the claim for 2022 cannot be checked (no order number).

**The 2022 public file's five-year ages.** The 0-4 to 10-14 pseudo-cohort overlaps only about 3 of 5 birth years (E5). The 2010 single-year age is unused: place paper (paper 3) reports under-1 Black mothers' children Black 0.39 (order rule 0.389, couple rule 0.379); the 0-4 pooled 0.437 hides a steep gradient inside 0-4 that the 2022 file cannot reproduce.

**Cohort comparison.** Pseudo-cohort is not longitudinal (different mothers, partners, survivors, informants). See E5.

**Category drift of "Black mother".** Population shares (weighted persons): White 47.5 to 43.3, Black 7.5 to 10.3, Brown 43.4 to 45.4, Yellow 1.10 to 0.42, Indigenous 0.43 to 0.62%. Among pairs aged 0-4, mothers: White 42.2 to 37.2%, Black 8.1 to 10.9% (+35% relative), while the weighted number of children is flat (10.2M vs 10.1M). Black mothers' schooling: no/incomplete primary 51 to 22%, higher 3.8 to 12.1%. Marginal self-identifiers entering "Black" and leaving "White" make the 2022 groups different populations. The paper's one-line "as expected if ..." for 5+ ages is the same drift and is untested.

**Informant analysis confounding.** Who answers is a household-structure variable: "other resident" is 87.5% relation 04 with 5% no partner, vs "mother" 67% / 31% / 2% and 23.5% no partner. Adjustment is for partner's race only, not for partner presence x informant identity. The informant is almost certainly the same person who reported the mother's own race (single household respondent), so mother-child concordance is partly a respondent-style effect (same informant gives both). The informant analysis cannot say whose rule it is until the informant is identified as partner vs mother vs other, and the mother's own informant is in the model.

## 3 Analyses the data allow but the paper lacks (ranked)

1. **Informant identity x partner x mother's own informant** (needs a pairs.py re-run adding P1220 order of the child's and the mother's informant, and the partner's order). Within mixed couples: child's race by who answered (mother / partner / other), and whether the same person answered for the mother. Already visible in the current file: Brown-mother, White-partner White 0.574 (mother) vs 0.639 (other resident).
2. **Father vs stepfather**, models and figures by relation (04 vs 05 vs 06), both censuses. Add to Figure 2. This turns the partner section from association into an informative contrast.
3. **Sibling discordance and household fixed effects.** 22-23% of Brown-mother households with at least 2 children 0-9 are discordant (2010 22.9%, 2022 22.2%); with a White partner 41.8% / 41.0%, Brown partner 14.4% / 13.9%, none 22.5% / 22.7%. Conditional logit with household effects gives age, sex and birth-order effects free of household rules; compare with binomial expectation 2p(1-p).
4. **Father's race-specific models and both parents' schooling** (the partner's instruction is already in persons). Interaction mother x partner race beyond Brown/Black references; White-mother/Black-partner, White-mother/Brown-partner (the file has 1.0M White mothers) children. Currently the paper models only Brown and Black mothers.
5. **Total vs direct effect of schooling.** Instruction effect without partner (raw 0.18 to 0.29, OR about 1.9) vs with (1.38): the mediation through partner is Schwartzman's point; currently the paper compares a conditional effect with a conditional effect.
6. **Urban/rural, household income per capita, region x state-level change.** Place paper uses municipality (2010); family paper offers region only. The state is in both files: state-level change 2010-2022 for the key quantities, with state composition.
7. **Imputation flags.** M0606 (2010) / MP0210 (2022) mark imputed race; donors are often household members, which inflates mother-child concordance. Re-estimate excluding imputed child and mother race.
8. **Grandmother and extended households.** The 18% excluded can be analysed with 2022 relation 10 (grandchild) against the head's race; at least show how their classification differs (selection bound).
9. **Yellow and Indigenous mothers.** Pairs hold 30,354 Yellow-mother children 0-9 in 2010 but 5,758 in 2022, and 24,430 vs 64,073 Indigenous: the clearest drift evidence and unreported. Show them (counts, matrix) rather than "too few".
10. **Single-year age in 2010** (0, 1, 2 ...), and the 2000-Census cohort series as a second pseudo-cohort for children (cohort 1995: White share 0.534 at 0-4 in 2000, 0.422 at 10-14 in 2010: -11 pp, a larger drop than the family pairs show).

## 4 Rival explanations untested, with the separating test

| Rival | Separating test (data held) |
|---|---|
| Ancestry / phenotype of a mixed-parent child, not a household rule | Relation 04 vs 06 (father vs stepfather) gap: 0.45-0.50 vs 0.14-0.16 pp. Sibling discordance 41% in Brown/White households. Proposed: report both; add a mother x partner x relation model. |
| Partner's classification (he answers) vs mother's | Informant identity x partner (3.1). Current partial evidence: +6.5 pp when "other resident" answers in Brown/White households. |
| Category drift of mother and partner (Black +35%, White partner -17% in Brown mother households, Yellow -80%) | Standardise 2022 to 2010 on mother's age, schooling, region, partner, relation; show within-stratum change; Yellow/Indigenous counts; a placebo census change in a group with no mother-child dependence. |
| Selection into the pairs (couple households, 18% out, differing by census) | Order-rule pairs in 2010 (done above: same gradient); bounding by Manski-type extremes for the excluded 18% in 2022; compare relation mix. |
| Same-respondent concordance (one respondent for mother and child) | Mother's own informant; concordance by same vs different informant. |
| Imputation donors | Exclude imputed race (M0606, MP0210). |
| Stepfather structure shifts (relation 05 up from 15% to 23% of Brown 0-9) | Present the rise within relation 04 only (0.559 to 0.614: persists). |
| Age effect vs cohort effect | 2022 cross-section gradient (+0.071) vs 2010 (+0.123) vs pseudo-cohort (+0.067): cannot separate; admit; add 2000 cohort series; use the age-period-cohort identification warning. |

## 5 Statistical issues

- **Variance.** Stratifying by state makes almost no difference (SE 0.000503 vs 0.000499 with weighting areas): with households as PSU, the stratum mean of the linearised score is near zero, so the strata are inert and the SE is essentially a household-clustered SE. Independent recomputation: household-only SE 0.000509 for Brown-mother 0-9 White 2010 (n = 786,610 households), Kish design effect 1.41. The estimate is conservative: it ignores finite-population correction (sampling fractions 5-50% in 2010), and calibrated weights. Stated as "design-based, adequate", it should be "conservative; weighting areas and tracts, unavailable for 2022". The 2010 sensitivity is therefore uninformative about the 2022 design.
- **Precision shown.** "0.24 (95%CI 0.24; 0.24)" appears throughout Table 1; use three decimals or percentage points. Sampling error is trivial relative to non-sampling (drift, imputation, informant); the paper treats interval widths as evidence and the "significant change" language (+0.003, CI +0.002; +0.005) is sampling-only and practically negligible.
- **Models.** Weighted logistic with `var_weights` (mean-scaled) and household-cluster SE: point estimates are pseudo-likelihood and reproduce (my refit: partner White 9.363 [9.265; 9.461], census 1.028 [1.018; 1.038], higher instruction 1.382, South vs Centre-West 2.000 / 1.400 = 1.43). Not stratified, no FPC. Fit a survey GLM (survey::svyglm with strata, ids = household) as a check. Non-collapsibility: compare ORs only within a model.
- **Model specification.** Pooled 0-9 with 2 age levels; no partner x age, partner x relation, partner x region, partner x instruction terms although the figures show heterogeneity. "Not determined" instruction dropped in 2010 only.
- **Two-census comparison.** The census x partner interaction is the only formal test of the key claim; it covers partner but not instruction, region or relation (the relation mix changed). Report the interaction as the paper's headline estimate with its decomposition, not a main-effect OR 1.03.
- **Multiplicity.** About 100 intervals in Tables S1-S2 and text; no tests are claimed, which is acceptable if claims are descriptive. But "at every age", "26 of 27" and "more than any other characteristic" are comparative statements with no formal contrast.
- **Cohort series.** Differences of 0.001 (exception 1940) are called a rise; no SE exists for the census counts (they are universe-level for 2010 and 2022 only, sample for 2000). The partial 2000 cohort breaks the unit (E7).

## 6 Claims stronger than evidence

| Quote | Why | Reword |
|---|---|---|
| "The partner decided most" (Abstract); "changed the child's classification more than any other characteristic" | Associative contrast of categories on different scales; father vs stepfather unseparated; "decided" implies agency. | "Differed most by the partner's race (OR 9.4 vs Brown partner), mainly when the partner is the child's father." |
| "A Brazilian household classifies a child as much by the partner as by the mother" (Conclusion) | Only a statement about co-variation; consistent with ancestry; 41% sibling discordance. | "Children's reported race follows the partner's race closely." |
| "the same children reported darker as they grow" | E5. | "Part of the age gradient is age; the data cannot isolate it from cohort." |
| "household, not the individual informant, holds the classification" | E6: within-partner informant effects of +6.5 pp; informant is endogenous. | Delete or hedge. |
| "Non-resident informants ... as a proxy who knows only the mother would" | Speculation; the non-resident also answers the mother's own race. | "Possibly because ..." and test with mother's informant. |
| "runs against the darkening of identification reported in surveys of the same period [6]" | Child-by-household classification of 0-9 vs adult self-identification in LAPOP; different objects; also the paper's own data show lighter classification only in mixed unions. | Remove "runs against". |
| "Health statistics ... inherit a classification that follows the father as much as the mother" | Father not identified (E2/partner). | "follows the couple's racial composition". |
| "We know of no study that compared how households classify children relative to the mother in two censuses" | Priority claim not searched for. | Search (Brazilian census literature on children of interracial couples, 2000 / 2010, IBGE analytic reports) and hedge. |
| "complete samples of two censuses" (Strengths) | The 2022 public file is a public-access version; weights are the public version; 2022 undercount and imputation not discussed. | "public-access samples". |
| "one pairing rule valid in both" | Validated in 2010 only, at the aggregate (E3). | "applicable in both". |

## 7 Numbers recomputed (printed vs recomputed)

All from pairs_2010/2022.parquet (rule = couple unless stated).

| # | Quantity | Printed | Recomputed | Status |
|---|---|---|---|---|
| 1 | White mothers, child White, 0-4, 2010 / 2022 | 0.87 / 0.86 | 0.870 / 0.863 | OK |
| 2 | Brown mothers, child White 0-4, 2010 / 2022 | 0.24 / 0.24 | 0.235 / 0.239 | OK |
| 3 | Brown mothers, child Brown 0-4 | 0.75 / 0.74 | 0.748 / 0.743 | OK |
| 4 | Black mothers, child Black 0-4 | 0.44 / 0.43 | 0.437 / 0.433 | OK |
| 5 | Black mothers, child Brown 0-4 | 0.40 / 0.39 | 0.402 / 0.388 | OK |
| 6 | Black mothers, child White 0-4 | 0.15 / 0.18 | 0.151 / 0.178 | OK |
| 7 | Table 1 record counts (6 cells) | 472,649 / 393,556 / 555,884 / 572,030 / 87,679 / 115,649 | identical | OK |
| 8 | Brown mothers 0-9 children, 2010 / 2022 | 1,201,189 / 1,181,851 | identical | OK |
| 9 | White / Black mothers 0-9, 2010 | 1,005,527 / 191,631 | identical | OK |
| 10 | Abstract total 2010, 0-9 | 2,398,347 | 2,398,347 | OK |
| 11 | Rule kept share of order pairs | 88% | 87.6% (0-24); **81.9% Brown 0-9** | Mislabelled (E2) |
| 12 | Rule vs order, Brown 0-9 White | 0.21 / 0.21 | 0.2095 / 0.2106 | OK |
| 13 | Black mothers 0-9, child Black, rule vs order | not printed | 0.476 vs 0.483 | Gap above own tolerance (E3) |
| 14 | Co-residence Brown children 0-4 / 20-24 | 94 / 95; 50 / 51% | 0.941 / 0.946; 0.500 / 0.508 | OK (definitions differ, E4) |
| 15 | Brown mother, White partner, child White 0-9 | 0.54 / 0.59 | 0.539 / 0.592 | OK |
| 16 | Brown partner / no partner 2022 | 0.12 / 0.22 | 0.119 / 0.216 | OK |
| 17 | Black mother, partner Black / Brown / White, child Black 2022 | 0.77 / 0.20 / 0.16 | 0.774 / 0.195 / 0.163 | OK |
| 18 | Partner shares: Brown mothers White partner | 20% / 17% | 20.2% / 16.8% | OK |
| 19 | No partner shares | 12% / 18% | 12.1% / 17.6% | OK |
| 20 | Black mothers with Black partner | 39% / 35% | 39.1% / 35.0% | OK |
| 21 | Brown/White standardised at 2010 partners | 0.23 (obs 0.22; 2010 0.21) | 0.226 (0.215; 0.210) | OK |
| 22 | Black/Black standardised | 0.47 (0.46; 0.48) | 0.466 (0.459; 0.476) | OK |
| 23 | Black/White standardised | 0.16 (0.16; 0.13) | 0.158 (0.158; 0.132) | OK |
| 24 | Black mothers Black by age 0-4 / 20-24, 2010 | 0.44 / 0.62 | 0.437 / 0.618 | OK |
| 25 | Same, 2022 | 0.43 / 0.58 | 0.433 / 0.577 | OK |
| 26 | Black mothers 10-14 Black, 2010 vs 2022 | 0.56 / 0.50 | 0.560 / 0.504 | OK |
| 27 | Brown mothers White 0-4 / 10-14, 2022 | 0.24 / 0.17 | 0.239 / 0.174 | OK |
| 28 | Informant shares 2022 | 61 / 28 / 3% | 60.8 / 27.5 / 3.4% (all ages 0-24) | OK but base (E12) |
| 29 | Logistic Brown/White: partner White OR | 9.36 (9.27; 9.46) | 9.363 (9.265; 9.461) | OK (refit) |
| 30 | Census OR | 1.03 (1.02; 1.04) | 1.028 (1.018; 1.038) | OK |
| 31 | Higher education OR | 1.38 (1.36; 1.41) | 1.382 (1.358; 1.406) | OK |
| 32 | South vs Centre-West | 1.43 | 2.000 / 1.400 = 1.43 | OK |
| 33 | Interaction census x White partner | 0.15 (SE 0.01) | 0.146 (0.0106) from json | OK; but see E1 |
| 34 | Cohort falls | 26 of 27 | 26 of 27 | OK numerically; E7 on unit |
| 35 | Household-only SE, Brown 0-9 White 2010 | 0.000503 (states) | 0.000509 | OK |
| 36 | Persons 2022 weighted | not printed | 203.08M (census 203.06M) | OK |
| 37 | Informant mother-vs-other, Brown mother, White partner | "hardly differs" | 0.574 vs 0.639 | Contradicted (E6) |

## 8 References

- [1] Schwartzman 2007: used for what the source says (educated non-White parents, partner effect). OK.
- [2] Telles 2002: consistency 79%; OK for observer-method inconsistency.
- [3] Muniz and Bastos 2017: OK.
- [4] Carvalho, Wood and Andrade 2004: OK for "cohorts move between categories" (Introduction); **not** for "move out of White" (Discussion), E9. Note it concerns 1950-1990, not "recent decades".
- [5] Marteleto 2012: reading notes give no direction of reclassification. Check against the paper itself before using for "toward Brown and Black".
- [6] Freeman, Telles and Goldberg 2025: LAPOP identification 2010-2023 darkening; adults, survey; used for "runs against", mismatch of object.
- [7], [8] IBGE microdata: OK. State that 2022 is the public-access version.
- [9] IBGE tables: does not support the cohort series as described (E8).
- Missing: literature on children of interracial couples and parental classification in Brazil beyond Schwartzman (to support or retire the novelty claim); Telles and Paschel 2014 / Bailey and Telles 2006 (in the reading report, unused here); the Census 2000.
- Standard demography of father-child ancestry (genetic ancestry vs classification) for rival 1.

## Consistency with place paper (paper 3)

Place paper uses the 2010 family classification with the order-rule pairs (all co-resident children): under 1, White mothers' White 0.88, Brown mothers' Brown 0.71, Black mothers' Black 0.39, Brown mothers' White 0.28, Black mothers' Brown 0.41. My single-year checks: order rule 0.389 (Black, age 0) and 0.287 (Brown-White, age 0), couple rule 0.379 / 0.289. Consistent. But paper 4 uses the couple rule on different ages (0-4 pooled), and shows the 2010 reference drifts (Black mothers' White 0.15 to 0.18; ages 5+ lighter in 2022). Paper 3 compares 2013-2024 certificates with the 2010 reference only; it should cite paper 4's drift or use 2022 as a second reference.
