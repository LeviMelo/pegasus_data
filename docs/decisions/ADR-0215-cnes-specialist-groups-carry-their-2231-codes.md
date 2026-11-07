# ADR-0215: CNES specialist groups carry their 2231-era codes, a field starts when its code exists, and a PF aggregate without a digest is rebuilt

2026-11-07. Status: active. Extends ADR-0150 (CNES supply fields); applies ADR-0104's observed conversion.

## Context

The toxoplasmosis study (toxoplasmose_brasil, P5) needed eye and infant specialist supply by municipality: ophthalmologists,
infectious-disease physicians, paediatricians, neonatal ICU beds and slit lamps. ADR-0150's groups held only physicians,
nurses and community health agents. A first build of the new groups for 2010-2023 showed three silent-zero hazards:

- **Stale aggregates.** A PF aggregate written before the curation digest existed was served as it was. A group added to
  the curation would have read zero everywhere.
- **Codes before 2011.** December 2010 holds no 2252xx code: every physician is under the original CBO 2002 codes 2231xx,
  which the label pack does not name. 225265 alone gave 0 ophthalmologists in 2010 and 19,784 in 2015.
- **Equipment before its code.** The ophthalmic equipment codes (337-350) are absent until December 2013. In 2010-2012 type
  3 holds only 31-36.

## Decision

1. **PF aggregates without a digest are rebuilt** (`sources.cnes.state_table`). The other datasets keep ADR-0150's rule,
   since their aggregates are summed without groups.
   - **Groups nest.** A code belongs to every group whose prefixes it matches (`_pf_groups` selects each group on its own).
   - **The fix.** ADR-0150 gave a code one group, the last one listed, so adding ophthalmologists would have removed them
     from physicians. A first build did exactly that: physicians in 2023 fell from 805,369 to 722,293.
   - **Verified.** After the fix physicians are 805,369 again. The digest carries the grouping rule, so aggregates built
     under the old rule are rebuilt.
2. **Each specialist group lists its CBO 2002 code and its 2231-era code**, measured as ADR-0104 measured CBO 94. The
   measure is the same CNS in the same municipality in December 2010 and December 2011 (`registries/CNES/agg/*.people.parquet`).
   Of the 2011 holders of each new code, the share that held the old code in 2010:

   | group | codes | share |
   |---|---|---|
   | ophthalmologists | 225265 ← 223144 | 84% |
   | infectologists | 225103 ← 223136 | 55% |
   | paediatricians | 225124 ← 223149 | 66% |

   Most of the rest held 223115, the generalist code. SIA-PA's ocular toxoplasmosis records bill both 225265 and 223144.
3. **New fields.**
   - `cnes_{ophthalmologists,infectologists,paediatricians}_{professionals,weekly_hours_sus}`, 2010-2023.
   - `cnes_beds_neonatal_icu_sus`: `neonatal_icu_bed_codes` 63, 80-82.
   - `cnes_equipment_slit_lamp_sus`: EQ 349, from 2013, when the code first appears.
4. **The slit-lamp field compares places that register equipment, not capacity.** Registered slit lamps grow from 562
   (2013) to 9,930 (2023) in all sectors, against about 20,000 ophthalmologists. That growth is registration, so the field
   is not a time series of supply.

## Evidence

Built 2026-11-07 into the shared home: PF December files 2010-2023, 2.67 GB fetched and deleted state by state. The
`jobs`/`people` tables kept beside the aggregates add about 30 MB a year. Free disk stayed at 57 GB.

## Consequences

A later change of PF groups re-groups from the kept tables without a download.
