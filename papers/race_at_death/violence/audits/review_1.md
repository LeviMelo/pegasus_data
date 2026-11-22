# Referee report 1: paper 5 (violence: race at birth, in hospital and on the certificate, by cause)

Standard: IJE / AJE / Soc Sci Med plus numerical audit. Read: `violence/text*.py`, the built `manuscript.docx` and `supplement.docx` (text extracted; `violence/out/manuscript.txt` and `supplement.txt` do not exist, only the .docx), `ledger.md`, `results.json` (`youth`, `context.youth`), `violence.json`, `analysis/violence.py`, the youth section of `analysis/results.py`, `analysis/counts.py`, `_candidates` and `candidate_counts` in `modelled_race.py`, the method paper's review `estimator/audits/review_2.md`, the figures, `reading_report.md`. Nothing was run or edited. Numbers in section 7 were recomputed from the JSON by short arithmetic only.

## 0. Overall judgement

**Major revision.** The question is important, the data are inventive, and the birth-to-certificate result is real in its direction: the net share of White falls by about 17 points between the birth record and the certificate for every external cause, against about 5 for natural deaths. But the paper's central inference ("the departure arises at death"; "labelling at death", specific to assault; "darker than earlier hospital records") is not supported by what is shown, for four reasons.

1. The hospital test is read through conditional shares (White in hospital, certified White), which are two-way flows. Net, the hospital record and the certificate of firearm victims are almost the same (White 24.9% vs 21.2%). The big contrast is that natural deaths are *lightened* (42.9% to 51.8%), not that assault victims are darkened (7.1).
2. The net birth-to-death shift is as large for transport accidents (-16.5 points) and suicide (-15.5) as for firearm assault (-16.9). That contradicts "specific to the cause" and the assault-specific labelling story. It is "external versus natural", which selection on unrecorded colour in life, or any medico-legal certification, would also produce.
3. The hospital register is a different population by cause: 2.1 net admissions per natural death against 0.24 per firearm death (9-fold), and admission-weighted, so the natural reference is dominated by heavy hospital users whose race is re-recorded repeatedly.
4. One sentence of the Discussion is contradicted by the paper's own table (section 1.1), and the "largest where the certifier is a medical examiner" claim is contradicted by Figure 2B.

Fixable with data in hand (section 3). The estimator is unvalidated for repeated admissions at this age and the SIH control scaling has a window mismatch (section 1.4). Reject is not warranted.

## 1. Errors

Ranked by consequence.

**1.1 Discussion: "called White most of those later certified Brown after an assault" is false.**
- Location: `text_discussion.py`, paragraph 1, sentence 3; also the second paragraph "called half of the firearm deaths Brown".
- Evidence: Results own sentence: of those certified Brown after an assault, 0.18 had been recorded White in hospital (all assault: `certified brown|hospital white` 0.181, se 0.018), against 0.164 for natural deaths (z 0.8 for the difference). So 78.5% of assault victims certified Brown had been Brown in hospital. "Half" is the share of *hospital-White* admissions later certified Brown (0.50), a different conditional. In absolute terms that flow is 0.501 x 1,220.9 = 612 admission-equivalents; the opposite flow (hospital Brown, certified White) is 0.126 x 3,450.6 = 435.
- Fix: delete the sentence; report both flows and the margins (section 1.2). The ledger row "hospital recorded half the later firearm victims White" also reads the wrong direction: `hospital white|certified brown` 0.50 is among hospital-White, not among victims.

**1.2 "Darker than ... earlier hospital records of the same people" is a statement about a conditional, not about the net classification.**
- Evidence (`violence.json`, admission-weighted marginals):

| group | hospital W / Black / Br | certified W / Black / Br | net W shift |
|---|---|---|---|
| natural | 42.9 / 3.7 / 53.4 | 51.8 / 5.7 / 42.4 | +8.9 |
| transport | 42.0 / 2.3 / 55.7 | 40.9 / 4.3 / 54.8 | -1.1 |
| suicide | 40.9 / 3.2 / 55.9 | 40.5 / 5.8 / 53.7 | -0.4 |
| firearm | 24.9 / 4.6 / 70.4 | 21.2 / 6.6 / 72.2 | -3.7 |
| all assault | 25.9 / 4.5 / 69.6 | 22.1 / 6.3 / 71.6 | -3.8 |

- The test of "arises at death" is therefore: net hospital-to-certificate darkening of 3.7 points in firearm victims, set against a 8.9-point lightening in natural deaths. The contrast of 12.6 points is half reference-group lightening. Natural-death hospital Brown are certified White 0.304 of the time (firearm 0.126); that is the reference group drifting, not assault victims drifting.
- Also the hospital-sample victims are much darker than all victims at birth (hospital firearm White 24.9% vs 33.4% by birth record among found deaths), so the hospital sample is selected (section 2).
- Fix: show margins and the full 3x3 flows in the main text; describe the effect as a difference in net movement, and state that the net hospital-to-certificate darkening in assault is small (about 4 points).

**1.3 "The departure toward Brown was specific to the cause: larger for every kind of assault than for transport accidents or suicide" holds only for one cell and fails net.**
- Evidence (rows of `by_kind`, birth-race mix of found deaths weighted by P(certified White | birth race)): birth-to-certificate net White shift: natural -5.3 points; transport -16.5; suicide -15.5; other assault -15.9; firearm -16.9; legal intervention -20.5. The cell "White certified White" separates transport (0.576) from firearm (0.350) only because Brown-to-White flows differ (0.135 transport vs 0.074 firearm; natural 0.215).
- The same shows the departure is bidirectional in all causes; Brown-at-birth victims of every external cause are certified White less often (0.07 to 0.14) than in natural deaths (0.21).
- Fix: replace "specific to assault" by "all external causes; larger for assault in the White-to-White cell". Test with a model, not by comparing cells.

**1.4 SIH control: the scale and the control cover different time windows.**
- Location: `violence.py`, tables `scale` and `cells`. `scale` counts all SIH admissions 2010-2024 by municipality and birth year and sex; the control and candidates only count admissions ending before death minus 30 days.
- Effect: young women are admitted for childbirth at 15-24 (the supplement says so). A death at 16 in 2016 has no delivery admissions in its window but the scale `f` counts deliveries up to 2024 (and `m/f` for a male death is shrunk, `f/m` for a female death inflated). The chance count is mis-scaled by an amount that depends on age at death, hence on cause, and on sex mix of deaths by cause (firearm 94% male, natural 57%).
- Also the control assumes the other sex's admissions have the same race mix as same-sex chance candidates. Delivery-driven female admissions are more Brown and SUS-poor. No check is shown.
- Fix: scale within the window (admissions ending before the death-30-day date, or by age at admission), or scale by population births ratio as in the birth analysis; show the share of the candidate count that is control per cause (not reported anywhere); report results for men only.

**1.5 Denominators do not reconcile between the two analyses; one equality is suspicious.**
- Deaths by cause, `results.json` `youth.by_kind` against `violence.json` (three races certified): natural 23,780 vs 22,803; transport 16,115 vs 15,938; suicide 5,925 vs 5,518; other assault 5,052 vs 4,892; legal intervention 1,268 vs **1,270** (the subset is larger); firearm 20,795 vs **20,795** (identical, which implies no certified Indigenous or ignored race at all).
- The two scripts define the population differently (`violence.py` needs valid DTNASC in 2000-2009, valid DTOBITO, IDADE 415-424, year 2015-2024; the count tables use the role table and years 2014-2024 with `age <= 24`). One definition must be used and the loss by certified race and cause reported (certified race ignored or Indigenous by cause is itself a candidate artefact).
- Fix: build both from one deaths table; add a flow diagram of exclusions.

**1.6 Cause groups: "natural (A00-R99)" is not what the code does.**
- `ELSE 'natural'` takes every code not starting V, W, X, Y, so S, T (injury nature codes recorded as underlying cause), U and Z are "natural". "Other external" includes Y10-Y34 (events of undetermined intent, the usual hiding place of homicides in Brazil) and is used as the comparator for the medical-examiner test ("0.37 assault vs 0.60 other external"). Separate Y10-Y34 and report it.

**1.7 `records_found` in `violence.json` is mislabelled.** It is the net number of admissions per death (natural 3.47, 2.26, 2.47; firearm 0.59, 0.51, 0.51), not a share found. Not used in the text, but anyone reading the file will take 3.47 as a probability. Rename; report it, it is a finding (section 2).

**1.8 Smaller.**
- "Table 1 ... 95%CI 0.67; 1.01" and "-0.00; 0.11": Wald intervals leave [0,1]; use logit or bootstrap percentile.
- "in every fifth of municipal composition ... less often": the fifth with 80%+ White has 0.79 vs 0.91, z -1.4; "in each region" includes North (0.19 vs 0.31, z -1.4). Point estimates agree, not each interval. Say "in the same direction".
- `by_schooling` entries have `deaths` 0 in the JSON (key left unfilled); harmless but breaks any table that reads it.
- Abstract and Methods say the estimator "holds below 25,600 births a year" but this paper uses 1,600 and states no reason; the SIH version, with several records per person, was not validated by the method paper (it validated infants and deaths-in-hospital).
- Methods "Race at birth ... before the 2011 form" is right, but the paper does not state that the birth colour of 2000-2009 is the *staff's* and its White share (55.8% in 2000 to 46.9% in 2009, falling to 38% when the mother declares, 2013) is a recording-era artefact; see 4.

## 2. Does the design separate labelling at death from selection in life?

Not yet. What the data show, and what remains open:

- **What the admitted population is.** Net admissions per death: natural 2.1, transport 0.24, suicide 0.34, firearm 0.24, all assault 0.24. Few victims have any earlier SUS admission with race recorded; the paper never states the share with at least one. The hospital subset is selected on SUS use (poorer, more Brown), so the hospital comparison tests labelling in a subset that is not the victims.
- **Weighting by admissions.** A person counts once per admission. Natural deaths (cancer, sickle cell, congenital, prematurity sequelae) carry about 9 times the weight per death, with repeated recording of race in the same hospital (copy-forward), so their baseline concordance (0.82) is inflated relative to a single-record person. Assault victims mostly contribute one admission. The contrast "0.82 vs 0.47" confounds cause with number of records. Fix: weight each death by net admissions to sum to 1 (cells carry the death id in `violence.py`), or take only the earliest or latest admission before the 30-day cut.
- **Reclassification between admission and death.** Unmeasured: the time gap. Most admissions of a person who dies at 15-24 are probably in infancy or childhood (neonatal, respiratory); a hospital race entered at age 1 by staff is close to the birth record, and 10 to 15 years of life lie between it and the certificate. Reclassification in life (self-declaration, adolescence, status) is the rival, and the 30-day exclusion is the only attempt to separate. Report the gap, and restrict to admissions within 1, 2, 5 years of death (or at age 10+).
- **The hospital's own observer classification.** SIH race is entered by admission clerks, usually from the document or by observation, often defaulted (missing in about a quarter of admissions in some years: Discussion; and 18-29% "other or missing" in the method paper's findable pairs, `review_2` 1.6). Missingness is dropped from the table (`jj` not in RACES) and from the denominator; whether missing hospital race differs by cause or race is not shown. A trauma admission is the situation most likely to leave race blank.
- **The earlier admission is "made in life"**: yes, but the paper cannot show that hospital and birth records agree *before* death for future victims. The missing link is a direct birth-to-hospital comparison among deaths by cause (both are in the data): if future victims are already darker in hospital than at birth, selection or reclassification in life is shown. The margins above hint at it (firearm hospital White 24.9% against 33.4% at birth, different samples).
- **Small municipalities only.** The threshold (1,600 births a year) is a precision choice, not shown to be representative: composition (fifths) is entirely within small municipalities, mostly Northeast and the interior, which is not where most homicides occur (the paper says so). `by_kind_large` exists in the results and is nonsense (natural White certified White 1.18, se 0.36). Intermediate bands (400, 800, 1,600, 3,200, 6,400) would show whether anything moves with size.

## 3. Analyses the data allow but the paper lacks (ranked)

1. **Net flows and margins**, birth, hospital and certificate, per cause (section 1.2/1.3), with a difference-in-differences against natural deaths and a model (multinomial or two logits: certified race given birth race, cause, age, sex, composition, certifier) instead of cell comparisons.
2. **Terminal admission versus certificate.** `pair_candidate_counts` and the SIH-to-SIM link (`sih_deaths_to_sim`) already exist: for deaths in hospital, the race on the admission that ended in death (an observer who saw the living person) against the certificate, by cause. That is the cleanest test of labelling at death, with a known-answer validation already in the repository. Also the 'place = health facility' stratum (0.45 vs 0.69 natural) points at it.
3. **Birth record versus hospital record for the same deaths, by cause** (needs the three-way table or restriction to deaths with both): do future victims drift in life?
4. **Time between admission and death** and age at admission; restrict to admissions at 10+ or within 5 years; and per-death weighting (one record per person).
5. **Cause of the earlier admission:** injuries (S/T, X/Y) as earlier admissions are visible in SIH (cause and diagnosis fields). Earlier violent injury admission against none: the people who are victims later have contact with violence earlier and a colour recorded by an emergency clerk.
6. **Double-White test for selection on latent colour:** among deaths recorded White at birth *and* White in hospital, the share certified Brown, firearm against natural. If both earlier records are lighter than the certificate and the gap persists, latent-colour selection is much less likely (4.1).
7. **Sensitivity** to the 30-day window (0, 7, 30, 90, 365 days; the first admission after an injury is the same event), to the municipality-size threshold, to dropping blank hospital race, to the control scale (state-level, within-window), to male-only (94% of firearm victims) and female-only strata.
8. **Men against women** (`by_kind_sex`): firearm M 0.352 vs F 0.322 (F n=1,225); other assault M 0.43 vs F 0.66 (se 0.10); natural M 0.70 vs F 0.65; transport M 0.56 vs F 0.67. Not in the text; the sex pattern bears on the labelling reading (female homicide is typically intimate, by non-police; the certificate source differs).
9. **Found share by race at birth and by certified race, per cause**, not only per cause. If movers differ by race and by cause, the cross-classification is of different groups (the method review makes this point).
10. **Newborn colour pre-2011 as reference against the mother's declaration** is not available for these births, but the contrast is available through the 2010-2013 cohorts in the children paper: where the mother declares, is the birth-to-death darkening smaller? A staff-recorded White is the plausible source of excess Brown among White-at-birth victims.
11. **Black victims** are in Table 1 but not discussed: Black at birth certified Black 0.285 firearm vs 0.271 natural (no gap); the net Black share rises 4.3% to 6.4% (firearm) and 3.9% to 6.1% (natural), the same in both. The "direction for Black victims requires identified linkage" sentence is therefore not needed; the data say the Black category does not behave like White.
12. **The medical examiner's information:** autopsy (NECROPSIA), and the informant fields of SIM (`FONTEINV`, `FONTES` where in the lake) as separate strata; certificate completed before or after investigation.
13. **Age** (`by_age` exists, not shown): natural 15 y 0.745 vs assault 0.415, 19 y 0.704 vs 0.389; the gap holds within age, which answers the birth-cohort rival (4.2) and should be shown.
14. **Standardisation beyond municipal composition:** age, sex, schooling, birth year; direct standardisation is only to the composition of the municipality (STD).
15. **Missing or Indigenous certified race by cause** (1.5), and Y10-Y34 as its own category.

## 4. Rival explanations untested, with the separating test

1. **Selection in life on unrecorded colour (regression to the mean in the White-at-birth category).** Birth colour is the staff's, and the White share of newborns falls from 55.8% (2000) to 46.9% (2009) and 38% once the mother declares (2013); White-at-birth is a mixture, and the people killed are drawn from its darker, poorer end. The hospital race, entered by another clerk, is a second noisy reading of the same latent colour, so conditioning on hospital White does not remove it. Test: double-White (birth and hospital) strata; mother's schooling within composition (the paper shows only the schooling gradient, parallel across causes); a placebo outcome with the same socioeconomic gradient and no certifier (e.g. natural deaths of the poorest fifth).
2. **Birth cohort and recording era.** External deaths concentrate at 17-21 (born 2003-2007), natural deaths at 15-18; the White share recorded at birth differs by cohort. Test: standardise by birth year (the `by_age` figures suggest the gap holds within age: 0.745 vs 0.415 at 15). Show it.
3. **Informant and source of race.** The Ministry's instruction (reading_report B3/7b) is that the informant gives the race; for violent deaths the source is often the police or the identity document, in the natural deaths the family at the bedside. The introduction ("completed by the medical examiner who has never seen the person") describes the form's filler, not the source of the race. A different source is not "labelling by the certifier". Test: stratify by `FONTEINV`/informant source, by autopsy, and by the presence of identity documents (death at the hospital vs street).
4. **Physician-certified assaults show the same gap.** Physician-certified assault 0.397 vs physician natural 0.693 (z -3.5); medical examiner assault 0.371 vs ME natural 0.582 (z -2.7): the gap is *no smaller* where the attending physician certifies. Assault against external-not-assault among physicians: -0.028 (z -0.3). The Discussion's "largest where the certifier, a medical examiner, sees a body with wounds" is contradicted. The certifier type does not separate the readings.
5. **Differential reclassification in natural deaths (reference group lightening).** Natural-death hospital Brown are certified White 0.304 vs 0.126 in firearm deaths; the gap may be produced by the natural group's drift toward White (physician-completed with hospital record). Test: net flows (1.2) and the same contrast with transport and suicide as references.
6. **Mobility.** Half the deaths are not found; differential moving by race and cause (victims move for work or flee) would change which group is observed. Test: found share by certified race and cause; bounds on the cross-classification when found share is 0.5.
7. **Measurement of the hospital race by repeated admission** (1.2, section 2): per-death weighting.
8. **Chance agreement in SIH:** control and candidate race composition differ by sex (deliveries); male-only analysis, within-window scale.
9. **Informative missingness of hospital race** at trauma admissions: sensitivity with missing as a category.
10. **Different certifier by place of death and region** is partly addressed (strata); medical examiner coverage differs by state; a state fixed effect.

## 5. Statistical issues

- **Estimator variance.** The birth-to-death SEs are those of the Poisson difference of counts and, as the paper admits, omit the denominator; the method review (1.3, 1.4) found model SEs mis-calibrated (conservative in pooled classes, uncovered covariances between cells sharing a key and between sexes). Cells of the same key but different certified class share candidates and are treated as independent. No calibration against a placebo (shifted birth date) is shown: the empirical null recommended in review_2 5.2. Here it is cheap and decisive: shift the key date by 7, 14 days and the cells should be 0.
- **Row proportions, ratio of sums.** `est = N(j,k)/row sum` has no finite moments where the row sum can cross zero (review_2 1.2); sparse rows are the ones reported: Black at birth (n 909 natural, 63 legal intervention), Black at hospital (10.7 admission-equivalents for legal intervention: est 0.158, se 1.215). Negative estimates appear (hospital Black certified White in transport -0.046 se 0.188; suicide -0.043; firearm hospital-black cells ok). Report n_est per cell, suppress cells under a stated floor, say how negatives are handled (`clip(lower=0)` only for "found").
- **Bootstrap.** 200 replicates over municipalities, SD only, one seed; the control scale `c` is held fixed (scale uncertainty omitted); the interval is then `est +/- 1.96 se` on the proportion (leaves [0,1]). For a 2.5% tail, 200 draws are too few to claim percentile intervals; 1,000 and percentile or BCa. The two cause-groups are independent bootstraps (the difference between groups has no covariance), fine, but no test of the difference is reported, only overlap of intervals.
- **Clustering.** Municipality bootstrap is right for the hospital part; the birth-to-death SE is Poisson, so the two tables carry different notions of uncertainty and the hospital intervals (0.82: se 0.010 on 20,532 admission-equivalents) are not comparable to the birth ones. Per-person clustering is impossible (no id): admission weights inflate the effective sample size of natural deaths.
- **Multiplicity.** About 8 readings in the ledger, 7 causes, 5 fifths, 5 regions, 2 periods, 3 certifiers, 4 schooling bands, 3 places: roughly 50 contrasts with no declared primary one. Declare the primary contrast (White-at-birth certified White, assault vs natural; a net-shift model) and treat the rest as supporting.
- **Conditioning direction.** Two conditionals (certified given hospital; hospital given certified) are shown; they answer different questions, only one is cited in the abstract.
- **No effect measure.** Differences of proportions are never given with an interval; the abstract gives two proportions and no contrast.

## 6. Claims stronger than evidence

| quote | why | rewording |
|---|---|---|
| "the departure arises at death" (Abstract, Conclusion, Discussion) | Net hospital-to-certificate shift in assault is -3.7 points; the earlier records are of a selected, admission-weighted subset; time since admission unmeasured; the same net birth-to-death shift occurs in transport and suicide | "Between the last earlier admission and death, the race of young people who died of assault changed little in net terms; the larger part of their shift from the birth record had already occurred by the earlier admission or is common to all external causes" (once the missing analyses show it) |
| "part of the racial gap in homicide rates is made by the certificate" (Abstract, Implications) | No rate is computed; net shift is relative to a staff-recorded newborn colour that is itself too White; the same shift occurs in external deaths not due to assault | "Certified race of young people killed by assault is darker than their birth record by about 17 points of White; whether this changes homicide rate ratios requires a denominator on the same classification" |
| "called White most of those later certified Brown after an assault" (Discussion) | contradicted: 0.18 | delete |
| "largest where the certifier, a medical examiner, sees a body with wounds and knows the circumstances" (Discussion) | physician-certified gap -0.30, ME -0.21 | delete or "present with physician and medical-examiner certifiers alike" |
| "The departure toward Brown was specific to the cause" (Results) | net shift -16 to -17 for transport, suicide, assault | "present in all external causes; largest in the White-to-White cell for assault" |
| "the gap did not come from where the victims lived" | composition is within small municipalities only; top fifth and North not significant | "persisted within fifths of composition" |
| "Social position at birth and the manner of death both moved the certificate, and the second did so at every level of the first" | schooling is a gradient on staff-recorded birth colour; no interaction test; at 12+ years the assault interval is 0.70 +/- 0.34 | "the gradient by schooling was parallel across causes" with the interaction test |
| "tests the two readings against a record made in life" (Strengths) | admission-weighted, selected, race of unknown provenance, undated | list as limitation |
| "validated against one-to-one linkage in infants" (Methods) | different regime (infants, one-year cohort, found 90%), SIH repeated records unvalidated, review_2 found the validation does not match the application | "agreed with linkage in infant deaths; not validated for ages 15-24 or for admissions with several records" |
| "We know of no study that compared the race of the same young people at birth, in hospital and at death" | the comparison is of cross-classifications of unlinked groups; the claim "same young people" is for the found, unlinked population | "unlinked records of the same birth date, sex and municipality" |
| "alike for every cause" (found share) | range 0.468-0.540; no test; by race not shown | give the range and the test |
| Title "Who becomes Brown when killed" | White-to-Brown is half of a bidirectional flow | "Race on the certificate of young people ... by cause of death" |

## 7. Numbers recomputed

All from `results.json` and `violence.json`; "ok" means matches the text.

1. Deaths: 23,780+16,115+5,925+7,391+5,052+20,795+1,268 = 80,326. ok.
2. Found share range: 0.468 (other assault) to 0.540 (transport) = 47-54%. ok; spread 7 points.
3. Natural White to White 0.6753 +/- 1.96x0.0197 = 0.636-0.714. ok.
4. Firearm 0.350 (0.311-0.389); difference from natural -0.325, z -11.7.
5. Legal intervention 0.321 se 0.087: (0.15-0.49) ok; z against natural -4.0. Brown cell 0.845 +/- 0.171 = (0.67-1.02), printed 1.01 (rounding of se 0.087 gives 0.674-1.016): interval above 1.
6. Transport -0.100, z -3.5; suicide -0.057, z -1.4 (not different from natural); other external -0.121, z -3.0; other assault -0.204, z -4.5.
7. Hospital, firearm: 0.472 +/- 1.96x0.039 = 0.396-0.548. ok. Natural 0.821 (0.801-0.841). ok. Contrast -0.349, z -8.6.
8. Hospital: certified Brown, hospital White: all assault 0.181 (se 0.018), natural 0.164 (se 0.009), z 0.8. ok as printed; contradicts the Discussion.
9. Hospital White certified Brown: natural 0.162, firearm 0.501; hospital Brown certified White: natural 0.304, firearm 0.126.
10. Flows firearm: 0.501x1,220.9 = 612; 0.126x3,450.6 = 435; net 177 of 4,898.5 admission-equivalents = 3.6% (3.7 by margins).
11. Margins firearm: hospital White 1,220.9/4,898.5 = 24.9%; certified White 1,037.6/4,898.5 = 21.2%. Natural 20,532.1/47,841.7 = 42.9% vs 24,805.3/47,841.7 = 51.8%.
12. Net admissions per death: natural 24,805.3+2,735.0+20,301.4 = 47,841.7 over 22,803 certified-race deaths = 2.10; firearm 4,898.5/20,795 = 0.24; all assault 6,549.5/26,957 = 0.24; transport 3,789.2/15,938 = 0.24; ratio natural/firearm 8.8.
13. Birth White share of found victims (rows of `by_kind`, three races): natural 49.3%, transport 53.8%, suicide 55.6%, other assault 39.8%, firearm 33.4%, legal 36.1%.
14. Net White shift birth to certificate (found, via rows): natural -5.3, transport -16.5, suicide -15.5, other assault -15.9, firearm -16.9, legal -20.5 points.
15. Certified White among all deaths (3 races, `violence.json`): natural 9,240/22,803 = 40.5%; firearm 3,259/20,795 = 15.7%; transport 35.0%.
16. Standardised: 0.445 vs 0.655, difference 0.210, se 0.029, z 7.2. ok (text 0.45, 0.65).
17. Composition fifths, assault minus natural: -0.222 (z -6.0), -0.256 (-4.7), -0.205 (-2.8), -0.236 (-3.5), -0.122 (-1.4). "Every fifth" holds for point estimates; the last is not significant.
18. Regions assault minus natural: North -0.125 (z -1.4), Northeast -0.288 (-7.7), Southeast -0.213 (-4.3), South -0.215 (-3.4), Centre-West -0.300 (-3.0).
19. Periods: 2015-2019 assault 0.423 vs natural 0.665 (z -4.4); 2020-2024 0.355 vs 0.678 (z -10.8).
20. Certifier: ME assault 0.371 vs external-not-assault 0.598 (z -9.2); ME assault vs ME natural -0.210 (z -2.7); physician assault 0.397 vs physician natural 0.693 (-0.296, z -3.5); physician assault vs external-not-assault -0.028 (z -0.3). ME-certified share of assaults 24,530/26,958 = 91%; of natural 2,163/23,780 = 9%.
21. Schooling (assault): 0.258 at 0-3 y, 0.522 at 8-11 y (printed ok); natural 0.504 and 0.795: gaps 0.246 and 0.273, parallel.
22. Age 15: natural 0.745 vs assault 0.415 (diff -0.330); age 19: 0.704 vs 0.389 (-0.315); assault flat from 15 to 24 (0.29-0.44), natural falls 0.745 to 0.52.
23. Sex, firearm: M 0.352 (n 19,570) vs F 0.322 (n 1,225, se 0.072); legal intervention F n 15, estimate 0.957 se 0.898.
24. Birth White share of newborns SINASC: 55.8% (2000), 46.9% (2009), 39.0% (2012, 93% mother field) from `results.json` "form".
25. Black at birth certified Black: natural 0.271 (se 0.032), firearm 0.285 (se 0.035): z 0.3. Net Black share: natural 3.9% to 6.1%; firearm 4.3% to 6.4%.
26. Hospital sparse cells: legal intervention hospital Black row n 10.7 with se 1.2 on est 0.158; transport hospital Black certified White -0.046 (se 0.188); suicide -0.043.
27. Cause counts mismatch (1.5): natural 23,780 vs 22,803 (977 lost, 4.1%); legal 1,268 vs 1,270.

## 8. References

- Cited and verified in the reading report: Soares Filho 2011; Cerqueira and Moura 2014; Saperstein and Penner 2010; Penner and Saperstein 2008; Noymer, Penner and Saperstein 2011 (abstract and the reading report show the US effect is small: 204 of 12,937 Black homicide victims not Black by next-of-kin report, odds 2.4 for homicide; the paper cites it as support without the magnitude, and the Brazilian effect here is more than 30 points. Say so, and say it prompts a measurement-source reading, not only labelling).
- Missing and in the reading report but not cited: Travassos and Williams 2004 (who reports race on the certificate; "informant"), Telles 1998 and Saperstein 2012 (observer classification follows status), Arias et al. 2010 (NCHS validity of race on death certificates; read, not cited), Atlas da Violencia (under-reporting of homicides; undetermined intent).
- Add: Hahn et al. 1992 (race on death certificates); Chipperfield, Bycroft and Chambers 2011 and Goldstein, Harron and Wade 2012 (linkage-error-corrected contingency tables); Lash et al. 2014 (bias analysis); Schuemie et al. 2014/2018 (negative-control calibration; empirical null from shifted dates); a source on Brazilian race classification by interviewers and its movement with status (Telles and Lim 1998); the Ministry's own manual for the death certificate race field (the introduction misdescribes the mechanism, reading_report 7b).
- The RECORD checklist is named but not given; the "100 Million Cohort" is mentioned without citation; the claim that the 1.779 resolution establishes that the examiner "in most cases has never seen the person alive" is not in that resolution (it regulates who must fill the certificate).
- The reference list (8) is thin for the claims: nothing on Brazilian studies of race misclassification in SIM by cause, on police lethality and certification, or on methods for linkage without identifiers beyond the companion paper.

## Summary table of required changes

1. Correct the false Discussion sentence and the ledger row; present margins and net flows; restate the hospital finding (net 4 points, against 9 of lightening in natural deaths).
2. Replace "specific to assault" and "arises at death" by results of a model on net shifts with transport and suicide as comparators; state that the effect is present in all external causes.
3. Fix the SIH design: per-death weighting, within-window control scale, report time to death, share with any admission, missing hospital race, and a male-only analysis; add terminal-admission versus certificate.
4. Add birth versus hospital for the same deaths, double-White stratum, age and birth-cohort standardisation, size-threshold and 30-day sensitivity, shifted-date placebo.
5. Reconcile denominators; split Y10-Y34; use bootstrap percentile intervals with 1,000 replicates; declare a primary contrast; correct references and the introduction's account of who records race.
