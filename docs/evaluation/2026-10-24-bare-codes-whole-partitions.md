# Bare codes of the whole latest partitions, searched (2026-10-24)

**Regime.** Branch `worktree-agent-ad89aab6c65d033e1` from `4fcfe5b` (pegasus-core-fixes), 2026-10-24. The starting point is
`data/probes/decode_coverage/2026-10-24-whole-partitions.json` (`decode_coverage.py` on `751c987`, the real catalog curated at `9d2936c`, every
family's whole latest partition): 191 labelled family-columns with bare codes (135 dataset-columns) and 56 coded family-columns bare entirely (32).
Measured on a copy of the real catalog (`sqlite3` backup, `curate` run on the copy with the branch's curation), the real lake and registries read
through directory junctions; the real home was not written. "Before" is that artifact, or the same renderer on a copy of `src` with the three ICD
files of `4fcfe5b`; "after" is the branch. Artifact `data/probes/decode_coverage/2026-10-24-bare-codes-fixes.json`. The columns outside the brief
are untouched (SIM `ESC`/`GESTACAO`, SINAN `ID_OCUPA_N`, SDTA, SIFC, `AP_MNDIF` ...: 104 labelled and 33 bare family-columns); the numbers below are for the
columns the pass re-measured: 87 labelled family-columns (68 clean after, 17 with cells left, 2 no longer a code) and 23 bare ones (20 clean, 3 with cells left).

## 1. ICD-10: the table stopped at 2008

`icd10.parquet` held the 2008 edition and 30 later codes. DATASUS publishes its own v2019 tables (`SIM/CID10/TAB/CNVS_CID10_v2019.rar`,
2025-10-13, 58 files; DATA_SOURCES) and `build_icd10.py` now reads them for the codes the 2008 edition lacks (ADR-0087, amended): 197 codes new to
the table, 19 kit abbreviations replaced by DATASUS's full description, 20 filler forms; the four WHO emergency codes keep their 2020 date; a code
the 2008 edition has keeps its label (the v2019 files reword 2,360 of them, some cut at a column width). The code trees are rebuilt from it.
Checked against WHO's ICD-10 2019 browser for A97 (0, 1, 2, 9), K64, C86 and R65 (0 to 3, 9): same codes, same meanings.

| renderer, the ICD columns of the latest partitions | bare cells before | after |
|---|---|---|
| SIM-DO `CAUSABAS`, `CAUSABAS_O`, 9 families (2009-2025) | 3,225; 2025 `CAUSABAS` 2,156 (A97.9 1,036, A97.2 702, A97.1 231, A97.0 55, R65.2 53, K64.9 35, C86.0 10, R65.1 7) and `CAUSABAS_O` 1,062 | 12; 2025 `CAUSABAS` 0 and `CAUSABAS_O` 5 (`J19`, `A149`, `I53` ...: no ICD-10 code) |
| SIM-DO `LINHAA` to `LINHAII` (tokens left `(?)`, 9 families) | 7,755 | 1,259 |
| SIM-DOREXT 2025 | 1 + 3 tokens | 0 |
| SIH-RD `DIAG_PRINC`, `DIAGSEC1-3` (two 2025 families) | 10 (U09, U10) | 0 |
| CIHA 2025 `DIAG_PRINC` | 3 (U09, U10) | 0 |
| SIA (`CIDPRI`, `CIDSEC`, `CIDCAS` ...) | 14 (`f99` lowercase, `L76`, `J49`, `STST`) | 14, no ICD-10 code |

Over every held partition (read directly, 2026-10-24) 208,517 cells hold a code the table gained: SIM 203,862 (11,083 bare and 192,779 read through the
subcategory fallback, "categoria N18 (subcategoria N18.5 não consta da CID-10)", now exact: R57.2 99,254, I48.9 28,202, C80.9 16,471, L89.9 15,244,
C79.9 10,843, N18.5 6,376), SIH 2,364 (140 and 2,224), CIHA 1,643 (311 and 1,332), SIA 648 (2 and 646), SINAN 0. The dengue deaths are 5,804 cells
(A97.9 2,923, A97.2 2,031, A97.1 602, A97.0 248) in `CAUSABAS`, `CAUSABAS_O` and the lines. Not in DATASUS's table: A09.0 and A09.9 (WHO 2019 has them; 1,741 and 3,313 cells of `CAUSABAS` over the held
years) keep the category fallback. The change reaches queries with the package: the renderer reads `icd10.parquet`.

## 2. SINAN-DENG, CHIK, LEPT

**The 0 is Espírito Santo's.** In SINAN-DENG 2018-2024 (13,460,004 rows) every cell of 0 in `SOROTIPO` (286,068), `HISTOPA_N`, `IMUNOH_N`, `RESUL_*`,
`CLINC_CHIK`, `EVOLUCAO`, `CLASSI_FIN` (8,678), `CRITERIO`, `HOSPITALIZ`, `ALRM_*` and `GRAV_*` (and the 9 of the signs and conditions) is on a
notification of that state (SG_UF_NOT 32), 100.0 % of each, none from the other 26 UFs. Rival readings, tested: a clinical "No" (the 0 would sit on
asked fields: in 2024 the 134,177 zeros of `ALRM_HIPOT` are all on cases classified 10, which are not asked for warning signs, while that state's 11 and 12
answer 1, 2 or 9; the 136,819 zeros of `GRAV_PULSO` include none on a case classified 12); a death, for `EVOLUCAO` 0 (none of its 2,206 has a death date,
all 70 coded 2 or 3 have one). It is the state's export writing 0 for a form not answered, and DATASUS's own tables say so: the kits' `Sim_nao.cnv`,
`Resultado.cnv`, `Sorodeng.cnv`, `Classdeng.cnv`, `Clinic_chi.cnv` send blank and every digit they do not list to "Ign/Branco" (`,0-9`), `evodeng.cnv` the 0 and the 9.
The roles already listed 0 as not recorded; the tables now name it. `TP_SISTEMA` 0 (136,988 rows of 2024, 8,726 of 2021) marks two of that state's
batches; its meaning is in no document and `FLXRECEBI` 0 (its only value, on those rows) and `TPAUTOCTO` 0 (50 cells; `Autoctone.cnv` lists only the blank) stay undecoded.

**`CLASSI_FIN` 8 is Inconclusivo.** `Classdeng.cnv` and `Classifi.cnv` (LEPT) list it; the Sinan Online dictionary of 2015 does not. The 1,447,939 rows of 8
(542,641 in 2024) are not the discarded nor the confirmed: of those tested in 2020 the 5 (Descartado, 538,654 rows that year) are positive in 1.8 % (NS1), 1.5 % (IgM) and
0.6 % (PCR), the 10 in 71 %, 92 % and 77 %, the 8 in 44 %, 50 % and 14 %; the 8 is closed (99.9 % have `DT_ENCERRA`) and has no criterion in 93 % (2024; the 10 and the 5 have one).
LEPT 2015-2024: the 6,439 rows of 8 are closed, 97 % without criterion (1 and 2: 2 %), any positive result 16.5 % (confirmed 43 %, discarded 1 %), no death. LEPT `LAB_MICR_1/2` 4 (130, 269) is in
neither the dictionary nor `Reage.cnv` (`,0-9`: Ign/Branco).

`NDUPLIC_N` is blank, 1, 0 (that state's zeros) or `/` in 2018-2024, never 2, so ADR-0159's duplicate rule removes nothing from dengue; said where the rule is declared
(`datasets/sinan_agravos.yml`). A consumer project's audit reported the same for 2010-2026; only the years held were measured.

| 2024 file / held file | bare cells before | after |
|---|---|---|
| SINAN-DENG, 46 columns (`CLASSI_FIN` 542,641; `SOROTIPO` 131,058; `GRAV_*` and `ALRM_*` 3.26 M over 24 columns; `HISTOPA_N`, `IMUNOH_N`, `CLINC_CHIK` 81,467 ...) | 4,563,864 | 273,988 (`TP_SISTEMA`, `FLXRECEBI` 136,988 each, `TPAUTOCTO` 12) |
| SINAN-CHIK 2019, 8 columns | 470 | 2 (`CLASSI_FIN` 0 and 8, one row each: `Classchik.cnv` lists neither) |
| SINAN-LEPT 2024, `CLASSI_FIN`, `LAB_MICR_1/2` | 1,626 | 0 |

## 3. SIH-RD

- **`DIAGSEC9` is not a code.** The DBF header declares it `C(1)` in the 4,592 + 457 files of the two signatures that carry it (DIAGSEC1-8 are `C(4)`; the layout prints
  `char (4)`), and every value it holds is one letter (916 of 12.35 M rows in the 2025 files, 1,007 in 2014-2024; `S`, `K`, `J`, `R` ...): the first character of a ninth
  secondary diagnosis. A letter names a chapter or two, not a code; the role is now `text` (791 + 218 cells of the two 2025 partitions leave the bare count).
- **`FONTE_ORC` 00 stays undecoded** (2,481,005 of 2,481,010 rows in the largest 2025 file; 01, 03, 04 on 411 rows of the year). `FONTEREM.CNV` lists 01 to 04 and blank/`zz`; no layout names the field
  (`IT_SIHSUS_1603` does not; the FTP's `Doc/` holds only it); the 00 is not "Ign/Branco" there. Nothing in a document or the records says what the 00 is.

## 4. The other columns

| column | before | decided | source and test |
|---|---|---|---|
| CIHA `GESTAO` D | 2,658,974 | `D` Dupla | CIH kit `GESTAO.CNV` "Dupla = D"; CIHA's kit and layout list no D; the 836 hospitals in both files of 2011-01 to 2011-04 carry the same code in both (358 M, 249 D, 229 E, none differs) |
| Painel de Oncologia `ESTADIAM` 0-4 | 147,184 | Estádio 0, I, II, III, IV | `Dicionario_Painel_Oncologia.pdf` seq 15 "0 - 0, 1 - I ... 4 - IV, 5, 9"; `ESTADIAMENTO.CNV` prints the digits as labels and the pack kept 5 and 9 only |
| SIA `AQ_TRANTE` 0 | 576,689 (47 % of the chemotherapy APACs of 2023-2025) | "Não informado", role `missing` 0 | layout and `TRA_ANTE.CNV`: S, N, blank. 28 % of the 0 give a previous treatment's diagnosis and date, against 92 % of S and 0.3 % of N: neither a No nor a Yes; 157 of 338 establishments write 0 on every row |
| SIA `MN_IND` U | 34,344 + 22,752 | `U` Individual | kit `MANT_IND.CNV`: M, I; files: M, U. U is on 100 % of the rows with `CNPJMNT` blank or zeros ("or zeros if it has none") and M on all but 0.01 % of the rest (SIA-PS 2012-2025) |
| SIA-PS `TP_DROGA` | 5,906 + 66 | OA, CA, OC, CAO, OCA, AOC, labelled in the order written | layout: A, C, O in a `CHAR (3)`; the kit's table is fixed in the order A C O. Left: AOO, OOO, OO, OCO, COO, OOC, CC, CCC (a letter twice: not defined), N, NNN, 0, 206 |
| SIA `AP_UFNACIO` 10 | 11,410 + 7,278 + 4,049 | `10` BRASIL, only | the table has 328 three-digit codes. Of the 10,811 patients with a `10` row, 1,304 also appear with a three-character nationality and 1,301 (99.8 %) with `010`. The other 135 + 30 + 57 cells (22, 27, 45, 43 ...) also read as state codes; not decoded |
| age-unit columns (`COD_IDADE`, `AP_COIDADE`, `TPIDADEPAC`) | all bare | correct, the scan was not | they decode with their age ("67 anos", IDADEDET: the unit digit and the two age digits are one code); the scan rendered the unit alone. `decode_coverage.py` now carries the age column in the batch: 20 family-columns clean. Left: unit 3 with age 00 (CIHA 65,884, CIH 4,704; IDADEDET lists months 01 to 11) |

**Left undecoded, with what was tried.**
- SIA `AQ_GRAHIS`/`AR_GRAHIS` (1,018,055 of 1,157,141 cells in AQ): the Manual Onco (campo 59) and `GRAU_HIS.CNV` print GX, G1 to G4; the files hold over 60 spellings (digits 0 to 11, X, II, G6 ...) and `2` and `02` coexist
  in 79 of the 107 establishments that file `02`. No document gives the digits and padding would be the guess the rule forbids.
- SINAN-TUBE `TPUNINOT` (68,580 of 81,933 cells in 2023): `C(2)`, holding `2` and ` 2` (left and right justified), never `02`; the single digits 1, 2, 4, 5, 7 are the single-digit-capable codes of `TipoUnidade.cnv`
  (01, 02, 04, 05, 07), but the table is keyed `02` and the file carries no unit identifier (`ID_UNIDADE`) to test the type against the CNES registry. `POP_SAUDE` 3 (4,804) and `POP_IMIG` 3 (389): São Paulo
  alone (24,922 notifications in 2023), every year 2019-2023, never in `POP_LIBER`/`POP_RUA`; the dictionary prints 1, 2, 9.
- SINASC `TPDOCRESP` 0 (101,554 of 2.4 M in 2024; 339,755 of 2.9 M in 2016): the layout prints 1 to 5. The 0 goes with a function coded 5 "outros" in 65 % (2016 and 2024) and none in 23 %; RS, MG, PR, CE lead.
  Consistent with "no document", not shown to be it.
- SIH-RD `FONTE_ORC` 00, SINAN-DENG `TP_SISTEMA` 0, `FLXRECEBI` 0, `TPAUTOCTO` 0, CHIK `CLASSI_FIN` 0 and 8: above.

## Findings

- **A scan that renders a column alone misses a composite key.** The age units were counted bare; the unit and the age are one IDADEDET code. The script now reads them together.
- **"Bare" and "read through the category" are different states.** 192,779 SIM cells of ICD-10 had a label ("categoria N18 ...") that was exact for no code; the count of bare cells never saw them.
- **A zero can be one state's export.** 100 % of 17 fields' zeros on one UF, with the field not asked on the rows that hold it, is the test that separates a clinical No from a filler; the same kit tables that call it Ign/Branco say what to label.
- **`harvest_codes.py` cannot be re-run as it stands.** Run unchanged it rewrites 46 lines of `codes/sinan.yml` that the hand corrections of 2026-10-24 had fixed ("Autônomo/cont a própria", "gnorado": line-break glitches of the PDF text);
  the supplements were merged into the shipped file in place with the harvest's own rule (the file round-trips byte for byte through `yaml.safe_dump`), and `supplements.yml` carries them for the next harvest.
- **A field the dictionary lacks needs its whole table.** DENG `GRAV_ORGAO` is in no dictionary; supplementing only 0 and 9 replaced the pack's 1 and 2 (9,742 cells went bare) until 1 and 2 were declared from `Sim_nao.cnv`.
- **A YAML edit can drop a key silently.** An `Edit` that ate the `AP_UNISOL:` line merged two variables; `curate` reported 5,418 variables instead of 5,419, which is how it showed.

## To run on the real home

`pegasus-data curate --root C:/Users/Galaxy/pegasus_core_data` (variable docs and the roles reach the catalog; the code tables are read from the YAML). The ICD-10 and code-tree files are in the package and need no rebuild; no label-pack rebuild is needed for any of this.
