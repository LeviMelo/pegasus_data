# The Grade Estatística 2022 as the population support (2026-10-24)

**Check.** `pegasus-data grade` (`sources/ibge_grade.build`) on IBGE's 56 quadrant zips, then the points pack and the
proximity graphs rebuilt from it (`build_municipality_points`, `build_proximity_graphs`) and compared with the shipped,
tract-based packs. What was counted and why: the grade's totals against the ones IBGE publishes for it (a wrong reading of
a cell, a quadrant read twice or a lost one would show); each cell identifier against its geometry (the coarse-cell names
are built from the corner); the shares of each cell; what the municipal assignment does to municipal sums against the
census tracts (the independent count of the same people); how far the rebuilt products move.

**Regime.** Branch `claude/nees-gaps-dc2b18`, 6091c06 (the build's code), `pegasus_core_data`, 2026-10-24; scripts in the
session scratchpad (`build_grade.py`, `packs_build.py`), artifact `registries/ibge_grade/cells_2022.parquet` (38 MB).
779 s for the build with other sessions' jobs on the CPU (a first version that tested each box against the full-resolution
polygons took 3.5 times as long and was stopped).

| | grade build | IBGE's note |
|---|---|---|
| cells | 14,127,809 | 14,127,809 |
| 200 m cells | 5,486,725 | 5,486,725 |
| people | 203,002,064 | 203,002,064 (levels 1-4) |
| occupied households | 72,546,543 | 72,546,543 |
| identifiers disagreeing with geometry | 0 (and 0 of the `nome_5KM` names) | — |

* **Peopled cells** 2,993,047; 200 m cells hold 180.0 million people in 1,666,604 peopled cells.
* **Borders.** 588,147 cells are shared between municipalities (159,712 peopled, 4,713,546 people); per-cell shares sum to
  1 within 3e-8. 418,177 cells meet no polygon; 39 of them hold people (285), placed in the nearest municipality, at most
  1,247 m away. Every one of the 5,570 municipalities of the mesh has people.
* **Against the census tracts** (`registries/ibge_points/tracts.gpkg`, `v0001` by `CD_MUN`): the grade's municipal sum
  over the census count has a median of 0.9998, but differs by more than 1% in 1,024 municipalities and by more than 5% in 56
  (0.838, 3521606, to 1.187, 2806909). The grade places a household where its coordinate falls; the census counts it in its
  tract's municipality. The grade is the support for where people are, not a municipal count.
* **Points pack** (5,571 rows): population centres moved a median 0.16 km (p90 0.52, p99 3.10, max 8.8 km, 1400050 in
  Roraima, whose tract point stood 9.2 km from the seat and whose grade point stands 0.8 km from it); 17 moved more than
  5 km; the distance from seat to population centre fell (median 0.61 → 0.56 km, p90 2.87 → 2.58 km). Still without a
  point, now with a warning: 5101837 (no polygon in the 2022 mesh) and 2605459's seat.
* **Proximity pack.** Contiguity (33,006 edges) and areas identical; population distance 167,421 edges (from 167,419),
  on the 166,462 pairs in both a median change of −0.30% (p5 −2.9%, p95 +0.8%), absolute median 0.25 km, p99 2.64 km. The
  three REGIC graphs are kept: the old build rewrote the pack without them (they were restored only by running
  `build_regic` after it).

**Tracts by sex and age** (`pegasus-data tracts`, `sources/ibge_tracts.build`, 21 s; `registries/ibge_tracts/`). IBGE's
*Agregados por Setores* demography file has residents by sex in eleven bands for 458,772 of the 468,099 tracts (the rest
have no residents). Counted: the published cells against two totals. IBGE's municipal file of the same theme equals the sum
of the tracts' published cells in every municipality-sex-band cell (201,752,886 people): it is built from them and is no
independent total. The basic file's tract residents (`v0001`, never suppressed) sum to 203,080,756, so suppression (`X`:
721,091 cells, 7.1%) leaves 1,327,870 people (0.65%) out of the sex-band cells; 5,472 municipalities fall short, 102 by more
than 5%, the worst by 65%. A small-area rate by sex and age on tract denominators carries that shortfall; it is reported per
municipality, not spread. Maceió: 1,620 tracts, 957,916 residents, 953,460 in published bands (1,539 cells suppressed).
