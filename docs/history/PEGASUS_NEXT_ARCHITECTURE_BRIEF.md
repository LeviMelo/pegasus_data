# Pegasus Data — Next-Phase Architecture and Implementation Brief

**Audience:** Codex / implementation agent taking over the current working tree after the 2026-08-23 remediation pass  
**Purpose:** define the next architectural upgrade of Pegasus after the defect-remediation wave, before further feature accretion makes the current abstractions harder to change.  
**Status:** implementation directive. This is not merely a design discussion. Inspect the current tree, challenge details where the source contradicts this brief, then implement the intent with tests and update the architecture/ledgers accordingly.

---

## 0. Context and starting point

The prior remediation pass should be treated as the **new baseline**, not reopened casually. According to the completed patch and its verification log, the tree ended with:

- 1,157 tests passing, 1 skipped;
- Ruff clean;
- `compileall` clean;
- `git diff --check` clean;
- one shared killable decode policy for fetch/profile/build/derived ingestion;
- physical-source single-flight decoding;
- archive/DuckDB member and column projection pushed into readers;
- transactional/staged writes for lake partitions, exports, population and DEMAS;
- versioned label pack rebuilt from the recovered full semantic catalog;
- cross-system label borrowing disabled by default;
- `_competencia` preserved internally for month-exact semantic rendering;
- lazy structural-null scans conformed to one requested schema;
- candidate caps no longer allowed to make semantic choices.

The rebuilt shipped label pack is roughly 30 MB and contains ~3.65 million versioned runs. The existing shipped CNES↔CNPJ crosswalk contains ~546k rows and is only ~4.4 MB. These facts are important because they demonstrate a key architectural point for the next phase: **large maintainer build state can often be compiled into very small runtime artifacts.**

Do not regress the remediation invariants while carrying out this redesign. Before changing architecture, preserve the current working tree, run the full suite in the configured Pegasus environment, and establish a clean reproducible baseline.

## 0.1 Assessment of the finished remediation patch

The finished patch is a strong baseline and should be treated as a completed corrective wave rather than casually rewritten during this architectural work. Its main directions are sound: shared decoder policy, physical-source single-flight, member/column projection, directory-level transaction units, month-level semantic provenance, versioned label resources, explicit foreign-system borrowing policy, structural-null lazy schemas, and refusal rather than truncated semantic ranking.

The architectural work in this brief is deliberately **not** a claim that the remediation patch failed. It addresses the next layer of problems exposed by that success: representation selection, semantic relation typing, crosswalks, resource packaging, adjudication, and a user-facing API that stops leaking source mechanics. Keep these changes separable in commits where practical.

---

# 1. Executive architectural decision

Pegasus is no longer merely an ETL implementation. It should now be organized explicitly around two different systems:

```text
MAINTAINER / COMPILER SIDE

    discover
      ↓
    profile / measure
      ↓
    collect documentary evidence
      ↓
    adjudicate semantic uncertainty
      ↓
    compile compact runtime artifacts


USER / RUNTIME SIDE

    express analytical intent
      ↓
    resolve dataset + period + geography
      ↓
    choose one physical representation per publication
      ↓
    acquire / decode / harmonize schemas
      ↓
    translate identity-level codes
      ↓
    derive requested dimensions
      ↓
    perform requested crosswalks/enrichments
      ↓
    return data + explicit adaptations/warnings/provenance
```

The maintainer side may be expensive, AI-assisted, evidence-heavy and occasionally manual. The runtime side should be **boring, deterministic, small and user-oriented**.

A central design objective for this phase is:

> **Every new piece of internal complexity must remove complexity from the public query interface rather than expose more internal DATASUS machinery to users.**

---

# 2. Non-negotiable principles

## 2.1 Preserve DATASUS source truth

Pegasus must never silently rewrite a raw DATASUS field into a derived interpretation.

If DATASUS publishes:

```text
CNES = 2001578
CNPJ = 00000000000000
```

and Pegasus can infer a valid CNPJ from a CNES→CNPJ crosswalk, the raw `CNPJ` remains exactly as published. Pegasus adds derived information instead:

```text
CNES       CNPJ_raw/original   CNPJ_resolved      CNPJ_resolution_status
2001578    00000000000000      12345678000190     crosswalk_fallback
```

The precise column naming can be refined, but the invariant cannot:

> **Derived semantics are additive. Raw data are never unauditably overwritten.**

This applies equally to labels, municipality normalization, identifier resolution, classification roll-ups and registry enrichment.

## 2.2 Conservative substantive dataset identity

Do not merge two observed datasets merely because they share a schema, filenames look similar, or their populations appear related.

Schema identity is not dataset identity.

Examples such as `SIM.DO`, `SIM.DOINF`, `SIM.DOMAT`, `SIM.DOEXT`, `SIM.DOR`, etc. must remain separate unless an explicit dataset-alias rule establishes that two observed publication names are merely names/representations of the **same declared dataset**.

Do **not** make speculative `subset_of`, `revision_of` or similar relations part of dataset identity or automatic concatenation behavior in this phase. Such relationships may later be stored as evidence-backed analytical metadata, but they are not necessary for safe retrieval.

The safe rule is:

```text
uncertain sameness → keep separate
explicitly established alias / representation → may unify under one logical publication/dataset
```

Add validation so ontology aliases cannot silently collide. If two declared datasets in the same system claim the same observed alias, ontology loading must fail loudly rather than last-write-wins.

## 2.3 Runtime uncertainty is temporary; development uncertainty is work

The runtime must not guess when an ambiguous semantic mapping cannot be resolved safely.

But that must **not** become an excuse to leave the system permanently unfinished.

The lifecycle is:

```text
runtime detects unresolved ambiguity
        ↓
returns raw code / safe result + warning
        ↓
creates or updates an adjudication work item
        ↓
automation builds an evidence package
        ↓
AI/maintainer adjudicates explicitly
        ↓
curation records the decision and provenance
        ↓
regression test asserts actual rendered output
        ↓
next runtime resource build contains the resolved decision
```

The existing refusal for uncurated candidate sets above `_MAX_CANDIDATES` is therefore only the runtime safety behavior. It now needs a first-class **resolution pipeline** behind it.

## 2.4 Source conventions can be trusted proportionally

Do not overengineer representation equivalence.

If the Ministry publishes:

```text
RDAC2401.dbc
RDAC2401.csv
RDAC2401.parquet
```

under the same system/series/UF/competence/publication stem, Pegasus may reasonably presume these are alternative representations of one publication. It does not need to decode terabytes merely to rediscover the publisher's own naming contract.

Use source conventions as **presumptive equivalence**, with lightweight validation and periodic maintainer sampling. Only escalate when evidence contradicts the presumption.

## 2.5 Adaptive temporal resolution should warn, not fail

The public API should accept one conceptual period request. Users should not have to know whether a subsystem is physically indexed by year, month, competence, annual national files, or row-level dates.

If a user asks for March–June 2024 from a source that can only represent 2024 annually, Pegasus should **adapt to the closest valid source resolution and warn**, not fail.

However, distinguish two cases:

1. **Publication resolution is coarse, but row-level time can represent the request.** Fetch the enclosing annual publication and filter rows exactly. Report that the physical publication was annual but the analytical filter was exact.
2. **Neither publication nor row-level data can represent the requested precision.** Expand/adapt to the enclosing annual period and emit an explicit `TimeResolutionWarning` stating requested and effective periods.

Do not confuse resolution adaptation with missing data. If expected publications are missing or acquisition is incomplete, preserve the existing conservative partial-data behavior rather than silently widening/narrowing the question.

## 2.6 Structural absence should be user-friendly

For a longitudinal query spanning schema generations, the high-level API should normally return the union schema with **structural nulls** where a field did not exist in an older generation.

Example:

```text
year   DIAGSEC1
1995   NULL   ← field structurally absent from this schema
...
2015   I10
2015   NULL   ← field exists but this row is missing
```

Those two null states are not ontologically identical. Therefore the result must additionally carry machine-readable structural-absence metadata and/or a query report identifying which selected periods/families did not contain each field.

The legacy lower-level functions may retain stricter defaults for compatibility during transition, but the new primary user-facing query path should favor union + structural-null semantics.

---

# 3. State and packaging architecture: four tiers, not “ship it or rebuild it”

One of the recurring architectural confusions has been treating every derived artifact as either something that must ship in the Python wheel or something every user must rebuild. That binary is wrong.

Use four explicit tiers.

## 3.1 Tier A — source code and small bootstrap resources

Ships with the Python package.

Examples:

- code;
- ontology declarations and curated decisions;
- filename grammars;
- dataset aliases;
- compact tree/bootstrap snapshot if still justified;
- compact label pack;
- compact crosswalk pack;
- bindings/schema summaries required for fresh-install semantics.

Target: tens of MB. A wheel should remain reasonable to install.

## 3.2 Tier B — compiled runtime semantic resources

Derived by maintainers from expensive state, but compact enough to distribute.

The current label pack is the canonical example:

```text
~15 GB semantic catalog
    ↓ compile / deduplicate / range-compress
~30 MB versioned label pack
```

The CNES↔CNPJ crosswalk is another:

```text
large CNES registry / semantic source
    ↓ extract critical join primitive
~546k rows
~4.4 MB Parquet
```

These artifacts may initially ship in the wheel. Longer term, support independently versioned resource bundles so semantic data can be updated without releasing new Python code.

Recommended identity:

```text
pegasus-data code version       0.x.y
runtime resource schema version N
runtime resource content date   YYYY-MM-DD
source snapshot/build ID        ...
```

Eventually support:

```bash
pegasus-data resources status
pegasus-data resources update
```

with checksum verification and atomic installation. The bundled resources remain a functional offline baseline.

## 3.3 Tier C — maintainer build state

May be large and expensive. Not shipped and not rebuilt by ordinary users.

Examples:

- full crawl/inventory catalog;
- full semantic catalog;
- source-document corpus;
- profiling statistics;
- candidate relation measurements;
- conflict ledgers;
- adjudication evidence;
- intermediate compiler state.

This can be gigabytes if genuinely necessary, but it must be measured and designed intentionally rather than allowed to balloon accidentally.

## 3.4 Tier D — user local state

Built or downloaded according to user needs:

- raw content-addressed blobs;
- local inventory/crawl deltas;
- Parquet lake partitions;
- selected large registries such as CNES;
- optional read-model SQLite databases;
- local resource updates;
- user-defined derived datasets.

The package must provide ergonomic management for these resources. Large registries are not “useless because they do not ship.” They are first-class optional local resources.

---

# 4. Storage: what likely went wrong and how not to repeat it

## 4.1 SQLite was not the fundamental mistake

Do not interpret the historical 14–15 GB catalog as evidence that SQLite is intrinsically inappropriate.

The architecture itself already contains evidence to the contrary:

- the original generated documentation/database read model reportedly became ~1.1 GB when millions of rows repeated textual `system`/`codelist` values and labels were duplicated into FTS;
- normalizing repeated codelist identity to integers and removing labels from FTS reduced that read model to roughly 531 MB;
- the same semantic facts compile into a ~30 MB Parquet label pack;
- the 546k-row CNES↔CNPJ artifact is ~4.4 MB.

The problem was primarily **representation multiplication**, not “SQLite bad.”

SQLite remains appropriate for mutable/catalog/query-ergonomic state when the schema is normalized and indexes are justified by actual access patterns.

## 4.2 The full catalog likely inflated for several compounding reasons

Do not accept this diagnosis solely from prose. Measure the live/recovered full catalog with SQLite `dbstat` before changing storage. But the current schema and architecture strongly suggest these drivers:

### A. Range expansion

DATASUS `.CNV` sources can define ranges compactly. Earlier ingestion expanded ranges into millions of explicit dictionary rows. The label-pack compiler later collapses many of these back into runs.

This is a canonical “expand then re-compress” storage smell.

Canonical semantic storage should preserve compact ranges/rules when possible rather than expanding every integer merely because lookup code finds point rows convenient.

### B. Repeated long text per semantic row

The `dictionary` table stores text fields such as:

- `system`;
- `family_id`;
- `field_name`;
- `schema_signature_scope`;
- `value_group` / codelist;
- `source`;
- especially full `source_ref` strings;
- validity strings.

At ~20 million rows, repeatedly storing long codelist names and provenance paths is extremely expensive.

The next maintainer-catalog schema should prefer integer foreign keys for repeated identities:

```text
systems(id, code)
codelists(id, system_id, name, ...)
sources(id, source_type, source_ref, ...)
validity_windows(id, valid_from, valid_to)

code_entries(
    codelist_id,
    code/range,
    label_id or label,
    source_id,
    validity_window_id,
    ...
)
```

Do not normalize blindly where it worsens ergonomics, but repeated large strings on multi-million-row tables are exactly where normalization pays.

### C. Text-heavy indexes multiplied the same storage again

Current/full schemas have several indexes over dictionary text columns. Every SQLite index is another B-tree containing indexed keys plus row references. On tens of millions of rows, an index on `(system, value_group, value_raw)` is not “free metadata”; it can itself occupy hundreds of MB or more.

Indexes must be treated as materialized access paths with a measured cost.

Before adding any new index, require:

1. the exact query it accelerates;
2. baseline query time;
3. indexed query time;
4. index byte size;
5. whether a narrower/integer/partial index could serve the same query.

Do not index large label text into FTS merely because full-text search exists. The architecture already learned this lesson.

### D. Multiple derived representations coexist in the same build universe

The full catalog can contain simultaneously:

- raw semantic dictionary rows;
- range rules;
- complete code tables;
- field↔codelist bindings;
- value-frequency profiles;
- conflict rows;
- append-only events/fetch history;
- generated bundles/read models.

Some duplication is legitimate because the access patterns differ. But each derived representation should have an explicit purpose and retention policy.

### E. Profiling/value-frequency data can be large without being runtime knowledge

`value_frequencies` and similar empirical tables are maintainer evidence. They are useful for semantic adjudication but do not belong in runtime packs. Keep them out of distributed resources and consider retention/top-k policies when full exact frequency distributions are not required.

## 4.3 Measure before redesigning

Add a maintainer script, e.g. `scripts/storage_report.py`, that produces a reproducible storage audit.

For SQLite use, where available:

```sql
SELECT name, SUM(pgsize) AS bytes
FROM dbstat
GROUP BY name
ORDER BY bytes DESC;
```

Also report:

```sql
PRAGMA page_size;
PRAGMA page_count;
PRAGMA freelist_count;
```

For every large table, report row count and approximate bytes/row. For every index, report bytes and the query family that justifies it.

For Parquet resources report:

- file bytes;
- row count;
- row groups;
- compressed bytes/row;
- schema;
- cardinalities relevant to partition pruning.

Do this **before** any large schema migration. The objective is to replace measured waste, not to redesign from intuition.

## 4.4 Storage guardrails

Add a CI/reporting budget for packaged resources.

Current rough baseline is approximately:

```text
labels.parquet              ~30 MB
labels_crosswalk.parquet    ~4.4 MB
tree.parquet                ~1.3 MB
bindings/schema/families    << 1 MB each
```

Recommended initial guardrail:

- report every packaged artifact and total packaged resource size on CI;
- fail if an individual resource or aggregate grows by >25% without an explicit budget update/rationale;
- require explicit architectural review if core runtime resources approach ~100 MB compressed;
- do not make 100 MB a religious limit—make unexplained growth the failure condition.

The maintainer catalog may exceed this drastically. That is acceptable only if `storage_report.py` demonstrates the bytes correspond to necessary evidence rather than repeated/expanded data.

## 4.5 Preferred storage forms

Use storage by access pattern, not ideology:

- **SQLite:** mutable catalogs, adjudication state, provenance ledgers, metadata lookup, local query ergonomics;
- **Parquet:** immutable/mostly immutable large mappings, compact runtime resources, analytical tables, column-projected access;
- **YAML/TOML:** small human-curated declarations and reviewable overrides;
- **content-addressed files:** raw source artifacts.

Do not force everything into SQLite merely for single-file ergonomics, and do not force everything into Parquet merely for compression. Keep interfaces abstract enough that users do not care.

---

# 5. Physical representation equivalence and deduplication

## 5.1 Problem

Pegasus already distinguishes logical identity from file representation conceptually, but ensure fetch/build execution actually chooses **one representation per logical publication**.

If DATASUS publishes:

```text
RDAC2401.dbc
RDAC2401.dbf
RDAC2401.csv
```

and all map to one logical publication key, an analytical query must not concatenate all three and triple the rows.

## 5.2 Do not perform exhaustive content equivalence

Do not decode every representation solely to prove equality.

Define a presumptive representation-equivalence contract based on publisher metadata:

```text
same authoritative publisher
+ same declared dataset/system/series
+ same geographic scope
+ same period/competence
+ same logical publication stem/member identity
+ distinct known representation extension/container
→ presume alternative representations of one publication
```

This assumption must be explicit in architecture and testable.

## 5.3 Representation selection

Group candidate physical files by `logical_id` / logical publication identity **before** fetch/build contribution.

Select one preferred representation according to a policy based on cost and fidelity. Do not hard-code a simplistic global extension order without measurements; establish reader-specific costs and source trust. A likely default might favor directly queryable/current representations over compressed legacy forms when equivalence is presumed.

Persist only small selection metadata, not content fingerprints of terabytes.

## 5.4 Lightweight validation and conflict handling

Maintainer validation should periodically sample publications with multiple representations and compare cheap properties:

- row counts where inexpensive;
- schema compatibility;
- selected key samples;
- optionally canonical hashes on small/sampled publications.

If representations disagree materially:

```text
representation_conflict(logical_publication, representations, evidence, status)
```

Then do not silently deduplicate that publication until adjudicated.

Conflict evidence is a maintainer build object and can remain small.

## 5.5 Tests

Add behavioral tests proving:

1. two physical representations with one logical publication contribute rows once;
2. two different logical publications with identical schemas both contribute;
3. two different observed series are never unified merely by schema;
4. an explicitly recorded representation conflict prevents silent preferred-representation collapse;
5. archive-member logical IDs remain distinct where one physical archive contains several datasets.

---

# 6. Dataset ontology: keep identity conservative

The ontology should answer:

> Which observed publisher names/series correspond to which declared logical dataset?

It should **not** be forced to encode every epidemiological relationship among datasets merely to make retrieval safe.

Implement now:

- uniqueness validation for `(system, observed_alias)`;
- no schema-based dataset unification;
- explicit provenance for aliases;
- optional `status`/`validity` if an alias itself changes over time;
- tests around confusing SIM and SIASUS names.

Defer unless independently justified:

- `subset_of`;
- `revision_of`;
- `overlaps_population_with`;
- `previous_version_of`.

If later added, these are **analytical relationship assertions**, never identity/merge rules, and must carry evidence + validity + review date.

---

# 7. Semantic model upgrade: stop treating every `.DEF` transformation as a competing label

## 7.1 Current conceptual problem

DATASUS `.DEF` files describe TabNet analytical transformations. A raw municipality field may legitimately appear with mappings to:

- municipality name;
- state;
- health region;
- macroregion;
- capital status.

These are not five competing meanings of the raw municipality code.

They are different relations over the same source domain.

A flat model such as:

```text
MUNIC_MOV → MUNICBR
MUNIC_MOV → REGIAO
MUNIC_MOV → CAPITAL
```

loses the semantic type of each relation and forces the renderer to rediscover it via ranking.

## 7.2 Introduce typed semantic relations

At minimum distinguish:

### `label_of`
Identity-preserving human-readable designation of the same coded entity/category.

Examples:

```text
120040 → Rio Branco, AC
E119   → exact ICD-10 category description
1      → Masculino
```

### `rollup_to`
Many-to-one analytical aggregation.

Examples:

```text
municipality → health region
municipality → state
ICD category → ICD chapter
procedure → procedure group
```

### `attribute_of`
Derived property of the same entity.

Examples:

```text
municipality → is_capital
procedure → complexity level
```

### `crosswalk_to`
Identifier namespace transformation / linkage relation.

Examples:

```text
CNES → CNPJ
historical municipality identifier → canonical municipality identifier
```

Potential later types include `part_of`, `equivalent_to` and `deprecated_by`, but do not add relation taxonomy without actual use cases.

## 7.3 Separate source domain, target type and relation

A semantic mapping needs at least:

```text
source code system / namespace
source field or field semantic type
relation type
target semantic type / namespace
codelist/reference artifact
validity interval
system scope
source authority/provenance
adjudication status
```

For example:

```text
CODMUNRES
  code_system = IBGE_MUNICIPALITY

BR_MUNICIPALFA
  source_namespace = IBGE_MUNICIPALITY
  relation = label_of
  target_type = municipality

CIRAC
  source_namespace = IBGE_MUNICIPALITY
  relation = rollup_to
  target_type = health_region
```

Then `labels=True` never considers CIRAC for the label column. It is simply not eligible.

## 7.4 Do not throw away `.DEF` evidence

Parsing should preserve what `.DEF` actually says:

```text
physical field
TabNet display dimension
codelist/reference name
axis role (row/column/selection/etc.)
source file + line
```

If the exact semantic relation cannot yet be inferred, store it as an unresolved transformation candidate rather than flattening it immediately into `field_codelists` as though it were a label candidate.

## 7.5 Statistical evidence remains valuable

Automation should measure each candidate relation using features such as:

### coverage

```math
C(L)=|S_X ∩ Domain(L)| / |S_X|
```

### row-weighted coverage

```math
C_w(L)=Σ_{x∈Domain(L)} n_x / Σ_x n_x
```

### granularity / distinction preservation

```math
G(L)=|L(S_X)| / |S_X ∩ Domain(L)|
```

### information loss

Compare entropy before and after mapping where useful:

```math
H(X) - H(L(X))
```

### structural features

- code width;
- numeric/alphanumeric pattern;
- leading zeros;
- range rules;
- temporal validity overlap;
- system compatibility;
- source authority;
- contradiction rates;
- consistency with other candidate mappings.

These measurements should **propose and support semantic relations**, not be the final authority where intent remains ambiguous.

---

# 8. First-class adjudication workflow (“manual backdoor”)

This is a required architectural feature, not a workaround.

No automation will perfectly reconstruct decades of institutional semantics. Stop trying to patch every ambiguity with increasingly complicated runtime ranking.

## 8.1 Work-item model

Create an adjudication ledger/table or equivalent with fields similar to:

```text
id
kind
system
dataset/family
field
candidate relations/mappings
reason opened
priority / estimated impact
observed data summary
measurement snapshot
source references
status: open | proposed | adjudicated | rejected | needs_external_evidence
resolution
resolved_by
resolved_at
curation target
```

## 8.2 Evidence-package generation

For each semantic ambiguity, provide a command/API that materializes a compact evidence package:

```bash
pegasus-data adjudicate show <id>
pegasus-data adjudicate export <id>
```

Include:

- field schema and examples;
- observed value distribution/sample;
- candidate mappings;
- coverage/granularity/information-loss metrics;
- `.DEF` declarations;
- `.CNV`/lookup excerpts;
- applicable official documentation already known to the catalog;
- relevant validity windows;
- prior curation and conflicts.

This is designed for AI adjudication.

## 8.3 Explicit curation

The adjudicator writes a compact human-reviewable decision, e.g. YAML:

```yaml
system: SINASC
field: CODMUNRES
semantic_type: municipality_identifier
code_system: IBGE_MUNICIPALITY

translation:
  relation: label_of
  codelist: BR_MUNICIPALFA
  target_type: municipality
  validity: inherited

dimensions:
  health_region:
    relation: rollup_to
    codelist: CIRAC
    target_type: health_region

evidence:
  - source: def
  - source: observed_coverage
  - source: granularity_analysis
  - source: official_doc
review:
  status: adjudicated
  date: 2026-08-23
```

Exact schema can differ, but decisions must be diffable, provenance-carrying and compilable.

## 8.4 Runtime refusal must feed the queue

If runtime rendering refuses an uncurated >12-candidate ambiguity, ensure the corresponding semantic question exists in the adjudication ledger. Repeated runtime refusals should not create duplicate work items.

## 8.5 Acceptance criterion

A semantic ambiguity should progress from:

```text
raw only / warning
```

to:

```text
adjudicated deterministic runtime behavior
```

without changing runtime ranking code.

---

# 9. Translation, dimensions and crosswalks are different user operations

## 9.1 Translation

Translation answers:

> What human-readable label denotes the same entity/category as this code?

Identity is preserved.

`labels=True` should therefore mean **identity-level translation only**.

Examples:

```text
SEXO 1 → Masculino
MUNIC_RES 120040 → Rio Branco, AC
DIAG_PRINC E119 → exact ICD-10 diagnosis/category label
```

## 9.2 Dimensions

A dimension answers:

> What analytical grouping/attribute can I derive from this value?

Examples:

```text
MUNIC_RES → health_region
MUNIC_RES → state
DIAG_PRINC → ICD chapter
```

These should not be silently created as “labels.”

## 9.3 Crosswalk/enrichment

A crosswalk answers:

> How can an identifier in one namespace be linked to another namespace or external/local registry?

Examples:

```text
CNES → CNPJ
CNES → local CNES establishment row
CNPJ → establishments (reverse, potentially one-to-many)
```

Crosswalks require explicit cardinality semantics because they can change row multiplicity.

---

# 10. CNES ↔ CNPJ: implement as a general temporal crosswalk, not a label

This is a priority use case.

## 10.1 Why this matters

Many DATASUS datasets contain CNPJ fields that may be placeholders or unusable for linkage, while CNES is available. A reliable CNES→CNPJ relation can be critical for linking patient/production data to establishment/legal-entity data.

The current resource already proves this can be compact: ~546k rows in ~4.4 MB.

## 10.2 Audit the current crosswalk before elevating it

The current label-pack crosswalk builder historically stored approximately:

```text
codelist
code
cnpj
```

without necessarily retaining system/vintage/provenance in the shipped relation.

Before creating the public API, measure the recovered/full catalog and answer:

```text
Within one validity window, does a CNES map to at most one CNPJ?
Does one CNES map to different CNPJs over time?
How often do multiple CNES codes map to one CNPJ?
Are there ambiguous overlapping mappings?
What source families/codelists provide the mapping?
```

Do not assume bijection.

## 10.3 Generic crosswalk data model

Compile a resource with a schema similar to:

```text
source_namespace       # CNES
source_code
target_namespace       # CNPJ
target_code
valid_from
valid_to
source_system          # if relevant / nullable when genuinely independent
source_ref / compact source ID
confidence / authority
status                 # active/conflict/etc. if needed
```

Normalize/compact provenance if necessary so the artifact stays small.

## 10.4 Direction and cardinality matter

CNES→CNPJ and CNPJ→CNES are not the same operation.

A legal entity can operate several health establishments, so reverse lookup is naturally one-to-many.

The crosswalk API must expose declared/measured cardinality, e.g.:

```text
CNES --many-to-one?--> CNPJ    (per competence/window, measure it)
CNPJ --one-to-many--> CNES
```

Do not describe a crosswalk as a “translation” if it can change multiplicity.

## 10.5 Enrichment must not silently multiply rows

Default enrichment invariant:

> **Adding an enrichment must not increase the number of fact rows.**

If a source key resolves to multiple target values in the applicable period, default behavior should mark the row as ambiguous/conflicted rather than explode it.

For example:

```text
CNPJ_resolved = NULL
CNPJ_resolution_status = "ambiguous_crosswalk"
```

and warn/report the count.

Allow explicit row explosion only through an advanced opt-in such as `explode=True` / a dedicated join API.

## 10.6 Resolution policy for an existing raw CNPJ field

Recommended default logic:

```text
raw CNPJ valid and crosswalk absent
    → resolved = raw
    → status = observed

raw CNPJ placeholder/invalid and unique crosswalk valid
    → resolved = crosswalk
    → status = crosswalk_fallback

raw CNPJ valid and crosswalk agrees
    → resolved = raw
    → status = observed_confirmed

raw CNPJ valid and crosswalk disagrees
    → resolved = NULL by default
    → status = conflict
    → preserve both raw and crosswalk candidate

multiple crosswalk candidates
    → resolved = NULL
    → status = ambiguous_crosswalk
```

Do not silently choose between two valid conflicting identifiers.

Use CNPJ checksum validation and explicit placeholder detection as evidence, not as permission to erase the raw field.

## 10.7 User communication

Every enrichment report should include:

```text
requested enrichment
source field/namespace used
target namespace
validity/competence handling
relationship cardinality
rows before / after
matched
unmatched
raw placeholders replaced in resolved column
confirmed matches
conflicts
ambiguous relations
```

For a one-to-many reverse relationship, surface that fact prominently before any explicit explode/join operation.

---

# 11. Large registries are optional local resources, not discarded functionality

The complete CNES establishment registry should not be placed in the wheel merely because it is useful. But it must remain easy to obtain, build, query and join locally.

Introduce a coherent resource/registry management layer.

Possible public concepts:

```python
pg.resources.status()
pg.resources.ensure("CNES", period=("2022-01", "2024-12"))
pg.resources.build("CNES", period=...)
pg.resources.remove("CNES", ...)
```

CLI equivalents:

```bash
pegasus-data resources status
pegasus-data resources ensure cnes --period 2022-01:2024-12
pegasus-data resources build cnes --period ...
```

The precise naming can change. The important design is:

- the runtime knows which enrichments require only a shipped compact resource;
- which require a local large registry;
- which local slices already exist;
- how expensive/much data a missing local resource would require;
- how to build only the necessary period/scope rather than the whole history.

For example, `CNES→CNPJ` should normally use the shipped compact crosswalk and **not** force a user to build the full CNES registry. Establishment name/type/ownership/history may require local CNES data.

Define a resource acquisition policy at the settings/query-planner layer rather than prompting interactively from a library call. A reasonable model is:

```text
resource_policy = "auto"   # use shipped/local resources; fetch/build the smallest necessary missing slice within configured limits
resource_policy = "local"  # never access network for enrichment; report what resource is missing
resource_policy = "remote" # allow required source retrieval regardless of current local materialization, still respecting safety/size guards
```

The exact names can change. `auto` should be conservative about unexpectedly huge optional downloads: before materializing a large registry slice, the plan/report should expose the estimated files/bytes, and configured size ceilings should turn an oversized automatic action into a clear resource requirement rather than a surprise multi-gigabyte download. Compact shipped artifacts such as the CNES↔CNPJ crosswalk should require no such ceremony.

---

# 12. Public API redesign: one analytical-intent layer over fetch/load mechanics

The current API exposes too many internal source-specific decisions (`years`, `months`, various label policies, knowing whether a file axis exists, etc.). Preserve lower-level functions for compatibility/power users, but introduce one primary API that expresses analytical intent.

## 12.1 Proposed primary entry point

Use a name such as `query()` unless a better existing API can be cleanly evolved without excessive breakage.

Conceptual form:

```python
result = pg.query(
    "SIH-RD",
    period=("2022-01", "2024-12"),
    geography="AL",
    select=["CNES", "CNPJ", "DIAG_PRINC", "MUNIC_RES"],
    labels=True,
    dimensions=["MUNIC_RES.health_region", "DIAG_PRINC.chapter"],
    enrich=["CNPJ"],
)
```

This should not require the user to know whether Pegasus serves the query from:

- an existing lake partition;
- a cached raw source;
- a new FTP download;
- annual or monthly publications;
- one or several schema generations;
- a shipped codelist;
- a local reference table;
- the CNES↔CNPJ crosswalk.

Those are planning details.

## 12.2 `period=` is the single public time request

Accept ergonomic forms such as:

```python
period=2024
period="2024"
period="2024-03"
period=("2020", "2024")
period=("2020-03", "2024-08")
```

Normalize to an internal closed/open interval representation.

Deprecate or demote `years=`/`months=` from the primary API. Lower-level compatibility wrappers may continue to support them.

## 12.3 Time-resolution planner

Each dataset/family/source capability should expose enough metadata to plan:

```text
publication temporal resolution
available period range
whether a row-level temporal field exists
row-level temporal precision
```

Planner behavior:

### exact physical support

Monthly request + monthly publication → select exact publications.

### coarse publication, exact row field

Monthly request + annual publication + reliable row month/date → fetch enclosing annual publication, then apply exact row filter.

### no exact representation

Monthly request + annual-only aggregate with no row time → fetch annual period and emit adaptation warning:

```text
Requested period: 2024-03 through 2024-06
Source temporal resolution: year
Effective period: 2024
Reason: source cannot represent subannual restriction
```

No hard error by default.

Provide advanced `time_policy="strict"` if a caller explicitly wants refusal instead of adaptation.

## 12.4 Geography should likewise express intent

A minimum user-facing form:

```python
geography="AL"
```

or structured selectors later:

```python
geography={"uf": "AL", "municipality": "270430"}
```

Do not make users reason about file partition axes. If a source has no UF file axis but does contain a reliable row-level UF/municipality field, the planner may fetch the enclosing national publication and filter rows. Report the cost/strategy.

If the requested geography cannot be represented either physically or at row level, do not silently return a broader geography merely because time adaptation does so. Geographic widening can fundamentally change the population and should remain explicit/refused unless a safe semantic rule exists.

## 12.5 Schema evolution default

Primary `query()` should use:

```text
schema_policy = union
missing_in_generation = structural_null
```

If a requested field exists in at least one selected schema generation, return it and null-fill generations where it did not exist.

If the field exists in none of the selected/known generations, raise a true missing/unknown-field error.

Attach structural-absence metadata and include it in the query report.

## 12.6 Labels

`labels=True` performs only identity-level `label_of` mappings.

Raw code columns remain.

Recommended result convention:

```text
DIAG_PRINC
DIAG_PRINC_label
MUNIC_RES
MUNIC_RES_label
```

Do not let health region/chapter/group mappings become generic labels.

## 12.7 Dimensions: ergonomic and explicit

Provide a simple string syntax for discoverable cases:

```python
dimensions=[
    "MUNIC_RES.health_region",
    "MUNIC_RES.state",
    "DIAG_PRINC.chapter",
]
```

Also consider an advanced typed form:

```python
pg.dimension("MUNIC_RES", "health_region")
```

Do not require users to know codelist names such as `CIRAC`.

Expose discoverability:

```python
pg.describe("SIH-RD").dimensions("MUNIC_RES")
pg.describe("SIH-RD").enrichments()
```

or equivalent structured metadata. The enrichment description should explain routes in domain language, for example:

```text
CNPJ
  available from: CNES
  relation: temporal identifier crosswalk
  default cardinality: at most one target per CNES+competence (if measurement confirms this)
  reverse CNPJ→CNES: one-to-many
  shipped resource: yes
  row multiplication on default enrichment: no
```

Result naming can follow:

```text
MUNIC_RES_health_region
DIAG_PRINC_chapter
```

while preserving raw and label columns.

## 12.8 Enrichment: two ergonomic levels

The earlier prototype:

```python
enrich={"CNES": ["CNPJ"]}
```

is technically explicit but not intuitive for a new user.

Prefer a simple target-oriented form when Pegasus can infer a unique declared route from selected columns:

```python
enrich=["CNPJ"]
```

If `CNES` is present and the semantic registry declares one safe CNES→CNPJ route, Pegasus resolves it automatically and reports the route.

For advanced/ambiguous cases support an explicit route object/string:

```python
enrich=[pg.enrichment("CNPJ", from_field="CNES")]
```

or an equivalently clear mapping:

```python
enrich={
    "CNPJ": {
        "from": "CNES",
        "as": "CNPJ_resolved",
    }
}
```

Avoid cryptic nested mappings as the only supported interface.

If more than one source field can legitimately produce CNPJ and no unique route exists, require explicit selection rather than guessing.

## 12.9 Derived identifier naming

Never overwrite the raw target field.

Recommended convention:

```text
CNPJ                  # raw DATASUS field, if present
CNPJ_resolved         # additive resolved identifier
CNPJ_resolution_status
```

The full candidate/provenance columns may be available under a provenance option rather than always emitted.

## 12.10 Provenance levels

Offer simple user policy rather than dozens of independent internal toggles:

```python
provenance=False          # default visible table remains clean
provenance="derived"      # show derived-field source/status columns
provenance="all"          # expose physical source provenance too
```

Even when provenance is hidden from the returned columns, it remains internally available for correctness and in the query report.

## 12.11 Query report and warnings

Do not require ordinary users to request `report=True` merely to learn that Pegasus changed the meaning of their request.

Use two channels:

1. Python warnings for material adaptations/conflicts;
2. structured `QueryReport` available optionally/through a result object or `return_report=True`.

Material warning classes should include at least:

- `TimeResolutionWarning`;
- `StructuralSchemaWarning` (possibly aggregated, not spammed per row/family);
- `SemanticFallbackWarning`;
- `CrosswalkAmbiguityWarning`;
- `ResourceFetchWarning`/cost note where useful.

The report should record requested vs effective period, source strategy, schema generations, structural absence, semantic substitutions, dimensions, crosswalk cardinality and enrichment statistics.

## 12.12 Explainability/discovery

Add a planning/explain path so users can understand what will happen without executing a huge query:

```python
pg.plan(
    "SIH-RD",
    period=("2020-01", "2024-12"),
    geography="AL",
    enrich=["CNPJ"],
).explain()
```

Output should say, for example:

```text
Dataset: SIH.RD
Requested period: 2020-01 .. 2024-12
Physical publications: monthly SIH-RD
Selected representations: DBC (or preferred available representation)
Schema generations: 2
Schema policy: union; structural-null fields: ...
Labels: identity-level mappings, vintage scoped
Enrichment: CNES → CNPJ, temporal crosswalk
Expected local/remote data: ...
```

This is much better UX than requiring users to infer internal behavior from function signatures.

---

# 13. Compile semantics into runtime artifacts

The maintainer semantic database should behave like compiler state. Runtime should consume compiled decisions.

Compile at least:

```text
runtime_dataset_map
runtime_field_semantics
runtime_label_relations
runtime_dimension_relations
runtime_crosswalks
runtime_schema_presence
runtime_join declarations
runtime_resource manifest
```

Do not ship empirical profiling tables merely because they were useful to make the decision.

Every compiled artifact should include metadata:

```text
resource schema version
content/build version
built_at
source catalog/build ID
curation revision / git commit
compiler version
```

A user should be able to inspect:

```bash
pegasus-data resources status
```

and know whether the runtime semantic pack predates the files they are querying. A newer source file is **not automatically invalid**; only genuinely unknown structures/semantics need escalation.

---

# 14. Local registry and external-source abstraction

Pegasus is increasingly an integration layer over several Ministry/IBGE/registry sources, not merely one FTP directory. Make that explicit without forcing users to understand source boundaries.

Create an internal `ResourceProvider` / `RegistryProvider` abstraction or equivalent that can describe:

```text
resource identity
source authority
coverage period/geography
local availability
estimated download/build cost
primary keys / namespaces
temporal semantics
```

Examples:

```text
DATASUS SIH publication provider
CNES registry provider
CNES↔CNPJ compact crosswalk provider
population provider
DEMAS API provider
IBGE geography provider
```

The query planner can then satisfy `enrich=` and `dimensions=` through providers.

Do not over-generalize into a plugin framework unless concrete providers require it. A small internal interface is sufficient.

---

# 15. Storage redesign of the maintainer semantic catalog

This is lower priority than API/crosswalk correctness but should be investigated now to prevent another storage blow-up.

## 15.1 First measure the recovered catalog

Run `dbstat`. Produce top table/index byte consumers. Do not infer from row counts alone.

Record the measurement in `FINDINGS.md` because it will resolve the question of what actually made the catalog ~15 GB.

## 15.2 Consider range-native dictionary storage

Instead of canonical storage consisting only of expanded point rows, consider a hybrid:

```text
codelist_points
  explicit arbitrary code → label rows

codelist_runs
  code_lo / code_hi → label ranges

codelist_rules
  expressions too complex to normalize safely
```

The runtime pack already demonstrates that ranges can dramatically reduce size.

Do not force DBF lookup tables that are truly enumerated into artificial ranges merely for compression.

## 15.3 Normalize high-cardinality repeated text

Particularly consider IDs for:

- systems;
- codelists;
- provenance sources/source refs;
- validity windows if repetition is high.

Benchmark query ergonomics before/after. Views can preserve readable SQL for maintainers.

## 15.4 Audit indexes

Generate a table:

```text
index | bytes | query served | measured speedup | keep/remove
```

Remove indexes whose cost has no demonstrated access-path benefit.

Prefer integer-key indexes over repeated long text where possible.

## 15.5 Retention policies

Append-only fetch/event history may grow indefinitely. Decide what is scientific provenance versus operational telemetry.

Scientific provenance should remain.

Purely operational logs may be summarized/rotated if they become significant.

Do not delete anything until measured; this is a design instruction, not an authorization for destructive cleanup.

---

# 16. Migration strategy: do not break the current API in one commit

The next phase is an architectural upgrade over a recently stabilized codebase. Use staged migration.

## Phase 0 — preserve and commit remediation baseline

- inspect the supplied finished patch;
- run full suite;
- ensure the working tree is cleanly checkpointed before redesign;
- do not mix bug-remediation diff with API redesign if avoidable.

## Phase 1 — evidence and storage audit

Implement:

- `storage_report.py`;
- resource manifest/version reporting;
- audit of recovered CNES↔CNPJ cardinality/vintage;
- audit of representation duplicates by logical ID;
- ontology alias collision validator.

Produce `FINDINGS.md` evidence before large migrations.

## Phase 2 — generic temporal crosswalk subsystem

Implement:

- typed crosswalk data model;
- versioned CNES→CNPJ compiled artifact;
- runtime crosswalk reader;
- cardinality-safe join/enrichment engine;
- additive `CNPJ_resolved` semantics;
- conflicts/ambiguities;
- report statistics;
- no row multiplication by default.

Keep the artifact small and measure it.

## Phase 3 — representation selection

Wire preferred representation selection into fetch/build using logical publication groups.

Do not full-content-compare by default.

Add sampled maintainer verification and conflict recording.

## Phase 4 — typed semantic relations and adjudication

Introduce relation types and migrate current manual bindings incrementally.

Do not require every `.DEF` binding to be perfectly classified before the runtime remains functional. Existing curated labels continue to work while unresolved transformations are queued.

Build adjudication CLI/evidence workflow.

## Phase 5 — new `QuerySpec` / primary `query()` API

Implement an internal immutable query specification first:

```text
DatasetRef
Period
Geography
Selection
SchemaPolicy
SemanticRequests
EnrichmentRequests
ProvenancePolicy
```

Then make `query()` consume it.

Refactor existing `fetch`, `load`, `scan`, `export` to share planners rather than independently translating arguments again.

Legacy APIs become wrappers over the same planning objects wherever feasible.

## Phase 6 — resource/registry management

Expose optional large-resource lifecycle and query-local build/fetch strategies.

## Phase 7 — deprecation cleanup

Only after the new API is demonstrated and documented should `years=`/`months=` and redundant expert knobs be deprecated from the primary examples.

Do not remove lower-level capabilities that advanced users/tests still need.

---

# 17. Internal planner architecture

Avoid repeating the current history where `fetch`, `load` and `scan` each encoded slightly different versions of the same semantic policy.

Create shared planning objects roughly like:

```python
@dataclass(frozen=True)
class QuerySpec:
    dataset: DatasetRef
    period: Period | None
    geography: Geography | None
    select: tuple[str, ...] | None
    schema_policy: SchemaPolicy
    labels: bool
    dimensions: tuple[DimensionRequest, ...]
    enrichments: tuple[EnrichmentRequest, ...]
    provenance: ProvenancePolicy

@dataclass(frozen=True)
class RetrievalPlan:
    logical_publications: ...
    representations: ...
    families: ...
    physical_filters: ...
    row_filters: ...
    hidden_dependencies: ...
    adaptations: ...

@dataclass(frozen=True)
class SemanticPlan:
    translations: ...
    dimensions: ...
    crosswalks: ...
    required_resources: ...
    warnings: ...
```

Names may differ. The requirement is one shared plan for one rule.

Examples of hidden dependencies the planner must carry until no longer needed:

- `_source_path`;
- `year`;
- `_competencia`;
- source namespace/key needed for enrichment;
- raw fields needed to resolve dimensions even if not requested in final output.

Only strip these after semantic operations complete.

---

# 18. Structural-null metadata

The user-facing union schema should remain concise while preserving the distinction between:

```text
field did not exist in this generation
```

and:

```text
field existed but this record is null
```

Implement at least two channels:

1. `QueryReport.structural_absence`, mapping fields to affected families/periods;
2. Arrow schema/table metadata where practical, e.g. a compact JSON under a Pegasus-specific metadata key.

Do not emit one boolean structural-absence column per data field by default; that would bloat wide datasets and defeat the ergonomic goal.

Provide an advanced option if researchers explicitly need row-level structural-presence indicators.

---

# 19. Resource updates versus Python package releases

DATASUS evolves continuously. Do not make Python versioning carry every source-tree change.

Design compatibility such that:

```text
code version
resource schema version
resource content version
```

are separate.

A new FTP file that follows known grammar/schema requires no resource release.

A new codelist vintage, corrected mapping, new dataset alias, or adjudicated semantic relation may warrant a new resource content build.

A breaking change in artifact schema requires a resource schema version and code compatibility check.

Initially resource updates may remain manual. Later `resources update` can query a release manifest.

Do not build an always-online update service as a prerequisite for this phase.

---

# 20. User-facing examples that the redesign must support

## 20.1 Basic query, no source mechanics

```python
import pegasus_data as pg

t = pg.query(
    "SIM-DO",
    period=("2018", "2024"),
    geography="AL",
)
```

User does not care whether files are annual/monthly or whether data came from cache/lake/FTP.

## 20.2 Subannual request against annual source

```python
t = pg.query(
    "SOME-ANNUAL-DATASET",
    period=("2024-03", "2024-06"),
)
```

If exact row filtering is impossible:

```text
TimeResolutionWarning:
requested 2024-03..2024-06; source supports annual resolution only;
effective period expanded to 2024.
```

Result is returned rather than failing.

## 20.3 Longitudinal evolving schema

```python
t = pg.query(
    "SIH-RD",
    period=("1995", "2024"),
    select=["DIAG_PRINC", "DIAGSEC1"],
)
```

`DIAGSEC1` is structurally null in generations where absent. Report identifies those periods.

## 20.4 Identity translation

```python
t = pg.query(
    "SIH-RD",
    period="2024-01",
    geography="AL",
    select=["MUNIC_RES", "DIAG_PRINC"],
    labels=True,
)
```

Returns:

```text
MUNIC_RES
MUNIC_RES_label
DIAG_PRINC
DIAG_PRINC_label
```

No health-region/chapter roll-ups masquerading as labels.

## 20.5 Dimensions

```python
t = pg.query(
    "SIH-RD",
    period="2024",
    geography="AL",
    select=["MUNIC_RES", "DIAG_PRINC"],
    dimensions=[
        "MUNIC_RES.health_region",
        "DIAG_PRINC.chapter",
    ],
)
```

## 20.6 Simple CNPJ enrichment

```python
t = pg.query(
    "SIH-RD",
    period="2024",
    geography="AL",
    select=["CNES", "CNPJ", "DIAG_PRINC"],
    enrich=["CNPJ"],
)
```

If the route `CNES → CNPJ` is uniquely declared, Pegasus uses it automatically.

Returns additive fields such as:

```text
CNES
CNPJ                    # original DATASUS
CNPJ_resolved
CNPJ_resolution_status
```

## 20.7 Explicit enrichment route

```python
t = pg.query(
    "SIH-RD",
    period="2024",
    select=["CNES"],
    enrich=[pg.enrichment("CNPJ", from_field="CNES")],
)
```

## 20.8 Registry enrichment requiring local data

```python
t = pg.query(
    "SIH-RD",
    period="2024-01",
    select=["CNES"],
    enrich=["CNES.establishment_name", "CNES.nature"],
)
```

Planner determines these require CNES registry data for the relevant competence. It should obtain/build the smallest necessary slice according to configured resource policy, not force a full-history CNES build.

## 20.9 Explain before executing

```python
plan = pg.plan(
    "SIH-RD",
    period=("2010", "2024"),
    geography="AL",
    enrich=["CNPJ"],
)
print(plan.explain())
```

---

# 21. Backward compatibility and expert controls

Do not delete useful low-level capabilities.

The current knobs such as:

```text
historical_labels
allow_borrowed_labels
allow_partial
on_missing_column
refresh
```

remain valuable for experts/tests.

The new high-level API should select safe defaults and hide most of these from normal workflows.

For example:

```text
high-level semantics="safe"
```

can correspond internally to:

```text
cross-system borrowing disabled
historical vintage preferred with reported fallback
partial acquisition refused
schema union + structural null
crosswalk conflicts not silently chosen
```

Do not add a vague `semantics="safe"` flag unless it actually reduces parameter clutter; the primary goal is sane defaults rather than another magic knob.

---

# 22. Testing strategy for the architectural upgrade

The previous project history proves that report-level tests alone are inadequate. Acceptance must assert actual output values and row behavior.

## 22.1 Representation tests

- one logical publication, multiple formats → one contribution;
- different publications with identical schema → both retained;
- representation conflict → no silent deduplication.

## 22.2 Time planner tests

- exact monthly source;
- annual source + row-level month → exact row filter;
- annual source without row-level month → adapted annual result + warning;
- actual missing publication remains a failure/partial-data condition rather than “adaptation.”

## 22.3 Structural-null tests

- field present in later generation only;
- output schema constant across batches;
- structural nulls inserted;
- report metadata names absent generations;
- true row-null and structural-null both represented as null in table but distinguishable in report.

## 22.4 Semantic relation tests

Use real-style examples:

```text
municipality label ≠ health region roll-up
ICD exact label ≠ ICD chapter
```

`labels=True` must never emit roll-up output as the label.

## 22.5 Adjudication tests

- large ambiguous candidate set → runtime safe refusal/raw code;
- work item exists;
- applying a curation decision removes runtime ambiguity without changing ranking code;
- exact rendered value asserted.

## 22.6 CNES↔CNPJ tests

Cover:

- valid raw CNPJ only;
- placeholder raw + unique crosswalk;
- valid raw + agreeing crosswalk;
- valid raw + conflicting crosswalk;
- multiple crosswalk targets in same applicable window;
- one CNPJ → multiple CNES in reverse lookup;
- row count unchanged in default enrichment;
- explicit explode/join required for multiplicative relation;
- competence chooses historical relation correctly.

## 22.7 Storage tests

- packaged-resource size report generated in CI;
- crosswalk remains within expected order of magnitude;
- no accidental registry inclusion in label pack;
- no multi-hundred-MB resource growth without explicit test/budget update.

## 22.8 End-to-end output inspection

Maintain a small set of real DATASUS smoke queries whose exported CSV/Parquet values are directly asserted or reviewed. The project's municipality incident demonstrated that “label coverage = 100%” can still mean the wrong label.

At minimum retain known-good assertions such as municipality code→municipality label, not merely “non-null label.”

---

# 23. Documentation redesign

Update documentation so users learn the conceptual API, not the FTP internals first.

README primary workflow should teach:

```text
query dataset
choose period/geography
select columns
labels
optional dimensions
enrichment
explain/report
```

Move `years`, `months`, family/schema generation, codelist selection, borrowing policies, FTP axes and resource staging into advanced/reference sections.

Document clearly:

- raw fields are preserved;
- labels are identity-preserving;
- dimensions change analytical granularity;
- crosswalks change identifier namespace and may have non-bijective cardinality;
- enrichment is additive;
- structural null means a field may not have existed in older schemas;
- time requests may be adapted with warnings when source resolution is coarser;
- large registries can be materialized locally;
- shipped resources are compiled semantic state, not the full maintainer catalog.

---

# 24. Specific current-tree follow-ups to inspect before implementation

Codex must verify these against the post-patch tree, not assume them from the pre-patch snapshot.

1. **Representation preference execution:** determine whether `preferred_representation()` / `representations` metadata is actually used by both `fetch` and `build`. If not, implement logical-publication grouping.
2. **Crosswalk runtime:** determine whether `labels_crosswalk.parquet` now has any runtime reader. The previous tree appeared to build/ship it without exposing it.
3. **Crosswalk temporal loss:** inspect the finished patch's crosswalk compiler. The label pack was made vintage-aware, but ensure crosswalk rows also retain temporal/system/provenance facts rather than overwriting `(codelist, code)` entries.
4. **API source divergence:** do not create another independent planner in `query()`. Build `QuerySpec` and use shared planners underneath existing fetch/load/scan/export paths.
5. **Resource manifest:** inspect existing `manifest.json`/bundle machinery before inventing another manifest format.
6. **Ontology aliases:** add collision validation if absent.
7. **Structural-null defaults:** determine compatibility impact before changing existing `load/fetch` defaults; new high-level query path can adopt union defaults first.
8. **Existing join declarations:** integrate the new crosswalk/enrichment model with `joins.yml` rather than creating an unrelated second join ontology.
9. **Curation schema:** reuse current variable YAML infrastructure where possible, but extend it to typed semantic relations instead of maintaining both flat and typed sources indefinitely.
10. **Storage:** run `dbstat` on the recovered ~15 GB catalog before any destructive/rebuilding changes and record evidence.

---

# 25. What NOT to do

Do not:

- full-scan terabytes merely to prove two Ministry files with the same logical publication stem are probably alternative representations;
- merge different systems/series by schema similarity;
- encode speculative epidemiological subset/revision claims as dataset identity;
- let a runtime candidate cap decide semantic truth;
- leave runtime ambiguity unresolved forever without creating a maintainer work item;
- overwrite raw DATASUS identifiers with linked/resolved values;
- allow a crosswalk enrichment to multiply fact rows by default;
- ship huge entity registries merely because they are useful;
- force every user to rebuild the maintainer semantic catalog;
- release a new Python package merely because the FTP tree changed;
- add indexes to massive SQLite tables without a measured query and byte-cost justification;
- recreate range-expanded semantic storage if a compact rule/run representation is sufficient;
- expose source-specific `years`/`months` mechanics as the only way to express time;
- fail a user simply because their requested time precision is finer than source publication resolution when a safe adaptation can be made and warned;
- return a broader geography silently when the requested geography cannot be represented;
- create a new planner separately for each public entry point.

---

# 26. Acceptance criteria for this phase

This architectural upgrade is complete only when all of the following are true.

## Runtime/API

- a new user can query a dataset with one `period=` argument without knowing source temporal indexing;
- temporal precision mismatch adapts with explicit requested/effective period warning rather than default failure;
- longitudinal schema evolution defaults to interpretable union/structural-null behavior on the primary API;
- `labels=True` performs identity labels only;
- dimensions are requested independently;
- `enrich=["CNPJ"]` is intuitive and works when a unique declared route exists;
- advanced explicit enrichment route is available;
- raw source columns remain untouched;
- CNPJ resolution is additive and auditable;
- default enrichment cannot increase row count;
- cardinality/conflict statistics are reported;
- optional large registries can be built/fetched locally through a coherent resource interface;
- `plan(...).explain()` or equivalent makes adaptations and resource needs inspectable.

## Semantics

- flat codelist bindings are no longer the only representation of semantic relationships;
- at least `label_of`, `rollup_to`, `attribute_of`, `crosswalk_to` are modeled;
- ambiguous runtime mappings create adjudication work;
- AI/manual adjudication can write an explicit decision and compile it into runtime state;
- ontology aliases cannot collide silently.

## Representation safety

- one logical publication contributes one preferred physical representation;
- different datasets/series are not merged from schema similarity;
- representation conflict can be recorded and prevents silent deduplication.

## Crosswalk safety

- CNES↔CNPJ temporal/cardinality properties are empirically measured and documented;
- shipped crosswalk retains enough validity/provenance to prevent historical mis-linkage;
- reverse one-to-many behavior is explicit;
- conflicts do not silently choose one identifier.

## Storage

- live maintainer catalog storage is measured by table/index using `dbstat`;
- causes of the ~15 GB footprint are documented with byte counts rather than guesses;
- packaged resources have CI size accounting;
- no fat label/entity registry is accidentally shipped;
- runtime artifacts remain compact;
- any maintainer-catalog redesign demonstrates measured savings and preserves provenance.

## Quality

- full pre-existing suite remains green;
- new tests assert actual returned values and row multiplicity, not just source tokens/report counters;
- Ruff/compile/diff checks remain clean;
- architecture, README, FINDINGS/DEFECTS/RESUME are updated without creating duplicate state ledgers.

---

# 27. Final design philosophy

Pegasus should become an **intent-driven analytical client backed by a semantic compiler**, not an FTP tree with increasingly clever convenience functions.

The difficult work belongs upstream:

```text
measure → investigate → adjudicate → compile
```

The user's operation should remain simple:

```python
pg.query(
    "SIH-RD",
    period=("2015", "2025"),
    geography="AL",
    select=["CNES", "DIAG_PRINC", "MUNIC_RES"],
    labels=True,
    dimensions=["MUNIC_RES.health_region"],
    enrich=["CNPJ"],
)
```

Internally Pegasus may have to:

- adapt source time granularity;
- choose among schema generations;
- retain hidden provenance;
- choose one physical representation;
- decode legacy formats;
- structurally null-fill fields;
- select vintage-specific identity labels;
- derive requested roll-ups;
- resolve a temporal CNES→CNPJ crosswalk;
- inspect local resource availability;
- record conflicts and warnings.

The user should not have to know any of that unless they ask `explain()`.

That is the target architecture.
