# pegasus_data

**Brazil's national health data, with its meaning attached.**

DATASUS publishes the administrative record of a health system serving 215
million people: 208,095 files and 991 GiB on one FTP server, twenty information
systems, 1992 to now. It publishes almost nothing that explains them. There is
no index of what exists and no machine-readable schema. The meaning of a code
lives in `.CNV` files written for a DOS tabulation program, in PDFs, and in the
names of directories.

pegasus_data reads that tree and hands back tables whose codes carry their
meaning: which classification a column uses, which version of it applies to the
year you read, which columns are dead, and what nobody has been able to
document.

> A number you cannot trace is worth less than no number.

```python
from pegasus_data import query

table = query("SIH.RD", period="2022-01", geography="AL",   # hospital admissions, Alagoas
              select=["MUNIC_RES", "SEXO", "DIAG_PRINC"])
table.to_pandas().head(2)
```

```text
  Município de Residência do Paciente (MUNIC_RES)  Sexo do paciente (SEXO)  Código do diagnóstico principal (DIAG_PRINC)
0                    Delmiro Gouveia, AL (270240)             Feminino (3)             Parto espontaneo cefalico (O800)
1                    Delmiro Gouveia, AL (270240)             Feminino (3)             Parto espontaneo cefalico (O800)
```

---

## Install

Python 3.11 or newer.

```bash
pip install pegasus-data          # library and CLI
pip install "pegasus-data[all]"   # + PDF, Excel, RAR and Polars support
```

From a clone: `pip install -e ".[all,dev]"`.

The wheel carries a **seed catalog** of the whole tree: every file with its
system, series, state, date and schema family, and every curated column
description. It also carries the **label pack** (3.65M code ranges). So a fresh
install answers `info()`, `explore()` and `search()` offline, and its first
`query()` downloads only the files it reads.

**Where the data goes.** `pegasus-data where` prints the data home and which
setting chose it. Set it with `pegasus-data config set --root D:/datasus`, or
with `PEGASUS_DATA_HOME`.

---

## Five minutes

### What exists

**Start here, whether you are a person or an agent:** `pegasus-data info` (or `print(info())`) prints everything this
install holds and can do, in about 370 lines: every dataset with its columns, years on the server and rows held, every
context field (climate, GDP, CNES supply, water, schooling…), every record link and aggregate, and the functions and
commands by area, each with the call that gets it. Read it whole before concluding something is missing; then
`search` for the column, role, SIDRA table or code.

```python
from pegasus_data import info, explore, search

info()                    # everything held and doable (the map's overview)
info("SIH.RD")            # one dataset: what one row is, coverage, schema generations, gotchas
info("SIM.DO.IDADE")      # one variable: its meaning and where that meaning comes from (a layout, or "INFERRED … unverified")
levels("SINAN-TOXG", "EVOLUCAO", ["1", "2", "9"])   # codes to labels, chosen as a query chooses them (pass every code the column holds)
query("SIH.RD", period=2016, rows={"DIAG_PRINC": ["B58", "P371"]})   # only those records, filtered in the scan
query("SINASC.DN", period=2019, geography="AL",
      condition=[{"role": "birth.weight", "op": "<", "value": 2500}])   # a condition on roles, not codes; the records it cannot
                                                                      # decide (weight not recorded) are counted apart: condition_report(table)
count_events("SIM.DO", "death", period=2019, condition=[{"role": "deceased.age_years", "op": "<", "value": 28, "unit": "days"}])  # events, unknown
explore("SIH.RD")         # years, states, files and bytes on the server, offline
explore("SIH.RD", year=2023, uf="SP")   # the files themselves, with sizes
lake_coverage("SIH.RD")   # what the local lake already holds, by year: partitions, states, rows, bytes
publications("SIH.RD", range(2014, 2024), ufs="AL")   # which files it was read from, one row each: the server's size and date, the digest
                          # decoded, when and from where fetched, the rows, preliminary or final; the files listed but not held, with why
dataset_facts("SIH.RD")   # what the curation documents of a dataset, with its sources: what a row is, its dates, the events, the notes
garbage_codes()          # the ICD-10 codes of little use as an underlying cause, with their GBD level 1-4 and package (GBD2017 for França's list)
price_index(reference="2025-12")   # IBGE's IPCA by month (or grain="year"): `factor` x a nominal amount = reais of December 2025
search("raça")            # columns about race: RACACOR, CS_RACA, RACA_COR …, each hit with the call that gets it
search("link deaths")     # anything: datasets, columns, fields, roles, events, links, aggregates, operations, SIDRA tables
cube("sidra:5938/37", place="uf")   # any IBGE SIDRA table as place x period (x strata): GDP by state, IBGE's statuses kept
search("Parda", kind="code")            # which codes mean "Parda", in which tables
```

Dataset names are the ontology's codes: `SIH.RD`, `SIM.DO`, `SINASC.DN`,
`SINAN.DENG`, `CNES.ST`, `SIA.PA`. `SIH-RD`, `SIHSUS.RD` and a bare `RD` mean
the same thing everywhere.

### Data

```python
from pegasus_data import query, plan

print(plan("SIM.DO", period=2022, geography="AL").explain())   # what will be read, before reading it
deaths = query("SIM.DO", period=2022, geography="AL")
births = query("SINASC.DN", period=("2020", "2022"), geography=["AL", "SE"])
dengue = query("SINAN.DENG", period=2022, select=["NU_IDADE_N", "CS_SEXO", "ID_MN_RESI"])
```

- **`period`** is `YYYY`, `YYYY-MM` or a `(start, end)` pair.
- **`geography`** is one state or several. Both select **DATASUS
  publications**, the files the Ministry cut by state and month. They never
  filter record variables such as the date of admission or the municipality of
  residence. Ask for a month of an annual dataset and you get the year, with a
  warning.
- **`present`** decides how the result reads (ADR-0084). The default,
  `"readable"`, puts meaning first and keeps the code in parentheses: values
  `Masculino (1)` under headers `Sexo do paciente (SEXO)`. A code no table
  decodes stays visibly undecoded: `9 (?)`. Other presets: `"analysis"` (raw
  codes plus `<column>_label` columns, for code that joins and groups on
  codes), `"labels"` (labels only) and `"codes"` (as filed). Any part is a
  template you can change, per call or as your default in `pegasus-data.toml`:

  ```python
  query("SIH.RD", period="2022-01", geography="AL",
        present={"values": "{code} - {label}", "names": "{name}", "language": "en"})
  ```
- **Derived columns come with it.** `IDADE_anos` is age in fractional years
  (18 months = 1.5), decoded from each system's own age encoding for SIH, SIM
  and SINAN.
- **`return_report=True`** also returns what was read, what was skipped and
  why, which columns could not be labelled and why, and which editions of a
  publication were superseded.
- A request that would download an unbounded history is refused unless
  `allow_unbounded=True` is passed.

`query` reads a lake you have built wherever it covers the request, and the FTP
server otherwise. The table is Apache Arrow: `.to_pandas()`, Polars and DuckDB
read it directly.

### From the command line

```bash
pegasus-data query SIH.RD --period 2023-01 --geo AL,SE --out sih.csv
pegasus-data query SIM.DO --period 2020..2022 --geo AL --present analysis --dictionary sim_dictionary.md --out sim.parquet
pegasus-data query SIM.DO --period 2022 --geo AL --values "{code} - {label}" --language en --out sim.csv
pegasus-data info SIH.RD
pegasus-data search raça
pegasus-data explore SIA.PA
```

`--dictionary` writes one entry per column: its curated name and description,
the table that decoded it, the evidence rung and the source it is documented
in.

### Labels for data you already have

```python
from pegasus_data import translate
labelled = translate("my_sih_extract.csv", system="SIHSUS")
```

### Aggregates

`aggregate()` serves prebuilt municipality × time cells (counts, sums and
means stored as mergeable states) that roll up through health regions, states
and the country without touching microdata. `serve/` exposes them over HTTP.

### Cubes

`cube()` is the one place × time object (ADR-0217): `cube("sidra:5938/37", place="uf")`
is IBGE's GDP by state, any SIDRA table without a declaration;
`cube("records:SRAG-NOTIF/notification", periods=[2022], grain="month", by=["CS_SEXO"])`
counts a record dataset's events by municipality, month and a column, with the event
type's own rules (duplicates, consolidation). Roll-ups follow the source's additivity and
are refused otherwise; a part without a value makes a total `incomplete`, never a
short sum. The other sources:

```python
cube("records:SIM-DO/death", by=["SEXO", "FAIXA_ETARIA"], periods=[2022], geography="AC",
     derived={"FAIXA_ETARIA": {"age": "IDADE_anos"}})          # age banded as SIM declares its age
cube("records:SIH-RD/rows", measure="VAL_TOT", periods=[2022])  # a column's sum; "A+B", "count:COL", "distinct:COL"
cube("climate:precipitation_mm", periods=[2023])               # BR-DWGD, municipality x year, with its months held
cube("climate:inmet/precipitation_mm", by=["station"], periods=[2023])   # INMET stations; a station is never summed
cube("climate:cptec/tmax@area", periods=["2023-03"], grain="epi_week")  # CPTEC daily grid: sums and days held
cube("modelled:population_account/population", by=["sex"], periods=[2022], where={"race": ["total"]})
cube("population:POPSVS", by=["sex"], periods=[2022])
```

A record no municipality places is counted in the cube's manifest (`unplaced_events`), never
a cell; a modelled estimate carries its bounds and is summed only when its product declares
it additive. Aggregate recipes (`build_aggregate`) are built from these cubes.

### Context: dimensions, enrichment, geography, fields

The record says what the source wrote; these add what it means and where it
happened. All of it is labelled with its source, and a value the source does
not hold comes back as `not_recorded`, never as a guess.

```python
from pegasus_data import (query, memberships, municipality_point, distance_km, cep_points, mesh, load_field, grade_cells,
                          tract_population, climate_daily,
                          load_population, race_reliability, age_standardised_rates)

# Roll a code up a published hierarchy (curation/joins.yml): ICD-10 chapter,
# the Ministry's mortality list, avoidable deaths, primary-care-sensitive admissions.
deaths = query("SIM.DO", period=2022, geography="SE",
               dimensions=["CAUSABAS.chapter", "CAUSABAS.avoidable_5_74",
                           "CODMUNRES.health_region_current"])

# The establishment as it was registered in the record's month (CNES.ST).
admissions = query("SIH.RD", period="2022-01", geography="AL",
                   enrich=["CNES.MANAGEMENT", "CNES.CARE_LEVEL", "CNES.HAS_NEONATAL_UNIT"],
                   present="analysis")   # raw codes, which race_reliability reads

memberships("280030").as_dict()      # health region, macroregion, comparable area, ...
municipality_point("280030")         # (lon, lat): the Grade Estatística population centre, or kind="seat"
distance_km("355030", "330455")      # 339.5 km, population centre to population centre
cep_points(uf="AL", municipality="270430")  # IBGE's CNEFE 2022: where each CEP lies inside its municipality (one row per CEP and
                                     # municipality): the median position of its addresses, the distance within which half and nine tenths
                                     # lie, address and household counts, census tracts; `pegasus-data cnefe` builds it, `cep-points` reads it
mesh("state")                        # IBGE polygons (GeoDataFrame: code, geometry), "municipality" too; fetched once
concept_index(["B58", "P37.1"], ["toxoplasm"])  # SINAN agravos holding the codes (counted), SIGTAP procedures
                                     # compatible with them, ICD-10 and SIGTAP labels matching the terms
dispensed(["G20"])                   # SIA AM medicines authorised under the codes: SIGTAP procedure, name, APACs (the lake's latest year)
stock_by_state(["pirimetamina"], 2025)  # BNAFAR stock of a drug by state and month, read by CATMAT filter (sources/bnafar.py)
build_extract("SIASUS-PA", range(2010, 2026), {"PA_PROC_ID": ["0202030768"]})  # the records the filters match, its
                                     # files read one by one (a dataset larger than the lake); extract_table reads them back
treatments(["B58"])                  # the medicines an official document gives for the codes (curation/treatments.yml),
                                     # with each one's SNGPC and CATMAT spelling; concept_index returns them too
captures(["P37.1"])                  # the populations systems list for capture–recapture (curation/captures.yml)
condition_codes(); procedure_compatibility()  # its two tables: each record's own condition code (SINAN's ID_AGRAVO), SIGTAP's
                                     # procedure-ICD compatibility; label_matches(terms, "SIGTAP") its label search
procedure_instruments(["0202030768"])  # the instruments SIGTAP registers a procedure on (BPA, AIH, APAC, RAAS, e-SUS APS): ["01", "02", "05"]
can_record("SIA-AN", "AP_PRIPAL", codes)  # whether a dataset's column can hold any of the procedures: True, False, or None (undeclared or
                                     # unknown; the declarations are `instruments:` in curation/roles). False means skip the dataset
load_population(series="POPSVS", years=2022)  # the denominator the Ministry divides by (OQ-12); table.schema.metadata[b"pegasus.series"]
                                     # says what it is: producer, vintage, reference date, years, method, with the documents
load_field("gdp", years=2021)        # IBGE municipal GDP and value added
grade_cells(municipality="2704302", resolution=1000)  # IBGE's Grade Estatística 2022: people and households per cell and
                                     # municipality, summed into IBGE's 1-500 km cells (`pegasus-data grade` builds it)
tract_population(municipality="2704302")  # Census 2022 residents per tract by sex and age band; IBGE's suppressed `X` is null
tract_aggregates("cor_ou_raca", municipality="2704302")  # Census 2022 colour or race per tract, a column per IBGE variable; tract_dictionary("cor_ou_raca") gives the labels
tract_aggregates("renda_responsavel", municipality="2704302")  # income of the household head per tract (decimals: V06004 mean, V06006 median; suppressed null)
weighting_area_table("renda_domiciliar_per_capita", municipality="2704302")  # the sample's income by weighting area; tract_weighting_area() maps a tract to its area
climate_daily(["tmax", "precipitation"], municipality="2704302", start="2024-01-01", weight="population")
                                     # CPTEC's SAMeT and MERGE by municipality and day, where people live (or weight="area");
                                     # as_of="2024-03-01" gives the values as published by then; climate_weekly sums epi weeks
query("FA-HUM", period=2017)         # a source off the FTP (curation/intake.yml, intake.py): yellow-fever cases, records in the lake;
                                     # its context fields (load_field("yellow_fever_human_cases")) are derived from them;
                                     # S2iD disasters ("S2ID-EVENTOS"), the school census ("INEP-EDBASICA") and ANS beneficiaries
                                     # ("ANS-ICB") are such sources too, landed with `pegasus-data fields`
race_reliability(admissions)         # flags SIH hospital-months whose race code is unusable
age_standardised_rates(deaths, year=2022, uf="SE")   # crude and WHO-standardised rate per 100,000
```

- **Dimensions** roll a code up:
  - **diagnoses** through TabWin concept lists (`.CNV`) read as trees;
  - **procedures** through SIGTAP's group, subgroup and form of
    organisation, as derived columns you select (`PROC_REA_grupo`,
    `PROC_REA_subgrupo`, `PROC_REA_forma`; pre-2008 codes bridged);
  - **any municipality column** of nine systems through any classification
    of the geography pack (`CODMUNRES.health_region_current`,
    `MUNIC_MOV.ibge_immediate_region`).

  Each is joined by validity window. A code no table covers, or a membership
  the systems contest, stays null and is counted in the report.
- **Enrichment** reads `CNES.ST` at each record's competence: 17 attributes
  (ADR-0125), plus `CNPJ` and the establishment's name.
- **Geography** resolves a municipality to every unit it belongs to: IBGE
  regions, health regions and macroregions (as of TabNet's current table),
  and IPEA's comparable areas for 1980, 1991 and 2000 to 2010. Where systems
  disagree the conflict is reported, not resolved. Build it with
  `pegasus-data geography`.
- **Fields** are municipal context: the IBGE aggregates API (GDP, value
  added; Census sanitation, literacy and population by race), BR-DWGD climate
  by municipality-month and S2iD disaster events, built
  with `pegasus-data fields --name gdp --years 2010-2021`. Daily weather (CPTEC's MERGE and SAMeT, 2000 to the day
  before yesterday, by population or area, every vintage kept) is read with `pegasus-data climate-update`, daily.
- **SIDRA**, IBGE's whole aggregates catalog (9,336 tables), through one interface: `pegasus-data sidra search esgoto --level N6`,
  `sidra show 6805`, `sidra fetch 6805 -p 2022 -c 11558=all`, then `Sidra().labelled(6805)` for the facts with labels and
  IBGE's marks as a status. Mobility between municipalities: `pegasus-data mobility` builds commuting (Census 2010), coach and boat links (IBGE 2016) and air passengers by month (ANAC); `proximity_graph("air_passengers", vintage=[202401])` reads them (ADR-0211). `Sidra().describe(t)["basis"]` (and a `basis` column in `labelled`) says whether a table is the Census universe or a sample estimate, from IBGE's note or the table's CV variables (ADR-0206). Series across censuses (`Sidra().series("population_age_sex")`) keep both claims where tables overlap (ADR-0142).
- **Quality flags** say which values not to take at face value. SIH race
  code 04 is a default or a swapped code in some hospitals (ADR-0128).

### Linking records across systems

The public files carry no common person identifier, so records about the
same person are linked through what they state about that person and a shared
event. Every linkage reports its own error.

```python
from pegasus_data import link, role_table

result = link("sih_deaths_to_sim", period=2022, geography="RR")   # a LinkResult
result.summary()   # pairs per pass, chance pairs from the negative control, validations, verdict
result.pairs       # record ids (file hash:row) on each side, and the pass that linked them
```

- **The declared links** are in `curation/links.yml`:
  - in-hospital deaths → death certificates;
  - infant deaths → birth records;
  - births → the mother's delivery admission.
- **Roles.** `role_table(dataset, …)` gives any dataset's records as the
  properties they state (`mother.birth_date`, `patient.sex`), normalised
  (the `compare:` columns of `curation/roles/<dataset>.yml`).
- **Refusal.** A linkage that is not viable raises `LinkNotViable` instead of
  returning pairs.
- **Discovery.** `discover_links("SINASC-DN", "SIH-RD", period=2022,
  geography="RR")` measures which fields two datasets share people through.
  Every key built from type-compatible roles is counted against a placebo,
  and the keys come back ranked by the pairs they isolate beyond chance
  (ADR-0119). Command line: `pegasus-data link-discover`.
- **Persons.** `build_entities(period=2022, geography="BR")` merges every
  stored link of a scope into persons, refusing a merge that would give one
  person two birth records or two deaths. `person_pairs(...)` lists any two
  kinds of record of one person, including pairs joined only through other
  links. Command line: `pegasus-data link-entities`.
- **Uncertainty.** Probabilistic pairs carry `p_match`, the calibrated
  probability that the pair is true. `link_draws(pairs, n=20)` yields
  plausible link sets for multiple imputation; combine the analyses with
  `linkage.uncertainty.combine` (Rubin's rules).
- **Cohorts.** `linked_deaths("SIH-RD", ["I21", "I22"], years=range(2018, 2023),
  geography="AL")` returns the first admission of each person with those
  diagnoses and the date of the death certificate (any cause) found within a
  year, or none, with the false-match rate and verdict of each horizon;
  `.mortality(30)` and `.mortality(365)` count over those followed that long. The
  run is computed once per codes and stored (ADR-0194).
  `linked_outcomes(..., link_name=...)` reads any cohort link the same way, the
  columns named for the event (`event_date`, `days_to_event`, `partner_record`)
  and `partner_roles=` adding the partner's own roles: a tumour's surgery to its
  radiotherapy (`sih_admissions_to_radiotherapy`, the APAC's pathology date).
- **Command line:** `pegasus-data link sih_deaths_to_sim --period 2022 --geo
  RR`; `pegasus-data link sih_admissions_to_sim --period 2018..2022 --geo AL
  --codes I21,I22`. The method is in ADR-0107, ADR-0110 and ADR-0111.

---

## The data model

```text
system        SIH          an information system, as the Ministry runs it
  dataset     SIH.RD       one of its published datasets
    family    113 columns  a schema generation of that dataset
      column  DIAG_PRINC   with its meaning, its codelist, and when it existed
```

**Systems and datasets are declared, not derived.** "SIH publishes a dataset
called AIH Reduzida, known as RD" is a fact about how the Ministry organises
itself. It lives in `curation/ontology.yml` (20 systems, 131 datasets), and the
FTP layout is evidence for it, never its definition. One archive can hold seven
datasets, one dataset can live in two directories, and one publication can be
split into lettered parts (`PASP2301a`, `b`, `c`). Every data file binds to a
declared dataset.

**Schema generations are first class.** SIH-RD has 20 generations, from 35 to
114 columns. `info("SIH.RD")` shows what each generation added and dropped,
which decides whether years either side of a boundary can be pooled.

**Structural absence is not missingness.** SIH-RD's nine secondary-diagnosis
columns do not exist before 2014. A query spanning the boundary unions the
generations and marks those rows null *structurally*, in the report, rather
than letting the gap read as unrecorded diagnoses. `availability("SIH.RD")`
and `field_available(...)` answer "did this column exist in that year" as
present, absent or unknown. Existing is not filling: `field_fill(dataset,
fields, years)` counts, per year, the records whose value is neither empty
nor one of the column's declared missing codes (SIM's `CB_PRE` exists from
2014 and fills almost no record).

Some forms spread one variable over columns, each column a cell of its axes (CNES-ST's attendance type × payer, AP##CV##). `grids(dataset)` lists them and `grid_table(dataset, name, period=..., geography=..., keep=[...])` reads one long, one row per record and cell.

**One codelist per column per schema generation.** A column is bound to every
TabNet table that mentions it (31 for SIH's `CNES`, 294 for PNI's `MUNIC`).
Which one actually labels it is decided once:
- curation first;
- otherwise measured against real files, with per-state slices of national
  tables set aside;
- a table that only rolls codes up (a municipality to its health region) is
  never a label.

Codelists are keyed by system and by validity window, so a 1995 admission
decodes against the 1995 table. When no table decodes a column, the code stays
raw and the report says why. A guess would be worse than a gap.

**Joins are declared, with their grain.** `SIH.RD` is one row per admission
(`N_AIH`) and `SIH.SP` many, so joining them and counting rows counts
professional acts. `curation/joins.yml` records each key and each side's grain.
Keys that people want but that do not exist are recorded as well: SISCAN exams
cannot be followed across patients.

**Personal identifiers pass through unmodified, and stay flagged.** Masking in
a library would destroy the evidence of what was published, and deciding what
may be disclosed about a person is not a data library's call. Some public
SIASUS files publish real professional CPFs and re-identifiable patient
records, and some SINAN files still carry full birth dates. See `DATA_SOURCES.md`.

---

## How it works, briefly

```text
ftp.datasus.gov.br ─► crawl (the whole tree in ~30 s) ─► catalog: files, strata, schemas, families
                   ─► download on demand ─► decode (DBC/DBF/CSV/XML/archives, in killable workers)
                   ─► normalise ─► label (the seed's bindings + the label pack) ─► your table
                                └─► optionally, a partitioned Parquet lake
```

`HOW_IT_WORKS.md` walks through it, and `ARCHITECTURE.md` maps the code.

---

## Documentation

The project's record follows one model (ADR-0001):

- **[`STATUS.md`](STATUS.md)**: what is true now, and what is being worked on.
- **[`CLAUDE.md`](CLAUDE.md)**: how to work on this repository, and the rules
  that are not stylistic.
- **[`HOW_IT_WORKS.md`](HOW_IT_WORKS.md)** and
  **[`ARCHITECTURE.md`](ARCHITECTURE.md)**: the system in prose, and the map
  of the code.
- **[`DECISIONS.md`](DECISIONS.md)**: every decision, with its evidence and
  what would reverse it.
- **[`EVALUATION.md`](EVALUATION.md)**: every measurement and live run,
  including the August 2026 lab notebook.
- **[`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md)**: what is not known, and what
  would settle it.
- **[`DATA_SOURCES.md`](DATA_SOURCES.md)**: measured facts about DATASUS,
  IBGE, SIGTAP and the rest.
- **[`RUNBOOK.md`](RUNBOOK.md)**: commands.
- **[`GLOSSARY.md`](GLOSSARY.md)**: the terms.

---

## Contributing

`curation/*.yml` holds what a variable *means*, the part no crawl can produce.
It is version-controlled because an assertion needs an author and a diff. Each
entry carries the rung of evidence behind it (layout document, TabNet `.DEF`,
web source, or inferred with its reasoning). A person's curation outranks
everything the machinery measures.

Changes are verified on the live system: `scripts/live.py` runs the scenarios
in this README against the real server on a fresh data home (CLAUDE.md §5).

MIT licensed.
