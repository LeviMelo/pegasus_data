## ADR-0243: A spreadsheet is read as text cells by one reader

**Date:** 2026-11-28. **Status:** active. **Request:** the author's review of f30096aa (abnc2027_neuro
`papers/TRIAL_t06b.md`, W7): "replace, never build beside" (CLAUDE.md §4).

**Context.** Six places read a spreadsheet, each with its own idea of where the header is and what a cell is:
`intake._excel_to_parquet` (pandas, the header found by a regex), `sources/anac_air.py`, `sources/census_commuting.py`,
`sources/ibge_links.py` and `proximity.py` (each its own `read_excel` with a fixed row), and
`scripts/ibge_dtb_vintages.py` (`xlrd` directly, with its own cell-to-text). The next source to read a workbook
(IBGE's yearly division, ADR-0244) would have been the seventh.

**Decision.** `decode/spreadsheet.py` is the reader of a sheet: `sheets(source, sheet)` gives every cell as the text
it shows (a whole number filed as a float loses its `.0`, an empty cell is None; typing stays with the caller's
declaration); `read_table(source, header=, sheet=, names=, stop=)` finds the one table by what its header's first
cell says, never by a row number, and returns its names, its rows and the sheet's cells (for a total printed above
the header). None or several sheets with such a header is an error that says what was found. `intake`,
`sources.ibge_dtb` and the DTB probe script read through it; `intake._cell_text` and the script's `xlrd` code are
removed.

**Consequences.** `tests/test_intake_excel.py` passes unchanged (12); SENATRAN 2015 and 2024 re-landed in a scratch
home equal the home's rows cell for cell (133,704 municipality-months); the probe script writes the same JSON. Still
open, recorded in ARCHITECTURE §5: the four older source modules keep their own `read_excel` until each is moved
with its source re-landed and its totals compared.
