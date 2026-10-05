## 2026-10-05: census series across 2000, 2010 and 2022, and the census context fields (ADR-0142 amendment)

**Scenario.** `pegasus-data sidra series <name> --fetch --report`, then `pegasus-data fields` for the fields declared with
`series:`; read back through PegaSUS's `gateway.context_field` unchanged. **Artifact.** the series in
`curation/sidra/series.yml`, the fields in `lake/fields/`. **Regime.** Data home `C:/Users/Galaxy/pegasus_core_data`,
branch `pegasus-core-fixes`, 2026-10-05, live IBGE server.

| check | counted | result |
|---|---|---|
| fields that already existed (2010, 2022) rebuilt from the series | `households`, `households_waste_collected`, `households_without_bathroom`, `persons_15_plus(_literate)`, five `population_<race>` | 0 of 5,570 municipalities differ in every year they had |
| national share, 2000 / 2010 / 2022 | sewer network (strict) 47.2 / 55.5 / 60.4; water network 77.8 / 82.9 / 83.9; waste collected 79.0 / 87.4 / 91.7; no bathroom 8.3 / 2.6 / 0.5 | agree with IBGE's published national figures |
| literacy | 15+: 87.1 / 90.4 / 93.0; 10+: 87.9 / 91.0 / none | 2000 15+ is computed (15-19 plus 20+ groups); 2022 publishes no 10+ |
| urban population | 81.3 / 84.4 / 87.4 | IBGE's urban situation at each census (the perimeter moves) |
| race, share of the table's Total | white 53.7 / 47.7 / 43.5; brown 38.5 / 43.1 / 45.3; black 6.2 / 7.6 / 10.2; indigenous 0.43 / 0.43 / 0.60 | 2000 is the sample; 2010 and 2022 the universe |
| persons at up to 1/2 minimum wage per capita, or none | 33.6 / 34.7 / 31.8 | shares inside each census year, never deflated |
| 2010 literacy 10+, preliminary universe (table 3149) against the final table 1699 | 345 of 11,130 cells differ, 7,582 persons of 162 M | the preliminary table stands in for 15+ in 2010 |
| households of the sanitation tables | 2000 and 2022 equal across tables; 2010 differs by 18 households (3154 vs 3218) | one `households` denominator is safe |

Reading: shares agree with the published ones, so the stitching is right where it was checked against an
independent figure; what it cannot check is the comparability of the concepts, which each series therefore states
(`comparability` strict / close, and `gaps`; `sidra series NAME --report` prints them with the places that have a
figure). Comparability that is only close: water (form of supply in 2000-2010, main supply in 2022), urban (the
perimeter), literacy 2010 (preliminary universe), race 2000 (sample, counts "Sem declaração"), income (the family's
per-capita income in 2000, the household's in 2010 and 2022; minimum wages of the year). Gaps: municipalities created
after a census have no figure in it (2000: 5,507 to 5,565 municipalities by table; 58 `...`); 10+ literacy has no 2022;
income in reais is not offered (it needs a deflator and is a mean).

A defect found and fixed on the way: `build_series` joined the arbitration key on null axis columns, so the
denominator rows of a series that mixed sources with and without axes were never `selected`.

The chains `phaseb.sh`/`phasec.sh`/`phased.sh` were still running at 06:11 (income_labour, table 10295); table 10062
is re-queued by `phased.sh` after them.
