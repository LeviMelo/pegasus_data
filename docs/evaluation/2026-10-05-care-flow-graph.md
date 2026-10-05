## Care-flow graph: SIH-RD residence -> hospital municipality, 2019 and 2022

**Scripts.** `pegasus-data graph SIH-RD --period Y --root C:/Users/Galaxy/pegasus_core_data` (`--to establishment`, `--by COMPLEX`, `--derive ...`); analyses `data/probes/care_flow/{analyse,sweep,disagree,complexity,years}.py`, outputs `*.parquet`, `*.analysis.json`, `sweep.json`, `years.summary.json`. **Regime:** branch `pegasus-core-fixes` (ADR-0144), core data home, 2026-10-05. Only 2019 and 2022 were run (the other years queued behind shared heavy slots and were not waited on).

**Counted and why.** Admissions (IDENT=1, one per N_AIH) by residence and by hospital municipality: the quantity every product derives from, and one TabNet publishes independently.

**Reconciliation.**

| year | events | TabNet | difference | edges | unplaced / unresolved |
|---|---|---|---|---|---|
| 2019 | 12,181,726 | 12,181,704 | 22 | 105,603 | 0 / 0 |
| 2022 | 12,377,318 | 12,376,634 | 684 | 98,347 | 0 / 0 |

The 2022 difference is chapter XXII, which TabNet's chapter list omits; the other 16 chapters equal ours exactly. DF municipality codes fold into 5300108 only.

**Residence != occurrence.** 34.2% (2019) and 34.6% (2022) of admissions are treated outside the residence municipality; 1.49% / 1.27% cross a state line. About 2,450-2,460 municipalities have resident admissions but treat none; about 2,600 have self-sufficiency under 10%; 3,107-3,120 treat any.

**Capitals, self-sufficiency 2019 / 2022.** Sao Paulo .962/.960, Rio .963/.963, Belo Horizonte .986/.985, Salvador .979/.964, Fortaleza .967/.971, Manaus .983/.989, Brasilia .991/.993, Recife .930/.925, Vitoria .783/.750, Florianopolis .846/.844, Curitiba .793/.950. 2022 import share: Campina Grande do Sul .88, Campo Largo .82, Vitoria .78, Recife .67.

**Curitiba 2019 (explained, real).** 21,073 Curitiba residents were admitted in Campo Largo in 2019, 3,068 in 2022. All come through one CNES, 0013846 (Campo Largo), which treated 18,276 distinct-AIH Curitiba residents in 2019 and 2,445 in 2022 (69,217 and 44,136 admissions in all). CNES-ST places 0013846 in Campo Largo (CODUFMUN 410420, CEP 83606-177) in both years, so SIH and the registry agree: it is not a municipality-code artefact. The admissions are general clinical and surgical (specialty 03 and 01), spread evenly over the 12 months of 2019 (1,300-1,800 a month; 120-290 a month in 2022); every AIH is unique. It is a real, large contracted use of a Campo Largo hospital by Curitiba that shrank by 2022, which is why Curitiba's self-sufficiency moves .793 -> .950. Which year the contract changed is unmeasured (2020-2021 not run). A graph over the hospital's municipality, as built, is correct; a reader should not treat Curitiba's 2019 figure as its steady state.

**Complexity (2022, `--by COMPLEX`; only medium 02 and high 03 are coded).** Medium 11,406,723 admissions, 67.3% at home, 3,120 treating municipalities, 66 communities (resolution 1). High 970,595, 42.8% at home, 612 treating municipalities, 36 communities. Establishment variant: 190,296 edges over 4,820 CNES, summing to 12,377,318.

**Flow communities against the official regions** (439 current health regions, 121 macro-regions). "Away kept" is the share of admissions treated outside the residence municipality that stay inside the unit.
- 2019: resolution 1 -> 59 communities, 3 -> 105, 10 -> 241, 20 -> 424 (vs health regions ARI .57, NMI .915; away kept .643 against the regions' .578), 80 -> 1,044.
- 2022: resolution 4 -> 130 communities against macro-regions: ARI .67, away kept .863 vs .804; resolution 21 -> 402 (87 singletons) against health regions: ARI .565, away kept .662 vs .584.
- At matched counts the flow communities keep 6-8 percentage points more of the away admissions than the official units. 16-18 communities span several states (Brasilia with 16 Goias municipalities; Francisco Beltrao PR with 8 SC). Largest macro-region disagreement 2022: Nordeste (GO) is 30% contained and 87% of it lies in the Brasilia community; Agreste and Sertao of Pernambuco flow to Recife.
- Nodal catchments: 2,215 (2019) and 2,182 (2022) hubs; honest, but fine-grained.

**Not shown.** The agreement with official regions depends on the resolution; no single "best" value is claimed. SUS-paid admissions only.
