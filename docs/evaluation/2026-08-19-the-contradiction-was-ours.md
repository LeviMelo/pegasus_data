## 2026-08-19 — 311,844 codelist contradictions, all manufactured

*Split from docs/history/FINDINGS.md §3e on 2026-09-28; text unchanged.*

## 3e. The contradiction was ours (2026-08-19)

### 311,844 contradictions, all manufactured

Sweeping every bound codelist for self-contradiction — a code carrying more than
one label — measured **311,844 (code, window) pairs across 264 codelists**.
Grouped by system as well as by codelist: **zero**. Every single one was created
here, not shipped by DATASUS.

Reference tables were keyed on the codelist name alone. Thirteen systems ship a
file called `SEXO.CNV` and they do not agree — SIHSUS codes sex `1`/`3`, SINASC
`1`/`2`, SINAN `M`/`F` — so all thirteen were merged into one table in which `1`
meant Masculino *and* Feminino. `ANO` is shipped by 15 systems, `MUNICBR` by 11.
Reference tables are now scoped by system, and a field decodes against its own
system's copy.

A second class was cross-**vintage**: reading with no year merged every validity
window, and SIHSUS renders `C96.7` as "…tec linf hematop e relac" today and "…e
corr" in the 1992–1997 kit. That is one code whose label was reworded, not two
meanings. A read with no year now returns the current vintage.

SIHSUS/RD went from sixty warnings to **zero**: `SEXO` renders as *Feminino*,
`MUNIC_RES` as *120020 Cruzeiro do Sul*, `DIAG_PRINC` with its label.

### The damage was never written to disk

The important question was not whether the code was fixed but whether wrong
labels had already reached Parquet, where no test would find them and a consumer
would read them as fact.

They had not. Every stored `*_label` value in every built partition was compared
against the labels its field's own binding allows, scoped to that partition's
system: **149 values checked, 0 contradicting, 0 unverifiable**. The build
normalises through a system-scoped dictionary cache and never had the merge bug —
it was introduced later, in the read path only, and lived for hours in one
working tree. Stored `SEXO` labels read `1 → Masculino, 3 → Feminino`, which is
SIH's correct coding and an independent cross-check of the render fix.

This is now a standing verify assertion rather than a one-off audit. The loose
form of it — matching a code against every codelist in the system — produces
false alarms, because `4` means one thing in `FINANC` and another in `REGIAO`;
the check scopes to the field's own binding.
