# TUSS terminology and the TUSS to SIGTAP correspondence, measured on TISS hospital items (2026-11-22)

**Regime.** Branch `worktree-agent-a95dcbc6e3a01353c` off 86d42f52, a scratch data home (deleted after). `pegasus-data tuss` read ANS's PDA 049 (`pda-049-tuss.zip`) and
`padraotiss_mapeamento_tuss_sigtap.zip` (sources and versions in DATA_SOURCES §17); the intake landed one unit of `ans_tiss_hosp_det`, AC 2024-03 (`_land_unit`, 3,854 rows equal to the file's
3,855 lines less the header), and `query("ANS.TISS_HOSP_DET", period="2024-03", present="analysis")` rendered it after `pegasus-data curate`. Scripts were scratch (not kept); the counts below
are the artifact.

**Labels.** `CD_PROCEDIMENTO` is bound to the `TUSS` codelist keyed by `CD_TABELA_REFERENCIA` + `CD_PROCEDIMENTO` (the mechanism of CNES `CLASS_SR`, ADR-0088, now read from an intake column's
`key:`), dated by `code_windows`. Of the 3,854 items: table 22 1,618, table 63 1,087, own table (`00`) 754, medicines (20) 374, packages (98) 18, OPME (19) 3.

| items | n | named |
|---|---|---|
| table 22 | 1,618 (245 codes) | 1,618 (100%), 245 codes |
| table 63 | 1,087 | 1,087 (100%) |
| tables 19, 20, 98 and own (`00`) | 1,149 | 0: not held, or not a TUSS code |

Every table-22 code of the sample is in the terminology. A code of one table can equal one of another, which is why the key is the pair, and an own-table item (`00` + `TABELA PROPRIA`) matches nothing.

**Correspondence to SIGTAP** (of the 245 table-22 codes, 1,618 items): 185 codes (75.5%), 1,189 items (73.5%) have at least one mapped SIGTAP procedure; 58 codes (427 items) are in the workbook with no
answer (`not_yet_mapped`); 2 codes (2 items) are not in it (terms newer than 2016-06). By the best degree of equivalence of an item's pairs: 1 (same meaning) 83 items, 2 (synonym) 343, 3 (TUSS less specific)
596, 4 (more specific) 132, ungraded 464 (grade absent, doubtful, or no pair); grades 1-2 make 26.3% of the items. Whole terminology: of 5,966 terms 5,700 are in the workbook, 3,172 of those mapped,
152 marked not in SIGTAP; of the 48 terms that name the spine or a vertebra (orthopaedic spine surgery is TUSS 30715xxx, 14 terms), 32 are mapped.

**Findings.**
- A term's start of validity is that of its current version (a 2024-06 revision of a 2010 term starts 2024-06; the file lists no ended term): windowing by the start alone left 13 items of March 2024 undecoded.
  The window is therefore from the earlier of start and implementation (`DT_FIM_IMPLANTACAO`), and one name serves every year: a procedure renamed since is named as today.
- The correspondence is a 2017 workbook for the TUSS of 2016-06: use it for the families it covers and read `mapping` and `equivalence` before treating a pair as the same procedure; a conversion needs the
  degree and a choice among several SIGTAP codes (one term maps to up to 111).
- Not done: tables 19 (1.39 M OPME terms) and 20 (45,355 medicines) and the small domains (23, 57, 41, 39, 50, 76, 52, 24, 77, 36, 60, 79), which would name the other items; the ANS OCL service
  holds the same terms with dates. AC 2024-03 holds no item of 30715xxx, so the spine families were checked on the workbook only.
