# IBGE's regions across 31 years of territorial divisions: no municipality ever moved

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`, after commit 0c93827;
- the membership pack `resources/geography.parquet` as committed (IBGE rows
  from the Localidades API, empty validity windows);
- IBGE's yearly division files (DTB) from
  `geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/`,
  downloaded 2026-10-03 to `sources/ibge_dtb/`.

**Script and artifact:** `scripts/ibge_dtb_vintages.py`, artifact
`data/probes/geography/ibge_dtb_vintages.json`.

**Why.** OQ-11: the IBGE rows are today's division, so a 1995 record rolled
up through them "is placed where it would be now". Whether that misplaces
anyone depends on whether the division changed. Counted here: for each
published year, the municipalities whose region code differs from today's.

**What IBGE publishes.**
- **Meso- and microregions:** 1994 (fixed-width text), 2000 (one row per
  level) and 2005–2022 (.xls). They are absent from the 2023 file on.
- **Immediate and intermediate regions:** 2019–2025.
- **Gaps:** 2001–2002 are not published. 2003–2004 list municipalities
  without regions.

**Result.**

| year | municipalities | region codes differing from today's |
|---|---|---|
| 1994 | 4,974 | 0 (meso, micro) |
| 2000 | 5,507 | 0 |
| 2005–2008 | 5,564 | 0 |
| 2009–2012 | 5,565 | 0 |
| 2013–2022 | 5,570 | 0 (all four from 2019) |
| 2023 | 5,570 | 0 (immediate, intermediate) |
| 2024–2025 | 5,571 | 0 |

- **No municipality ever left.** The 5,571 ever published are all in
  today's division.
- **The only change is new municipalities,** 4,974 to 5,571, each placed
  in a region from its first year. Comparable areas (IPEA AMC, ADR-0126)
  are what keep a series across those splits.
- **Names changed; codes did not.** 1994 is upper case without accents.

**Consequence.**
- **Today's IBGE division places every record of 1994–2025 in the region it
  was published under.** The empty windows are correct as they are, and no
  year-by-year copy was added: it would duplicate the same answers.
- **OQ-11 is resolved for IBGE's classifications.** DATASUS's own tables
  (health regions per system) carry their kits' windows where the kits
  have them. Their vintage question is part of the TabNet comparison,
  ADR-0129.
