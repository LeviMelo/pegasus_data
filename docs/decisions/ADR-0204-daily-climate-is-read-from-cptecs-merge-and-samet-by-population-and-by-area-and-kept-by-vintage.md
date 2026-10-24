# ADR-0204: Daily climate is read from CPTEC's MERGE and SAMeT, by population and by area, and kept by vintage

2026-10-24. Status: active. Complements ADR-0178 (BR-DWGD stays the source of the yearly climate fields); examines the two
products ADR-0178 did not.

## Context

ADR-0178 chose BR-DWGD's municipal zonal means for yearly context fields: every municipality, every day 1961-2024, read
once. It did not ask for daily values to a recent date, and none of its candidates gives them: the release read ends
2024-03-20 (v3.2.4, to 2025-12-31, is on Google Drive behind quota), its municipal means are area-weighted, and a model fed
in operation by another product than the one it was trained on learns a step at the junction. Two consumers need the
opposite: a dengue spatio-temporal forecast (daily or weekly exposure to the day before yesterday, back-tested as of each
date) and a diabetes prevalence study (exposure where people live).

CPTEC/INPE publishes two daily gridded products over South America on a plain file server: MERGE (gauges merged with GPM
IMERG, 0.1°, 1998 on) and SAMeT (stations merged with ERA5 and corrected by lapse rate, 0.05°, 2000 on), each one product
throughout, with a file per day the morning after. SAMeT's recent days are made from forecasts and rewritten about a week
later with ERA5 (its Read-me; the server's times confirm it: a TMAX day appears at 03:06 UTC the next day, and TMAX of
2026-10-15 was rewritten at 03:06 on 10-22).

## Decision

1. **Source.** Daily precipitation from MERGE and daily Tmax, Tmin and Tmed from SAMeT, from 2000-01-01 (the first day
   both exist) to the last file served, read through the one transport and never kept as grids (`sources/cptec.py`).
2. **Two municipal means per day**, from the Grade Estatística's weights (ADR-0203): by population (where people live)
   and by area (the territory; BR-DWGD's kind). Weight on a grid cell with no value (SAMeT's sea cells, where coastal
   towns' people live) is read at the nearest cell with a value within 10 km; `coverage` is the share read at its own
   cell; `stations` the product's stations or gauges in the cells touched.
3. **Every vintage kept.** A file is read when not held or when the server lists it with another time; its rows are added
   beside the old ones with `published` (the server's `Last-Modified`). `climate_daily` returns the latest, or with
   `as_of` the latest published by then; a day first read after its rewrite has only its final value. A week or month is
   a sum and a count of days at read (`climate_weekly`, epidemiological weeks).
4. **No splice.** BR-DWGD keeps the yearly fields 1961-2024 (ADR-0178) and is the reference this product is validated
   against over the overlap; neither fills the other's gap.
5. **MERGE is served as it is, with its bias stated.** It is about 15% drier than the gauges (Evidence); a
   model reads it as a consistent series, not as gauge totals, and nothing rescales it.
6. **Humidity is not served yet.** Neither product has it; ERA5-Land through the Copernicus CDS needs the author's
   account. INMET's stations (hourly humidity) stay observations.

## Evidence

Evaluation 2026-10-24-cptec-daily-climate:

* the backfill holds every day 2000-01-01 to 2026-10-23 of the four variables (9,793 files each), 2.4 GB;
* the store equals its own files: means recomputed from the 2023 grids differ from the stored ones by at most 7.6e-6
  (float32); MERGE's daily grids summed over September 2023 equal CPTEC's published monthly accumulation on all 380,741
  cells (difference 0);
* SAMeT against BR-DWGD (area-weighted, 1,613,270 complete municipality-months 2000-01 to 2024-02, 5,563 municipalities):
  Tmax bias +0.06 °C, RMSE 0.75, r 0.98; Tmin −0.04, 0.74, 0.98; the Tmax difference drifts from +0.19 °C (2000) to
  −0.46 (2023);
* MERGE against BR-DWGD: −17.9 mm a month (RMSE 35.4, r 0.96, anomaly r 0.91), a ratio of 0.845 in every month of the
  year and at every intensity; against INMET's automatic gauges (2023, 143,568 station-days) 0.83 of their totals,
  0.89 in cells holding a merged gauge and 0.64 in cells holding none; BR-DWGD is within −2.1 mm a month of the same
  gauges (ADR-0178), so MERGE is the dry one;
* the day is tested, not assumed: MERGE's day fits the 24 h ending 12 UTC (r 0.88 against 0.60 for the UTC day), SAMeT's
  the UTC calendar day (Tmax RMSE 0.63 against 0.69 for the local day);
* population against area weighting: annual rain differs a median 1.7%, 7.2% at p90, 19% at p99 (2000-2008);
* SAMeT's land mask leaves 74 municipalities under 90% of their population weight at its own cells (31 under 50%);
  clause 2 reads that weight at the nearest land cell.

## Consequences

* The vintages exist only from the first daily `climate-update`; until it runs every day (not scheduled by this work),
  a backtest before 2026-10-24 reads final values.
* The backfill reads about 39,000 files (63 GB) to store 2.4 GB; a later update reads only new and rewritten files.
