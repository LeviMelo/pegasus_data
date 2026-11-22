# Response to audit report 4

## Errors

| point | action |
|---|---|
| E1 infant ratio estimator | The infant White to Brown ratio by mother's race is now computed from the linked pairs alone, with a delete-one-state jackknife: 0.81 (0.78-0.84). The candidate estimator's 0.79 carries its own jackknife (SE 0.034 against 0.023 Poisson). The Abstract and Discussion use the linkage figure; Methods say the regional ratios use the linkage. The Indigenous ratio is not taken from the linkage (62% linked against 80-81%). |
| E2 case mix | Refitted without the macro-region: the deaths' own variables explain none of the municipal variance (-1% for Brown mothers' infants certified White, -1% for Black). The text says the earlier 74% belonged to the macro-region; the rescaling caveat of logistic variance (Merlo) is stated. |
| E3 census-based denominator | Methods and Supplementary Text S3 state how the account assigns race to children born after 2010 (their cohort's 2022 Census shares carried back by the state's reclassification rate, per ADR-0151); the dangling citation in the supplement is replaced by plain text. |
| E4 wording | Title is now "Race on the death certificate and place"; "same child" counterfactuals removed; the rival explanation (the Brown category differs between regions; an observer classifying by appearance would produce the gradient) is named in the Discussion and limitation (5); the Conclusion says the certificate's relation to the other two depends on place; Implications say linkage removes the certificate's dependence on place, not the birth record's. |
| E5 continuous surface | Removed. |

## Points

P1: "lower bound" became "attenuated"; the within-state comparison of neighbours is reported (0.56 across against 0.49 within, log-odds squared); the Abstract gives the slope. P2: the multilevel sentence removed from the borders argument. P3: Abstract and Discussion name the ages (infants against 0-9) and limitation (1) says the census mother's race is the household's report. P4: "misstates" is now "changes, relative to the mother's race"; regional ratios refitted with INLA linear combinations (credible counts 159, 446, 115; 469 with the certified ratio credibly higher, now reported); all four classes of the U printed; the high end explained (Brown deaths leave the Brown numerator) and the shrinkage of the low end named. P5: the census-composition claim narrowed to the municipal models of infants. P6: GDP tested with the composition spline: odds ratio per doubling 1.06 (1.04-1.08), 0.97 (0.95-0.99) with the state; parallel cells in the after-infancy paragraph; the 15-24 natural-death wealth gradient reported with its error. P7: linkage threshold (17.9-18.9 bits), estimated false links (0.57-0.75% a year), agreement on delivery type and plurality, per year in Supplementary Table S11; per-step flows after infancy still not done. P8: the 1,600-birth restriction is next to the 15-24 figures in the Abstract. P9: the JSON key renamed (`full_fit`); AIC differences called approximate. P10: the t-sensitivity range printed.

## Minor

Figure 4E drawn without the binomial bars; Figure 3C scale widened to ±0.45; the negative zero removed; Supplementary Table S15 note says thirds weighted by linked deaths; "agreed with neither" became "departed from both"; Roth, Freeman and Penner now cited for what their abstracts say (reading report, Task C); Saperstein 2010 supported by its abstract; Keele and Titiunik cited for the logic. Supplementary items remain out of citation order (not done).
