# Missing codes declared by the record's own form, across SINAN

**Date and regime.** 2026-10-08; pegasus-core-fixes; `scripts/propose_missing.py SINAN-<series> 2019-2021` on the repo's own data home. Logs:
- `data/probes/p1/`: the first rule, morning;
- `data/probes/p1b/`: the refined rule;
- `data/probes/p1c/`: the newly reviewed forms and the dengue check;
- `data/probes/review/`: the review sheets and decisions.

**What was counted, and why.** The SINAN columns whose missing codes the proposer can declare, and the source each declaration rests on. PegaSUS reads a category column only once its missing codes are declared. A wrong declaration is a wrong label, invisible downstream.

**The rule, refined the same day (corrected here).** The morning's rule declared only the codes the form itself calls not recorded. It made a code the form does not define, such as the tabulation's `0` "Ign/Branco", an undecoded value. This note first said that the tabulation "lumps documented and undocumented codes", citing CONJUNTVIT 5. That is wrong where a code is undocumented: the form is silent there, and the tabulation's reading stands. The rule now:
- A code the form defines with a meaning is that meaning, whatever the tabulation's catch-all calls it ("the form overrules").
- A code the form does not define, which the tabulation calls not recorded, is not recorded.
- Without the form's dictionary, the tabulation alone declares nothing.
- A code the records use that the form does not define, and the tabulation does not call not recorded, is written into the evidence as a CONFLICT (added after the cases below).

`--check --write` re-reads already-declared columns by the same rule and replaces the ones that differ, with their evidence.

| series | the form decides | the tabulation only (left undeclared) | the form overrules |
|---|---|---|---|
| CHIK | 58 | 18 | 0 |
| HANS | 10 | 5 | 0 |
| IEXO | 18 | 11 | 0 |
| LEPT | 41 | 9 | 0 |
| MENI | 33 | 27 | 1 |
| SIFC | 18 | 12 | 1 |
| TUBE | 23 | 22 | 1 |
| VIOL | 76 | 40 | 1 |
| SIFA, SIFG, ZIKA | 0 | 24 | 0 |

277 declarations rest on the form (from 232 under the first rule).

**The second wave** (`data/probes/p1c/`). 43 newly reviewed forms, read over 2019–2021 or 2020–2021, or 2019 where a form's later files are published empty (PEST, LER):
- The form decides 950 columns.
- 524 have only the tabulation to rest on and stay undeclared. Most belong to forms whose dictionary is not harvested: PFAN 118, HIVC 76, SDTA 64, EXAN 50.
- The form overrules the tabulation on 18 codes. Most are "não se aplica" or "não utilizada": LEIV `DROGA` 6, `FALENCIA` 4, ANTR `FIM_ANIMAL` 5.
- ANTR's wound sites print 3 "Desconhecida". That means unknown, so the rule now reads it as not recorded (5 columns re-declared).
- The dengue check: 71 of its 72 hand declarations agree with the rule. The 72nd (HOSPITALIZ) differs only because 2021's labels are narrower than the 2019–2023 labels it rests on; it was kept, and the limit is documented in `--check`.

**The 39 conflicts, by cause:**
- **Widths.** The form prints `01`–`09` where the records use `1`–`9`, or the reverse: ACGR/ACBI/DRT `SIT_TRAB`, `TIPO_ACID`, `PART_CORP1-3`, DERM `AGENTE`, `LESAO`, HEPA `FONTE`, `FORMA`. Codes are never padded, so those values stay undecoded, visibly. A width-aware codelist is the follow-up.
- **The dictionary omits codes the system computes.** AIDA `ANT_REL_CA` 36–90: the dictionary itself stops at 34 (read again after the page-header fix). AIDA/AIDC `CRITERIO` 101 and 601. TPRAPIDO2 3 and 4, which the two sibling tests document.
- **Titres the form does not type as numbers**: CHAG `TIT_*`.
- **Isolated codes**: HEPA `HIV` 3, RE_ANTIHBC 5, ANTR `CONDIC_ANI` 0, ESQU `STCURA2` 0, MALA 12.

**What PegaSUS reads** (`pegasus-core coverage`, every dataset with event types):
- 62 of 67 datasets run; 2,714 of 5,335 columns are read (2026-10-07: 674 of 2,175 over 23 datasets). SINAN: 54 datasets, 2,318 of 4,610 columns.
- The rest by reason: 938 missing codes not declared (one source only), 527 excluded by their role (free text, administrative), 300 drafts, 246 numbers that are not measurements.
- The 5 that do not run:
  - ESPO, NTRA, SDTA and TRAC record surveys, outbreaks and epizootics, not persons, and have no residence stratum;
  - CIHA's age unit 5 is unresolved (OPEN_QUESTIONS 74).

**The overrules, read against the records** (a form is a source, not the truth):
- SIFC `LABC_IGG` 4 "não se aplica": the largest category, 15,353 of 27,186 recorded in 2021. The tabulation's labels would have read most records as missing.
- TUBE `BACILOSC_E` 4 and VIOL `LES_AUTOP` 8, also "não se aplica".
- MENI `ANT_TRAUMA`: the dictionary prints "1. Sim / 3. Não / 9.Ignorado", but the records hold 1, 2 and 9 and never 3. The 2010 count was 23,627 of 27,721 recorded with code 2. The dictionary's 3 is a typo; 2 = Não is added by `curation/codes/supplements.yml`, with both claims cited.

**Field layouts harvested** (`scripts/harvest_codes.py`).
- The harvest now keeps every field's type (date, number, text), width, label and any code table it names, not only its codes: 2,293 SINAN fields typed.
- Against the previous output, no code table was lost or changed.
- Two defects were found by reading tables against the records:
  - ESQU `EVOLUCAO`: "1 – Cura 2, Não Cura" was read as one code. The records use 2 (65 in 2021); corrected by a supplement.
  - ESQU `AN_QUANT`: an attempted rule treated number-typed code lists as quantities, which the records refuted. The field holds 0 and 1 only (1,298 and 1,096), a flag as the form prints it. The rule was withdrawn.
- The role drafter (`scripts/draft_column_roles.py`) types a documented column by its form. It covers every SINAN form in the catalog, and it takes a role from the shared notification block or from another form only where both forms print the same label and the same codes or type. Codes alone are no meaning (every yes/no shares them), nor is a type alone (`DT_COLETA` is a blood bank's sample on HEPA's form).

**Draft roles reviewed.** Each drafted column was read against its form's layout, its variable note and one year's values (sheets and decisions in `data/probes/review/`):
- AIDA 78 of 78, HEPA 81 of 81, LEIV 98 of 113, LTAN 87 of 115, LEPT 8 more.
- First role files for 12 forms: ANTR, ANIM, ACGR, ACBI, FMAC, HANT, COQU, ESQU, TETA, DIFT, FTIF, MALA.
- Left as drafts, each with its reason: 2000–2006 legacy columns with no source for that layout (their variable notes borrow other forms' meanings: LEIV `DOSES` "rabies doses", `TUBE` "occupational"), ANTR `DOSES` (most often 13, 24, 31), FTIF's undocumented `UF`.

Found in the records along the way:
- ACGR 2021: B34.2 (coronavirus infection) is the most frequent injury code, 36,357 of 218,860: COVID-19 notified as a work accident.
- AIDA 2021: only 21,327 of 38,060 records carry the investigation form (`ORIGEM` 1).

**Place columns.** A place column is read only when it names a code system that nests in the residence's.
- State columns were given IBGE's (`UF_BR`) where the values prove it: TUBE `SG_UF_2` 70,875 of 70,875 in 2021, VIOL `SG_UF_OCOR` 373,172 of 373,172.
- Abbreviation columns keep their reason: MENI's hospital state (0 of 10,455 numeric), SIFC's two (525 of 26,570).
- Weeks and years are calendar indices, never measurements (`column_roles`: a property ending in `week` or `year`). SINAN-HANS's diagnosis week had been modelled as a measurement.
