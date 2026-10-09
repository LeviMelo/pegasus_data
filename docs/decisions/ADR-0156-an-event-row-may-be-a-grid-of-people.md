# ADR-0156: an event's row may be a grid of people by sex and age band

**Date:** 2026-10-09. **Status:** accepted. Resolves OQ-76.

**Context.** A SINAN-SDTA row is one foodborne outbreak. The form's field 32 counts its ill by sex and age band in
21 columns, and its field 29 (NU_TOT) counts every ill person. ADR-0155's weight is a single column. A grid needs more:
each of its cells is a different (sex, band). The dataset declared no event type (`event_types: []`), so PegaSUS
counted no foodborne illness.

**Decision.** A weight may be a `grid`, declared with its parts:
- `cells`: column, sex (male, female or null) and the band's lower edge (null when the age is unknown);
- `bands`: the lower edges;
- `total`: the row's count of every ill person;
- `margin`: the form's own sum of the grid.

`count_events` and `grid_events` read a grid row into rows by (`grid_sex`, `grid_age_band`).
- **Total beyond the grid.** The total's people beyond the grid are counted with sex and age unknown. In SDTA the grid
  covers the ill who were interviewed (field 28), not all the ill.
- **Blank cells.** A blank cell is never read as zero:
  - when it is the row's only blank, the margin solves it;
  - otherwise it holds no one in the grid, and any people it had fall to the total's unknown remainder.
- **No count at all.** A row with neither a grid nor a total is `unquantified`: an outbreak whose ill were not
  counted, never zero.
- **Grid above the total.** Where the grid exceeds the total, the grid counts.

**Declared.** SINAN-SDTA `case`, with bands 0, 1, 5, 10, 20 and 50.
- **Grid consistency.** Tested on the records (2010, 2015, 2019, 2023): in every row that fills the grid, each
  band's three sexes sum to the band's total, and each sex's bands sum to its total.
- **Single blanks.** 0 to 3 rows a year (2007–2024) leave a single cell blank, solved from NU_F_TOT.
- **The place.** ID_MUNI_RE is re-declared from "residence" to `outbreak.municipality` (where). The column is named
  RE and TabNet tabulates it as residence, but the dictionary's field 11 is the outbreak's municipality of
  occurrence.
- **Axes.** SDTA's own semantic axes give occurrence and onset.

**Consequences.**
- PegaSUS reads a grid event's strata from the grid. The place is the municipality of the entity the grid counts, and
  the block's age bands are those the population and the grid share (`gateway.age_edges(source, dataset)`).
- Per-record computations (marks, links) refuse a grid event.
- SDTA 2015–2023 assembles on 6 bands × 2 sexes, with 80,909 cases allocated. Visible gaps:
  - 14,408 cases of unknown sex;
  - 973 of unknown age;
  - 457 outbreaks never counted.
- The old aggregate recipe `sinan_sdta_municipality_month.yml` named columns SDTA does not have and the wrong
  disease; it is withdrawn.
