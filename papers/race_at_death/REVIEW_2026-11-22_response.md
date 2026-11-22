# Response to the review of 2026-11-22

Each point below is marked done (with where) or not done (with the reason). The analyses were run on the working tree of 2026-11-22:
- new scripts: `analysis/category_test.py`, `birth_vs_census.py`, `hospital_declaration.py`, `violence_place.py`;
- new modes: `indicators2.py review3` and `estimator.py byage`;
- census 2022 table 9606, fetched by pegasus_data into `data/census2022_women_15_49_race.parquet`.

Every number cited below is interpolated in the manuscripts from these results files.

## Section 4, the two tests first

**Test C: is the Brown category the same population everywhere?** Done, in `results/category_test.json`.

In the 2010 Census sample, children aged 0-9 of a Brown mother and a Brown father were reported White more often in whiter municipalities:
- 0.09 where under 10% of births were White;
- 0.14 where 90% or more were;
- most of the rise below 30%.

On the logit scale the slope was 0.16 (SE 0.006), or 0.16 with age, sex and schooling held. The certificate's slope on the same axis was 0.66. Families therefore account for a quarter of the certificate's gradient at most.

For all Brown mothers, the family's gradient (0.15 to 0.36) is about half partner mix and half the rate within couple type.

Where the results went:
- Paper 1: readings table, row "The Brown category differs between regions", now "weakened: a small part at most". The result is in Results, "The family and the birth record against place", and Figure 6A.
- Paper 4: section "Place" and Figure 6A.

**Test B: does the birth record bend toward the local majority?** Done, in `results/birth_vs_census.json`. It does.

| Comparison | Logit slope (1 = follows the census) | Within region | Within state |
|---|---|---|---|
| Birth records 2012-2013 vs census 2010 mothers of children aged 0-2 (mothers against mothers, so fertility cannot explain it) | 1.46 | 1.13 | 1.12 |
| Birth records 2021-2023 vs census 2022 women aged 15-49 | 1.52 | 1.29 | 1.33 |

Sampling error in the census would flatten the slope, not steepen it, so these are lower bounds.

Where the result went:
- Paper 1: limitation (3) became a result (Figure 6B and a new readings row). Against self-declaration, the certificate's place dependence is understated, not overstated.
- Paper 3: point 3.2 below.

## Section 2

**A. The reference is unstable.**
- Paper 2: done. The off-diagonal cells of the 3 × 3 repeat matrix were recovered from the published diagonal (0.75, 0.52, 0.87) by row sums and reversibility. The misclassification of one declaration was taken as its matrix square root, and deaths and births were corrected alike.
  - Black to Brown: 1.12 observed, 1.16 corrected.
  - White to Brown: 0.77 observed, 0.72 corrected.
  - Black and Brown together against White: 1.32.
  - Reported in the Discussion. The instability dilutes the Black excess; it does not create it.
- Papers 1 and 3: see 3.1.

**B.** Done; this is test B above.

**C.** Done; this is test C above.

**D. Space in papers 3, 4 and 5.** Done, as a new main figure in each:
- Paper 3, Figure 6: practice by state and the birth record's shortfall.
- Paper 4, Figure 6: municipal gradient of fixed couple types, and states in 2010 against 2022.
- Paper 5, Figure 4: the cause contrast by composition of the place of occurrence and by place of death.

**E. References.**
- Paper 4: done, 7 → 15 references (quota law; Francis & Tannuri-Pianto 2012, 2013; Francis-Tan & Tannuri-Pianto 2015; Bailey et al. 2018; Freeman 2025; Tomás 2025; Travassos 2011).
- Paper 5: done, 8 → 13 (Santos 2013 and Rodrigues 2012 on medico-legal assignment of race; Melo 2013; Romero 2019; Aiquoc 2022).
- Each reference was found and its abstract read; the record is `references/candidates_2026-11-22.md`. Rodrigues 2012 is partly verified: Crossref gives a single page number.

**F. Overlap.** The one-page map is `RESULT_MAP.md`. The papers already name their companions where they lean on them; no paper was merged or dropped.

**G. Process text.** Done. The Crossref sentence is gone from paper 6 (see 6.1).

## Paper 1, place

- **1.1** Done (test C).
- **1.2** Done (test B).
- **1.3** Done. 7,780 → 4,594 words from Introduction to Conclusion, counting the build's paragraphs; about 5,150 with the text of Table 1:

  | Section | Words |
  |---|---|
  | Introduction | 488 |
  | Methods | 1,017 |
  | Results (with captions) | 2,202 |
  | Discussion | 1,136 |

  Where the detail went:
  - "Time and place" is one paragraph; its detail is in Supplementary Text S3.
  - The method details are in Text S2.
  - The detailed results paragraphs are in Text S4.
- **1.4** Done. The title names infants (2013-2023). The 1-9 years analysis is one sentence in Results and lives in the supplement.
- **1.5** Done. The Results of the abstract are four findings.
- **1.6** Done. The abstract and the conclusion now give the establishment variance (0.29 against 0.03 for the municipality) and the certifying physician.
- **1.7** Done.
  - Figure 4A: the legend moved below the panel.
  - Figure 1: the census box now feeds the linked deaths, as the family's classification and the birth record's reference.

## Paper 2, indicators

- **2.1** Done. The linked share is 76% in the North and 89% in the South, 87% of neonatal and 65% of later deaths. Deaths are now scaled within certified race × region × neonatal or later × year, and this is the main analysis because the estimates moved:

  | Estimate | Old scaling | Post-stratified |
  |---|---|---|
  | White to Brown, by the mother's race | 0.805 | 0.766 |
  | Black to Brown | 1.146 | 1.116 |
  | Excess deaths of Brown mothers' infants | 44,851 | 55,127 |

  The coarser scaling is reported as a sensitivity.
- **2.2** Done. The paper's "usual" computation (certified deaths over births by the mother's race) gives an Indigenous to White ratio of 1.81 for 2017. Caldas, Santos and Cardoso (Cad Saude Publica 2022;38(4):e00101721) published 1.81 (95%CI 1.67; 1.96) from the same systems by the same computation. Cited in the Results, and asserted in the build.
- **2.3** Done. The abstract gives the region-standardised ratio, 0.86. Excess deaths within regions are 29,448, against 55,127 at the national rate.
- **2.4** Done. Births with no race were 4.1% of births in 2013, 1.8% in 2023 and 3.3% overall. Distributed proportionally they would lower every rate by that share and leave the ratios unchanged.
- **2.5** Done (see A).
- **2.6** Done. Figure 3A is now the 510 regions ranked with 95% credible intervals, coloured by macro-region, instead of a map of the prior.

## Paper 3, Black category

- **3.1** Done.
  - The ladder (Figure 2) shows four levels, each named for what it is:

    | Level | Recorded Black |
    |---|---|
    | The mother herself at her next birth | 0.52 |
    | The family: child under 1 / aged 1-4 | 0.39 / 0.47 |
    | The hospital: the mother at delivery | 0.36 |
    | The certificate: the infant | 0.18 |

  - The mother's declaration at this birth is a dotted line at 1, not a bar.
  - The abstract opens on the four levels, and the conclusion and a Discussion paragraph read each record against its comparator.
  - The title is kept: "recorded as Brown" describes the certificate against the family.
- **3.2** Done.
  - Who fills each form is stated from the birth-record manual.
  - In the fifth of hospitals with the lowest admission practice, 5.2% of mothers were Black on the birth record, against 10.9% expected from their municipalities' women in the 2022 Census. In the top fifth, 9.3% against 9.6%. The slope is 0.21 with schooling held, and 0.00 within states.
  - So the birth record's shortfall follows the state's practice, not each hospital's. There, the "declaration" is partly the institution's.
- **3.3** Done. Figure 6A gives practice by state with bootstrap intervals over hospitals:
  - lowest: AC 0.04, AL 0.04;
  - highest: RS 0.59, SC 0.63.
- **3.4** Done. Public-system deliveries were 60% of births in 2021:
  - 26% of births to mothers with 12 or more years of schooling;
  - 47% of White mothers' births;
  - 68% of Black mothers' births.

## Paper 4, family

- **4.1** Done. In 2010 the municipal gradient is small for every fixed couple type:
  - two Brown parents, child White: 0.09 to 0.14;
  - two White parents, child Brown: 0.09 to 0.005;
  - two Black parents, child Black: 0.76 to 0.81.

  The states kept their order between 2010 and 2022 (Figure 6).
- **4.2** Done. The claim of symmetry is withdrawn. A log-linear model of the nine couple types (children aged 0-9 of both members of the couple) gives, as log-odds:

  | Term | 2010 | 2022 |
  |---|---|---|
  | Taking the mother's class | 1.52 | 1.48 |
  | Taking the father's class | 1.41 | 1.40 |
  | Mother minus father | 0.12 (0.11; 0.12) | 0.07 |
  | Pull toward White over Brown | 0.29 | 0.36 |
  | Pull away from Black | −1.57 | −1.43 |

  These are reported as odds ratios in the abstract and Results. The old "about alike" assert is replaced by asserts on these terms.
- **4.3** Done. Table 1 has two columns of odds ratios, one per outcome, with labelled rows grouped by variable and the references named.
- **4.4** Done. The sex and age findings are discussed with Travassos 2011 and Francis & Tannuri-Pianto 2013, and stated as associations of the report, not of appearance.
- **4.5** Done. The quota law (Lei 12.711/2012) is discussed with the literature on declarations after quotas. The census changes among children reaching 10-17 years fit that incentive; the data cannot test it.

## Paper 5, violence

- **5.1** Done (Figure 4; Supplementary Table S3). The assault minus natural shift:
  - died in the municipality of residence: −12.9 points (−16.9; −9.1);
  - standardised to the composition of the place of occurrence: −14.0 (−17.1; −11.0);
  - all deaths found: −11.5.

  The contrast is a finding about the death.
- **5.2** Done. The place of death is the informant proxy. Natural deaths were in hospital in 82% of cases, assaults in 17%. The assault minus natural shift was −5.8 points (−11.2; −0.4) within hospital deaths and −10.3 out of hospital. Part of the contrast goes with the place of death, and part remains.
- **5.3** Done. In paper 6's validation, the share of each declared class sharing the key was 0.91 (White), 0.90 (Black) and 0.88 (Brown). That raises the share White at birth among those found by about a point for every cause alike. It would bias the cause contrast only if it differed between causes by more than the contrast, which is untestable (Limitations).
- **5.4** Done. Natural causes are defined once. Signed percentage points no longer print "-0", in tables or text. A sentence that read "fell by +4.3" now reads "fell by 4.3", with an assert that the shifts are negative.
- **5.5** Done.
  - Natural deaths at these ages: neoplasms 16%, nervous system 14%, ill-defined 11%, infectious 11%, circulatory 10%.
  - Against transport deaths, assaults shifted alike from birth to the certificate: −0.6 points (−3.6; 2.7).
  - From the earlier hospital record to the certificate, assaults changed about 6 points more than transport deaths.
  - The paper now says the contrast is external against natural, not homicide against the other external causes.

## Paper 6, estimator

- **6.1** Done, partly.
  - The paper is Chipperfield, Bishop and Campbell, Survey Methodology 2011;37(1):13-24 (Statistics Canada 12-001-X201100111444). The earlier text named the authors wrongly.
  - Statistics Canada answers automated clients with a bot check: the in-app browser and curl with a browser User-Agent both got 403 on the catalogue page and the PDF. It was not bypassed.
  - The method is described from Chipperfield & Chambers (J Off Stat 2015), read in full: EM maximum likelihood from formed record pairs, with a match-probability model estimated from a clerical sample.
  - The Discussion says precisely why it cannot run on the same units (no pairs and no match model when a key is shared). The Crossref sentence is removed.
  - Not done: the 2011 text was not read at its publisher, for the reason above.
- **6.2** Done (Supplementary Table S9). By age at death, the admissions' estimate on the linked units against its target:

  | Age at death | Mean absolute difference | Cells outside the model interval (of 20) |
  |---|---|---|
  | under 1 | 0.0042 | 0 |
  | 1-4 | 0.0015 | 0 |
  | 5-14 | 0.0011 | 0 |
  | 15-24 | 0.0016 | 0 |
  | 25-59 | 0.0011 | 1 |
  | 60+ | 0.0016 | 2 |

  This validates hospital deaths at 1-14 years, not deaths outside hospital at those ages.
- **6.3** Done (Figure 2D). Accuracy against the expected chance candidates per unit, for infants by size, admissions by size and admissions by age: the mean difference stays under 0.007 below about one chance candidate per unit and rises to 0.02-0.10 above it. The abstract, Results and Conclusions define the domain by that quantity.
- **6.4** Done.
  - The abstract is 387 words.
  - The main text has one validation table (Table 1), the design, validation and simulation figures, and no long tables. Former Tables 2-4 are Supplementary Tables S6-S8.

## Not done, and why

- Reading Chipperfield et al. 2011 at its publisher: blocked by a bot check, see 6.1.
- Abstract lengths: papers 2-4 run 436-514 words. Journal limits are the author's decision, so the abstracts were not cut to a limit.
- Whether six papers go out, and where: the author's decision. `RESULT_MAP.md` prepares it.

A separate Sonnet verifier checked every point against the built text and the results files. It found three defects in paper 5 (fixed above) and a text-export encoding problem (all twelve exports are now UTF-8).
