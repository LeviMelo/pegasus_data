# ADR-0198: A kit describes the data filed in its folder, and a column its form types a date is never decoded

**Date:** 2026-10-23. **Status:** active. **Amends:** ADR-0152 (a kit's window), ADR-0079 (a curated doc's word on whether a column is coded).

**Context.** The decode coverage on records (evaluation 2026-10-23) left 66 coded columns bare. Two causes were defects of the mechanism, not of one column:
- CIH's TabWin kit sits in `/CIH/200801_201012/Auxiliar/`, so `tabkit.kit_validity` gave its codelists the folder's window 200801-201012. DATASUS filed 869
  data files under that folder and the last month is 201104 (`CRSP1101` to `CRSP1104`, `file_facts` of the maintainer catalog), so no window covered 2011 and
  `labelpack.select_windows` labelled nothing: SEXO, GESTAO, MORTE, COBRANCA, NATUREZA and COD_IDADE of CIH-CR 2011 were bare, with their tables in the pack.
- SINAN's `TRATAMENTO` is the treatment's start date on visceral leishmaniasis and the type of entry on tuberculosis (TUBE `tp_entrada`, six codes in the
  harvested form dictionary). A variable doc is one per system and column, and it said `code_system: none`, which the renderer obeys before it looks at the form's
  own table; declaring it coded would have put "(?)" after every leishmaniasis date.

**Decision.**
- **A kit named by its folder, not its file, takes the folder's window widened to the first and last month of the data files under that folder**
  (`dictionary.settle_folder_windows`, run after `settle_era_windows` in every semantics run; `tabkit.kit_folder` says which kits). A kit named for its window
  (`TAB_SIH_199201-199712.zip`) is not touched. On the maintainer catalog it widens one kit (CIH, 200801-201012 to 200801-201104, 709,927 dictionary rows) and no other.
  The shipped pack is re-windowed the same way for its 199,831 CIH rows (a one-off edit of `valid_to`, checksum in `manifest.json` refreshed; the next
  `build_resources` reproduces it).
- **A column the family's own form dictionary types a date, with no code table, is never decoded**, whatever a system-wide doc says
  (`curation.form_types_a_date`, read by the renderer and by `field_decision`). Of 328 date-typed harvested fields none had a coded doc, so nothing changes
  today; it is what lets `TRATAMENTO` be declared coded for the forms whose dictionary prints a table.
- A series' harvested table does not outrank a system-wide `code_system: none` in general: of the 15 pairs where both exist, several are wrong (ESQU `AN_QUANT`
  is a number, SIFC `SIN_OUTR_E` free text). Each column is declared coded by its own entry.

**Consequences.** 22 columns gain labels (evaluation 2026-10-23, section "After the metadata pass"). The renderer reads one more lookup per column
(`harvested_field`, memoised with the curation). A future dated-folder kit whose data run past its name is widened with no curation row.
