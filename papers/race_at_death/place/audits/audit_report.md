# Audit report: race at death vs race declared at birth (manuscript.txt, supplement.txt, figures)

Auditor read: conventions.md, failure-modes.md, manuscript.txt, supplement.txt, build.py, results.json, fig1-3.png.
Severity: error / should fix / minor. JSON paths are relative to results/results.json.

## A. Errors

1. **error** "The proportion White fell in every cohort born from 1940 to 2009 between successive censuses (Table 4)."
   False in the data: cohort 1940 has White 54.8% (2010) and 54.9% (2022), a rise (`cohorts`, cohort 1940, years 2010 and 2022: 0.5477 vs 0.5490). The sentence is hand-typed in build.py (line 326-327), not generated. Table 4 shows only 6 of the 14 cohorts, so the reader cannot check it either.
   Fix: compute the statement from `cohorts` (assert), or restrict it to the cohorts shown ("in each of the six cohorts in Table 4"), or put all 14 cohorts in a supplementary table.

2. **error** Supplementary Table S4 note: "Not estimable: standard error of 1 or more."
   For the White column the code (build.py line 454) prints "not estimable" for every "large" row, whatever the SE. The SEs in `kinds.*.large."Branca stays".se` are 0.42, 0.40, 0.30 and 0.17 (all below 1). The estimates are 1.39, 1.51, -0.21 and -0.35, outside [0,1]. The Black column does use SE<1, so the note is true only there.
   Fix: state the real rule ("estimate outside 0-1") for White, apply one rule in code, and say in Results that the estimates were impossible values.

3. **error** Abstract Methods: "...estimate deaths by declared and certified race in municipalities of any size."
   Supplementary Table S2 contradicts this. In the 25,600+ class, deceased found is 114.9% (`validation.rows[>=25,600].found` = 1.149, impossible). The White estimate is 0.42 against 0.64 by linkage. At 1-4 years White is 4.14 (95%CI 0.96; 7.32) and the Branca>Parda cell is -1.75 (`children.1-4.by_size[>=25,600].moves."Branca>Parda".est`). Supplementary Text S1 says the control cures t>1, but it does not in this class.
   Fix: say that the estimator was valid up to 25,599 births per year and failed above; reword the abstract and the Discussion sentence "to every size of municipality" (see 13).

4. **error** Table 2 "all" row Deaths = 60,145, against the title n=60,146, the abstract and text "60,146 deaths", and Figure 2.
   The class rows sum to 60,145 (13,703+16,265+13,473+9,148+7,556). `children.1-4.deaths` = 60,146. The same 60,145 is in Supplementary Table S2. One death is unexplained.
   Fix: state the one death excluded (no size class) or use one figure everywhere.

5. **error** Figure 3 and Table 3 titles: "Certified race of people recorded as White at birth who died at 15-24 years ... (n=80,526)".
   80,526 is the sum of all deaths in the four cause groups, whatever the race at birth (`kinds.*.small.deaths`). It is not the number of people recorded as White. The figure population is therefore mis-stated (convention: one population per figure, matching the text).
   Fix: give the estimated deaths among people recorded as White at birth (Table 3 should carry that column too), or state "among all N deaths".

6. **error** Discussion: "cohorts whose birth record carries the mother's declaration reach age 15 from 2026."
   Methods use births from 2012 onward (2011 not used). The first such cohort reaches age 15 in 2027.
   Fix: "from 2027".

7. **error** Participants (3): "Deaths at 15 to 24 years in 2014 to 2024 of people born from 2000 to 2010" (also Table 3 and Figure 3 "2014-2024").
   By exact age this is impossible. People born in 2000 are 15 in 2015, and people born in 2010 reach 15 in 2025, after the last death year. The age is probably computed as the difference of calendar years, which Methods never say.
   Fix: state how age was computed and give the correct periods (probably deaths 2015-2024 of people born 2000-2009). If age is approximate, say so.

## B. Should fix

8. **should fix** Abstract Conclusion / Discussion: "a direction that depends on age and on the cause of death".
   Age is never varied on a common basis. Children use the mother's race as reference and all municipality sizes. Youths use the newborn's colour on the pre-2011 form and only municipalities under 1,600 births. The age contrast is confounded with the reference classification. Results `kinds_5_14` (natural, assault at 5-14) exists but is not used.
   Fix: either bridge the two (use `kinds_5_14`) or drop "depends on age".

9. **should fix** Objective: "from infancy to age 24, and what that departure does to mortality rates by race".
   Ages 10-14 are not covered (Participants: 1-9 and 15-24). Mortality rate ratios exist only for 1-9 years, none for 15-24. "Does to" reads causally.
   Fix: write "in infancy, ages 1-9 and ages 15-24" in the objective, and use "measure ... and how rates ratios by race differ when computed from certified race", used identically in abstract, Introduction and conclusion.

10. **should fix** "Declared race" is the mother's own race for births from 2012 and the newborn's colour for 2000-2010.
    The abstract and objective ("race declared at birth") never say this. Methods say "taken to carry the mother's own declaration". The competing explanation for the main childhood finding is that the child's race differs from the mother's. It is mentioned only in limitation (5), without a direction, and the abstract and Introduction do not name it.
    Fix: name the construct in the abstract ("the mother's race recorded at birth"). Add the mother-child discordance to the Discussion as an explanation of "lightening" and give its likely direction. Use one term ("race on the birth record", or "declared race" with its definition) in all titles; Table 3 says "colour recorded at birth" while Table 2 says "declared by the mother".

11. **should fix** Certified-race rate ratios (1.43, 0.81, 6.00; 1.21, 1.11, 3.07) have no interval anywhere (abstract, Results, Figure 2, S3).
    The headline claim "reversed the gradient" (0.66 (0.54; 0.81) vs 1.43) compares a ratio with an interval to a ratio without one.
    Fix: give an interval for the certified ratio (Poisson or jackknife) and a ratio of the two ratios with its interval, or soften "reversed".

12. **should fix** The "all" rows pool the unstable 25,600+ class.
    1-4 years "all" White = 0.92 (0.79; 1.05), higher than every class (0.77-0.82), with upper limit above 1. The declared-race deaths come from the same pooling. In the 25,600+ class declared White is only 0.088 of declared deaths against 0.24-0.33 elsewhere (`children.1-4.by_size[...].declared_mix.Branca`). The headline rate ratio 0.66 may be biased. No sensitivity analysis excludes that class.
    Fix: add a sensitivity analysis excluding 25,600+ births (`children.1-4.rate_ratio` recomputed), report it in the Results and Supplement, and say which classes enter "all".

13. **should fix** Discussion: "The childhood findings extend to ages 1 to 9, and to every size of municipality".
    Rate ratios were not computed by municipality size. The largest class is unstable (see 3, 12). Also "what linked records had shown for infants [3,4]": Cardoso 2005 (title: "o que dizem os sistemas nacionais") and Caldas 2017 (census-based rates) compare systems, not linked records.
    Fix: restrict to "in classes below 25,600 births", and rephrase the citation claim to what [3,4] did.

14. **should fix** Proportions with confidence limits outside 0-1: Table 2 (0.77; 1.02; 0.92 (0.79; 1.05)), Supplementary Table S2 (e.g. Indigenous 1.01, 1.03, 1.12, 5.16; White -0.67; 2.98; Indigenous -0.19; 0.46).
    Fix: use limits on the logit scale or truncate at 0 and 1, or suppress cells with an impossible estimate (same rule as S4, see 2).

15. **should fix** Sensitivity analysis announced in Methods has no result: "children whose certificate records a municipality of birth other than the residence (threat: selection of those who did not move)". The result appears nowhere in Results or the Supplement. Limitation (1) only says the certificate's municipality of birth "did not identify movers".
    Fix: report the analysis (or its failure) in Results/Supplement, or delete it from Methods.

16. **should fix** Validation reference and linkage are not described.
    The "one-to-one probabilistic linkage ... used birth weight and maternal age" has no source, builder, rule or accuracy. It covers only 50,545 of 63,379 deaths (79.8%), so estimator and linkage are compared on different populations. A linkage has its own error (Introduction [15]). There is no agreement measure, and Results state no conclusion (estimator minus linkage, e.g. White -0.04 overall, Black +0.08 in 6,400-25,599). The Discussion never mentions the validation result.
    Fix: add the linkage to Methods with source and reference, give differences (estimator minus linkage) with intervals, and discuss the validation (and the failed class) in the Discussion.

17. **should fix** Limitations (1)-(6) mostly lack a direction. Only (4) comes near one ("affects ratios only through differences in earlier mortality"). Missing limitations: assumption that t does not vary by declared race (stated in Methods for the ratios, not tested, not in limitations); validation only for infants (t 0.96) while ages 1-9 have t about 0.75 and 15-24 about 0.5; the 15-24 results apply to municipalities under 1,600 births, which hold 80,526 of 170,775 deaths (47%); the reference at 15-24 is the colour recorded for the newborn; unknown race on the certificate (2,408 of 60,146 deaths at 1-4, 4.0%) and Yellow category dropped from ratios; preliminary 2023-2024 death files; cause-of-death misclassification (ill-defined causes in "natural causes").
    Fix: add each, with direction.

18. **should fix** Discussion limitation (2): "the jackknife gave similar values except for Indigenous children".
    Counts SE vs jackknife SE differ for 5-9 White (0.11 vs 0.07), 5-9 Black (0.29 vs 0.21) and 1-4 Black (0.16 vs 0.13) (`children.5-9.rate_ratio.Branca`). Hand-typed in build.py.
    Fix: "the jackknife gave a smaller standard error for White and Black children and a larger one for Indigenous children".

19. **should fix** Limitation (1): "about seven in ten children" vs 74.9% (1-4) and 73.9% (5-9); "about" also breaks the exact-values rule. At 15-24 deceased found is 0.48-0.63 (`kinds.*.found`) and is not mentioned.
    Fix: give 0.75, 0.74 and 0.49-0.52.

20. **should fix** "children declared Black are mostly certified Brown" (Discussion).
    Observed: 0.54 (0.45; 0.62) in the <400 class and 0.51 (SE 0.087) overall (`children.1-4.by_size[all].moves."Preta>Parda"`). The interval includes 0.5, so "mostly" is not established. "Often certified White" for Brown children (0.31) is also interpretive.
    Fix: give the proportions.

21. **should fix** Discussion para 2: "close to the proportion ... (26.7% ... born in 2000 to 2004)".
    The 2005-2009 cohort gives 1-0.392/0.482=18.6% (`cohorts` 2005, 2022; `cohorts_birth` 2005), not shown. Census declaration, mortality and migration differ from certified race. Only the cohort that fits is used.
    Fix: report both cohorts and say these are not the same quantity.

22. **should fix** Discussion para 2 only cites references already in the Introduction ([3,4,12,5,11,8]). Conventions require other national and international studies, with discrepancies. The same direction (darker for violence) is "agreement" with [12], but [12] found homicide victims classified as Black, not Brown. No Brazilian study of race on SIM by cause is discussed. Add at least 4 new references (race concordance on infant death certificates in the US/Brazil; Brazilian SINASC-SIM linkage studies; cause-specific misclassification).

23. **should fix** Uncited factual claims.
    Introduction para 3: "after the first year of life a death certificate carries no birth weight or maternal data", "can separate individuals only where few children are born on a day", and "but not its agreement with the declaration at birth beyond infancy" (a negative gap needs a search statement). Methods: "the form introduced in 2011" (system change in year X), census tabulations and "official population estimates", ICD-10, the "national linkage of hospital deaths to death certificates" (Supplementary Text S2: system not named). Discussion: "a medical examiner for most external deaths". [14] (Fellegi and Sunter) supports probabilistic linkage only, not "deterministic or probabilistic ... can separate individuals only where few children are born".

24. **should fix** Supplementary item numbering: S2 is cited after S3, S4 and S5. In the text, first citations are Table S1, Text S1, Text S2, Table S3, S4, S5; Table S2 appears only in the Table 1 note (after Results prose) and in Text S1. Failure-modes: "supplementary items numbered in order of first citation".
    Fix: cite S2 in the Validation paragraph or renumber.

25. **should fix** Table 1 and Figure 1 title "n=63,379" while the table omits the 25,600+ class (7,751 deaths) and the figure shows only four classes (n=55,628). The "all" row is in the table, the figure has none.
    Fix: state the population plotted in the title or add the 25,600+ and "all" points.

26. **should fix** Methods gaps (conventions §2):
    - extraction dates per source; whether 2023-2024 deaths are preliminary, with a sensitivity analysis;
    - territorial division source and year;
    - why the size classes are 400, 1,600, 6,400, 25,600 (steps of 4) and why 1,600 was the cut for ages 15-24. The text says White "could not be estimated" above 1,600, so the threshold looks chosen after seeing results; say so;
    - handling of unknown race on the certificate and the Yellow category;
    - the flow from all deaths to each analytic set (Supplementary Text S2: 106,565 -> 19,332 pairs -> 5,579 not reconciled);
    - the Methods entry for the 1,208,430 delivery admissions (Supplementary Text S2, "for comparison") is absent;
    - variance of the estimator is "sum of the counts" (Text S1) but the control is scaled, and the ratio j,j / sum j needs the delta method, not stated.

27. **should fix** "Three readings" (hospital, certificate, declared) has no interval on any figure (n=5,579), is not introduced in the Introduction, is not interpreted in the Discussion (only limitation (6)) and holds a 28.2% mean false-pair share.
    Fix: add intervals and either interpret it in the Discussion or move it wholly to the Supplement.

28. **should fix** Table 4 (birth cohorts) has only 6 of the 14 cohorts used for the claim in item 1. Title lacks n and period; cells hold three percentages separated by " / " (convention: one estimate per cell; unit in header).

29. **should fix** "Generated, not typed": build.py hard-codes claims that depend on results: "fell in every cohort born from 1940 to 2009" (false, item 1), "not estimable above 1,600" (Results, Discussion), "about seven in ten", "jackknife similar except Indigenous", "row of those recorded as Brown agreeing in the larger ones".
    The last is also overstated: Brown certified Brown is 0.62 (large) vs 0.81 (small) for other external causes (`kinds.other external.large."Parda stays"` vs `.small`).

30. **should fix** `results.json` top-level `validation.deaths_all` = 63,769 and `validation.linked` = 52,063 disagree with the rows used in the paper (63,379 and 50,545). Stale or transposed fields in the single source of truth. `kinds_5_14` is unused.

## C. Minor

31. **minor** Title: "linked birth and death records". The estimator avoids individual linkage, and only infants are linked one-to-one. The Methods say "related". It also names no design ("cross-sectional") as the conventions require. Period "2013-2024" vs Table 3 "2014-2024".

32. **minor** Sentence-initial connectors: "As a result, mortality by certified race placed ..." and "Or, among people recorded as White at birth ...". Temporal verbs for a cross-sectional contrast: "the certificate lightens", "reversed the gradient" (abstract, conclusion, Discussion). Use "the ratio by certified race was above 1 where the ratio by declared race was below 1". "Death certificates assign a race" (abstract) is a mechanism word.

33. **minor** Table and figure notes use "a)", "b)" letters without anchors in titles, headers or cells (Table 1 note b; Table 2, 3, 4 note a; all figure notes). Convention: anchors, or per-panel notes without letters. Table 1 and Table 2 notes include "CI: ... interval". The "95%CI" label is repeated in every cell; put it in the header. Notes on Table 1 do not only clarify (location of the 25,600+ class).

34. **minor** Table 1 mixes percentage (found 91.5%) and proportion (0.79) in one table. Table titles name a method ("by the candidate estimator and by one-to-one linkage"). Table 4 title has no n. Supplementary Tables S2, S3, S4 lack n and period in the title (S2: period only in a note). Supplementary Table S5 column header "... Brown" is not standing alone.

35. **minor** Figures: Figure 1 legend order is scrambled (3 columns) and no values are marked although the text quotes them. Figure 3 does not show the Brown-certified-Brown values cited as "(Table 3, Figure 3)". Figure 3 y-axis "Proportion of deaths at 15-24 years" omits the condition ("among those recorded as White at birth"). Figure 2: label 1.05 overlaps the interval. Figure 2 legend names the symbol but not the missing interval for certified ratios.

36. **minor** One term per concept: "estimator" vs "candidate estimator"; "linked" vs "related"; "declared race", "recorded as White at birth", "colour recorded" (Table 3), "race declared by the mother" (Table 2); "deceased found" is an estimate (t), but Results write "the estimator found the deceased among the candidates in 96.3%".

37. **minor** Abstract: "95%CI" undefined at first use in the abstract and body ("confidence interval"); no data period, setting, or n for the 15-24 result. Abstract Results do not name the 15-24 reference as the newborn's colour.

38. **minor** References: [4], [7], [15] lack an article number or pages (e.g. [15] "2019:dyz203"). [2] (Chor and Lima) and [8]-[9] are cited for claims their titles only partly support: "numerator from the death certificate, where race is recorded by a physician or a registrar" ([2]); "cohorts reclassifying toward the Brown and Black categories" ([9]: category definitions, not reclassification). Reference [18] is a landing page; the "cited 2026 Nov 21" date should be a tested one. Keyword "Race Factors" and the other MeSH/DeCS terms are unverified (placeholder).

## D. Checks that found no problem

- **Abstract vs body numbers.** Every abstract number equals the body: validation 0.71/0.65/0.19 and 0.75/0.66/0.20; the three rate ratios by declared and certified race; the two 15-24 proportions. Abstract also matches Table 1 "all", Table 3 "natural", "assault".
- **Table-to-text counts.** Table 1 deaths add to 63,379 with the S2 25,600+ class; Table 3 deaths add to 80,526; S4 sex rows add to the "both sexes" rows; Table 1 and S2 agree.
- **JSON spot-checks (about 40 numbers).** Recomputed intervals match to the printed decimals:
  - `validation.rows[all].stays`: White 0.709 ±1.96*0.0368 -> 0.64; 0.78. Brown 0.60; 0.69. Black 0.15; 0.24.
  - `validation.rows[<400]` and `[6,400-25,599]`: 0.75; 0.83 (0.0190), 0.48; 0.90 (SE 0.1078), 0.16; 0.36 (Black, 0.0507).
  - Linkage values 0.78/0.68/0.16 and 0.72/0.66/0.18.
  - `children.1-4.rate_ratio`: White 0.663 (SE 0.0676) -> 0.54; 0.81 (log scale). Black 1.109 (0.1619) -> 0.83; 1.48. Indigenous 4.605 (0.5917) -> 3.58; 5.92. Certified 1.43, 0.81, 6.00.
  - `children.5-9.rate_ratio`: 0.67 (0.48; 0.93), 1.05 (0.60; 1.82), 2.04 (1.18; 3.51); certified 1.21, 1.11, 3.07.
  - `children.1-4.by_size[<400].moves`: 0.54 (0.45; 0.62) and 0.31 (0.29; 0.33).
  - `kinds.natural.small`, `kinds.transport.small`, `kinds.assault.small`: all White and Brown stays and Branca>Parda values in Table 3 and Results.
  - `kinds.natural.large`/`assault.large` Brown: 0.62 (0.50; 0.74), 0.80 (0.73; 0.88).
  - `triples`: 0.76, 0.77, 0.37; 0.80, 0.71, 0.55; 0.90 and 0.50; S5 grid.
  - Form table: 2.5%, 55.0%, 92.7%; Black 1.6% and 5.5%.
  - Table 4 (6 cohorts) and the birth-record composition 53.4/42.7/2.7.
  - Leave-one-state-out range 0.63-0.70 (`loo_min`, `loo_max`).
  - Rate ratios use SE = max(counts, jackknife) as Methods state (checked for all six ratios).
  - 26.7% = 1-0.391/0.534.
- **Figures vs tables.** Figure 2 labels equal the abstract values; Figure 3 labels equal Table 3. Figure numbering follows first citation: Table 1, Figure 1, Table 2, Figure 2, Table 3, Figure 3, Table 4.
- **Cross-references.** "Supplementary Table S1", "Text S1", "Text S2", "Table S3", "Table S4", "Table S5" point to the right items (S2 order: see 24).
- **Objective wording.** The abstract, the last Introduction paragraph and the conclusion carry the same words (see 9 for content).
- **Language.** No "respectively", "moreover", "however", "strongly", "substantially"; no database field names used as words (checked by grep).
- **Discussion structure.** The first paragraph has no numbers; the literature comparison, limitations, implications and conclusion exist (flaws in 17, 22).
- **References.** 18 references listed, all cited, numbered in order of first appearance, no orphans, citations before punctuation.
- **Population and period match.** Table 1 and Figure 1 (2021-2022), Table 2 and Figure 2 (2013-2024) match Participants.

## E. Placeholders in square brackets (3)

1. Line 2: "[Authors, affiliations, ORCID, funding, conflicts of interest and contributions: to be supplied by the authors; not part of the blinded text]".
2. Line 8 (keywords): "[to be checked against MeSH/DeCS by the authors]".
3. Ethics and data availability: "[Ethics statement, data and code deposit with a persistent identifier, and disclosure of the use of generative artificial intelligence in the analysis and drafting: to be completed by the authors in the wording of the target journal.]" "The code is in the study repository" has no identifier either.

## F. What a referee asks first

1. Is the estimator valid at ages 1-24, where it was never validated and the share found is 0.5-0.75 against 0.96 in infants, and does it fail in the largest municipalities (items 3, 12, 16)?
2. Is the "lightening" a certifier effect or the child's race differing from the mother's, and is t independent of race (items 10, 17)?
3. Why do the age and cause patterns not rest on one common reference (item 8)?
4. Where is the interval on the certified ratios and the test of the "reversal" (item 11)?

## Counts

Errors: 7 (items 1-7). Should fix: 23 (items 8-30). Minor: 8 (items 31-38).
