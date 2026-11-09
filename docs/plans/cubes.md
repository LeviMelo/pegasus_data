# Plan: one space × time object, the cube

Written 2026-11-08 from two surveys of the code (every mechanism that makes a place × time table, and an audit against
CLAUDE.md's principles). It is the working plan for the unification: what the cube is, how each existing mechanism maps
onto it, the stages, and what each stage must prove before the next. Decisions go to ADRs, measurements to evaluation
entries (CLAUDE.md §7). This file points at them and changes with the work.

---

## 1. Why

Thirteen mechanisms each turn data into a table indexed by place × time (× strata):

- context fields (`fields.py`, 123, five builders);
- aggregate recipes (`_aggregate.py`, 60);
- the SIDRA fact store and its series;
- population series and the population account;
- the modelled products;
- `count_events`, care flows, rates;
- CPTEC daily climate;
- the HTTP aggregates.

They overlap, with these defects:

- **The algebra holds in one place only.** The aggregate engine has it: accumulator states, per-axis additivity, refusals,
  partial periods and pushforward roll-up. Fields declare `law` and `over`, and no code applies them; PegaSUS re-aggregates
  them itself, averaging what is not `law: sum`.
- **Three declarations say which column is the place, the time and the measure.** They are the datasets' `semantic_axes`
  (aggregates), `intake.yml`'s `place`/`period`/`fields` (intake fields), and `curation/roles` (flows, linkage). Only the
  roles are typed, windowed by year and shared across all 184 datasets.
- **Hand-curated slices stand beside general stores.**
  - `gdp` is one SIDRA table and variable, re-keyed and with its status renamed, beside a fact store that already holds
    any table whole.
  - 43 CNES fields come from a private DBC pipeline (`sources/cnes.py`, a third-party mirror) beside the CNES datasets the
    FTP reader serves.
  - 55 of the 60 recipes are near-copies for SINAN agravos.
- **Place and time have no shared encoding.** A municipality is a 6-digit string, a 7-digit string, an int32, an int of
  either width, or a "+"-merged string. Time is a year, a month, an AAAAMM competência, a period string, a date or an epi
  week. Status vocabularies differ by builder: `ok`, `no_cnes_record`, `partial_year`, SIDRA's six.
- **"Context" is decided in the data layer.** Which quantity is context for a study is the study's decision. pegasus_data
  should serve every measure on the same footing.

## 2. The cube

A **cube** is one measure observed over named axes. It is stored as long facts that hold accumulator state, never finished
numbers:

| column | meaning |
|---|---|
| `place` | the place's code at its level (municipality: IBGE's 7 digits as int; uf: 2 digits; country: 0; a classification's member code), from `geography`'s spine |
| `period` | the period's start as text at the cube's grain: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, `YYYY-Www` (the Ministry's epi week) |
| one column per stratum | the stratum's code as the source writes it (sex, age, race, vaccine, dose, cause…), named by the axis; labels are joined at read, never stored |
| state columns | per measure kind, from `measures.py`: `n` (count), `sum`, `sumsq`, `num`/`den`, `min`/`max`; an estimate carries its interval (`lo`, `hi`) |
| `status` | one vocabulary: `value`, `zero`, `not_applicable`, `not_available`, `suppressed`, `partial` (a period not wholly covered) |
| `source` | the publication the fact comes from (a file, a SIDRA request, a model version) |

A cube's **manifest** states:
- the measure (kind, unit, additivity per axis, stock or flow) and the axes (each with its level, codelist, or SIDRA
  classification);
- the place universe and its vintage, and the support (which cells could be observed);
- the partial periods and the sources with their digests;
- a fingerprint over all of it.

These are the aggregate engine's artifact fields, made general.

**One computation, one store, one door.** `cube(...)` returns the cube at any place level and any time grain. It rolls up
by pushforward along `geography.memberships` (with their validity windows) and along the time lattice:
day → epi week, day → month → year. The `measures.py` algebra decides what is refused: a stock summed over time, a mean of
means, a roll-up through a map that is not total. The base cuboid is the only one stored.

## 3. Where cubes come from (adapters, not mechanisms)

Each adapter turns one kind of source into facts. Nothing downstream knows which adapter made a cube.

| adapter | source | the cube's axes come from | declaration |
|---|---|---|---|
| **records** | any record dataset `query()` serves: FTP, intake (SI-PNI, SRAG, SISAGUA…), CNES's datasets | the **roles**: the place role (and whose place: residence or where), the `when` role, strata and dimension roles; the measure is an event type's count or a numeric role's sum | none per cube. A cube is named by dataset, event type, measure and axes, and built on request. A materialised list is optional (what to build ahead) |
| **published** | SIDRA (every table), population series, the modelled products | the publication's own classifications (SIDRA `c<id>`, the series' axes, the model's strata) | none per table: `sidra:<table>/<variable>` is a cube as soon as the registry knows it |
| **gridded** | BR-DWGD, CPTEC, INMET | the product's variables; the place from the zonal weights (population or area) | the product's module (`sources/brdwgd.py`, `cptec.py`), unchanged in substance |

## 4. What becomes of each mechanism

| today | becomes |
|---|---|
| `fields.py` SIDRA slice and series fields (26) | published cubes; a series stays a stitched published cube (`sidra/series.py`), now served through `cube()` |
| CNES fields (43, private DBC pipeline) | records cubes over the CNES datasets (ST/LT/EQ/EP/PF) through the one reader; the code groups (bed and equipment codes, CBO groups) become strata codelists, not field names |
| BR-DWGD and INMET fields | gridded cubes; `climate_monthly` is their base |
| intake `fields:` (46) | records cubes over the intake datasets; the intake's place and period declarations generate the dataset's roles, so there is one declaration of place and time |
| aggregate recipes (60) | records cubes; a recipe shrinks to a materialisation request (dataset, event type, axes), and the 55 SINAN copies to one rule (done: `family_specs`) |
| `count_events` | the records adapter's counting core (status, consolidation, weights): one counting path, not two |
| population series, account, modelled products | published cubes, with estimate states (`lo`, `hi`) |
| CPTEC daily | a gridded cube at day grain; `climate_weekly` is its epi-week roll-up |
| care flows | a records cube with two place axes (residence, where); `careflow.py` stays graph analytics over it |
| `load_field(name)` | kept as a name resolver: each of the 123 old names maps to its cube definition and returns the same rows, so PegaSUS (`gateway.context_field`) keeps working; it is then deprecated in favour of `cube()` |
| `aggregate()`, `capabilities()`, `serve/` aggregates | read cubes |

**Preserved without exception.** Every one of the 123 fields and the 60 recipes must answer, on the same inputs, the same
values as before. Each stage measures that, field by field, before it removes what it replaces (CLAUDE.md "never lose a
question"). Built data is not deleted until its cube reproduces it.

## 5. Stages

Each stage ends merged, verified on real data, documented, and with nothing it replaced left standing.

**Progress (2026-11-09, evaluation 2026-11-09-the-cube-stage-1).**
- **Stage 1 is done.**
- **Stage 2.**
  - **The records adapter** counts events (or rows, or sums a column) by the dataset's bindings: curated, read from
    its roles, or the place and period the intake landed each record by (`_MUNICIPALITY`, `year`, `_MONTH`: the
    binding `landed`, the default where the roles give none, as for SNGPC's municipality names). So an intake
    declaration is the one declaration of its place and time. It applies codes or prefixes in `where`, reads only the published years, and caches each cube by its data's
    fingerprint.
  - **Reproduced:** the 17 SISAGUA count fields equal cell for cell; yellow fever equal; SRAG 29 lower (the
    notifications filed twice).
  - **Population cubes** are added.
- **Stage 4 (gridded) is done.** One adapter, `climate:`, serves BR-DWGD (`climate:<measure>`, by year), INMET
  (`climate:inmet/<measure>`, by month or year: the municipality a station stands in is the place, the station a stratum that
  is never summed) and CPTEC (`climate:cptec/<variable>[@area]`, by day, epi week, month or year, aggregated inside the scan).
  `climate_weekly` is CPTEC's epi-week cube. The three stored bases are the raw observations and stay (evaluation
  2026-11-09-principles-audit-defects).
- **Stage 5 is done (2026-11-09).**
  - An aggregate artifact is its manifest alone. Its cells are the recipe's records cubes (`_aggregate._load_artifact`,
    kept by the cube store), so `aggregate()`, `capabilities()` and `serve/` read cubes through one loader and
    `cells.parquet` is gone. Equal to the old cells on AC 2022 (SIH, CNES-ST, SINASC); SIM by its 13 unplaced records.
  - Moments and log-moments come from cubes as `n`, `sum`, `sumsq` (and `sumlog`, `sumsqlog`): a variance equals the
    records' on AC 2022 SIH-RD.
  - `intake.py`'s field derivation and the stored-field writers are removed (every field is served; `lake/fields` keeps
    only the climate bases). `/population` reads the population cube; min and max come from cubes, and `ratio` (a mean
    under another name) is gone. `semantic_axes` no longer declares an axis: a binding names roles, and what its columns
    code is their roles' (ADR-0221). Recipes stay YAML: they carry labels and measures, more than a materialisation request.
  - **Done (2026-11-09):** PegaSUS's `contexts: auto` gives the same contexts before and after (evaluation
    2026-11-09-stage-5-one-door).
- **Stage 3 has measured requirements.**
  - The mirror's 1,728 CNES DBCs are the FTP's own files and are adopted into the blob store, so no download is needed.
  - The CNES fields need four things records cubes do not have yet:
    - a distinct count (establishments by `CNES`, teams by `IDEQUIPE`, persons by `CNS_PROF`);
    - an exclusion (the "other" facilities: unit types outside the listed groups);
    - a code made of two columns (equipment `TIPEQUIP` + `CODEQUIP`, the CNES equipment codelist's key);
    - a support mask (a municipality absent from December's ST register is `no_cnes_record`, not 0).
  - The professionals' fields also need the PF files, which were fetched and released when ADR-0215 was built.

1. **The cube core.**
   - The fact schema and manifest; canonical place (`geography.to_code7`, levels) and period keys; the store
     (`<lake>/cubes/<id>/`).
   - `cube()` with roll-up and the `measures.py` refusals.
   - The **published** adapter for SIDRA: every table a cube.
   - **Done when:** the 5 SIDRA-slice fields and the 21 series fields come out of `cube()` value for value, SIDRA's status
     kept, and any table nobody declared (one picked at random from the registry) is served as a cube.
2. **Records cubes on roles.**
   - The records adapter: event counting from `event_types`, axes from roles, measures from `measure_of_role`.
   - Intake declarations generate their datasets' roles.
   - **Done when:** the 46 intake fields reproduce, and the SINAN, SIH, SIM and SINASC recipes reproduce on a state-year,
     cell for cell.
3. **CNES through the one reader.**
   - The CNES fields as records cubes over the CNES datasets; `sources/cnes.py`'s mirror pipeline removed.
   - **Done when:** the 43 fields reproduce for a measured year, and every difference is explained (the mirror is a copy
     of the FTP's DBCs).
4. **Gridded, population and modelled cubes;** CPTEC's weekly roll-up as the time lattice.
5. **One door.**
   - `load_field` becomes the name resolver; `aggregate()`, `capabilities()` and `serve/` read cubes.
   - `fields.py`'s builders, `intake.py`'s field derivation, recipes as YAML, and `semantic_axes` as an axis declaration
     are removed.
   - `scripts/codehealth.py` shows no orphan.
   - **Done when:** PegaSUS's study runs (its `contexts: auto`) give the same contexts as before.

## 6. Vocabulary (applied as each stage lands)

- **cube:** the place × time object.
- **column:** a column; "field" stops naming the place × time object.
- **context:** a study's choice of cubes, a PegaSUS word, not a pegasus_data object.
- The intake's `role:` becomes `meaning:`: a column's description, not an entity.property.
- `curation/roles.yml`'s linkage block moves into `curation/roles/` (one declaration per column). Done (ADR-0219).

## 7. What a row is: one home per fact (defect 9, inventory 2026-11-09)

Where curation states it: `datasets/*.yml` `what_one_row_is` + `unit_of_analysis` (154 datasets; `grain:` blocks none); `intake.yml` `one_row` +
`unit_of_analysis` (20 sources, projected into the same dataset docs by `intake.py`: one home, not a duplicate); `roles/*.yml` `record:` (187, read by
`linkage/roles.py`, hashed into role-table keys); event types' `grain:` (falls back to `what_one_row_is`); `products.yml` `grain` and intake `period.grain`
(a product's axes and a period step: not the row). Of 148 datasets with both a roles file and a dataset doc, 123 `record` tokens appear in the unit or
description, 25 differ: the token is a coarse linkage class (every SIASUS APAC block is `procedure`), the unit the grain (SIASUS-AB authorisation,
SIHSUS-ER rejection reason, SINAN-HIVE exposed child, -HIVG pregnancy, -NTRA survey batch, -SDTA outbreak). Both are true; they are not two copies.
Done: SINAN's `unit_of_analysis: notification` ×53 stated once under `shared:` (`semantics.curation.dataset_entries`, the one reader of a file's datasets).
Decided (2026-11-09): `record:` stays where it is, the typed record class (one word from a closed set, read by linkage, the person graph and the
role-table keys), and `unit_of_analysis` stays the prose grain a person reads; deriving either from the other would turn prose into a key or lose the
grain. A roles-only dataset takes its grain from `record`, the only statement it has. Each SINAN roles file states its own `record:` because a roles
file is one dataset's whole declaration.
