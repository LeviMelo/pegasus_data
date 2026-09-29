## 2026-08-18 — V4: what a TAB_*.zip kit holds

*Split from docs/history/FINDINGS.md §1 V4 on 2026-09-28; text unchanged.*

### V4 — `TAB_*.zip` contents · **resolved**

`TAB_SIH_199201-199712.zip` (2,926,349 bytes) holds **246 members**: 177 `.CNV`, 62 lookup `.DBF`,
4 `.DEF`, 2 help files, 1 DLL. Notable lookups:

| member | rows | what |
|---|---|---|
| `CID10.DBF` | **14,197** | complete ICD-10 with Portuguese descriptions (`CID10, OPC, CAT, SUBCAT, DESCR, RESTRSEXO`) |
| `TPROC.DBF` / `TPROC10.DBF` | 7,717 / 7,712 | procedure codes and descriptions |
| `EMUSO.DBF` / `EMUSO10.DBF` | 3,206 / 3,184 | procedures flagged for multiple use |
| `TCNESBR.DBF` | 7,543 | establishments by CNES, plus 26 per-UF variants |
| `TCHBR.DBF` | — | establishments by CNPJ, plus per-UF variants |

The 14,197-row count in the brief is confirmed exactly. The modern `TAB_SIH.zip` (6,005,360 bytes,
modified 2026-08-17) carries 794 `.CNV` and 81 lookup tables.
