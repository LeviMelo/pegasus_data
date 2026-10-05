# CNES supply fields, 2008-2023 (2026-10-05)

**What.** The 35 `cnes_*` fields (ADR-0150) built by `build_fields`: `sources/cnes.py`, `fields._build_cnes`, the December file of each year, 27 states, 2,160 state files, 1,829 s on the core data home (mirror download; aggregates cached in `registries/CNES/agg`). Report: `pegasus_project/data/handoffs/cnes_build_report.json`. Regime: branch pegasus-core-fixes, `C:/Users/Galaxy/pegasus_core_data`.

**Counted and why.** National sums per year against known magnitudes, six places against each other, and the rows that did not land. **0 unallocated codes in every field and year** (the DF region codes are mapped to 530010 for 2008-2017). Municipalities with no establishment in the ST register (`no_cnes_record`): 7 in 2008, 6 in 2009-2012, 2 in 2013, 1 in 2014-2015, 4 in 2016, 1-2 afterwards, 1 in 2023.

| National | 2008 | 2015 | 2023 |
|---|---|---|---|
| Establishments, SUS / non-SUS | 70,680 / 119,883 | 93,456 / 192,555 | 116,554 / 291,079 |
| Beds total / SUS / ICU | 502,971 / 364,935 / 31,556 | 496,287 / 339,985 / 40,960 | 528,532 / 351,426 / 62,359 |
| CT units | 2,455 | 3,996 | 6,774 |
| ESF teams / EAB + EAP | 29,769 / 0 | 41,039 / 418 | 53,511 / 6,171 |
| Physician registrations / distinct CNS | 770,910 / 350,116 | 969,955 / 497,807 | 1,553,128 / 805,369 |

**Places, 2008 to 2023.** Sao Paulo: beds 34,248 to 37,923, CT 222 to 473, ESF teams 864 to 1,668, distinct physicians 29,727 to 69,164. Rio: beds 26,444 to 21,871, ESF teams 126 to 1,294 (the family-health expansion). Brasilia: ICU beds 670 to 1,882. Rio Branco: ESF teams 39 to 83, CT 3 to 16. Bora (SP, 3.5 k residents) and Serra da Saudade (MG): no hospital, bed or scanner, 2-7 physicians, 2 ESF teams. Rates for 2023 over the population account: beds per 1,000 residents 3.09 in Sao Paulo, 2.93 in Rio Branco, 2.49 nationally; ICU beds per 100,000 50.2 and 24.3; ESF teams per 10,000 residents 1.36 and 2.10, 2.51 nationally (times 3,450 is a 87% potential coverage).

**Findings.**
- Magnitudes agree with what is known: ESF teams about 30 k (2008) to 53 k, CT about 6.8 k, ICU beds 62 k in 2023.
- Beds step up in 2020 (490,397 to 535,821), the pandemic year; left as registered.
- ESF teams step 44,421 to 49,000 in 2020, where the team typology changes (types 70 and 71); not shown to be real growth.
- Distinct physicians overstate: 3.78 per 1,000 nationally (sum over municipalities, several CNS per person) against 5.64 in Sao Paulo and 2.49 in Rio Branco; compare places, do not read the national sum as a headcount. Registrations and weekly hours are exact counts of the register.
- 16 municipalities have no rate: the population account merges them into a parent's place.

**Not done.** E-Gestor's validated coverage; months other than December; teams before EP starts (2007-04).
