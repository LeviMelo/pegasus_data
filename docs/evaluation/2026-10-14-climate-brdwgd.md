# Climate from BR-DWGD's municipal series: coverage, variables, reproduction of INMET, gaps

**Date:** 2026-10-14. **Regime:** branch `fix3-climate`; Zenodo record 13906834 (BR-DWGD v3.2.3) read live on 2026-10-14; INMET's
station-months from the real root read-only (`registries/inmet` Zenodo mirror 14925215, placement in `lake/fields/climate`);
fields built under a scratch root (17.7 s from the cached monthly sums). Script `scripts/climate_validation.py --root <root>`,
artifact `data/probes/climate_validation.json`. Decision: ADR-0178 (supersedes the station source of ADR-0177).

## (a) What the municipal series cover
- **Where they live.** `brclimr` 0.2.0 (CRAN, 2024-04-04) queries DigitalOcean Parquet (Zenodo 7824920, v1.0.0, 2023-04-13): all seven
  variables end **2020-07-31**. Its authors' later record, Zenodo **13906834** (2024-10-09, concept 7824919, one file per variable,
  2.0-2.2 GB), is BR-DWGD **v3.2.3, 1961-01-01 to 2024-03-20**, the same end for every variable (pr, Tmax, Tmin read; the
  record states it for all seven). No municipal release of v3.2.4 (the grid, 1961 to 2025-12-31, April 2026) exists on Zenodo today.
- **Municipalities.** 5,567 codes of IBGE's 2010 mesh: 5,565 municipalities and the lagoons 4300001/4300002 (dropped). Of the
  5,571 in the identity pack: 5,563 have all 23,090 days (128,495,850 municipality-days with a value); **Fernando de Noronha and
  Bombinhas have no value on any day** (46,180 NaN municipality-days = 2 x 23,090: no grid cell); **six created after 2010 have
  no series** (Mojuí dos Campos, Pescaria Brava, Balneário Rincão, Pinto Bandeira, Paraíso das Águas, Boa Esperança do Norte).
- **Statistics per municipality-day:** count, max, mean, min, stdev (and sum for precipitation). `mean` is area-weighted: against
  an exact area-weighted recomputation from the grid (Tmin, 1970-1999) the median absolute difference is 0.001 °C, against
  0.06 °C for the unweighted mean of the touching cells.
- **Reading cost.** Zenodo gives 60-120 KB/s a connection and 133 requests a minute (HTTP 429 with DuckDB's many small requests;
  a whole file would take hours). `sources/brdwgd.py` fetches each wanted row group as one byte range, 16 at once: about 1,200 row
  groups (0.5 GB) and 20 minutes a variable alone, 30 minutes for the three together.
- **INMET for comparison:** 912 placed stations, 674 municipalities ever; a municipality with 11 complete months of temperature
  in a year: 397 (7.1%) in 2010, 341 in 2023, 196 in 2021.

## (b) Variables
| | INMET stations (mirror) | BR-DWGD municipal release |
|---|---|---|
| precipitation | hourly / daily | daily mean over the municipality (also sum, count, max, min, sd) |
| air temperature | hourly dry bulb (24-hour mean); conventional daily mean, max, min | **Tmax, Tmin only**: no mean (mid-range reads 0.7 °C above INMET's 24-hour mean, median of 257,920 station-months; 10-90%: 0.2-1.2) |
| humidity | relative humidity, dew point (automatic); mean and minimum RH (conventional) | RH |
| radiation | global radiation (automatic), insolation hours (conventional) | Rs |
| wind | 10 m speed, gust, direction (automatic); mean speed (conventional) | u2 (2 m speed) |
| other | station pressure, evaporation (conventional) | ETo |
| coverage | 674 municipalities, point values; hourly only from 2000; mirror ends 2025-01-01 | 5,563 municipalities, 1961 to 2024-03-20 |

The lake's `climate` base keeps only precipitation and temperature of the stations. INMET has what BR-DWGD lacks: a 24-hour mean
temperature, pressure, dew point, gusts and direction, insolation, evaporation, hourly values, and April 2024 to January 2025.
The fields declared are the six that existed; RH, Rs, u2 and ETo are in the same release, one variable each away.

## (c) Reproduction of INMET (station-months with at least 90% of their days, against the municipal value; 1961-2024)
| | station-months | bias | RMSE | r |
|---|---|---|---|---|
| mid-range (what `air_temperature` is) vs station mid-range | 229,107 (909 stations) | -0.07 °C | 0.75 °C | 0.981 |
| mid-range vs station 24-hour mean (definition + error) | 222,683 | +0.63 °C | 1.03 °C | 0.978 |
| mean daily maximum | 229,107 | +0.08 °C | 0.93 °C | 0.973 |
| mean daily minimum | 229,107 | -0.22 °C | 0.84 °C | 0.980 |
| monthly precipitation (mean month about 100 mm) | 238,213 | -2.1 mm | 45.6 mm | 0.923 |

After removing each station's calendar-month climatology: mid-range r 0.962, RMSE 0.26 °C; precipitation r 0.838, RMSE 41 mm (the
temperature error is mostly a constant offset between a site and its municipality). By region (N, NE, SE, S, CO): mid-range
RMSE 0.61, 0.66, 0.95, 0.62, 0.71 °C, bias -0.12, -0.16, -0.17, +0.16, +0.13; precipitation RMSE 67, 39, 41, 34, 50 mm. By decade the
mid-range bias goes from -0.12 (1960s) to +0.08 (2020s), RMSE 0.72-0.82; the Tmax bias from -0.1 to **+0.46** °C and the
precipitation bias from -4.3 to +0.4 mm: the stations that inform the grid change. INMET's stations are inputs of BR-DWGD:
this is a reproduction, not an independent test.

**Maceió A303** (months complete in both, 2003-2024; station mean = 24-hour mean):
| month | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| station mean °C | 26.6 | 26.8 | 26.8 | 26.4 | 25.4 | 24.3 | 23.7 | 23.7 | 24.3 | 25.3 | 26.0 | 26.5 |
| station mid-range °C | 27.0 | 27.3 | 27.3 | 26.8 | 25.8 | 24.7 | 24.0 | 24.0 | 24.6 | 25.7 | 26.4 | 26.9 |
| BR-DWGD mid-range °C | 27.1 | 27.3 | 27.4 | 27.0 | 26.0 | 25.0 | 24.3 | 24.3 | 24.9 | 25.9 | 26.7 | 27.1 |
| station rain mm | 98 | 91 | 120 | 192 | 306 | 345 | 260 | 173 | 103 | 70 | 46 | 36 |
| BR-DWGD rain mm | 78 | 84 | 102 | 172 | 276 | 326 | 243 | 148 | 85 | 55 | 37 | 36 |

Temperature reproduces (mid-range +0.2 °C; the station's 24-hour mean 25.5 °C, the municipality's mid-range 25.8 °C in 1991-2020).
Rain is 11% low (1,642 mm against 1,841 mm over the same months; the municipality 1991-2020: 1,567 mm): A303 stands on the wet coast
and the cell averages the municipality. Where the gauge failed (complete-month rule: February to August 2021, no precipitation)
BR-DWGD gives 13.9, 189.1, 252.5, 265.4, 254.9, 236.2 and 215.2 mm (mid-range 27.4 to 24.3 °C); no independent observation checks them.

## (d) The gap and its fill
BR-DWGD's municipal series end 2024-03-20: 2024 is `partial_year` (2.645 months), and April 2024 to today (2026-10) is absent.
Compared on their overlap with the v3.2.4 grid (1961 to 2025-12-31; Google Drive, 355 MB monthly archive, zonal means recomputed here
with the current mesh): Tmax differs by an RMS of 0.03-0.09 °C a month, Tmin by 0.09-0.28 °C (0.5 °C or more in 207 municipalities
in 1970-1999: 41 in Mato Grosso, 27 each in Pará and Tocantins, 25 in Minas Gerais), precipitation by 3-8 mm a month before 2010, 12 mm in the 2010s and 22 mm in 2020-2024:
the newer version revises the past, so a grid fill would put a step at 2024-03.
ERA5-Land municipal means (the same authors; 2024 and 2025 records, 8 variables, 40 MB a variable-year; 4 variables x 2 years = 320 MB,
about 15 minutes) have what BR-DWGD lacks, a 24-hour mean. In 2023, against INMET's 6,205 station-months: mean temperature
bias +0.06 °C, RMSE 1.00 °C (BR-DWGD's mid-range: +0.82 against the same mean), but Tmax bias -0.99 °C, Tmin +0.51 °C and precipitation -18.9
mm a month with RMSE 64 mm (BR-DWGD: +0.82 mm, 42 mm); against BR-DWGD itself, Tmax -1.49 °C, Tmin +0.64 °C, precipitation -21 mm. The least-cost
fill is therefore ERA5-Land with a per-municipality-month offset fitted on the overlap; it is not done here (a decision on a different
product), and the fields stop at the release, with `partial_year` and `source` saying so.

## Build in the real lake (the coordinator; writes `lake/fields/{climate_monthly,...}` and `registries/brdwgd`)
`PYTHONUTF8=1 python -m pegasus_data.cli fields --root C:/Users/Galaxy/pegasus_core_data --name climate_monthly --name temperature_months --name air_temperature --name air_temperature_monthly_max --name air_temperature_monthly_min --name precipitation_months --name precipitation_mm`
About 30 minutes the first time (3 x 0.5 GB by byte range from Zenodo, then 18 s); later runs read the cached monthly sums.
