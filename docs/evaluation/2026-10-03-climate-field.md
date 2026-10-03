# Climate field from INMET stations (station-month, placed by location)

**Date:** 2026-10-03.

**Regime:** `pegasus-data fields --name climate --root pegasus_data_home`,
reading the CC-BY-4.0 Zenodo mirror of INMET (record 14925215). INMET's own
portal and API were unreachable.

**Placement.** A geopandas spatial join against IBGE's municipal mesh. A
station within 2 km of the mesh's coastline takes the nearest municipality.
- **Positions from the mirror's catalog:**
  - 696 within a municipality, 2 by the coastal rule, 1 unplaced
    (Abrolhos, 70 km offshore);
  - every placed station agrees with its catalog state;
  - names agree for 640; the rest are stations named after a neighbouring
    city (the "Florianópolis" station is in São José).
- **Conventional stations closed before 2025** are positioned from NOAA's
  ISD station history (WMO number). 196 are placed this way, and names
  agree for 152. Some old NOAA coordinates are off: Pari-Cachoeira lands in
  Japurá. Every row carries `coordinates_from` and `placed_by`.

**Result:**
- 274,813 station-months, 1961–2025, from 894 stations;
- 45,534 station-months unplaced: their station is in neither source.

**Checks against known climate:**
- **Brasília A001, 2022:** no rain June–August, 428 mm in November,
  monthly means 19–24 °C.
- **Manaus A101, 2022:** mean 27.6 °C, 2,448 mm.
- **Brasília conventional 83377, 1961–1990:** mean 20.6 °C, 1,487 mm a
  year, near the published normals.
