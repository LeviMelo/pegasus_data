# Explanation ledger: paper 1 (place)

The question: why does the race on an infant's death certificate depart from the mother's declaration, and why
differently by place? Results: `results/*.json` (key in brackets). Status: supported, weakened, excluded, bounded, untestable.

| Reading | What it predicts | Test | Result | Status |
|---|---|---|---|---|
| Transmission: the certificate copies the mother's race or the birth record | agreement near 1, highest where the birth record is at hand; no gradient there | agreement and gradient by birth-establishment and first-day death (`mechanism.copy`) | agreement 0.67 at hand against 0.61 elsewhere; gradient steeper at hand (0.73 against 0.56) | excluded as the main mechanism |
| The family's classification (the instruction: ask the informant) | certificate equals the family's at each place | certificate against census family by municipality; investigation with family interview (`mechanism.investigation`) | nationally equal for Brown to White, opposite departures by region; investigation: see the json | weakened |
| Local majority conformity | symmetric cells: White mothers' infants darker where White is rare; Black mothers' infants Brown where Brown dominates; even odds near a White majority | `mechanism.cells` | WP slope -0.84, PW +0.64, KP on Brown share +0.55; even odds at about 58% White births | supported (cross-sectional) |
| A state practice | a step at state borders | border test (`spatial.border`) | slope 0.46 (0.26; 0.65): half a step, half a smooth gradient | supported in part |
| Category drift: the Brown category differs by region (appearance) | the same gradient with no local norm; certifiers in another municipality see the same child | residence against occurrence composition among deaths outside the residence (`mechanism.occurrence`) | see the json | open |
| The certifier as a person | physician variance beyond establishment and place | crossed physician, establishment, municipality (`physician.json`) | see the json | open |
| A norm that follows the population as it changes | within-place slope equal to the between slope | Mundlak with region-by-year effects (`panel.json`); long panel with censuses (`panel_long.json`) | within 0.05 (-0.01; 0.12) against 0.51 in regions; census within change too small (SD 0.07 against 0.98) | weakened; a slow norm not separable from a fixed trait |
| Wealth or services | context explains as composition does | deviance, multilevel, within | less alone, little beside composition; nothing within | weakened (collinear with composition) |
| Case mix of the deaths | municipal variance explained by individual variables | multilevel sequence | none without the macro-region | excluded |
| Linkage selection by place | linked share differs by certified race or place with composition | linked share by certified race and region | 81.1, 81.1, 80.2%; lower in the North | bounded |
| Method: smoothing, nAGQ = 0, multiplicity | variance ratio inflated; variances understated; spurious clusters | family less shrunk; Laplace refits (`laplace.json`); FDR on local Moran | see the json | open |
