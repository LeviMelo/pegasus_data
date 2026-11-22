# Explanation ledger: paper 3 (the Black category)

The question: who records the infant of a self-declared Black mother as Black, and why so seldom? Results: `results/black.json`,
`results/mechanism.json` (keys in brackets). Status: supported, weakened, excluded, bounded, untestable.

| Reading | What it predicts | Test | Result | Status |
|---|---|---|---|---|
| Copying the mother's chart | the hospital's record of the mother predicts the certificate only where the infant died where it was delivered | Mantel-Haenszel and conditional logit within death establishments, died there against elsewhere (`black.mh_death_estab_*`, `clogit_*`) | OR 2.01 died there, 1.75 (1.28; 2.43) elsewhere | weakened |
| Shared perception of the same person | the association survives where the chart is not at hand; the person's record dominates the hospital's practice | as above; practice with the mother's own record in the model (`practice_loo_eb.practice_person`) | person OR 1.89; practice 1.10 (1.02; 1.18) beside it | supported, not proved (appearance unrecorded) |
| A hospital-wide practice | practice predicts the certificate; the same mother is recorded alike in every hospital only by its practice | leave-one-out shrunk practice, clustered by hospital; the same mother in two hospitals (`movers`) | 1.20 at equal composition, 1.10 beside the person; movers: see the json | weakened |
| The reference is staff-made | the Black share of declarations and its agreement with the hospital depend on who filled the birth record | `filler` by TPFUNCRESP, within hospitals; the same mother's declaration across births (`movers.declared_again`) | see the json | open |
| A Brown default in hospitals | a mass of hospitals near 0 Black for Black-declared mothers | distribution of practice; blank bounds | p10 0.01; blanks as Black 0.50, as other 0.28 | bounded |
| The rise is who declares | standardised to 2013's mothers the rise vanishes | direct standardisation (`certificate_by_year_standardised`) | 0.155 to 0.233 standardised | excluded |
| The certificate and the hospital move together | equal trends on the same infants | joint model (`joint_trend_same_infants`) | certificate +0.45 a decade; hospital 0.37 less (SE 0.09) | excluded |
| The certifier | variance by physician beyond establishment | `physician.json` | see the json | open |
| Age: infants classed lighter | certificate lower for infants than older children in the same municipalities | estimator after infancy, same municipalities | 0.18 against 0.24 at 1-4; 5-9 imprecise | supported, one contrast |
| Linkage selection | infants with and without the delivery record certified alike | `individual.black_with_record` | 0.19 against 0.18 | excluded |
