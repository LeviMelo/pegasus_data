# The aggregate layer — reconciled design

**Status:** design, reconciled against the tree at `b294c6f`. `REQUEST.md` is a
requirements synthesis written without access to the codebase; this document is
what survives contact with it.

**One-line answer to the request:** the aggregate layer is a much *smaller*
extension than `REQUEST.md` assumes, because four of the six things it asks to be
designed already exist and one of the remaining two is a compile job rather than
a sourcing job. What is genuinely missing is **measures, the build, and the
artifact**.

---

> **The mathematics behind this document is in
> [`AGGREGATE_ALGEBRA.md`](AGGREGATE_ALGEBRA.md)** — why an aggregate is a map
> into a commutative monoid, why roll-up is pushforward along a map of key
> spaces, and why every failure mode is one of those two structures breaking.
> Read it first if you want the rules to be derivable rather than memorised.

## 1. The premise, measured

`REQUEST.md` asserts the frontend must not aggregate microdata at request time.
That is correct, and it is now a measurement rather than an intuition:

| measurement | value |
|---|---|
| `fetch("SIH-RD", uf="AC", years=2022)` | **130 s** for 49,547 admissions × 113 columns |
| the same rows at municipality × month × sex | **989 cells** |
| compression | **50×** (419× at municipality alone) |

Acre is ~0.4% of national SIH volume. A frontend that hits microdata pays two
minutes for one state-year of the *smallest* state. The artifact is the right
shape, and 50× is the number that justifies it.

**The corollary matters as much:** compression is what makes the artifact worth
building, and dimensionality destroys compression. `DIAG_PRINC` has ~14,000 ICD
codes. Adding it to the same artifact as sex × age multiplies cells by ~10³ and
the artifact stops being smaller than the microdata. This is the empirical basis
for §6's layout decision, and it is why **there must not be one universal cube**.

---

## 2. What already exists — consume, do not rebuild

This is the core reconciliation. `REQUEST.md` asks for six things; four are built.

### 2.1 The semantic axis model — **built, and deliberately left for this**

`REQUEST.md` §"Do not hard-code residence/occurrence" asks for a named binding
from observational grain to dimension, rather than a `spatial_role` enum.

That shipped. `curation/datasets/core.yml`:

```yaml
semantic_axes:
  default_time: competence
  time:
    competence: {fields: [ANO_CMPT, MES_CMPT], encoding: year_month}
    admission:  {fields: [DT_INTER],           encoding: date}
    discharge:  {fields: [DT_SAIDA],           encoding: date}
  default_geography: residence
  geography:
    residence: {fields: [MUNIC_RES], code_system: ibge_municipality}
    facility:  {fields: [MUNIC_MOV], code_system: ibge_municipality}
```

Named, multi-valued, with declared defaults and encodings — exactly the model
requested. It has **no code consumer today**, and that is on purpose.
`FINDINGS.md` §3l records why:

> The old `time_by`, `geography_by` and `unresolved_time` query switches were
> removed. Their semantic knowledge remains under `semantic_axes` in curation for
> `describe()`, documentation and **future opt-in analytical helpers**.

The aggregate layer is that helper. **It should be the first consumer of
`semantic_axes`.** Introducing a parallel binding vocabulary would recreate the
exact duplication that removal was meant to end.

### 2.2 Typed semantic relations — **built**

`semantics/relations.py` + `curation/joins.yml` already provide
`RelationType.{label_of, rollup_to, attribute_of, crosswalk_to}`, persisted in
`semantic_relations` with validity windows, an adjudication queue, and
overlap validation.

`rollup_to` is precisely the edge a geographic roll-up must traverse, and the
distinction it draws — a roll-up is *not* a label, it deliberately changes
granularity — is the distinction that took a multi-day defect to learn
(`FINDINGS.md` §3k). Roll-up must go through this, not through a new hierarchy.

**Gap:** only ~6 relations are seeded. Population is mostly derivable from the
curated `codelist`/`codelists` declarations.

### 2.3 The summability rule — **built**

`ledger.aggregation ∈ {additive, mean, non_summable}`, derived from semantic type
and from TabNet's own `incremento` declaration — the Ministry stating which of
its variables it sums. Its docstring already states the rule `REQUEST.md`
restates:

> counts may be summed across cells and rates may not — the rate of two
> municipalities combined is not the mean of their rates, it is the summed
> numerator over the summed denominator.

The measure algebra must **read** this and refuse illegal reducers. It is the
existing guard, already populated.

### 2.4 Versioned artifact machinery — **built**

`_resources.py` (`ResourceRecord`, `ResourceStatus`, content version, sha256),
`ResourceManager`, `resources/manifest.json`, and build fingerprints on lake
partitions. `REQUEST.md`'s "aggregate image" hash is this machinery with a
different input list.

### 2.5 `rows_per_key` — **built, and is half of the grain problem**

`joins.yml` already carries `rows_per_key: one | many | unmeasured` per dataset
member, with the exact warning `REQUEST.md` raises:

> SIH.RD is one row per AIH and SIH.SP is many, so joining them and counting rows
> counts professional acts while looking like it counts admissions.

---

## 3. What is missing

1. **Measures.** Nothing anywhere declares a measure. This is the real gap.
2. **The aggregate build and the artifact.** No catalog table, no writer, no spec.
3. **A geography membership graph.** See §4 — a compile, not a sourcing job.
4. **Machine-readable grain.** `unit_of_analysis` is prose (§5).

---

## 4. Geography: compile, do not source

`REQUEST.md` says the code "appears to derive canonical municipality IBGE7 and
UF, but not the full set of geographic memberships", and asks for them to be
sourced and stored.

Correct about `normalize/geo.py`, which does IBGE6↔7 and UF only. **Wrong about
what is needed.** Every national classification is already in the shipped label
pack, keyed on the 6-digit municipality code. Measured:

| classification | codelist | municipalities | members |
|---|---|---:|---:|
| health region (CIR) | `CIRBRC` / `CIRBRN` | 5,681 | **467** |
| regional de saúde | `RSAUDBR` | 5,701 | 647 (but see §4.1) |
| health macroregion | `BR_MACSAUD` | 5,582 | 287 |
| health colegiado | `CSAUDBR` | 5,417 | 315 |
| IBGE microregion | `MICROBR` | 5,697 | 591 |
| IBGE mesoregion | `MESOBR` | 5,632 | 165 |
| administrative division (DRS) | `BR_DIVADM` | 5,613 | 448 |
| metropolitan region | `RMETRBR` / `BR_REGMETR` | 841 / 1,325 | 116 / 96 |
| PNDR region | `BR_PNDR` | 1,126 | 14 |
| territórios da cidadania | `BR_TERRCID` | 1,854 | 120 |
| agglomeration | `AGLBR` | 478 | 56 |
| capital / extreme poverty | `BR_CAPITAL` / `BR_EXTRPOBREZ` | 30 / 1,562 | 26 / 1 |

139 national municipality-keyed codelists ship in total.

**`CIRBRC` is the national health-region table.** `CIRAC` — the 24-row Acre
table that produced "Baixo Acre e Purus" — is one state's slice of the same
classification. The thing that caused the worst defect in this project's history
is the *per-UF* form of a table that also exists nationally.

So the deliverable is a compiled reference, not new acquisition:

```
geography.parquet
  municipality_ibge6, municipality_ibge7, classification, member_code,
  member_label, source_codelist, valid_from, valid_to
```

~5,600 municipalities × ~12 classifications ≈ **70k rows**, well under 1 MB —
the same "large maintainer state compiles to a small runtime artifact" pattern
the previous brief established. `geo.memberships(code, vintage)` is the right
shape for the accessor.

### 4.1 But the classifications are system-scoped, and two of them disagree

Measured after the table above, and it changes the design. Grouping only by
municipality, these codelists look self-contradictory — `RSAUDBR` maps 2,612
municipalities to more than one region. That apparent contradiction is mostly
manufactured, in the same way as `FINDINGS.md` §3e's 311,844:

| scoping | CIRBRN | RSAUDBR | MSAUDBR | MICROBR | MESOBR |
|---|---:|---:|---:|---:|---:|
| municipality only | 295 | 2,612 | 951 | 50 | 50 |
| + validity window | 295 | 2,612 | 951 | 50 | 50 |
| + **system** + window | **0** | **0** | **0** | **0** | **0** |

So the mapping is deterministic **only when scoped by publishing system**, and
the label pack's existing precedence rule — a system-specific row beats a
`system IS NULL` row — resolves most of the rest.

What survives that is real, and splits in two:

**Encoding variance, not disagreement.** `CIRBRN` differs on 295 municipalities,
but on only **46** does the region *name* differ. The other 249 are the same
region under a different code width: `420005 → SIM:42008 | SINASC:4208`, both
"SC Meio Oeste". Same for accents — `Xanxerê` vs `Xanxere`.

**Two schemes under one codelist name.** `RSAUDBR` differs on 2,612 and the name
differs on **1,944**:

```
130002 -> CIH:1306 "DIRES 6" | SIASUS:1302 "Triângulo" | SIHSUS:1302 "Triângulo" | SINASC:1306 "DIRES 6"
```

That is not a disagreement about which region a municipality is in. It is **two
different regionalisations published under one codelist name** — CIH/SINASC on
the older DIRES scheme, SIA/SIH on the named-region scheme. `MSAUDBR` has the
same problem on 858.

**Consequences for the design:**

- **`CIRBRN` is the health-region classification to use.** 5,680 municipalities,
  467 members, and genuine cross-system disagreement on **0.8%** of them.
- **`RSAUDBR` and `MSAUDBR` must not be compiled as single classifications.**
  Either scope them per system or leave them out; collapsing them invents a
  regionalisation nobody publishes.
- **The reference is keyed `(municipality, classification, system, window)`**,
  not by municipality alone. `REQUEST.md`'s "stored once as canonical reference
  relationships" is not quite achievable: an aggregate over SIH must roll up
  through SIH's regionalisation, or its totals will not reconcile with DATASUS's
  own TabNet output for the same query.
- **The residual 46 go to the adjudication queue** that `semantics/relations.py`
  already implements. They are not resolved by picking.

**Two honesty constraints, both non-negotiable:**

- **These tables carry no vintage of their own.** They are TabNet roll-ups
  captured at one moment. Municipalities move between health regions; health
  regions are redrawn. The compiled artifact must record the *source vintage it
  was compiled from* and must not present an undated mapping as if it were
  valid for 1995. Where vintage is unknown the honest value is a recorded
  unknown, not "current" — this is the §3l rule already adopted for relations.
- **Sentinel members are members.** `0000 Ignorado/Exterior`,
  `1100 Município ignorado`, `1190 Região não definida`. Folding these into a
  real region is the "Baixo Acre e Purus" class of error; dropping them silently
  biases every count. They stay, labelled as what they are.

---

## 5. Grain: formalise, but derive it

`unit_of_analysis` is prose today — `admission`, `death`, `establishment-month`,
`professional-establishment-month`, `establishment-bed type-month`.

`REQUEST.md` is right that a machine needs this: for `CNES.ST`,
`COUNT(rows over Jan–Mar)` counts **establishment-months**, not establishments.

But note that the prose **already names the components**. `establishment-month`
is `[establishment, month]`. The formalisation is a structured `grain:` list
whose members are entity types, and it constrains reducers:

- a grain containing a period component makes bare `COUNT(*)` a count of
  *entity-periods*, and any distinct-entity measure must be declared as such;
- `rows_per_key` (§2.5) already states one-vs-many per join key and should
  agree with the grain.

Do **not** hand-author sixty grain files. Declare the component list beside the
existing `unit_of_analysis`, in the file that already exists, and let the prose
stay as the human-readable form of the same fact.

---

## 6. Physical layout — decided by measurement

`REQUEST.md` explicitly declines to prescribe this. The measurement in §1 decides
it:

- **One artifact per (dataset, axis binding, dimension set).** Not a universal
  cube. Compression is the justification for the artifact and dimensionality
  destroys compression.
- **Sparse.** Only observed cells. A dense municipality × month × sex × age grid
  is 2.7M cells/year nationally and mostly empty.
- **Partitioned by year**, matching the lake's existing `year=` convention, so
  partition pruning works and a rebuild is per-year.
- **Accumulator state, not finished indicators**, exactly as `REQUEST.md` says:
  store `los_n`/`los_sum`, not `mean_los`; `numerator`/`denominator`, not `rate`.

A `SIH.RD` municipality × month × {sex, age band} artifact for the full national
series lands in the low tens of millions of rows — comfortably Parquet, and two
orders of magnitude below the microdata it replaces.

---

## 7. Three traps `REQUEST.md` does not mention

All three are previously-burned ground in this project. Each produces a
plausible-looking wrong number rather than an error.

**7.1 Structural absence across schema generations.** SIH.RD has 20 schema
generations. A municipality × year artifact spanning 1992–2026 whose dimension
column is absent from early generations will produce a bucket that means *"the
column did not exist"* while reading as *"unknown"*. `schema_presence` and
`availability()` already know exactly when each column existed. The build must
consult them and either refuse the span or mark the affected periods explicitly.
This is the same class as `DIAG_SECUN`, which is present and dead — filled with
`'0000'` — from the 113-column generation onward.

**7.2 Classification vintage changes.** SIM runs CID-9 before the CID-10
changeover and both are bound because the vintages overlap on the tree
(`FINDINGS.md` §3f). An artifact that groups by "diagnosis chapter" across that
boundary is mixing two classifications under one label. Codelists already carry
validity windows; the aggregate must scope by them, not ignore them.

**7.3 Sentinels.** See §4. Also `120000 → 'Acre - Gestão estadual'`, which is
the most common value of `PA_GESTAO` in real SIA data — a sentinel that outnumbers
every real member.

**Denominators.** Rates need a population series. `population_series` already
exists with `stratifications` and `age_standardizable` recorded per series. A
rate measure must name its series; it must not silently pick one.

---

## 8. Plan

Sequenced so each phase is independently useful and independently revertible.
Phase 0 is a prerequisite for the roll-up requirement and is pure compile with a
checkable output, so it goes first.

### Phase 0 — compile the geography reference — **DONE**

`geography.py`, `curation/geography.yml`, `resources/geography.parquet`,
ARCHITECTURE §14.14, FINDINGS §3n, `tests/test_geography_memberships.py`
(22 tests).

Built: **98,584 rows in 140 KB**, nine classifications compiled and five
excluded with their measurements.

| classification | municipalities | contested |
|---|---:|---:|
| health_region | 5,680 | 46 |
| ibge_microregion | 5,697 | 69 |
| ibge_mesoregion | 5,632 | 50 |
| health_colegiado | 5,417 | 292 |
| metropolitan_region | 1,325 | 13 |
| citizenship_territory | 1,854 | 0 |
| pndr_region | 1,126 | 0 |
| agglomeration | 2,375 | 0 |
| capital | 30 | 0 |

```python
>>> memberships("120040").as_dict()
{'agglomeration': 'Rio Branco', 'capital': 'Rio Branco',
 'health_region': 'AC Baixo Acre e Purus', 'ibge_mesoregion': 'Vale do Acre',
 'ibge_microregion': 'Rio Branco', 'pndr_region': 'Vale do Rio Acre'}
```

Three things the build changed about the design as written above:

1. **Membership is system-scoped** (§4.1). The pack is keyed
   `(municipality, classification, system, window)`, not by municipality alone.
2. **`Membership.contested`** marks the 46 health-region municipalities where
   publishing systems disagree, because the no-system fallback is alphabetical
   and alphabetical tie-breaking is what caused the original defect. Naming a
   system clears the flag.
3. **`health_macroregion` is not shipped.** Neither candidate table is usable
   and the exclusion is recorded with its measurement.

### Phase 1 — grain and the measure algebra
Structured `grain:` beside `unit_of_analysis` (§5). Accumulator kinds
(`count`, `sum`, `mean{n,sum}`, `ratio{num,den}`) with `lift → merge → finalize`,
constrained by `ledger.aggregation`. No artifact yet — just the algebra and its
refusals.
**Test:** merging two `mean` states equals the mean of the union; a
`non_summable` field cannot be given a `sum` reducer.

### Phase 2 — `AggregateSpec` and the build
Spec reads `semantic_axes` for its geography/time binding (§2.1) — it does not
introduce its own. Fingerprint over spec + source fingerprints + schema/semantic
versions + reference versions + engine version, reusing `_resources.py`.
Vertical slice: **SIH.RD → municipality × month × {sex, age band}** with
`admissions`, `deaths`, `los{n,sum}`, `cost_sum`, under **both** the `residence`
and `facility` bindings, which `semantic_axes` already declares.

### Phase 3 — serving
A read verb over the artifact: select measures, filter period/geography/dimension,
roll up through the geography reference and the merge semantics. No UI concepts
in the API — no `/map`, no `/ranking`.
**Test:** municipality × year served without touching SIH microdata; mean LOS
derived from state; municipality → UF roll-up equals direct aggregation.

### Phase 4 — break the event assumption on CNES
`CNES.ST` is establishment-month. If the abstraction assumes `COUNT(rows)` means
"events", it fails here and gets redesigned before coverage broadens — as
`REQUEST.md` correctly insists.

---

## 9. What I recommend against

- **A universal cube.** §6.
- **A new binding vocabulary.** §2.1 — `semantic_axes` exists and was kept for
  this.
- **Hundreds of per-dataset measure files.** `REQUEST.md` says this and is right.
  Measures should be templated over the axes and the ledger, with per-dataset
  declaration reserved for what cannot be derived.
- **Query-time aggregation as the primary path.** §1. It may exist as an escape
  hatch for an unmaterialised slice, but it must be explicitly opt-in and must
  report that it is doing the expensive thing.
