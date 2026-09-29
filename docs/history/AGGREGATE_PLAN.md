# The aggregate layer — implementation plan

**This is the single source of truth for what is being built, how, and where.**

Three documents, one job each. Do not duplicate between them:

| document | answers |
|---|---|
| [`AGGREGATE_ALGEBRA.md`](AGGREGATE_ALGEBRA.md) | **why** these rules — the mathematics |
| [`AGGREGATE_DESIGN.md`](AGGREGATE_DESIGN.md) | **what** exists already and what is missing |
| **this file** | **where** every change lands, and in what order |

Status is tracked in §7. Nothing here is aspirational: every "reuse" names a
symbol that exists today.

---

## 1. The anti-redundancy contract

This is a mature codebase. Every capability below either **reuses a named
existing symbol** or is justified as genuinely absent.

| need | reused symbol | never build |
|---|---|---|
| microdata for a build | `pegasus_data.query()` | a retrieval path |
| axis bindings (residence/facility; competence/admission) | `semantic_axes` in `curation/datasets/*.yml` | a binding vocabulary |
| row-level dimension derivation | `_query_engine.semantics._apply_dimensions` | a second row resolver |
| classification → codelist | `curation/geography.yml` (sole authority) | a restatement in `joins.yml` |
| cell-level geographic pushforward | `geography.memberships()` / `geography.members()` | a second hierarchy |
| "did this column exist then" | `_availability.field_available()` | schema-generation logic |
| summability of a field | `ledger.aggregation` when present | a parallel classification |
| multi-valued detection | `variable_docs.multi_valued` | new metadata |
| rate denominators | `population_series` table | a population source |
| artifact identity / versioning | `_resources.py` fingerprint pattern | a hashing scheme |
| atomic writes | `persist/staging.py` | a writer |
| dataset grain prose | `dataset_docs.unit_of_analysis` | a replacement |
| CLI shape | `@app.command(rich_help_panel="MAINTENANCE")` as `labelpack` | a new entry point |
| warnings/refusals | `_query_engine/model.py` warning classes | a new error taxonomy |

**Artifacts are data, not package content.** Per ARCHITECTURE §14a they live
under `Settings.lake_dir / "aggregates"` and never in the wheel.
`geography.parquet` ships because it is 140 KB of compiled semantics; a SIH cube
is derived data.

---

## 2. Files

### New

| path | contents |
|---|---|
| `src/pegasus_data/measures.py` | the monoid algebra: accumulator kinds, per-axis additivity, unit checking |
| `src/pegasus_data/_aggregate.py` | `AggregateSpec`, `build_aggregate()`, `aggregate()`, `AggregateReport` |
| `src/pegasus_data/curation/aggregates/sih_rd_municipality_month.yml` | the first spec |
| `tests/test_measures.py` | the algebra laws |
| `tests/test_aggregate_build.py` | build correctness against a direct GROUP BY |
| `tests/test_aggregate_serve.py` | pushforward, Total, refusals |
| `tests/test_geography_relations_agree.py` | the single-authority guard |

### Modified

| path | change |
|---|---|
| `src/pegasus_data/semantics/curation.py` | add `Grain`, `parse_grain()`, `dataset_semantics()`, `semantics_for()` — the one reader for `semantic_axes` + grain |
| `src/pegasus_data/geography.py` | docstring: it is a compiled reference view, not the row resolver |
| `src/pegasus_data/cli.py` | `aggregate-build` and `aggregate` commands |
| `src/pegasus_data/__init__.py` | export `aggregate`, `AggregateSpec`, `AggregateReport` |
| `pegasus_data_ARCHITECTURE.md` | §14.15 (`aggregate()`), §3.1 module list |
| `docs/FINDINGS.md` | anything measured that was not already known |

---

## 3. Phase 1 — reconciliation, grain, algebra

### 1a. Single authority for classification → codelist

`curation/geography.yml` declares `health_region → CIRBRN`. `joins.yml` declares
the same artifact again on a `rollup_to` relation. That duplication is how
`CIRAC` rotted there unnoticed.

* **`tests/test_geography_relations_agree.py`** — any `rollup_to` relation whose
  `target_name` matches a declared classification must name that
  classification's codelist. Drift becomes a failure.
* **`geography.py` docstring** — states it is a compiled reference view for
  lookup and member listing; `_apply_dimensions` remains the only vintage-exact
  row-level resolver.

### 1b. Structured grain — **derived, not restated**

The plan first said "add a `grain:` block to 132 datasets". Measuring the prose
changed that: **the `unit_of_analysis` string already names the components**.
`establishment-bed type-month` is literally `[establishment, bed type, month]`,
and splitting on the hyphen is correct for all but a handful of the 39 distinct
grains. Restating them by hand would have violated the rule `REQUEST.md` itself
sets — never store what can be deterministically derived.

So `parse_grain()` derives, and `curation/datasets/*.yml` may carry an explicit
override only where the prose does not parse:

```yaml
unit_of_analysis: municipality-vaccine-dose-period   # unchanged, human-readable
grain:                                               # OPTIONAL override
  components: [municipality, vaccine, dose, month]
  period_component: month
```

Measured: 132 datasets read, **19 period-bearing**, zero hand-written
declarations needed for the datasets used so far. `Grain.counts()` names what
`COUNT(*)` counts, which is what `check_measure()` refuses against.

### 1c. `measures.py`

```python
class Accumulator(Protocol):        # lift / merge / finalize / identity
COUNT, SUM, MEAN, RATIO, MINMAX     # concrete kinds
@dataclass Measure:
    name: str
    kind: Accumulator
    source_field: str | None
    unit: str                       # what one increment counts; checked vs grain
    additive_over: frozenset[str]   # {"geography", "time", "dimensions"}
    time_reducer: str               # for semi-additive: mean | last | max | None
def merge_states(a, b, measure) -> state
def finalize(state, measure) -> value | None
def check_rollup(measure, axis) -> None | Refusal
```

Refusals raised here, not at the call site:

* `sum` requested over an axis not in `additive_over`;
* `count(entity)` where the grain is entity-period;
* a median or percentile;
* `finalize` of the identity for a mean (undefined, not 0).

Works when `ledger.aggregation` is empty — an unknown field is `non_summable`
until measured, so absence causes refusal rather than assumption.

---

## 4. Phase 2 — spec and build

### Spec — `curation/aggregates/*.yml`

```yaml
name: sih_rd_municipality_month
dataset: SIH-RD
geography_binding: residence      # a key of semantic_axes.geography
time_binding: competence          # a key of semantic_axes.time
time_grain: month
dimensions: [SEXO, RACA_COR]   # age banding needs IDADE + COD_IDADE; see ALGEBRA §7
measures:
  admissions: {kind: count, unit: admission}
  deaths:     {kind: sum, field: MORTE, unit: death}
  los:        {kind: mean, field: DIAS_PERM, unit: day}
  cost:       {kind: sum, field: VAL_TOT, unit: brl}
```

### `build_aggregate(spec, *, period, settings)`

1. `plan()` → explain, refuse unbounded;
2. `query()` per year — **the only retrieval path**;
3. `lift` each row into accumulator state; group by the key tuple;
4. **support mask**: for each (year, dimension) record
   `field_available(dataset, field, year)` — `present | absent | unknown`;
5. write `lake_dir/aggregates/<name>/cells.parquet` through
   `persist/staging.py` — one file, not year partitions. At 2,417 cells for a
   state-year, partitioning buys nothing and a single file makes the
   one-base-cuboid invariant obvious. Partition when a national multi-year
   artifact makes it pay;
6. write `manifest.json` with the fingerprint of
   `(spec, source fingerprints, curation fingerprint, geography sha256, engine version)`.

Rebuild exactly when the fingerprint changes. **The geography sha256 is in the
hash** — changing `geography.parquet` changes every health-region roll-up.

### CLI

```
pegasus-data aggregate-build <name> --years 2022 [--uf AC]
pegasus-data aggregate <name> --by health_region --by year -m admissions --out t.csv
```

---

## 5. Phase 3 — serve

```python
aggregate(name, *, measures=None, by=None, where=None,
          totals=None, settings=None) -> pa.Table | (table, AggregateReport)
```

* `by` names a **level per axis**: `["health_region", "year", "SEXO"]`;
  omitting an axis marginalises it (that *is* Total);
* an axis named in `by` is expanded into its categories; an axis omitted is
  totalled. `total`/`total_known` — the two legitimate denominators when a
  dimension carries an "Ignorado" sentinel — are **not yet implemented**; today
  a total includes the sentinel category, which is the arithmetic that keeps
  Total equal to the sum of its parts. Recorded in §9;
* pushforward for geography uses `geography.memberships()`; for time uses the
  month → year map; for coded dimensions uses `rollup_to` relations;
* `finalize` applied last.

`AggregateReport` carries: cells returned, unmapped mass under a partial
classification, contested municipalities encountered, support gaps crossed, and
every refusal considered.

**Invariant:** every result derives from the one materialised base cuboid.
Independently computed cuboids can disagree; deriving them makes consistency
structural.

### Refusals

| situation | behaviour |
|---|---|
| measure not additive over a requested axis | refuse, name the axis and the reducer that would work |
| partial classification (`metropolitan_region`) | proceed, and **report the unmapped mass** |
| contested municipality, no system named | proceed, flag; naming a system clears it |
| multi-valued dimension with a grain-count measure | refuse, offer `count(mentions)` |
| span crosses structural absence | proceed, mark affected periods in the mask |

---

## 6. Acceptance

Each phase must prove these before the next starts.

**Phase 1** — merging two `mean` states equals the mean of the union;
`finalize(identity)` is `0` for a count and `None` for a mean; a stock refuses
`sum` over time; `count(establishment)` on an establishment-month grain is
refused with alternatives named; every declared `rollup_to` agrees with
`geography.yml`.

**Phase 2** — the artifact reproduces a direct `GROUP BY` on real
SIH-RD/AC/2022 **exactly**; the fingerprint changes when `geography.parquet`
does; the support mask marks years where a dimension was absent.

**Phase 3** — municipality → UF equals direct aggregation from the base;
marginalising sex equals the sum over sex categories (the SIDRA invariant);
mean LOS from state matches the direct computation; metropolitan-region roll-up
reports the unmapped ~76%; a semi-additive measure refuses `sum` over time.

---

## 7. Status

| phase | state |
|---|---|
| 0 — geography compile | **done** (`e205236`) |
| 1 — reconciliation, grain, algebra | **done** — `measures.py`, `semantics.curation.dataset_semantics()`, `tests/test_geography_relations_agree.py`, `tests/test_measures.py` (58) |
| 2 — spec and build | **done** — `_aggregate.py`, `curation/aggregates/`, `pegasus-data aggregate-build`, `tests/test_aggregate_build.py` (16) |
| 3 — serve | **done** — `aggregate()`, `pegasus-data aggregate`, `tests/test_aggregate_serve.py` (25) |
| 4 — break it on CNES | **done** — `curation/aggregates/cnes_st_municipality_month.yml` |
| 5 — geography from IBGE | **done** — `sources/ibge_localidades.py`, `docs/IBGE_LOCALIDADES.md`, `tests/test_ibge_localidades.py` (20) |
| 6 — `semantic_axes` by family | **done** — 5 → **125 of 132** datasets |
| 7 — self-review and remediation | **done** — see §7c |

Verified on live SIH-RD/AC/2022: 49,547 admissions → 2,417 cells in 199 s;
the artifact reproduces a direct `GROUP BY` with **zero disagreeing cells**;
Total over sex equals the sum of its categories (49,547); mean length of stay
served from state matches `sum/n` exactly; `metropolitan_region` reports 49,477
of 49,547 unmapped instead of returning 70 as a national figure.

---

## 9. Deliberately deferred

* **`total_known`.** A dimension with an "Ignorado" category has two legitimate
  denominators. Today `aggregate()` gives the one that keeps Total equal to the
  sum of its parts — the sentinel is a category like any other. Naming the other
  explicitly is a small addition and belongs with the first analysis that needs a
  percentage.
* **Age bands.** They need `IDADE` interpreted through `COD_IDADE`, and
  `IDADE_anos` is settled-withheld. Not reopened here.
* **Time reducers for stocks.** `time_reducer` is declared, validated and
  enforced as a *refusal*; applying `mean`/`last`/`max` over time is not yet
  implemented, so a stock is refused rather than silently reduced. That is the
  safe half, and the right half to ship first.
* **Widening a record-date build.** A record-date artifact now NAMES the periods
  it cannot have filled (§3q) rather than fetching the neighbouring publication
  year itself. Saying which edges are short is honest and cheap; widening the
  fetch is a policy decision about cost that belongs with whoever runs the build.
* ~~**`query(select=...)`.**~~ **Fixed** (§3q). A source projection now excludes
  the columns synthesised after retrieval. The build still projects afterwards
  rather than narrowing the fetch, which is a separate optimisation.

---

## 7c. Phase 7 — reviewing what was built

Measured rather than re-read, and it found three defects of my own plus one in
the query engine. `FINDINGS` §3q has the numbers; the shape of them is the
lesson.

**Everything passed throughout.** None of these were correctness bugs. They were
found by asking what the code costs at the scale it is *for*.

| defect | before | after |
|---|---:|---:|
| `memberships()` scanned the pack per call | 665 ms each; **62 min** for a national roll-up | 168 µs; **0.96 s** |
| `aggregate()` merged cell by cell | 2.6 s on 133,680 cells | 1.1 s |
| `build_aggregate()` lifted row by row | 199 s end to end | 113 s (its aggregation ~70 s → ~3 s) |

Both merges are now Arrow grouped aggregation, and that is a **property of the
algebra**: every accumulator is a commutative monoid whose merge IS a column
aggregate, so the whole vocabulary maps onto `group_by().aggregate()` with no
special cases. Every figure on the rebuilt artifact is identical to the loop's.

Also fixed: **the time rule is now enforced** rather than merely stated. A
record-date artifact names the periods it cannot have filled, because a December
admission is billed in January and a series built from one publication year is
missing its own edges. And **`query(select=[...])` works** — it was passing
downstream-synthesised columns to the source projection.

---

## 7b. Phases 5–6 — geography authority and axis coverage

**Phase 5 — IBGE.** `docs/IBGE_LOCALIDADES.md` is the audit. DATASUS's
microregion table is IBGE's classification *exactly* (558 groups against 558,
none assigned differently) and its mesoregion table differs only by filing three
municipalities under "Ignorado"; the 14% "disagreement" was `.CNV` label
truncation, FINDINGS §3e for the third time. But DATASUS publishes **neither** of
the classifications IBGE has used since 2017, and IBGE publishes **no** health
regions. So: IBGE for territorial identity, DATASUS for health-service geography,
an `authority` column on every membership, and a test refusing to let one
classification be claimed by both.

**Phase 6 — axes by family.** From **5 datasets to 90 of 132**, in two edits.
Datasets inside a system are not independent — 58 SINAN agravos share the
notification block — so axes inherit from `shared:` (file) and
`shared_by_system:` (system), with a dataset's own declaration winning.

**Grain does NOT inherit**, and that is load-bearing: CNES's 13 datasets share
`CODUFMUN` and have different grains, so inheriting it would make `COUNT(*)` mean
one thing across establishment-month and professional-establishment-month —
exactly what §14.15 refuses.

`tests/test_semantic_axes.py` checks **every declared field exists in curation**,
because a field that does not produces an aggregate with no rows and no error —
the phantom-codelist failure of §3k in another costume. It immediately caught one:
`DTREGISTRO` invented for SIM where the column is `DATAREG`.

**125 of 132 now carry both axes, and the seven that do not are deliberate:**

| left out | why |
|---|---|
| `TABWIN.APP`, `TABNET.APP`, `TABDOS.APP`, `DADOS_ABERTOS.APAC`, `SIASUS.IMPBORL` | not datasets — TABWIN is a Windows application |
| `IBGE.PROJUF` | projected by **state**, so it declares `semantic_axes: {}` — an explicit opt-out |
| `PCE.PCE` | a 12-character composite geocode no municipality table decodes whole |

Two mechanisms came out of finishing this. Inheritance now tests for the KEY's
presence rather than its truthiness, so `semantic_axes: {}` says "this dataset
genuinely has none" — a different claim from silence, and the difference matters
because silence would have given PROJUF its family's `MUNCOD` and keyed its
cells on something no municipality table resolves. And `build_aggregate()` now
refuses a geography binding whose `code_system` is not `ibge_municipality`, at
the spec rather than in the output.

---

## 7a. Phase 4 — the stock dataset, and what it proved

`REQUEST.md` asks for this explicitly: *"If CNES reveals that the abstraction is
event-centric or assumes `COUNT(rows)` has universal meaning, redesign before
broadening coverage."*

It does not. CNES.ST is one row per establishment per month — a **stock**
observed repeatedly, where SIH.RD is an **event** stream — and extending to it
needed **a spec and no code**, because both differences were already refusals in
`measures.py`:

* `COUNT(*)` counts establishment-**months**. Declaring that measure with
  `unit: establishment` is refused against the grain, so the shipped spec names
  it `establishment_months`. Over a quarter the difference is roughly threefold.
* `QTINST*` is installed capacity at an instant. It is declared additive over
  geography and dimensions but **not** over time, with `time_reducer: mean`
  named beside it — so summing rooms across months is refused rather than
  returning "room-months".

The contrast is the test: `admissions` is additive along all three axes and
`consulting_rooms` along two, and both are declared rather than inferred.

---

## 8. Explicitly not being built

A universal cube. A second binding vocabulary. Query-time aggregation as the
normal path. Hundreds of per-dataset measure files. Age-standardised rates
(needs a retained age stratum and a named standard population — a spec decision
to take deliberately, recorded in `AGGREGATE_ALGEBRA.md` §7).
