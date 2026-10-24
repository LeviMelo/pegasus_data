# Daily climate from CPTEC's MERGE and SAMeT, by population and by area (2026-10-24)

**Check.** `pegasus-data climate-update` (`sources/cptec.update`, ADR-0204) read every daily file of MERGE (precipitation)
and SAMeT (Tmax, Tmin, Tmed) from 2000-01-01 and stored two municipal means a day; `scripts/cptec_validation.py` then
compared them with BR-DWGD's municipal series and with INMET's automatic stations, and recomputed the store from the
files. What was counted and why: whether every day is held; whether the store adds or loses anything against its own
files and against CPTEC's own aggregates (a reading error would show there, not against another product); the agreement
with the two independent references, by region and year (a step or drift is what a model trained on one decade and run on
another would learn); which day window each product means (tested against the stations' hours rather than assumed); and
how far population and area weighting part.

**Regime.** Branch `claude/nees-gaps-dc2b18`; backfill launched on 7bfd55b (precipitation from f742f46, whose decoding is
the same), `pegasus_core_data`, 2026-10-24; artifacts `data/probes/climate/cptec_validation.json`,
`cptec_brdwgd_precipitation.json`, `cptec_station_samples_2023.parquet`. Backfill: 39,172 files (about 63 GB, nothing kept
but the means), 2.4 GB stored, about 2 h with the three SAMeT variables in parallel processes.

**Held.** 9,793 days of each variable, 2000-01-01 to 2026-10-23 (2026-10-24 not yet published); 5,570 municipalities in
MERGE, 5,569 in SAMeT (Fernando de Noronha lies east of its grid). A second update reads nothing.

**Exactness.** Means recomputed from the 2023 grids equal the stored ones within 7.6e-6 (float32), for both weights and
the four variables. MERGE's daily grids summed over September 2023 equal CPTEC's `MERGE_CPTEC_acum_sep_2023.nc` on all
380,741 cells (difference 0). Maceió's Tmax of 2026-10-20 sampled at its 1 km grade cells from `day_grid` (31.535 °C)
equals the stored population mean (31.531 °C) to the edge cells.

| against BR-DWGD (area-weighted, complete months 2000-01 to 2024-02; 1,613,270 municipality-months) | bias | RMSE | r | anomaly r |
|---|---|---|---|---|
| SAMeT Tmax (°C) | +0.06 | 0.75 | 0.982 | 0.89 |
| SAMeT Tmin (°C) | −0.04 | 0.74 | 0.982 | 0.85 |
| MERGE precipitation (mm a month) | −17.9 | 35.4 | 0.961 | 0.91 |

* **Drift.** The Tmax difference moves from +0.19 °C (2000) to −0.46 (2023), Tmin from −0.10 to +0.20: the two products
  disagree on the trend by about 0.6 °C over 23 years.
* **MERGE is dry, and the reading is not the cause.** Its ratio to BR-DWGD is 0.845 in every calendar month (0.835 to
  0.856) and at every intensity (dry months, months over 200 mm: 0.843). Against INMET's automatic gauges in 2023 (24 h
  ending 12 UTC, complete days, 143,568 station-days) MERGE holds 0.83 of their totals: 0.89 in cells where a gauge is
  merged, 0.64 where none is. BR-DWGD is within −2.1 mm a month of the same gauges (2026-10-14-climate-brdwgd).
  Rival readings ruled out: the decoding (CPTEC's own monthly accumulation is reproduced exactly) and the day window (a
  window shift moves rain between days, not out of the month).

| against INMET's automatic stations, 2023, the grid cell holding the station | utc_day | local_day | ends_12utc |
|---|---|---|---|
| precipitation, r (RMSE mm) | 0.60 (8.9) | 0.51 (9.9) | **0.88 (5.2)** |
| Tmax, r (RMSE °C) | **0.993 (0.63)** | 0.992 (0.69) | 0.874 (2.57) |
| Tmin | 0.989 (0.66) | 0.984 (0.78) | 0.990 (0.64) |
| Tmed | **0.992 (0.56)** | 0.987 (0.70) | 0.971 (1.06) |

MERGE's day is the gauge day (the 24 h ending 12 UTC, as Rozante et al. 2020 state); SAMeT's is the UTC calendar day (Tmin
cannot tell, its minimum falls inside both). In cells without a station the errors double (Tmax RMSE 1.32 °C). The
stations are among both products' inputs: a reproduction check, not an independent one.

**Population against area.** Annual precipitation 2000-2008 (50,130 municipality-years): the two weights differ a median
1.7%, 7.2% at p90, 19% at p99, up to 86%; 2404101's people get 32% more rain than its territory. SAMeT's land mask holds
less than 90% of the population weight at its own cells for 74 municipalities (31 under 50%: coastal towns, Fortaleza
0.49); that weight is read at the nearest land cell within 10 km, and `coverage` says how much.

**Found and fixed on the way.** eccodes fails ("no definitions found") when two threads load its definitions, and
netCDF4/HDF5 loses an in-memory dataset ("Not a valid ID") under threads: decoding is now one at a time, and every SAMeT
row decoded before that fix was deleted and read again. Two `update` processes of one variable would add a vintage twice:
a per-variable lock.

**Vintages.** In October 2026 a SAMeT TMAX day appeared at 03:06 UTC the next day and was rewritten at 03:06 seven days
later (TMIN: 17:04 the same day, rewritten six days later); MERGE's days were written once. The backfill holds one vintage
per file, the one served on 2026-10-24: a backtest before that date reads final values until `climate-update` runs daily.
