# Response to review 2 - paper 2, `indicators/`

New analysis: `analysis/indicators2.py`, with output `results/indicators2.json`, and the figure `figures_indicators.py`.

| Review item | Done |
|---|---|
| Top 1: mother's race against child's race | Done. The paper is rebuilt on the 2 x 2: numerator by the mother's race or certified, denominator by the mother's race or by the child's (households' flows). White to Brown: 0.80, 1.31 and 0.79 (certified over the child's births). Black to Brown: 1.15, 0.49 and 0.80. The waterfall: Brown to White takes the ratio 0.80 to 1.61, White to Brown brings it to 1.28, and the child's births bring it to 0.79. The title, abstract and conclusion now name the mismatch. |
| Top 2: intervals; Indigenous scale | Every 2 x 2 ratio has a delete-one-state jackknife; the certified White to Brown ratio has SE 0.076, against 0.005 from Poisson. Linked deaths are scaled by certified race; Indigenous scale 1.63, mother's ratio 1.96 (was 1.60). |
| Top 3: region-standardised | Mantel-Haenszel over regions: 0.87, 1.66 and 0.81. |
| Top 4: neonatal, cause, years, Ministry indicator | Age, cause and year are in Supplementary Table S1 and Figure 1C; the reversal holds in every stratum (asserted). Not done: the Ministry's published series; the text calls the usual computation "the usual way" and does not claim it is the Ministry's. |
| Top 5: regional layer | The joint flow model is not fitted. The text reports credible counts per model only, drops the ratio-of-ratios credibility counts, says the mother's-race map is mostly the prior, and gives the regional 2 x 2. The census-based 0.94 has left the Abstract for Supplementary Table S3. |
| 1.3 "Brown children" | Now "children of Brown mothers". |
| 3.9 absolute measures | Excess deaths: 44,851 (Brown) and 8,543 (Black) by the mother's race, against deficits on the usual indicator. |
| 5.6 primary | The paper is declared descriptive. |
