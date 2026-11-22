# Review 3 - paper 2, `indicators/` (final verification)

Read: manuscript.txt/supplement.txt, text*.py, display_plan.md, review_2, response_2, indicators2.json, results.json, spatial.json, the four figures. Note: `out/manuscript.txt` and the PDFs (03:28) are older than the .docx (03:43); the only text difference I found is the Figure 2 caption (docx: yearly jackknife intervals; txt: "not computed"). The txt/PDF must be rebuilt before submission; the figure PNG already shows the intervals. Nothing else run; recomputation is read-only Python on the JSON.

## 1. Verdict: major revision (close to minor on the central result)

The core finding is sound and now correctly framed: numerator and denominator on different constructs (child on the certificate, mother on the birth record) reverse White to Brown (0.80 to 1.31), and the child's denominator brings it back (0.79). The intervals for the 2 x 2 are now honest at national level, and the paper is short. But (a) the Abstract mixes two rate sets and its own ratio does not follow from its own rates; (b) "almost entirely from one flow" and "the children of Brown mothers die more often by the child's classification" overstate what the numbers show (order-dependent waterfall; child's-race interval includes 1 and 10 of 19 strata); (c) the regional results contradict the "households classify the same" mechanism in the South and Northeast and are left unexplained; (d) the objective promises the 510 regions, but the 2 x 2 and Black to Brown are not done there; (e) Methods promise sensitivity analyses whose results are printed nowhere; (f) a false sentence on standardisation; (g) several review-2 analyses still missing.

## 2. Review-2 items

| Item | Fixed? |
|---|---|
| 1.1 certified-ratio CI Poisson only | Fixed. Jackknife SE 0.076 (log-scale 1.31: 1.17; 1.46). Linkage/census-flow error still excluded; stated in Methods. |
| 1.2 scale by certified race (Indigenous) | Mostly. Factors 1.27/1.29/1.29/1.63; Indigenous ratio 1.96. NOT fixed: Abstract and Table 1 note still quote 11.0 and 13.6 per 1,000 (`rate_mother_linkage`, old global scale: 11.01, 13.59, ratio 0.81) whereas Results quote 10.8 and 13.5 (0.80). Same paper, two values for the same rate. The 4.1% linked deaths with no/Yellow mother's race are only in Figure 1. Regional models still use rounded scaled counts as Poisson counts; response silent. |
| 1.3 "Brown children" | Fixed in the Abstract ("children of Brown mothers"), but the Conclusion then says "classified consistently, by the mother or by the child, the children of Brown mothers die more often": under the child's classification the group is Brown children, not children of Brown mothers (see 3.2). |
| 1.4 regional dependence of the two models | Partly. Ratio-of-ratios credibility counts dropped; Limitations admit no joint uncertainty. But Figure 3C and "3.15 times / 1.83" still use a ratio of separately fitted posterior means, no intervals. |
| 1.5 crude vs standardised | Done (0.87, 1.66, 0.81) but the new sentence is wrong: "the crude national ratios are pulled toward 1 by the concentration of White births in regions of lower mortality". True only for the usual way (1.31 vs 1.66). For the mother's race crude 0.80 is FARTHER from 1 than standardised 0.87; for the child's 0.79 vs 0.81 no change. Standardisation is over 5 macro-regions only; Black to Brown standardised values (1.18, 0.53, 0.85) exist in JSON but not in Table 1. |
| Top 1 reframing, 2 x 2, waterfall | Done; see 3.1 for what the waterfall can and cannot support. |
| Top 4 age/cause/year | Done (S1, Fig 2C), but S1 prints no intervals; with the jackknife the child's-race White to Brown CI includes 1 in 8 of 11 years (the rest touch 1.00-1.02), post-neonatal 0.94 (0.75; 1.18), congenital 1.06, external 0.95, other 0.93. |
| Top 4 Ministry comparator | Not done (conceded). "The usual way the rate is computed" (Abstract, Methods, Discussion) is still an authors' definition with no citation of an official series. Needed: one sentence plus the Ministry's published White/Brown/Black infant rate for 2013-2023 beside Table 1, or an explicit "defined here". |
| Top 5 joint flow model; Black to Brown regionally; prior sensitivity; map A | Not done. Map A (near-uniform, prior-driven) is retained, though honestly labelled in the text. No prior sensitivity, no raw regional ratios, no exceedance/multiplicity control. |
| 2.4 mother's race misrecording sensitivity | Not done. |
| 2.5 coverage, cohort vs period denominators | Not done. |
| 3.6 birth weight / gestational age / schooling | Not done. |
| 3.8 state / municipal size | Not done for infants. |
| Linkage selection bound; false links by race | Not done ("cannot be checked" remains, though a tipping-point bound can be computed). |
| 5.5 class means by composition | Unchanged: hand-set cut-points, no intervals, WLS R2 = 0.065 not reported, and the non-monotone pattern (3.15, 1.92, 1.83, 2.19) reported only as "3.15 and 1.83". |
| Table 1 deaths/births per cell | Not added. |
| Title "four inequalities" | Fixed. |

## 3. Numbers recomputed (printed / recomputed from JSON)

1. White/Brown mother's rates: Results 10.8/13.5 = 10.84/13.48 ok; Abstract 11.0/13.6 = 11.01/13.59 from a different (old) calculation; 11.0/13.6 = 0.81, not the 0.80 printed beside it. Inconsistent.
2. White to Brown mother's 0.80 (0.77; 0.84): est 0.8046, se 0.0157; exp(ln est ± 1.96 se/est) = 0.77; 0.84. ok. Rates ratio 10.8426/13.4752 = 0.8046 ok.
3. Usual 1.31 (1.17; 1.46): 1.3054, se 0.0756 -> 1.17; 1.46 ok; rates 14.102/10.803 = 1.3054 ok.
4. Child's 0.79 (0.58; 1.07): 0.7897, se 0.1223 -> 0.58; 1.07 ok; 10.361/13.120 = 0.7897 ok.
5. Black to Brown 1.15 (1.09; 1.20), 0.49 (0.42; 0.56), 0.80 (0.66; 0.98): all reproduce.
6. Linked share 309,203/383,975 = 80.53%; 383,975-74,772 = 309,203 ok. Scale factors 1.27/1.29/1.29/1.63 ok. Shares by certified race 81.1/81.1/80.2/61.9 ok. No-race 8.4% ok.
7. Excess deaths 44,851 = 2.633 per 1,000 x 17.04 M Brown births ok; 8,543 Black, deficits 56,205 and 16,418 ok.
8. Waterfall 0.80 to 1.61 to 1.28 to 1.31 to 0.79 ok. For Black: text says "Black mothers' infants certified Brown took the ratio from 1.15 to 0.57"; the actual step is 1.37 to 0.57 (1.15 to 1.53 after Brown to White, to 1.37 after White to Brown, to 0.57). The code prints WF[0] and WF[3], skipping two steps. Misstatement.
9. Waterfall shares (log scale, total +0.484): Brown to White +0.696 (144%), White to Brown -0.234, Black to Brown -0.079, Brown to Black +0.019, Indigenous -0.004, remaining flows and no-race deaths +0.087 (18%). "Almost entirely" is one order of an order-dependent path; and 18% of the log change is not a flow but the exclusion of the 8.4% certificates without race (Brown deaths lack a race more often). See 4.1.
10. Year ranges: mother's 0.76-0.85 (0.761-0.854), usual 1.24-1.39 (1.242-1.394) ok; the child's cell (0.73-0.86) is not reported, and its yearly jackknife intervals reach 0.99-1.02 from 2020.
11. Strata (S1) match JSON (neonatal 0.81/1.13/1.21/0.43/0.73/0.71 etc.). Congenital mother's 0.98 is not an inequality to be "reversed" (null to 1.75). Child's cell: 0.69 perinatal to 1.06 congenital, spanning 1; "returns to the mother's" holds for none of congenital (1.06 vs 0.98 ok) ... but 0.72 vs 0.57 infectious and 0.94 vs 0.77 post-neonatal are not equal.
12. Regional (macro) child's White to Brown: 0.74, 0.52, 1.00, 1.35, 0.88 ok vs mother's 0.96, 0.88, 0.85, 0.84, 0.88 ok. In the South Black to Brown child's is 1.82 vs 1.21 mother's; Brown certified rate 5.8 vs mother's 11.4 per 1,000, child's 7.4: regional household flows do not reproduce the certificate in the South.
13. 446 / 159 regions: matches spatial.json. 115 and 469 (dropped from text) also present. 400 reversed.
14. Composition classes: 3.15 (<10%), 1.92, 1.83 (30-59%), 2.19 (>=60%) ok; text prints two.
15. Standardised 0.87/1.66/0.81 ok (0.866/1.658/0.805); Black 1.18/0.53/0.85 unprinted.
16. 2.6 and 4.6 per 1,000 differences ok (2.633, 4.607).
17. Abstract statement "Black infants' excess ... fell below parity ... even over the child's births" 0.80 (0.66; 0.98) ok but the upper limit is 0.98.

## 4. Claims against the evidence

4.1 "The reversal came almost entirely from Brown mothers' infants certified White" (Abstract). Not supported as worded: the waterfall is path-dependent (flows switched on in one order); the Brown to White flow alone gives +144% of the net change, partly offset; and 18% of the net log change is the no-race exclusion, a separate artefact. Give a Shapley or all-orders decomposition with intervals, and report the no-race effect as its own step. In the Results the verbal description ("remaining flows and the deaths with no race") hides that the last step is larger than Black to Brown and Indigenous steps combined.

4.2 "Classified consistently, by the mother or by the child, the children of Brown mothers die more often" (Abstract conclusion). By the child the point estimate is 0.79 with CI 0.58; 1.07 (includes 1); in 4 of 7 cause/age strata the CI includes 1; it also excludes the error of the 2010 flows (survivors classified by a household respondent, applied to 2013-2023 births, no interval). Say "point estimate below 1, compatible with 1". Also the group is "Brown children", not "children of Brown mothers".

4.3 "households also classify as White in similar proportion" (Discussion). Nationally 0.25 vs 0.28 (review 2). Regionally the child's cell is 0.52 in the Northeast and 1.35 in the South: the "return" does not occur where certification of White is more frequent than households would give. This is evidence that part of the reversal is certification practice and place (paper 1), not only the mother/child construct. The Results state the regional spread; the Discussion ignores it and concludes "a property of the rate". Needs a sentence and a regional figure or table of the flows (certificate vs household) per region.

4.4 "held in every year, age and cause" (Abstract): true for the two reversed cells in point estimates; congenital mother's 0.98 shows that in some strata there is no inequality to reverse; no intervals in S1. Say "direction of the difference between the two classifications held in all strata".

4.5 "Black category: ... for a reason other than the mismatch of terms" is a plausible reading, but "the certificate uses the Black category less than households do" is a description, and the other reading is untested: SINASC staff under-record Black mothers (paper 3) and the flows condition on a mother's race that is itself misrecorded. State as undecided.

4.6 "the usual way" not sourced (2).

4.7 Abstract "nationally and in each of 510 immediate regions": the regional work covers White to Brown, mother's vs certified only; no child's denominator, no Black to Brown, no intervals for contrasts. Align objective, title of Figure 3 and Abstract with what was done, or do it.

4.8 Standardisation sentence false for the mother's race (2, 1.5).

4.9 Methods list three sensitivity analyses (deaths with no race given the mother's race; large municipalities; found share by 10 points) and report none for infants in Results or Supplement (S1-S4 contain none). Either print the results or delete the sentence.

## 5. Missing analyses, ranked (feasible with data held)

1. Shapley (all-orders) decomposition of the 0.80 to 1.31 change plus no-race as a separate step, with jackknife or bootstrap intervals; by region (flows by region exist). Feasible, small. Directly repairs 4.1.
2. Flow comparison certificate vs household by region (and state): "implied certifier flow" against the census flow; the South case shows where the child's denominator fails. Separates construct from certification practice, the central question. Feasible (census by region and linked flows in hand).
3. Census flow uncertainty: propagate the census sample error and 2010 vs 2022 flows (2022 census age-0 race, 2000) into the child's cell; show how much of 0.79 (0.58; 1.07) moves. Feasible.
4. Bounds/tipping point for unlinked deaths (19.5%; 38% Indigenous) and no-race certificates: all unlinked Brown / all White; ratios of the 2 x 2 under both. Feasible, cheap.
5. Adjusted national ratios (maternal schooling, age, birth weight, prematurity from SINASC on linked records; state-year fixed effects): the mother's-race ratio is crude; test whether it persists within strata. Feasible for the linked cell (not the certified).
6. Black to Brown regionally and by state, and the child's cell by state (27 rows, no model). Feasible.
7. Official comparator (Ministry's published series) as external check of the 1.31 and 0.49. Feasible by hand or via the Painel; not in hand locally.
8. Sensitivity of the Black to Brown mother's ratio to the mother's race misrecording measured in paper 3 (net flow 0.74). Feasible.
9. Joint regional model (multinomial of certified class given mother's class by region) or raw regional ratios for regions with at least 20 White deaths; prior sensitivity; exceedance probabilities. Feasible; moderate effort.
10. Mother's-race infant ratio by place/type of death (hospital vs home) and certifier type: tests whether the flow depends on who certifies (paper 1 overlap; keep to a sentence).

The data were not used to their full extent: the linked records carry schooling, age, birth weight, gestational age, plurality, place and type of birth and death, none of which enter the 2 x 2.

## 6. Figures (guide sections 2, 5, 6, 7; 175 mm, 300 dpi; all PNGs are 300 dpi)

Figure 1 (`flow_infants`, 2066x992 px = 175 mm at ~300 dpi, text about 8-9 pt: legible). Problems: shared with paper 1, so the "place" box lists variables paper 2 does not use (GDP, schooling, urbanisation, physicians, certifying physician, race left blank, establishments) and the arrow "by residence and occurrence" is unexplained; the census box has no arrow and its text ("how households report other, surviving children") is cryptic; the 2 x 2 design the paper rests on is not drawn; counts missing for births (SINASC 2012-2023 total), census flows. The linked boxes' numbers are right. Replace the place box by "Census flows" and a 2 x 2 schema.

Figure 2 (`indicators_decomposition`, 2148x1029): panel A: four colours on a log axis, intervals visible, the grey fourth cell (0.49/1.89) is never discussed in the text; panel B: a connected line across categorical steps implies continuity, no intervals, single order of switching, 8 rotated 45-degree labels that use a third of the panel height (only 8 ~7 pt labels): replace with a waterfall or dot plot with Shapley bars; two series in yellow and black, ok for colour-blindness but the black Black line dominates; panel C: blue and green overlap and jitter at the same x, green intervals cross 1 in most years (honest, but then the text "returns to the mother's" is not visible as such); axis labels ok. Legend is at the bottom outside the panels, good. The abstract's 11.0/13.6 rates and the 44,851 deaths appear in Table 1 only; the rates in the Abstract (11.0/13.6) are in no item with that value (Table 1 note says 11.0/13.6, Results text 10.8/13.5).

Figure 3 (`regional_ratios`, 1846x1970): no no-data class needed (510/510), but (i) colour scale of A and B is censored at 4 though the certified ratio reaches 10.3 (B is saturated brown over the whole North and most of the Northeast; C saturates at 3 while D shows 12.6), so the one place where the indicator fails most cannot be read; (ii) map A is nearly white: it shows the prior, not data, and occupies a quarter of the main figure; (iii) region borders in white lines at this scale are barely visible, state borders black are fine; (iv) panel D: legend "mean by class of composition" overlaps the x-axis zone and is cut by the axis start; the line is a mean in four classes drawn as a smooth line with no intervals, and its rise above 35% White is not supported (class means 1.92, 1.83, 2.19); colourbar for GDP is jammed against the axes; (v) panel C and D largely repeat paper 1. The display plan's claim "most where few births are White" is supported by D only for the extreme left.

Supplementary Figure S1 (`regional_ratios_1to9`): intervals present for the mother's series, family's and certified series with no interval and a legend that says so; "n.e." entries for North 1-4 and three 5-9 panels leave the main contrast absent where it matters; the axis (0.25 to 4) is not log labelled at the ends (axis starts near 0.1 unlabeled). Acceptable as supplement; the 1-9 estimates should not carry the weight of the infant ones.

Display plan: items 1-4 are present, but the plan's "Figure 2C gained yearly jackknife intervals" is true only in the .docx; txt/PDF stale. Every Abstract number is in a main item except 11.0 and 13.6 (conflict above).

## 7. Minor

- The pre-1h "Ilhéus ¿ Itabuna" encoding error persists in Supplementary Table S2 and in the build data.
- Table 1 has no deaths and births per cell; add n.
- "Reversal", "ratio of ratios", "misstated" are used for the same object; define once.
- "Mother's race" and "certified race" should read "birth-record (mother's) race" and "certificate (child's) race" throughout.
- Methods mention a modelled census-based population and a family's classification "reported in the supplement" (S2, S3) but the Abstract no longer uses them: keep the supplement short or drop.
- 2013-2024 deaths vs 2012-2023 births: state the period/cohort mismatch for infants.
- Number of verbal claims asserted in `text.py` is good; add asserts for "almost entirely" and "returned".
- The Black to Brown ratio is reported without the Brown-to-Black and Black-to-Brown flows by region; one table suffices.
- RECORD checklist: confirm it is filed.

## 8. Top five required changes

1. Reconcile the rates: one set (10.8/13.5) in Abstract, Table 1 note and Results; recompute the ratio from the same rates.
2. Replace the single-order waterfall by an all-orders (Shapley) decomposition with intervals, report the no-race exclusion as its own step, and correct "from 1.15 to 0.57" (it is 1.37 to 0.57); drop "almost entirely" unless the decomposition supports it.
3. Reword the child's-race conclusion ("point estimate below 1, interval 0.58; 1.07") and account for the South (1.35) and Northeast (0.52): compare certificate and household flows by region and say what share of the reversal is construct vs certification practice.
4. Align the objective with the work (510 regions: 2 x 2 and Black to Brown not done, no intervals for the contrast) or add them; fix the false standardisation sentence; print or delete the three sensitivity analyses; add bounds for unlinked/no-race deaths and census-flow uncertainty.
5. Fix the figures: Figure 1 (remove place box, draw the 2 x 2 and census flows), Figure 2B (waterfall with intervals, lower label burden), Figure 3 (uncensored or labelled scales for B and C, drop or shrink map A, fix D legend overlap and the unsupported smooth line), rebuild the txt/PDF so the caption and text match the .docx.

**Verdict: major revision.**
