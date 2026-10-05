## ADR-0150: CNES supply is read as December stocks and declared as `cnes_*` fields of the existing fields mechanism, with the code groups in `fields.yml`

**Date:** 2026-10-05. **Status:** active. **Request:** pegasus_project ARCHITECTURE section 12 phase 3 "CNES fields" (a field of kind `level`, read through `gateway.context_field`).

**Context.** The place x year layer held IBGE, INMET, S2iD, ANS and INEP, and nothing on the health system's own supply. CNES publishes five relevant datasets (ST establishments, LT beds, EQ equipment, EP teams, PF professionals) as monthly state files; a stock must not be summed over months.

**Decision.**
1. **Competence.** The December file of each year, 2008-2023, all 27 states, through the DATASUS mirror (`sources/cnes.py`). PF is 3.8 GB compressed over all years, so each state file is aggregated once to municipality x group, cached under `registries/CNES/agg`, and the PF DBC is deleted.
2. **Mechanism.** 35 scalar fields `cnes_*` in `curation/fields.yml` (`source: cnes`, `family`, selectors, `unit`, `law: sum`, `gaps`), built by `fields._build_cnes` into `<lake>/fields/<name>/year=Y`, one row per IBGE municipality, so `gateway.context_field` reads them unchanged. The groups (`cnes:` block) are CNES's own codes: hospital = TP_UNID 05, 07, 15; primary-care unit 01, 02, 45; specialised clinic 04, 36; the rest `other`. ICU beds = ESP_LEIT 61-63, 74-83, 85, 86. CT 111, MRI 112, mammography 102/103/117, dialysis 677. ESF teams = TIPO_EQP 01-03, 12-15, 24-39, 70 without a deactivation date; physicians = CBO 2231, 225; nurses 2235; community health agents 515105. SUS = VINC_SUS 1 (establishments), QT_SUS (beds), IND_SUS 1 (equipment), PROF_SUS 1 (hours).
3. **Missing is not zero.** A municipality with at least one establishment in the year's ST file gets a value, 0 included (`ok`); one with none is null, `no_cnes_record` (1 to 7 municipalities a year). A CODUFMUN that is not an IBGE municipality would be summed and reported as unallocated; none occurs once the DF region codes are mapped (the CODUFMUN_municipio rule).
4. **Rates.** Fields store sums only. `field_rate(name, per=...)` divides by the municipal total of `population-account-2` (1 August); 16 municipalities that the account merges into a parent have no rate. Primary-care coverage is the ESF team field over population; the 3,450-persons-per-team coverage is a convention applied at use, not stored.

**Evidence.** docs/evaluation/2026-10-05-cnes-supply-fields.md: ESF teams 29,769 (2008) to 53,511 (2023); CT 2,455 to 6,774; ICU beds 31,556 to 62,359; capitals against small municipalities plausible; no unallocated codes.

**Not decided.** Distinct physicians are an upper bound (several CNS per person, persons in several municipalities); an unduplicated headcount needs a CNS crosswalk. The 2020 step in ESF teams (43.6 k to 49.0 k) coincides with the new team typology and is not shown to be growth. Months other than December; non-SUS equipment quantities.
