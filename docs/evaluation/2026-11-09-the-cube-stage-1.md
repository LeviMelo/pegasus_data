# The cube, stage 1: SIDRA tables and series as cubes (2026-11-09)

**What was measured.** Whether the 26 context fields built from SIDRA (5 table slices, 21 stitched series) come out of
`cube()` exactly as they were stored, and whether an undeclared table is served. Real home `pegasus_core_data`, master
after bd867e4, ADR-0217. Scripts: the session's `cmp_sidra.py`, which compares stored fields with `cube()` by
(municipality, year) → (value, status), and `cmp_views.py`, which compares stored copies with `load_field` on all seven
columns and their types.

| check | result |
|---|---|
| 26 fields against `cube()` | 26 equal, 0 differences (about 640,000 rows: gdp 122,540; households 16,642; population by race 16,705…) |
| 26 stored copies against `load_field` served from the cube | 26 equal on all columns and types |
| GDP 2021 rolled up from municipalities to states | 27 rows, Brazil 9,012,142,031: the field's verified total |
| undeclared tables | 2683/343 (deaths by civil status, 122,540 rows, 95 `not_available`) and 10381/696 (5,570 rows) served; their state roll-ups too |
| a table with no municipal facts held | raises with the fetch command, never an empty table |
| a stitched series read | 8.2-8.6 s built, 0.66-0.70 s from the cube cache |

The 26 copies under `lake/fields/` were removed after the second check.
