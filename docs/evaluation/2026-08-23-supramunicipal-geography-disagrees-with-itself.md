## 2026-08-23 — DATASUS publishes supramunicipal geography, and disagrees with itself

*Split from docs/history/FINDINGS.md §3n (second) on 2026-09-28; text unchanged.*

## 3n. DATASUS publishes supramunicipal geography, and disagrees with itself (2026-08-23)

### Every national classification was already shipping

`normalize/geo.py` canonicalises a municipality — six digits to seven, check
digit, UF — and stops. "Which health region is this municipality in" had no
answer, and it is the question almost every roll-up asks.

The answer was already in the label pack. DATASUS publishes each supramunicipal
classification as an ordinary `.CNV` codelist keyed on the six-digit
municipality code. 139 national municipality-keyed codelists ship. Among them:

| classification | codelist | municipalities | members |
|---|---|---:|---:|
| health region (CIR) | `CIRBRN` | 5,680 | 478 |
| IBGE microregion | `MICROBR` | 5,697 | 586 |
| IBGE mesoregion | `MESOBR` | 5,632 | 165 |
| colegiado de gestão | `CSAUDBR` | 5,417 | 303 |
| metropolitan region | `BR_REGMETR` | 1,325 | 95 |
| PNDR region | `BR_PNDR` | 1,126 | 14 |

**`CIRBRN` is the national health-region table.** `CIRAC` — the 24-row Acre table
that labelled Rio Branco "Baixo Acre e Purus" and cost this project days (§3k) —
is one state's slice of that same classification. The fix compiles to 98,584 rows
in a **140 KB** artifact.

Note what that resolves: Rio Branco's health region genuinely *is* "Baixo Acre e
Purus". It was never wrong as a region, only as a municipality's name. It is now
reachable under its own name, deliberately, which is what the rollup guard was
groping toward.

### The compile is deterministic only when scoped by publishing system

Grouped by municipality alone these tables look self-contradictory. Add the
validity window and the publishing system and every contradiction vanishes:

| scoping | CIRBRN | RSAUDBR | MSAUDBR | MICROBR | MESOBR |
|---|---:|---:|---:|---:|---:|
| municipality only | 295 | 2,612 | 951 | 50 | 50 |
| + validity window | 295 | 2,612 | 951 | 50 | 50 |
| + **system** + window | **0** | **0** | **0** | **0** | **0** |

The same lesson as §3e: most apparent contradiction was manufactured by the
comparison. The window alone resolves nothing — it is the *system* that carries
the disagreement.

### What survives the scoping splits in two, and only one half is real

**Encoding variance.** `CIRBRN` differs on 295 municipalities but the region
*name* differs on only **46**. The other 249 are the same region under a
different code width — `420005 → SIM:42008 | SINASC:4208`, both "SC Meio Oeste" —
or an accent, `Xanxerê` vs `Xanxere`.

**Two schemes under one codelist name.** `RSAUDBR` differs on 2,612 and the name
differs on **1,944**:

```
130002 -> CIH:1306 "DIRES 6" | SIASUS:1302 "Triângulo"
          SIHSUS:1302 "Triângulo" | SINASC:1306 "DIRES 6"
```

That is not a disagreement about where a municipality is. It is **two different
regionalisations published under one name** — CIH and SINASC on the older DIRES
scheme, SIA and SIH on the named-region scheme. `MSAUDBR` has it on 858 and
`BR_DIVADM` on 2,979.

**Consequence:** a supramunicipal roll-up is not system-neutral. An aggregate
over SIH must roll up through SIH's regionalisation or its totals will not
reconcile with DATASUS's own TabNet output for the same query. The compiled pack
is therefore keyed `(municipality, classification, system, window)`, and the 46
residual health-region conflicts are reported to the caller rather than resolved
by picking.

### Health macroregion is an honest gap

A municipality does belong to a health macroregion. **No shipped table says which
one without contradicting itself**: `BR_MACSAUD` conflicts on 66% of
municipalities (and 220 of its rows carry no member code at all), `MSAUDBR` on
4%. Neither is compiled. `curation/geography.yml` records both exclusions with
their measurements, because "we ship no macroregion mapping" is a finding and
picking one system's answer for two-thirds of Brazil is not.

### Sentinels are members

`999999 → Ignorado/Exterior` and `120000 → Município ignorado - AC` are kept.
Folding them into a real municipality is the §3k error; dropping them biases
every count, because the rows carrying those codes do not disappear from the
data.

### The same defect was live in `joins.yml`, in relation form

Found while building the above, not by looking for it. `curation/joins.yml`
declared:

```yaml
  field: MUNIC_RES
  relation: rollup_to
  target_name: health_region
  artifact: CIRAC        # <- Acre's 24 rows, as the NATIONAL roll-up
```

`_apply_dimensions` loads `relation.artifact` directly, so
`query("SIH-RD", dimensions=["MUNIC_RES.health_region"])` decoded municipality
codes with a 24-row Acre table. Measured:

| capital | under `CIRAC` | under `CIRBRN` |
|---|---|---|
| São Paulo `355030` | *not covered* | 35054 SP São Paulo |
| Rio de Janeiro `330455` | *not covered* | 33005 RJ Metropolitana I |
| Fortaleza `230440` | *not covered* | 23001 CE 1ª Região Fortaleza |
| Belo Horizonte `310620` | *not covered* | 31008 MG Belo Horizonte… |
| Rio Branco `120040` | 12002 Baixo Acre e Purus | 12002 AC Baixo Acre e Purus |

Every roll-up outside Acre returned nothing, and nothing said so.

This is §3k exactly — the per-UF form of a classification that also exists
nationally — surviving in a layer built after that fix, because the fix was
applied to curated `codelist` declarations and this is a `relations` entry.
Changed to `CIRBRN`, and
`test_every_declared_rollup_artifact_spans_many_states` now refuses any
municipality-keyed roll-up whose table covers fewer than 20 states, so the shape
cannot be reintroduced anywhere in `joins.yml`.
