## ADR-0127: Context fields are IBGE's municipal statistics, declared by IBGE's own table and variable, stored as totals with IBGE's markers kept

**Date:** 2026-10-03. **Status:** active. **Part of:** ADR-0050 (aggregates),
ADR-0055 (denominators).

**Context.**
- **No context fields.** The PegaSUS lineage's quantities were flows
  (events), stocks (population) and fields (properties of a place and year:
  income, sanitation). Its recollection notes that pegasus_data "does not
  yet hold SIDRA, a population method, climate or disasters". Fields are
  what an analysis adjusts for.
- **IBGE's aggregates API is the first-party source.** Each table states its
  variables, units, periods and territorial levels in
  `/agregados/<table>/metadados`.

**Decision.**
1. **`curation/fields.yml` declares each field** by IBGE table, variable and
   unit, as the metadata states them. It starts with municipal GDP (5938/37)
   and the gross value added of public administration (5938/525) and of
   agriculture (5938/513), 2002–2023.
2. **`pegasus-data fields` reads them** into `<lake>/fields/<name>/year=YYYY/`.
   Each row holds municipality (6 and 7 digits), value, status, unit and
   source. `load_field(name, years=…)` reads them back.
3. **Totals only.** A per-capita figure is computed at use over POPSVS, not
   stored, as CLAUDE.md requires of stored aggregates.
4. **IBGE's markers are a status, never a value:**
   - `-` is a true zero;
   - `..` (not applicable), `...` (not available) and `X` (suppressed) are
     null with their reason.
5. **The response is gzip without `Content-Encoding`**, as with IBGE's
   meshes. It is detected by its magic bytes.

**Evidence.** EVALUATION 2026-10-03 "Context fields from IBGE". GDP 2021 has
5,570 municipalities, all `value`, and sums to R$ 9,012,142,031 thousand:
Brazil's GDP for the year. Aracaju reads R$ 18,405,678 thousand.

**Consequences.**
- **A new field is one YAML entry,** checked against IBGE's metadata.
- **Census tables, sanitation, climate (INMET) and disasters (S2iD) are not
  declared yet;** each needs its own source check. STATUS lists them.
