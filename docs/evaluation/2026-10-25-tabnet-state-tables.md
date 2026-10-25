# TabNet's state territorial tables against the national ones (2026-10-25)

**Check.** `geography._tabnet_rows` (ADR-0210) reading TabNet's 27 `territorio/{UF}_macsaud.cnv` and `{UF}_regsaud.cnv`
beside the national `br_macsaud.cnv` and `br_regsaud.cnv`; the geography pack rebuilt into scratch and compared row by
row with the shipped one before replacing it. Branch `macsaud` from a7dd7d0, `pegasus_core_data` (TabNet cache),
2026-10-25. What was counted and why: municipalities the state tables place that the national ones do not, or place
elsewhere (the state tables are what TabNet's state tabulations use, so a difference is a count that will not
reconcile); every other change the rebuild brings (a pack rebuilt for one reason must not move anything silently).

| classification | municipalities | members | added by state tables | state ≠ national |
|---|---|---|---|---|
| `health_macroregion` | 5,607 (was 5,606) | 124 | 110001 Alta Floresta D'Oeste → 1101 MACRORREGIONAL II (CACOAL) | 0 |
| `health_region_current` | 5,607 (was 5,606) | 446 | 110002 Ariquemes → 11001 Vale do Jamari | 0 |

* The national tables leave both in the state's "Ignorado" range; nees-gt-ms had found the same single difference for the
  macroregion by comparing the 27 state files with the national one municipality by municipality.
* The state tables' labels read mis-decoded ("CafÚ" for Café, `RO_regsaud.cnv`); a first rebuild that took them replaced
  the national labels of 52 regions and was discarded. Labels now come from the national table.
* Every other difference of the rebuilt pack: 6,173 rows of the CIH system whose window ends 201104 instead of 201012,
  ADR-0198's widening of CIH's kit window, which the shipped pack had not been rebuilt with.

**Use.** SIH-RD RO 2024, principal diagnosis E10-E14 (IDENT 1), by residence macroregion: 1101 1,169, 26 of them Alta
Floresta's (before: 1,143 and the 26 unclassified). TabNet's `nrro.def` gives 1,170 for 1101; the remaining
admission is not explained by this change and was not traced.
