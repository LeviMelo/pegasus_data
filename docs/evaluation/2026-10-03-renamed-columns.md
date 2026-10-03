# Renamed columns: what values can and cannot show

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`;
- a fresh data home, with files read through the HTTPS mirror (about
  0.6 GB);
- run by a Sonnet agent; the findings below were reviewed before curation.

**Script and artifact:** `scripts/column_renames.py`, artifact
`data/probes/schema/column_renames.json`. The artifact holds every candidate
pair with its scores and runner-up, the files read, the boundaries skipped,
and the pure additions and drops.

**Why.** OQ-57: columns present in one layout and absent in the next may be
one variable under two names. File presence pairs every unique field with
every other, so it cannot choose. What is counted: for each pair of adjacent
layouts of a dataset, how closely each old-only field's value distribution
matches each new-only field's (1 − total variation, `tv`), against the best
rival.
- Sample: one file per layout, the same state where possible, up to 200,000
  rows.
- A pair is "strong" only when it matches closely and no rival comes near.

**Coverage.** 286 layout boundaries in 162 datasets:
- 93 had fields unique to both sides and were sampled, across 24 datasets;
- 185 had unique fields on one side only: 144 pure additions and 41 pure
  drops;
- 8 were skipped: 2 because the mirror lacks the file, 2 because the
  decoder gave no table.

**Strong renames** (name similarity agrees in every case, but was not part
of the score):

| dataset | old → new | boundary | tv | runner-up |
|---|---|---|---|---|
| SIM DOINF / DOEXT | FILHVIVOS → QTDFILVIVO | 1995 → 1996 | 0.89 / 0.86 | 0.55 / 0.53 |
| SIM DOINF | FILHMORT → QTDFILMORT | 1995 → 1996 | 0.91 | 0.55 |
| SIM DOINF | PESONASC → PESO | 1995 → 1996 | 0.86 | 0.08 |
| SINASC DN | FIL_VIVOS → QTDFILVIVO | 1995 → 1996 | 0.81 | 0.40 |
| SINAN hantavirus | CONF_INF_U → COUFINF | 2006 → 2007 | 0.81 | none |

SIM DOFET `BAIRES` ↔ `CODBAIRES` matched strongly, but in opposite
directions at two adjacent boundaries (1996 → 1997 and 1997 → 1998). That is
not a single rename, and it was not curated.

**What values cannot show.** Renames where the coding changed with the name
score about zero:
- `DATAOBITO` → `DTOBITO` and `DATANASC` → `DTNASC`, where YYMMDD became
  DDMMYYYY;
- SINAN `NU_IDADE` → `NU_IDADE_N`, where `A031` became `4003`;
- SIH `DIAG_SEC` → `DIAG_SECUN`, where procedure codes became ICD codes.

These need a document or a decoding rule, not a value match.

**Ambiguous because rivals share a code domain.** Pairs such as SIM
`ESTCIVIL` → `ESTCIV`, SIM `MUNIRES` → `CODMUNRES`, and SINAN-DENG
`CON_EVOLUC` → `EVOLUCAO` and `CON_CLASSI` → `CLASSI_FIN` are likely by name,
but a rival of the same domain scores within 0.15. One-digit codes (1/2/9)
make 70 such ties, mostly in SINAN; values cannot separate them.

**SINASC-DNR `CODIGO` and `CONTADOR`,** the example OQ-57 began from, are
not the same variable: tv 0, Jaccard 0. `CODIGO` is an 8-digit identifier,
and `CONTADOR` a sequence.

**What was done.**
- **The five strong renames are written into the curation of both names**
  (`notes` or `vintage_note`), where `info()` and the dictionary show them.
- **Columns are not merged in a query.** A query over both eras still
  returns both columns, each null in the other era.
- **OQ-57 stays open, narrowed:** whether to merge confirmed renames at
  read time, and the coding-changed renames, which need documents.
