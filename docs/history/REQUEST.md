Yes. The main correction is now clear: **the recipe is not a query-time plan. It is build-time metadata for a persistent aggregate artifact.** Normal frontend use should mostly filter/select already-computed aggregate data.

I would hand Claude Code something close to the following brief.

---

## Objective

Extend `pegasus_data` with a **light but mathematically disciplined aggregate layer** that converts its canonical DATASUS data into persistent, versioned, frontend-ready analytical artifacts.

The immediate target is the dominant PegaSUS workload:

$$
\text{geography} \times \text{time} \rightarrow \text{measure(s)}
$$

especially municipality-indexed longitudinal tables. The frontend should normally **not aggregate DATASUS microdata** and should normally **not trigger expensive aggregation at request time**. It should receive a precomputed table and perform cheap filtering, selection, roll-up where mathematically safe, and visualization.

### Target flow

```text
DATASUS source
      ↓
existing pegasus_data normalization / semantics / lake
      ↓
OFFLINE AGGREGATE BUILD
      ↓
AggregateArtifact
      ↓
backend serves/filter/slices artifact
      ↓
frontend
```

The frontend-facing operation should usually resemble:

```text
load aggregate
→ select measure
→ filter period/categories/geography
→ return compact table
```

rather than:

```text
frontend request
→ scan microdata
→ GROUP BY millions of rows
→ calculate aggregate
```

---

# Core abstraction: `AggregateArtifact`

Treat a computed aggregate as a first-class persistent product, not an ephemeral query result.

Conceptually:

```text
AggregateSpec       →       AggregateArtifact
definition/recipe           materialized result
versioned                    stored
reproducible                 cacheable
small metadata               exportable
```

The **spec should already exist before serving time**, and its artifact should normally already have been built.

A spec might conceptually say:

```text
source dataset: SIH.RD

base observational grain:
    admission

spatial axis:
    binding: patient/residence → municipality
    canonical geography: IBGE municipality

temporal axis:
    competence
    output grain: month/year

dimensions retained:
    sex
    age band
    selected diagnosis grouping
    ...

aggregate states:
    admissions = count
    deaths = sum(MORTE)
    los = {n, sum}
    cost = sum(VAL_TOT)

validity/provenance:
    source vintages
    schema generations
    reference versions
```

The artifact might physically resemble:

```text
municipality
time
sex
age_band
...
admissions
deaths
los_n
los_sum
cost_sum
```

From which:

$$
meanLOS=\frac{los\_sum}{los\_n}
$$

can be derived cheaply.

Whether this is physically one Parquet dataset, several compatible artifacts, or another layout should be decided from the real codebase/cardinalities. **Do not assume my proposed physical layout is correct.**

---

# Important design principle: preserve aggregate state, not only finished indicators

The stored artifact should retain the quantities required for mathematically valid recombination.

For example:

```text
mean
→ store sum + n

rate
→ store numerator + denominator

variance
→ potentially n + Σx + Σx²
```

This allows:

```text
municipality-month
→ municipality-year
→ UF-year
→ health-region-year
```

without returning to microdata, where the corresponding reducer is actually composable.

This should probably be formalized as a small aggregation algebra:

```text
lift raw observations → aggregate state
merge aggregate states
finalize state → displayed measure
```

Do not assume every DATASUS field is summable and do not implement naïve “GROUP BY + SUM everything.”

---

# Geographic infrastructure

Verify and likely extend the existing geography normalization.

Current code appears to derive canonical municipality IBGE7 and UF, but **not the full set of geographic memberships required by the project**.

Desired model is not one hierarchy:

```text
municipality → UF → region
```

but a versioned geographic reference structure capable of resolving multiple classifications:

```text
municipality
 ├→ UF
 ├→ IBGE macroregion
 ├→ health region
 ├→ health macroregion
 ├→ metropolitan region
 └→ other supported supramunicipal geographies
```

These should be stored **once as canonical reference relationships**, then derived from a geographic code.

Do not duplicate deterministic values throughout dataset metadata or fact tables unnecessarily.

Desired operation conceptually:

```python
geo.memberships(code="2704302", vintage=2024)
```

→ all valid geographic memberships.

Before implementing anything new, inspect the existing codelist/reference/DEMAS/IBGE machinery carefully; reuse it if the necessary structures already exist.

---

# Do not hard-code `residence / occurrence`

The aggregate system needs something more general than:

```text
spatial_role = residence | occurrence
```

Different DATASUS families represent different kinds of entities.

Examples:

```text
SIH
admission → patient residence
admission → hospital
hospital → geographic location

SINAN
case → residence
case → notification location
...

CNES
establishment-month → establishment
establishment → geographic location
```

So model this more generally as a **semantic binding/path from the dataset's observational grain to a dimension**.

Conceptually:

```text
observation/entity
    --relationship-->
dimension member
```

Examples:

```text
admission.patient.residence → municipality
admission.establishment.location → municipality

establishment.location → municipality
```

Then geographic roll-up is a separate operation through the canonical geography reference graph.

The exact representation should be chosen after examining how the current ontology, `unit_of_analysis`, `depends_on`, joins and codelists are modeled. Avoid introducing another parallel metadata system if existing structures can express this cleanly.

---

# DATASUS is heterogeneous: formalize base grain

Do not assume every source represents independent events/patients.

Examples include:

```text
SIH.RD
grain ≈ admission

SIM.DO
grain ≈ death

CNES.ST
grain ≈ establishment × period

CNES.PF
grain ≈ professional × establishment × period
```

This matters mathematically.

For an establishment-month table:

```text
COUNT(rows over Jan–Mar)
```

means establishment-months, not necessarily distinct establishments.

Therefore the aggregation layer needs a machine-readable concept of **base grain / observational unit**, likely extending or formalizing the existing `unit_of_analysis`.

This should constrain valid reducers.

---

# Keep new metadata minimal

Strong constraint:

> **Never manually store metadata that can be deterministically derived from existing metadata, reference tables or code.**

Examples:

```text
municipality → UF
municipality → health region
field validity from schema generations
geographic labels from reference tables
```

should be derived.

Manual metadata should be reserved for irreducible semantic assertions such as:

* what an observational unit actually represents;
* how a field/entity relates to an analytical dimension;
* special measure definitions that cannot be inferred;
* mathematically meaningful aggregation semantics.

Prefer inheritance/templates/shared declarations over per-dataset duplication.

Do **not** begin by creating hundreds of `sih.yml`, `sim.yml`, etc. measure files.

---

# Offline aggregate recipes

Recipes/specs are important, but they should primarily drive the **build system**, not normal HTTP requests.

Conceptually:

```text
registered AggregateSpec
        ↓
dependency/fingerprint check
        ↓
build or refresh
        ↓
persistent AggregateArtifact
```

Artifact identity/provenance should probably include some equivalent of:

$$
hash(
spec
+ source\ fingerprints
+ schema/semantic\ versions
+ reference\ versions
+ aggregate\ engine\ version
)
$$

Reuse the project's existing fingerprint/cache/provenance machinery if possible.

A materialized artifact should be exportable together with enough metadata to reconstruct:

```text
what source?
what aggregate definition?
which geographic/time interpretation?
which filters/case definition?
which source/reference vintages?
which code/version built it?
```

This is the “aggregate image” concept.

---

# Frontend contract

The frontend should consume an already analytical dataset.

For example:

```text
municipality | year | sex | age | admissions | deaths | los_n | los_sum
```

It can then cheaply perform:

* period filtering;
* map selection;
* linked-view filtering;
* safe roll-ups;
* comparisons;
* charting;
* derived `mean_los`;
* geographic roll-up where accumulator semantics permit it.

The backend should not expose UI-specific concepts such as:

```text
/map
/ranking
/timeline
```

The same aggregate artifact should support multiple visual projections.

This is broadly the same experience SIDRA provides: **dimensions + geography + time + measures → analytical cells**, except `pegasus_data` must manufacture that analytical structure from heterogeneous DATASUS source records.

---

# What Claude should inspect before designing

Do not implement directly from this brief. First determine how much already exists in:

* `unit_of_analysis`;
* field `aggregation` metadata;
* canonical time normalization;
* geographic normalization;
* codelist roll-ups;
* reference tables;
* DEMAS/IBGE geography sources;
* ontology relationships / joins / `depends_on`;
* Parquet lake layout and partitioning;
* existing fingerprint/cache/materialization lifecycle;
* Arrow/DuckDB execution code.

The desired solution should **extend the existing abstractions**, not create competing ones.

---

# Suggested first deliverable

I would ask for a design + small vertical implementation, not a sweeping rewrite.

Prove the architecture with:

```text
SIH.RD
→ precomputed municipality × time artifact
```

containing a small reusable set of accumulator states such as:

```text
admission count
death count
LOS {n,sum}
cost sum
```

under at least the two legitimate spatial bindings already available in SIH.

Then demonstrate that the artifact can:

1. serve a municipality×year frontend table without scanning SIH microdata;
2. roll municipality safely to UF using the geography reference system;
3. roll time safely where valid;
4. derive mean LOS correctly from accumulator state;
5. rebuild only when its dependency fingerprint changes;
6. export its recipe/provenance;
7. remain compatible with extending the same machinery to a structurally different family such as CNES.

If CNES reveals that the abstraction is event-centric or assumes `COUNT(rows)` has universal meaning, redesign before broadening coverage.

---

## One-sentence target

**Turn `pegasus_data` from “canonical DATASUS rows” into “canonical DATASUS rows plus persistent, reproducible, mathematically composable multidimensional aggregate artifacts,” with municipality×time as the first dominant materialization but without baking event-table assumptions, one geographic hierarchy, or frontend-specific views into the architecture.**

I would explicitly tell Claude that the architecture above is a **design hypothesis and requirements synthesis, not a prescribed implementation**: inspect the repository, challenge any assumption that conflicts with its actual abstractions, and prefer a smaller extension of existing machinery whenever possible.
