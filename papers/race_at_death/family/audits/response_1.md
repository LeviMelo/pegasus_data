# Response to review 1 - paper 4, `family/`

New analysis is in `analysis/family.py` (section "review 1", key `review1` in `results/family.json`), run on `pairs2_*.parquet`. That pairing re-run of `data/probes/census2022/pairs.py` adds the informant's, the partner's and the mother's own informant order numbers, and the order-number agreement. The paper's reading changed: the child's race follows the father and the person answering, not a household rule.

| Item | Done |
|---|---|
| E1 interaction "concentrated with White" | Corrected: the rise is with White (0.15, SE 0.01) and Black partners (0.18, SE 0.02), not with no partner (0.03). |
| E2 coverage 88% | Now 0-9 by mother's race: 82% Brown and Black, 84% White. |
| E3 rule validated only in one cell | Pair-level agreement: the order number points at the couple's woman for 99.8% of pairs. Black mothers' children reported Black: 0.476 by the rule against 0.483 by the order number, stated. The text says the rule cannot be checked in 2022. |
| E4 selection quantity | Figure 5C now shows the share of children in the pairs (child of the couple, with the mother), not co-residence. The Discussion no longer claims selection is excluded. |
| E5 "same children darker" | Removed. The pseudo-cohort difference (+0.07) is about half the 2010 cross-sectional gradient (+0.12), and the text says age and cohort cannot be separated. |
| E6 informant average | Replaced by who answered within the couple. When a White partner answered, a Brown mother's child was reported White in 0.65, against 0.57 when the mother answered. Black mother and White partner: 0.49 against 0.40. With a Black partner, Black 0.80 against 0.76; with a Brown partner, 0.17 against 0.20. Selection of who answers is stated. |
| E7 partial 2000 cohort | Cohort 2000 is excluded at the 2000 Census, in the text, the figure and Supplementary Text S1. |
| E8 reference [9] | Removed. The series is described as the population account (Supplementary Text S1). |
| E9, E5 citations | carvalho2004 is now cited only for "reclassification between censuses has been described". marteleto2012 is dropped. The "toward Brown and Black" direction is now carried by freemannc2024 (adults' identification). |
| E10 mother's own informant | Computed: the mother answered for herself in 72% of pairs, the partner in 21%. |
| E11 drift | 2022 reweighted to the 2010 mothers' instruction and region. Brown mothers' children reported White: 0.198, against 0.210 (2010) and 0.215 (2022), so the rise becomes a fall. Black mothers' schooling profile is reported. The abstract and conclusion now say the changes depend on who the mothers are. |
| E12 informant base | Now the 0-14 base, with the partner separated (65 / 25 / 4 / 4%). |
| Father vs stepfather (rival 1) | Done (Figure 3A-B, text). White against Brown father: 0.56 against 0.11 (2010), 0.61 against 0.12 (2022). White stepfather: 0.30-0.39, against 0.15-0.16 for a Brown stepfather. The rise holds among fathers. |
| Sibling discordance | Done (Figure 3C). Brown mother with White partner: 42% / 41% of households. Brown couples: 16% / 15%. White couples: 4%. |
| Precision | Table S1 and the 0-4 text use three decimals. The text says the intervals reflect sampling only. |
| Claims (section 6) | Reworded. "decided" is gone. "follows the couple, mostly the father". "complete samples" is now "public-access samples". "valid in both" is now "applicable in both, checked in 2010". The priority claim is now "we found no study". "runs against" is removed. |
| Not done | Survey GLM refit (svyglm). Conditional logit with household effects. Imputation flags (M0606, MP0210). Analysis of the excluded 18% (grandchild relation). Yellow and Indigenous mothers, named as a limitation. Single-year ages of 2010. The 2000-Census child pseudo-cohort. |
