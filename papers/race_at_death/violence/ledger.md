# Explanation ledger: paper 5 (violence)

The question: are young people certified darker after a violent death, and is that made at death or in life? Results: `results/results.json`
(`youth`, `context.youth`), `results/violence.json`. Status: supported, weakened, excluded, bounded, untestable.

| Reading | What it predicts | Test | Result | Status |
|---|---|---|---|---|
| Labelling at death | an earlier record made in life is lighter than the certificate for homicides, not for natural deaths | earlier SIH admission against the certificate, by cause | hospital White, certified White: 0.82 natural, 0.47 firearm | supported |
| Selection in life (victims already Brown) | the earlier hospital record already Brown for victims | as above | the hospital recorded half the later firearm victims White | weakened |
| Composition of where victims live | the gap vanishes at equal composition | fifths of composition; standardisation | gap in every fifth; standardised 0.45 against 0.65 | excluded |
| The certifier type | the gap is the IML's, not the cause's | within medical examiners | 0.37 assault, 0.60 other external | excluded |
| Social position at birth | the gap is schooling | by the mother's schooling | gap at every level of schooling | excluded as the whole |
| Movers differ by cause | found share differs by cause | found share | 0.47-0.54, alike | excluded |
| The capitals differ | large cities unlike the small | not reachable without identified data | untestable here | untestable (needs a data-use agreement) |
| Chance agreement | the control removes it | other-sex control; small municipalities | estimator validated in infants | bounded |
