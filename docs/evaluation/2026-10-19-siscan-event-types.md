# SISCAN: event types for its 15 datasets, counted against the raw files and TabNet's own base

**Regime.** Branch `meta-siscan` (from `pegasus-core-fixes` `d7d75ac`, then merged to `3e74557`), 2026-10-19; a fresh data home; one national CSV year (2013, the smallest complete one) per 2013-onwards dataset, one state-month per SISCOLO/SISMAMA series. Script and output: `data/probes/siscan_events/` (`count_new_event_types.py` through `count_events`; `independent_figures.py` reads the same files with ftplib, pandas, `datasus_dbc` and `dbfread`, never `pegasus_data`; `counts.json`, `comparison.json`).

**Declared** (`curation/datasets/siscan.yml`, which replaces the five SISCAN entries and the stale `SISCAN.PACNT` of `declared.yml`): an event type for all 15, none with a status rule.
- `exam` (kind `exam`) on the ten exam datasets. Five are weighted because a row is a group of identical exams: CC and HC by `QTDEXA`, CM, HM and MM by `QUANTEXAME` (the Ministry's TabWin increment "Quant. Exames"), and SISCAN_CITO_MAMA by `QT_EXAME` (the only 2013-onwards CSV that merges identical exams). The other four CSVs are one exam a row.
- `examined_patient` (kind `examinee`) on the five `_PACNT` files, consolidated on (`CO_PACIENTE`, competence year): a woman a year with her worst result (Notas Técnicas 1, 4, 9, 10, 14). It is another event, never added to the exams it republishes.
- Primary classifiers are the result: the 13-category laudo (CITO_COLO), the BI-RADS code (MAMOGRAFIA, MM), the lesion class (HISTO_MAMA), the squamous result (HISTO_COLO), the aspiration result (CITO_MAMA, CM), the patient file's laudo; SISCOLO's cytology has no single result column, so its adequacy partitions and the result families follow.
- Per-dataset `semantic_axes` replace the system-level ones (`ANO_COMP` and `CO_MUN_UNIDADE_SAUDE` do not exist in the CSVs, and the latter is empty): residence for every dataset, plus the collecting unit's municipality for the five SISCOLO/SISMAMA series. New kinds `exam` and `examinee` in `event_types.KINDS`.

**Counted, against what.**

| event, file | `count_events` | independent figure | |
|---|---|---|---|
| CITO_COLO exam, 2013 | 134,887 | CSV rows 134,887; TabNet kit RJ 57 = 57 by month (1, 2, 11, 9, 22, 12) | equal |
| CITO_MAMA exam, 2013 | 666 | CSV 604 rows, sum `QT_EXAME` 666; kit 716 rows, equal by state in 13 of 14 | SP: kit 208, CSV 158 |
| HISTO_COLO exam, 2013 | 1,210 | kit 1,210 rows, equal in 17 of 17 states | equal |
| HISTO_MAMA exam, 2013 | 444 | kit 444, equal in 15 of 15 states | equal |
| MAMOGRAFIA exam, 2013 | 93,229 | CSV rows 93,229; kit (DF only) 25 = 25 | equal |
| CC, AC 2010-03 / RN 2013-09 | 5,781 / 9,844 | `dbfread` on `datasus_dbc`'s DBF: 5,675 / 9,727 rows, sum `QTDEXA` 5,781 / 9,844 | equal |
| HC SP 2013-09, CM BA 2013-09, HM SP 2014-06, MM AC 2014-06 | 2,320, 596, 1,558, 784 | rows 2,277, 524, 1,329, 728; sum of the weight the same | equal |
| `examined_patient`: CITO_COLO, CITO_MAMA, HISTO_COLO, HISTO_MAMA, MAMOGRAFIA, 2013 | 131,366, 520, 1,174, 420, 91,992 | distinct (patient, year) of the CSV; rows 132,182, 520, 1,193, 420, 91,992 | equal |

The weight is what makes the row counts wrong: 5,675 rows are 5,781 exams, and CITO_MAMA's 604 rows 666. Its rule is tested on the one file with an individual-level twin: the kit has one row per exam, and the CSV's `QT_EXAME` sums to the kit's row count in 13 of 14 states. SP's 50 more exams in the kit are all December (kit 100, CSV 50; one municipality 62 against 31); not explained. Identical rows are exams: the kit, which adds the patient's CNS and the dates, holds the same 1,210 and 444 rows as the CSVs while having only 3 copies in each.

**Found on the way**
- **TabNet's SISCAN pages fail** (2026-10-19): `dhdat.exe?SISCAN/cito_colo_resid` (one of the fifteen links of the Ministry's page; the only one tried, with `.def`, `.dhd`, `deftohtm`, `tabcgi` and SISCOLO/SISMAMA guesses) answers a Python traceback ("No such file" in `dhdat.py`) and `deftohtm.exe` "Arquivo DEF não encontrado", while `deftohtm.exe?sih/cnv/niuf.def` answers (browser User-Agent, curl and the in-app browser alike). The kit's DBFs (`sources/tabkits/.../TAB_SISCAN/DADOS`, CC for RJ only, MM for DF only) are the independent base.
- **The facility columns of the CSVs are empty** in CITO_COLO and MAMOGRAFIA (`CO_UNIDADE_SAUDE`, `CO_PREST_SERVICO` and their municipalities and states): 2013 whole, and head and tail (about 16,000 rows) of 2014, 2016, 2018, 2020, 2023 and 2025. The roles declare them for 2013-2025. The exam has a residence and no place of occurrence.
- **The result codes are the counters.** CITO_COLO's `CO_LAUDO_CITOPATOLOGICO` follows TAB_SISCAN's `laudo_citopatologico.cnv` (no `.def` binds it): each code's rows carry exactly the matching counter (08 on 1,129 rows = `NU_LESAO_IE_BAIXO_GRAU`, 10 on 1,908 = ASC-US ...), and `00` (1,141) is the 56 rejected plus 1,085 unsatisfactory samples. HISTO_COLO's squamous result 01-06 equals NIC I, II, III, micro-invasive, invasive, not assessable (4,951, 2,653, 2,894, 117, 660, 109 in 2014). `NU_AMOSTRA_REJEITADA`, `NU_AMOSTRA_SATISFATORIA` and `NU_LIMITE_NORMALIDADE` are 0 on every row read.
- **`CO_PACIENTE` is stable across years**: the 24, 52 and 14 ids found in both the 2013 and 2014 files of CITO_MAMA, HISTO_COLO and HISTO_MAMA agree on municipality, race and sex in all 90. 0.6% (CITO_COLO) and 1.3% (HISTO_COLO) of the women of 2013 have 2 to 4 rows in a year, so the Nota's one-row rule does not hold on them; the key keeps the first.
- **SISCOLO and SISCAN overlap in 2013-2015 without containing each other**: RN 2013-09 holds 9,844 SISCOLO exams and 3,653 SISCAN ones, 81 municipalities in both, 39 only in SISCAN, 32 only in SISCOLO. No exam key is shared; the datasets say not to add them.
- Corrected where written: the ontology's five patient files were "a row per patient and competence month" and a "dimension joined to the exams" (a row per patient and year, no exam key); five SISCOLO/SISMAMA descriptions and CITO_MAMA's said "one exam a row"; `joins.yml` said the id's stability was unestablished; `OPEN_QUESTIONS` 54 called the CSV header-less (it has a header).

**Not settled** (OQ-91): why the kit's SP December 2013 has 50 more exams; whether an exam is in both SISCOLO and SISCAN in 2013-2015; the women counts have no independent figure (TabNet down); the labels of `CO_LAUDO_CITOPATOLOGICO`, `NU_LAUDO_HISTOP`, `TP_LAUDO_CITOP` and the HISTO_MAMA codes are not bound (the codes follow the CNVs and the counters, but no `.def` ties them); the patient files' `CO_FAIXA_ETARIA_PACIENTE` (CITO_MAMA, MAMOGRAFIA) holds an age in years while its role says an age bracket; `C_NEO_MALI` of SISCOLO's HM holds `06` and `006` for one code.
