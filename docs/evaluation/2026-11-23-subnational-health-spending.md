# Subnational health spending: SIOPS against SICONFI, and SIOPS landed (2026-11-23)

**Regime.** Branch `worktree-agent-a0b12a19a96ddca8a` off a40ea0f4, a scratch data home (deleted after). Source `siops_municipal` (`curation/intake.yml`, new `origin.kind: tabnet`), roles
`curation/roles/SIOPS-MUNICIPAL.yml`. Landed with `pegasus-data intake siops_municipal --years 2005,2013,2018,2021,2023,2025 --unit AC --unit SE`; the check script and its per-municipality answers are
`data/probes/siops/ver_<uf>_<year>.json` (gitignored). Facts about the sources are in DATA_SOURCES §18.

**Why a blind spot.** Municipal own-resource spending on health (15% of the tax base by LC 141; 12% for states) was nowhere in the home.

**Assessment.** Both sources were read, not guessed.
- *SIOPS* (DATASUS TabNet "Indicadores Municipais", `siops-asp.datasus.gov.br`, plain http; https does not connect from here, http does; `siops.datasus.gov.br` redirects to gov.br and its PHP consultation is one HTML form per
  municipality and year; the FTP has no SIOPS folder; the open-data portal search redirected and the `dados.gov.br` API answered 401, so a dataset there is not excluded): every state, 2000-2025, one row per municipality and
  year that declared, 22 contents of which five are reais amounts (tax base, SUS transfers, personnel, spending from own resources, total spending). Own-resource spending and the EC 29 share exist **only here**.
- *SICONFI* (`apidatalake.tesouro.gov.br/ords/siconfi/tt`, open JSON, 5,000 rows a page, an answer per entity and year): DCA-Anexo I-E has spending by function and subfunction with the three stages (empenhada, liquidada,
  paga) for all municipalities from 2013; the RREO holds **no Anexo 12** (the ASPS statement) for São Paulo 2019/2023, Rio Branco 2018/2023, Acre 2023, and a small municipality files the simplified RREO (anexos 01, 02, 06:
  Acrelândia 2023). SICONFI cannot answer "how much of its own resources did the municipality put in health".
- *Verdict.* SIOPS is the primary source (the health-specific declaration, the only one with the constitutional share); SICONFI DCA is the independent check and the only source of subfunction and stage detail, not
  integrated here (OQ 102). The two are not the same figure (below), so each stays its own dataset.

**Landing.** AC and SE, 2005 / 2013 / 2018 / 2021 / 2023 / 2025: 22 and 75 municipalities a year, 97 rows a year, every unit's file lines equal its rows, and each additive column's sum over the rows equals TabNet's Total row
(checked at every landing, `check_total`). 2023: spending 704,611,409.91 (AC) + 2,234,559,879.30 (SE) = 2,939,171,289.21 through `load_field('siops_health_spending')`; own resources 1,442,084,186.73; SUS transfers,
tax base, personnel and 97 declarations read the same way. Indicator 3.2 recomputed from the amounts (own resources over tax base) differs from the published one by at most 0.0049 points (rounding), 2023. Municipalities under
the 15% minimum: 2023 one (Mâncio Lima, 10.93%), 2021 four, 2018 five.

**Against SICONFI DCA-Anexo I-E, function 10, despesas empenhadas** (one request per municipality; AC and SE):

| year | municipalities with DCA | SIOPS equals DCA to R$ 1 | SIOPS / DCA, total | range |
|---|---|---|---|---|
| 2023 | AC 22, SE 75 | 13 and 54 | 1.036 and 1.030 | 0.970-1.212 |
| 2021 | 22, 75 | 15 and 51 | 1.038 and 1.043 | 0.953-1.522 |
| 2018 | 20, 75 | 8 and 57 | 1.047 and 1.075 | 0.946-1.721 |

198 of 289 (69%) equal to the real; the rest differ both ways, SIOPS larger in total by 3-8%. Rio Branco 2023: SIOPS 313,604,022 against function 10 empenhada 288,265,512 (liquidada 261,263,040). The cause of the
differences is **not established**: SIOPS's own stated rule (empenhada less restos a pagar without financial availability) should lower it, so it would be spending SIOPS counts outside function 10, or a retification
after the DCA; neither was tested.

**Left out and why.** TabNet's subfunction shares (2.21-2.26): 2013-2015 only and mostly 0,00, no rows before, `...` after (checked on SE, every year); spending by subfunction 301/302 comes from DCA. Brasília is in the
state base. A municipality that did not declare is absent (TabNet shows it as Frequência 0 only with "show zero rows"). Asking for a subfunction content together with the rest returns no rows at all for 2000-2012
(every municipality of AC, SE and SP read as Frequência 0), which is why they are not asked for.

**Read as `query`.** `query("SIOPS-MUNICIPAL", period="2023")` gives 49 columns for the 97 municipalities (typed value, `__RAW` as TabNet wrote it, UF, code, name).

**National landing (2026-11-23, the real home).** 2002-2025, 26 states a year, 5,409-5,568 municipalities a year, 132,911 municipality-years in every field. TabNet holds no municipal table for 2000-2001: asking those years made the field build refuse ("publishes none of the years"), so the declared range is 2002-2025.
