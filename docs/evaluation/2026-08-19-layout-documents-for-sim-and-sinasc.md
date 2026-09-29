## 2026-08-19 — Layout documents exist for SIM and SINASC, in a different dialect

*Split from docs/history/FINDINGS.md §3d on 2026-09-28; text unchanged.*

### Layout documents exist for SIM and SINASC, in a different dialect

The harvester only knew the `IT_*` dialect, so `Estrutura_do_SIM_2025.pdf` and
`Estrutura_SINASC_para_CD.pdf` — both sitting on the tree — yielded nothing. Adding the `Estrutura_*`
dialect took layout coverage from 163 field descriptions across 5 documents to **331 across 8**.

The extraction needed three passes to be trustworthy, and the failure is worth recording: those
tables number their rows with exactly the syntax a value list uses (`4- Naturalidade`), so the loose
value-line rule was reading the document's own row counter and attributing it to whichever field
came last. SIM's causal-chain fields were being told they had a code `40` meaning "Causas da". Fixed
by detecting the dialect and taking values only from the valid-values cell, where the shape can be
checked: at least two distinct codes, numeric runs starting at 0 or 1.
