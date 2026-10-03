# Municipality points: seat and population centre instead of polygon centroids

**Date:** 2026-10-03.

**Regime:** `geography.build_municipality_points`, run by `pegasus-data
geography`. Artifact `data/probes/geography/municipality_points.csv`; the
shipped pack is `resources/municipality_points.parquet` (457 KB).

**Sources** (IBGE):
- Localidades 2022, for the seats: "Sede Municipal" plus the 27 capitals,
  categorised "Capital Estadual" and "Capital Federal";
- Census 2022 tracts with their population (`v0001`, 1.5 GB);
- the full-resolution municipal mesh.

**Why.** No code here used polygon centroids yet. A representative point is
needed for maps, residence-to-care distances and station proximity. The
polygon centroid lies a median 5.6 km from the seat:
- more than 10 km for 1,521 municipalities, more than 50 km for 161, more
  than 100 km for 50 (Altamira: 407 km);
- outside the municipality itself for 55.

**The population centre** is the population-weighted median, coordinate by
coordinate, of the tracts' points.
- **A weighted mean was tried first and rejected:** Castelo de Sonhos,
  about 900 km south, pulled Altamira's 94 km into the forest. The median
  puts it 0.9 km from the seat.
- **Duplicated tracts fixed.** The tract file repeats a multi-part tract
  once per piece (5,595 rows over 468,099 tracts), so its sum ran to
  204,029,638. Merged per tract, the total is 203,080,756, the census
  figure exactly.

**Result:** 5,570 municipalities with a seat and a population centre. Seat
to population centre: median 0.6 km, 90th percentile 2.9 km, 99th 14.9 km.

**IBGE's seat points have errors.**
- 30 seats lie more than 20 km from their population centre, 4 more than
  50 km.
- Porto Velho's seat (-9.646, -63.960) is about 100 km south of the city.
  The population centre, (-8.769, -63.870), is in the city, which holds 93%
  of the residents.
- Manicoré's seat is about 237 km from the town.
- Some of the 30 are genuine spread, for example Amontada's coastal
  districts.

**Decision.**
- **The population centre is the default point**
  (`municipality_point(code)`, `distance_km(a, b)`).
- The seat and the centroid stay in the pack, for comparison.
