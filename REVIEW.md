This is the first corrective pass in this sequence that I would call **fundamentally successful**. `7bbd076` actually restores the source-oriented contract we adjudicated, preserves the good architecture from the previous work, and closes almost all of the defects we explicitly handed Codex. 

I would keep this commit. I would **not** reopen the query architecture again.

There are, however, a few real remaining issues. One is fairly important because the new temporal-relation resolver is now more capable than the SQLite schema that stores adjudicated relations.

# Overall verdict

The intended architecture is now finally recognizable in the code:

```text
SOURCE METADATA
    ↓
publication planning
    ↓
lake / fetch / hybrid
    ↓
requested-slice ETL
    ↓
labels / dimensions / explicit enrichment
    ↓
researcher does analysis
```

The previous row-level analytical behavior is genuinely gone. `time_by`, `geography_by`, and `unresolved_time` were removed; municipality requests no longer become `MUNIC_RES`/`MUNIC_MOV` predicates; annual SIM requests no longer inspect `DTOBITO`; and the documentation explicitly says `period`/`geography` are publication coordinates. 

Codex also reports **1,213 passed / 1 skipped**, clean Ruff, compile checks, manifest checksum, and clean staged diff. I cannot independently execute that repository here, but nothing in the supplied patch contradicts that report.

## What is now properly fixed

**The source-vs-analysis boundary is fixed.** This was the main architectural redirection. The tests now explicitly assert that heterogeneous `MUNIC_RES` values survive an AL publication request and that legacy analytical-axis arguments are rejected.  

**Annual source adaptation is conceptually correct.** A March–April request against annual SIM becomes an enclosing 2020 source request with a warning, not a `DTOBITO` filter. 

**Planning is metadata-only.** Codex added a regression explicitly preventing `plan()` from touching lake fact data. 

**Archive-member completeness is substantially fixed.** New lake provenance stores `logical_source_id(path, member)`, and completeness uses `(family, logical publication, member)` rather than merely the enclosing path.  The new test correctly makes an archive with A/B members and records only A as locally built; the planner then refuses to regard the year as complete. 

**Representation reconciliation is now genuinely global.** Builder and retrieval gather candidates across selected families, choose representations once, then execute only selected `(family,path,member)` units.   Existing open conflicts now block even singleton candidate calls. 

**Capability duplication was fixed correctly.** Curation now separates `source_publication` from `semantic_axes`, and `query_capabilities.json` is compiled from the former rather than manually duplicating analytical variable metadata.  The runtime capability resource no longer contains record-level geography/time axes. 

**Unknown dimension vintage no longer silently becomes “current.”** The dimension engine returns null when it cannot establish a safe temporal relation, except when an unbounded mapping is explicitly proven time-invariant. 

**Relation resolution now understands time and precedence.** It filters by `valid_from`/`valid_to`, then applies local > shipped > legacy and dataset/system specificity. 

**CNES resource handling is much better.** The registry path bug was fixed, CNES attribute lookup is by requested CNES IDs rather than inheriting fact geography, and optional resources increasingly pass through `ResourceManager`. 

**The crosswalk audit wording is now epistemically correct.** The 1,816 and 13,923 values are described as pairwise overlaps rather than canonical ambiguity intervals. That is the right correction. 

So the large previous review is essentially closed.

---

# Remaining issue 1 — the temporal relation resolver can express history, but the catalog cannot

This is the most concrete remaining architectural defect.

Codex upgraded `relations_for()` so that the same semantic target can have:

```text
artifact A, valid through 2010
artifact B, valid from 2011
```

and the resolver correctly chooses A or B by vintage. The new tests demonstrate exactly that. 

But the existing SQLite table has this primary key:

```sql
PRIMARY KEY (
    system,
    dataset,
    field_name,
    relation_type,
    target_type,
    target_name
)
```

It does **not** include `valid_from` or `valid_to`. 

And `adjudicate()` still performs:

```sql
ON CONFLICT(
    system,
    dataset,
    field_name,
    relation_type,
    target_type,
    target_name
)
DO UPDATE ...
    valid_from = excluded.valid_from,
    valid_to   = excluded.valid_to
```



Therefore the local/manual adjudication system cannot actually store:

```text
DIAG_PRINC.chapter:
    CID_OLD  through 2010
    CID_NEW  from 2011
```

as two decisions.

Applying the second decision overwrites the first.

The same problem exists in `seed_relations()`: multiple curated temporal relations occupying the same semantic target slot overwrite each other when seeded into `semantic_relations`. 

The tests miss this because the temporal-history tests monkeypatch `load_relations()` with two in-memory relations rather than storing two adjudicated relations in SQLite.

### What to change

The relation's database identity must represent a **temporal assertion**, not merely a semantic target.

I would prefer a stable `relation_id` primary key, plus a non-unique semantic slot:

```text
relation_id
system
dataset
field
relation_type
target_type
target_name
artifact
valid_from
valid_to
...
```

with explicit overlap/conflict validation.

Alternatively, include the temporal boundaries in a uniqueness constraint, although nullable bounds make that more awkward.

Then add the important test:

```text
adjudicate A valid through 2010
adjudicate B valid from 2011

new connection:
relations_for(... vintage=201006) → A
relations_for(... vintage=201106) → B

both rows remain stored
```

I regard this as the main remaining defect because the whole AI/manual adjudication backdoor is supposed to be a first-class source of historical semantic truth.

---

# Remaining issue 2 — Pegasus now needs a proper concept of a **coarse source vintage**

The query architecture is correctly refusing to invent a month from `DTOBITO`, but there is now an important distinction:

```text
month known       = 2020-06
year known only   = 2020, month unknown
time wholly unknown
```

The current semantic machinery tends to collapse the last two.

For annual source files, the builder already deliberately writes `_competencia=None`: it only assigns competence when `normalized_date % 100` contains a real month.  Fetch provenance similarly stores month competence only when a month exists. 

That's good for preventing false precision.

But `_apply_dimensions()` sees:

```python
competence is None
```

and treats the vintage as completely unknown. It only allows an entirely unbounded, globally time-invariant mapping. 

Yet for SIM 2020 we know:

```text
vintage ∈ [202001, 202012]
```

We do **not** know nothing.

This means Pegasus may unnecessarily return null for an annual dataset even when one relation/artifact is demonstrably valid throughout all of 2020.

The correct abstraction is an interval:

```text
monthly source:
    source_vintage = [202006, 202006]

annual source:
    source_vintage = [202001, 202012]

unknown:
    source_vintage = unbounded/unknown
```

Then a semantic derivation is safe if a single effective relation/mapping applies over the **entire interval**.

This would preserve the safety principle while avoiding unnecessary nulls.

---

# Remaining issue 3 — direct crosswalk enrichment still converts a year into December

This is related but more dangerous.

The patch adds/follows this behavior when `_competencia` is absent but a `year` column exists:

```python
int(year) * 100 + 12
```

i.e. 2020 becomes **202012**. 

That is not a neutral transformation.

Suppose:

```text
CNES X → CNPJ A through June 2020
CNES X → CNPJ B from July 2020
```

and the caller supplies:

```text
year = 2020
```

Picking December means Pegasus can resolve B even though the temporal information only establishes “somewhere in 2020.”

For core `query()` this is less likely because `_competencia` is deliberately carried internally, including null for annual publications.

But `enrich_cnpj()` / `enrich_cnes()` are useful primitives in their own right and should remain semantically safe.

Again, use the coarse interval:

```text
2020 → [202001, 202012]
```

and resolve only if exactly one target applies throughout the whole interval.

Otherwise:

```text
resolved = NULL
status = temporally_ambiguous/coarse_vintage
```

Do not choose January or December arbitrarily.

---

# Remaining issue 4 — exact resource **content-version equality** undermines independent resource updates

This is an architectural regression against something we explicitly designed earlier.

`ResourceManager` now requires:

```python
local_manifest["resource_content_version"]
==
bundled_manifest["resource_content_version"]
```

or rejects the local resource as incompatible. 

That is fine for detecting a random stale file today, but it conflates:

```text
resource format compatibility
```

with:

```text
resource data freshness/version
```

We explicitly wanted Pegasus code releases and semantic-resource releases to be decoupled.

For example:

```text
pegasus-data 1.4
bundled semantic content = 2026-08-23

user downloads compatible semantic pack = 2026-09-15
```

That newer pack should generally be usable if its **resource schema/ABI** is compatible.

The current exact equality rule rejects it.

You need separate concepts:

```text
resource_schema_version
    reader compatibility — strict

resource_content_version / data_epoch
    which evidence snapshot this pack contains — may be newer

minimum_reader_version / compatibility range
    if needed
```

So validate:

```text
schema/ABI compatible?
checksum correct?
manifest identity correct?
```

but do not require the local content timestamp/version to equal the wheel's bundled snapshot.

This matters directly to the intended:

```text
huge maintainer semantic build
        ↓
new compact runtime resource pack
        ↓
users update resources without reinstalling Pegasus
```

architecture.

---

# Remaining issue 5 — `cnes_names` “covered years” is still inferred too optimistically

Codex fixed the obvious bug where an all-years build stored no covered years.

But the new algorithm determines coverage by unioning years found in individual rows' `valid_from`, `valid_to`, and `source_ref`. 

The regression test even uses one dictionary entry valid 2022–2023 and concludes:

```text
resource coverage = 2022, 2023
```



That proves **a relation exists across those years**.

It does not necessarily prove:

> the local CNES-name directory is complete for every establishment in both years.

Resource completeness is a property of the **source snapshot/build**, not the union of individual record validity windows.

This distinction matters because otherwise:

```text
CNES lookup fails
```

is ambiguous between:

```text
establishment genuinely unresolved
```

and:

```text
resource incomplete for that period
```

The safe long-term solution is to derive `covered_years` from source-level evidence:

```text
which complete CNES/reference snapshots/codelists were ingested?
```

rather than from row temporal ranges.

This isn't likely to generate a false name—it generates missing names—but it can overstate the authority/completeness of the resource.

I would classify this P1 rather than P0.

---

# Remaining issue 6 — mixed annual/monthly requests are safe-ish but still structurally crude

The planner retains `year_resolutions`, which is good. But for a subannual request, if **any** requested year is annual:

```python
annual_enclosure = ...
```

it creates one global `time_resolution` adaptation and leaves `months=()` for the whole request. 

The executor then has one global:

```python
coarsening = any(time_resolution adaptation)
```

and passes that to `_filter_source_period()`. 

This is correct enough if:

```text
annual rows → _competencia NULL
monthly rows → _competencia exact
```

because monthly rows still get filtered while annual nulls are retained.

But it has two weaknesses.

First, monthly fetch years may be over-fetched because the planner does not retain month pushdown once one annual year appears.

Second, with `retain_annual_enclosures=True`, **any null source competence gets retained**, even if that null actually represents broken provenance on a supposedly monthly source. 

A safer representation would explicitly distinguish:

```text
annual enclosure
vs
missing provenance
```

instead of using null for both.

This is not currently evidence of widespread wrong output, so I would not hold the whole architecture on it. But the existing per-year resolution information should eventually drive per-year source selection/adaptation rather than collapsing back to one global boolean during execution.

---

# Remaining issue 7 — capability compilation should reject duplicate source declarations

The new compilation design is correct:

```python
source_publication curation
→ query_capabilities.json
```

But:

```python
datasets[code] = compiled
```

silently makes the last declaration win if two curation files accidentally define the same `source_publication.dataset`. 

Given how strongly this project treats semantic conflict, this should hard-fail:

```text
duplicate source-publication capability declaration for SIH.RD
```

rather than depend on sorted file order.

Small change, worthwhile invariant.

---

# Resource centralization is improved, but not literally “one gate” yet

Codex's docs now say all runtime opens pass through `ResourceManager`.

Mostly true.

But `cnes_registry` is a special case:

```python
if record.name == "cnes_registry":
    return
```

in `_validate()`, because lake integrity is delegated elsewhere. 

Then `LocalCnesRegistryProvider` performs its own publication/year completeness calculation.

This is defensible—the CNES registry is a lake dataset, not a static pack—but the architecture should say:

> one **resource resolution interface**, with lake-backed resources delegating integrity/completeness to the lake catalog.

rather than implying one uniform validation implementation.

I wouldn't call this a bug; it's documentation/abstraction precision.

---

# A few things I specifically do **not** think need more work now

I would **not** revisit the source-oriented `query()` decision. That is settled.

I would not bring back `time_by` or `geography_by`.

I would not add row filtering “just for convenience.”

I would not redesign CNES↔CNPJ again. The predicate-pushed, additive, ambiguity-aware model remains correct.

I would not replace SQLite because of the previous storage incident.

I would not require byte-by-byte representation equivalence.

I would not collapse the query engine modules again.

I would not try to make the optional `cnes_names` maintainer compiler masquerade as a fresh-install downloader. Codex now documents that boundary accurately.

---

# Severity summary

| Area                                      | Verdict                                          |
| ----------------------------------------- | ------------------------------------------------ |
| Source-vs-analysis boundary               | **Fixed**                                        |
| Metadata-only planning                    | **Fixed**                                        |
| Lake/fetch/hybrid completeness            | **Fixed substantially**                          |
| Archive-member identity                   | **Fixed**                                        |
| Global representation reconciliation      | **Fixed**                                        |
| Singleton conflict refusal                | **Fixed**                                        |
| Capability source of truth                | **Fixed**                                        |
| Unbounded acquisition guard               | **Fixed**                                        |
| Historical relation resolver              | **Good implementation**                          |
| Historical relation persistence in SQLite | **Still broken for >1 temporal local assertion** |
| Unknown-vintage safety                    | **Much better**                                  |
| Coarse annual vintage semantics           | **Needs refinement**                             |
| Crosswalk with only `year`                | **Potentially unsafe December assumption**       |
| Resource integrity                        | **Good**                                         |
| Independent resource-pack updates         | **Blocked by exact content-version equality**    |
| `cnes_names` coverage authority           | **Still too optimistic**                         |
| Crosswalk overlap audit                   | **Fixed/precisely documented**                   |
| Query architecture maintainability        | **Good**                                         |

## Acceptance judgment

I would call `7bbd076`:

> **Accepted as the architectural baseline, with one important semantic-storage defect and several bounded hardening items remaining.**

This is materially different from my reviews of the earlier patches. I no longer see a reason to distrust the basic source-selection model.

The one thing I would fix **before declaring the semantic/adjudication subsystem closed** is the `semantic_relations` primary-key problem. Right now the runtime can reason about historical relations that the manual/AI adjudication database itself cannot faithfully retain. That is a real contradiction in the architecture.

After that, I would address the annual/coarse-vintage model and resource-version compatibility. The rest can be handled as hardening rather than another architectural correction.
