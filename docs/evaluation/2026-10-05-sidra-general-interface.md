## 2026-10-05: the general SIDRA interface (ADR-0142)

**Scenario.** `pegasus-data sidra scan | series | curated | fetch`, `pegasus-data fields` and `population`
through `pegasus_data.sidra`. **Artifacts.** `data/probes/sidra/2026-10-05-survey.json` (the catalog survey);
the registry, the kept responses and the facts are in the data home (`registries/sidra/`, `lake/sidra/`).
**Regime.** Data home `C:\Users\Galaxy\pegasus_core_data` (not fresh), branch `pegasus-core-fixes`, 2026-10-05,
the live IBGE server, one process at a time, 0.3 s between requests.

**What was counted, and why it is the thing that matters.**

| check | counted | result |
|---|---|---|
| The fifteen IBGE fields rebuilt through the interface against the previous implementation's output (the old `fields.py` run beside it) | every row of every partition: 83 partitions, 15 fields | **identical, schema and values** (GDP 122,540 rows in 22 years; markers `zero` and `not_available` unchanged) |
| The Census series `CENSO` (tables 1552, 1378, 9514) against the files the previous `census.py` wrote | every cell, sorted by municipality, sex, age | **identical**: 1,124,130, 1,124,130 and 1,125,140 cells; 169,799,170, 190,755,799 and 203,080,756 people |
| Each census cell set against the table's own Total, municipality by municipality | 5,507, 5,565 and 5,570 municipalities | **0 mismatches**; 58 municipalities of 2000 have a null Total (IBGE `...`), kept as nulls |
| Race × sex × single age (9606, 2010 and 2022, 11.25M values) against its own Totals | 11,135 municipality-periods | **1,549 are short of the Total, none above**: the five races add up to 6,608 (2010) and 11,119 (2022) people fewer. The same residual is left by table 9605's national margins (Total 190,755,799 and 203,080,756 against the five races), so it is people with no declared race, which IBGE lists in no category, not a loss in the fetch. Kept visible: `--validate` reports it |
| Race × sex × age band (2093, the 2000 and 2010 sample) against its Totals | 11,072 municipality-periods | differences of a few people **in both directions** (2010 national sum 190,755,800 against 190,755,799): the rounding of an expanded sample. Its 2010 top band is 70 and over (the 70-79 and 80+ cells are `...`); its race counts match sample table 136's, not the universe tables' (white 90.62M against 91.05M) |
| Planned values against rows returned | every request fetched (see below) | **0 shortfalls**: rows equal the planned value count |
| Limits | planned requests of at most 48,000 values, ID text under 3,500 characters | **0 refusals** in the planned runs; a deliberate 51,180-value request (the documented failing size) was refused with HTTP 500, halved by the safety net and returned all 51,180 rows |
| Throughput | requests of about 4 MB | median 5.6 s for 4 MB, about **8,000 values a second**; 14× smaller as gzip on disk |
| Category ids across tables | (classification, category) pairs over the scanned tables | **0 name conflicts in 20,855 pairs over 6,095 tables** (the scan was still running), so crosswalks are keyed by classification |
| Classifications with no Total | registry | 392 of 15,233; a request that omits them is answered with category 0 |
| The compendium against IBGE's metadata | 97 tables | all 97 exist and publish N6; two variable lists were wrong and are corrected in `compendium.yml` (5938 had variable 521, which is table 21's; 6917's list was table 6916's); 6 tables have variables the compendium does not mention |
| Variable kind inferred from unit and name against the compendium's kind | 291 variables | 274 agree (94%); the 17 others are monthly means the compendium tagged by their unit, so the inferred kind is the safer for refusing a sum |

**The catalog (survey, 2026-10-05).**
- 9,336 tables of 70 researches; `?nivel=N6` selects 4,448 and `?nivel=N3` 6,269. **N6 is not every municipality:**
  PNS, PeNSE and PNAD Contínua list the 27 capitals, so their health indicators are state-level; the Census (1,022 N6 tables of 1,388), MUNIC
  (186, 2005–2023), PNSB (263, 2000–2017), Registro Civil (73 of 127, 1984–2024), GDP (1999–2023), CEMPRE (1996–2024) and the Censo
  Agropecuário (1,145) cover the lattice of their year (5,507 to 5,570). The estimates (6579) are municipal totals; the projections (5
  tables) are state level and the 2018 revision.
- Census N6 tables spanning each census: 1991 58, 2000 264, 2010 444, 2022 371; 98 span two or more. Only 31 groups of tables ask the same
  question (same classifications and variables) in different periods, 2 with three vintages: cross-census series need the curated crosswalks of
  `axes.yml` and `series.yml`.
- Registro Civil births and deaths by municipality of residence, 2003–2024 (tables 2609, 2683), are the independent benchmark for SINASC and SIM
  completeness; the compendium ranks them T4. Priced with `categories:` policies: 5.4M and 10.3M values (the full cubes are 1.4G and 2.5G).

**Cost of the compendium** (`sidra curated --tier T1_CORE`, before fetching): 259M values in 7,776 requests, about nine hours; six cubes make 224M
of them (3572: 120M; 1552: 40M; 9606: 27M; 200: 13M; 2093: 13M; 616: 11M). The census series fetch only the cells they use (9606: 11.3M).

**Sanitation across the censuses** (series `households_*`, shares computed at use over IBGE's own Totals):

| | 2000 | 2010 | 2022 |
|---|---|---|---|
| households | 44,795,101 | 57,324,185 | 72,456,368 |
| sewer network, strict category | 47.2% | 55.5% | 60.4% |
| water network | 77.8% | 82.8% | 83.9% |
| waste collected | 79.0% | 87.4% | 91.7% |

The 2010 Total differs by 18 households between tables 3154 (57,324,185) and 1436/3218 (57,324,167). The 2022 sewer category "rede geral, rede
pluvial ou fossa ligada à rede" (46290) is not comparable and stays out of the series.

**Fetched at the time of writing.** At 04:50: 32 tables in the store (1,078 request parts, 39.4M rows counting overlaps, 105 MB Parquet) from the curated groups housing_sanitation (13 tables, 6.9M rows), education (8 tables, 7.0M rows; table 10062 stopped by an IncompleteRead at 18 of 59 requests and was resumed, see the ingestion state below) and the population series; income_labour and demography run next, then the remaining groups. The scan covered all 9,336 tables (4,448 list N6, 271,798 categories). Table 9860 (6.06 billion values) is skipped by size, 3572 (120M) likewise.

**Defects found by running it, and fixed.** The fact store kept the same observation twice when two selections overlapped
(Total cells fetched by a field and by a census series): reads now keep the latest. A classification with no Total made the registry load
fail on its implicit category 0. A metadata request hung for 300 s: metadata now waits 60 s. The first planner cut equal pieces (372 requests for
a cube that needs 235); it now fills each request (281).

## Ingestion state of the fetch chains (2026-10-05 09:30)

Chains `phaseb.sh` (done 06:45), `phasec.sh` (running: household_assets 7 tables and disability 4 tables done, fertility started 09:27; indigenous_quilombola, economy, pnsb_sanitation_services, civil_registry, civil_society, economy_sectors follow) and `phased.sh` (waits for phasec; its education re-run is now only cache hits). **Not finished**, so this is a snapshot, not the final count. Store at 09:29 (footer sums, `data/probes/sidra_count.py`/`.json`): 67 tables, 3,290 request parts, 117.1M rows counting overlaps, 351 MB Parquet; largest 3425 (16.8M rows), 2111 (13.9M), 9606 (12.0M), 616 (11.3M).
- **By group (rows returned, 0 shortfalls in every fetched table):** housing_sanitation 11 of 13 tables fetched in the run (6.93M rows; 1436 stopped by an IncompleteRead and fetched on a later run, 9860 skipped for size), education 7 of 8 (6.98M; 10062 below), income_labour 15 of 16 (32.7M; 3572 skipped: 119.9M values), demography 9 of 13 (7.25M; 200, 1552, 2093, 9606 skipped by the 8M ceiling and already stored by the series fetches), household_assets 7 (6.47M), disability 4 (32.4M).
- **Failures:** two IncompleteRead on large bodies (tables 1436 and 10062); no other error and no shortfall. 1436 was fetched on a later pass. **10062** was re-run alone with `sidra curated --table 10062 --fetch` through the resumable fetch: 46 of its 59 requests were already stored, 13 fetched (380,322 rows), 59 of 59 present, 2,105,460 rows = the planned values, 0 shortfalls.
- Skipped by `--max-values` on purpose: 9860 (6.06 billion values), 3572 (119.9M), and in the demography pass four cubes stored earlier.
- **`sidra check`**: axes clean (every curated category matches IBGE's name); six compendium tables list IBGE variables the compendium does not mention (21: 40, 3606: 6, 3612: 4, 5938: 39, 6916: 22, 6917: 22), a curation note, not a data fault.
- To fill when phasec and phased print ALL DONE: the last groups' rows and the final store count.
