## 2026-09-28 — The frontend's API after the redesign, and one served number checked against the microdata

**Question.** After ADR-0061 to ADR-0073, does `serve/` still answer what
`../pegasus_view` asks? And is a number it serves the number the microdata
gives?

**Regime.**
- `python -m pegasus_data.serve --port 8765`, run from the repository (the
  maintainer home, 62 recipes, 51 built), as `start-pegasus.ps1` launches it.
- Microdata recomputed with `query()` on the live home.
- Branch `redesign` at `26b48ff`.

**What was counted.**
- The HTTP status of every route the frontend calls: `/health`, `/datasets`,
  `/datasets/{a}/capabilities` for all 51 built artifacts, `/artifacts/{a}`,
  `/population` and `/geo/membership`.
- One headline cell, SIH-RD for Alagoas in January 2022, against the same
  count taken from the microdata.

**Result: the routes.**
- `/health`: 62 artifacts, 51 built.
- `/datasets/{a}/capabilities`: **51 of 51** returned 200.
- `/artifacts/sih_rd_municipality_month?by=uf,year` (27 rows),
  `…?by=brazil,year,FAIXA_ETARIA&dim.SEXO=3` (18 rows),
  `cnes_st…?by=brazil,month` (12 rows) and `sim_do…?by=uf,year` (27 rows) all
  returned 200.
- `/population?series=POPSVS&by=uf,year`: 702 rows.
- `/geo/membership`: all 5,571 municipalities.
- An unknown level (`by=state`) is refused with 422 and the list of levels
  that exist.

**Result: the number.** The recipe declares geography by residence
(`MUNIC_RES`) and time by competência. So the check reads every state's
January 2022 file (988,307 rows, 36 s through `query()`) and keeps the
residents of Alagoas (`MUNIC_RES` 27xxxx):

| | served | microdata |
|---|---|---|
| admissions | 13,027 | 13,027 |
| deaths | 594 | 594 |
| cost (R$) | 18,268,199.10 | 18,268,199.10 |
| length of stay (days) | 72,140 | 72,140 |

The same month by other definitions shows why stating the definition matters:
- 12,854 rows in Alagoas's own January file (publication state);
- 12,741 admitted in January across all of Alagoas's 2022 files (event date);
- 12,506 discharged in January.

The served figure is right for its declared definition, and a reader asking a
different question gets a different, also-correct number.

**Not checked here.** The rolled-up levels (health region, macroregion)
against an independent source, and the other 50 built artifacts cell by cell.
