## 2026-08-19 — Classification changes, not data going bad (CID-9/CID-10)

*Split from docs/history/FINDINGS.md §3f on 2026-09-28; text unchanged.*

## 3f. Classification changes, not data going bad (2026-08-19)

### SIM: CID-9 and CID-10 overlap on the tree

The instruction proposed a 1996 boundary. Measured, a year boundary is wrong:
`SIM/CID9` spans **1979–1998** and `SIM/CID10` spans **1996–2024**, so the two
overlap for three years and any threshold mis-assigns them.

Both classifications are bound instead, which resolves it per row rather than per
year. That is safe because the code spaces are disjoint — SIM's 9,740 CID-9 codes
and 14,198 CID-10 codes share **exactly zero** codes, CID-9 being numeric and
CID-10 letter-prefixed — so exact matching selects the right classification
without anything needing to know a row's vintage. Recorded as `vintage_note` in
the variable dictionary, which is now a first-class field.

### SIH: the same, in a different shape

The same applies to SIHSUS and nobody had noticed, because its CID-9 era does not
look like SIM's. **426 of the 1,590 distinct `DIAG_PRINC` values are 6-digit
numeric**, and they are CID-9: `065099` decodes to "650 - Parto normal". The kit
ships CID-9 as **seventeen chapter files** rather than one table, so all
seventeen are bound alongside `CID10`. Safe on the same grounds: 7,681 codes
across the seventeen chapters with **zero** contradicting labels, and zero
overlap with CID-10.

### Presence in a bound table now outranks shape

Finding SIH's 6-digit form changed the rule. A shape regex is a heuristic and a
narrow one — SIM writes CID-9 as three or four digits, SIH as six — and no
pattern should have to know that. If a codelist bound to the column decodes the
token, the token is valid. That is proof; the regex is inference.

### ATESTADO mixes two separators

`T07/X366*Y96` — one cell, both `/` and `*`. Splitting on the heavier one leaves
the other inside a token, and the whole value then fails every check. A token
rule may now name a *set* of separators.

### The measurement, before and after

| column | malformed before | after |
|---|---|---|
| `SIM.CAUSABAS` | 386 (7.7%) | **0** |
| `SIHSUS.DIAG_PRINC` | 552 (11.0%) | **0** |
| `SIM.ATESTADO` | 2,526 → 486 | **283 (8.8%)** |
| `SIM.LINHAA–LINHAD` | 3 | 3 (0.06%) |

Across all 23 ICD-bound columns: **913 of 53,156 values malformed (1.72%)**.

`IBGE.IDADE` still reports 619 malformed and should: it holds age bands like
`2559` and is bound to CID10 only because a distributional detector matched on
shape. That is the false binding already recorded as an open question, and
leaving it visible is the point.
