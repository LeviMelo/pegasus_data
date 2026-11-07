# CNES specialist fields 2010-2023: the 2231-era codes, nested groups, the slit-lamp code (2026-11-07)

**Regime.** Branch `pegasus-core-fixes`, the shared home `C:\Users\Galaxy\pegasus_core_data`, run on 2026-11-07. The build
was `fields.build_fields` for the new `cnes_*` fields of ADR-0215, then every PF field, for 2010-2023.

**Footprint.** The catalog (`files`) puts PF's December files for 2010-2023 at 2.67 GB; the largest state file is 68 MB
(SP 2023). Each file is deleted once aggregated. The `jobs`/`people` tables kept beside the aggregates take 8.7 MB for
SP 2023 and about 30 MB a year nationally. Free disk stayed at 57 GB, and the fetch took 36-96 s a year.

**What a first build got wrong, and why.**

| year | ophthalmologists (225265 only) | with 223144 |
|---|---|---|
| 2010 | 0 | 14,455 |
| 2011 | | 14,621 |
| 2015 | 19,784 | 19,784 |
| 2023 | 30,375 | 30,375 |

- **2231-era codes.** December 2010 has no 2252xx code. The conversion, measured as the same CNS in the same municipality
  in 2010 and 2011, is 223144 → 225265 (84% of the 2011 holders), 223136 → 225103 (55%) and 223149 → 225124 (66%).
  December 2011 still holds 14,710 rows of 2231 codes.
- **Groups were exclusive.** A code took the last group listed, so physicians in 2023 fell from 805,369 to 722,293. With
  nested groups they are 805,369 again.
- **The slit-lamp code (EQ 349) is absent until December 2013.** Type 3 holds only 31-36 in 2010-2012. Registered slit
  lamps then rise from 562 (2013) to 9,930 (2023) in all sectors, against about 20,000 ophthalmologists: registration,
  not supply.
- **Neonatal ICU beds (SUS):** 3,637 in 2010 and 4,895 in 2020.
