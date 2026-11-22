# Response to review 1 - paper 5, `violence/`

`analysis/violence.py` is rewritten, with output `results/violence.json`. The paper's conclusion changed with it.

| Review item | Done |
|---|---|
| Top 1: false sentence; margins and net flows | Margins are now given for the same deaths: share White in hospital and on the certificate. Firearm assault: 0.23 and 0.20. Transport: 0.39 and 0.36. Natural causes: 0.39 and 0.46. From birth to the certificate: natural 0.48 to 0.43; transport 0.53 to 0.37; firearm 0.33 to 0.16. The paper now concludes the darkening is mostly present in life, not made at death. The false sentence is deleted. |
| Top 2: not specific to assault | Agreed and stated. Every external cause loses more White from birth to the certificate than natural causes, and assaults no more than transport accidents (asserted). The medical-examiner claim is dropped; physicians and medical examiners are both given. |
| Top 3: hospital design | One record per person: whether any earlier admission was recorded White, Black or Brown. Admissions per death are reported (1.96 natural, 0.22 firearm), as is the share of deaths with an earlier admission (0.47 and 0.21). Added: men only (unchanged); a 180-day window (unchanged); the admission in which the person died (firearm: hospital White 0.22, certificate 0.26). |
| Top 4: placebo, sensitivities | Placebo with the admissions' birth dates moved by a week: a residual of about a tenth of the estimate for firearm deaths and 3% for natural deaths, stated as a limitation. Not done: the birth-by-hospital cross for the same deaths (needs both candidate sets per death); the 400-birth threshold. |
| Top 5: denominators, bootstrap, primary | Bootstrap now uses 1,000 replicates over municipalities. The two scripts define legal intervention differently: the youth estimates (`common.KIND`) use the codes Y35 and Y36 as filed; `violence.py` uses Y35-Y36 with any fourth character. Their small-municipality sets also differ: births of 2012-2023 against 2000-2009. Both are noted and not yet reconciled. |
| Capitals | Unchanged: they need identified linkage, which is the author's decision (a data-use agreement). |
