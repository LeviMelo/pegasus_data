# Climate as context fields: one value per municipality and year

*Note, 2026-10-14: the source measured here (INMET's stations) is superseded by BR-DWGD's municipal series (ADR-0178, [2026-10-14-climate-brdwgd](2026-10-14-climate-brdwgd.md)); the figures below stand as measurements of the stations.*

**Date:** 2026-10-14. **Regime:** branch `fix2-climate`; station-month base read from `pegasus_core_data/lake/fields/climate`
(read-only, 275,810 station-months); derived tables built under a scratch root (`registries/inmet` junctioned to the real one),
14 s. Decision: ADR-0177.

**What was counted.**
- Naive means are wrong. Maceió (270430), a coverage-weighted year: 25.3 °C mean of 1991-2020 (24 years), annual cycle 23.6 °C
  (Jul-Aug) to 26.9 (Mar), 1,795 mm a year; the same table with a gappy year: 2020 (4.6 months observed) 27.1 °C.
- Against known climate: Brasília 1961-1990 20.59 °C (the 2026-10-03 entry's single-station 20.56); Manaus 2022 27.77 °C, the mean
  of its two stations (27.58 and 27.97); Curitiba 17.8, Porto Alegre 19.8, Recife 26.0, Brasília 21.3 (1991-2020, ok years).
- Rows per field (all years): 20,818 municipality-years with temperature (14,345 `ok`, 6,473 `partial_year`), 21,339 with
  precipitation (15,237 `ok`).
- Why 11 months: knocking a block of months out of the 9,968 complete municipality-years moves the mean by a median 0.11 °C and
  0.39 °C (95%) for one month, 0.81 for two (year-to-year SD, median over municipalities: 0.52 °C); monthly precipitation by 16%
  and 28% against about 20%.
- Networks where both stand in a municipality (19,340 municipality-months observed at least 90%): mean temperature -0.17 °C
  (automatic minus conventional, median), maximum -0.7, minimum +0.1 (10-90%: -1.1 to +1.5); monthly precipitation correlation
  0.83. Two stations of one network: median |difference| 0.4-0.6 °C.

**Build in the real lake** (the coordinator; writes `lake/fields/{climate,temperature_months,...}`, offline):
`PYTHONUTF8=1 python -m pegasus_data.cli fields --root C:/Users/Galaxy/pegasus_core_data --name climate --name temperature_months --name air_temperature --name air_temperature_monthly_max --name air_temperature_monthly_min --name precipitation_months --name precipitation_mm`
