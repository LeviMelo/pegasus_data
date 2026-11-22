# Review 3 - paper 3, `black_category/` (final verification)

Read: manuscript.txt, supplement.txt, ledger, display plan, review_2 and response_2, black.json, mechanism.json, physician.json, spatial.json (multilevel terms), mechanism.py, mechanism2.py, physician.R, text*.py asserts, the six figures (opened). Nothing run on the large data, nothing edited.

## 1. Verdict: MAJOR REVISION (narrow)

The paper is much better than at review 2. The title and unit are honest, the net count is stated as a count ratio, the copy reading is tested (association persists where the delivery chart was not at hand), the practice is leave-one-out and clustered by hospital, movers, physician, filler and decomposed-time analyses exist, and every printed number I recomputed matches the result files. What remains is not arithmetic but inference: three headline sentences are stronger than the analyses under them (practice "added little"; "the hospital sets the level"/"the person as staff see her"; "the data show it belongs to the person, not the chart"), the movers evidence has an understated standard error and an unexamined rival (registry memory), two copy channels are untested, and several figure defects remain. All fixes are feasible with data held.

## 2. Review-2 items: fixed or not

| Item | Status | Evidence in the manuscript |
|---|---|---|
| Title/unit "Black children" | Fixed | "Infants of Black mothers recorded as Brown"; "the unit of this study is the infant of a Black mother ... measures how the certificate uses the category ... not how many infants were Black". |
| Undercount wording | Fixed | "certificates recorded 0.34 (0.32; 0.36) as many infants as Black as there were infants of Black mothers". |
| Commissions sentence, "which a hospital-wide practice cannot produce" | Fixed (deleted/reworded) | Gone. |
| 1. Reference is staff-entered | Partly | "entered on the birth record by staff on her answer"; filler analysis (-0.7, -1.0 points); stability 0.52. But the inference drawn is a non sequitur (section 4, claim 5) and Table S2's "Who classifies" column still states unmeasured assumptions ("household", "hospital staff", "certifier or informant"). |
| 2.1 Movers | Mostly | New: 0.92 vs 0.58; slope 1.01 (SE 0.03; 1.16). Not done: mother plus hospital variance decomposition, event study; SE is HC1 (mechanism2.py line 159), not clustered by hospital; sample is small municipalities with 34.5% chance pairs. |
| 2.2 Physician | Partly | "0.29 between physicians, 0.42 between establishments, 0.21 municipalities". Not done: physician fixed-effect contrast; whether the mother's hospital record survives physician plus establishment terms. Only 9,337 deaths over 5,883 physicians (1.6 per physician; 212 with 5 or more): the physician/establishment split is weakly identified and no interval is given. |
| 2.3 Copying | Partly | A done ("1.98 ... 1.75 (1.25; 2.44) among the 2,173 who died elsewhere"). B (infant's own SIH race), C (home deaths, only Fig 4 terms), D (investigation source; computed in mechanism.json, not reported) not done. |
| 2.4 Filler, newborn colour | Filler done; newborn colour dropped silently | The 212-record reason appears in response_2 only; the manuscript should say it. |
| 2.5 Facility model | Mostly | "shrunk by a beta prior ... errors clustered by hospital ... 1.33, 1.20, 1.10". Not done: ownership/teaching moderators, hospital random effect, same-municipality contrast. Interpretation unresolved (section 4, claim 2). |
| 2.6 Composition of the rise | Partly | Standardised to region, schooling, age only: "from 0.15 to 0.23". Table 1 calls "the rise is who declares" **excluded**: too strong (section 4). |
| 2.7 Other admissions of the same woman | Not done | Not mentioned. |
| 2.8 Blanks | Bounded | "0.28 to 0.50". Blank-by-hospital not modelled. |
| 2.9 Heterogeneity | Not done | Only Fig 4 terms, uninterpreted (GDP, illiteracy, "not recorded" schooling OR 1.73 in the json). |
| 4.1, 4.2 clustering, LOO, shrinkage | Fixed | |
| 4.3 MH heterogeneity | Fixed | "Breslow-Day p = 0.003, so the association varied between hospitals"; adjusted clogit 2.01. No random-effects summary or tau. |
| 4.4 Non-monotone White cell (0.17) | **Not fixed** | Reported, still uninterpreted. The data explain it (section 3). |
| 4.5 Net intervals | Fixed | |
| 4.6 Multiplicity | Partly | Two primaries named; abstract still carries 14 estimates. |
| 4.7 Ages 1-9 | Partly | Reduced to one contrast, but its interval still ignores the denominator variance (supplement S2 says so), and the Results sentence compares it to a binomial interval for infants. |
| 4.8, 4.10 adult women, map | Fixed (moved/cut) | |
| 4.9 nAGQ | Partly | Fig 4's model is still nAGQ = 0 (disclosed); S5's order-dependent "variance explained" table remains (one row -1.4%). |
| 4.11 Joint time model | Fixed | "difference of -0.37 (95%CI -0.55; -0.18)". See the 2023 caveat. |
| 4.12 2023 hospital series | Explained, not shown | The 21.5% to 2.8% blank figures are not printed or tabulated in the paper; the text count (96,646 to 127,570) differs from Table S4 (92,004 to 119,012), see section 3. |
| 4.13 Unit mix in the ladder | Partly | Hatched net bars separate counts from proportions, but census 2010, hospital 2012-2023 public deliveries, certificates 2013-2023 and a municipality-restricted 1-4 estimator still sit on one axis. |
| 5.x claim rewording | Mostly | Exceptions: Discussion "the data show that it belongs to the person as staff see her ... and not to the chart"; Implications "the birth record ... closer to the mother's answer" (unsupported: 0.52 stability). |
| 6 flow with counts | Partly | Fig 1 has three boxes and no step counts (309,203; 291,812; 22,305; 10,568; 2,173; 490 hospitals excluded). |
| 7 sibling reconciliation | Partly | Spatial text cut to a sentence; the establishment-over-municipality finding that changes paper 1's reading is not stated. |

## 3. Numbers recomputed (printed vs recomputed)

| # | Printed | Recomputed from files | |
|---|---|---|---|
| 1 | certified Black 0.18 (0.17; 0.20) | 0.1837, SE 0.0074: 0.169; 0.198 | ok |
| 2 | net certificate 0.34 (0.32; 0.36) | 7,560/22,305 = 0.3389; SE 0.0087 | ok |
| 3 | net hospital 0.74 (0.68; 0.81) | 697,191/939,740 = 0.7419; SE 0.034: 0.676; 0.808 | ok |
| 4 | blanks bound 0.28-0.50 | 0.3626 x 0.7821 = 0.2836; + 0.2179 = 0.5015 | ok |
| 5 | MH 2.05, 346 hospitals; adjusted 2.01 (1.77; 2.28) | 2.054 (346); exp(coef) 2.012 (1.774; 2.282) | ok |
| 6 | elsewhere 1.75 (1.25; 2.44), "2,173 who died elsewhere" | clogit 1.749 (1.253; 2.441) with n 2,173, but the informative MH sample is **838 deaths in 114 establishments** (1.77; 1.28-2.43) | number ok; denominator misleading |
| 7 | practice 1.33 / 1.20 / 1.10 (1.02; 1.18), person 1.89 | exp(.2859), exp(.1832), exp(.0950) = 1.331, 1.201, 1.100; CI 1.022; 1.183; hb 1.891 | ok |
| 8 | joint difference -0.37 (-0.55; -0.18); hospital 0.08 | -0.3658 (-0.548; -0.183); 0.4495 - 0.3658 = 0.084 | ok |
| 9 | standardised 0.15 to 0.23; crude 0.21 | 0.1545 to 0.2331; crude 0.2124 | ok, but see the 2023 jump below |
| 10 | 5.6% to 7.9% | 0.0558, 0.0788 | ok |
| 11 | movers 0.92 / 0.58 / 1.01 / 1.16 / 13% | 0.9177, 0.5836, 1.0133, 1.0133/(1-0.1257) = 1.159, 12.6% | ok |
| 12 | 34.5% chance pairs; 0.52 / 0.87 / 0.75 | 788,387/2,284,318 = 0.345; 0.5248, 0.8714, 0.7547 | ok |
| 13 | filler 10.1/6.6/6.8%; -0.7 (0.4), -1.0 (0.2) | 0.1010, 0.0657, 0.0681; -0.0070 (0.0045), -0.0096 (0.0016) | ok |
| 14 | SVO 0.59 (0.47; 0.75), IML 0.65 (0.53; 0.81), <20 0.82, 1.25, 1.14 | exp(-0.526 +- 1.96 x 0.120) = 0.591 (0.467; 0.748); 0.652 (0.526; 0.809); 0.82 (0.74; 0.92); 1.251 (1.03; 1.51); 1.144 (1.02; 1.28) | ok |
| 15 | variances 0.29 / 0.42 / 0.21; 9,337, 5,883 | 0.285, 0.421, 0.209; same | ok |
| 16 | 1-4 years 0.24 (0.20; 0.27); infants same municipalities 0.18 (0.17; 0.18) | 0.2351, SE 0.0201; 0.1763, SE 0.0029 | ok (but SE ignores denominator variance) |
| 17 | 0.19 vs 0.18 selection check | 0.1854 vs 0.1822 | ok |
| 18 | 0.06 vs 0.02; 1.6% of Brown mothers' infants | 0.0627, 0.0152; 0.0165 | ok |
| 19 | hospitals with a race rose 96,646 (2022) to 127,570 (2023) | black.json births by year: 92,004 and 119,012 (Table S4). mechanism.py counts all hospitals, including the 490 left out elsewhere | **inconsistent counts for one quantity** |
| 20 | same-sample comparison (not printed) | 3,872/10,568 = 0.366 recorded Black by the hospital vs 0.185 certified: the cleanest like-for-like version of "fewer than the hospitals record their mothers" | add it |

No arithmetic error found. Ledger row "OR 2.01 died there, 1.75 (1.28; 2.43)" mixes the MH and clogit versions (1.98 and 1.75 (1.25; 2.44) in the paper); align it.

## 4. Claims against evidence

1. **"Beside the mother's own record, the hospital's practice added little (1.10 per logit unit)."** Two defects. (a) Scale: the 1.10 is per logit of shrunk practice, the 1.89 is a binary contrast. The beta prior (0.71, 1.73) gives a logit SD of about 1.9, so 1 SD of practice is OR 1.41 at equal composition, 1.71 alone, and 1.20 beside the mother's record; across the p10-p90 range (about 4 logit units, 0.01 to 0.64) it is roughly 2.1. Fig 3B plots both on one axis, inviting the misreading; text_results.py even asserts "practice < 1.2 and person > 1.5" on this basis. (b) Mediation: the paper's own movers result says practice determines the hospital's record of the mother (slope 1.01). Conditioning on that record then estimates only the direct effect of practice. The total effect (1.33 alone; 1.20 adjusted) is the relevant quantity for "a hospital-wide practice decides". Table 1's prediction ("practice predicts the certificate as well as the mother's record") is therefore not a valid test. Report effects per SD or per interquartile range, the total effect and a mediation share.
2. **"The hospital sets the level; a mother who changes hospital takes on its rate in full."** The slope is estimated with HC1 errors although mothers share destination hospitals: cluster by hospital pair (the SE 0.03 and the assert "est - 2 se > 0.8" rest on it). The estimand is also read too broadly: in another hospital a Black-recorded mother is recorded Black again 0.58 against 0.355 if not recorded Black first (OR 2.5), so a person component remains across hospitals. In the same hospital the same contrast is 0.92 vs 0.13 (OR about 76). Persistence that strong inside one hospital is what registry memory would produce (the clerk copies the race from her previous file); it is not evidence of perception. The paper uses 0.92 as supporting evidence without this reading. Also mover selection (small municipalities, 34.5% chance pairs, corrected by an assumed zero slope among chance pairs) limits generalisation.
3. **Copy reading "weakened" by the elsewhere stratum.** "Where the chart was not at hand" is not established. A transferred neonate arrives with a referral summary, and SUS establishments draw on shared upstream registers (CadSUS/prenatal card) that would give the delivery hospital, the receiving hospital and the certifier the same race entry. The association then survives "elsewhere" without perception. Untested but testable: the association among mothers with no prenatal visits (no card), and the infant's own admission race.
4. **Non-monotone gradient is regional, not mysterious.** Among Black-declared mothers, 42% of those the hospital recorded White live in the South (against 3% of those recorded Brown and 21% of those recorded Black), where certificates use Black most (South OR 2.08). Within the Southeast the White- and Brown-recorded cells are equal (0.148, 0.149). So Fig 3A and Table S3 are region-confounded, and the within-region contrast is Black-recorded against everything else. State this; draw Fig 3A within region or standardised.
5. **"The data show that it belongs to the person as staff see her, at a level the institution sets, and not to the chart."** The shared element could equally be the mother's own varying self-classification (the 0.52 stability) carried to a hospital registration and to the informant at death, or her phenotype, or the father. "The element unnamed" appears in Table 1 but the Discussion sentence asserts the staff-perception reading. Replace "show" by "are compatible with". Likewise the filler argument ("argues that the declaration is the mother's rather than the filler's") does not follow: role invariance within a hospital does not separate the mother's answer from the hospital's shared way of asking. The -1.0 point difference is 15% relative to a 6.6% share and is statistically clear (SE 0.2); the assert that both are under 0.02 is arbitrary.
6. **"Faster on the certificate than in the hospital."** Supported as a contrast (-0.37, CI excludes 0) but the hospital record changes definition in 2023 (race blank 21.5% in 2022, 2.8% in 2023, filled mostly with other categories). The standardised certificate also jumps 0.191 (2022) to 0.233 (2023) after a flat 2018-2022; the headline "0.15 to 0.23" leans on one year (SE about 0.01). Give the trend without 2023, and the 2013-2022 contrast.
7. **"The rise is who declares: excluded."** Only region, schooling and age were standardised. More mothers declaring Black (5.6% to 7.9%) changes unobserved composition (shade, referral), and the linked share of deaths moved from 77% to 82% over the years (review 2). Say "not explained by region, schooling and age".
8. **"Statistics of the Black population ... undercount it."** The declaration is called unstable (0.52 repeated) and not truth, and 49% of hospital "Black" records belong to mothers who did not declare Black (net 0.74 is mostly offsetting false positives from the 8.2 million Brown mothers at 3.8%). "Differ between hospitals" is supported by movers; "undercount" is conditional on the reference. Add one clause.
9. **Physician share.** Variance 0.29 on 1.6 deaths per physician is weakly identified; present ICC (0.29 and 0.42 on a latent scale with residual 3.29 are about 7% and 10%) and the Brown-mother cell (physician variance 0.79 there) for contrast, or temper "present".
10. **Table 1 Status column** mixes results with verdicts ("sets the level", "excluded", "weakened") not computed by any test; define each status by a rule or drop the column.

## 5. Rival explanations untested and missing analyses, ranked (feasible with held data)

1. **Infant's own hospital record vs certificate (in-hospital deaths; SIH.RD race of the neonate, 2013-2023).** Direct copy test and the only observation of the infant, the stated unit. Feasible (SIH-SIM link exists; needs the neonatal run). Highest value.
2. **Shared-upstream/informant channels:** association by prenatal visits (none vs adequate, SINASC), by place of death (home, no chart), by investigation source and `TPPOS` (already computed in mechanism.json: Black share among Black-declared is flat, 0.14-0.22, across sources; unreported). Feasible now.
3. **Mother and hospital variance decomposition (AKM or mover event study) and the within- vs across-hospital persistence on the odds scale,** with hospital-clustered errors; add second-birth declaration instability by hospital. Feasible with the paired file.
4. **Total, per-SD and mediated practice effect**, with ownership/teaching (CNES) and the municipality's other hospitals as contrasts. Feasible (CNES held).
5. **Time artefacts:** series excluding 2023, restricted to hospitals that filled race in all years; inverse-probability weights and bounds for the 19.5% unlinked; the rise among repeat mothers (mother's earlier births). Feasible.
6. **Same woman's other SIH admissions** (race stability within person across hospitals) as an independent test that hospital race tracks the person at all. Feasible, noisy.
7. **Cause, age at death, weight, region strata for the 2.0 OR** (heterogeneity already shown by Breslow-Day p = 0.003); report tau or random-effects OR. Quick.
Not feasible: father's race, mother's phenotype, newborn colour (212 records), staff identity at the bedside.

## 6. Figures (against figures.md sections 2, 5, 6, 7 and the display plan)

- **Fig 1 (`flow_black`)**: three boxes, no counts per step. Add 309,203 -> 291,812 -> 22,305 -> 10,568 -> 2,173 elsewhere, 490 hospitals out, the movers sample. Legible at 175 mm (about 8 pt).
- **Fig 2 (`black_ladder`)**: the x-axis label is cut at the right edge ("(hatch"). The image is 215 mm wide, so reduction to 175 mm leaves about 6 pt text, under the 7-9 pt rule. Census bars have no interval; two rows read 0.18; the axis mixes proportions and ratios of counts. The abstract's 0.55 Brown is not shown. Legend sits in empty space (ok).
- **Fig 3**: panel A tick labels collide ("(n=3,872)(n=5,616)"); A is crude and region-confounded (section 4, claim 4), and the White bar sits above Brown with no note. Panel B puts a binary OR and a per-logit OR on one axis (the scale problem). Panel C draws the two lines but not the abstract's number (slope 1.01/1.16) or the OR contrast; the abstract's "takes on its rate" and 0.55/-0.37 are in no main item, contradicting the display plan's "every abstract number is in a main item". Intervals present, no overlaps with data.
- **Fig 4**: 22 terms with n and events absent; terms are unordered by theme (certifier, place, age, cause, mother, context, region); it carries the municipality-only nAGQ = 0 model rather than the physician/establishment result in the text. Four weak terms (GDP, illiteracy, capital) are never discussed. Legible.
- **Fig 5A**: regional lines are conditional fits (random effect zero), not data, the pattern flagged "region lines drawn as if trends" in section 7. Use raw regional proportions with intervals. **5B**: legend is wedged between series; the 2023 definition change is not marked; the standardised dashed line is hard to see and its 2023 spike unflagged.
- **Fig S1** is fine; it carries n (328 hospitals, area by deaths) and the diagonal.

## 7. Minor

- Methods say 1,595 hospitals with 30+ Black mothers while the delivery model uses 977; state once which set is which.
- Results sentence "2,173 who died elsewhere" overstates information (838 informative).
- "The use of the category clustered in space ... as a companion paper describes": unsupported number-free sentence; cite or cut.
- Brown-recorded deaths dominate: 5,616 vs 3,872 Black-recorded vs 950 White-recorded; give the three n in the text.
- Ledger row on the filler says "see the json"; update the ledger (open rows now settled).
- Reference [9] (Travassos and Williams) is a review of race concepts, a thin support for "in practice the certifier often enters it".
- The abstract still reports 14 estimates; keep the primary two plus movers and physician.

## Top five required changes

1. Rewrite the practice comparison: report total, per-SD and mediated effects; drop "added little" and the common-axis OR plot and Table 1 prediction.
2. Movers: hospital-clustered errors, odds-scale within- vs across-hospital persistence with the registry-memory reading, and a mother plus hospital variance decomposition or event study.
3. Add the untested copy channels: infant's own SIH race, prenatal-visit strata, home deaths, investigation source; soften "the data show ... belongs to the person" to "compatible with".
4. Explain the White-recorded cell by region (42% South) and redraw Fig 3A within region; run the time series without 2023 and with linkage weights; replace "excluded" and fix the 96,646/92,004 and 2,173/838 inconsistencies.
5. Repair the figures: Fig 2 label and size, Fig 3 tick collisions and a panel carrying the abstract's movers and trend numbers, Fig 1 counts, Fig 5A raw regional proportions.

VERDICT: major revision (narrow; every required change is feasible with data held).
