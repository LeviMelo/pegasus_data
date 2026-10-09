# ADR-0158: a variable spread over columns is a grid of named axes

**Date:** 2026-10-09. **Status:** accepted. Revises ADR-0156 (where a weight grid's cells are declared).

**Context.** Some forms put one variable in many columns, and each column's name carries its codes:
- SINAN-SDTA counts an outbreak's ill by sex × age band in 21 columns;
- CNES-ST flags attendance type × payer (AP##CV##, 49 columns), management by programme × manager (GESPRG#E/#M), and
  rooms and beds by installation (QTINST##, QTLEIT##), each spread from an SCNES table (LFCES006, 007, 015).

ADR-0156 declared SDTA's cells inside its event's weight. A second declaration for CNES-ST's flags would be a second
mechanism for one thing.

**Decision.**
- **Declaring a grid.** A role file declares `grids:`. Each grid has a value (count, flag), named axes with their code
  tables, and cells: a declared column and one code per axis. Every cell is a distinct combination.
- **Reading a grid.** `pegasus_data.grids(dataset)` lists a dataset's grids. `grid_table(dataset, name, period,
  geography, keep)` reads one long: one row per (record, cell), the axes' codes, and the cell's raw value.
- **Events counted from a grid.** An event weight names its grid and says which axes are sex and age: `{grid: ill,
  sex: {axis, male, female}, age: {axis, unknown}, total, margin}`. A sex code it does not name is unknown; an age
  code is the band's lower edge, unless the weight names it unknown.
- **What was declared.**
  - SDTA's `ill`: 21 cells; its counts are unchanged (2023: 19,879, 2,404 of unknown sex, 106 outbreaks never counted).
  - CNES-ST's `attendance`: 7 × 7 codes, 49 cells.
  - CNES-ST's `management`: 6 programmes × state or municipal, 12 cells. Programme 3 is named only by its code; the
    layout gives CODPROG no table.
  - CNES-ST's `installations`: 40 installations × rooms or beds, 52 cells.

**Consequences.** Acre's CNES-ST of 2023-01 reads long as 62,622 rows by establishment, attendance type and payer.
