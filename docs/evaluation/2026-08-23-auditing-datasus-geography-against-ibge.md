## 2026-08-23 — Auditing DATASUS geography against IBGE

*Split from docs/history/FINDINGS.md §3p (second) on 2026-09-28; text unchanged.*

## 3p. Auditing DATASUS geography against IBGE (2026-08-23)

Full account in `docs/IBGE_LOCALIDADES.md`. The findings that belong in the
project's knowledge repository:

### The publication year is not the record year — 7.44%, measured

The SIH file published under **year 2022** for Acre contains **3,687 admissions
(7.44%) that happened in 2021**, the earliest in February 2021.

| column | means | years inside the "2022" file |
|---|---|---|
| `ANO_CMPT`/`MES_CMPT` | billing competence | 2022 only |
| `DT_INTER` | when the patient went in | **2021: 3,687** · 2022: 45,860 |
| `DT_SAIDA` | discharge | 2021: 3,100 · 2022: 46,447 |

An admission in December is billed in January, so the lag is structural, not
noise. **Never infer record time from the publication coordinate.** A series by
admission date requires reading `DT_INTER` AND fetching the neighbouring
publication years, or the edges are silently short.

### Comparing labels instead of partitions manufactures disagreement — again

`MESOBR` against IBGE's mesorregião agrees on **14.3% of labels**. That number is
worthless. `.CNV` labels are width-limited, so DATASUS writes `Leste RO` for
`Leste Rondoniense`.

Compared as **partitions** — which municipalities group together, regardless of
the group's name:

| | DATASUS groups | IBGE groups | split by IBGE | split by DATASUS |
|---|---:|---:|---:|---:|
| `MICROBR` vs microrregião | 558 | 558 | **0** | **0** |
| `MESOBR` vs mesorregião | 139 | 137 | **0** | 2 |

`MICROBR` **is** IBGE's classification, exactly. `MESOBR` differs only because
DATASUS files three municipalities (`431936`, `432146`, `510619`) under
"Ignorado" where IBGE knows the answer.

This is the third time this project has been caught by it — §3e (311,844
manufactured contradictions), §3n (295 municipality conflicts that were code-width
variants), and now this. **The rule: when two sources look like they disagree,
compare the structure before the strings.**

### DATASUS's geography is built on a classification IBGE retired in 2017

IBGE replaced mesorregiões and microrregiões with **Regiões Geográficas
Imediatas** (510) and **Intermediárias** (133). Neither appears in any of the
2,348 codelists the label pack ships. Every DATASUS roll-up above the
municipality uses a nine-year-deprecated classification.

The legacy ones stay — thirty years of health data is tabulated against them —
but the current pair now ship alongside, from IBGE.

### Municipality coverage was nearly fine, and I reported it wrongly first

Only **three** IBGE municipalities are absent from `BR_MUNICIPALFA`, and two are
explicable (Brasília is covered by a range row; Pinto Bandeira exists under an
older code). Boa Esperança do Norte was created in 2021 and not yet installed.

An earlier pass of this audit reported *"Pescaria Brava (420547) appears in zero
codelists"* as a headline. **The code was wrong** — it is `4212650` → `421265` —
and the municipality is present. The finding was an artifact of a misremembered
code checked against nothing. Recorded because the failure mode is the one this
project keeps repeating: a confident claim resting on an unverified premise.

### What each institution actually owns

IBGE has **no health regions**. The *Região de Saúde*, the *colegiado* and the
health macroregion are Ministry of Health constructs with no IBGE equivalent and
no crosswalk. That is why the outcome is a supplement rather than a replacement:
IBGE for territorial identity, DATASUS for the health-service geography it
invented, and an `authority` column on every membership so a caller can see which
institution answered.

### Datasets inside a system share their axes — 5 to 90 in two edits

`semantic_axes` (which column carries the municipality, which carries the date,
and what each role IS) existed for **5 of 132** datasets, which made the
aggregate layer look general and was not.

The leverage is that DATASUS datasets are not independent. All **58 SINAN
agravos** carry the same notification block, so `ID_MN_RESI` is the municipality
of residence in every one; SIH's datasets are all views of an AIH; CIHA's rows
all carry the same `MUNIC_RES`/`MUNIC_MOV` pair. A file-level `shared:` for SINAN plus a
`shared_by_system:` block covering fourteen systems took coverage to **125 of
132**, and the seven left out are each left out for a stated reason: five are
not datasets (TABWIN is a Windows application), `IBGE.PROJUF` is projected by
state, and `PCE.PCE` uses a 12-character composite geocode.

**Saying "none" is a different claim from saying nothing.** `IBGE.PROJUF` shares
a system with five municipality-keyed files. Staying silent would have given it
their `MUNCOD` and keyed its cells on something no municipality table resolves —
every roll-up unmapped, every total a subset. So inheritance tests for the key's
PRESENCE, and `semantic_axes: {}` is an explicit opt-out.

**Grain must NOT inherit, and that is the load-bearing part.** CNES's 13 datasets
share `CODUFMUN` and have *different* grains — establishment-month,
professional-establishment-month, establishment-bed type-month. Inheriting grain
would make `COUNT(*)` mean one thing across them, which is the assumption §14.15
exists to refuse.

What is **not** derivable is the ROLE. Nothing in the bytes says `MUNIC_RES` is
where the patient lives and `MUNIC_MOV` is where they were treated. The columns
themselves are already identifiable from their curated codelist binding; only the
naming is an assertion.

A declared field that does not exist yields an aggregate with **no rows and no
error** — the phantom-codelist failure of §3k wearing another costume. So
`tests/test_semantic_axes.py` checks every declared field against curation, and
caught one immediately: `DTREGISTRO`, invented for SIM, where the column is
`DATAREG`.

### Still unresolved

* No health macroregion ships. `BR_MACSAUD` conflicts on 66% of municipalities,
  `MSAUDBR` on 4%, IBGE has none.
* IBGE's endpoint returns **today's** division. A 1995 record rolled up through
  it is placed where it would be now. Validity windows are left empty to say the
  vintage is unknown rather than asserting timelessness; IBGE publishes historical
  divisions and wiring them in is the next step.
