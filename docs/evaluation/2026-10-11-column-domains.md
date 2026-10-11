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
