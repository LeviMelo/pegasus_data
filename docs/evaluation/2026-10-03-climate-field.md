# Climate field from INMET stations (station-month, placed by location)

**Date:** 2026-10-03.

**Regime:** `pegasus-data fields --name climate --root pegasus_data_home`.

**Correction to the first version of this entry.** It said INMET's portal
and API were unreachable. They are reachable: INMET's firewall resets any
request without a browser user agent, which a single curl attempt read as an
outage. `sources/inmet.py` now sends one.

**Readings.** From the CC-BY-4.0 Zenodo mirror of INMET (record 14925215).
Checked against INMET's own 2022 archive for Brasília A001: 1,356.4 mm over
8,759 readings and a 21.247 °C mean over 8,760, identical in both.

**Positions,** first source that has the station:

| source | stations |
|---|---|
| INMET station API | 652 |
| mirror catalog | 64 |
| NOAA ISD history (conventional stations closed before both) | 197 |

**Placement.** A geopandas spatial join over IBGE's full-resolution mesh. A
coastal station within 2 km of the mesh takes the nearest municipality.
- 912 of 913 stations are placed; Abrolhos, 70 km offshore, is not.
- **Against INMET's own registration** (the IBGE code inside each WIGOS
  identifier), placement agrees for 610 of 652.
- **The 42 that differ** were tested against two explanations.
  - Mesh simplification: rejected. The intermediate mesh gave 44
    disagreements, the full one 42.
  - What remains is about half stations on a border (under 1 km away) and
    half registry errors: Lençóis A425 is registered 307 km away, Novo
    Horizonte 159 km.
- **Rows carry `inmet_municipality7`, `coordinates_from` and `placed_by`.**
  NOAA's older coordinates are the weakest: names agree for 152 of 196.

**Result.** 275,810 station-months, 1961–2025, from 912 stations. 44,537
are unplaced: their station has no position in any source.

**Checks against known climate:**
- Brasília 2022: no rain June–August, 428 mm in November;
- Manaus 2022: mean 27.6 °C, 2,448 mm;
- Brasília 1961–1990: 20.6 °C, 1,487 mm a year.
