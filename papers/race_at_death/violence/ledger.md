# Explanation ledger: paper 5 (violence)

The question: are young people certified darker after a violent death, and is that made at death or in life? Results: `results/results.json`
(`youth`, `context.youth`), `results/violence.json`. Status: supported, weakened, excluded, bounded, untestable.

| Reading | What it predicts | Test | Result | Status |
|---|---|---|---|---|
| Labelling at death | the certificate departs from the last record of life by cause | the same deaths at birth, in hospital, on the certificate (`three_records`) | hospital to certificate: natural +5, assaults -6 points (difference -11, CI excludes 0) | supported (2026-11-22, review 2) |
| Selection in life (victims reclassified before death) | birth to hospital darker for victims than for others | as above | birth to hospital about -15 points for every cause | excluded |
| Hospital clerks code darker | the hospital darker than birth and certificate whatever the cause | as above; the admission of death | darker than birth for every cause; darker than the certificate at the dying admission | supported as a level; the inference rests on the comparison between causes |
| Composition of where victims live | the gap vanishes at equal composition | fifths of composition; standardisation | gap in every fifth; standardised 0.45 against 0.65 | excluded |
| The certifier type | the gap is the IML's, not the cause's | within medical examiners | 0.37 assault, 0.60 other external | excluded |
| Social position at birth | the gap is schooling | by the mother's schooling | gap at every level of schooling | excluded as the whole |
| Movers differ by cause | found share differs by cause | found share | 0.47-0.54, alike | excluded |
| The capitals differ | large cities unlike the small | not reachable without identified data | untestable here | untestable (needs a data-use agreement) |
| Chance agreement | the control removes it | other-sex control; placebos at +-7 and +-14 days | residual about +12% of persons for firearm, -4% natural, in hospital | bounded; stated |
