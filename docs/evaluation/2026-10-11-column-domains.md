# What a categorical column is a fact about: `fact_domain` (2026-10-11)

**Why.** PegaSUS reads every `kind: category` role of model dimension, stratum or mark as a group dimension. `mark` mixes facts about
people or disease (SIH `MORTE`, SINAN `EVOLUCAO`) with billing and management fields (SIH `COBRANCA`, `FINANC`, `GESTAO`, `TPDISEC1-9`),
so a study could report "group heterogeneity in COBRANCA", which says nothing about people.

**Change.** Every categorical role may carry `fact_domain` (`person`, `clinical`, `process`, `administrative`) and a required
`fact_domain_evidence` (the layout label, the role, and the reason), validated by `semantics/column_roles.py` like `instruments`;
`pg.roles` returns both, `pegasus-data roles` shows a `domain` column, `undeclared_fact_domains()` lists what is not placed. The key
is not `domain`: that is a measurement's numeric range, which PegaSUS already reads. Definitions: person = attribute of the person
(race, schooling, nationality, marital status, occupation, sex, age band, residence); clinical = fact about the health event
(outcome, death, criterion, gestational stage, test result, sign, exposure, autochthony, work-relatedness, comorbidity); process = how
care or notification happened (admission character, bed specialty, complexity, place of death or birth, delivery type, medical
assistance, autopsy or exam done, referral, specimen collected, treatment given, prenatal care); administrative = billing, financing,
management, contract, legal nature, record type, internal flags, encoding units, the facility register (CNES `establishment`, `team`).

**How placed.** From each column's entity.property role and its dictionary label, by rules over the 2,621 distinct roles, then read
class by class and corrected (`scratchpad` tool, not kept: the declarations are the product). Two calls follow the instruction rather
than the first reading: `MARCA_UTI`/`MARCA_UCI` are administrative (bed-type billing marks), and the SIA/SIH exit codes (`COBRANCA`,
`PA_MOTSAI`, `PA_ALTA`, `PA_ENCERR`, `PA_PERMAN`, `PA_TRANSF`) are administrative while the death flag stays clinical.

**Result** (regime: branch `column-domains`, no lake, no network). 5,411 categorical roles in 167 files: 5,384 placed
(person 590, clinical 2,646, process 766, administrative 1,382), 27 left undeclared. Studied datasets, group set = model dimension,
stratum or mark:

| dataset | category | person | clinical | process | administrative | group set | of them administrative |
|---|---|---|---|---|---|---|---|
| SIH-RD | 45 | 6 | 6 | 3 | 30 | 41 | 26 |
| SIM-DO | 45 | 11 | 12 | 12 | 10 | 37 | 3 |
| SINASC-DN | 34 | 11 | 6 | 10 | 7 | 29 | 2 |
| SINAN-TOXG | 14 | 3 | 6 | 0 | 5 | 10 | 2 |
| SINAN-TOXC | 14 | 3 | 6 | 0 | 5 | 10 | 2 |
| CIHA | 12 | 2 | 1 | 3 | 6 | 8 | 5 |
| SIASUS-PA | 36 | 4 | 1 | 7 | 24 | 36 | 24 |

SIH-RD's 35 `mark` columns lose 26 (the billing, financing and coding fields); 15 of its 41 group columns remain. TOXG and TOXC:
the administrative five are `IN_VINCULA`, `NDUPLIC_N`, `TPUNINOT`, `TP_NOT`, `TP_SISTEMA`.

**Undeclared (27, no documentation to place them).** SINAN `DURACAO` (LEIV, "Duração"), `NUM_ENVOLV` (VIOL, "Número de envolvidos"),
`MAT_ORG` (ACBI, "Material orgânico"), `OUTROS` (DENG), `CON_DIAG_D` (HANT, name truncated), `TRATAMENTO` (TUBE: its label says "date of
treatment start", its role says entry type), `AFASTAMENT` (DERM, LER, LERD, PAIR: work leave, neither a clinical nor a care fact on
the form); SISCAN-HC `CCOLDEFAUL`, `CO_COLP_PO`, `CO_EXTEN_C/L/P/V` (meaning not established); APAC `AMP_CARACT` ("Característica", AMP
twice), `PAC_INDTRA`, `PAC_INSTRA`, `PAF_INDTRA`, `PAF_INSTRA` (no label); `CRSOCOR` (SIM, five datasets: a geographic code, not a
fact domain).

**Limits.** The reasons are family-level; a column's call rests on its label and role, not on a value-by-value reading. A person
condition recorded on a SINAN form (pregnancy, comorbidity, vaccination, habits) is `clinical`, not `person`.

## Extension: every column a study reads as a field (2026-10-11)

`fact_domain` now covers every other role a reader uses: any kind (number, date, code_tree, place, institution, text) whose model is not
`link_only` or `excluded` (`FIELD_MODELS`); `undeclared_fact_domains()` lists them with the categories. Placed by entity.property and
the dictionary label, then read entity by entity: diagnoses, causes, lab results, measurements, symptom, exposure and death dates are
clinical; procedures, care and ICU days, length of stay, sample, test, notification, investigation, registration and receipt dates and
places of care or occurrence are process; billing values, billed days, competence, manager and exit fields, system timestamps and the
CNES register (establishment, bed, team, professional, CNPJ) are administrative; age, birth, residence, occupation and the parents'
attributes are person. Obstetric and vaccination histories on a form are clinical.

Result (branch `fact-domains-all`, no lake, no network): 4,193 non-categorical field roles in 167 files, 4,176 placed (person 845,
clinical 1,157, process 1,325, administrative 849). With the categories: 9,560 of 9,604 placed (person 1,435, clinical 3,803, process
2,091, administrative 2,231); 44 undeclared. Studied datasets (non-categorical field columns): SIH-RD 71 (36 administrative: the 19 `VAL_*`,
the `US_*`, `QT_DIARIAS`, `DIAR_ACOM`, `ANO_CMPT`, `MES_CMPT`, `GESTOR_DT`, facility and manager fields; 14 process: `DIAS_PERM`,
`UTI_*`, dates, procedures; 15 clinical: the diagnoses; 6 person), SIM-DO 45 (15 clinical, 19 process incl. `DTCADASTRO`, `DTRECEBIM`,
`DTINVESTIG`, `NUDIAS*`; 10 person; 1 administrative), SINASC-DN 41 (15 clinical incl. `PESO`, `SEMAGESTAC`, `APGAR1/5`, `QTDFILVIVO`;
14 person; 11 process incl. `CONSPRENAT`; 1), SINAN-TOXG and TOXC 24 each (8 person, 7 clinical, 8 process, 1 administrative).

Undeclared, new (17): `DURACAO` (CHAG, DENG: "Duração", no unit or object), `NU_AFAST` (DERM, LER, LERD, PAIR) and `DTDIASINAC` (HANT)
(work leave, as `AFASTAMENT` before), `MUNIC`/`UF` of the PNI coverage tables (10: the label does not say whether it is where the dose
was given or where the person lives). Judgement calls: system timestamps (`DT_DIGITA`, `DTRECEBIM`) are process (a delay in the
notification chain) while `DT_ULT_ALT`, `DT_CRIACAO`, `DT_CARGA` are administrative; SIA/APAC exit dates follow the exit codes
(administrative).
