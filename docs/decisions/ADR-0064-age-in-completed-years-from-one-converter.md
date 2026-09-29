## ADR-0064: Age is derived in completed years by one converter, declared per curated recipe

**Date:** 2026-09-28. **Status:** active. **Supersedes:** ADR-0020 (no
`IDADE_anos`). **Amends:** ADR-0058 (age banded in aggregates).

**Context.**
- Two converters existed. `view._derive_age_years` read the unit column's
  labels for words like "meses" and divided. `_age.years_column` knows each
  system's documented encoding (SIH's separate `COD_IDADE`; SIM's and
  SINAN's leading unit digit) and maps sub-year ages to 0.
- They disagreed on infants: 0.5 years against 0.
- The first could not run at all for SIH, because `COD_IDADE` has no
  codelist. So `IDADE_anos` was never produced, and `query()` also turned
  derived columns off. No read path returned an age in years (live run
  2026-09-28).
- ADR-0020 withheld the derivation because no unit codelist existed.
  ADR-0058 then decoded the same units for aggregates, reading only "years"
  and "100+".
- The USP SIH dictionary in the harvested sources
  (`sources/sih_batch/usp_dict.txt`) states 0 ignored, 2 days, 3 months,
  4 years, which agrees with `_age.py`.

**Decision.**
- `IDADE_anos` is **age in completed years**, the epidemiological convention,
  computed only by `_age.years_column`, floored in the stated unit: months
  ÷ 12, SIH's days ÷ 365.25. Minutes and hours are 0, and SIM's and SINAN's
  layouts bound them below a year anyway (`sources/sim2025.txt`: months
  01–11, days 01–29, hours 01–23). Unit 5 is 100 + value. An unknown or
  ignored unit is null.
- A curated `derived` recipe declares its `encoding` (`sih`, `sim`, `sinan`,
  `years`). SIH (`IDADE`+`COD_IDADE`), SIM (`IDADE`) and SINAN (`NU_IDADE_N`)
  declare it.
- `view._derive_age_years` and its label-reading unit table are deleted.
- `query()` carries curated derivations whenever it carries labels.

**Measured after:** SIH `IDADE` 48, unit 4 → 48.0; SIM `IDADE` 478 → 78.0;
SINAN `NU_IDADE_N` 4026 → 26.0.

**Alternatives.**
- Fractional years (six months = 0.5). This needs exact minute, hour and day
  codes, and the sources disagree on which digit is days.
- Mapping every sub-year unit to 0, which `_age.py` did before. That is wrong
  for a SIH record giving 30 months (2 completed years).

**What would reverse it.** A layout document showing that a system's "years"
or "100+" unit code is not the one `_age.py` reads.
