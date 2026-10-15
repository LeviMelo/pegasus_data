# Record conditions on roles, against TabNet's published 2019 figures

**Regime.** 2026-10-15, branch `record-conditions` (from `pegasus-core-fixes` df36045; ADR-0193), scenario `scripts/live.py conditions`
(artifacts `data/probes/live/record-conditions-lake/` and `record-conditions-fresh/`). Brazil's births and deaths and the admissions of Brazil
and Alagoas on the shared lake (`pegasus_core_data`, read only, `max_download=0`: the lake path); Acre and Alagoas births and deaths on a
fresh scratch home whose state files were fetched from the FTP server (the fetch path: the lake holds the national SINASC and SIM files, not
the states'). The figures compared with are DATASUS TabNet's, queried 2026-10-15: SINASC `sinasc/cnv/nvuf.def` (births by the mother's
residence, 2019), SIM `sim/cnv/obt10uf.def` (deaths by residence, 2019, "Faixa Etária det", "Local ocorrência"), SIH `sih/cnv/niuf.def`
(Internações, the twelve 2019 processing months, "Faixa Etária 1"); the bands are summed to each clause. They are embedded in the scenario
(`TABNET_2019`).

**What was counted and why.** Each condition is the topic itself, written on roles (`count_events(dataset, event, period=2019,
geography=..., condition=[...])`); the figure that matters is the count and the number it could not decide, both of which TabNet publishes
(its "Ignorado" row). A synthetic check would pass by construction; the published tables are made by DATASUS's own tabulation of the same files.

| condition (roles) | Brazil | TabNet | unknown | TabNet "Ignorado" |
|---|---|---|---|---|
| births | 2,849,146 | 2,849,146 | | |
| `birth.weight` < 2500 | 247,856 (8.70 % of the 2,848,400 weighed) | 247,856 | 746 | 746 |
| `birth.weight` < 1500 | 40,453 | 40,453 | 746 | 746 |
| `birth.delivery` in 2 (caesarean) | 1,604,189 (56.34 % of 2,847,293) | 1,604,189 | 1,853 | 1,853 |
| `birth.delivery` in 1 | 1,243,104 | 1,243,104 | 1,853 | 1,853 |
| `birth.gestation_band` in 1-4 (under 37 weeks) | 315,831 (11.23 %) | 315,831 | 36,313 | 36,313 |
| `birth.gestation_weeks` < 37 | 315,751 | 315,831 | 37,092 | 36,313 |
| `mother.age` < 20 | 419,255 (14.72 %) | 419,255 | 72 | 72 |
| deaths | 1,349,801 | 1,349,801 | | |
| `deceased.age_years` < 1 (infant deaths) | 35,293 (12.39 per 1,000 live births) | 35,293 | 2,358 | 2,358 ("Idade ignorada") |
| `deceased.age_years` < 28 days | 24,505 | 24,504 | 2,358 | 2,358 |
| `deceased.age_years` < 7 days | 18,403 | 18,402 | 2,358 | 2,358 |
| `death.place` == 3 (home) | 264,628 (19.6 %) | 264,628 | 859 | |

Alagoas (residence, fetch path): every row equal (weight < 2500 3,837 of 49,803, 3 unknown; caesarean 26,085, 42 unknown; mothers under 20
10,636; infant deaths 659, 447 under 28 days, 344 under 7 days, 1 unknown; home deaths 4,888) except weeks < 37 (4,531 with 842 unknown, TabNet
4,531 and 841). Acre (fetch path): births 16,280, weight < 2500 1,187 (115 unknown), caesarean 7,232 (12), mothers under 20 3,901, infant deaths
259 (18 unknown), 131 under 28 days, 92 under 7 days, home 950: equal in every row. SIH-RD (lake, `patient.age_years` from `IDADE` and
`COD_IDADE`): Brazil 12,181,726 admissions, 644,887 under one year, 3,221,765 of 60 and over (1 age unknown); Alagoas 171,660, 10,312, 34,900:
equal to TabNet's.

**The two differences, and what they are.**
- Weeks under 37 against the published preterm figure: TabNet's "Duração da gestação" is the band `GESTACAO`, which is filled for
  779 more births than the weeks `SEMAGESTAC` (`birth.gestation_weeks`, from 2010). The band role reproduces the published number exactly;
  the weeks role leaves 779 births unknown and 80 preterm births uncounted. A study of preterm birth before 2010 can only use the band: the weeks
  role is carried by no column then, so every birth of those years is unknown, and the clause is refused only when no year read carries it.
- One death: SIM 2019 holds a record whose `IDADE` is `300` ("0 months", no birth date, N179). `_age` decodes it as 0.0 years, so it is
  under 28 days and under 7 days here; TabNet bins it with the 28-364 days. A month count of 0 cannot say whether the child had 20 or 29 days
  (OQ 85); infant deaths are unaffected (35,293 both).

**Other results.** The pushed-down predicate and the evaluation after an unfiltered read agree (Brazil, weight < 2500 and caesarean: 147,383
true, 182 unknown, 2,701,581 false both ways). A condition costs what the read costs: Brazil's births under a condition take 1.3-3.9 s on the
lake against 2.2 s uncounted, the 12.2 M SIH admissions 3-5 s. `require` refuses a clause no year read carries (weeks of gestation for 2005, declared
from 2010) and counts the unknown where only some years carry it; `bind` refuses SINASC's `baby.race` in 2012-2013 (`RACACOR` and `RACACORN` both carry
it), a number against a code, an order between codes, a missing code as a value, and a role the dataset does not declare, naming the closest.
