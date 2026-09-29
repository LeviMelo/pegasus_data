# EVALUATION.md

The index of this project's measurements. Each measurement is one file under
`docs/evaluation/`; read the index, then the entries you need. How
measurements are made, and what "ground truth" means here:
[`docs/evaluation/methods.md`](docs/evaluation/methods.md).

**The rule: nothing is declared working on the basis of a plausible-looking
output** (CLAUDE.md §5). Open the table, read the labels, and count the rows
against an independent figure: TabNet, the file's own row count, a direct
`GROUP BY` over the same microdata.

---

**Writing one.** A new measurement is a new file
`docs/evaluation/YYYY-MM-DD-<slug>.md` and one row here, in the same commit
as the work it justifies (CLAUDE.md §7). The entry names:

- the live scenario or script that produced it (a scenario name, or a
  script under `scripts/`);
- its artifact under `data/probes/`;
- the unit that binds (bytes on the wire, wall clock, rows, labels);
- what was counted and why that is the thing that matters;
- the regime: commit, data home (fresh or local), date.

A live run that changed nothing is still an entry. A number later found to
have measured the wrong thing is corrected in its file, saying so.

**Split from `docs/history/FINDINGS.md` on 2026-09-28** (ADR-0001); the text
of every entry is unchanged. That notebook numbered §3n–§3q twice (2026-08-23
query architecture, then 2026-08-23 geography and aggregates, committed
2026-08-27); `group` says which. Two entries come from
`docs/history/pegasus_data_ARCHITECTURE.md` §21 and §22, which held measured
state and doubts that FINDINGS did not. `group` names the section an entry sat
in.

| date | measurement | group |
|---|---|---|
| 2026-08-18 | [The previous inventory of DATASUS was missing a third of it](docs/evaluation/2026-08-18-the-prior-inventory-missed-a-third-of-datasus.md) | §0 The headline |
| 2026-08-18 | [V1: there is no HTTPS mirror, and none is needed](docs/evaluation/2026-08-18-v1-no-https-mirror.md) | §1 The [V] list, resolved |
| 2026-08-18 | [V2: the self-extracting .exe payload is LHA, with seven DBF members](docs/evaluation/2026-08-18-v2-the-exe-payload-is-lha.md) | §1 The [V] list, resolved |
| 2026-08-18 | [V3: the .CNV and .DEF grammars](docs/evaluation/2026-08-18-v3-cnv-and-def-grammars.md) | §1 The [V] list, resolved |
| 2026-08-18 | [V4: what a TAB_*.zip kit holds](docs/evaluation/2026-08-18-v4-tab-kit-contents.md) | §1 The [V] list, resolved |
| 2026-08-18 | [V5: procedure tables are in the kits; SIGTAP attributes are not](docs/evaluation/2026-08-18-v5-procedure-tables-and-sigtap.md) | §1 The [V] list, resolved |
| 2026-08-18 | [V6: .duck storage version, handled by construction](docs/evaluation/2026-08-18-v6-duck-storage-version.md) | §1 The [V] list, resolved |
| 2026-08-18 | [V7: IBGE/projpop is UF-level projections, 2000-2070](docs/evaluation/2026-08-18-v7-ibge-projpop.md) | §1 The [V] list, resolved |
| 2026-08-18 | [V8: the Ministry's own denominator stays open](docs/evaluation/2026-08-18-v8-the-ministrys-denominator.md) | §1 The [V] list, resolved |
| 2026-08-18 | [V9: DEMAS endpoint granularity](docs/evaluation/2026-08-18-v9-demas-endpoint-granularity.md) | §1 The [V] list, resolved |
| 2026-08-18 | [V10: Dados_Abertos has no new naming grammar](docs/evaluation/2026-08-18-v10-dados-abertos-naming.md) | §1 The [V] list, resolved |
| 2026-08-18 | [V11: the 32 failed directories](docs/evaluation/2026-08-18-v11-the-32-failed-directories.md) | §1 The [V] list, resolved |
| 2026-08-18 | [D4's root cause is a listing-dialect bug, not a protocol limitation](docs/evaluation/2026-08-18-d4-is-a-listing-dialect-bug.md) | §2 [M] claims that did not survive re-measurement |
| 2026-08-18 | [SIH-RD has at least nine schema generations, not three](docs/evaluation/2026-08-18-sih-rd-has-at-least-nine-generations.md) | §2 [M] claims that did not survive re-measurement |
| 2026-08-18 | [DIAG_SECUN in the 113-column generation is present, not absent](docs/evaluation/2026-08-18-diag-secun-is-present-and-constant.md) | §2 [M] claims that did not survive re-measurement |
| 2026-08-18 | [Codelists are not columns](docs/evaluation/2026-08-18-codelists-are-not-columns.md) | §3 Design corrections the implementation required |
| 2026-08-18 | [Dictionary entries need their validity window](docs/evaluation/2026-08-18-dictionary-entries-need-a-validity-window.md) | §3 Design corrections the implementation required |
| 2026-08-18 | [Choosing which codelist labels a field](docs/evaluation/2026-08-18-choosing-which-codelist-labels-a-field.md) | §3 Design corrections the implementation required |
| 2026-08-18 | [Parquet is not smaller than a .dbc, and that is the wrong comparison](docs/evaluation/2026-08-18-parquet-is-not-smaller-than-a-dbc.md) | §3 Design corrections the implementation required |
| 2026-08-18 | [One outlier file must not redefine a directory](docs/evaluation/2026-08-18-one-outlier-file-must-not-redefine-a-directory.md) | §3 Design corrections the implementation required |
| 2026-08-18 | [Codepage detection cannot be "first one that works"](docs/evaluation/2026-08-18-codepage-detection-cannot-be-first-that-works.md) | §3 Design corrections the implementation required |
| 2026-08-18 | [Performance corrections found by running it](docs/evaluation/2026-08-18-performance-corrections-found-by-running-it.md) | §3 Design corrections the implementation required |
| 2026-08-18 | [Labels for hierarchical classifications do not belong in the lake](docs/evaluation/2026-08-18-hierarchical-labels-do-not-belong-in-the-lake.md) | §3b Corrections after review |
| 2026-08-18 | [official_name: one source is not "no source"](docs/evaluation/2026-08-18-official-name-one-source-is-not-no-source.md) | §3b Corrections after review |
| 2026-08-18 | [Codelist coverage is a measured gap list, not a whitelist](docs/evaluation/2026-08-18-codelist-coverage-is-a-measured-gap-list.md) | §3b Corrections after review |
| 2026-08-18 | [Three idempotence bugs this work exposed](docs/evaluation/2026-08-18-three-idempotence-bugs.md) | §3b Corrections after review |
| 2026-08-19 | [The full-tree crawl, and what it found](docs/evaluation/2026-08-19-the-full-tree-crawl.md) | §3c The full-tree crawl |
| 2026-08-19 | [lake_partitions duplicated rows rather than zeroing them](docs/evaluation/2026-08-19-lake-partitions-duplicated-rows.md) | §3d Measured results that changed the design |
| 2026-08-19 | [SP_ATOPROF and SP_PROCREA are not 8-digit](docs/evaluation/2026-08-19-sp-atoprof-and-sp-procrea-are-two-widths.md) | §3d Measured results that changed the design |
| 2026-08-19 | [SIM's CAUSABAS contains ICD-9, not malformed data](docs/evaluation/2026-08-19-sim-causabas-contains-icd9.md) | §3d Measured results that changed the design |
| 2026-08-19 | [SIM's ATESTADO separates on /, not *](docs/evaluation/2026-08-19-sim-atestado-separates-on-slash.md) | §3d Measured results that changed the design |
| 2026-08-19 | [IBGE.IDADE is bound to CID10 and matches nothing](docs/evaluation/2026-08-19-ibge-idade-bound-to-cid10-matches-nothing.md) | §3d Measured results that changed the design |
| 2026-08-19 | [29 SIH columns are dead in the current generation](docs/evaluation/2026-08-19-29-sih-columns-are-dead.md) | §3d Measured results that changed the design |
| 2026-08-19 | [SIGTAP is reachable, over HTTP only](docs/evaluation/2026-08-19-sigtap-is-reachable-over-http-only.md) | §3d Measured results that changed the design |
| 2026-08-19 | [Layout documents exist for SIM and SINASC, in a different dialect](docs/evaluation/2026-08-19-layout-documents-for-sim-and-sinasc.md) | §3d Measured results that changed the design |
| 2026-08-19 | [COD_IDADE is deliberately unbound](docs/evaluation/2026-08-19-cod-idade-is-deliberately-unbound.md) | §3d Measured results that changed the design |
| 2026-08-19 | [CEP: settled, and recorded as settled](docs/evaluation/2026-08-19-cep-settled.md) | §3d Measured results that changed the design |
| 2026-08-19 | [311,844 codelist contradictions, all manufactured](docs/evaluation/2026-08-19-the-contradiction-was-ours.md) | §3e The contradiction was ours |
| 2026-08-19 | [Classification changes, not data going bad (CID-9/CID-10)](docs/evaluation/2026-08-19-classification-changes-not-data-going-bad.md) | §3f Classification changes |
| 2026-08-19 | [A schema census, not a schema sample](docs/evaluation/2026-08-19-a-schema-census-not-a-schema-sample.md) | §3g A schema census |
| 2026-08-19 | [Reading what DATASUS never published (microdatasus)](docs/evaluation/2026-08-19-reading-what-datasus-never-published.md) | §3h Reading what DATASUS never published |
| 2026-08-19 | [What the catalogue holds after the census](docs/evaluation/2026-08-19-what-the-catalogue-holds.md) | §3i What the catalogue holds |
| 2026-08-21 | [Identifiers and re-identification risk in public SIASUS files](docs/evaluation/2026-08-21-identifiers-and-re-identification-risk-in-siasus.md) | §3j Identifiers and re-identification risk |
| 2026-08-23 | [A municipality labelled as its health region](docs/evaluation/2026-08-23-a-municipality-labelled-as-its-health-region.md) | §3k A municipality labelled as its health region |
| 2026-08-23 | [Review closure exposed four reusable engineering rules](docs/evaluation/2026-08-23-review-closure-four-engineering-rules.md) | §3l Review closure |
| 2026-08-23 | [The next architecture is evidence compilation, not warehouse shipping](docs/evaluation/2026-08-23-evidence-compilation-not-warehouse-shipping.md) | §3m The next architecture |
| 2026-08-23 | [Query completeness is a publication-set property](docs/evaluation/2026-08-23-query-completeness-is-a-publication-set-property.md) | §3n (first) Query completeness |
| 2026-08-23 | [Source selection and analytical filtering are different products](docs/evaluation/2026-08-23-source-selection-and-analytical-filtering-differ.md) | §3o (first) Source selection |
| 2026-08-23 | [Temporal truth has extent, identity and authority](docs/evaluation/2026-08-23-temporal-truth-has-extent-identity-authority.md) | §3p (first) Temporal truth |
| 2026-08-23 | [The distributed artifact is a separate correctness boundary](docs/evaluation/2026-08-23-the-artifact-is-a-correctness-boundary.md) | §3q (first) The artifact boundary |
| 2026-08-23 | [DATASUS publishes supramunicipal geography, and disagrees with itself](docs/evaluation/2026-08-23-supramunicipal-geography-disagrees-with-itself.md) | §3n (second) Supramunicipal geography |
| 2026-08-23 | [Building the aggregate layer](docs/evaluation/2026-08-23-building-the-aggregate-layer.md) | §3o (second) Building the aggregate layer |
| 2026-08-23 | [Auditing DATASUS geography against IBGE](docs/evaluation/2026-08-23-auditing-datasus-geography-against-ibge.md) | §3p (second) Auditing geography against IBGE |
| 2026-08-23 | [Reviewing the aggregate layer at the scale it is for](docs/evaluation/2026-08-23-reviewing-the-aggregate-layer-at-scale.md) | §3q (second) Reviewing the aggregate layer |
| 2026-08-23 | [Measured state of the catalog and shipped artifacts (ARCH §21)](docs/evaluation/2026-08-23-architecture-measured-state.md) | ARCH §21 Measured state |
| 2026-08-23 | [What we are least sure of (ARCH §22)](docs/evaluation/2026-08-23-architecture-what-we-are-least-sure-of.md) | ARCH §22 Doubts |
| 2026-08-29 | [An artifact knows its scope and was throwing it away](docs/evaluation/2026-08-29-an-artifact-knows-its-scope.md) | §3r An artifact knows its scope |
| 2026-08-29 | [DATASUS does not use one date format](docs/evaluation/2026-08-29-datasus-does-not-use-one-date-format.md) | §3s One date format |
| 2026-08-30 | [The serve path met its first national artifact](docs/evaluation/2026-08-30-the-serve-path-met-a-national-artifact.md) | §3t The serve path |
| 2026-08-30 | [The build spent an hour labelling nothing](docs/evaluation/2026-08-30-the-build-spent-an-hour-labelling-nothing.md) | §3u Labelling nothing |
| 2026-08-30 | [Reviewing the whole with fresh eyes (three-front review)](docs/evaluation/2026-08-30-reviewing-the-whole-with-fresh-eyes.md) | §3v Three-front review |
| 2026-08-30 | [Generic had quietly become shallow: recipe depth](docs/evaluation/2026-08-30-generic-had-become-shallow.md) | §3w Recipe depth |
| 2026-08-30 | [Owning the decompressor](docs/evaluation/2026-08-30-owning-the-decompressor.md) | §3x Owning the decompressor |
| 2026-08-30 | [The CNES stock that measured the wrong columns](docs/evaluation/2026-08-30-the-stock-that-measured-the-wrong-columns.md) | §3y The CNES stocks |
| 2026-09-28 | [The first live runs on a fresh home: the primary interface returned codes without meaning](docs/evaluation/2026-09-28-the-first-live-runs-on-a-fresh-home.md) | live (`scripts/live.py`) |
| 2026-09-28 | [The maintainer catalog refreshed from a full crawl: listing is cheap, and 5% of the tree had no family](docs/evaluation/2026-09-28-the-maintainer-catalog-refreshed-from-a-full-crawl.md) | maintainer build |
| 2026-09-28 | [Age units measured against the records' own dates: SIM's layout document is wrong, and SINAN hides plain years](docs/evaluation/2026-09-28-age-units-measured-against-dates.md) | live |
| 2026-09-28 | [The frontend's API after the redesign, and one served number checked against the microdata](docs/evaluation/2026-09-28-the-served-aggregate-matches-the-microdata.md) | live (`serve/`) |
| 2026-09-29 | [43,916 .CNV codes glued to their labels, and a year that took four minutes](docs/evaluation/2026-09-29-glued-cnv-codes-and-a-slow-year.md) | kit re-parse; live (`query`) |
| 2026-09-29 | [A fresh-home sweep of undecoded values: 1.23 million undecoded cells to 0.56 million](docs/evaluation/2026-09-29-fresh-home-sweep-of-undecoded-values.md) | live (`scripts/sweep_undecoded.py`, fresh home) |
| 2026-09-29 | [Description and decoding coverage after the kit rebuild: undecoded 240 → 34, missing descriptions 441 → 130](docs/evaluation/2026-09-29-coverage-after-the-kit-rebuild.md) | maintainer (`pegasus-data meaning`) |
| 2026-09-29 | [The mapping tables: CNES ↔ CNPJ checked against each record's own CNPJ, the team registry, and the 2008 procedure bridge](docs/evaluation/2026-09-29-mapping-tables-cnes-cnpj-teams-and-the-2008-bridge.md) | live (`query(enrich=…)`), `scripts/registry_fields.py` |
