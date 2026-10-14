# What a methods section can cite: files read, the denominator, what a row is (2026-10-14)

Regime: branch `fix6-provenance` (from 0325b7c), read-only on `pegasus_core_data` (catalog `mode=ro`, lake parquet columns) and on
`pegasus_data_home` (POPSVS lake); `info()` on a copy of the catalog. One probe ran `info("SIH.RD")` on the real root and, as
`info` does, wrote its curated text (`curation_state` 16:30:46 UTC, head's curation): the cause of ADR-0181's "not decided".
Decision: ADR-0181.

| what | measured |
|---|---|
| `publications("SIH.RD", 2014..2023)`, every UF | 7.4 s; 3,240 files held (27 UFs x 12 x 10), 119,005,606 rows decoded = the sum of `lake_partitions.row_count` (270 partitions); 1,375 listed and not held (972 `.dbc` in `MHJ_14_16`, 268 `.xml`, 135 `.dbf`), each the same publication (`logical_id`) as a held file; status `undeclared` for all (SIH-RD declares no `final_after_years`) |
| Alagoas SIH-RD | 12 monthly files a year, 2014-2023; 1,692,728 rows |
| `publications("SIM.DO", 2014..2023)` | 0.3 s; 10 national files held (DOBR), 14,179,520 rows = the partitions' sum; 270 per-UF files listed and not held ("the same records are in the national file"); all `final` (PRELIM tree not in the span; year + 1 < the fetch year) |
| where the bytes came from | every held blob (3,250) was served by the public mirror (`mirror:https://datasus-ftp-mirror...`), none by ftp.datasus.gov.br; none changed on the server since its fetch |
| SIM-DO year | DTOBITO in the file's year for 14,179,520 of 14,179,520 rows, DOBR2014-DOBR2023 |
| SIH-RD dates, Alagoas 2014-2023 | ANO_CMPT = file year 100%; discharge in the competence month 64.8%, earlier 35.2%, later 0; admission in it 53.2%, earlier 46.8% |
| SIH-RD AIH types, Alagoas 2014 | IDENT 1: 157,005; IDENT 5: 8,429; the curation counts type 1 (TabNet = 52,733 type-1 rows in AC 2014; RIPSA F.3 excludes type 5) |
| `info("SIH.RD").documentation` | had no `what_one_row_is` (key `SIHSUS_RD` against `SIH`); now has it and 7 gotchas |
| POPSVS, Alagoas / Brazil | 3,217,819 -> 3,218,381 -> 3,218,607 (+0.017%, +0.007%); 210,103,642 -> 210,862,983 -> 211,695,158 (+0.361%, +0.395%); Alagoas +1.25% 2001, +0.43% 2010, +0.09% 2021 |
| Alagoas natural increase (SINASC-DN births less SIM-DO deaths, residents) | 23,718 (2021), 22,620 (2022), 24,578 (2023): about 23,200 and 23,600 per 1 July interval, so net migration of about -22,600 and -23,400 (-0.70%, -0.73%); Brazil -171,700 and -212,600 (-0.08%, -0.10%) |

**What POPSVS is**, from the Ministry's note (`/IBGE/doc/NT-POPULACAO-RESIDENTE-2000-2024.pdf`) and IBGE's notes 01/2024: DATA_SOURCES §6.1,
`curation/populations.yml`. The note covers 2000-2024; POPSBR25 (listed 2025-10-29) is described by no document found.

**The brief's "IDENT 1, 5 counted"**: the curation counts type 1 only; the files hold 1 and 5. Stated so in SIH-RD's gotchas.
