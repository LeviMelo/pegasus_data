# Referee report 2: paper 5 (violence), final verification

Read: `out/manuscript.txt`, `supplement.txt`, `text*.py`, `ledger.md`, `display_plan.md`, `results/violence.json`, `results.json` (`youth`, `context.youth`), `analysis/violence.py`, `common.py` (KIND), `counts.py`, the four figures, review_1 and response_1. Numbers recomputed from the JSON with short scripts. Nothing edited, no build, no git.

## 1. Verdict

**Major revision.** The rewrite fixed the false sentences of review 1 and added useful designs (one record per person, terminal admission, placebo, men only, 180 days). But the new central conclusion ("recorded darker before they were killed"; "the change was already present in hospital records made during life"; "the racial gap in violent death is not mainly made at death") rests on a comparison the data do not support, and one headline claim ("agreed less in both directions") is false for the whole table.

1. **The "darker in life" inference compares levels across different subsets, and within-cause the hospital record is as dark as in natural deaths.** Share White, birth (all deaths found) then hospital (admitted persons): natural 0.482 then 0.385 (-0.097); transport 0.533 then 0.394 (-0.139); suicide 0.527 then 0.425 (-0.102); firearm 0.330 then 0.234 (-0.096); other assault 0.388 then 0.257 (-0.131). The hospital record is about 10 points darker than the birth record in natural deaths and firearm deaths alike. What differs by cause is the hospital-to-certificate step (natural +0.075, firearm -0.032, z of the contrast about 6). Read as a chain, the excess darkening of assault against natural deaths arises between the hospital and the certificate, the opposite of the paper's reading. The chain is not valid either, since the three margins come from different sets (birth: all found; hospital: the 21-47% with an admission, a SUS-selected, darker subset). That is the point: the paper has no birth record for the admitted deaths, so "darker than at birth already in life" is untested. "Hospital White 0.24 against 0.38 for natural" only restates the birth difference (0.33 against 0.48). Review 1 (section 1.2, analysis 3) asked for the birth-by-hospital cross for the same deaths; response_1 declined it as "needs both candidate sets per death" and then built the conclusion on its absence.
2. **"The two records agreed less for violent deaths, in both directions" is false.** Hospital Brown certified White: natural 0.300, firearm 0.126, transport 0.149. Hospital Brown certified Brown: firearm 0.810, transport 0.806, natural 0.623 (Figure 4A shows it). Overall three-race agreement, rebuilt from the cells and row shares: natural 0.66, suicide 0.71, firearm 0.70, transport 0.75. Violent deaths do not agree less overall; only the hospital-White row differs (0.46 against 0.74). The exchange is asymmetric (White to Brown at assault, Brown to White in natural deaths), which is a different finding. This sentence is in the Abstract, Results and Discussion.
3. **The hospital's own race is darker than the certificate in every cause at the terminal admission** (the cleanest test, review 1 analysis 2): hospital White against certificate White, natural 0.362 against 0.453, transport 0.322 against 0.373, firearm 0.217 against 0.260. If anything the certificate is lighter than the clerk's record of the dying person. This favours a rival (clerks code darker; SIH defaulting to Brown) for the whole "darker in hospital" level, and it appears in Results without interval, without n (675 persons for firearm, 12 for legal intervention) and is absent from the Abstract and Discussion.
4. **The SIH control scale is unchanged** (all admissions 2010-2024 by municipality and birth year; review 1 item 1.4), and the placebo now shows its cost: a 7-day shift leaves +384 of 3,187 persons (12%) for firearm, +188/2,227 (8%) transport, +126/1,069 (12%) other external, and -247/9,564 (-2.6%) for natural, opposite in sign. The text prints "3%" for natural through `abs()`, hiding that the bias is negative there. A bias that differs in size and sign by cause (sex mix, deliveries) is exactly what could create the differences being interpreted, and it is not subtracted.
5. **Unaddressed from review 1:** time since admission and age at admission; share of hospital race missing or defaulted by cause and year; the Y10-Y34 split; "natural" still includes S/T/U/Z codes (`ELSE 'natural'` in `violence.py`, `NOT IN V-Y` in `common.KIND`), against "A00-R99" in Methods; Wald intervals above 1; a declared primary contrast.

## 2. Review-1 items: fixed or not

| Item | Verdict | Evidence in the manuscript |
|---|---|---|
| 1.1 false Discussion sentence | Fixed | Deleted; new Discussion never says "called White". |
| 1.2 margins, net flows | Partly | Margins now given (Fig 4B, "changed by +0.08 ... -0.03"). Interpretation wrong (above, 1). Full 3x3 flows only in the supplement. |
| 1.3 "specific to the cause" | Fixed | "every external cause lost more White ... assaults no more than transport accidents". But suicide's loss is 14, not 16-17 (below). |
| 1.4 scale window, deliveries | Not fixed | Code unchanged; placebo exposes it (above, 4). No stratum for the control's share of candidates. |
| 1.5 denominators | Disclosed, not reconciled | Figure 1 says 87,391 deaths; Table 1 and Results say 80,326 (natural 25,869 against 23,780). The Methods sentence on the two municipality sets ("class municipalities by mean births of 2012-2023 ... of 2000-2009; the two sets are not identical") is in `text.py` and the docx but **not in the built `manuscript.txt`/PDF** (PDF and txt are dated 03:29, text.py 03:39: stale). One set should be used; the counts table has the municipality, so this is cheap. |
| 1.6 natural / Y10-Y34 | Not fixed | Methods still "natural (A00-R99)"; undetermined intent sits in "other external", which is the comparator in the certifier sentence. |
| 1.7 `records_found` | Moot | Replaced by `with_admission`, `admissions_per_death`; both now reported. |
| 1.8 Wald intervals, fifths, regions | Not fixed | Table 1 still prints "0.84 (0.67; 1.01)" and "-0.00; 0.11". "held in every fifth ... in each region" stays: top fifth z -1.4 (0.79 against 0.91), North z -1.4 (0.19 against 0.31). |
| 1.8 validation wording | Not fixed | "validated against one-to-one linkage in infants" with no caveat for 15-24 or multi-record admissions; no reason given for 1,600. |
| Top 3 per-death weights, men, 180 d, terminal | Done | Person-level; men 0.460, 180 d 0.459; terminal given (no interval). |
| Top 4 placebo | Done, weak | One shift (7 d), residual stated, not subtracted, no interval. Birth-by-hospital cross, size threshold, double-White not done. |
| Top 5 bootstrap 1,000 | Done for hospital only | Table 1 still Poisson, omitting denominator variance. |
| Claims table: "same young people" | Not fixed | Intro "We know of no study that compared the race of the same young people"; Strengths "follows the same young people" (records are unlinked, overlapping sets). |
| Intro: who records race | Not fixed | Still "completed ... by the medical examiner ... who in most cases has never seen the person alive [3]" with CFM 1779, which regulates who completes the form; informant not tested. |
| References (Travassos, Arias, Telles, Hahn, Lash, Schuemie, Chipperfield) | Not fixed | Still 8 references. Magnitude of the US effect (Noymer) still not stated. |
| Black category (11) | Not fixed | Table S2 has it; no text. Black-hospital cells are mostly "not estimable". |
| Ledger | Stale | `ledger.md` still says "labelling at death ... supported", "hospital recorded half the later firearm victims White", "certifier excluded", the opposite of the paper now. |

## 3. Numbers recomputed (printed against recomputed)

| # | Quantity | Printed | Recomputed | |
|---|---|---|---|---|
| 1 | Table 1 deaths | 80,326 | sum 80,326 (hospital set 87,391) | ok, sets differ by 9% |
| 2 | Found share | 47%-54% | 0.468-0.540 | ok |
| 3 | Natural White to White | 0.68 (0.64; 0.71) | 0.675 +/-1.96x0.0197 | ok |
| 4 | Firearm White to White | 0.35 (0.31; 0.39) | 0.350 | ok |
| 5 | Birth to certificate White, natural | 5 points | 48.2 to 43.2 = 5.0 | ok |
| 6 | Same, transport | 16 | 53.3 to 36.9 = 16.4 | ok |
| 7 | Same, **suicide** | "16-17 for transport, suicide and firearm" | 52.7 to 38.4 = **14.4** | **wrong** (Abstract, display_plan) |
| 8 | Same, firearm | 17 | 33.0 to 16.3 = 16.8 | ok |
| 9 | Earlier admission, natural / firearm | 47% / 21% | 0.465 / 0.210 | ok |
| 10 | Admissions per death | 2.0 / 0.2 | 1.96 / 0.22 | ok |
| 11 | Hospital White, assault / natural | 0.24 / 0.38 | 0.239 / 0.385 | ok |
| 12 | Net shift natural / transport / assault | +0.08 / -0.03 / -0.03 | +0.075 / -0.032 / -0.035 (se 0.012, z 2.9) | ok; "not darker" at net is then not exact |
| 13 | Hospital White, certified White: firearm / natural | 0.46 (0.40; 0.51) / 0.74 | 0.456 / 0.743 | ok |
| 14 | Hospital Brown, certified White: firearm | 0.13 | 0.126; natural 0.300 omitted | ok, selective |
| 15 | Men / 180 days | 0.46 / 0.46 | 0.460 / 0.459 | ok |
| 16 | Terminal, firearm: hospital White, certificate White | 0.22, 0.26 | 0.217, 0.260 (n_est 675) | ok |
| 17 | Placebo natural | "3%" | -247/9,564 = -2.6% (negative) | sign hidden |
| 18 | Composition, lowest / highest fifth | 0.17 v 0.39; 0.79 v 0.91 | same; z -6.0, -1.4 | ok; "every fifth" interval-wise no |
| 19 | Standardised | 0.45 v 0.65 | 0.445 v 0.655 | ok |
| 20 | Certifier | ME assault 0.37, physician 0.40, ME external 0.60 | 0.371, 0.397 (n 1,905, se 0.08), 0.598 | ok |
| 21 | Schooling, assault | 0.26 to 0.52 | 0.26 to 0.52; natural 0.50 to 0.79 | gradients 0.26 v 0.29: "for assaults more steeply" (Discussion) **false in absolute terms** |
| 22 | Agreement three-race | "less for violent" | natural 0.66, firearm 0.70, transport 0.75 | **false** |
| 23 | Birth to hospital White, firearm / natural | not shown | -0.096 / -0.097 | undermines central claim |
| 24 | Legal intervention, Brown to Brown | 0.84 (0.67; 1.01) | est +1.96 se exceeds 1 | interval above 1 |

## 4. Claims against the numbers

| Claim | Problem |
|---|---|
| Title "Recorded darker before they were killed"; Conclusion "recorded darker than at birth already during life" | Birth-to-hospital change is about the same in natural (-10) and firearm (-10) deaths; different subsets; not shown (section 1, point 1). Title asserts a temporal result the design cannot give. |
| "Hospital records already showed most of that change" | Compares a hospital level with a birth level on different sets; the part specific to assault (versus natural) is -0.12 at birth to certificate and -0.11 between hospital and certificate. |
| "The racial gap in violent death is not mainly made at death" | No rate is computed; rests on point 1; the paper's own terminal-admission result is inconsistent with the "darker in life" level. |
| "agreed less ... in both directions" (Abstract, Results, Discussion) | False for hospital Brown and for overall agreement. |
| "net, not darker" (Conclusion) | Net -0.035 (z 2.9) for assault; the Abstract says "about as dark", the Conclusion says "not darker". |
| "The data favour the second [selection or reclassification in life]" | Cannot separate classification by hospital clerks (darker at terminal admission) or selection into SUS from reclassification in life. The 30-day exclusion is the only guard. |
| "It held whoever certified" | 91% of assaults are medical-examiner certified; physician-certified n = 1,905, se 0.08; certifier type itself moves external deaths (0.43 physician, 0.60 ME). |
| "held in every fifth ... in each region" | Top fifth and North not significant; say "in the same direction". |
| "counts each person once, and measures chance agreement with a negative control and a shifted-date placebo" (Strengths) | The placebo shows an uncorrected 12% residual, opposite in sign for natural deaths. |
| "assaults no more than transport accidents" | Supported (firearm 16.8, transport 16.4), but "most of all by assault" in the Conclusion rests on the hospital level only. |

## 5. Rival explanations still untested and missing analyses (ranked; F = feasible with data held)

1. **Birth, hospital and certificate for the same deaths** (F): per death, birth candidates and admission candidates both exist in the DuckDB; estimate the 3-way table, or restrict to deaths with a unique key in both. This is the single decisive analysis for "darker in life". Without it, drop the title and conclusion. (F, medium work.)
2. **Hospital coding practice** (F): share of SIH `RACA_COR` missing/99/defaulted by year (2010-2024) and cause; restrict to years after race completeness rose; compare terminal-admission race with certificate and with birth for the same persons. Tests clerk defaulting to Brown.
3. **Time and age at admission** (F): `ds` and `dn` are in `adm`; restrict to admissions at 10+ or within 5 years of death; report the gap by cause. Natural deaths probably have recent chronic admissions, assaults childhood ones.
4. **Control scale within the window / by age** and the placebo at several shifts (7, 14, 28, 365 days) as an empirical null subtracted per cause (F, cheap). Female-only and male-only strata.
5. **Double-White stratum** and latent-colour selection (white at birth and white in hospital, then certified): needs 1 (F).
6. **Rates by birth race against rates by certified race** (F): `common.rates` and cohort births exist; the Introduction's motivation (racial gap in homicide rates) is never evaluated. This would be the paper's most useful single result.
7. **Age and birth-cohort stratification**, sex (`by_age`, `by_kind_sex` already computed and unused: natural 0.745 at 15 against 0.415 for assault; firearm F 0.32 vs M 0.35), cause-specific model with interaction (certified race given birth race, cause, age, sex, composition) with a declared primary contrast and a 3-race multinomial.
8. **Y10-Y34 undetermined intent** as its own group (the usual homicide hiding place); S/T/U/Z out of "natural".
9. **SIM fields not used**: autopsy, informant/source (`FONTE*`), `CIRCOBITO`, place; stratify.
10. **Size-threshold sensitivity** (400, 800, 1,600, 3,200) and one common municipality set for Table 1 and the hospital analysis (F).
11. Earlier injury admissions (S/T, X/Y codes in SIH diagnosis) as a covariate: contact with violence before death.
12. Black victims: the net Black share changes little (Black to Black 0.285 firearm against 0.271 natural); report.

Not feasible without identified data: the capitals; true person-level linkage.

Use of the data: the SIH diagnosis, age, admission date and facility; the SIM autopsy and informant fields; the births' mother's age and parity; and the rate denominators are all held and unused. The paper uses race and cause only.

## 6. Figures (guide sections 2, 5, 6, 7; display plan)

- **Figure 1 (`flow_violence`)**: the box titles "Live births 2000-2009 (SINASC)" and "Deaths at 15-24, 2015-2024 (SIM)" are wider than their boxes and collide with the borders (opened at full size). The figure states 87,391 deaths while Table 1 and the Results state 80,326: the reader sees two denominators and no explanation (the explaining Methods sentence is missing from the built PDF/txt). Numbers beyond that are absent: no n by arrow (deaths with a candidate, with an admission), so it is a design sketch more than the flow diagram the guide expects.
- **Figure 2 (`violence_cause`)**: legible, intervals present, legend in empty space. Legal-intervention interval cut at 1.0 and the Brown estimate bound above 1 is clipped without note. No n per cause; the guide asks for n and values (forest layout). It does not display the margins (birth versus certificate share White), which is the central result in the Abstract; that exists only in Table 1.
- **Figure 3 (`violence_strata`)**: three panels at 175 mm: legend and tick text about 6-7 pt (small); panel A's top-right points and bars overlap (assault and natural at 0.9); amber (external) and vermilion (assault) are close in hue for colour-blind readers; panel B drops three of nine points (SE above 0.15) without a mark, and has no legend of its own (shared with A, but the points sit apart and the verification-service panel shows only natural); panel C "8-11" and "12 or more" labels nearly touch; y-range above 1.0 with bars exceeding 1.0. No n anywhere.
- **Figure 4 (`violence_hospital`)**: panel B, the paper's core evidence (net change), has **no intervals**, though the caption says "bars, 95% confidence intervals"; the bootstrap se of the net shift is 0.009-0.045 and is available. Suicide's hospital marker is hidden under the certificate marker. Panel B has no birth reference, so it cannot show what the Discussion says; the three margins per cause (birth, hospital, certificate) should be one panel, with the same-set caveat. Panel A omits Black and the terminal/men/180 checks (text only). No n.
- **Abstract numbers in a main item**: everything except the "16-17" claim (wrong for suicide), the net-shift values (visible only as marker gaps in 4B, never printed) and the 5-point natural change (Table 1 only as two columns, no difference). Display plan states "every abstract number is in Table 1 or Figure 4": not true for the net shifts or for the 16-17 range.
- Text in English, locale consistent; sources named in captions.

## 7. Minor

- Margins mix bases: birth margins over four classes (`declared_mix` includes Indigenous), hospital and certificate margins over three races.
- Terminal admission cells for legal intervention (n_est 12) should be suppressed, not printed.
- Table 1 has no CI for the margins; the abstract has no effect measure or interval for any net shift.
- "alike for every cause" for found share with a 7-point spread and no test; found share by race not given.
- `with_admission` clips negative per-death estimates (`clip(lower=0)`), which biases the shares upward; say so.
- Legal intervention: S2 row "white" 0.24 (0.03; 0.46) from n_est 12 to 206 persons; text relies on it ("0.32") with an interval of width 0.34.
- Intervals for hospital cells are percentile; for Table 1 Wald. Two notions of uncertainty are mixed in one paper.
- The build outputs (`out/manuscript.txt`, PDF) are older than the docx and `text.py`; rebuild before reading.
- Methods "Race at birth ... by staff" is right; the recording-era artefact (staff-recorded White share 55.8% in 2000 to 46.9% in 2009) is not used as a rival (regression to the mean in the White-at-birth category).

## Verdict line and top five required changes

**Verdict: major revision.**

1. Do the birth-by-hospital-by-certificate analysis for the same deaths (or at minimum restrict birth margins to admitted deaths); until then remove the title "Recorded darker before they were killed" and every statement that the departure is "already present in life".
2. Correct the false statements: "agreed less in both directions" (overall agreement natural 0.66, firearm 0.70), "16-17" including suicide (14), "for assaults more steeply" by schooling, "net, not darker" (-0.035, z 2.9); restate the finding as an asymmetric exchange.
3. Test hospital clerk coding as the rival: SIH race missingness and defaulting by year and cause, the terminal-admission result with intervals in the Discussion, admission age and gap, within-window control scale, and an empirical-null subtraction from shifted-date placebos at several shifts.
4. Use one deaths population and one municipality set for the whole paper; fix cause groups (S/T/U/Z out of natural, Y10-Y34 separate); state a primary contrast and a model with interaction; use bootstrap or logit intervals (no interval above 1); put intervals in Figure 4B and fix Figure 1 text overflow.
5. Evaluate the stated motivation (rates by birth race against certified race), and update the references, the Introduction's account of who records race, the "same young people" wording and the stale ledger.
