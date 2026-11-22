# Verification of response_6 - paper 1, place

## Verified in manuscript.txt and recomputed (results/panel_long.json, panel.json, mechanism.json, data/spatial/laplace.json, spatial.json)
- Item 1, long panel: "On this outcome a certificate fixed in each place predicts -1 and one that follows the census predicts 0: the interval excludes full following and includes a fixed certificate." Within -0.6486 (SE 0.2634) gives (-1.165; -0.132); between -0.540; within SD 0.068 against 0.976; lead model -0.33 (0.58) and lead -0.54 (1.10); 2000-2010 -0.23 (2.22). All match. "Followed the census population" is gone. Fig 5D has "follows" (0) and "fixed" (-1) reference lines.
- Item 2: verification-service share within municipality +0.614 (SE 0.198) gives (0.23; 1.00); within immediate regions 0.846 (0.265) gives (0.33; 1.37); blanks -1.446 (0.198). GDP 0.029 (0.048), physicians -0.039 (0.044). Match. Fig 5C shows all six covariates.
- Item 3: residence 0.32 against 0.42 "not tested ... the contrast is inconclusive"; Table 1 "not settled"; the Discussion no longer weakens the rival on it.
- Item 4: cells -0.84, 0.64, 0.55; even odds 0.579 (0.557; 0.602) printed 58% (56%; 60%). Abstract, Results, Discussion, Table 1 say "partly" and state the 50% prediction.
- Item 5: Laplace refit 0.8685, 0.9121 against nAGQ=0 0.8697, 0.913: "86.8% against 87.0%" and "91.2% against 91.3%" correct. Physician ranking "weakly identified" with 3.7 deaths per physician (82,173/22,103). The "35%" crossing, "a third one" and "unevenly between intermediate regions" for the Black category are absent. The -0.19 sentence reads "a conditional slope; the crude national proportion went from 0.26 to 0.25". Limitation (10) on father/household is present.
- Figures: Fig 1 shows 74,772 unlinked and 12,691 without the mother's race (383,975-309,203 and 309,203-296,512, correct). Fig 3A title carries Moran's I 0.77; 3B "variance of the logit field 0.21 of A's" (0.284/1.382 = 0.205, correct).
- Other recomputed values match: 0.45/0.06 (0.446/0.057), regions 0.51/0.05, reliability 0.59 (41% noise) and 0.94, 11% (0.053/0.943/0.514), share died elsewhere 0.462.

## Failing - fixes required
1. **Unrendered template in the Results (manuscript.txt line 61):** "({pct(OCC['share_elsewhere'], 0)} of linked deaths)" is printed literally. The string in place/text_results.py that begins "the local majority only partly. Of the infants who died outside ..." lacks the `f` prefix. Add it (the value is 46%), rebuild, and grep txt and docx for "{".
2. **"Three panel designs ... far less than between them" is not true of the long panel.** Abstract ("within places it moved with composition far less than between them, in three panel designs"), Results ("The three designs agree that within places the certificate moved with composition much less than between places"), Discussion ("small in all three") and Table 1. In the long panel the within estimate (-0.65) is as large as the between (-0.54), and Fig 5D draws them that way; by its own benchmark -0.65 is 35% of the way from fixed (-1) to following (0), with SE 0.26. Restrict the claim to the yearly panel and the census decade, and say the long panel does not discriminate.

## New or residual problems (minor)
- The Abstract's "context 60%" in the multilevel models (socioeconomic plus services, 0.596) appears nowhere in the Results, which give 55% and 43% separately. Report 60% in the Results or use 55% and 43% in the Abstract.
- The medical-examiner share was significant within immediate regions (-0.30, SE 0.149; CI -0.60; -0.01). Review 6 asked for it; the text reports only verification service and blanks, and Table 1 "within places, wealth and physicians nothing" is silent on it. Add one clause (Fig 5C shows it).
- "Over the census decade it moved about a third as far" is 0.29/1.01 = 0.29: say "under a third".
- display_plan.md is stale: it still says Moran's I 0.77 is the "none" point of 4B and "5 times" lies between maps; both are now in the Fig 3A/3B titles. The 58% and the 46% are in no main figure (58% is in Table 1).
- Acknowledged as not done: intervals for Fig 4B/4D, equalised-noise test, linkage weights; the "5 times" ratio has no interval.

## Verdict
FAIL until fixes 1 (build defect) and 2 (overstated claim) are made. Everything else claimed done is present and correct.
