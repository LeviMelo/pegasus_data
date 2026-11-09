# Stage 5, one door: PegaSUS's contexts, the population route, extremes, bindings that name roles only

**Regime.** pegasus_data master 059719a and the working tree on it, the one home `C:\Users\Galaxy\pegasus_core_data`,
2026-11-09. Artifacts in the session scratchpad (pickled before/after snapshots); nothing under `data/probes/`.

- **Done-when, PegaSUS's `contexts: auto`** (docs/plans/cubes.md stage 5). PegaSUS `studies/lepto_rs_check.yml` copied
  as `ctx_check` (SINAN-LEPT, RS, 2019-2023, `depth: survey`): `contexts: auto` reads all 123 declared fields for 5,570
  municipalities whatever the study's size. Run on pegasus_data 5ac2e9a (before the stage 5 commits) and on master,
  each with a fresh `PEGASUS_WORKSPACE`/`PEGASUS_HOME`. The contexts section (226,632 rows, 76 variables): 220,954
  estimates, 0 differ; profile, associations, rates, trends and the rest equal (≤1.8e-9). Every declared context read
  directly (`gateway.context_value` 2019-2023, `context_series` 2015-2023): 521,296 value cells, max relative difference
  4.2e-16 (summation order, `sisagua_surveillance_result_sum`); 2,868,550 series cells bit-equal; the same 83 unreadable.
- **`/population` on the population cube.** Ten requests (POPSVS, POPTCU, POP, CENSO, projpop; municipality, uf, year,
  age band, none) before and after: every total equal; every row equal but two, where codes no place takes now leave the
  state rows as they leave the events' (`place_states`): POPTCU 2001 RS 2,633 (431453) and POP 1980 GO 739,049 (52
  codes of prefix 52 no current code names). Both stay in `total`, named in `unresolved`. A state-filed series
  (projpop's `ufcod`) is a cube at uf and country and refuses a municipality.
- **Extremes from cubes.** `records:SIH-RD/rows` AC 2022 `max:`/`min:DIAS_PERM` by residence: 118 places, 0 differences
  from the records; AC's state maximum 307 days. The SIH recipe with two extreme measures added builds 831 cells merged
  by max/min. `ratio` was a mean under another name (each value lifted to (x, 1)): removed; a rate of two quantities is
  two `sum` measures divided after aggregating, as `/population` already serves.
- **Bindings name roles only** (ADR-0221 points 5-6): 1,173 of 1,239 resolved bindings unchanged, 59 month columns
  declared `precision: month`, after which all curated ones resolve as before; 52 implied months corrected, 10 false
  implied bindings replaced by 5 year-month pairs, 2 SRAG places gained. Cubes equal: SIM-DO 2022 1,544,266, SIM-DOR
  1995 893,868 (+9 unplaced), SINASC-DN 1994 2,571,571, CNES-ST AC 2022-12 1,266.
- **Precision measured where held.** The 100 date roles that name a month but declare no `precision` were read on the
  lake's Parquet (every distinct value, up to 20 files): 6 held are all AAAAMM and now declare it (SIA-PS and SIA-SAD
  `DT_ATEND`, `DT_PROCESS`; PAINEL_ONCOLOGIA `ANOMES_DIA`, `ANOMES_TRA`); 8 are month numbers (SISAGUA, SNGPC, SIES
  `NU_MES`/`MES`: halves the intake lands); 86 are not in the lake and stay undeclared rather than guessed. An
  undeclared month is still read correctly (its layout is measured); a `month` wrongly declared on a day date would cut
  DDMMAAAA into a false month, so none is declared without its values.
