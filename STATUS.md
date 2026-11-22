# STATUS.md

What is true now. This file is rewritten in place, never appended to. Its
history is in git; measurements are in `EVALUATION.md` and decisions in
`DECISIONS.md`. The opening section and the architecture review written 2026-11-21, the next sections 2026-11-09; the declarations section 2026-10-08; the population and
climate section 2026-10-24.

## Where the project is

One branch, **`master`**. It is on GitHub to bd867e4; the commits since are local (the author pushes). The work of
2026-11-21 was an architecture review of the whole package (below); before it, the release: one map of what the package
holds and can do, one space × time object, and the principles audits' defects closed one by one.

- **The map** (ADR-0216). `compendium()` and the home's copy (`_compendium.current`) describe:
  - every dataset `query()` serves, each column's query-time codelists and fill;
  - the context fields, roles, events, links, aggregates and SIDRA's tables;
  - the 50 products of `curation/products.yml`;
  - every function and command.

  `search()` reads it. A stale map is served while one detached process rebuilds it (52 s; it was 11 min). The map
  is also written as text files to grep, the manual (`<home>/manual/`, `INDEX.md` about 850 tokens; plan
  agent-interface): `pegasus-data info` prints its index, `info --all` the overview (about 420 lines). It also lists
  the home's undescribed stores; one is left, `registries/tse` (the electorate zip, no reader yet).
- **Storage and speed (2026-11-21/22).**
  - The record key is computed on read, not stored (ADR-0231): the lake went from 42.9 to 27.1 GB and the role tables
    from 13 to 2.8 GB.
  - Row filters drop raw rows before normalising: the SIH-SP extract is download-bound, 5.6 → 2.8 s a file.
  - Intake units land four at a time: TISS 0.33 → 0.9 units a second.
  - Every DuckDB spill directory is per process.
  - A cohort link's passes are judged horizon by horizon (LINKAGE_VERSION 5), so every stored run is recomputed once.
  - ANS TISS hospital files 2015-2025 are landing nationally.
  - The science of the ABNc 2027 studies runs in its own session (`../abnc2027_neuro`).
- **The catalog's open questions.** None are open; the 733 were noise or answered (ADR-0216). Real ones are in
  `OPEN_QUESTIONS.md`.
- **SI-PNI per-dose records** are declared on request (`PNI.DOSES`, 200 GiB zipped, built by naming years). June 2020 is
  landed and verified. Intake writes are sorted by place and month, about 30% smaller.

## The modelled studies revisited (2026-11-21, ADR-0226; docs/plans/population.md)

- **Population account.** `model-build population_account` had been broken by the move to `studies/` (an import);
  fixed, and the rebuild equals `population-account-7` in every cell. Its difference from POPSVS is written term by
  term (evaluation 2026-11-21-account-against-popsvs). It is now an **open research line** (`docs/plans/population.md`,
  units P1 to P6): first runs of births and the electoral roll as symptoms cut the 2010 to 2022 error by a tenth and do
  not transfer to 2000 to 2010. Next: the benchmark as one function (P1), the closing census's own error (P4).
- **`population-account-8`** (ADR-0227): the 2022 census at IBGE's corrected population, as 2000 and 2010; 210.863 M in
  2022, 0.0167 RMS from POPSVS at 2022. `-7` stays stored.
- **What a reader gets differently since 2026-11-21** (for any study running on this home): the latest
  `population_account` is `-9` (every state, year, sex and age at IBGE's, ADR-0228; 2022 total 210.863 M, was 211.962 M; by municipality size up to -5% in the largest and
  +3% in the smallest against `-7`), so `field_rate` and the `modelled:population_account` cube changed with it (name
  `population-account-7` to keep the old one); `load_population` (POPSVS, the census) is untouched. The latest
  `race_confusion_women` is `-2`. Link role tables rebuild once (7-digit municipality codes placed).
  **SIM and SINASC** (ADR-0230): SIM-DO 2009, 2011 and 2013-2017 and SINASC-DN 2006-2012 are now read from the 27 state
  files, where the national file cut the cause lines (`LINHAA`..`LINHAII`) or the anomaly codes (`CODANOMAL`); the
  records and every other column are the same, row counts unchanged, and the lake holds one reading per year (the
  national partitions of those years were pruned, as were 40 unlisted leftovers). A run that read those partitions
  while they were replaced (21 Nov, 14:30-15:00) should be run again; role tables of those years rebuild once.
  **SIGTAP procedures** are labelled only inside their window (0403070171 from 202312); `link(..., match="procedure")`
  and `sih_readmissions` are new; CNES neurosurgery fields (`cnes_neurosurgeons_*`, `cnes_accreditation_*`,
  `cnes_beds_neurosurgery`, ...) are declared. Also new: a `stay` event type for SIH-RD (AIHs chained by person, discharge reason and day;
  `hospitalisation` unchanged), `sih_admissions_to_radiotherapy`, census tract aggregates (`tract_aggregates`), and
  a partition whose files differ by a column is written as several part files (SIA-AQ 2013-2015 had failed).
- **Race.** A third reference: a death linked to the dead person's own birth (`sim_deaths_to_own_birth`), giving
  `race_confusion_child` (ages 1-14, children born from 2012). The birth record's colour is the mother's only from the
  2011 form. False links are priced per pair, inside the municipality; `race-confusion-women-2` is the women's product
  under that model. From 15 a man is recorded darker than a woman of the same colour at birth: the women's matrix is
  not carried to men. Open: adults over 24, and 15-24 under a reference comparable with the census.
- **Race, concluded 2026-11-21** (docs/plans/race.md, evaluation 2026-11-21-race-own-birth): children's mortality by
  declared race for the whole country, without a matrix (ADR-0229: Branca 0.66 of Parda at ages 1-4, certificates say
  1.43); at 15-24 the certificate depends on the kind of death (white at birth and killed: certified Branca 0.33-0.38);
  cohorts change declared race through life (53% Branca at birth, 39% at 20); for a death in hospital the hospital's
  race stands in for the declared mix better than the certificate. No adult product; the bridges are usable for Branca
  against Parda in small municipalities, not for Preta alone.
- **Population, concluded for now** (docs/plans/population.md): the yearly signals stay out of the forecast (they do
  not transfer across three truths); groups of municipalities and age groups have tested interval laws
  (`population_benchmark`); race intervals wait for the next census.
- **Linkage.** A 7-digit municipality code (SINASC to 2005) is placed in link roles; before, a link on residence over
  those years found nothing, silently. Role tables rebuild once (`ROLE_TABLE_VERSION` 2).

## The architecture review (2026-11-21, ADR-0222 to ADR-0225)

The author asked for an assessment of the architecture and then handed the work over. What changed, each against the
outputs it replaced (evaluation 2026-11-21-architecture-review):
- **One read path.** A read is one `ReadRequest`, two sources (`api.read_lake`, `retrieve.read_source`) and one
  finishing stage; `load` and `fetch` carry no private switch. `scripts/read_equivalence.py` (thirty real reads) is the
  gate of any change to it. The file selection the builder and the reader each wrote is one function
  (`representations.select_publications`).
- **Declared shapes.** Every curation file is checked against its kind's schema where it is parsed; a misspelt key is
  refused by name. It found twenty `intake.yml` descriptions cut at a comma.
- **Kept artefacts.** One atomic-write and build-on-miss mechanism (`persist/kept.py`) for about twenty copies; a cube's
  version leaves out the layers above it, so an edit to a command or a study rebuilds no cube.
- **Layers.** Declared and checked (`scripts/layers.py`, in CI): no module-level upward import; 34 function-level ones
  listed. The study builders are `studies/`; `intake.yml`'s declarations are read in the meaning layer; 152
  function-level imports hoisted with start-up unchanged.
- **Types.** `mypy` is clean and blocking in CI (256 findings cleared).
- **Long functions.** Sixteen over 200 lines became three, each split verified on its outputs.

**Defects found on the way, fixed.**
- `population_account.vital_events` raised on every call since 5fbfe1d (2026-11-09): the population account could not
  be built. Found by the type checker.
- A read reported label-fallback warnings for months it never asked (a memoised table's month).
- Twenty intake column descriptions truncated by YAML.
- The cube cache shared one temp name between processes and deleted the old version before writing the new one; the
  reference stamp missed a label edited to the same length; the records cube's version left out the geography pack.
- A pattern-declared roles file was matched against `None` for a dataset with no series.

**Left, with reasons.** Three build functions over 200 lines (`labelpack.build_label_pack`,
`Builder._materialise_partition`, `Builder.build`): a split is verified only by a label-pack or lake build of hours.
`scan()` and `export()` keep their own parameters. `read_events` and `count_events` stay in `semantics/event_types.py`
(PegaSUS imports them there). Modules are not grouped into folders per layer, and the 121 public names are unchanged
(PegaSUS and 225 records name them). **To do after this merge on the real home:** `pegasus-data curate` (the
`intake.yml` descriptions changed), and records cubes and reference stamps rebuild once on their next read.

## The space × time unification (docs/plans/cubes.md, ADR-0217)

Thirteen mechanisms made place × time tables. The cube (`cubes.py`, `cube()`) is the one object: one long shape,
roll-ups only along the source's additivity, named by where it comes from.

| stage | state |
|---|---|
| 1. core and SIDRA | **done.** Any SIDRA table is a cube without a declaration. The 26 SIDRA and series fields are views of their cubes (26/26 equal) and their copies are removed |
| 2. records on roles | **done in code.** `records:<dataset>/<event or rows>` serves events, rows, sums of one or several columns, and distinct counts. It takes `where` as codes, prefixes, exclusions, bounds or two-column codes; months as periods; a support mask; one geography's publications. Bindings are curated or read from the roles. Cubes are cached by their data's fingerprint. Every intake count, sum and outcome share is a view: SISAGUA's 33 equal, yellow fever equal, SRAG lower by its 29 duplicate notifications. The full national rerun (2026-11-09, on 90717dd and after) found every cube-served field equal to its stored copy, and the 91 copies (843 MiB) are removed. S2iD's records are landed (76,190 events) and `disasters` is a view of them (`fields.rows_view`: every row equal to its copy, which is removed). SIES is a state-level records cube (a place binding whose values are states; its two fields equal, copies removed). INEP's school records are landed (2021-2024) and its margins are one cube per column (`fields.margins_view`: 334,200 cells equal; 2023's total 47,304,632 as verified). Every field is now a cube or a view; only BR-DWGD's monthly base and INMET's stations are stored |
| 3. CNES through the one reader | **done in code.** The mirror's 1,728 DBCs are adopted (5/5 sampled byte-identical to the FTP). All 43 CNES fields are cubes over December's register: the 25 supply fields equal for all 16 years (the neonatal ICU field adds 2008-2009, which its copy lacked), and the 18 professionals' fields equal for Acre 2015. **Done.** All 43 equal their stored copies nationally, every year (2026-11-09, after the Brasília fix), and `sources/cnes.py`'s mirror pipeline is removed |
| 4. gridded, population, modelled | population cubes done (`population:<series>`); BR-DWGD's six annual fields are views of `climate:<measure>` over the stored municipality-month base (356,032 rows each, equal). Modelled products are cubes (`modelled:<product>/<estimate>`) on axes each manifest now declares (place, period, strata, additive estimates; the 11 stored versions given theirs): the 2022 account sums to the file's 211,961,662, and a non-additive estimate refuses an implicit total. The climate family is one adapter: `climate:<measure>` (BR-DWGD), `climate:inmet/<measure>` (INMET's station-months, the station a stratum, never summed; equal to the stored `climate` field cell for cell, 1990 and 2023) and `climate:cptec/<variable>[@area]` (CPTEC's daily grids by day, epi week, month or year, sums with the days held; `climate_weekly` is now its epi-week roll-up, equal on 5,304 Alagoas weeks). The stored bases `climate_monthly`, `climate` and `climate_daily` stay: they are the observations, nothing was removed |
| 5. one door | **done (2026-11-09).** PegaSUS's `contexts: auto` gives the same contexts before and after the stage (220,954 estimates, 0 differ; every declared context to 4e-16). An aggregate artifact is its manifest; its cells are the recipe's records cubes, read by the one loader `aggregate()`, `capabilities()` and `serve/` share (`cells.parquet` gone). Measures from cubes: counts, sums, means, moments, log-moments, min and max (`ratio`, a mean under another name, removed). `/population` reads the population cube (one placing rule; a state-filed series refuses a municipality). Every intake field is a cube or view (`intake._derive` and the stored-field writers removed). `semantic_axes` no longer declares an axis: a binding names roles, code systems and period forms are the roles' (`precision: month`), and the binding names stay a curated vocabulary (ADR-0221). Recipes stay YAML: they carry labels and measures. **Left:** 86 month-named date roles not in the lake declare no `precision` (read correctly by measured layout; declared when their files are read) |

**Found on the way, repaired (2026-11-09).** `pegasus-data families` deleted every family it does not derive from the
crawl, the intake's among them. SRAG, SISAGUA, SNGPC, FA, BNAFAR, SIES and REGIAO were unreachable by `query`. The
stage now keeps intake families, and `pegasus-data intake-register` restored 391 partitions (711,680,059 rows) from
disk.

## The principles audit (2026-11-08): open defects

Ranked. Evidence is in the session audit, summarised here; each is closed by replacing the special case with the
general rule.
1. ~~CNES has its own pipeline~~ **closed:** all 43 CNES fields are records cubes through the one reader (equal to their
   stored copies nationally); `sources/cnes.py` and `_build_cnes` are removed.
2. ~~One column, three declarations~~ **closed (ADR-0219):** linkage reads `compare:` from the roles files
   (`roles.yml` deleted, 108 roles equal); the intake's `role:` is `description:`.
3. ~~Study modules name datasets and columns in code~~ **closed (2026-11-09).** The population account's inputs
   are declared on its product (`inputs:` of `products.yml`: event types and strata roles, `column_roles.column_of`);
   sex is read from its label by one function (`sex_of`) where four modules kept a code map; the 48 collected files
   were rewritten in that form, and every reader's output is equal. The account, the tensor, the backcast and
   completeness read SIDRA through `cube()` and censuses through `load_population`, not lake paths; every function
   returns the same arrays. ANS's records are landed (602 MB, 2021-2025), its field is a records-cube view, and `sus_dependent`
   reads it and its unplaced links through the API (the cube's count equals the old SQL: 42,301 in 2022, 44,800 in
   2024). Closed.
4. ~~Age encodings named per system~~ **closed (ADR-0218):** five forms with the unit table as data, declared once on
   each system's `IDADE_anos`; the 59 aggregates name the variable. Decoding equal on six systems' records.
5. ~~Linkage cardinality hard-coded~~ **closed (9958a80):** read from each dataset's roles file (`persons:`).
6. ~~Column names guessed in code~~ **closed:** the enrichment's key and a record's own CNPJ are read from the roles
   (`column_roles.facility_code_field`, `facility_cnpj_field`; `OWN_CNPJ_FIELDS` and the `"CNES"` defaults gone), the
   register's key from CNES-ST's roles, the profiler defers to declared roles (`declared_verdict`). SIH-RD and SIA-PA
   2022-01 AC enrichments equal before and after; SIA-PA `enrich=["CNPJ"]` and SIH-RD `["CNES"]` now work. The CADGER
   kit's name columns are declared since 2026-11-09 (`codelists.yml` registry `establishments`); the profiler's name
   hints still serve undeclared columns.
7. ~~Hand-fixed lists and thresholds~~ **closed:** the CNES groups already live in `fields.yml` (`cnes:`, read by
   `groups()`); the codebook cut moved to `codelists.yml` (`codebook:`), the linkage verdict bands to `links.yml`
   (`verdict:`, ADR-0107), values unchanged; the UF lists derive from `config.UF_NUMERIC` (`UF_ABBREVIATIONS`).
   UF sets and 20 `judge()` verdicts identical before and after; the last list went with `sources/cnes.py`.
8. ~~Repeated plumbing~~ **closed (33a0d62):** one dataset spelling (`ontology.dataset_key`, 10 sites), one YAML reader
   (`curation.read_yaml`, 12 modules), snapshot and SIGTAP on the project transport. `semantics_for` on 12 spellings
   hashes the same before and after; SIGTAP listed 227 exports and fetched one at its listed size.
9. ~~Declaration sprawl~~ **closed:** the 54 generated SINAN recipes are one template on `sinan_agravos.yml`
   (`_aggregate.family_specs`; dengue keeps its own file): all 60 specs equal field for field, 19 descriptions now
   name the agravo where they gave its code. **Row facts** (2026-11-09 inventory, docs/plans/cubes.md §6): of 148 datasets with a roles `record:` and a doc unit, 25 differ (coarse linkage tag vs grain, not copies); SINAN's 53 repeated `unit_of_analysis` stated once under `shared:` (describe, dataset docs, grains identical before and after). The roles' `record:` (a typed class) and the docs' `unit_of_analysis` (prose grain) are two facts, each with one home: closed (docs/plans/cubes.md §7).
10. ~~Overloaded terms and code serving `pegasus_view`~~ **closed:** GLOSSARY "Vocabulary" gives field, role and source one
    meaning each. No module had pegasus_view as its only consumer (`presentation`: api, CLI, executor; `capabilities`:
    `workbook`, `_compendium`, `serve`; timeline routes: `s_timeline`), so none was removed; its start script and
    wording left RUNBOOK, workbook and the docs. Nothing in `../pegasus_project` imports them.

## The second principles audit (2026-11-09): closed

The audit (`docs/plans/principles-audit-2.md`, 45 items, a read-only sweep) was the work plan; each item was verified
before it was fixed and is marked there with its evidence (evaluation 2026-11-09-principles-audit-defects).
- **Done:** every semantic item, S1-S9 (codes placed by the one rule, sex and race read by their labels and widths,
  unknown kept unknown, missing kept missing, code meanings and thresholds of the study modules declared), and T1-T18,
  T21, T23, T24: one number reader, one period module, one banding, one municipality reader; the CNES recipes, the
  bridges, the enrichment targets (`joins.yml`), the register kits' columns, owners, open end and code tables
  (`codelists.yml`), the published tables of the source adapters (`published_tables.yml`), the study constants
  (`products.yml` `parameters:`) and ~20 thresholds declared; every folder of the home through `Settings`; every store
  listed by its owner; the study modules read their events through the records cube (no event-file store).
- **Found on the way and fixed:** the records cube counts an event coded "Município ignorado - <UF>" in its state and the
  country and says it by state at municipality level (`unplaced_by_state`); a record date filed without its day, or as
  its year alone, keeps its month or year (SIM-DO 2000: 497 deaths). With both, the cube equals the old event files in
  2000, 2012 and 2022.
- **Checked, no change:** H2 (deliberate imports), H4 (the normalize path is live), H6, T19, T20, T22.
- **Checked, kept (code shape, not principle):** H1's last test-only helpers (`measures.merge_all`,
  `ensure_adjudication_item`); H3: `scripts/codehealth.py` lists 6 cycles (`proximity`/`ibge_grade` broken), each a real
  two-way relation closed by one function-level import (a store installs the seed a store writes; an ontology lookup uses
  the request parser that consults it; an orchestrator calls a stage that reads its constants), so a third module would
  serve the graph, not the code; H5: codehealth flags no long function, and `column_roles._column` is a validator whose
  branches are its rules.

**R1. The modelled products could not be rebuilt from the repository (found 2026-11-09): closed: all six rebuild from the repository.**
`pegasus-data model-build <product> --version V --validation TEXT` calls the function each modelled entry of `products.yml`
declares (`build:`): `population_tensor.build_population_account` (the events of 1991-2023 into the work area, SIM-DOR to
1995; account, calibration, forecast, split, race, shapes, migration schedule, backcast; 25 minutes), `sus_dependent`,
`completeness`, `population_account.build_registration_completeness`. Each was rebuilt under a check version and compared
with the stored one (evaluation entry 2026-11-09-principles-audit-defects, row R1); the check versions are deleted.
`population-account-6` reproduces to the last float32 bit (37 of 219 M cells, 1e-7) once the placing rule of October is
restored, and differs by at most 9e-5 in 2001-2021 (0.16 on cells of a few people in 1991-1999) under today's rule, which
places 5 deaths and 8 births of 2000-2010 differently; `system_completeness` is equal; `sus_dependent` differs only where
ANS republished its December files; `registration_completeness` by 2.5e-5 in 2 of 108 cells. `race_confusion_infant`
(`modelled_race.build_infant_product`) assembles its inputs from the stored `sim_infant_deaths_to_sinasc` runs and role tables
(63,769 deaths, 52,063 linked, the cross-tab equal to the scratch table in all 80 cells) and refits to the stored scales and
held-out log loss (0.8091), its estimates within MCMC noise (mean |dp| 0.002). `race_confusion_women` (`build_women_product`)
assembles 106,565 deaths of 2015-2022 (19,332 linked) with the false-link share per municipality class (about 1 hour 40 minutes:
a pass per death year, 94 s to 683 s, is the cost; nothing is cached). Its default scale selection (2015 against 2022) diverged
(800 of 800 draws), so `build` refuses a diverged sampler and the product declares the selection of the stored version
(`scale_selection`: train 2015-2016, score 2017-2018; `build(selection=)`). Under it the fit has no divergence (R-hat 1.014, ESS 53)
and the scales equal the stored ones except age 1.5 for 0.5 (held-out log loss 0.85274 against 0.85276: a flat surface); the
estimates agree to a mean |dp| of 0.0125 (max 0.25), more than MCMC noise, probably (not isolated) because the strata moved (19,332 linked pairs against
20,084, see the evaluation row) and the age scale; `race-confusion-women-1` stays the shipped version. The band inputs are rebuilt (ADR-0220): the build writes `population_account_bands`
beside the account; `population-account-7` and `-bands-7` were built from the repository, `sus-dependent-3` on them, and
`field_rate` reads the current account. The deaths whose residence is the state's "ignored" municipality (0.34% of 2012's) are in no municipal cell by
construction; since 2026-11-09 the cube counts them in their state and the country, and an aggregate's manifest says them by
state (`unplaced_by_state`).

## One data home (2026-10-24, ADR-0200, ADR-0208)

Every process of this user, PegaSUS included, resolves `C:\Users\Galaxy\pegasus_core_data`
(`%APPDATA%\pegasus-data\config.toml`), and it is the only folder holding pegasus data.
* **No strays left.** The homes adopted under ADR-0200 and those made since are gone: 23 were adopted and removed
  (15.4 GB), 6 without a catalog deleted. Nothing was held only there.
* **The build catalog.** The label build catalog moved into the home (`_label_build/`), and the repository holds no
  `pegasus_data_home/`.
* **Downloads.** A build now releases the downloads its verified partitions hold.
  * The 13.6 GB built before this were released with `prune` (4,274 files), and reads of them come from the lake.
  * 17.4 GB of downloads were never built (SIA-PA and SIA-BI most of it) and are kept.

## Reads and labels (2026-10-24)

* **Month reads.** A monthly intake unit is a publication of its month, so a one-month SNGPC query opens one file
  (4,543,907 rows in 3.9 s, formerly the year's 58.6 M). The real catalog is dated with `pegasus-data intake-periods`.
* **Large results.** Rendering works at any size, building labels in pieces under 1 GiB.
* **SIH-SP.** Its sex and age are read through the AIH from SIH-RD (ADR-0199).
* **Care flows.** Edges carry a role-named quantity's `(n, sum)` (ADR-0201).
* **Decode coverage** is measured over whole partitions (`scripts/decode_coverage.py`). On the 41 held datasets, 954
  coded columns are labelled and 29 are bare, but 66 labelled columns leave codes bare: ICD-10's 2016 dengue codes
  A97.x, SINAN-DENG's `0`s, SIH `FONTE_ORC` `00`, CIHA `GESTAO` `D`. A curation pass on these is under way.
  The 111 unheld datasets were sampled one file each: 33 columns bound, 186 re-kinded and wrong labels corrected.
* **Stored link runs are stale.** Every stored link run went stale on 2026-10-23, because the role-table key hashes the
  whole label pack, so a CIH label fix re-keyed every dataset. The key is being narrowed to what a role table reads, and
  then the runs must be re-made.

## Population support and daily climate (2026-10-24, ADR-0203 to ADR-0205; gaps found by nees-gt-ms)

- **Where people are.** IBGE's Grade Estatística 2022 is served (`pegasus-data grade`, `grade_cells`): 14.1 million
  cells of 200 m / 1 km with people and households, each with its municipalities; it equals IBGE's published totals. It is
  the one population weight: the points pack's population centre, the population-distance graph and the climate weights
  read it (the tract points and the internal 5 km grid are gone). Its municipal sums are not counts (>1% off the census in
  1,024 municipalities).
- **Tracts.** The Census 2022 tracts are served as published (`census_tracts`, `tract_population`: sex × eleven age bands,
  `X` null); suppression leaves 0.65% of residents out of the bands (102 municipalities short by more than 5%).
- **Where a CEP lies** (ADR-0205): CNEFE 2022 landed whole (111.1 million records, 931,499 CEPs equal IBGE's aggregate) and
  `cep_points` per CEP and municipality. SIH-RD Alagoas 2023: 95.4% of AIHs' CEPs found, the municipality agrees on all of
  them, but 70% sit on a CEP spread over 2 km and 21% on their municipality's only CEP: the patient CEP places most
  admissions in the municipality, not finer.
- **Mobility layers** (ADR-0211): commuting to work and to study (Census 2010), weekly coach and boat departures (IBGE 2016) and air passengers by month (ANAC, 2000 on) as graphs in `proximity_graph`, built by `pegasus-data mobility`; IBGE's population arrangements in the geography pack. Paused 2026-10-25 with everything built in `pegasus_core_data`; to resume: re-run `pegasus-data mobility --layer anac_air` for a new ANAC release (it detects one itself), OPEN_QUESTIONS 94-96 resolved 2026-11-05 (docs/evaluation/2026-11-05-mobility-open-questions.md). `projpop` ages are decoded (0-90, 90 and over) since 5229138.
- **Universe or sample** (ADR-0206): every SIDRA read says what its numbers rest on (`basis`); 99 tables declared from IBGE's notes (read in a browser: the notes are behind a bot check), 4,103 sample by their CV variables, 5,160 unknown until declared (1,306 of them the Census's).
- **SINAN read from its DBCs** (ADR-0207): dengue 2020 and 32 other SINAN partitions had been built from Dados Abertos exports (2020's with 538,654 discards); now from `FINAIS/*.dbc`. A lake read's report names its files; `ID_MN_RESI_municipio` gives the residence as a municipality or null.
- **Republished files** (ADR-0209): a lake partition built from a version DATASUS has since replaced is no longer served; SIH-RD 2025-09..12 (republished 16/10) rebuilt; a build records its files' layout so `families` cannot move them.
- **CNES beds** (2026-10-25): LT read to 2026-09 (a month not yet published names the latest one); the COVID-19 ICU codes 51 and 52 counted, ICU beds of 2020-2021 up by 20,538 and 25,237.
- **Care flows by bed-days** (ADR-0201, landed before this work): SIH E10-E14 2023, 138,316 admissions and 941,694
  bed-days, every nees-gt-ms figure reproduced and read again apart.
- **Daily climate.** CPTEC's MERGE (precipitation) and SAMeT (Tmax, Tmin, Tmed), 2000 to the day before yesterday, by
  municipality, weighted by population and by area from the grade, every file kept by vintage (`climate_daily`,
  `climate_weekly`, `pegasus-data climate-update`). SAMeT rewrites a day about 7 days later with ERA5: only a daily
  `climate-update` keeps the provisional values a backtest needs (nothing schedules it yet). BR-DWGD stays the source of
  the yearly fields; nothing is spliced. Held: every day 2000-01-01 to 2026-10-23 (2.4 GB). SAMeT agrees with BR-DWGD
  (Tmax +0.06 °C, RMSE 0.75; a drift of about 0.6 °C between them over 2000-2023); MERGE is about 15% drier than the
  gauges (0.83 of INMET's totals, 0.64 where no gauge is merged), stated, not rescaled.
- **Not done.** Humidity: ERA5-Land(-T) through the Copernicus CDS needs the author's account (`~/.cdsapirc`); Saldanha's
  ERA5-Land municipal means on Zenodo (dew point, 1950-2025, yearly releases, no account) would give history only.
  Per-cell climate is not stored (the raw grids are 63 GB; the disk had 17-27 GB free): `cptec.day_grid` reads one day's
  grid on demand, to be sampled at the grade's cells.

## Declarations and labels (branch `pegasus-core-fixes`, 2026-10-08)

Work for PegaSUS's work plan units P1 (declarations at scale) and P2 (labels across schema generations).
- **Roles.** All 166 catalog datasets have role files: 10,456 columns, no drafts, and a variable note on every column (evaluation 2026-10-08-typing-every-dataset). CNES's five template "series" removed; SIH's CM files moved from SISCAN to SIH; IBGE's three population publications no longer summed as one.
  - Done: every SINAN form with records but COLE and TETN, SIM's and SINASC's ten sub-series (legacy layouts on their 1996+ roles), SIH's seven, CIH, and SIA's twenty (PA among them; SIA.PR newly declared).
  - Each column is decided from its evidence sheet (`scripts/role_evidence.py`): its variable note, its form's layout, its values.
  - Also done: CNES (13), Dados Abertos (13), PNI (6), SISCAN (15), SIH-CM, IBGE (9), RESP (2), SINAN COLE and TETN, e-SUS Notifica, Painel Oncologia, PCE, SISPRENATAL.
  - Event types for 75 datasets (from 67), all of which PegaSUS now reads (3,977 of 6,242 columns, 2026-10-09; SDTA's outbreaks counted as their ill by sex and band, ADR-0156; SINAN's notification block declared from its own dictionary, MENI's annex codes harvested): DOREXT, DNEX, CIH-CR, Painel Oncologia, RESP, DCCR, and SIA PA, BI, PS and SAD, whose rows weigh their approved quantity (ADR-0155, OQ-75 resolved); eleven name-guessed dataset declarations corrected (DOR, DOREXT, DORIG, DNR, DNEX, DNRIG, NTRA, TRAC, ESPO, SIH MT, BASE_AIH1).
  - Declarations corrected by testing them on records: IBGE POP/POPS/POPT and ESCA/ESCB were summed; SISCAN's CSVs and the SI-PNI residence extracts were unreachable behind other declarations; SIH's CM files sat under SISCAN.
  - Missing codes: RESP, Painel Oncologia and CIH from their own forms; SINAN's yes/no convention (9 = Ignorado in 943 of 943 harvested tables) for form-less flag columns. CIH/CIHA age unit 5 is decades (OQ-74 resolved); CIHA runs in PegaSUS.
  - SIA's APAC code tables declared (AN, AQ, AR, ATD); a tabulation band is a domain only where the records stop at its edges (ADR-0154 addendum).
  - Undeclared by evidence, not by omission: SIA's AP_CODEMI, AP_COIDADE, AP_ETNIA and AP_UFNACIO (the Informe Técnico 2019-07 names them with no codes; their tabulations alone speak); 367 columns in all still lack missing codes after the 2026-10-09 sweep (1,014 declarations over 122 role files).
  - 2026-10-09: a sweep of `propose_missing.py` over every dataset with undeclared categories, first on one year each, then on each column's own years (a greedy cover of their spans); the proposer reads a column with no value from its form alone and drops a column absent from its files.
  - Decoders made safe (evaluation 2026-10-05-decode-memory): a non-DBC payload is refused before inflation (one had filled the disk with 47.8 GB); Parquet is read from memory; stale temp directories are pruned. Person links measured against each other (`entities.triangles`), sides counted through persons, link specs read once per process.
  - SDTA's outbreaks are events of their own (ADR-0157, `persons: false`): PegaSUS reads them in one exposed cell (its decision 0034), φ 1.04 against the ill's 0.066. Its 47 counts declared from the form.
  - A role may state why its missing codes cannot be decided (`missing_unknown`); `scripts/sweep_missing.py` runs the proposer over every event dataset and writes the declarations or the reasons (running; years the FTP outage left unread are re-swept).
  - Duplicate entries are one record (ADR-0159): rows equal but for entry metadata (SDTA: one Maranhão outbreak entered 32 times; 2023 1,134 outbreaks from 1,162), and the source's own flag (SINAN's NDUPLIC_N 2, every agravo).
  - The lake is built by `build_lake` for any caller; PegaSUS's `update` builds it over a plan's datasets (a CIHA year: 12 s from 30-60 min).
  - A variable spread over columns is a grid of named axes (ADR-0158): SDTA's ill, CNES-ST's attendance × payer, programme × manager, installation × rooms/beds, read long by `grid_table`.
- **Missing codes.** The form decides where its dictionary is harvested, and the tabulation speaks only where the form is silent.
  - A code the records use that neither defines is written as a CONFLICT (evaluation 2026-10-08-declarations-by-form).
  - Two dictionary errors were corrected by supplement, with both claims cited.
- **Labels.** The label pack chose a vintage before a system, which left SIH 2008–2010 and 378 system-codelists unlabelled in the pack fallback. Fixed (OQ-73); the SIH 2010 links are being recomputed.
- **Throughput.** `translate` takes 0.1 s a call (from 22 s).
- **2026-10-19, SISCAN's strata and labels** (branch `meta-siscan-strata`, ADR-0197): all 15 datasets answer the engine's `_strata` (age in years, or a band's lower edge `IDADE_faixa_anos`; SG_SEXO / CO_PAC_SEX; CC and HC by their declared `implied_sex: 2`, which the engine reads since pegasus_project f1134ea), so the catalog counts them ready for studies (100 of 154); cytology and histopathology laudo codes bound by their counters. Open: OQ-91.
- **2026-10-19, SISCAN's event types** (branch `meta-siscan`, ADR-0196, evaluation 2026-10-19-siscan-event-types): all 15 datasets declare an event (`curation/datasets/siscan.yml`): `exam` (rows are groups of exams in SISCOLO/SISMAMA and CITO_MAMA, summed by `QTDEXA`/`QUANTEXAME`/`QT_EXAME`) and `examined_patient` (the five `_PACNT` files, a woman a year, never added to the exams); counts equal the raw files and TabNet's own base. Open: OQ-91.
- **2026-10-19, SRAG, yellow fever, ESPO, NTRA and SISPRENATAL-PN** (branch `meta-srag`, evaluation 2026-10-19-srag-fa-event-types): SRAG-NOTIF (the lost `srag` intake declaration written again, 194 columns), FA-HUM and FA-EPIZ get roles and event types (`case` with `present`; `epizootic`, a new kind, also SINAN-ESPO's); NTRA is a denominator and SISPRENATAL-PN a pregnancy-month, neither an event; codes filed as `5.0` are read as `5` at landing (`int_code`; 2020's covid-19 was invisible), the SRAG age has the `sivep` encoding, `query` reads an intake dataset's provenance and `intake.yml` code lists; each count equals an independent figure; OQ-92, OQ-93.
- **2026-10-19, what each dataset is for** (branch `meta-contexts`, ADR-0195, evaluation 2026-10-19-dataset-use-and-context-roles): a dataset without an event type declares its `use` (context, denominator, support, reference, not_an_event_source) and `why_no_event_type` with its evidence, on 64 datasets (the SRAG, FA, SINAN-ESPO/NTRA, SISCAN and SISPRENATAL ones are other branches', listed by `undeclared_uses()`); roles for SISAGUA's six tables, SNGPC, BNAFAR, SIES, REGIAO, ANS, INEP and S2iD (298 columns); five stale descriptions corrected (SIH-MT, CH, SIA-AC, SIH-RJ, SNGPC's row); OQ-90.
- **2026-10-15, record conditions on roles** (ADR-0193, evaluation 2026-10-15-record-conditions): a topic that is a condition on a record's fields (birth weight under 2,500 g, deaths under one year or 28 days, caesareans, mothers under 20, deaths at home, admissions of the elderly) is `condition=[{"role": ..., "op": ..., "value": ...}]` on `query`, `count_events` and `read_events`, three-valued, the unknown counted apart; Brazil 2019 SINASC, SIM and SIH equal TabNet's published figures (weight < 2,500 g 247,856 with 746 unknown; infant deaths 35,293), Alagoas and Acre equal on the fetch path. Open: SIM `IDADE` `300` counts one death as neonatal (OQ 85); no OR between clauses.
- **2026-10-14, SISAGUA by municipality and month** (ADR-0192, evaluation 2026-10-14-sisagua): the surveillance basic parameters (E. coli, total coliforms, turbidity, free chlorine, fluoride, colour, with the samples assessed beside each share) were landed with January-September as no month (`NU_MES` `01`-`09`) and with no numerator row for a place-month without a positive; read as `01`-`09`, versioned (`PERIOD_DERIVATION`), zero-filled over the population, and a field declares its `grain` and `law: sum`. Santa Maria 2018 re-landed: E. coli 20 of 534. Open: VIGB/VIGC/VIGD (and SNGPC, with the same padding) are still to be landed again in `pegasus_core_data`; PegaSUS's `context_field` drops the month and must sum the months of a year; the cadastros (population supplied, treatment, catchments) are not ingested.
- **2026-10-14, source notes of the core systems** (branch `fix2-notes`): SIM-DO, SIM-DOFET, SINASC-DN, SIHSUS-RD and SIA-PA declare `source_notes` from the Ministry's DO/DN manuals, TabNet notes, Portaria SVS 116/2009, RIPSA 2008 and the SIASUS Informe Técnico (DATA_SOURCES); a study's methods section no longer says "no source declares notes" for them.
- **2026-10-14, units** (branch `fix8-units`, ADR-0184): every measure of SIH-RD/RJ, CIHA, SIM-DO*, SINASC-DN*, SIA's APAC family, PS, SAD and PA states its `unit` with the document line or why none is known (171 and 55; 666 measures elsewhere are listed by `undeclared_units()`); money names its competence column(s) and `unit_from`; SIM/SINASC `SERIESC*` are ordinal numbers, not undecoded categories; PegaSUS reads the new keys from `pg.roles` rows.
- **2026-10-14, sex codings and measure fills** (branch `fix9-curation`, ADR-0189; the two paper audits): SINASC `SEXO` is `1/2/0`, `1/2/9` (2010-2011) or `M/F/I` (2014) by file year and decodes to the same three labels in all 16 (a curated code may carry a window; `9` only for 2010-2011); the measures' missing codes are declared where a kit, a layout or a spike says so (SINASC `99`, `9999`; APAC laboratory and clinical fields' zero fill and `9999`, ATD and AN, AM, AQ, ACF, AB), with plausibility domains in the unit for haemoglobin and albumin; ATD's event type states ATD's own numbers, `AP_CIDCAS` (a diagnosis on 12-24%) and 'caso novo' (no new patient), and its first competence (2014-08). Open: the scales of the laboratory fields (OQ 82), codes no document names (OQ 83).
- **2026-10-14, a mismatched export no longer drops a publication** (branch `fix-lake-mismatch`, ADR-0190): the build follows a representation refused for its columns with the publication's next, as `retrieve.fetch` does, and a refused export puts the native `.dbc` ahead of the other exports (67 of SINAN's 98 families had that rule switched off); SINAN-ZIKA 2015-2019 and SINAN-CHIK 2014-2019 are built in `pegasus_core_data`, row counts equal the `.dbc` headers'; a publication none of whose representations fits is an `errors` entry. Open: the exports of SINAN are not censused (OQ 84).
- **2026-10-14, the semantics structure** (branch `struct-semantics`, ADR-0187): one curation epoch for every loader of the curation (`semantics/epoch.py`, in place of sixteen memos), every place column states `place_of` (1,067 columns: subject, event or record), the warehouse and the pack choose a vintage's windows by one rule, `read_events` also reads an event type's records; 122 real calls equal before and after (evaluation 2026-10-14-semantics-structure). Left: the normaliser's labelling path (OQ 79).
- **2026-10-14, the read path** (branch `fix-query-path`, ADR-0163, ADR-0164): a query's fixed cost 0.2-1.3 s to 0.07-0.1 s warm (a labelled one, 8.8 s to 0.26 s); the lake is read from `lake_partitions`; a year published nationally and per state is read once; a typo'd `select=`/`rows=` column raises (evaluation 2026-10-14-query-fixed-cost).
- **2026-10-10.** Event types for 82 datasets: SIA's AB, ABO, ACF, AD, AM and AMP, each count equal to its APACs, and SIH-SP by its approved quantity (evaluation 2026-10-10-sia-apac-events); SIA.AB is follow-up after gastroplasty, not the surgery; a derived name with a recipe per layout lost the APAC age on narrow reads (fixed). Storage: 68 GB free from 16; modelled floats in BYTE_STREAM_SPLIT (`reencode-modelled`); `_record_key` and the catalog's `source_ref` are the remaining large levers (evaluation 2026-10-10-storage-and-compression).
- **2026-10-10, for PegaSUS's studies.**
  - `roles(dataset, period=)` reads a role's column in the year's layout generation: SIM-DOFET's residence.
  - Event types declare their source's notes (ADR-0160) and their denominator when it is other events (ADR-0161):
    live births for TOXG, TOXC, SIFG and SIFC; total births for DOFET.
  - The concept index (`concept_index`): conditions read from the roles' event-type columns, SIGTAP's compatibility, and
    label search over ICD-10 and SIGTAP.
  - `mesh`: IBGE's polygons for maps.
  - DEMAS assessed: 113 paths; the non-FTP origin is the Portal de Dados Abertos.
  - In progress on their own branches: SI-PNI (`pni`), medicines (`medicines`), links for the toxoplasmosis study
    (`links`). SISAGUA is merged (ADR-0162).

## Record linkage (merged 2026-11-08; ADR-0107 to ADR-0124)

**The theory** (`docs/plans/linkage-theory.md`; accepted 2026-10-03; what
executing it taught is in §11) is executed through T1–T5:

- **T1, records and the lake.**
  - Linkage reads the lake through role tables. They are cached per scope;
    a national table is built state by state when the lake holds only state
    partitions.
  - A record's identity is the hash of its own fields, numbered for exact
    duplicates within a file (ADR-0124). It is the same in the national and
    the state publication.
  - CIHA publishes 735,049 duplicate rows.
- **T2, scope invariance.**
  - A slice is linked against the national partner side, with national u,
    error channels per state shrunk toward the nation's (ADR-0123), and the
    national threshold and calibration.
  - Measured: SE, RR and SP give exactly the national run's pairs (SP
    133,476 of 133,476).
- **Impossibility as learned evidence** (ADR-0121): the `order` and `joint`
  comparison kinds exist, but are not used in the death specs. There, both
  re-read a field another comparison already uses:
  - the order comparison read the death date, charging a month typo twice;
  - the place comparison read the facility.
  Together they dropped thousands of true SIH-death pairs
  (`scripts/link_pair_fate.py`).
- **Padded partner periods** (ADR-0121): infant deaths and newborn
  admissions read SINASC one year back. Infant deaths: 23,845 → 25,982
  pairs.
- **T3, entities.**
  - `build_entities()` merges links into persons, with uniqueness
    constraints.
  - The newborn link inherits the mother's delivery AIH, which doubled
    Sergipe's pairs.
- **T4, settings as annotators.** SIH's excess "asian" is two hospital
  practices: a default fill (04 for everyone), and SIM's code for brown
  written into SIH (one hospital, fixed in September 2022). Nothing is
  relabelled (OQ-66).
- **T5.** `p_match` on every pair (a calibrated local false-match rate);
  `link_draws()`.
- **Discovery** (ADR-0119): a placebo-checked search over typed fields finds
  the hand-written keys. SIH and CIHA share 0.4% of persons.
- **Cohort links** (ADR-0194): `sih_admissions_to_sim` is declared once and
  run per codes, years and area (`linked_deaths()`). Alagoas I21-I22
  2018-2022: 17.1% dead within 30 days (2.1% coincidences), 28.5% within a
  year (16.0%), 88.8% of in-hospital deaths found. Run per state and period
  only so far (46 s); the national scope is not measured. SINAN-TOXC cases are
  declared and not viable.

**National, 2022** (final runs: record keys, per-state channels, u from 10
million hashed pairs, padded infant and newborn links; `data/logs/final_relink.done`):

| link | pairs | FDR upper 95% | minutes |
|---|---|---|---|
| SIH deaths → SIM | 551,005 (91.0%) | 1.03% | 2.4 |
| deliveries → SIH | 1,529,614 (60.7%) | 0.74% | 7.4 |
| infant deaths → SINASC (2021 padded) | 25,939 (80.9%) | 0.79% | 2.6 |
| newborn admissions → SINASC (2021 padded, inherited AIH) | 79,048 (20.3%) | 1.07% | 5.4 |
| maternal deaths → SIH | 877 (53.5%) | 1.80% | 2.6 |
| CIHA deaths → SIM | 59,506 (60.6%) | 1.08% | 2.6 |
| births → CIHA deliveries | 195,566 (7.8%) | 0.99% | 4.0 |
| SINAN dengue deaths → SIM | 503 (47.6%) | 1.74% | — |

**National, 2021** (`data/logs/redo_2021.done`, after the SIH 2021 lake was
completed with RDPR2106; CIHA is not on the mirror):

| link | pairs | FDR upper 95% |
|---|---|---|
| SIH deaths → SIM | 699,995 (91.1%) | 0.97% |
| deliveries → SIH | 1,601,762 (61.0%) | 0.66% |
| infant deaths → SINASC | 25,909 (81.8%) | 0.87% |
| newborn admissions → SINASC | 74,220 (19.4%) | 1.07% |
| maternal deaths → SIH | 1,937 (56.8%) | 1.28% |
| SINAN dengue deaths → SIM | 0 (not viable) | — |

Entities 2021: 2,384,759 persons, 97 merges refused.

**National, 2023** (`data/logs/relink_2023.done`; CIHA is not on the mirror):

| link | pairs | FDR upper 95% |
|---|---|---|
| SIH deaths → SIM | 539,575 (91.7%) | 1.01% |
| deliveries → SIH | 1,524,602 (61.0%) | 0.69% |
| infant deaths → SINASC | 26,102 (81.9%) | 0.74% |
| newborn admissions → SINASC | 87,037 (21.3%) | 1.07% |
| maternal deaths → SIH | 833 (51.9%) | 1.23% |
| SINAN dengue deaths → SIM | 0 (not viable) | — |

Entities 2023: 2,159,524 persons, 105 merges refused.

- **Scope test:** the SE, RR and SP slices are identical to the national run
  (SP 133,471 of 133,471).
- **Entities:** 2,418,661 persons, 99 merges refused.
- **Admission–baby pairs only through other links:** 9,919, of which 7,324
  are newborns under 28 days and 2,580 older infants.

**Speed** (EVALUATION 2026-10-03 "Performance pass"), each change checked
identical to the code it replaced:
- the SP slice of SIH deaths takes 274.5 → 41.9 s;
- a cold CIHA role build 26.2 → 14.2 s;
- the lake build of CIHA 2022, 182 → 96 s;
- linkage DuckDB is capped at 40% of RAM;
- SIH-RD AL 2023, files cached, 21.3 → 16.9 s; one month 6.8 → 5.6 s
  (2026-10-04).

**Data sources.**
- **The DATASUS FTP data channel** has dropped every passive connection
  since 2026-10-03; control still answers.
  `data/probes/ftp/data_channel.jsonl` records when the channel returns.
- **The fetcher falls back to a byte-identical public mirror,** checked
  against the listed size and recorded as `mirror:<url>` (ADR-0122).
  - A new fetcher starts mirror-first when the home's latest fetch came from
    the mirror within 30 minutes.
  - Of equivalent copies, the cached or smallest one is read (ADR-0133).
    SIH 2008–2014 had fetched CSV/XML copies the mirror lacks.
- **TabNet over HTTP** is a first-party source:
  - the current territorial tables;
  - tabulations used to check every count below.

**Meaning fixes found on the way** (unchanged): SINASC `LOCNASC` 5, SIH
`IDENT`, SIH-SP `SERV_CLA` 000000, SIM `IDADE` minutes, `TABPAIS`,
`CLASSI_FIN`, SINAN `ORIGEM`, inferred descriptions marked (ADR-0116,
OQ-64), 1990s SIH V-codes.

- **Race reliability** (ADR-0128). `race_reliability()` flags SIH
  hospital-months whose code 04 is a default or SIM's brown: 329
  hospital-months in 64 hospitals in 2022.
- **Exact chance agreement** (ADR-0132). u(equal) is counted from value
  frequencies: national SIH deaths gives 551,012 pairs, against 551,005.

**Open in linkage:**
- **Infant admissions beyond 28 days:** not identifiable directly (measured);
  they are reached through deaths.
- **A coverage prior,** only with coverage measured independently of the
  link (EVALUATION 2026-10-03 "Coverage by stratum").
- **Other systems and years:**
  - SINAN dengue deaths → SIM: 47.6% in 2022, not viable in 2023 (no
    birth date);
  - chemotherapy APAC deaths → SIM was tried and withdrawn: its date is not
    the death date;
  - 2023 is linked (above);
  - SINAN HIV/AIDS and congenital syphilis cannot be linked from public
    fields: no birth date or facility (EVALUATION 2026-10-03 "SINAN
    linkage potential").
  - Toxoplasmosis (2026-10-10, EVALUATION "Toxoplasmosis links"):
    - TOXC → SIH admissions with the disease: 1,444 pairs, 5.75% chance, use with caution;
    - TOXC → SIM: 101 pairs, 6.9% chance, use with caution;
    - SIH → SIM, TOXC → SINASC and TOXG → SINASC: not viable. No three-source capture.

## Context around a record (2026-10-03)

- **Dimensions** (`query(dimensions=...)`):
  - **official concept lists** (ADR-0134): `CAUSABAS.mortality_list`,
    `avoidable_0_4` and `avoidable_5_74`; `DIAG_PRINC.icsap_group` and
    `icsap_condition`; ICD chapters. SIM SE 2022 matches TabNet by cause.
  - **any municipality column of nine systems,** through any classification
    of the geography pack (ADR-0130);
  - **SIGTAP group, subgroup and form** as derived columns (ADR-0092;
    ADR-0131 withdrawn as a duplicate). SIH SE 2022-01 matches TabNet
    exactly.
- **Enrichment:** 17 CNES attributes, read as of the record's month
  (ADR-0125).
- **Geography:**
  - IBGE regions, correct for every year since 1994 (measured);
  - TabNet's current health regions and macroregions (ADR-0126, ADR-0129);
  - IPEA comparable areas.
- **Places:** `municipality_point` and `distance_km` use the Census 2022
  population centre, not the polygon centroid (EVALUATION 2026-10-03
  "Municipality points").
- **Fields** (`load_field`):
  - IBGE GDP and value added (ADR-0127);
  - Census sanitation, literacy and population by race, for 2010 and 2022
    (all fifteen IBGE fields are read through `pegasus_data.sidra`, ADR-0142).
  - Climate (ADR-0178): BR-DWGD v3.2.3's municipal zonal means (Saldanha et al., Zenodo), 1961-01-01 to 2024-03-20,
    5,563 of the 5,571 municipalities (not Noronha or Bombinhas: no grid cell; six created after 2010: no series); 2024 is `partial_year`.
    `climate_monthly` is the municipality-month base; `air_temperature` (and `_monthly_max`/`_min`) over `temperature_months`,
    `precipitation_mm` over `precipitation_months`: one value per municipality and year (ADR-0177;
    build with `pegasus-data fields --name ...`, RUNBOOK). `climate` keeps INMET's station-months (1961-2025, 912 stations)
    as observations to validate against, not as the source.
  - `disasters`: S2iD's recorded events, 1991–2025 (76,190), with COBRADE
    type and human damages.
- **SIDRA** (`pegasus_data.sidra`, `pegasus-data sidra`, ADR-0142):
  - a registry of IBGE's tables built from its own metadata (`sidra scan`; `search`, `show`, `survey`, `rank`);
  - a planner under the measured limits and a long fact store with provenance; the curated compendium (97 tables) priced and fetched by group (`sidra curated`);
  - series across censuses with both claims kept: `population_total`, `population_age_sex` (`CENSO`), `population_race_sex_age`,
    `population_race_sex_ageband`, and sewer, water and waste coverage 2000, 2010, 2022;
  - not built: SIDRA tables at state level as context fields (PNS, PNAD Contínua; `fields.yml` is municipal), and the
    sample-based 2010 labour cube (table 3572, 120M values) which `sidra curated` skips by size.
- **Units:** SIH money is in reais from 1995 on (OQ-21 resolved).
- **Renamed columns:** five confirmed by values are curated (OQ-57
  narrowed).

## Done (live-verified)

- **Presentation** (ADR-0084).
  - Headers read "Variable name (CODE)" and values "Label (code)"; an
    undecoded value reads `code (?)`.
  - Presets `readable` (the default), `analysis`, `labels` and `codes`, plus
    templates and pt/en.
  - Every coded column leaves rendering with a label companion (ADR-0093).
- **Canonical classifications,** one table for every system (ADR-0087):
  - ICD-10, falling back to the category when a subcategory is not listed
    (ADR-0089);
  - SIGTAP, with group, subgroup and form as dimensions (ADR-0092);
  - CBO 2002, banks, naturality/countries, states and health regions.
- **Establishments and legal entities.**
  - Registry names come from the CNES kit (692,004 establishments,
    ADR-0086).
  - CNPJ → legal name; a CPF is never resolved (ADR-0093).
  - A maintainer is named through the row's establishment (ADR-0094); the
    documented all-zeros is "Sem mantenedora" (ADR-0097).
- **Relations between columns.**
  - A composite key (`CLASS_SR`, `PA_CLASS_S`, `SUBFIN`), whose parts can carry
    the record's width: age unit + age via `IDADEDET` reads "3 dias"
    (ADR-0088, ADR-0098).
  - A sibling that names the code (ADR-0090).
  - Path tables whose unlisted codes are named by their deepest listed level
    (`VINCULO`, `S_CLASSEN`, ADR-0096).
- **Municipalities** show the 7-digit IBGE code.
- **The kits are read correctly** (ADR-0095). 43,916 `.CNV` lines had codes
  glued to their labels (`PACIENT15`); a re-read now supersedes the old
  reading.
- **Speed** (ADR-0097). One year of SIASUS-ACF, files cached: 104 s → 16.7 s
  (35 s in a fresh process).
- **Descriptions.**
  - DADOS_ABERTOS inherits SIASUS's curation (ADR-0095).
  - Curated: BASE_AIH1 (60 fields), SIA PQ (7), SIA UO (4) and the SI-PNI
    exports (22).
- **Sweep tools.** `scripts/sweep_undecoded.py` lists undecoded values over 16
  datasets. `scripts/def_evidence.py` lists what each `.DEF` offers for them.

## Linking datasets (ADR-0100 to ADR-0103)

- **One establishment registry.** Typed identifiers: only a valid CNPJ is
  stored, a CPF is never stored or resolved, and no identifier appears in any
  name or label (ADR-0102). The registry also holds maintainers,
  inclusion/exclusion dates, 107,438 health teams (INE) and the federal
  university hospitals.
- **CNES ↔ CNPJ** reads the registry first, then older kits' claims.
  - SIH AC 2023-01: 4,160 of 4,165 resolved, and every one confirmed by the
    admission's own `CGC_HOSP`.
  - The reverse direction works; it resolved nothing before.
- **The 2008 procedure break is bridged** by the official Tabela Unificada
  map, one-to-one only. 96.3% of SIH AC 2005 admissions reach a SIGTAP
  procedure, and the SIGTAP group/subgroup dimensions are continuous.
- **Pre-2006 occupations** decode from SIM/SINASC's own `OCUPA` table.
- **SIA's 2001–2007 establishment codes** are keyed by the file's state
  (`SIA_UPS_BR`).
- **Every legacy APAC archive's members are measured** by ranged header reads
  (1,721 of 1,723), so components reach the years they exist in (EX and PC,
  2003–2006) and absent ones are not gaps (ADR-0103).

## Coverage now

- **Kits and pack.** The maintainer catalog was re-read with the fixed parser.
  The label pack and the seed are rebuilt from it; the pack no longer loses a
  window the catalog lacks (ADR-0095).
- **Per family-field** (`pegasus-data meaning`, 22,714 rows):
  - missing descriptions: 441 → 130;
  - undecoded: 240 → 34;
  - opaque: 120.
- **Per cell, fresh home, 16 datasets:** undecoded 1.23 M → 0.56 M, with no
  regressions. What remains is mostly values that no source documents
  (EVALUATION, 2026-09-29).
- **SINAN, every form 2023, fresh home** (5.2 M rows, 57 forms): undecoded
  cells 14.5 M → 7.2 M → CNAE and CLASSI_FIN fixed since, and errors 3 → 0. The
  fixes:
  - native DBC before the lossy Dados_Abertos exports (ADR-0135);
  - per-form tables never merged, cached or outweighed (ADR-0136);
  - page-break-complete form dictionaries;
  - 238 coded fields un-marked as uncoded;
  - lookups keyed correctly (CNAENET, UNIDINVEST);
  - canonical CNAE 2.0 (EVALUATION 2026-10-03).

## Open fronts

- **The project's work is ordered in `../pegasus_project/BACKLOG.md`** (2026-10-10, PegaSUS architecture revision 5). Its [data] units are pegasus_data's next work: phase 4 (concept index), phase 5 (source assessment of the DEMAS API's 113 endpoints and ANVISA's open data, the publication audit, source definitions and caveats as declarations, SISAGUA, medicines, SIASI and the DSEI support, primary care, the remaining DEMAS families), phase 6 (TOXG/TOXC → SINASC and other links, with viability).

- **Undecoded because no source names them** (OQ-61; fresh-home sweep, 21
  columns and 48,763 cells, from 52 and 560,585 the same morning): largest SIH-SP
  `SERV_CLA` `000000`; SIA-AQ/AR histology grade and `AQ_TRANTE`; SIA-PS
  nationality and ethnicity; CNES bank codes and placeholders; SINASC
  `TPDOCRESP` `0`; SINAN-HANS `9`s; SINAN `0` in DENG/CHIK conditional fields,
  AIDA `CRITERIO` 101/601, ANTR `FIM_ANIMAL` 6. Each
  reads `code (?)`. Settled by measurement against other columns of the same
  record: SIH `TPDISEC*`, `SP_DES_*`, `SP_U_AIH`, `GESTOR_TP`/`GESTOR_COD`;
  SIA `TIPPRE`, `UFDIF`/`MNDIF` `9`, `PA_CODOCO`; CNES `TP_PREST` `99`,
  all-zero `CNPJ_MAN`/`CNPJ_CC`; SINASC `CODPAISRES` (ADR-0105, ADR-0106).
- **Undescribed:**
  - SIA UO's 74 modality fields and PQ's 14 name-only fields (no layout
    found);
  - BASE_AIH1's 11 fields without an RD/SP twin;
  - its age pairing, unverified until a sample of the 12 GB file is read.
- **SIH-RD 2014 was unreadable** in every state until 2026-10-04 (ADR-0135 amendment); AC 2014 now equals TabNet.
- **Speed.** Of a 17-second state-year, rendering is 15 s: label tables
  (6), the pack and reference reads (2.5), decoding (2.7); imports cost ~1.5 s
  per process, pandas included (pyarrow loads it).
- **Code health (2026-10-04):** `mypy src/pegasus_data` is clean. `view` is
  split into `view` and `lookups`, `retrieve` into `retrieve` and `_request`,
  and `cli` into a package by help panel; the command tree is unchanged
  (61 commands, same parameters).

## The PegaSUS handoff (2026-10-04, `docs/history/2026-10-04-pegasus_data-handoff.md`)

| § | state |
|---|---|
| 1 storage | **Done** (`docs/evaluation/2026-10-04-storage.md`): per-process DuckDB spill (6.7 GB freed), national-only role cache with derived states, `prune` (4.47 of 6.0 GB on the linkage home, dry run), national-only builds, `_row` delta. A 16-byte key, typed money and dates, and sorting were measured and not adopted (ADR-0124 amended). |
| 2 roles | **Done for 16 datasets** (ADR-0137): 1,540 columns, 69 still draft with reasons. The person/event test on linked records: race agrees 0.72, event attributes 0.08–0.24. |
| 3 event types | **Declared** (ADR-0137). SIM, SINASC and dengue probable cases equal TabNet 2022 in 27/27 states; SIH within 76 of 12.4 M (OQ-68). No confirmed-case rule for TUBE, HANS, SIF*, VIOL or ZIKA without a source. SIA APAC (AQ, AR, AN, ATD): kind `authorisation`, an event is an APAC (ADR-0147); ACF, AM, AD, AB, ABO, AMP not yet. |
| 4 aggregation | **Done** (ADR-0138): national SIM 2010–2023, municipality × year × 18 ages × sex × ICD category: 10,974,296 cells, 18,878,605 deaths, 14/14 years = TabNet; 655 s and 11.4 GB peak (from 1,205 s and 15.1 GB). |
| 5 code structures | **Done** except OQ-69: ICD10/SIGTAP/CBO2002/CNAE20 trees; CID-BR-10, ICD-10 lists 2 and 4, avoidable causes, ICSAP. Not served: the SIH morbidity list (no ICD mapping found), GBD (licence: the author's call), ICD-9 → ICD-10. |
| 6 graphs | **Done** (ADR-0138): contiguity by border km, population distance, REGIC 2018 links and cities, areas, care flows (sum exactly to events). Travel time: later. |
| 7 modelled tier | **Declared** (ADR-0139, `modelled.py`). Sources: ANS beneficiaries 2021–2025 (= ANS TabNet) and INEP enrolment margins 2021–2024 are fields. TSE needs a TSE–IBGE crosswalk; CadÚnico and RAIS are not started. Models: `race_confusion_infant` (ADR-0143) and the population account (`population_account.py`, `population_tensor.py`; `population-account-3`, ADR-0151, the 5,570-municipality × single-age × race tensor, 2000-2023, and `population-account-4`, the same with a forecast to 2030 (pseudo-forecast median error 0.049 / 0.039 at eight years against 0.071 / 0.062 vital-only; 80% coverage 0.81 / 0.89); `population-account-5`, ADR-0151 item 6, adds 1991-1999 by comparable area (total only; hold-out Contagem 1996: area error 0.028 after the national rescale, 80% / 95% coverage 0.83 / 0.94; the 1996 level is 5% above the raw Contagem, unresolved);  `population-account-2`, ADR-0148: cohort residual between censuses and a lagged-migration projection to 2023; cross-period median error 0.052 / 0.056 against 0.074 / 0.079 vital-only, 80% coverage 0.79 / 0.84; `-1`, ADR-0145, stays readable); `population_without_private_coverage` (`sus-dependent-2`, 2021–2023) and `system_completeness` (`-2`; SIM, SINASC by UF, 2000–2023) (ADR-0146), both rebuilt on `population-account-2`. |

**The ICD ontology** (PegaSUS handoff `docs/handoffs/2026-10-06-race-and-icd-ontology.md` in pegasus_project, part B):
- **Item 1 (attributes per code) built from the DATASUS 2008 release:** `code_attributes()` (14,233 codes: dual role, sex, CAUSAOBITO, underlying-cause eligibility per the release's own rule, references, merged codes).
- **Item 6 (external-cause axes) built:** mechanism, intent, motor-vehicle person and adverse effect by the NCHS matrix (its published statements parsed and run in order), and the place of occurrence of W00–Y34 as the release's own descriptions name it (X59, Y06 and Y07 found not to carry a place).
- **Nested groups (2026-10-06):** the ICD10 tree now keeps the release's group nesting (C53 > C51-C58 > C00-C75 > C00-C97 > II); it had hung every category on the outermost group. `code_trees.parquet` rebuilt, same 26,359 rows.
- **Age and sex plausibility (2026-10-06):** `code_attributes()` carries NCHS Part 11 Table G's edits (absolute or conditional) beside the release's RESTRSEXO; the two sex sources agree wherever both speak. The SIM kit's typed garbage codes are the code list `SIM-POUCO-UTEIS` (types as written, not interpreted). The GBD garbage codes with levels 1-4 are `garbage_codes()` (2026-10-14, ADR-0182: GBD 2017 and 2019 from open-access supplements; use GBD 2019 from 2020, SIM codes COVID-19 as B34.2), and `price_index()` is IBGE's IPCA for constant reais (ADR-0183). ICD-9 → ICD-10: `code_bridge("ICD9-ICD10")` from NCHS's 1996 double-coding study (2,296,922 deaths; 410 → I21 97.6 %, 486 → J18 65.7 %, NCHS's published pneumonia ratio about 0.70).
- **Not done:** a later DATASUS release (only V2008 is harvested; the harvested page is a frame stub with no version, and `CID10CSV.ZIP` answered 404 on 2026-08-19, `sources/hdr_CID10CSV.ZIP.txt`), ICD-9, ICD-O, the further lists and the relation graph.

## Waiting on the user

- **Publishing.** `master` is on GitHub (2026-11-08); PyPI and platform wheels for the compiled DBC engine are not
  (ADR-0074, CLAUDE.md §4).
- **GBD's licence** (OQ-69): IHME's non-commercial agreement against an
  open-source package.

## Tests and checks

- `scripts/live.py --all --fresh` and `scripts/sweep_undecoded.py` on a fresh
  home.
- `ruff check src scripts tests` and `scripts/check_docs.py`.
- `pytest -q -m "not network"` is a regression net that does not grow
  (CLAUDE.md §5).
- **2026-10-10 (later).** `roles(dataset, period)` picks the column a role sits on in a year (SIM-DOFET/DOINF/DOEXT residence: MUNIRES 1979-1995, CODMUNRES from 1996); a source's own definitions, validity, finality and known errors are declared on event types (`source_notes`, ADR-0160: SINAN TOXG, TOXC, ROTA). Evaluation 2026-10-10-dofet-residence-and-source-notes.
