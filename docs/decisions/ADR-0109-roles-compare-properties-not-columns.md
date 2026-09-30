## ADR-0109: Records are compared through roles, the property a column states about an entity, normalised through the project's own meaning

**Date:** 2026-09-30. **Status:** active. **Part of:** ADR-0107.

**Context.**
- **The same concept is filed differently in each system.**
  - Dates: DDMMYYYY in SIM and SINASC, YYYYMMDD in SIH and CIHA; SIA-PS's
    `DT_ATEND` is a month (YYYYMM).
  - Sex: SIH 1/3, SIM and SINASC 1/2, SIA M/F. The decoded labels agree up to
    case ("Masculino", "masculino").
  - Missing places: CIHA AC files every residence as 120000, "Município
    ignorado - AC". In CIHA SP 2023-01 that is 16.4% of 580,210 records.
- **The same property belongs to different people.** SINASC `DTNASCMAE` and
  SIH `NASC` are both birth dates, but in a delivery admission the SIH patient
  is the SINASC mother. A synonym list ("birth date = birth date") would link
  babies to their mothers' admissions.
- **Labels that mean the same thing are spelled differently.** SIM writes
  "cesáreo", SINASC "cesário"; SIM "tripla e mais", SINASC "tripla e+". On the
  first live run of the infant-death link (AC 2022), delivery type "agreed" in
  46.5% of pairs whose plurality agreed in 99.2%.

**Decision.**
- **`curation/roles.yml` declares roles.** For each dataset: the kind of
  record, and for each role, `<entity>.<property>`, the column, and a type:
  date (with format), month, sex, municipality, facility, integer, number,
  code, label.
- **`linkage/roles.py` normalises through the project's meaning:**
  - dates are parsed by declared format;
  - sex is read from the decoded label;
  - a municipality or facility whose label says "ignorado" is missing;
  - widths are checked, never padded;
  - a `label` role may declare `categories` (canonical category → the
    spellings each system uses); a label outside the map is missing, not
    guessed.
  
  Anything unparseable is null and contributes no evidence.
- **Only the role columns are read.** `query(select=…)` keeps them, and every
  row keeps its record identity `(_blob_sha256, _row)`.
- **Roles are declared for the spine:** SINASC-DN, SIM-DO, SIH-RD and CIHA,
  plus SIASUS-PS for error channels.

**Defects found and fixed on the way.**
- **Provenance vanished under `select=`.** `query(provenance="all",
  select=…)` returned no provenance columns (`executor._final_projection`);
  it now always does.
- **National queries failed for per-state datasets.** `geography="BR"` raised
  NothingPublished for datasets published only per state (SIH-RD, CIHA).
  The planner now reads every state and reports the adaptation; datasets
  with a national file (SIM's DOBR, SINASC's DNBR) keep it.

**Result.**
- **Roles resolve live on AC.** SINASC 2022: 14,483 births, 17 missing
  mother's birth dates. SIH-RD 2023-01: 4,165 admissions, 0 missing. SIM
  2022: 4,159 deaths, 10 missing birth dates.
- **Declaring the categories fixed delivery type.** Infant-death link, AC
  2022: agreement rose from 46.5% to 97.6%; plurality agrees in 100%.
