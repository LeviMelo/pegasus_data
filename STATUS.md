# STATUS.md

What is true now. This file is rewritten in place, never appended to. Its
history is in git; measurements are in `EVALUATION.md` and decisions in
`DECISIONS.md`. Last rewritten 2026-10-04; the declarations section 2026-10-08.

## Where the project is

`redesign` (2026-09-28 to 09-30: meaning on the read path, every variable
described and code translatable, ADR-0061 to ADR-0106) was live-verified and
fast-forwarded into `master` on 2026-09-30, locally (not pushed). Work
continues on branch **`linkage`**: record linkage across systems, planned in
`docs/plans/linkage.md` (ADR-0107).

## Declarations and labels (branch `pegasus-core-fixes`, 2026-10-08)

Work for PegaSUS's work plan units P1 (declarations at scale) and P2 (labels across schema generations).
- **Roles.** All 166 catalog datasets have role files: 10,456 columns, no drafts, and a variable note on every column (evaluation 2026-10-08-typing-every-dataset). CNES's five template "series" removed; SIH's CM files moved from SISCAN to SIH; IBGE's three population publications no longer summed as one.
  - Done: every SINAN form with records but COLE and TETN, SIM's and SINASC's ten sub-series (legacy layouts on their 1996+ roles), SIH's seven, CIH, and SIA's twenty (PA among them; SIA.PR newly declared).
  - Each column is decided from its evidence sheet (`scripts/role_evidence.py`): its variable note, its form's layout, its values.
  - Also done: CNES (13), Dados Abertos (13), PNI (6), SISCAN (15), SIH-CM, IBGE (9), RESP (2), SINAN COLE and TETN, e-SUS Notifica, Painel Oncologia, PCE, SISPRENATAL.
  - Event types for 74 datasets (from 67; SDTA withdrawn, an outbreak per row, OQ-76), all of which PegaSUS now reads (3,556 of 6,137 columns): DOREXT, DNEX, CIH-CR, Painel Oncologia, RESP, DCCR, and SIA PA, BI, PS and SAD, whose rows weigh their approved quantity (ADR-0155, OQ-75 resolved); eleven name-guessed dataset declarations corrected (DOR, DOREXT, DORIG, DNR, DNEX, DNRIG, NTRA, TRAC, ESPO, SIH MT, BASE_AIH1).
  - Declarations corrected by testing them on records: IBGE POP/POPS/POPT and ESCA/ESCB were summed; SISCAN's CSVs and the SI-PNI residence extracts were unreachable behind other declarations; SIH's CM files sat under SISCAN.
  - Missing codes: RESP, Painel Oncologia and CIH from their own forms; SINAN's yes/no convention (9 = Ignorado in 943 of 943 harvested tables) for form-less flag columns. CIH/CIHA age unit 5 is decades (OQ-74 resolved); CIHA runs in PegaSUS.
  - SIA's APAC code tables declared (AN, AQ, AR, ATD); a tabulation band is a domain only where the records stop at its edges (ADR-0154 addendum).
  - Next: the APAC columns whose tabulation alone names their codes (AP_CODEMI, AP_COIDADE, AP_ETNIA, AP_UFNACIO); CNES-ST's flag grids as their two axes (attendance type × payer, level × management).
- **Missing codes.** The form decides where its dictionary is harvested, and the tabulation speaks only where the form is silent.
  - A code the records use that neither defines is written as a CONFLICT (evaluation 2026-10-08-declarations-by-form).
  - Two dictionary errors were corrected by supplement, with both claims cited.
- **Labels.** The label pack chose a vintage before a system, which left SIH 2008–2010 and 378 system-codelists unlabelled in the pack fallback. Fixed (OQ-73); the SIH 2010 links are being recomputed.
- **Throughput.** `translate` takes 0.1 s a call (from 22 s).

## Record linkage (branch `linkage`, ADR-0107 to ADR-0124)

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
  - `climate`: INMET station-month precipitation and temperature, placed in
    the municipality each station stands in (1961–2025, 912 stations).
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

## The PegaSUS handoff (2026-10-04, `2026-10-04-pegasus_data.md`)

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
- **Age and sex plausibility (2026-10-06):** `code_attributes()` carries NCHS Part 11 Table G's edits (absolute or conditional) beside the release's RESTRSEXO; the two sex sources agree wherever both speak. The SIM kit's typed garbage codes are the code list `SIM-POUCO-UTEIS` (types as written, not interpreted). ICD-9 → ICD-10: `code_bridge("ICD9-ICD10")` from NCHS's 1996 double-coding study (2,296,922 deaths; 410 → I21 97.6 %, 486 → J18 65.7 %, NCHS's published pneumonia ratio about 0.70).
- **Not done:** a later DATASUS release (only V2008 is harvested; the harvested page is a frame stub with no version, and `CID10CSV.ZIP` answered 404 on 2026-08-19, `sources/hdr_CID10CSV.ZIP.txt`), ICD-9, ICD-O, the further lists and the relation graph.

## Waiting on the user

- **Publishing.** `master` (fast-forwarded to `redesign`) and `linkage` are
  not pushed (CLAUDE.md §4). Platform wheels for the compiled DBC engine
  (ADR-0074).
- **GBD's licence** (OQ-69): IHME's non-commercial agreement against an
  open-source package.

## Tests and checks

- `scripts/live.py --all --fresh` and `scripts/sweep_undecoded.py` on a fresh
  home.
- `ruff check src scripts tests` and `scripts/check_docs.py`.
- `pytest -q -m "not network"` is a regression net that does not grow
  (CLAUDE.md §5).
