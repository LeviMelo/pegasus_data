# Age-standardised rates (direct, over POPSVS)

**Date:** 2026-10-03.

**Regime:** `rates.age_standardised_rates`, run on SIM-DO SE 2022 (14,791
deaths, `IDADE_anos`) from the linkage home, with POPSVS 2022 from
`pegasus_data_home`.

**Method.** 5-year bands 0–4 … 75–79 and 80+ (POPSVS closes at 80).
- **Standards:** WHO World Standard 2000–2025 (its bands from 80 on folded
  into 80+), or Brazil 2022 from POPSVS.
- **Interval:** Fay–Feuer gamma 95% interval.

**Result** (per 100,000):

| scope | crude | WHO 2000 (95% CI) | Brazil 2022 |
|---|---|---|---|
| Sergipe | 650.5 | 606.1 (596.3–616.0) | 728.1 |
| Aracaju | 637.0 | 551.4 (534.2–569.1) | — |

- **The direction is right.** Sergipe is younger than Brazil and older than
  the WHO world population, so Brazil's standard raises its rate and WHO's
  lowers it.
- **Unknown ages are excluded and counted:** 1 death without an age is in
  `unaged`.

**Found on the way.** `load_population(uf=...)` ignored the state filter for
POPSVS, which has no `uf` column, and returned the whole country. It now
filters on the municipality code's state digits (SE: 2,273,589 people), and
refuses when it cannot filter.
