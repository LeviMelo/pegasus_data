## 2026-08-18 — V2: the self-extracting .exe payload is LHA, with seven DBF members

*Split from docs/history/FINDINGS.md §1 V2 on 2026-09-28; text unchanged.*

### V2 — self-extracting `.exe` payload · **resolved, and it is not what was predicted**

The brief: *"These are a PE stub with a standard archive appended. Strategy, in order: Python
`zipfile` directly, then `rarfile`, then `7z` via subprocess, then a raw signature scan for
`PK\x03\x04` and `Rar!\x1a\x07`. Expected payload: one or more `.dbc` or `.dbf`."*

Measured on `/dissemin/publicos/SIASUS/APAC/2002/acac0202.exe` (21,354 bytes):

- The stub identifies itself as **`LHA's SFX 2.13S (c) Yoshi, 1991`**.
- The payload is an **LHA archive using method `-lh5-`**, header level 0, beginning at offset 1636.
- `PK\x03\x04` does not appear anywhere in the file. Neither does `Rar!`. `zipfile` raises
  `BadZipFile`; `rarfile` rejects it. The predicted ladder fails at every rung except `7z`.
- The payload is **seven** DBF members, not "one or more":

  | member | bytes | fields | what it is |
  |---|---|---|---|
  | `ACAC0202.DBF` | 75,066 | 19 | APAC master record (`APA_*`) |
  | `COAC0202.DBF` | 55,498 | 14 | billed procedures (`COB_*`) |
  | `OPAC0202.DBF` | 31,715 | 17 | other procedures (`OPC_*`) |
  | `PFAC0202.DBF` | 11,536 | 21 | patient, radiotherapy (`PAF_*`) |
  | `PCAC0202.DBF` | 7,204 | 21 | patient, chemotherapy (`PAC_*`) |
  | `UDAC0202.DBF` | 4,092 | 66 | dialysis unit (`UDI_*`) |
  | `EXAC0202.DBF` | 3,756 | 13 | serology (`EXA_*`) |

**Consequence for the design.** One archive is *seven logical datasets with seven distinct
schemas*, so an archive member has to be a first-class row in the family model. The prior
implementation's `choose_archive_member()` — which selects a single "best" member — would have
discarded six of the seven.

**Implementation.** `decode/lha.py` implements `-lh0-`/`-lhd-`/`-lz4-` (stored) and
`-lh4-`/`-lh5-`/`-lh6-`/`-lh7-` (LZSS + static Huffman) in pure Python, so the package does not
require an external binary. Verified byte-exact against 7-Zip on all seven members. `7z` remains a
fallback for `-lh1-` and friends, and its absence degrades to a recorded decode gap.

**Also worth flagging:** `ACAC0202.DBF` carries `APA_CPFPCN` — an eleven-digit patient CPF — and
`APA_CPFRES`, `APA_CPFDIR` alongside `APA_NOMERE` and `APA_NOMEDI` (names). These are direct
personal identifiers in a public, unauthenticated download. The profiler classifies them as
`personal_identifier_cpf` and the ledger raises an open question against every such column.
