## ADR-0244: A municipality's name is a fact with years, and a source's own spellings are declared in that source

**Date:** 2026-11-28. **Status:** active. Supersedes the `municipality_name_aliases` of f30096aa. **Request:** the
author's review of f30096aa ("the name aliases is a particularly concerning point"; abnc2027_neuro
`papers/TRIAL_t06b.md`, W8).

**Context.** A source that names a municipality instead of coding it (SENATRAN's fleet, SNGPC's sales) was placed by
IBGE's current names only (`municipalities.parquet`, from the Localidades API, which knows today). f30096aa added
`geography.yml`'s `municipality_name_aliases`: 43 names typed by hand, applied to every source and every year, mixing
three different things: a name IBGE itself used until some year (Embu, Parati), a source's own spelling that IBGE
never wrote ("BARAO D0 MONTE ALTO"), and a name cut at the source's column width. A code has a history in this
package (`legacy_places`, `municipalities_by_year`); a name had none. IBGE publishes the names: its yearly territorial
division (DTB) lists every municipality with its name for 1994, 2000 and each year from 2003.

**Decision.**
- `sources/ibge_dtb.py` reads each edition's municipalities (three layouts; counts checked: 4,974 in 1994, 5,571 in
  2025, each year equal to `municipalities_by_year`). `geography.build_municipality_names` compiles them into
  `resources/municipality_names.parquet` (`code7, name, first_year, last_year`; 5,630 names of 5,571 municipalities,
  59 with two), built by `pegasus-data geography`; `geography.municipality_names()` reads it.
- `geography.municipality_name_keys(aliases=, truncated=)` is the one rule that places a written name, in order:
  IBGE's current name; a name IBGE wrote in any edition, where it names one municipality of the state; the source's
  own `aliases`; the source's `truncated` width. A key two municipalities share places nothing.
- A source's own spellings are declared in its `place` (`intake.yml`), and an alias that IBGE's names already place is
  refused, so the list holds only what it must. `municipality_name_aliases` (the YAML list, the function, the schema
  key) is removed.
- A historical name is not bounded by the record's year: sources keep a name long after it changed (SENATRAN writes
  "EMBU" in 2024; IBGE changed it in 2012). The uniqueness rule is what guards it: no name in the 25 editions names
  two municipalities of one state.

**Consequences.** Of the 43 hand entries, 26 are IBGE's own former names and need no declaration, 2 are the
30-character cut, and 15 are SENATRAN's spellings, now under `senatran_fleet`. SENATRAN 2015 and 2024 re-landed in a
scratch home place the same 5,570 municipalities with identical cells (133,704) and the same 34 unallocated rows.
SNGPC, landed before the list existed, holds 627,552 industrialized rows (22 names, of 528,478,139) and 7,905
compounded rows (2 names) that name a municipality and are unallocated in the home; the name history places all 24
names. They take effect when SNGPC is next landed (not done here: 540 million rows).
