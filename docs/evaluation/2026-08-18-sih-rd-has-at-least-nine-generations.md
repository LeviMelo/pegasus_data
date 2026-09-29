## 2026-08-18 — SIH-RD has at least nine schema generations, not three

*Split from docs/history/FINDINGS.md §2 on 2026-09-28; text unchanged.*

### SIH-RD has at least nine schema generations, not three

The brief's regression target: *"SIH-RD resolves to three generations — 35 columns (1992), 86
columns (2008–2014, has `DIAG_SECUN`), 113 columns (2017+, has `DIAGSEC1..9` and no
`DIAG_SECUN`)."*

Measured across January files for Acre, decoded and hashed by ordered field list:

| file | columns | schema signature |
|---|---|---|
| `RDAC9201.dbc` | 35 | `25acd6ef` |
| `RDAC9801.dbc` | 41 | `d572a887` |
| `RDAC0001.dbc` | 60 | `b94037e0` |
| `RDAC0501.dbc` | 69 | `32f7b80f` |
| `RDAC0701.dbc` | 75 | `3b553258` |
| `RDAC0801.dbc`, `RDAC0901.dbc` | 86 | `bc6a3d49` |
| `RDAC1101.dbc`, `RDAC1201.dbc` | 93 | `8066395a` |
| `RDAC1401` … `RDAC2401` | 113 | `e2f7244a` |
| `RDAC2601.dbc` | 114 | `d7f8d30a` |

The brief's three generations are real and present; they are simply a subset of what exists. Its
compendium held two sampled files for the family, so the intermediate generations could not be
seen — which is precisely defect D2, showing up in the brief's own numbers.

Note also that the 113-column schema appears from **2014**, not 2017.
