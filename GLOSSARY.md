# GLOSSARY.md

One paragraph per term, in plain language, **with the failure it prevents**. A
definition that does not name a failure is not pulling its weight. Terms are
grouped by where they first matter: the tree, meaning, retrieval, aggregates.

---

## The tree and its inventory

**DATASUS.** The Ministry of Health's IT department, which publishes the
administrative records of Brazil's public health system as files on
`ftp.datasus.gov.br`. It publishes no index and no machine-readable schema.
*Prevents:* treating the FTP layout as a contract. It is an observation, and it
changes.

**System.** One of DATASUS's information systems: SIH (hospital admissions),
SIA (outpatient production), SIM (deaths), SINASC (live births), SINAN
(notifiable diseases), CNES (establishments) and about fourteen more. A system
is declared in `curation/ontology.yml` and is recognised in the tree by its
filename prefix. *Prevents:* decoding a code against the wrong system's table.
`SEXO=3` is Feminino in SIH and undefined in SINASC, so every codelist is keyed
by its system (ADR-0021).

**Dataset.** One kind of record a system publishes, such as `SIH.RD` (AIH
Reduzida, one row per admission) or `CNES.ST` (one row per establishment per
month). A dataset is an institutional declaration, not a directory: it may be
spread over many files, several trees and several formats, and it states what
one row is. *Prevents:* `fetch("SIA-AC")` returning nothing while reporting
success because a string match found none of its spellings (ADR-0033).

**Series.** The dataset code as it is spelled in filenames, before the
ontology binds it (`RD`, `PASP2509A`, `SISCAN_CITO_COLO_2013`). Only 181 of
1,505 observed spellings are clean codes. *Prevents:* using a spelling as an
identity.

**Binding (ontology).** The mapping of an observed `(system, series)` pair onto
a declared dataset, recording which rule fired (declared alias, filename,
archive member, year suffix, template). An ambiguous bare code binds to
neither dataset. *Prevents:* rows filed silently under a dataset they do not
belong to. Not to be confused with a codelist binding (below).

**Ontology.** The declared systems and datasets in `curation/ontology.yml`,
with the rules that bind the crawl to them (`ontology.py`). A dataset may have
zero files. *Prevents:* identity that changes whenever DATASUS reorganises the
tree.

**UF.** *Unidade federativa*, one of Brazil's 27 states (including the Federal
District), written as two letters (`AC`) or a two-digit code (`12`). Most
DATASUS files are split by UF in the filename. *Prevents:* reading a UF
restriction as a filter on patients' residence; in `query()` a UF selects the
files published for that state (ADR-0043).

**Competência.** The month a record was billed or reported (`AAAAMM`), which
is the coordinate DATASUS publishes by. It is not the date of the event: an
admission in December is billed in January, and 7.44% of the admissions in
Acre's 2022 SIH file happened in 2021. *Prevents:* inferring record time from
the publication coordinate. `_competencia` is immutable provenance.

**Publication coordinate.** Where a record sits in DATASUS's publication
scheme: system, dataset, UF, competência or year, archive member. `query()`'s
`period` and `geography` select publications by these coordinates.
*Prevents:* a period silently becoming a filter on `DT_INTER` or `DTOBITO`, or
a UF becoming a filter on `MUNIC_RES` (ADR-0043).

**Stratum.** `(system, series, year)`, the unit of schema evidence: one census
entry records which schema its files carry. *Prevents:* concluding a schema
from one file (defect D2).

**Schema signature.** A hash of a file's ordered field list, names and types.
Two files with the same signature share a column layout. *Prevents:* pooling
files whose columns differ as though they were one table.

**Schema generation.** One schema signature within a dataset, reported with
the columns added and dropped against the previous one. SIH-RD has twenty,
from 35 to 114 columns. *Prevents:* pooling years across a boundary where a
column appears or changes meaning; "113 columns, 2014–2025" does not say that,
"+6, −1 at this boundary" does.

**Family.** `(system, series, schema_signature)`, the unit of data: one family
spans every year that shares a layout. A schema change starts a new family.
*Prevents:* one schema change corrupting a whole series, and one dataset
splitting in two because it is published in two formats.

**Representation.** One physical form of a family's data: `.dbc`, `.csv.zip`,
`.duck`, a member of an archive. One global selector chooses the cheapest
readable form per logical publication, and a contradiction between forms is
recorded as a conflict and refused. *Prevents:* reading the same publication
twice and duplicating facts (ADR-0047).

**Archive member.** One file inside a container: an APAC `.exe` holds seven
DBF members, seven datasets. Members are first-class rows. *Prevents:*
keeping one "best" member and discarding six datasets.

**Header census.** Reading every stratum's schema from the first few KB of a
file (the DBF header, stored uncompressed ahead of a `.dbc` payload) by a
ranged fetch. 19.23 MB instead of 183 GiB of decodes. A census stratum is
marked `'header'`, never `'ok'`. *Prevents:* a sampled schema catalogue, and
"we know the columns" being read as "we know what is in them" (ADR-0024).

**Blob.** A fetched file, stored in `blobs/` under the SHA-256 of its content.
*Prevents:* downloading the same bytes twice when DATASUS moves or mirrors a
file (ADR-0004).

**Catalog.** The SQLite database (`_catalog/catalog.sqlite`) holding
everything discovered, decided or left open: files, strata, families,
dictionary, bindings, curation, open questions, build outcomes. The
maintainer's full catalog was about 15 GB; it is Tier C and does not ship.
*Prevents:* re-deriving upstream facts downstream. A catalog whose tables
disagree with the shipped schema is refused, not migrated.

**Lake.** The Parquet store of decoded records,
`lake/<system>/<family_id>/uf=<UF>/year=<YYYY>/`, plus reference tables under
`lake/reference/`. Each partition is replaced whole and staged. *Prevents:*
decoding the same state-year again, and a rebuild landing beside its own stale
output.

**Coverage gap.** A recorded row saying something could not be read: a
directory that would not list, a file that timed out or would not decode.
*Prevents:* a failure becoming an absence. Missing is not zero.

## Meaning

**Codelist.** A table from code to label, such as `SEXO.CNV` or `CID10`. It
belongs to a system and a validity window, and it is bound to fields
separately, because one codelist serves several fields. *Prevents:* the
1,339,916 spurious "conflicts" produced by treating codes as columns
(ADR-0011).

**Codelist binding.** A row in `field_codelists` saying a codelist can decode
a field, with its source, confidence and measured decode rate. `.DEF` binds
generously (145 tables to one municipality column), so bindings are measured,
dead ones withheld, and the ones that matter declared in curation.
*Prevents:* a column labelled by a table that decodes none of its values, or
by a health-region table where a municipality was asked for (ADR-0031,
ADR-0041).

**Vintage / validity window.** The period for which a codelist row is true,
`valid_from`/`valid_to`, read from a kit's filename (`TAB_SIH_199201-199712`).
Codes are reworded and reassigned, and municipalities are created and merged.
A source vintage is an interval: a month, a whole year, or unknown.
*Prevents:* labelling a 1998 record with today's municipality table, which
resolves every code to the wrong place, and treating a year as December
(ADR-0048).

**CNV.** TabNet's codelist format: a header with the number of categories and
the code width, then label and match-expression rows. The last matching rule
wins. *Prevents:* labelling every record "Ignorado" by reading first-match.

**DEF.** TabNet's tabulation definition: which data files it reads (`A`),
which fields tabulate as rows, columns or selections against which `.CNV`, and
which are additive measures (`I`, the Ministry's own statement that a variable
is summable). *Prevents:* guessing which codelist a field uses. It also
declares tabulation axes as if they were code systems, which is why its
bindings are measured.

**TAB kit.** A `TAB_<SYSTEM>*.zip` (or `.rar`) bundle of `.CNV`, `.DEF` and
lookup `.DBF` files for DATASUS's DOS tabulator. Its filename names its
validity window. *Prevents:* missing the dictionary DATASUS did publish
(defect D7), and mixing a 1990s kit's mappings with the current one.

**TabNet / TabWin.** DATASUS's tabulation programs (web and desktop). Their
published tables are the independent figure a count is checked against, and
their files are the richest source of meaning on the tree. *Prevents:*
declaring a number right because it looks plausible.

**Authority ladder.** The order in which claims about meaning are merged,
lowest number winning: `manual`(0), `cnv`/`layout_doc`(1), `def`(2),
`sigtap`(3), `dbf_lookup`(4), `demas_api`(5), `pdf`(6), `community` and
`semantic_match`(7), `inferred`(8). *Prevents:* a community transcription or
an inference overriding the publisher, and a source conflict being resolved
silently (ADR-0008).

**Curation.** The version-controlled YAML under `src/pegasus_data/curation/`:
what each system and dataset is, what one row is, each variable's meaning and
decoder, join keys, geography roles, aggregate recipes. It is the `manual`
rung and outranks every extraction, and a changed fingerprint reloads it into
an existing catalog. *Prevents:* human judgement having no way in, and a
correction in the wheel never reaching a catalog built before it (ADR-0018).

**Code system (`code_system`).** A per-variable rendering rule: `internal`
(the label replaces the code), `external` (code and label, because the code is
a join key such as a municipality or ICD code), `none` (as typed). *Prevents:*
a municipality column losing its joinable code, or a contradictory table being
applied to a column curation marked unbound.

**Label pack.** `resources/labels.parquet`, the semantic layer compiled small
enough to ship: 3,654,320 versioned label runs across 2,238 codelists, about
30 MB. Registries are held back by declared role. *Prevents:* a fresh install
returning data with no meaning attached, as `fetch("SIM-DO")` once did
(ADR-0037).

**Codelist role.** What kind of thing a codelist is, declared in
`curation/codelists.yml`: `enumeration`, `classification`, `geography`,
`registry` (held back), `crosswalk`. *Prevents:* a size cap that keeps 450
municipal roll-ups and drops CID10.

**Undecoded.** A code with no mapping, left as the raw code and reported as a
named, countable gap (`categorical_undecoded`). *Prevents:* a plausible guess,
which is worse than a gap because nothing downstream can see it (ADR-0009).

**Sentinel.** A code meaning "unknown", "ignored", "abroad" or "state-level",
such as `9`, `999999` or `120000`. Sentinels are per field: `9` is missing in
one column and a category in another. In geography they are members, not
dropped rows. *Prevents:* a global sentinel rule that deletes real categories,
and counts that shed their unknowns.

**Constant column.** A column holding one value on every non-null row, such as
`DIAG_SECUN = '0000'` in SIH's current generation. It is flagged, not labelled.
*Prevents:* 3,784 rows of a retired placeholder being counted as data.

**Availability (present / absent / unknown).** Whether a column exists in a
dataset in a given year: carried by a decoded schema, positively not carried,
or not known because nothing was decoded. *Prevents:* a structural absence,
such as `DIAGSEC4` before 2014, read as clinical missingness (ADR-0034).

**Relation (semantic).** A typed statement about a field: `label_of` (its
identity label), `rollup_to` (a coarser level, such as municipality → health
region), `attribute_of` (a property, such as "is a capital"), `crosswalk_to`
(another identifier). Only `label_of` becomes an automatic label. *Prevents:* a
roll-up replacing a municipality's name (ADR-0044).

**Adjudication.** The queue in which unresolved semantic uncertainty becomes a
work item with its evidence: `pegasus-data adjudicate show|export|apply`
records a reviewed decision as a local relation. *Prevents:* a truncated
ranking or a silent guess deciding meaning because a cost cap was reached.

**Dimension.** A requested derived column over a field, such as
`MUNIC_RES.health_region` or `DIAG_PRINC.chapter`, produced from a `rollup_to`
or `attribute_of` relation valid for each row's vintage. *Prevents:* roll-ups
appearing uninvited as labels, and one current table rewriting historical
categories.

**Crosswalk.** A mapping from one identifier to another, such as CNES↔CNPJ,
requested explicitly as an enrichment. It keeps the raw value, is temporal,
returns null with a status on ambiguity, and changes row count only when asked
(`explode=True`). *Prevents:* overwriting an observed identifier or
multiplying fact rows through a default join (ADR-0045).

**Join key.** An identifier shared across datasets (AIH, CNES, APAC), declared
in `curation/joins.yml` with each side's rows per key and the axis it is
versioned by. *Prevents:* counting professional acts while believing you
counted admissions, and joining a 2015 admission to today's hospital record.

**Personal identifier.** A column holding a CPF, CNS, name, birth date or
postcode. It passes through unmodified and is flagged. *Prevents:* a library
hiding the evidence that the Ministry publishes identifiable data
(ADR-0032).

**Semantic axes.** The curated statement of which column in a dataset carries
the geography and the time, and what role each plays (`residence`,
`occurrence`, `facility`, …). Axes inherit within a system; grain does not.
*Prevents:* an aggregate keyed on the hospital's municipality presented as the
patients' (ADR-0053).

## Retrieval and packaging

**`fetch()` / `load()` / `query()` / `plan()`.** `fetch()` retrieves
source-shaped rows from DATASUS in one call; `load()` reads a built lake;
`query()` is the front door that plans publication selection, lake or fetch,
labels, dimensions and enrichments; `plan()` returns that plan without running
it. *Prevents:* a caller needing to know DATASUS's file layout to get a table,
and a short table returned quietly (the report names what could not be done).

**Structural absence.** A selected column that a schema generation does not
carry, null-filled and listed in the query report and Arrow metadata.
*Prevents:* a union across generations hiding which years could not have held
the value.

**Bundle.** A packed copy of the semantic layer (`pegasus-data pack`) for use
without a crawl, restored additively and by column name. *Prevents:*
translation depending on the FTP server being up.

**Resource tiers.** A: shipped code, curation and bootstrap resources. B:
compiled runtime semantics (label pack, crosswalk, bindings, query
capabilities). C: maintainer build state, never shipped. D: user-local state
(blobs, lake, optional registries). Each runtime resource has a manifest entry
with version, checksum, size and budget. *Prevents:* the choice between
shipping 15 GB and making every user rebuild it (ADR-0046).

**Staging.** Writing a replacement beside its target under a unique token and
swapping it in by rename, keeping the old one aside for rollback, one
reader-visible unit (a partition directory) at a time. *Prevents:* an
interrupted rebuild leaving nothing where the data was (ADR-0038).

## Aggregates and the frontend

**Grain.** What one row of a dataset is: an admission, a death, an
establishment-month. *Prevents:* `COUNT(*)` meaning establishments where it
counts establishment-months.

**Measure.** A declared quantity in an aggregate recipe (`admissions`,
`deaths`, `los`, `beds`), with its kind (`count`, `sum`, `mean`, `ratio`,
`min`, `max`), source columns and per-axis additivity. *Prevents:* a measure
merged along an axis where it does not add up.

**Accumulator state (monoid).** What an aggregate stores instead of a finished
number: `los_n` and `los_sum`, not a mean. Each kind's state merges by a
commutative, associative operation with an identity (a monoid), so any roll-up
is a merge. *Prevents:* the mean of means, and totals that are not the sum of
their parts (ADR-0050).

**Pushforward.** Applying a map of keys (municipality → health region, sex →
Total) to cells and merging the states that land on the same key. Valid only
when the map is total and single-valued; otherwise the unmapped mass is
reported or the roll-up refused. *Prevents:* 70 admissions in metropolitan
regions presented as the national figure.

**Cuboid / base cuboid.** One choice of level per dimension is a cuboid; the
artifact materialises only the finest (base) one, and every other view is
derived from it. *Prevents:* a "Total" computed separately that disagrees with
the sum of its categories.

**Stock vs flow.** A flow happens during a period (admissions) and adds up
over time. A stock is a level at an instant (beds, rooms) and does not: summed
over months it becomes "bed-months". Stocks are refused over time
(ADR-0051). *Prevents:* installed rooms summed across months and reported as
"room-months".

**Recipe (aggregate spec).** A YAML file under `curation/aggregates/` naming a
dataset, its geography and time bindings, dimensions and measures.
`aggregate-suggest` reports the evidence for choosing dimensions and does not
write the recipe. *Prevents:* thin descriptors making a generic frontend a
window onto almost nothing, and a dimension chosen without knowing its cost.

**Artifact.** A built aggregate: its cells, a manifest recording every
qualifier the build applied (UF scope, years, partial periods, support) and a
fingerprint over spec, source digests, curation, engine and geography.
*Prevents:* an Acre-only build shown as Brazil (ADR-0057), and a stale roll-up
nobody can detect.

**Support mask.** Which cells could have been observed at all, from column
availability and the build's scope. *Prevents:* "not observed" rendered as
zero.

**Membership.** Which supramunicipal unit a municipality belongs to, compiled
per classification, publishing system and window, with the authority (IBGE or
DATASUS) that defines it. *Prevents:* a roll-up through one system's
regionalisation reported against another's TabNet totals (ADR-0049,
ADR-0052).

**Capabilities.** The descriptor `capabilities()` projects for the frontend:
datasets, dimensions and their levels, measures as components and a formula,
roll-up targets, spatial coverage, denominator compatibility. It decides
nothing; every fact comes from its owning module. *Prevents:* a UI control
that is drawn and does nothing, and a descriptor that drifts from the specs
(ADR-0054).

**Denominator compatibility.** Whether a population denominator is valid for
a geography role: yes for `residence`, `patient`, `area`; no for facility or
occurrence roles. *Prevents:* a small town with a regional hospital shown at
several times its real risk (ADR-0055).

**`serve/`.** The HTTP transport over the library for `../pegasus_view`
(`/health`, `/datasets`, `/datasets/{a}/capabilities`, `/population`,
`/geo/membership`, `/records`). It shapes the wire (7-digit municipality codes,
codes and labels sent apart) and holds no logic; `/records` is off unless the
server starts with `--allow-records`. *Prevents:* the frontend growing a branch
per dataset, and identifiable rows exposed on a network by default.

## Record linkage

**Record identity.** `(_blob_sha256, _row)`: the content hash of the source
file and the record's ordinal in it, counted before any filtering. Survives
re-downloads because the blob store is content-addressed. *Prevents:* a link
that points at "row 12 of today's query" (ADR-0107).

**Role.** The property a column states about an entity, `<entity>.<property>`:
SINASC `DTNASCMAE` is `mother.birth_date`; SIH `NASC` is `patient.birth_date`.
Declared in `curation/roles.yml` with a type that says how the value is
normalised. *Prevents:* comparing columns by name, and linking a baby to its
mother's admission because both carry "a birth date" (ADR-0109).

**Link spec.** A declared linkage in `curation/links.yml`: two sides, passes,
the negative control and held-out validations. *Prevents:* a linkage that
exists only in a notebook and cannot be re-run at another scope (ADR-0110).

**Pass.** One 1:1 join on one key, in a cascade from strictest to loosest; each
pass sees only the records earlier passes left unlinked. *Prevents:* a loose
key claiming records a strict key would have linked correctly.

**Negative control.** The same pass over the same remaining records, with one
key deliberately shifted (a birth date by 7 days). Every pair it finds is a
coincidence, so its count estimates the chance pairs in the real pass.
*Prevents:* mistaking coincidences for links; two linkages with similar raw
counts can be 0.1% and 58% chance.

**Chance rate.** Control pairs as a percentage of real pairs, per pass and over
the kept passes. *Prevents:* reporting a link count without its error.

**Verdict.** Viable (every kept pass ≤ 5% chance, best held-out agreement
≥ 90%), use with caution (≤ 20%, ≥ 75%), not viable; fixed before any result
(ADR-0107). *Prevents:* thresholds tuned to make a result look good.

**Bits of identity.** The entropy of a key: how many yes/no questions it
answers. Singling out one of N records takes log2(N) bits; a key short of that
leaves collisions. *Prevents:* building a linkage that cannot be unique in
principle (ADR-0107).
