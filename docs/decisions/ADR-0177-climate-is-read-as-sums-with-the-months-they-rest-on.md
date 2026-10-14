# ADR-0177: the climate fields are sums with the months they rest on, one value per municipality and year

**Date:** 2026-10-14. **Status:** accepted.

**Context.** `climate` stored INMET's station-month sums, counts and extremes. A context consumer reads a field as one value per
municipality and year, optionally over a declared denominator (`over`), through `load_field`; the station-month table has no
`value`, `status` or `unit`, so a study declaring it left it out ("a count with no declared denominator"). Averaging it naively
is wrong in three ways found on the lake: an hourly station has 24 times the readings of a daily one; a year with months missing
is a mean of the wrong season (Maceió 2020, 4.6 months observed, reads 27.1 °C against its 1991-2020 mean of 25.3 °C); and an annual
precipitation total over the months held reads a gappy year as dry.

**Decision.**
- **`climate` stays as the base** (station-month, the monthly and seasonal questions are asked of it). Six fields are read from it
  in the one build (`fields --name ...`): `temperature_months`, `air_temperature`, `air_temperature_monthly_max`,
  `air_temperature_monthly_min`, `precipitation_months`, `precipitation_mm`. Each is a sum with its denominator in `over`, so the
  mean is formed at use and lifts to a coarser place as a ratio of sums, like every other context field. Value, status, unit, source
  as elsewhere, plus `months`, `stations`, `automatic_share`. A municipality without a station has no row.
- **Coverage weights, not readings.** A station-month's coverage is its days observed over the days of the month (an hourly
  station's readings / 24). A municipality-month is the coverage-weighted mean of its stations; its own coverage is its best
  station's. A municipality-year sums coverage (`*_months`, 0-12, the denominator) and coverage times the month's value. No
  station counts more for being hourly, a month half observed counts half, and nothing is thresholded inside the month.
- **Precipitation is a mean month, not a total** (`precipitation_mm` over `precipitation_months`; times 12 for a year): the
  stations' month total per unit of coverage.
- **A year is `ok` at `inmet: min_months` = 11 months observed, else `partial_year`** (value kept; consumers read `ok` only).
  Chosen from the data: on the 9,968 complete municipality-years, leaving one month out moves the mean temperature by at most 0.39 °C
  (95%), two by 0.81 °C, against a year-to-year SD of 0.52 °C; precipitation 16% and 28% against a spread of about 20%.
- **Extremes are kept with their network.** An automatic station reports its hottest hourly reading, a conventional one its
  thermometer's maximum (0.7 °C higher, median of 19,340 municipality-months with both); `automatic_share` says how much of a
  value is automatic. The mean temperature differs by -0.2 °C between the networks and is not flagged.

**Consequences.** A study naming `climate` (infarto_alagoas, toxoplasmosis_survey9) names the fields above instead. Nothing is
interpolated; unscreened sensor faults are in the readings (A401 June 2007, 43.9 °C) and in `gaps`. Evidence:
`docs/evaluation/2026-10-14-climate-context-fields.md`.
