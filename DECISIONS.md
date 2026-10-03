# DECISIONS.md

The index of this project's decisions. Each decision is one file under
`docs/decisions/`, named `ADR-NNNN-<slug>.md`; read the index, then the entries
you need.

**Append-only.** Never edit a decision's substance; to reverse one, write a new
ADR that says what it supersedes. A later note on an entry's status line is
allowed and dated. Each entry states the context with its evidence, the
decision, the alternatives where they were recorded, and **what evidence would
overturn it**.

**Status** here is derived from the entries themselves: `superseded` when a
later ADR says it supersedes this one; `retired` when the thing it governed was
removed (ADR-0040's single-bookkeeper architecture document, frozen by
ADR-0001). `relations` lists what the entries say of each other (supersedes,
amends, and the inverse).

ADR-0002 to ADR-0060 were **backfilled on 2026-09-28** from the August 2026
record frozen under `docs/history/` (the architecture document, `FINDINGS.md`,
`DEFECTS.md`, `HANDOFF.md`, the aggregate design notes) and from the commit
log. Each is dated by the commit or document that took the decision, and
cites them. They are numbered in that order, which is why ADR-0001, dated
last, comes first.

| ADR | date | decision | status | relations |
|---|---|---|---|---|
| [ADR-0001](docs/decisions/ADR-0001-documentation-follows-the-pharos-model.md) | 2026-09-28 | Documentation follows the PHAROS model; the old documents are frozen | active |  |
| [ADR-0002](docs/decisions/ADR-0002-a-listing-that-cannot-be-read-is-an-error.md) | 2026-08-18 | The listing method is chosen per directory and recorded; a listing that cannot be read is an error, not an empty directory | active |  |
| [ADR-0003](docs/decisions/ADR-0003-no-https-mirror-ftp-is-the-transport.md) | 2026-08-18 | There is no HTTPS mirror; FTP is the transport | active |  |
| [ADR-0004](docs/decisions/ADR-0004-blobs-are-content-addressed.md) | 2026-08-18 | Fetched files are stored content-addressed by SHA-256 | active |  |
| [ADR-0005](docs/decisions/ADR-0005-readers-dispatch-by-content-probe.md) | 2026-08-18 | Readers dispatch by content probe, not by suffix | active |  |
| [ADR-0006](docs/decisions/ADR-0006-a-family-is-system-series-schema.md) | 2026-08-18 | A family is (system, series, schema signature); format is a representation, and an archive member is a dataset | active |  |
| [ADR-0007](docs/decisions/ADR-0007-dbc-is-decoded-by-the-datasus-dbc-wheel.md) | 2026-08-18 | `.dbc` files are decompressed by the third-party `datasus-dbc` wheel | superseded | superseded by ADR-0059 |
| [ADR-0008](docs/decisions/ADR-0008-meaning-is-merged-by-a-source-authority-ladder.md) | 2026-08-18 | Claims about meaning are merged by a source-authority ladder | active |  |
| [ADR-0009](docs/decisions/ADR-0009-never-guess-a-code-undecoded-is-visible.md) | 2026-08-18 | Never guess a code's meaning; an unmapped code is undecoded, visibly | active |  |
| [ADR-0010](docs/decisions/ADR-0010-sentinels-are-per-field-and-the-raw-value-is-kept.md) | 2026-08-18 | Normalization is typed per field; sentinels are per field; the raw value survives its label | active | amended by ADR-0063 |
| [ADR-0011](docs/decisions/ADR-0011-codes-belong-to-codelists-with-validity-windows.md) | 2026-08-18 | Codes are stored per codelist, bound to fields, and carry a validity window | active |  |
| [ADR-0012](docs/decisions/ADR-0012-the-labelling-codelist-is-chosen-by-observed-coverage.md) | 2026-08-18 | The codelist that labels a field is chosen by observed coverage | active | amended by ADR-0041; amended by ADR-0072 |
| [ADR-0013](docs/decisions/ADR-0013-the-date-convention-is-inferred-per-directory.md) | 2026-08-18 | A filename's date convention is inferred per directory, by the dominant pattern | active | amended by ADR-0065 |
| [ADR-0014](docs/decisions/ADR-0014-labels-are-joined-at-read-time-not-frozen-into-the-lake.md) | 2026-08-18 | Classification labels are joined at read time from vintage-scoped reference tables, not frozen into the lake | active |  |
| [ADR-0015](docs/decisions/ADR-0015-codes-match-at-exact-width.md) | 2026-08-18 | Codes match at exact width; a mixed-width table is split by width, never padded | active | amended by ADR-0062 |
| [ADR-0016](docs/decisions/ADR-0016-derived-state-is-replaced-never-accumulated.md) | 2026-08-18 | Derived state is replaced, never accumulated; a catalog that disagrees with its schema is refused | active |  |
| [ADR-0017](docs/decisions/ADR-0017-identity-comes-from-the-filename-not-the-path.md) | 2026-08-18 | System identity comes from the filename, not the path; the prefix map is learned, held, and settled by a person | active | amended by ADR-0065 |
| [ADR-0018](docs/decisions/ADR-0018-curation-yaml-is-the-manual-authority-rung.md) | 2026-08-19 | Curation in version-controlled YAML is the manual authority rung | active |  |
| [ADR-0019](docs/decisions/ADR-0019-sigtap-is-read-from-the-ministrys-own-export.md) | 2026-08-19 | SIGTAP is read from the Ministry's own export, over HTTP, with layout-driven parsing | active |  |
| [ADR-0020](docs/decisions/ADR-0020-cod-idade-stays-unbound-and-idade-anos-is-not-derived.md) | 2026-08-19 | `COD_IDADE` stays unbound, and no `IDADE_anos` column is derived | superseded | amended by ADR-0058; superseded by ADR-0064 |
| [ADR-0021](docs/decisions/ADR-0021-a-codelist-is-keyed-by-its-system.md) | 2026-08-19 | A codelist is keyed by its system, and a codelist that maps one code to two labels is refused | active |  |
| [ADR-0022](docs/decisions/ADR-0022-no-stage-may-hang-silently.md) | 2026-08-19 | No stage may hang silently | active |  |
| [ADR-0023](docs/decisions/ADR-0023-classification-revisions-are-resolved-per-row.md) | 2026-08-19 | Classification revisions are bound together and resolved per row; presence in a bound table outranks shape | active |  |
| [ADR-0024](docs/decisions/ADR-0024-schemas-are-catalogued-by-a-header-census.md) | 2026-08-19 | Every schema is catalogued by a header census from ranged fetches | active |  |
| [ADR-0025](docs/decisions/ADR-0025-community-transcriptions-are-parsed-never-executed.md) | 2026-08-19 | Community transcriptions are parsed, never executed, and rank below every primary source | active |  |
| [ADR-0026](docs/decisions/ADR-0026-fetch-is-one-call-from-datasus-to-a-table.md) | 2026-08-19 | `fetch()` is one call from DATASUS to a labelled table, with every path taken from the catalog | active | amended by ADR-0073 |
| [ADR-0027](docs/decisions/ADR-0027-the-semantic-layer-packs-into-an-offline-bundle.md) | 2026-08-19 | The semantic layer packs into an offline bundle, restored additively and by column name | superseded | superseded by ADR-0075 |
| [ADR-0028](docs/decisions/ADR-0028-the-data-dictionary-is-one-sqlite-database.md) | 2026-08-19 | The generated data dictionary is one SQLite database, not a tree of Markdown pages | superseded | amended by ADR-0069; superseded by ADR-0075 |
| [ADR-0029](docs/decisions/ADR-0029-the-crawled-map-ships-in-the-wheel.md) | 2026-08-19 | The crawled map of the tree ships in the wheel; what ships is what cannot be derived | superseded | superseded by ADR-0067 |
| [ADR-0030](docs/decisions/ADR-0030-an-external-classification-ranks-beside-datasus-not-above.md) | 2026-08-19 | An external canonical classification ranks beside DATASUS's copy, not above it | active |  |
| [ADR-0031](docs/decisions/ADR-0031-a-binding-is-measured-and-a-dead-one-is-withheld.md) | 2026-08-19 | A binding is measured against observed values; one that decodes nothing is withheld | active | amended by ADR-0072 |
| [ADR-0032](docs/decisions/ADR-0032-personal-identifiers-pass-through-unmodified.md) | 2026-08-20 | Personal identifiers pass through unmodified, and stay flagged | active |  |
| [ADR-0033](docs/decisions/ADR-0033-the-ontology-is-declared-and-the-crawl-binds-to-it.md) | 2026-08-21 | Systems and datasets are declared in `curation/ontology.yml`; the crawl is evidence bound to the declaration | active |  |
| [ADR-0034](docs/decisions/ADR-0034-column-availability-has-three-states.md) | 2026-08-21 | Column availability has three states: present, absent, unknown | active |  |
| [ADR-0035](docs/decisions/ADR-0035-joins-are-declared-as-keys-with-grain.md) | 2026-08-21 | Joins are declared as keys with each side's grain, not as dataset pairs | active |  |
| [ADR-0036](docs/decisions/ADR-0036-doubts-are-recorded-in-a-separate-confidence-file.md) | 2026-08-22 | What the project is least sure of is recorded in `docs/CONFIDENCE.md` | superseded | superseded by ADR-0040 |
| [ADR-0037](docs/decisions/ADR-0037-a-label-pack-ships-with-declared-codelist-roles.md) | 2026-08-22 | A windowed label pack ships in `resources/`, and codelist roles are declared, not inferred | active |  |
| [ADR-0038](docs/decisions/ADR-0038-every-replacement-is-staged-and-swapped.md) | 2026-08-22 | Every replacement is staged beside its target and swapped atomically, one reader-visible unit at a time | active |  |
| [ADR-0039](docs/decisions/ADR-0039-decoding-runs-in-killable-worker-processes.md) | 2026-08-22 | Decoding runs in a pool of persistent, killable worker processes | active |  |
| [ADR-0040](docs/decisions/ADR-0040-counts-and-doubts-live-in-the-architecture-document.md) | 2026-08-23 | Counts live only in ARCHITECTURE §21, and doubts in §22 beside them | retired | supersedes ADR-0036 |
| [ADR-0041](docs/decisions/ADR-0041-the-decoder-link-is-declared-and-a-capped-ranking-refuses.md) | 2026-08-23 | The variable-to-decoder link is declared in curation; an uncurated candidate set above the cap is refused | superseded | amends ADR-0012; amended by ADR-0061; superseded by ADR-0072 |
| [ADR-0042](docs/decisions/ADR-0042-labels-are-not-borrowed-across-systems-by-default.md) | 2026-08-23 | Labels are not borrowed across systems by default, and a historical fallback is recorded, not narrated | active |  |
| [ADR-0043](docs/decisions/ADR-0043-period-and-geography-select-publications.md) | 2026-08-23 | `query()` and `plan()` express publication-coordinate intent; period and geography never filter record variables | active | amended by ADR-0073 |
| [ADR-0044](docs/decisions/ADR-0044-semantic-relations-are-typed-and-uncertainty-becomes-work.md) | 2026-08-23 | Semantic relations are typed, and unresolved uncertainty becomes an adjudication item | active | amended by ADR-0061 |
| [ADR-0045](docs/decisions/ADR-0045-cnes-cnpj-is-a-temporal-crosswalk-not-a-label.md) | 2026-08-23 | CNES↔CNPJ is a temporal crosswalk requested as an enrichment, not a label | active |  |
| [ADR-0046](docs/decisions/ADR-0046-resources-are-packaged-in-four-tiers.md) | 2026-08-23 | Resources are packaged in four tiers, each runtime artifact with manifest identity and a lifecycle | active | amended by ADR-0067 |
| [ADR-0047](docs/decisions/ADR-0047-one-selector-chooses-a-representation-per-publication.md) | 2026-08-23 | One global selector chooses a representation per logical publication; a conflict refuses | active | amended by ADR-0068; amended by ADR-0071 |
| [ADR-0048](docs/decisions/ADR-0048-a-source-vintage-is-an-interval.md) | 2026-08-23 | A source vintage is an interval, and an unknown vintage resolves to null, not to "current" | active |  |
| [ADR-0049](docs/decisions/ADR-0049-supramunicipal-geography-is-compiled-scoped-by-system.md) | 2026-08-27 | Supramunicipal geography is compiled from the label pack, keyed by system and window, and health macroregion is not shipped | active |  |
| [ADR-0050](docs/decisions/ADR-0050-aggregates-store-mergeable-state-in-one-base-cuboid.md) | 2026-08-27 | Aggregates store mergeable accumulator state in one base cuboid, built once and served without microdata | active |  |
| [ADR-0051](docs/decisions/ADR-0051-a-stock-is-refused-over-time.md) | 2026-08-27 | A stock measure is refused over time; no time reducer is applied in the core | active |  |
| [ADR-0052](docs/decisions/ADR-0052-ibge-owns-territory-datasus-owns-health-geography.md) | 2026-08-27 | IBGE owns territorial identity; DATASUS owns the health-service geography; every membership says which | active |  |
| [ADR-0053](docs/decisions/ADR-0053-semantic-axes-inherit-within-a-system-grain-never-does.md) | 2026-08-27 | Semantic axes inherit within a system and a file; grain never inherits | active |  |
| [ADR-0054](docs/decisions/ADR-0054-capabilities-is-a-projection-and-serve-is-transport.md) | 2026-08-29 | `capabilities()` is a derived projection, `serve/` is transport, and microdata is off by default | active |  |
| [ADR-0055](docs/decisions/ADR-0055-a-denominator-is-compatible-by-geography-role.md) | 2026-08-29 | Denominator compatibility is a rule over geography roles, not a table over datasets | active |  |
| [ADR-0056](docs/decisions/ADR-0056-a-date-columns-layout-is-measured.md) | 2026-08-29 | A date column's layout is measured from its values, not declared per system | active |  |
| [ADR-0057](docs/decisions/ADR-0057-every-build-qualifier-is-recorded-in-the-manifest.md) | 2026-08-29 | Every qualifier a build applies to its input is recorded in the artifact's manifest | active |  |
| [ADR-0058](docs/decisions/ADR-0058-age-is-banded-per-system-in-aggregates.md) | 2026-08-30 | Age is decoded per system and banded in aggregates, reading only the "years" and "100+" units | active | amends ADR-0020; amended by ADR-0064; amended by ADR-0070 |
| [ADR-0059](docs/decisions/ADR-0059-the-dbc-decompressor-is-first-party.md) | 2026-08-30 | The DBC decompressor is first-party: a PKWare DCL "explode" in C and in Python | active | supersedes ADR-0007; amended by ADR-0074 |
| [ADR-0060](docs/decisions/ADR-0060-a-measure-reads-the-columns-its-dictionary-row-names.md) | 2026-08-30 | A measure's source columns are the ones its dictionary row names; a `sum` may declare several | active |  |
| [ADR-0061](docs/decisions/ADR-0061-one-labelling-policy-for-every-read.md) | 2026-09-28 | One labelling policy for every read; `query()`'s `label_of` gate is removed | active | amends ADR-0044, ADR-0041; amended by ADR-0072 |
| [ADR-0062](docs/decisions/ADR-0062-width-is-matched-per-value-never-used-to-filter-a-codelist.md) | 2026-09-28 | Width is matched per value; a codelist is never filtered by a column's curated width | active | amends ADR-0015 |
| [ADR-0063](docs/decisions/ADR-0063-a-label-is-a-companion-the-raw-code-always-stays.md) | 2026-09-28 | A label is a companion; the raw code always stays | active | amends ADR-0010 |
| [ADR-0064](docs/decisions/ADR-0064-age-in-completed-years-from-one-converter.md) | 2026-09-28 | Age is derived in completed years by one converter, declared per curated recipe | superseded | supersedes ADR-0020; amends ADR-0058; superseded by ADR-0070 |
| [ADR-0065](docs/decisions/ADR-0065-a-split-publications-part-is-part-of-its-identity.md) | 2026-09-28 | A split publication's part is part of its identity; descriptive names may carry a year | active | amends ADR-0017, ADR-0013 |
| [ADR-0066](docs/decisions/ADR-0066-progress-is-measured-by-live-scenarios.md) | 2026-09-28 | Progress is measured by live scenarios; no new unit tests | active |  |
| [ADR-0067](docs/decisions/ADR-0067-a-fresh-catalog-starts-from-the-shipped-seed.md) | 2026-09-28 | A fresh catalog starts from the shipped seed | active | supersedes ADR-0029; amends ADR-0046 |
| [ADR-0068](docs/decisions/ADR-0068-the-newest-edition-of-a-publication-wins.md) | 2026-09-28 | The newest edition of a publication wins; only undated editions refuse | active | amends ADR-0047; amended by ADR-0071 |
| [ADR-0069](docs/decisions/ADR-0069-search-reads-the-catalog-and-the-label-pack.md) | 2026-09-28 | `search()` reads the catalog and the label pack; no dictionary build is needed | active | amends ADR-0028; amended by ADR-0075 |
| [ADR-0070](docs/decisions/ADR-0070-age-is-fractional-years-from-measured-units.md) | 2026-09-28 | Age is one column of fractional years, decoded from measured unit tables | active | supersedes ADR-0064; amends ADR-0058 |
| [ADR-0071](docs/decisions/ADR-0071-a-representation-is-its-full-suffix-and-self-derived-conflicts-do-not-gate.md) | 2026-09-28 | A representation is known by its full suffix; a self-derived conflict is re-evaluated, not stored as a gate | active | amends ADR-0047, ADR-0068 |
| [ADR-0072](docs/decisions/ADR-0072-one-compiled-label-binding-per-family-and-field.md) | 2026-09-28 | One label binding per (system, family, field), compiled from samples and shipped | active | supersedes ADR-0041; amends ADR-0012, ADR-0031, ADR-0061 |
| [ADR-0073](docs/decisions/ADR-0073-query-is-the-one-data-door.md) | 2026-09-28 | `query()` is the one public door to data; one dataset identifier; one CLI verb | active | amends ADR-0026, ADR-0043 |
| [ADR-0074](docs/decisions/ADR-0074-the-native-engine-builds-into-a-user-cache.md) | 2026-09-28 | The native DBC engine builds into a per-user cache, never the package; wheels should ship it compiled | active | amends ADR-0059 |
| [ADR-0075](docs/decisions/ADR-0075-the-dictionary-database-and-the-bundle-are-retired.md) | 2026-09-28 | The dictionary database and the semantic bundle are retired; the seed and `compendium()` carry the meaning | active | supersedes ADR-0027, ADR-0028; amends ADR-0069 |
| [ADR-0076](docs/decisions/ADR-0076-a-query-states-and-bounds-its-download.md) | 2026-09-28 | A query states its download before anything moves, and is bounded by default | active |  |
| [ADR-0077](docs/decisions/ADR-0077-archives-are-censused-and-their-members-are-publications.md) | 2026-09-28 | Archives are censused, and each table inside a multi-table archive is its own publication | active | amends ADR-0071 |
| [ADR-0078](docs/decisions/ADR-0078-a-republished-file-is-re-censused-and-added-columns-are-read.md) | 2026-09-28 | A republished file is re-censused, and a file that only gained columns is read, not refused | active |  |
| [ADR-0079](docs/decisions/ADR-0079-a-code-table-found-only-in-a-document-is-written-in-the-curation.md) | 2026-09-28 | A code table found only in a document is written in the curation | active | amends ADR-0012, ADR-0072 |
| [ADR-0080](docs/decisions/ADR-0080-a-code-belongs-to-its-form.md) | 2026-09-28 | A code belongs to its form; per-form alternatives are chosen per family, never merged | active | amends ADR-0072, ADR-0079 |
| [ADR-0081](docs/decisions/ADR-0081-every-file-header-is-read-and-a-publication-is-read-once.md) | 2026-09-28 | Every file's header is read, and a publication is read once whatever its layout or tree | active | amends ADR-0020, ADR-0068, ADR-0071, ADR-0078 |
| [ADR-0082](docs/decisions/ADR-0082-one-label-decision-and-reads-never-hold-the-catalog.md) | 2026-09-28 | One label decision for query and compile; reads never hold the catalog | active | amends ADR-0072, ADR-0080 |
| [ADR-0083](docs/decisions/ADR-0083-a-remote-duckdb-is-described-by-range.md) | 2026-09-29 | A remote DuckDB database is described by ranged reads; its tables are members | active | amends ADR-0077 |
| [ADR-0084](docs/decisions/ADR-0084-presentation-is-one-declarative-step.md) | 2026-09-29 | How a result reads is one declarative step, applied last; the default reads "Masculino (1)" under "Sexo (SEXO)" | active | amends ADR-0063, ADR-0073 |
| [ADR-0085](docs/decisions/ADR-0085-meaning-is-measured-for-every-field.md) | 2026-09-29 | Meaning is measured for every field of every family, against a total standard | active |  |
| [ADR-0086](docs/decisions/ADR-0086-registries-come-from-the-owners-current-kit.md) | 2026-09-29 | Registries come from their owner's current kit, on first use; a coded column that nothing decodes is visibly undecoded | active | amends ADR-0063, ADR-0084 |
| [ADR-0087](docs/decisions/ADR-0087-standard-classifications-are-canonical-and-labels-must-mean.md) | 2026-09-29 | A standard classification is one canonical table for every system, and a label must say what the code means | active | amends ADR-0079, ADR-0080, ADR-0085 |
| [ADR-0088](docs/decisions/ADR-0088-a-code-that-needs-another-column-is-keyed-by-both.md) | 2026-09-29 | A code that means something only with another column is keyed by both; labels shed the codes embedded in them | active | amends ADR-0084, ADR-0087 |
| [ADR-0089](docs/decisions/ADR-0089-icd-codes-fall-back-to-their-category.md) | 2026-09-29 | An ICD-10 code the classification does not list is labelled by its category, and says so | active | amends ADR-0087 |
| [ADR-0090](docs/decisions/ADR-0090-a-record-can-name-its-own-code.md) | 2026-09-29 | A record can name its own code; a label's inputs survive a narrow select | active | amends ADR-0087, ADR-0088 |
| [ADR-0091](docs/decisions/ADR-0091-value-overlap-is-not-a-source.md) | 2026-09-29 | A binding inferred from value overlap is not a source of meaning | active |  |
| [ADR-0092](docs/decisions/ADR-0092-sigtap-is-canonical-and-hierarchies-are-dimensions.md) | 2026-09-29 | SIGTAP is canonical, its hierarchy is a dimension, and derived columns can be selected | active | amends ADR-0087, ADR-0089 |
| [ADR-0093](docs/decisions/ADR-0093-naturality-cnpj-and-the-coded-label-invariant.md) | 2026-09-29 | Naturality and CNPJs decode from canonical tables; every coded column leaves with a label companion | active | amends ADR-0086, ADR-0087 |
| [ADR-0094](docs/decisions/ADR-0094-a-label-reached-through-another-column.md) | 2026-09-29 | A label can be reached through another column of the row | active | amends ADR-0090, ADR-0093 |
| [ADR-0095](docs/decisions/ADR-0095-kits-are-read-by-column-and-curation-is-inherited.md) | 2026-09-29 | A `.CNV` is read by its columns; a republishing system inherits curation; the age unit is keyed with the age | active | amends ADR-0088 |
| [ADR-0096](docs/decisions/ADR-0096-a-path-coded-table-names-an-unlisted-code-by-its-listed-levels.md) | 2026-09-29 | A code built from levels is named by its deepest listed level when the table does not list it | active | amends ADR-0089, ADR-0092 |
| [ADR-0097](docs/decisions/ADR-0097-render-work-is-done-once-per-distinct-thing.md) | 2026-09-29 | Rendering does its work once per distinct thing; a field's own codes come before a label reached through another column | active | amends ADR-0084, ADR-0094 |
| [ADR-0098](docs/decisions/ADR-0098-the-sweep-bindings-composite-keys-with-widths.md) | 2026-09-29 | What a live sweep of sixteen datasets bound: composite keys carry the record's widths, path tables name their levels, and twins share tables | active | amends ADR-0088, ADR-0094, ADR-0096 |
| [ADR-0099](docs/decisions/ADR-0099-an-opaque-label-is-replaced-by-its-documented-meaning.md) | 2026-09-29 | A label that restates a code, or drops its unit, is replaced by the documented meaning | active | amends ADR-0085, ADR-0087 |
| [ADR-0100](docs/decisions/ADR-0100-one-establishment-registry-typed-identifiers-and-the-crosswalk-reads-it.md) | 2026-09-29 | One establishment registry with typed identifiers; the CNES ↔ CNPJ crosswalk and the name enrichment read it | active | amends ADR-0086, ADR-0093, ADR-0094 |
| [ADR-0101](docs/decisions/ADR-0101-classification-changes-are-bridged-by-the-official-maps.md) | 2026-09-29 | A change of classification is bridged by the official map, and only where the map is one-to-one | active | amends ADR-0092 |
| [ADR-0102](docs/decisions/ADR-0102-no-identifier-inside-a-label.md) | 2026-09-29 | No CNPJ or CPF inside a label, wherever the label comes from | active | amends ADR-0100 |
| [ADR-0103](docs/decisions/ADR-0103-legacy-sia-establishments-by-state-and-archive-members-measured.md) | 2026-09-29 | SIA's pre-2008 establishment codes are keyed by the file's state, and a multi-table archive's members are measured, not assumed | active | amends ADR-0077, ADR-0088, ADR-0098 |
| [ADR-0104](docs/decisions/ADR-0104-cbo-1994-bridged-by-the-conversion-datasus-applied.md) | 2026-09-29 | CBO 1994 is bridged to CBO 2002 by the conversion DATASUS applied, measured, and all bridges are one resource | active | amends ADR-0101 |
| [ADR-0105](docs/decisions/ADR-0105-codes-given-meaning-by-measurement.md) | 2026-09-29 | Undocumented codes are given a meaning when the data proves it, inline codes keep their fallback, and TabWin's order marks leave labels | active | amends ADR-0079, ADR-0102 |
| [ADR-0106](docs/decisions/ADR-0106-fallback-tables-sentinels-and-positional-codes.md) | 2026-09-29 | Measured sentinels and single codes, national tables behind the system's own, and positional CNV codes | active | amends ADR-0093, ADR-0105 |
| [ADR-0107](docs/decisions/ADR-0107-record-linkage-architecture.md) | 2026-09-30 | Record linkage is a query, finds candidates by intrinsic properties, weighs evidence in bits learned from the data, and reports its own error | active | |
| [ADR-0108](docs/decisions/ADR-0108-tabwin-groupings-are-not-meanings.md) | 2026-09-30 | A TabWin grouping is not a code's meaning: SIH IDENT from the layout, and catch-all ranges measured before they are trusted | active | |
| [ADR-0109](docs/decisions/ADR-0109-roles-compare-properties-not-columns.md) | 2026-09-30 | Records are compared through roles, the property a column states about an entity, normalised through the project's own meaning | active | part of ADR-0107 |
| [ADR-0110](docs/decisions/ADR-0110-deterministic-linkage-engine.md) | 2026-09-30 | The deterministic linkage engine: specs as data, 1:1 passes over what is left, a negative control per pass, verdicts fixed in advance | active | part of ADR-0107 |
| [ADR-0111](docs/decisions/ADR-0111-probabilistic-linkage-learned-from-anchors-and-controls.md) | 2026-09-30 | Probabilistic linkage learns each field's error channel from leave-one-field-out anchors and sets its threshold by measured false matches | active | part of ADR-0107 |
| [ADR-0112](docs/decisions/ADR-0112-link-store-timeline-and-serve-routes.md) | 2026-09-30 | Link results persist in the lake; a pregnancy is served as a timeline of linked events, behind the microdata switch | active | part of ADR-0107 |
| [ADR-0113](docs/decisions/ADR-0113-ambiguity-margin-and-verdicts-on-the-upper-bound.md) | 2026-09-30 | A probabilistic pair must be each side's clear best, and a verdict is judged on the 95% upper bound of its chance rate | active | amends ADR-0107, ADR-0111 |
| [ADR-0114](docs/decisions/ADR-0114-blocks-keep-an-identifying-key.md) | 2026-09-30 | Every candidate block keeps an identifying key; typo-variant blocks exist and are used only where they add links | active; amended 2026-09-30 (blocks selective at national scale) | part of ADR-0107, ADR-0111 |
| [ADR-0115](docs/decisions/ADR-0115-residence-scored-given-the-place-of-care.md) | 2026-09-30 | Residence is scored given the place of care: agreement away from the hospital weighs more than agreement at it | active | part of ADR-0111 |
| [ADR-0116](docs/decisions/ADR-0116-info-shows-the-standing-of-each-description.md) | 2026-09-30 | `info()` shows where each variable's description comes from; an inferred one reads as unverified | active |  |
| [ADR-0117](docs/decisions/ADR-0117-newborn-size-from-icd-p07-and-unseen-levels-never-count-for-a-match.md) | 2026-09-30 | A newborn admission's P07 codes are evidence against the birth's weight and weeks; a level no anchor showed never counts for a match | active | part of ADR-0111 |
| [ADR-0118](docs/decisions/ADR-0118-seven-digit-municipality-table.md) | 2026-09-30 | Seven-digit IBGE municipality codes decode against a seven-digit table (MUNIC_BR7), chained after the six-digit one | active | part of ADR-0087 |
| [ADR-0119](docs/decisions/ADR-0119-link-discovery-measures-which-fields-carry-shared-people.md) | 2026-10-02 | Link discovery measures which typed fields carry people shared by two datasets, against a week-shifted placebo; a link spec is checked against it, not only asserted | active | part of ADR-0107 |
| [ADR-0120](docs/decisions/ADR-0120-linkage-theory-executed.md) | 2026-10-03 | The linkage theory executed: lake-backed cached roles; a slice linked against the nation with national u, pooled m and the national calibration; a placebo that shifts every left date; p_match; entities and inherited evidence; chance agreement estimated where scores are compared; settings as annotators | active | part of ADR-0107 |
| [ADR-0121](docs/decisions/ADR-0121-impossibility-as-learned-evidence-and-padded-partner-periods.md) | 2026-10-03 | Event order and category pairs as evidence-only comparison kinds (removed from the death specs the same night: both double-counted compared fields); a partner side may be read over a padded period, with inherited evidence per year | active | part of ADR-0107 |
| [ADR-0122](docs/decisions/ADR-0122-a-verified-mirror-serves-a-file-the-ftp-will-not.md) | 2026-10-03 | When the FTP transfer fails, a public byte-identical mirror serves the file, size-checked against the DATASUS listing and recorded as `mirror:<url>` | active | part of ADR-0003 |
| [ADR-0123](docs/decisions/ADR-0123-error-channels-per-setting.md) | 2026-10-03 | Error channels (m) are estimated per setting (the state that publishes the left record), shrunk toward the national ones, in every run; scope invariance becomes exact (SP 578 disagreements -> 0) | active | part of ADR-0107 |
| [ADR-0124](docs/decisions/ADR-0124-record-identity-is-a-content-key-numbered-for-duplicates.md) | 2026-10-03 | A record's identity is the hash of its own fields, numbered for exact duplicates within its file (CIHA publishes 735,049 duplicate rows); resolves OQ-65 | active | part of ADR-0107 |
| [ADR-0125](docs/decisions/ADR-0125-establishment-attributes-as-of-the-record.md) | 2026-10-03 | An establishment's attributes are read from CNES.ST at the record's own month through `query()`; 17 attributes; an empty attribute is `not_recorded` | active | part of ADR-0045, ADR-0100 |
| [ADR-0126](docs/decisions/ADR-0126-geography-from-tabnet-current-tables-and-ipea-comparable-areas.md) | 2026-10-03 | Health macroregions and current health regions from TabNet's current territorial tables (reverses ADR-0049's exclusion); comparable areas (AMC) from IPEA; `pegasus-data geography` builds the pack | active | part of ADR-0049, ADR-0052 |
| [ADR-0127](docs/decisions/ADR-0127-context-fields-from-ibge-aggregates.md) | 2026-10-03 | Context fields are IBGE's municipal statistics declared by table and variable, stored as totals with IBGE's markers kept; `pegasus-data fields`, `load_field()` | active | part of ADR-0050, ADR-0055 |
| [ADR-0128](docs/decisions/ADR-0128-race-reliability-flagged-per-hospital-month.md) | 2026-10-03 | SIH race is flagged per hospital and month by measured rules (code 04 as a default, or as SIM's brown); `race_reliability()`; never relabelled; resolves OQ-66 | active | |
| [ADR-0129](docs/decisions/ADR-0129-current-health-region-is-tabnets.md) | 2026-10-03 | The system-neutral current health region is TabNet's `br_regsaud` (`health_region_current`); per-system CIRBRN claims stay, contests reported; resolves OQ-10 | active | |
