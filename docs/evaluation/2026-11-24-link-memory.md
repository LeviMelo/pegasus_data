# A national link year needs about 3 GB, not 6-7, with DuckDB held to 2 GB (2026-11-24)

Regime: pegasus_data before and after this commit; home `C:\Users\Galaxy\pegasus_core_data`; `linked_deaths("SIH-RD",
["0403010314"], years=2019, geography="BR", match="procedure", link_name="sih_admissions_to_sim")`, refresh.

- **What was measured:** the process's peak resident memory, sampled every 0.1 s, by phase. Reported by t10: 5-7 GB
  per year for a 45,000-person cohort, killed at a 7 GB limit.
- **Before** (memory_limit at 40% of RAM, 12.8 GB): peak 6.17 GB for a 5,025-person cohort, so the cost does not scale
  with the cohort. Reads: SIH-RD 5,343 rows, 1 MB; SIM-DO 2018-2020, 4,223,344 rows, 0.86 GB as Arrow, 2.0 GB resident.
  The jump to 6.2 GB came in the pairing, inside DuckDB.
- **After** (`link_memory_gb` 2.0 by default, `PEGASUS_LINK_MEMORY_GB` overrides): peak 3.26 GB, 47 s against 37-50 s.
  Result unchanged: cohort 5,025, linked 694, chance 13.54%, "use with caution".
- What remains above 2 GB is the right side held in Python as Arrow (about 0.9 GB) and its copies.
