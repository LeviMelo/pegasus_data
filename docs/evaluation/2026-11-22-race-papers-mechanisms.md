# Race papers: who classifies, two censuses, and labelling at death (2026-11-22)

Scripts:
- `papers/race_at_death/analysis/{mechanism,mechanism2,panel,panel_long,family,violence,indicators2}.py`;
- `physician.R`;
- `counts.py mechanism`;
- `data/probes/census2022/pairs.py`.

Outputs in `papers/race_at_death/results/`. Data home `C:/Users/Galaxy/pegasus_core_data`. Commit: this one.

Paper 1, certified race of infants against the mother's (296,512 linked deaths):

| test | result |
|---|---|
| copy test: same establishment as the birth, death on day 0-1 | agreement with the mother 0.67, against 0.61 elsewhere; composition slope steeper there (0.73 against 0.56) |
| symmetric cells | White mothers' infants certified Brown slope -0.84; Brown to White +0.64; Black to Brown on the Brown share +0.55; even odds at 58% White births |
| death outside residence (46%) | composition of the place of death 0.42 against residence 0.32 per logit unit |
| crossed variance, 2014-2018 | Brown to White: physician 0.79, establishment 0.46, municipality 0.08. Black: 0.29, 0.42, 0.21 |
| Mundlak panel with region-by-year effects | within 0.05 (-0.01; 0.12) against 0.51 between; long census panel within -0.65 (SE 0.26) against -0.54 between |
| local Moran clusters, Brown to White | 546 high-high at p < 0.05; 356 under FDR. None for Black |

Paper 3, the Black category:
- Who filled the birth record changes the Black share by under 1 point within hospitals.
- Same mother at the next birth, chance pairs removed (34.5% of pairs): declared Black again 0.52 (White 0.75, Brown 0.87). The hospital recorded her Black again 0.92 in the same hospital and 0.58 in another.
- A mother who changed hospital took on its practice in full (slope 1.01, SE 0.03).
- The hospital's record of the mother predicts the infant's certificate within establishments of death: 1.98 for infants who died where they were born, 1.75 (1.25; 2.44) for those who died elsewhere.
- The certificate's rise, standardised to the mothers of 2013: 0.155 to 0.233.

Paper 4, the census pairs: 6.14 M records in 2010 and 5.33 M in 2022.
- Brown mothers with a White partner: child reported White 0.54, then 0.59.
- Black mothers' children aged 0-4 reported Black: 0.437, then 0.433.
- Another resident answered as the mother did (OR 0.97).

Paper 5:
- Deaths at 15-24 years: 81,499. Earlier SIH admissions: 7.8 M.
- Of those an admission had recorded White, certified White: 0.82 after a natural death, 0.47 after firearm assault.
- This is weighted by admissions, which the review asks to weight by person.

Paper 2:
- White to Brown: 0.80 with deaths and births by the mother's race; 1.31 with certified deaths over the mother's births; 0.79 with certified deaths over births by the child's race (household flows).
- Black to Brown: 1.15, 0.49 and 0.80.
- Region-standardised: 0.87, 1.66 and 0.81.

Data facts:
- SIH filled the admission's race from 2023: among Black-declared mothers it was blank on 21.5% in 2022 and 2.8% in 2023.
- Further facts are in `DATA_SOURCES.md`.
