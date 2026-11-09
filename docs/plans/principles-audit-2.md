<!-- Second principles audit, 2026-11-09 (a read-only sweep; each item verified before it is fixed). The register is in STATUS.md. -->
# pegasus_data principles audit 2 (read-only, 2026-11-09, master @ 36daa84)

Scope: `src/pegasus_data/` (207 modules). Method: grep sweeps for the patterns listed in the brief, reading each hit's
context, an AST scan for module-level functions/classes with exactly one textual occurrence (the definition), and
`scripts/codehealth.py`. All paths are relative to `src/pegasus_data/`. The 10 defects of STATUS's register are closed;
where a closure left a residue it is marked **RESIDUE**.

Severity: S = semantic (could yield a wrong number or label), T = structural (second mechanism / hand-fixed fact that
will drift), H = hygiene. Size: XS under 20 lines, S under 100, M under 300, L more.

Totals: 41 items. S = 9, T = 24, H = 8.

---------------------------------------------------------------------------------------------------------------------

## SEMANTIC (S)

**S1. A second 6-to-7 digit municipality expander that invents the check digit** (RESIDUE of defect 6/placing rule) — done (S1 commit): every `<base>_ibge7` companion is recomputed by the one placing rule where every read passes (`view.placed_companions`); an unknown code gives null (120000 had given 1200003). Normalisation's algorithm is left writing the lake, since its plan digest keys every partition and changing it would mark the whole lake stale; the stored values are corrected at read
- `normalize/geo.py:156-188` (`to_seven_digit`), `:120-125` (`MunicipalityIndex.from_catalog` fills the rest "using the
  check digit"), `:128-133` (`to_seven`), `check_digit_array:134`. Used by `normalize/engine.py:351` (every
  `municipality_code_6/7` column gets `<name>_ibge7`) and by `build.py:535`, `retrieve.py:1264`.
- It seven-digits any 6-digit code, known or not, by algorithm. `geography.to_code7` (`geography.py:625-637`) states the
  opposite rule: "the check digit is not derivable, and a wrong seventh digit joins to the WRONG municipality"; and
  `normalize/geo.py:41-43` itself says some real codes fail the algorithm. So an unmapped 6-digit code becomes a
  plausible-looking 7-digit code that is not a municipality (or is another).
- Violates: "never guess a code's meaning; an unmapped code is undecoded, visibly"; one placing rule
  (`geography.place_municipalities`).
- Fix: drop the algorithmic fallback; `_ibge7` is the pack's `code7` or null (counted), via `geography.to_code7`/`place_municipalities`.
  Then `check_digit*` is only a validator. Size S.

**S2. Intake's SQL placing rule lacks `legacy_places`, though `place_municipalities` says it is "the same rule"** — done: one source of the rule's facts (`geography.placing_rule`: universe, sole-municipality states, legacy codes), read by `place_municipalities` and registered as the intake's SQL tables; on 7 test codes (legacy Rio, Brasília's regions, an ignored code, 7 digits) the SQL and Python answers agree
- `intake.py:496-502` (`_MUNICIPALITY` CASE) vs `geography.py:640-673` (adds `legacy_places` from `geography.yml:343`:
  Rio de Janeiro 3345xxx; also trims `.0` with `endswith` while SQL uses `'\.0+$'`).
- Two implementations of one rule already diverged: a code legacy-placed in Python is unplaced in an intake landing.
  The docstring (`geography.py:648-649`) claims they apply the same rule.
- Violates: second mechanism for one job; rows silently unplaced (they are kept with `_MUNICIPALITY` NULL, so counted
  only if someone counts).
- Fix: generate the intake CASE from the same data (`universe`, `sole`, `legacy_places` registered as one DuckDB table by a
  function that `place_municipalities` also reads), or place in Python over distinct values and join. Size M.

**S3. `sus_dependent` turns any non-"M" sex into female and matches a coverage class by the first letter of a label** — done (branch worktree-agent-a28eb98f9b9fd700e): sex through `canonical_sex`, coverage by the field's declared `where`, age bands parsed from the labels, years and account version declared; 2021-2022 cells equal (99,667,547 links, 0 unknown sex)
- `sus_dependent.py:78` (`1 if r["sex"] == "M" else 2`), `:71` (`r["coverage"].startswith("M")`, comment "stored with a
  replacement character"), `:37-39` (`ANS_BAND`: PT label text to bands), `:85` (`years = [2021..2025]`), `:93`
  (`"population-account-2"` pinned).
- A null/unknown sex lands in the female denominator cells (missing counted as a value). The coverage test guesses the
  meaning "medical-hospital" from a letter of a corrupted label; band meaning comes from label text equality.
- Violates: "never guess a code's meaning"; "missing is not zero/other".
- Fix: take sex and coverage from the ANS records cube's codes (roles/codelist `categories`), band edges from the
  cube's age dimension; unknown sex -> reported residual, not a sex. Size S.

**S4. Sex read from a label's first letter** — done (branch worktree-agent-a28eb98f9b9fd700e): one `canonical_sex` (`curation/categories.yml`) for linkage and `sex_of`; `encode_race` matches at width; real labels and codes equal, 0 of 69.5 M race values had a leading zero
- `population_account.py:208-219` (`sex_of`: `startswith("m")` / `startswith("f")` on the lowercased label; the one function
  closing defect 3), `:222` `SEX_INDEX = {"M": 0, "F": 1}`; `modelled_race.py:62` `CODE = {"1":0..."5":4}` with
  `lstrip("0")` at `:79`.
- "Masculino"/"Feminino" pass, "Menino", "Mulher", "Male"/"Female" (English pack) or a "Maiores de..." label pass or fail
  by accident; a third value starting with m/f is silently sex. `lstrip("0")` makes `"01"`==`"1"` (widths not exact).
- Violates: "never guess a code's meaning", "widths matched exactly".
- Fix: sex from the field's roles (`categories: {male: [...], female: [...]}` per codelist/validity window), race codes
  from the RACACOR codelist; one function in `semantics/column_roles`. Size S.

**S5. `quality.race_reliability` encodes SIH's RACA_COR code meanings and thresholds in code** — done (branch worktree-agent-a28eb98f9b9fd700e): columns by role, codes from the year's codelist labels through the roles' categories, thresholds in `curation/quality.yml`; SIH-RD CE and AC 2022 flags equal on 579,505 rows
- `quality.py:20-60` (code `04`=amarela, `03`=parda, 50 %, 10 %, 1 %, `MIN_ADMISSIONS=30`), default column names
  `RACA_COR`, `CNES`, `DT_SAIDA`.
- A fact about one system's codes lives in code, reading `"04"` etc. as strings (exact widths assumed), so it breaks
  silently on another vintage/system and on a codelist change.
- Violates: hand-fixed facts; "never guess a code's meaning".
- Fix: resolve the codes from the column's codelist (label "Amarela"/"Parda") through roles; keep thresholds as declared parameters of the check in `curation`. Size S.

**S6. `completeness.ill_defined_shares` hard-codes ICD chapter R and the CAUSABAS column; SIM/SINASC branches throughout** — done (branch worktree-agent-a28eb98f9b9fd700e): ill-defined causes declared on the `death.cause` role, per-system model in `products.yml`, SIM/SINASC branches removed; the 1,296-row product equal
- `completeness.py:193-204` (`CAUSABAS`, `R` except `R95`), `:228-258` (`if system == "SINASC"` / `"SIM"` x6),
  `:135-137` (`ANCHOR_SD`, `MODEL` per system), `:27` and `:225-226` (`period[:4]`, `period[5:]`).
- Which causes are "ill-defined" is a semantic fact (ICD-10 R00-R99 minus R95 by the module's own choice) written in the
  code on a column name; cause column per system differs.
- Violates: hand-fixed lists; names a column in code.
- Fix: `ill_defined` as a declared cause group (event_types/conditions `where`) on SIM's roles; per-system model choices into
  the product's manifest/curation. Size M. (Module is also dead, see H1.)

**S7. `geography.memberships` pads codes to 6 with `zfill` to make a lookup succeed** — done (this commit): `memberships` refuses widths other than 6/7, census commuting raises on a non-7-digit code; `detectors.py:291` (a UF check) and the CNV parser's documented TabNet rule left
- `geography.py:766-767` (`six.zfill(6) if six.isdigit()`); similarly `sources/census_commuting.py:215,221` (`zfill(7)`
  on origin/destination codes), `profile/detectors.py:291` (`v.zfill(2) in UF_NUMERIC`), `semantics/cnv_parser.py:558` (documented).
- A 5-digit or shorter code ("11000") becomes "011000", and a municipality code stripped of leading zeros by a CSV
  export is re-padded to the width that matches. Documented padding in the CNV parser is the TabNet rule; these are not.
- Violates: "widths are matched exactly; never pad or truncate a code to make a join succeed".
- Fix: refuse (return empty, counted) on a width other than 6/7; the census-commuting case needs the source's declared width
  (declare it in the source's spec, not `zfill`). Size XS.

**S8. `[:6]` truncation of a 7-digit code in many readers instead of the placing rule** — done (this commit): `geography.place_six` in `rates` (with an unplaced row), `field_rate`, the CPTEC and tract filters; left as not municipality columns of records: `crosswalk` (dates), `population_account` and `sus_dependent` (keys the rule itself produced), `geography:660,1070` (declared and mesh codes), `detectors:266` (match against a supplied set)
- `rates.py:101,125`, `fields.py:536`, `population_account.py:293-294`, `sus_dependent.py:106`, `crosswalk.py:213-214`
  (dates), `geography.py:660,1070`, `sources/cptec.py:441`, `sources/ibge_tracts.py:182`, `profile/detectors.py:266`.
  15 sites.
- Each trims to 6 without verifying the code is a municipality (a 7-digit code that is not IBGE's, a `53xxxx` DF region,
  3345xxx legacy, would be a "municipality"). `rates.age_standardised_rates(by=...)` rates on `str(v)[:6]` with no
  placement and no unplaced count.
- Violates: one placing rule; "silent drop of unplaceable rows without counting".
- Fix: a `geography.six(code)` helper over `place_municipalities` returning (code6, placed) and counting unplaced; use it. Size S.

**S9. Missing treated as zero in a few readers** — done (this commit): CPTEC stations null, census `validate` counts absent, `_partition` makes the null-as-rest explicit; `intake.py` (counted) and `_vintage.py` left
- `render_groups.py:147` (`fill_null(competencia, 0)`: records with no date form a group "0" with the grouping), `intake.py:532`
  (`COALESCE(year, 0)`: a record with no year lands in a partition `year=0`; counted at `:588` `count_if(year = 0)`, so
  visible, acceptable) , `sources/cptec.py:161` (`np.nan_to_num(fields[1], nan=0.0)`: the NEST/station-count grid missing
  becomes 0 stations, and `fields[0]` precipitation keeps NaN; check `stations==0` is not read as "no data" in the
  reducer), `sources/census_commuting.py:262` (`fillna(0.0)` on answered/graph weights of municipalities absent from the
  tables), `_vintage.py:40` (`fill_null(..., 0)` on a competence column).
- Violates: "missing is not zero".
- Fix: carry null, count it; for cptec keep the stations grid's NaN as "not observed". Size XS each.

---------------------------------------------------------------------------------------------------------------------

## STRUCTURAL (T): hand-fixed facts about the data in code

**T1. CNES field recipes name 15 columns and their filters in code** (RESIDUE of defect 6/7; the groups moved to `fields.yml`, the columns did not) — done: each family's recipe (dataset, measures, group column, SUS codes with their layout evidence, fixed filters) is declared in `fields.yml` `cnes: families:` and `cnes_cube` is generic; the 43 plans are byte-identical
- `fields.py:425-466` (`_cnes_cube_plan`): `TP_UNID`, `VINC_SUS`, `CODLEITO`, `QT_EXIST/QT_SUS/QT_NSUS`, `TIPEQUIP+CODEQUIP`,
  `IND_SUS`, `CBO`, `PROF_SUS`, `HORA_AMB+HORAHOSP+HORAOUTR`, `CNS_PROF`, `TIPO_EQP`, `DT_DESAT`, `IDEQUIPE`; dataset names
  `CNES-ST/-LT/-EQ/-PF/-EP`; `{"1"}` for SUS (`VINC_SUS == "1"`, `IND_SUS == "1"`, `PROF_SUS == "1"`).
- A fact per column that curation (`fields.yml: cnes:` or roles) should declare; the "1 means SUS" meaning is hard-coded
  three times.
- Fix: put dataset, measure column, sector column, and its SUS codes in each `cnes:` family in `fields.yml`; the function becomes generic. Size M.

**T2. Same-job duplicates: number parsing (7 readers)** — done (this commit): `normalize.types.to_number`, 40 outputs equal on SIH/SIM
- `_aggregate.py:633` (`_to_number`, regex `[+-]?\d+([.,]\d+)?`), `normalize/types.py:70-97` (similar regex + comma, raises
  to nulls on `ArrowInvalid`), `_age.py:112-127,176-186` (`_digits_to_years`, `number_of`), `semantics/event_types.py:590-598`
  (`^\d+$` raising), `sources/ibge.py:285-293` (`^-?\d+$`), `conditions.py:357-365` (`float(code.replace(",", "."))`),
  `cubes.py:380` and `linkage/roles.py:219` (bare `cast(float64, safe=False)`, raise on text).
  `cubes.py:446,459` imports the private `_aggregate._to_number`.
- Different thresholds of what counts as a number: `1.234,5`, `+5`, `-`, blanks and `0,5` are read differently.
- Fix: one `normalize.numbers.to_number(array, policy)` that returns (values, unparsed count); the six call sites use it. Size M.

**T3. Same-job duplicates: period parsing (about 14 ad hoc sites)**
- `normalize/time.py:87` (`competencia_to_year_month`), `_query_engine/model.py:239` (`_period`), `retrieve.py:1686` (`_month_of`),
  `intake.py:517-533` (SQL `substr(ym,1,4)`/`5,2`), `serve/_filters.py:70`, `serve/_payload.py:106`, `capabilities.py:659`,
  `labelpack.py:858,1012,1287,1377,1418`, `cubes.py:348,367,550,599,658` (`str(p)[:4]`), `sidra/prices.py:64,96`,
  `completeness.py:226`, `population_backcast`, `providers.py:70,139`, `snapshot.py:133,149` (`YYYYMM` arithmetic with `* 100`, `% 100`, `// 100`
  in about 25 places).
- Each re-derives (year, month) from an int/str; validity (`1..12`) is checked in some (`intake.py:900`, `model.py:253`) not others.
- Fix: one `periods.py` (`Period` already exists in `_query_engine/model.py`): `parse`, `year_of`, `month_of`, `span`, `format`. Size M.

**T4. Same-job duplicates: municipality code conversion and the municipality universe (6 readers of `resources/municipalities.parquet`)** — done (this commit) except `intake.py:407-420` and `normalize/geo.py` (others' files): `geography.municipalities()` is the one reader
- `geography.py:366` (code6 list for ranges), `geography.py:1153` (UF code from sigla), `presentation.py:250-257` (code6->code7 dict),
  `persist/reference.py:564`, `proximity.py:197`, `normalize/geo.py:93-107` (from catalog rows), `serve/_population.py:44`, `intake.py:407-420`
  (builds `universe`, `sole`, `names` again).
- Each reads the file or recomputes `sole` (UFs with one municipality) separately (`geography.py:652-655`, `intake.py:412-414`).
- Fix: `geography.municipalities()` is the one reader; expose `to_code7`, `sole_by_uf`, `uf_code(sigla)` from it and delete the copies. Size S.

**T5. `lake` / `registries` / `modelled` paths hand-assembled outside their owners**
- `Path(root)/"lake"` with `SimpleNamespace(lake_dir=...)` at `completeness.py:223,283`, `population_account.py:1048`,
  `population_backcast.py:360,386`, `population_tensor.py:708`, `sus_dependent.py:59-66` (3 further hand-made `settings` objects).
  `"registries"/<name>` assembled at `cli/pipeline.py:51-58`, `concepts.py:45`, `fields.py:556,592`, `geography.py:940`, `intake.py:188`, `adopt.py:150-171`.
- Violates the one-data-home rule's spirit: the "registries" and "lake" subfolder names are knowledge of `config`.
  `population_backcast.py:360` reads `lake/modelled/population_account/<source>` directly instead of `read_modelled`.
- Fix: `Settings.registry_dir(name)`, `Settings.lake_dir`, and build products with `load_settings(root=...)` (as `sus_dependent.load_ans` already does). Size S.

**T6. Direct readers of another store's layout** — part done: the SIDRA fact parts (`sidra.store.fact_parts`) and a dataset-year's lake files (`persist.lake.published_files`) are listed by their owners; the cube cache and linkage's role tables call them (the listings identical: 5,733 parts; SIH, SIM, SINASC, CIHA years). Left: `intake.py:810,856`, `extract.py:335`, `serve/_membership.py:51`, `lookups.py:73`
- `linkage/roles.py:319` (`lake.glob(f"{system}_{series}_*/**/year={year}/*.parquet")`, a second reader of the lake's family/partition layout; `persist.lake.Lake` owns it),
  `intake.py:810,856` (globs the lake for its own parts; owner of writes, but should use `Lake.family_dir`/the catalog's partition rows),
  `cubes.py:260` (`table=*/req-*.parquet` = the SIDRA store's layout, duplicated from `sidra/store.py:149,193`),
  `extract.py:335` (`year=*/*.parquet` of its own extract), `serve/_membership.py:51` (the pack file read directly), `lookups.py:73` (registries glob).
- Fix: each store exposes `parts(...)` / `fingerprint(...)`; consumers call it. Size S per site.

**T7. Dataset spelling and system aliases still hand-mapped** — part done: `column_roles.declared_key` reads the system's declared spellings (`system_spellings`) and matches pattern-keyed roles files (`SINAN-*`) instead of a hand alias map; all 185 catalog datasets resolve to the same roles file. Left: `registry.OWNER`, `curation.INHERITS`, `modelled.OFFICIAL_SERIES`
- `semantics/column_roles.py:569-575`: `{"SIHSUS-RD": "SIH-RD", "CIHA-CIHA": "CIHA"}` and `system.upper() == "SINAN" and "SINAN-*"` (RESIDUE of defect 8: "one dataset spelling").
- `registry.py:266` `OWNER = {"CADGER": "CNES", "UNIDTOTAL": "CNES", CNPJ_TABLE: "CNES", "INE_EQUIPE": "SIASUS"}`; `semantics/curation.py:1014` `INHERITS`; `modelled.py:41` `OFFICIAL_SERIES` (system names).
- Fix: aliases in `curation/datasets` (`aliases:`), `owner:` on registry tables in curation; roles files declare `applies_to: SINAN-*`. Size S.

**T8. Registry/CNES key and label column guesses**
- `registry.py:254-255` (`CHAVE, CNES, CODIGO, CO_EQUIPE, INE` / `DS_REGRA, NOMEFANT, NOME, NO_EQUIPE, DESCRICAO` tried in order), `registry.py:198-199`
  names `CNES-ST`; `semantics/tabkit.py:42-70` (`KNOWN_CODE_TABLES`: 17 table prefixes to code/label columns, verified per its comment but still code),
  `profile/detectors.py:50-55,523` (name hints; acknowledged open in STATUS item 6 as "the profiler's name hints still serve undeclared columns").
- Fix: kit-table roles in `curation/` (`code_column`, `label_column`) for the CADGER kit and tabkit; detector hints are the declared remainder. Size M.

**T9. SIA pre-2008 establishment naming duplicated twice in `persist/reference.py`** — done: one list (`reference.sia_establishment_tables`) for the reader and its fingerprint, same tables in the same order
- `persist/reference.py:419-427` (`UPS-N{uf}`, `CNESN{uf}`, `CNESN{uf}1/2/3`) and `:655-656` (same list again for the fingerprint); `:457` (`"CIRBRN"`, `"health_region"`); `:464-470` `CLASSIFICATIONS` map; `labelpack.py:675,757` (`"CNES"` namespace literal).
- The list is a fact about DATASUS kits and exists twice; adding `CNESN4` would update one and silently not the fingerprint.
- Fix: one `SIA_UPS_TABLES(uf)` generator (or declare the pattern in curation) used by both. Size XS.

**T10. Bridges and standard names in `view.py`**
- `view.py:546-549`: `BRIDGE_NAMES {"A": "SIGTAP_A", "H": "SIGTAP_H"}`, `BRIDGE_TARGETS {"SIGTAP_A": ("SIGTAP", 10), "CBO94": ("CBO2002", 6)}`, `BRIDGE_UNIQUE = 0.95`.
- Which classification a bridge lands in, and the widths 10 and 6, are data facts.
- Fix: `bridges:` in `codelists.yml`. Size XS.

**T11. Enrichment targets as strings in the executor and planner**
- `_query_engine/executor.py:395-410`, `_query_engine/planner.py:148-154` (`"CNPJ"`, `"CNES"`, `"CNES.ESTABLISHMENT_NAME"` branches), `crosswalk.py:41`, `:202` `CADGERBR`, `:213-215` (`hi.startswith("9999")` sentinel in `DATAEXCL`, `[:6]` of a date), `_query_engine/semantics.py:319` (`190001 <= value <= 219912`), `:427`.
- Three targets are hand-coded branches; `9999` as "no end date" is a sentinel rule written in code, not the field's ledger.
- Fix: enrichments as declared relations (`links.yml`) dispatched by name; the "open end" sentinel in the registry table's schema. Size M.

**T12. Per-source readers carrying code tables and layout facts**
- `sources/pes.py:23-48` (hand-typed IBGE tables 9, 10, 12, 1: ~90 numbers), `sources/ibge_tracts.py:32-39` (file name with a date `20260520`, `SEX_BANDS` V01009-V01030 by position),
  `sources/census_commuting.py:44-54` (fixed-width layout, SIDRA ids), `sources/ibge_cnefe.py:79-101,480-484`, `sources/bnafar.py:78` (`SOLID_ORAL = {"U0042": "COMPRIMIDO", "U0041": "CAPSULA"}`, with its measurement in the comment), `geography.py:915` (`_SEAT_CATEGORIES` IBGE category names), `sources/ibge_biomas.py:22` (`NOT_MUNICIPALITIES`).
- These are source adapters, and the comments carry evidence, so tolerated individually; but tables of published numbers and code meanings belong in `resources/` or `curation/` with their source and date.
- Fix: move numeric tables (`pes.py`, `SOLID_ORAL`, `SEX_BANDS`) to a curated YAML/CSV with `source:` and `as_of:`; keep layout constants. Size M.

**T13. Study modules duplicate axes and analytic choices**
- Ages: `population_account.A = 81` (:40), `population_tensor.AGES = 101, OLD = 21` (:163-164), `completeness.AGES = 101`, `rates.BANDS` (5-year to 80+), `modelled_race.AGE_BANDS`, `sus_dependent.ANS_BAND`.
  UF lists: `completeness.UFS:27`, `modelled_race.UF_CODES:68` (copies of `config.UF_NUMERIC`), `ontology.UFS`.
  `COVID = (2020, 2021, 2022)` (`population_forecast.py:26`), `WINDOW = 10`, `LAG_GROUPS` (`population_account.py:448`), `PRE_SCALE`, `KAPPA`, `ALPHA_SD`, `NATIONAL_DRIFT`.
- COVID years excluded from the trend fit is an epidemiological choice hard-coded (CLAUDE.md: "every hand-fixed choice is a debt to learn or integrate over").
- Fix: UF lists from `config.UF_NUMERIC`; study constants into each product's manifest/`products.yml: parameters:` with their rationale; ages one axis. Size M.

**T14. Single-purpose study builders write straight to parquet by path**
- `completeness.py:59`, `population_account.py:300,335,516`, `population_forecast.py:41,47` read `events_dir/{deaths,births}_{year}.parquet` (a private file convention written by `collect_events:225`), with columns `residence`, `sex`, `age`, `events`.
- Closed in part by defect 3, but the intermediate file convention is still a second store.
- Fix: read the events through `cube("records:SIM-DO/...")`; drop `collect_events`. Size M.

**T15. Non-obvious UF abbreviation/code tables replicated** — part done: the cubes read state codes from `geography.uf_codes_by_sigla` (SIES 2023 11,518 rows as before); the profile detector and registry lists remain
- `cubes.py:421,671` build `{abbr: int(code)}` from `UF_NUMERIC`; `geography.py:1148-1162` reads sigla from the pack; `profile/detectors.py:291`; `registry.py:186` `_UFS`; `persist/reference.py:405` `_UF_CODES`. Four spellings of "the UFs".
- Fix: `config.UF_NUMERIC` plus two derived constants in one place. Size XS.

**T16. Unit/format dictionaries in code**
- `linkage/roles.py:60` (`_FORMATS` date patterns), `profile/detectors.py:206` (`unit_legend {"1": "hora", ...}`: age-unit meaning in the profiler, which ADR-0218 moved into `IDADE_anos` curation for decoding), `intake.py:881` (`MONTHS_PT`; another month table exists in `discovery/listing.py`), `linkage/model.py:64` (`_PAD` digit table: algorithm constant).
- Fix: profiler reads the age-unit table from `curation`; one month-name table. Size XS.

**T17. Two ways to resolve a hospital race-confusion population / NEST** (minor)
- `modelled_race.py:624` strings `"SIM.DO"` and `"SINASC-DN"` in a manifest (two different spellings of a dataset in one dict); `linkage/timeline.py:108-118` calls `_records("SINASC-DN"/"SIH-RD"/"SIM-DO")`, `DELIVERY` etc. - study modules naming datasets in code (defect 3 style).
- Fix: `ontology.dataset_key`, and the timeline's datasets from the link declarations. Size XS.

**T18. Linkage and engine thresholds**
- `linkage/engine.py:58-60` (`CHANCE_DROP = 20.0`, `MIN_COMPARED = 30`), `linkage/discover.py:61-62,146-147` (`SHIFT_DAYS = 7`, `MAX_INTERVAL_DAYS = 60`, top-5, top-3), `linkage/placebo.py:36-45` (`PLACEBO_DAYS = 182`, `KEY_REACH = 0.5`, `BLOCK_MIN_EXPECTED = 30`), `semantics/label_bindings.py:45-55,505` (`TOO_WEAK 0.5`, `SHARE_TIE`, `MIN_EVIDENCE = 5`, `0.95`), `semantics/icd.py:393` (`0.10`), `inventory/systems.py:33-36`, `semantics/coverage.py:40` (`0.9999`), `persist/reference.py:938` (`BLANK_LABEL_THRESHOLD = 0.9`).
  About 25 analytic thresholds not in curation (the linkage verdict bands already live in `links.yml`).
- Violates: hand-fixed thresholds (principle 4/"always ask whether it can be made better"). Not semantic: they gate diagnostics and verdicts.
- Fix: one `thresholds:` block per subsystem in curation, with the measurement it came from. Size M.

---------------------------------------------------------------------------------------------------------------------

## STRUCTURAL, further second-mechanism notes

**T19. `geography.py` fetches and composes multiple stores by hand**: `memberships`, `classifications`, `mesh_file`, `_pack_path` and the registries are all in one 1,164-line module with 4 `pq.read_table` sites (`:366,451,608,679,1096,1153`) of different packs; no single `pack(name)` reader. Fix: `geography._pack(name)` with the mtime cache already at `:676`. Size XS.

**T20. Two label-lookups paths** (view vs lookups): `view.py:1103-1108` interprets `code_system` (`internal`/`external`/`none`) in the renderer while `lookups.py` and `persist/reference.py` resolve codelists; `suggest.py:189` also tests `code_system in ("internal","external")`. Three modules branch on the same pair of strings. Fix: one `CodeSystem` enum/predicate in `semantics/curation`. Size XS.

**T21. Registry reader duplicated for the CNES lookup** — done: `registry.facility_names` (692,004 establishments), read by the timeline and the name enrichment (FUNDHACRE for 2001586 as before); the crosswalk's CNPJ lookup is another question and stays: `crosswalk.py:202`, `linkage/timeline.py:89`, `_query_engine/semantics.py:427` each call `lookup("CADGERBR", "CNES", ...)` and rebuild a code-to-name dict. Fix: one `facility_names(settings)` using `column_roles.facility_code_field`. Size XS.

**T22. Dated sentinels "9999"**: `linkage/timeline.py:191` sorts missing dates as `"9999"`; `crosswalk.py:215` treats `9999*` as open end; `profile/detectors.py:46` has `DATE_SENTINELS` as a global set (the file itself says it is per-field). Fix: per-field sentinels from the ledger only. Size XS.

**T23. `view._apply_derived` and `_aggregate` both bucket ages/bands** — done (this commit): `_age.bands`, outputs equal; `ibge_tracts.BANDS` buckets nothing, and `rates._band`, `modelled_race.age_band*`, `ibge_tracts.BANDS` implement the same "closed-open band by edges" in numpy/Python separately. Fix: `_age.bands(values, edges)`. Size S. Follow-up: the race model's bands keep an unknown age as -1 and leave that death out of the fit (the routing had put it in band 0, and before it the last band).

**T24. `retrieve.py` and `fields.py` read registries/mesh through hard-coded subfolders** (see T5) and `fields.py:556-592` names INMET and BR-DWGD caches inline. Folded into T5; listed separately because both are field readers whose stores STATUS calls "the only stored ones left".

---------------------------------------------------------------------------------------------------------------------

## HYGIENE (H)

**H1. Unreferenced functions (no caller in `src`, `scripts`, `tests`, docs or CLI)**: AST scan, one occurrence = the definition.
- `completeness.py`: `census_uf:40`, `events_uf:54`, `interval_events:83`, `growth_balance:100`, `build_completeness:207`
  (the whole module is reachable only through nothing; `ill_defined_shares` is called only by `build_completeness`).
- `population_account.py`: `build_registration_completeness:1009` (reads `collect_events:225`, which has one test reference).
- `population_backcast.py`: `area_matrix:188`, `member_totals:202`, `split_shares:231`, `backcast_tables:295`, `write_product:349`.
- `population_tensor.py`: `build_account:636`. `sus_dependent.py`: `build_sus_dependent:84`. `modelled_race.py`: `confusion_row:418`.
- `cubes.py`: `cube_manifest:840`. `labelpack.py`: `build_crosswalk_pack:726`. `pipeline.py`: `schema_signature_for:1155`.
- `semantics/gaps.py`: `gap_report_json:279`. `semantics/ledger.py`: `field_report:436`.
  (`sources/bnafar.py:program`, `measures.merge_all`, `semantics/relations.seed_relations/ensure_adjudication_item`,
  `config.label_build_catalog` and `_query_engine/coverage.compile_capability_payload` have tests/scripts references only.)
- 23 symbols with no caller; 6 of them are the "build" entry points of modelled products (population account, backcast,
  completeness, SUS-dependent) with no CLI command and no RUNBOOK mention: either wire them to `pegasus-data` (the products exist in `products.yml`) or delete them. Size S.

**H2. Unused imports** (codehealth): `cli/__init__.py:21` (5 names; side-effect registration, probably intended), `linkage/entities.py:30` `pyarrow`, `retrieve.py:51` `DownloadBudgetExceeded`. XS.

**H3. Five import cycles** (codehealth), the large one through `api -> readplan -> normalize.engine -> semantics.dictionary -> persist.reference -> labelpack -> semantics.curation -> intake -> fields -> _explore -> retrieve -> _dictionary -> api`; handled by local imports (there are ~150 function-level imports). The cycle between `geography <-> sources.ibge_grade`, `view <-> semantics.label_bindings`, `_request <-> ontology` could be broken by moving the shared helper. M.

**H4. The legacy normalize/fetch path** (`normalize/engine.py`, `retrieve._read_families`, `build.py:535`) still carries `to_seven_digit` (S1), `MunicipalityIndex`, `SOURCE_EPI_WEEK_FIELDS` and the profile detectors; STATUS names the lake/intake path as the one door. Verify which of the two paths `query` reaches and remove the other (largest dead-code candidate: `profile/`, 677 + `normalize/` 467 lines). L.

**H5. Oversized functions with 100+ cyclomatic complexity**: `semantics/column_roles._column` (141, 152 lines), `view._render_table` (117, 435), `cubes._records` (115, 256), `_query_engine/executor.query` (106, 375), `_aggregate.aggregate` (95). `retrieve.fetch` has 32 parameters, `api.load` 25, `api.export` 22. Not a principle breach; a place where special cases hide. M.

**H6. Naming/doc drift**: `intake.py:1405` comment-level "same rule" claims (see S2); `geography.py:648`. XS.

**H7. `docs` contradiction**: STATUS says the CADGER kit's name columns are in no roles file (open), and the register lists item 6 closed. Not a code finding; the T8 entry carries it.

**H8. Worktree residue**: `.claude/worktrees/agent-ad7a19c743a81dcef/` holds a full second copy of the repo (including `src/`); it is untracked (`?? .claude/`). Greps over the repository root hit it; remove when the agent is done. XS.

---------------------------------------------------------------------------------------------------------------------

## Checked and clean (no finding)

- No `== "SIM"`-style branching in the query/lake/cube path; the only system literals in logic are in `completeness.py` (S6), `fields.py` CNES (T1), `column_roles.py:574` (T7).
- `fill_null(0)` on measures: `_aggregate.py:704` fills only `_n` count states (correct: a count of nothing is 0; sums stay null), `cubes.py:454` is documented and keeps null when no part holds a number.
- `ljust`/`rjust`: only in display code and the bisect key in `cnv_parser.py:583` (algorithmic).
- `zfill` in `cnv_parser.py:543,558` and `labelpack.py:164,828` implement TabNet's documented width rule (the unpadded alias is deliberately not emitted).
- Direct lake reads in `adopt.py` and `intake.py` writers are the stores' own owners.
- Hand-written code to label dicts: only `bnafar.SOLID_ORAL` (T12) and `profile/detectors.py:206` (T16); no `{"1": "Masculino", ...}`-style label table in code.
- Defect-3 residue check: no module under `population_*`/`sus_dependent` touches `lake/` paths for SIDRA or ANS any more except `population_backcast.py:360` (T5) and `modelled` writes (via `write_modelled`).

## Top 8

1. S1 normalize/geo.py invents the municipality check digit (second 6-to-7 mechanism, contradicts `to_code7`).
2. S2 intake SQL placing rule lacks `legacy_places` and trims differently from `place_municipalities`.
3. S3 `sus_dependent`: non-M sex becomes female; coverage class by first letter of a corrupted label.
4. S4 sex by label first letter (`population_account.sex_of`); race `lstrip("0")`.
5. T1 CNES recipes carry 15 column names, 3 "1 means SUS" filters in `fields.py`.
6. T2 seven number parsers; T3 about fourteen period parsers.
7. S5 `quality.race_reliability` hard-codes RACA_COR 03/04 meanings.
8. H1 + H4 23 unreferenced functions (6 product builders with no entry point) and a probably-dead legacy normalize/profile path.
