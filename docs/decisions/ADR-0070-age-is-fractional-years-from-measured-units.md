## ADR-0070: Age is one column of fractional years, decoded from measured unit tables

**Date:** 2026-09-28. **Status:** active. **Supersedes:** ADR-0064 (age in
completed years). **Amends:** ADR-0058 (age banded in aggregates).

**Context.**
- ADR-0064 derived `IDADE_anos` in completed years: 18 months became 1, and
  12 days became 0. That throws away information the source states, and
  infant ages became indistinguishable.
- The user proposed one normalised column of fractional years (18 months =
  1.5), in place of several columns encoding the same thing differently.
- Doing that needs the exact meaning of every unit code. The layout documents
  do not supply it reliably. Measured against the records' own dates
  (evaluation 2026-09-28, "age units measured against dates"):
  - SIM's units are 0 minutes, 1 hours, 2 days, 3 months, 4 years and
    5 = 100+. Its structure document says 1 = minutes.
  - SIH's are 2 days, 3 months, 4 years and 5 = 100+.
  - SINAN's are 1 hours, 2 days, 3 months, 4 years, and 0.8% of values carry
    no unit digit and are plain years. The old decoder turned those into
    days.

**Decision.**
- `IDADE_anos` is **fractional years**: the stated quantity times
  years-per-unit. A year is 1; a month is 1/12; a day is 1/365.25; an hour is
  1/8,766; a minute is 1/525,960. Unit 5 is 100 + quantity. It is null when
  the unit is unknown (SIH `0`, SIM `999`/`000`) or the quantity is not
  digits.
- It is computed only by `_age.years_column`, from the measured tables in
  `_age.UNITS`. The curated `derived` recipe declares its `encoding`: SIH
  (`IDADE`+`COD_IDADE`), SIM (`IDADE`), SINAN (`NU_IDADE_N`).
- Completed years is `floor(IDADE_anos)`. Age bands compare the same number,
  so a fractional age lands in the band it belongs to.
- **One derived column, not an encoding string.** A record states one
  quantity in one unit ("18 months", never "1 year 6 months"). A composite
  `yy-mm-ww-dd-hh` string would imply a precision the source does not have.
  The lossless statement is the raw pair, which is always kept (ADR-0063). Its
  standard spelling, if a caller wants one, is the ISO-8601 duration of
  quantity and unit (`P18M`, `P12D`, `PT5H`), not a new column.

**Alternatives.**
- *Completed years* (ADR-0064). Rejected as lossy.
- *A composite duration string column.* Rejected as false precision (above).
- *Age from the dates, where the record has them.* SIM and SIH carry birth
  and event dates. They are the ground truth this decision was measured with,
  but they are separate fields with their own errors. `IDADE` is the field the
  Ministry publishes as age, so the derived column decodes it, and the dates
  stay available to anyone who wants the other definition.

**What would reverse it.** A vintage whose unit codes differ from the measured
tables. The same measurement, run on an older year, would show it.
