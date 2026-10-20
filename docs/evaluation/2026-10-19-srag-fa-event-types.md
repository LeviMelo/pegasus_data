# SRAG, yellow fever, trachoma, sporotrichosis and antenatal care: roles, descriptions and event types (2026-10-19)

**Regime.** Branch `meta-srag` from `d7d75ac`, merged with `pegasus-core-fixes` at `3e74557` (ADR-0195); a fresh data home built by the code under test
(SRAG 2019 and 2022, FA-HUM and FA-EPIZ landed through `intake`; SINAN-ESPO crawled and decoded from the FTP); `pegasus_core_data` only read. Artifacts are
not kept: every figure is re-run from the call named.

**Declared.**

| dataset | roles | event type | what a row is |
|---|---|---|---|
| SRAG-NOTIF | 194 columns + `IDADE_anos` (`roles/SRAG-NOTIF.yml`) | `notification` (kind notification), classifier `CLASSI_FIN`, consolidated by `NU_NOTIFIC`, no status | one notification of the SIVEP-Gripe SRAG form |
| FA-HUM | 15 | `case`, `present: [ID]` | one confirmed human case, at its probable place of infection |
| FA-EPIZ | 11 | `epizootic` (new kind), `persons: false` | one epizootic occurrence in non-human primates |
| SINAN-ESPO | existing | `epizootic`, classifiers `ESPECIE`, `TP_ZN_OCO`, `TP_AMB_OCO`; the shared person notification no longer holds | one notified sporotrichosis epizootic in cats or dogs |
| SINAN-NTRA | existing | none: `use: denominator` | one survey batch; its positives are SINAN-TRAC's persons |
| SISPRENATAL-PN | `NU_GESTA` corrected | none: `use: not_an_event_source` | one pregnancy-month of attendance, not an enrolment |

The descriptions of FA-HUM, FA-EPIZ and SRAG-NOTIF are in `curation/intake.yml` (they are intake sources; `known_biases` is now carried from there), their events and axes in
`declared.yml`. `undeclared_uses()` lists none of the six; `undeclared_units()` and `undeclared_fact_domains()` none of the three new role files.

**Counts through `count_events`, against an independent figure.**

| event | call | counted | independent figure |
|---|---|---|---|
| SRAG-NOTIF notification, 2022 | `count_events("SRAG-NOTIF", "notification", period=2022)` | 560,577; by `CLASSI_FIN` blank 27,877, 1: 12,576, 2: 32,881, 3: 4,259, 4: 242,528, 5: 240,456; `EVOLUCAO` 2: 92,635 | the original `INFLUD22-23-03-2026.parquet` read with pyarrow: footer 560,577 rows, 560,577 distinct `NU_NOTIFIC`, the same counts by `CLASSI_FIN` and `EVOLUCAO`. No published annual total of the notifications was found: InfoGripe's counts use only records meeting fixed sign criteria (its notice), so they are not these rows |
| SRAG-NOTIF, the float-spelled file | INFLUD19 landed; `by=["CLASSI_FIN"]`, 2019 | 48,941 rows landed (75 with onsets of 2018); 48,866 events of 2019: blank 1,026, `1`-`4` 7,029, 9,309, 190, 31,312, no other spelling | the shared home's lake holds the same file with `1.0`-`4.0` (47,840 of 47,840 filled values of the 2019 partition) |
| FA-HUM case, 1994-2026 | `count_events("FA-HUM", "case", period=...)` in two gap-free ranges | 2,911 | the file's 2,912 rows less the empty row it ends with (`ID` blank). 2016/2017: 778 cases, 262 deaths (`OBITO` SIM) against 779 and 262 in the PAHO/WHO update of 13 December 2017 (read); 2017/2018: 1,376 and 483 against 1,261 confirmed (409 deaths) of 6,525 notified on 8 May 2018 (the Ministry's monitoring report of that date, a copy on medbox.org, read), the later figure of 1,376 and 483 is the Ministry's informe 27 as a search summary quotes it (the page asks for gov.br authentication, not read) |
| FA-HUM, Minas Gerais 2016/2017 | `UF_LPI` MG | 465 cases, 152 deaths | SES-MG bulletin of 30/01/2018 (read): 475 and 162, counted in the state, where the file counts by probable place of infection |
| FA-EPIZ epizootic, 1999-2026 | `count_events("FA-EPIZ", "epizootic", ...)` | 2,637; 2017/2018: 867; 2016/2017: 425 | informe of 8 May 2018 (read): 738 confirmed of 7,410 notified; COES informe 40/2017 (read): 474 confirmed of 3,660 on 10 May 2017, and the Ministry's warning that confirmed numbers can fall on reclassification |
| SINAN-ESPO epizootic, 2013-2022 | `count_events("SINAN-ESPO", "epizootic", period=(2013, 2022))` | 32,492; `ESPECIE` 1: 31,166, 2: 1,184, 3: 142 | the system's serial `ID_NOTIFICACAO` ("número seriado ... em ordem sequencial", the dictionary): 32,492 distinct values, 1 to 32,492 with no gap |

**Decisions.**
- **SRAG has one event, the notification, and no status.** `CLASSI_FIN` has no code for a discarded case (blank is open), the Ministry reports the rows as SRAG cases, and the dictionary's
  warning on `HOSPITAL` other than 1 is not a rule the files follow (4,615 of 11,646 such rows of 2022 died of SRAG). The classifier is the final classification: the dictionary has no
  ICD-10 column. The key `NU_NOTIFIC` merges 29 notifications that sit in two yearly files.
- **Codes filed as float text are read as integers at landing (`type: int_code`).** INFLUD19 and INFLUD20 (onsets 2019 and 2020, 1,255,861 rows in the lake) file `CLASSI_FIN`, `EVOLUCAO`, `PCR_SARS2`
  and `AN_SARS2` as `5.0`, and `RAIOX_RES` is `6.0000000000` (a decimal(38,10)) in every file: an exact match on `5` missed 100% of 2020's covid-19 classifications. The existing field files
  `srag_covid` and `srag_deaths` start in 2021, which this explains (inferred, the lost declaration is not in the history). The roles list both spellings for `fatal` while a lake landed
  before this still holds `2.0`.
- **The age stratum has its own encoding, `sivep`** (`NU_IDADE_N` with `TP_IDADE`: 1 days, 2 months, 3 years), measured against `DT_NASC` and `DT_SIN_PRI` on 560,372 rows of 2022: 1.0 day,
  30.2 days and 365-368 days a unit. `IDADE_anos` of 2022: 0 to 136, one null (the age -9).
- **An epizootic is an event of animals** (kind `epizootic`, `persons: false`): no sex, age or person exposure; the population exposed is that of its place. FA-EPIZ's file is read as the confirmed
  epizootics by its size (above), which its dictionary does not state; the event says so.
- **`present`, a new key of an event type**: the columns a row must fill to be a record at all. FA-HUM ends with an empty row (`ID` blank in 1 of 2,912): without it the count is 2,912.
- **SINAN-NTRA is no event.** In 2019 TRAC lists 5,932 persons against NTRA's 6,431 positives; all 1,112 TRAC batches (unit, notification date, survey type) are in NTRA and TRAC has exactly
  `NU_CASOPOS` rows in 1,067 of them, so a weight on `NU_CASOPOS` counts each case twice and the batch has no sex or age. NTRA holds what TRAC lacks, the people examined (444,257): the denominator of a survey's positivity (survey type 1:
  1.35% positive, type 2: 4.55%).
- **SISPRENATAL-PN is no event yet.** Amapá 2013: 3,377 rows, 2,803 `NU_GESTA`; 2,485 appear once, 318 two to seven times in distinct months with `QT_CONSULT` counting up; (`NU_CNS`, `DT_INC`) gives 2,804.
  A pregnancy count needs a key no document gives, and no published total was found (TabNet's index lists no SisPreNatal table). `NU_GESTA`, read as the woman's gravidity, reaches 3,929, 122,739 and
  84,061 (Amapá 2013, 2014, Roraima 2013) and repeats across states: it is a record serial and is now `link_only`. This was a wrong label.

**Wrong statements corrected where written.** FA-HUM "suspected and confirmed" (the file is confirmed cases: the 2017/2018 season has 1,376 rows against 6,525 notified); FA-EPIZ "date and week mostly empty" (blank in 22 of 2,637);
SINAN-ESPO "one notified epizootic (cats, dogs)" without its animal nature; SINAN-NTRA "sum NU_CASOPOS for cases found" (those are TRAC's cases); SISPRENATAL-PN "one pregnancy enrolled" and "rows are pregnancies".

**Repaired on the way (all in `src`).** The `srag` intake declaration was in no commit although the shared lake holds the dataset (`families.notes` "intake: srag", fields `srag_cases`, `srag_covid`, `srag_deaths`,
`srag_icu`): `info("SRAG-NOTIF")` answered "does not resolve to a system" and `query` named no system. It is written again (`intake.yml`, the four fields as the lake's files, `DT_SIN_PRI` as the period, the residence as the place), with
the Distrito Federal's administrative regions (13,247 rows of 2022 with 5300xx codes) placed in Brasília by the landing's existing rule. `query` of an intake dataset failed on the provenance column (`_source_path` against the
intake's `_SOURCE_PATH`): `Lake.read` takes the upper-case column. An intake column's code list was never served as `CURATED.<SYSTEM>.<FIELD>`: `_inline_tables` reads `intake.yml` too, and 2022's `CLASSI_FIN`, `EVOLUCAO`,
`CS_SEXO` and `TP_IDADE` now label.

**Not settled.**
- Which epizootics FA-EPIZ holds (OQ-92). The shared home's FA-HUM has two families of 2,912 rows each (`FA_HUM_93e11462ac` with a `COLUMN15`, `FA_HUM_c5cfec72d2`): a read there may count the cases twice; a fresh landing has one.
- The shared home's SRAG lake was landed before the declaration (224 columns, float codes in 2019-2020, the DF unplaced) and its fingerprint is not this declaration's: `build_source` re-lands its eight files (about 400 MB).
- `query` over a range with a year the dataset has no row for (2012 for FA-HUM) answers "DATASUS publishes nothing for years=[2012]".
- `HISTO_VGM`, `COD_IDADE`, `REINF`, `RES_IGG/IGM/IGA` are `review: draft`: no document names their codes. The subagent's reading that `SISPRENATAL-PN`'s `NU_CNS` is stored shifted by 0x4B was not verified here.
- A pregnancy count for SISPRENATAL-PN waits for an independent total (OQ-93).
