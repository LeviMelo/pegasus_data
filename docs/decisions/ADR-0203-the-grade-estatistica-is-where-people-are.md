# ADR-0203: IBGE's Grade Estatística 2022 is where people are, and every population weight is read from it

2026-10-24. Status: active. Replaces the tract-derived 5 km grid of `proximity.build_proximity_graphs` and the tract points
of `geography.build_municipality_points`.

## Context

Three mechanisms needed the location of a municipality's people and each built its own from the Census 2022 tracts: the
population distance graph (tracts' representative points binned to an internal 5 km grid, not exposed), the population
centre of the points pack (the weighted median of tract points), and nothing for climate (BR-DWGD's municipal means are
area-weighted). A tract point stands for all its households, however large the tract: a rural tract of hundreds of km²
is one point. Consumers (nees-gt-ms, the dengue spatio-temporal model) asked for population-weighted exposure and a
sub-municipal support.

IBGE publishes that support: the Grade Estatística 2022 (Notas metodológicas 01/2025), 14,127,809 equal-area cells of
200 m (urban) and 1 km (rural) holding the residents and occupied households of the 2022 universe, placed by each
household's CNEFE coordinate (levels 1-4; 56,229 people at levels 5-6 left out).

## Decision

1. **Served as a reference layer** (`sources/ibge_grade.py`; `pegasus-data grade` builds, `grade_cells()` /
   `pegasus-data grade-cells` reads): `registries/ibge_grade/cells_2022.parquet`, one row per cell and municipality, with
   the cell's whole counts (`total`, `total_dom`) and the municipality's `share` of the cell. A read multiplies by the
   share and sums into IBGE's own coarser cells (1 to 500 km, named as IBGE names them); counts are only summed.
2. **The municipality is the mesh's.** A cell takes the municipalities of IBGE's maximum-quality mesh it meets; a cell on
   a border is shared by the part of 8 × 8 points over it inside each polygon (exact areas for a sliver no point lands
   in); a cell outside every polygon with people in it goes to the nearest municipality, marked `placed = nearest`.
3. **One weight for everything that weighs by people:** the points pack's population centre is the weighted median of
   the grade's cells, the population distance graph uses the grade's 5 km cells at the population-weighted centre of their
   native cells (great-circle distances), and the climate products weigh grid cells by the grade (ADR-0204). The area
   weight of the climate products is the grade's too (cell area × share), so both weights come from one table.
4. **The grade places people; the census counts them.** A municipality's sum over the grade is where its residents'
   coordinates fall, not the census count of its tracts; a count per municipality is still read from the census.
5. **The tracts are served as IBGE publishes them** (`sources/ibge_tracts.py`; `pegasus-data tracts`,
   `census_tracts()`, `tract_population()`, `tract_mesh()`): identity and basic counts, and residents by sex in eleven
   age bands, a suppressed count (`X`) null and flagged, never filled. The grade has no sex or age; the tract is the
   finest support that has them, and the one a CEP's addresses fall in (CNEFE's `COD_SETOR`).

## Evidence

Evaluation 2026-10-24-grade-estatistica:

* the build reproduces the note: 14,127,809 cells (5,486,725 of 200 m), 203,002,064 people and 72,546,543 households;
  every identifier agrees with its geometry (the 200 m name carries the north edge); shares sum to 1 per cell (error 3e-8);
* 588,147 cells are shared between municipalities (159,712 of them peopled, holding 4.7 million people); 39 peopled cells
  (285 people) lie outside the mesh, at most 1.25 km from it;
* against the census tracts the grade's municipal sums differ by more than 1% in 1,024 municipalities and by more than
  5% in 56 (from −16% to +19%), hence clause 4;
* rebuilt packs: contiguity and areas identical; population points moved a median 0.16 km (p99 3.1 km, max 8.8 km) and lie
  nearer the seats (median 0.61 → 0.56 km, p90 2.87 → 2.58 km); population distances change a median −0.3% (p99 2.6 km);
  REGIC's links, which the old build dropped from the pack it rewrote, are kept.

* tracts: 468,099, 458,772 with demography; the published sex-band cells hold 201,752,886 of the 203,080,756 residents
  (suppression: 721,091 cells, 7.1%; 102 municipalities short by more than 5%); IBGE's municipal file of the theme is the
  sum of the same cells, equal cell by cell.

## Consequences

* Building the packs needs the grade in the data home (711 MB of zips, 38 MB of cells, 13 minutes); the tract file is no
  longer read by the build.
* `population_2022` of the points pack is now `population_grade_2022` (the grade's people placed in the municipality).
* `municipality_point` warns (`NoPointWarning`) with the reason when a municipality has no point of a kind.
