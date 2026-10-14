# ADR-0178: the climate fields are read from BR-DWGD's municipal series, not from stations

**Date:** 2026-10-14. **Status:** accepted. Refines ADR-0177 (same fields, same form; the source changes).

**Context.** ADR-0177 read the six climate fields from INMET's stations. A station gives the climate of its own site: in any
year at most 397 of the 5,570 municipalities (7%) had a station with 11 complete months of temperature (2010; 341 in 2023),
674 ever; Alagoas has 102 municipalities and 1 to 4 of them a usable station-year in each of 2020-2024; the gauge of Maceió's A303 reported nothing from
February to July 2021 while its thermometer worked. A municipal exposure needs a gridded, quality-controlled product that
covers every municipality and every month, built by someone who keeps building it.

**Decision.**
- **The source is BR-DWGD** (Xavier et al. 2022: every Brazilian rain gauge and station interpolated to a daily 0.1° grid
  from 1961) **through its municipal zonal means**, which Saldanha et al. (the R package `brclimr`) compute and publish on
  Zenodo (concept record 7824919): `sources/brdwgd.py` reads the latest version of that record (today v3.2.3, 2024-10-09,
  1961-01-01 to 2024-03-20, IBGE's 2010 mesh). No grid is downloaded and none interpolated here. The mean is area-weighted
  (against a recomputation from the grid, the median absolute difference is 0.001 °C; the unweighted mean of the touching cells differs by 0.06 °C).
- **The fields keep their names, their `over` denominators and `family: gaussian`** (ADR-0177's form: sums of coverage-weighted
  months, precipitation as a mean month). A month's coverage is the days held over its length, so 2024 (Jan, Feb, 20 days of
  March) has 2.645 months and is `partial_year`; every earlier year has 12 and is `ok`. `source` names the release of the row.
  A new base `climate_monthly` holds the municipality-month sums and day counts the fields are read from.
- **Two definitions change, and are stated in the fields:** `air_temperature` is the mid-range of the mean daily maximum and
  minimum (BR-DWGD has no 24-hour mean; it reads 0.7 °C above INMET's, median of 257,920 station-months), and
  `air_temperature_monthly_max/min` are the means of the daily extremes, no longer the month's single hottest and coldest
  reading.
- **INMET's stations stay as observations** (`climate`, `inmet.station_months`), the reference the fields are validated
  against (`scripts/climate_validation.py`; EVALUATION 2026-10-14 "Climate from BR-DWGD").
- **Not covered, said and not filled:** Fernando de Noronha and Bombinhas (no grid cell: no value on any of the 23,090 days),
  the six municipalities created after 2010 (no series), and the days after 2024-03-20. No municipality is interpolated from a
  neighbour. A reproduction: against 229,107 complete station-months of 909 stations, the mid-range has bias -0.07 °C and
  RMSE 0.75 °C, precipitation bias -2 mm and RMSE 46 mm a month (stations are inputs of BR-DWGD: not independent).

**Alternatives.**
- Zonal means computed here from grids (BR-DWGD v3.2.4, TerraClimate, CHIRPS): measured, and set aside by the author: someone
  already does that job and keeps doing it. v3.2.4 (1961 to 2025-12-31, Google Drive, 355 MB) has no municipal release yet.
- `brclimr` 0.2.0's own files (DigitalOcean, fast): v1.0.0, every variable ends 2020-07-31, older grid.
- ERA5-Land municipal means (the same authors, yearly records to 2025): the fill for the gap, not the source (it has a 24-hour
  mean but its precipitation is 19 mm a month low against INMET in 2023); ERA5/CDS itself needs an account.

**Consequences.** The coordinator rebuilds `climate_monthly` and the six fields (RUNBOOK; about 30 minutes the first time,
Zenodo serves 80 KB/s a connection). A study naming `climate` names `air_temperature` and `precipitation_mm`. Trends: the
bias of Tmax against INMET drifts from -0.1 °C (1960s) to +0.5 °C (2020s) as the stations that inform the grid change.
**Would overturn it:** Saldanha et al. stop publishing (read the grid, then), or a municipal release of a newer BR-DWGD
version that moves the past (v3.2.4 moves monthly Tmin of 1970-1999 by an RMS of 0.5 °C or more in 207 municipalities, and
precipitation by 12 to 22 mm a month in 2010-2024), which the build would read at once and the fields would carry in `source`.
