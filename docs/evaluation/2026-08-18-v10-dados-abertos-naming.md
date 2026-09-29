## 2026-08-18 — V10: Dados_Abertos has no new naming grammar

*Split from docs/history/FINDINGS.md §1 V10 on 2026-09-28; text unchanged.*

### V10 — `Dados_Abertos` naming grammar · **resolved: there is no new grammar**

The brief attributes 82 `DADOS_ABERTOS_UNPARSED_*` families to descriptive filenames. Measured,
the subtree's filenames are overwhelmingly *classic*: `DENGBR20.csv.zip`, `LEPTBR07.json.zip`,
`CHAGBR15.xml.zip` — prefix, geo, year.

What defeated the prior parser was the **composite suffix**. Its `strip_composite_suffix` handled
`.csv.gz` but not `.csv.zip`, so the stem became `DENGBR20.csv`, which matches no pattern. These
files are therefore not a new naming problem but *more of D3*: the same SINAN series republished
in three containers, which collapse into single families once parsed.

A genuinely descriptive tail does exist — `apac_atd.duck.zip`, `siasus_pa_ac.duck`,
`base_aih1.duck` — and gets its own grammar (`descriptive`, `descriptive_uf`).
