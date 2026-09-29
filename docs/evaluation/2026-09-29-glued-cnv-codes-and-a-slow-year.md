## 2026-09-29 — 43,916 `.CNV` codes glued to their labels, and a year that took four minutes

**Question.** A live query of the open-data APAC for fistula creation read
discharge reason `15 (?)` and attendance character `06 (?)`, although both are
in the SIA kit. It took 259 s for one year of a small dataset. Why, on both
counts, and how far does each defect reach?

**Regime.**
- Branch `redesign`: `14d9a28` before, `588a3de` after.
- Maintainer home `pegasus_data_home` for the kit re-parse; live home
  `~/pegasus_live/home` for the timings.
- Date 2026-09-29.

**What was counted, and why.**
- **The `.CNV` re-parse.** Every `.CNV` member of every TabWin kit in the
  catalog was parsed with the old and the new parser, and each category line
  whose codes changed was counted. A changed line is a code the dictionary
  held wrongly: it could never match a record.
  - Scenario: `scratchpad/cnv_diff.py`, whose method is in this entry.
  - Artifact: `data/probes/cnv_abutting_codes.json`.
- **Wall clock.** `query("SIASUS-ACF", period="2023-01" | "2023")` was timed
  and profiled with cProfile. Wall clock for a person is a binding constraint
  (CLAUDE.md §3).

**Result: the kits.**
- **Scale.** 36 kits and 7,952 `.CNV` files; **43,916 category lines** had a
  code glued to label text, because the label filled its field and the parser
  wanted a space before the code column (ADR-0095).

| system | file | lines |
|---|---|---:|
| SIASUS | `CNESN<UF>`/`CNESC<UF>` (establishment names by state) | 38,191 |
| SIASUS | `PROC1199.CNV` (procedures, 1999 table) | 2,070 |
| SIM | `CBO2002.CNV` | 738 |
| SINASC | `ESTABEL.CNV`, `ESTAB06.CNV` | 1,352 |
| SINASC | `CBO2002.CNV` | 492 |
| SIM, SINASC, SINAN | `GRUPO4.CNV` | 708 |
| SIASUS | `MOTSAIPE`, `CARAT_AT`, `TIPOPRES`, `PROCSIA`, … | small |

- **Examples.** `MOTSAIPE.CNV` line 6 held code `PACIENT15`, and `CBO2002.CNV`
  held `(correios412115`.
- **Checks.**
  - Every change inspected took the code at the aligned column and dropped
    label text.
  - No line whose old code was clean changed.
  - The `medico02.CNV` overflow case still takes its own fallback.

**Result: time.**

| run | time | largest cost |
|---|---:|---|
| ACF 2023-01, before | 43 s | YAML parsing, 25 s |
| ACF 2023-01, after | 15 s | reference maps |
| ACF 2023 cached, before | 104 s | maps rebuilt 492×; per-row presentation |
| ACF 2023 cached, after | 16.7 s | per-group binding decisions |

Both warm runs return the same table (`Table.equals`).

**Consequences.**
- The parser is fixed. Re-ingestion now supersedes `.CNV` readings. Without
  that, the corrected codes would have been inserted beside the wrong ones.
- The maintainer dictionary is rebuilt (`data/logs/rebuild-cnv.ps1`).
- The render path was restructured (ADR-0097).
- A year is still not "seconds" (OQ row to follow if the remaining
  per-group selection resists).

**Also found on the way.**
- **Glued codes are not the whole gap.** `AP_TPATEN` `12` and `AP_TIPPRE` `00`
  are absent from every source, so they read `(?)`, correctly.
- **The ACF flags** hold S/N while the kit tabulates them with a 1/0 table;
  they now decode from the layout.
- **`query()` refused a whole year over one unreadable 5.9 KB file.** It
  hard-coded `allow_partial=False`, while the error told the caller to pass it.
- **A second shape of glued code.** After the rebuild, 87 dictionary codes still
  mixed prose and digits (`punção/biópsi020101` in SIASUS `FORMORGS`). There the
  label had run past the column as well. Splitting that last token when it ends
  in a code or range of the declared width recovers 129 more lines (SIASUS 124,
  SIHSUS 4, RESP 1; `data/probes/cnv_glued_tail.txt`), and ranges are kept whole.
- **The first rebuild's `reference` step crashed** (`rc-reference.log`):
  `view.clear_lookup_caches` still called `cache_clear` on functions the ADR-0097
  refactor had turned into cached wrappers. It is fixed and the step re-run
  (`data/logs/rebuild-cnv2.ps1`).
- **Supersession was itself slow.** One `LIKE` delete per `.CNV` member made
  re-reading the CIHA kit take 45 minutes. One indexed range read per kit
  replaced it; all 38 kits then re-read in 89 minutes, superseding 17,515,772
  rows.
- **What remains after both fixes** (catalog after `rebuild-cnv2`): 13 dictionary
  codes still mix prose and code.
  - 10 are alphanumeric ICD codes glued in SIM's TabWin groupings
    (`orgânicaR652` in `CID10_18`, `determinadaY175` in `CID10_20_ST`). SIM's
    cause fields decode through canonical ICD-10 (ADR-0087), not through these
    groupings.
  - 2 are in SISCAN `Adequabilidade.cnv`.
  - 1 is a FORMORGS line whose prose ends in a hyphen.

  The split is not widened to alphanumeric tails. A letter-and-digit code
  cannot be told from the prose around it as safely as a digit run of the
  declared width can.
