# Catch-all ranges: which observed codes a TabWin residual range was decoding

**Date:** 2026-09-30. **Regime:** branch `linkage`, fresh home `~/pegasus_fresh`,
the 16+ slices of `scripts/sweep_undecoded.py`. Script: `scripts/catchall_audit.py`.
Artifact: `data/probes/catchall_audit.json`.

**Why this count.** A code that reads as decoded while no document names it
is worse than a code that reads `(?)`: it is invisible downstream (CLAUDE.md
§1). The label pack holds 17,184 range rows with a residual label in 140
code lists (ADR-0108). The question is which of them decode codes that
actually occur.

**Method.** For every coded column in each slice, a code is counted when:
- no bound table lists it individually;
- its rendered label is a residual word (ignorado, outros, não se aplica,
  não informado, demais, sem informação, inválido, em branco);
- it falls inside a residual range;
- it is not all 9s.

The first version compared ranges without the rendered label and flagged SIH
`SEXO` 3 (2,715 rows), which a higher-priority table decodes as "Feminino"
through its own range. The rendered label is the test that matters.

**Counted.**

| slice | column | code | rows | range | verdict |
|---|---|---|---|---|---|
| SINASC AC 2022 | `LOCNASC` | 5 | 369 | 5–9 "Ignorado" | **wrong label**: the 2019 structure says *Aldeia indígena*; fixed (ADR-0108 amended). Brazil 2022: 1,966 births |
| CNES-PF AC | `UFMUNRES` | 000000 | 19,175 | 000000–009999 "Ignorado ou exterior" | kept: all-zero residence is the conventional unknown |

**Findings.**
- In these slices the catch-all ranges hide one real code, and it was a
  mislabel of indigenous-village births: a place people are born, read as
  "Ignorado".
- The audit covers only codes that occur in one slice per dataset. The
  wider question of each code list's residual ranges stays under ADR-0108;
  the script is the tool to run on more slices.
