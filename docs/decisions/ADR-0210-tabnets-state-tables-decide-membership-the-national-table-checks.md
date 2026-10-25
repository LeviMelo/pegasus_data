# ADR-0210: TabNet's state territorial tables decide membership, and the national table checks them

2026-10-25. Status: active. Amends ADR-0126 (health classifications from TabNet's current tables).

## Context

`health_macroregion` and `health_region_current` were read from TabNet's national tables, `territorio/br_macsaud.cnv`
and `br_regsaud.cnv`. TabNet's own state forms classify by the state's table instead (`sih/cnv/nrro.def`:
`LMacrorregião de Saúde,MUNIC_RES,1 , territorio\RO_macsaud.cnv`). nees-gt-ms found Alta Floresta D'Oeste (110001)
absent from `br_macsaud.cnv`, which leaves it in the "Ignorado - RO" range, while `RO_macsaud.cnv` puts it in 1101.
SIH diabetes admissions of 2024 by residence in macroregion 1101 were then 26 short of TabNet's.

## Decision

1. **The 27 state tables (`{uf}_macsaud`, `{uf}_regsaud`, declared as `state_table` in `curation/geography.yml`) decide
   membership**, since they are what TabNet's state tabulations use. The national table is read too, as the check.
2. **A disagreement is recorded, never resolved silently.** The build reports each municipality the state tables add
   (`added_by_state_tables`) and each one where state and national tables name different members
   (`state_and_national_differ`, with both codes).
3. **Labels come from the national table** for every member it names. The state tables' labels are not decoded as the
   national one's ("CafÚ" for Café in `RO_regsaud.cnv`), so they serve membership only.

## Evidence

Evaluation 2026-10-25-tabnet-state-tables: the state tables agree with the national ones on every municipality both
list (0 differing) and add one each: 110001 to macroregion 1101 and 110002 Ariquemes to region 11001 (Vale do Jamari).
The rebuilt pack differs from the shipped one by those two rows and by 6,173 CIH rows whose window ends 2011-04 (ADR-0198,
not rebuilt into the pack before). SIH-RD RO 2024, E10-E14 (IDENT 1) in 1101: 1,169, 26 of them Alta Floresta's.
