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
| 2026-09-29 | [SIA's 2001–2007 APAC archives: members measured by ranged header reads, and their establishments named by state](docs/evaluation/2026-09-29-legacy-apac-archives-members-measured.md) | maintainer census; live (new home) |
| 2026-09-29 | [Measured code meanings: SIH secondary-diagnosis type, SIH-SP travel flags, SIA residence and occurrence codes](docs/evaluation/2026-09-29-measured-code-meanings.md) | live (new home) |
| 2026-09-29 | [Measured sentinels and national fallbacks: undecoded columns 52 → 21, cells 560,585 → 48,763](docs/evaluation/2026-09-29-measured-sentinels-and-national-fallbacks.md) | live (`scripts/sweep_undecoded.py`, fresh home) |
| 2026-09-30 | [What omnisus teaches: a survey of a neighbouring project, with each finding checked against ours](docs/evaluation/2026-09-30-what-omnisus-teaches.md) | survey; DBC check against `datasus_dbc` |
| 2026-09-30 | [The deterministic baseline reproduces omnisus's RR 2022 linkage to the pair](docs/evaluation/2026-09-30-deterministic-baseline-reproduces-omnisus.md) | live (`linkage.engine.link`, fresh home) |
| 2026-09-30 | [Pre-merge live run: every scenario and every declared dataset, before `redesign` became `master`](docs/evaluation/2026-09-30-pre-merge-live-run.md) | live (`scripts/live.py --all --fresh`) |
| 2026-09-30 | [National linkage measurements: bits of identity, error channels, travel flows, SIH/CIHA coverage, join grains](docs/evaluation/2026-09-30-national-linkage-measurements.md) | live (`scripts/linkage_study.py`, national) |
| 2026-09-30 | [Catch-all ranges: which observed codes a TabWin residual range was decoding](docs/evaluation/2026-09-30-catch-all-ranges.md) | live (`scripts/catchall_audit.py`, fresh home) |
| 2026-09-30 | [Health pass: 1990s SIH diagnoses, warnings about out-of-period tables, and code lists that exist nowhere](docs/evaluation/2026-09-30-health-pass-sih-diagnoses-and-dangling-tables.md) | live (fresh home), curation scan |
| 2026-09-30 | [Private-sector links (CIHA) and what CIHA's "residence" really holds](docs/evaluation/2026-09-30-private-sector-links-and-ciha-residence.md) | live (`link`, fresh home) |
| 2026-09-30 | [CIHA's residence field tested against SINASC (linked deliveries, six states)](docs/evaluation/2026-09-30-ciha-residence-tested-against-sinasc.md) | live (`scripts/ciha_residence_check.py`, fresh and national homes) |
| 2026-09-30 | [Residence scored given the place of care (ADR-0115)](docs/evaluation/2026-09-30-residence-given-the-place-of-care.md) | live (`link(refresh=True)`, fresh home) |
| 2026-09-30 | [The omnisus facts, measured on our data (SIM minutes, TABPAIS, CLASSI_FIN, ORIGEM, RR June 2022)](docs/evaluation/2026-09-30-omnisus-facts-verified.md) | live (fresh and national homes), catalog |
| 2026-09-30 | [Newborn admissions linked with ICD-10 P07 evidence (ADR-0117)](docs/evaluation/2026-09-30-newborn-admissions-with-p07-evidence.md) | live (`scripts/neonatal_size_codes.py`, `link(refresh=True)`, fresh home) |
| 2026-09-30 | [The 73 inferred code-table bindings, measured](docs/evaluation/2026-09-30-inferred-bindings-audited.md) | live (fresh home) |
| 2026-09-30 | [National linkage, 2022: all seven links under the current engine; CIHA residence on deaths](docs/evaluation/2026-09-30-national-linkage-2022.md) | live (`pegasus-data link --refresh`, national home; `scripts/ciha_residence_check.py --deaths`) |
| 2026-10-02 | [Link discovery, national 2022: the data reveals the hand-written keys](docs/evaluation/2026-10-02-link-discovery.md) | live (`scripts/link_discovery.py`, national home) |
| 2026-10-02 | [Impossible pairs in the national links: mostly recording errors, not false links](docs/evaluation/2026-10-02-impossible-pairs-measured.md) | live (`scripts/link_impossibility.py`, national home) |
| 2026-10-02 | [Race for the same person across systems (linked pairs, national 2022)](docs/evaluation/2026-10-02-race-across-systems.md) | live (`scripts/race_across_systems.py`, national home) |
| 2026-10-02 | [Linkage speed, first pass: 58 → 9.2 min for the national SIH-deaths link, identical pairs](docs/evaluation/2026-10-02-linkage-speed-first-pass.md) | live (cProfile; national home) |
| 2026-10-03 | [Entities from the national links: 2.39 million links merged into persons, 78 conflicts](docs/evaluation/2026-10-03-entities-from-national-links.md) | live (`build_entities`, national home) |
| 2026-10-03 | [Value-specific chance agreement: tried, measured, removed (code kept in the entry)](docs/evaluation/2026-10-03-value-frequency-weighting-tried.md) | live (`scripts/link_scope_test.py`, national home) |
| 2026-10-03 | [`build` reported a failed download as an empty success](docs/evaluation/2026-10-03-build-hid-a-failed-fetch.md) | live (`pegasus-data build`, SINASC 2021, national home) |
| 2026-10-03 | [The FTP data channel stopped answering; the mirror is byte-identical](docs/evaluation/2026-10-03-ftp-data-channel-down-mirror-identical.md) | live (ftplib/sockets probes, fetcher fallback; national home) |
| 2026-10-03 | [Impossibility as learned evidence; padded infant deaths](docs/evaluation/2026-10-03-impossibility-as-learned-evidence.md) | live (`data/logs/impossibility_test.py`, Sergipe; national pending) |
| 2026-10-03 | [The national newborn link ran out of memory; u is now counted, not materialised](docs/evaluation/2026-10-03-newborn-link-memory.md) | live (national run; Sergipe old-vs-new comparison) |
| 2026-10-03 | [SIH's excess "asian" is two hospital practices: a default fill, and SIM's numbering written in](docs/evaluation/2026-10-03-sih-asian-default-fill-and-code-swap.md) | live (`scripts/race_settings.py`, `scripts/race_code_swap.py`; national home) |
| 2026-10-03 | [Error channels per setting: the scope test](docs/evaluation/2026-10-03-error-channels-per-setting.md) | live (`scripts/link_scope_test.py`, national home) |
| 2026-10-03 | [Performance pass: linkage 6.5x, role builds 1.9x, lake builds 1.9x, every output identical](docs/evaluation/2026-10-03-performance-pass.md) | live (cProfile; old-vs-new comparisons; national home) |
| 2026-10-03 | [Entities on the final 2022 links, and the admission-baby pairs by age](docs/evaluation/2026-10-03-entities-final-links-and-age-split.md) | live (`build_entities`, `scripts/route_pairs_by_age.py`; national home) |
| 2026-10-03 | [Coverage by stratum: link rates vary, but mostly with the evidence, not with coverage](docs/evaluation/2026-10-03-coverage-by-stratum.md) | live (`scripts/link_coverage.py`; national home) |
| 2026-10-03 | [Chance agreement (u) was sampling noise on its most important level](docs/evaluation/2026-10-03-chance-agreement-sampling-noise.md) | live (five draws per estimator; national home) |
| 2026-10-03 | [Establishment attributes as of the record](docs/evaluation/2026-10-03-establishment-attributes-as-of-record.md) | live (SIH-RD SE 2022-01 with 8 CNES enrichments; national home) |
| 2026-10-03 | [Which population series the Ministry's tables divide by: POPSVS, measured against TabNet](docs/evaluation/2026-10-03-population-series-against-tabnet.md) | live (TabNet tabulation; local population series) |
| 2026-10-03 | [Geography from TabNet and IPEA; context fields from IBGE](docs/evaluation/2026-10-03-geography-tabnet-ipea-and-fields.md) | live (TabNet, IPEA, IBGE APIs; maintainer home) |
| 2026-10-03 | [Contested health regions against TabNet's current table](docs/evaluation/2026-10-03-health-region-conflicts-against-tabnet.md) | measurement (geography pack; TabNet territorial table) |
| 2026-10-03 | [IBGE's regions across 31 years of territorial divisions: no municipality ever moved](docs/evaluation/2026-10-03-ibge-regions-across-vintages.md) | measurement (IBGE DTB 1994-2025; geography pack) |
| 2026-10-03 | [Census fields: sanitation, literacy and population by race (2010, 2022)](docs/evaluation/2026-10-03-census-2022-fields.md) | live (IBGE aggregates API; fresh home) |
| 2026-10-03 | [Municipality and procedure dimensions, checked against TabNet](docs/evaluation/2026-10-03-municipality-and-procedure-dimensions.md) | live (SIM-DO SE 2022, SIH-RD SE 2022-01; TabNet) |
| 2026-10-03 | [Exact chance agreement on equality, national SIH deaths → SIM](docs/evaluation/2026-10-03-exact-chance-agreement.md) | live (national 2022 link, linkage home) |
| 2026-10-03 | [SIH money is in one unit across every era (Acre, 1992–2023)](docs/evaluation/2026-10-03-sih-money-units-across-eras.md) | live (mirror microdata; TabNet) |
| 2026-10-03 | [Renamed columns: what values can and cannot show](docs/evaluation/2026-10-03-renamed-columns.md) | live (93 layout boundaries sampled through the mirror; fresh home) |
| 2026-10-03 | [Official concept lists as dimensions, checked against TabNet](docs/evaluation/2026-10-03-official-concept-lists.md) | live (semantics and label pack rebuild; SIM SE 2022, SIH SE 2022-01; TabNet) |
| 2026-10-03 | [SINAN dengue deaths → SIM (national 2022)](docs/evaluation/2026-10-03-sinan-dengue-deaths-to-sim.md) | live (national probabilistic link) |
| 2026-10-03 | [SINAN linkage potential: what the schemas offer, and what was measured](docs/evaluation/2026-10-03-sinan-linkage-potential.md) | schema census; live (national 2022 links) |
| 2026-10-03 | [Climate field from INMET stations (station-month, placed by location)](docs/evaluation/2026-10-03-climate-field.md) | live (Zenodo mirror of INMET; NOAA ISD; IBGE mesh) |
| 2026-10-03 | [Disasters field from S2iD (one row per municipal event, 1991–2025)](docs/evaluation/2026-10-03-disasters-field.md) | live (MIDR open data) |
| 2026-10-03 | [Municipality points: seat and population centre instead of polygon centroids](docs/evaluation/2026-10-03-municipality-points.md) | live (IBGE Localidades 2022, Census 2022 tracts) |
| 2026-10-03 | [Age-standardised rates (direct, over POPSVS)](docs/evaluation/2026-10-03-age-standardised-rates.md) | live (SIM-DO SE 2022; POPSVS) |
| 2026-10-03 | [SINAN descriptions against the official data dictionaries](docs/evaluation/2026-10-03-sinan-descriptions-against-dictionaries.md) | audit (dictionary texts; 46 variables corrected) |
| 2026-10-03 | [Residence compared by distance between population centres](docs/evaluation/2026-10-03-residence-distance-bands.md) | live (national 2022 links, not stored) |
| 2026-10-03 | [SINAN form dictionaries: page-break truncation, coded fields marked uncoded](docs/evaluation/2026-10-03-sinan-form-dictionaries.md) | live (SINAN.ACBI 2023 BR) and audit (stored decisions against each form's DEF) |
| 2026-10-03 | [An export older than its native file is an older edition](docs/evaluation/2026-10-03-stale-export-editions.md) | live (SINAN.ACBI 2023, repo and fresh home); catalog count |
| 2026-10-03 | [SINAN undecoded sweep: every form, 2023, fresh home](docs/evaluation/2026-10-03-sinan-undecoded-sweep.md) | live (57 forms, 5.2M rows, three runs) |
| 2026-10-04 | [Open questions pass: curation, join grain, linkage evidence, rebuild speed](docs/evaluation/2026-10-04-open-questions-pass.md) | live (joins, SE 2022 link) and audits |
| 2026-10-04 | [Storage, measured: spill, role caches, blob pruning, lake encodings](docs/evaluation/2026-10-04-storage.md) | measurement (linkage home) and live (build/prune on the live home) |
| 2026-10-04 | [A role for every column, and event types against TabNet](docs/evaluation/2026-10-04-roles-and-event-types.md) | live (national 2022, linkage home) and TabNet |
| 2026-10-04 | [National cause-of-death aggregation 2010–2023; ANS and INEP as population sources](docs/evaluation/2026-10-04-aggregation-and-population-sources.md) | live (national SIM, three runs) and source checks (ANS TabNet, INEP margins) |
| 2026-10-04 | [Defects PegaSUS found: ICD-10 COVID categories, border lengths, log-normal accumulator, record identity, a refused representation, SINAN dates, RACACOR labels](docs/evaluation/2026-10-04-pegasus-core-fixes.md) | rebuild diffed against the shipped packs; live (SINASC, SINAN dengue, LEPT, CHAG, ESQU, ZIKA, CHIK; SIM/SINASC/SIH/SINAN translate) |
| 2026-10-05 | [Decode memory: a ctypes slice cost 10x the DBF per worker; decode admission; streaming label-pack build](docs/evaluation/2026-10-05-decode-memory.md) | measurement (SIH-RD blobs, decode pool, 3 processes) and live (SIM.DO 2022 national) |
| 2026-10-05 | [Snapshot: first and second run on the real home, a simulated revision, `as_of`; 92 files the mirror held in an older state](docs/evaluation/2026-10-05-snapshot.md) | live (real home, 915 declared files, 1.74 GB; scratch home) |
| 2026-10-05 | [Race bridge: SIM against the declaration at birth as a confusion matrix; infant mortality by race raw vs bridged vs linked truth; the adult plan](docs/evaluation/2026-10-05-race-bridge-model.md) | live (52,063 linked infant deaths 2021–22, held-out year, NUTS) and an ecological identification test |
| 2026-10-05 | [The general SIDRA interface: 15 fields and the three censuses reproduced cell for cell; race categories short of the Total by 6,608 (2010) and 11,119 (2022); the survey of 9,336 tables; sanitation across censuses](docs/evaluation/2026-10-05-sidra-general-interface.md) | live (IBGE aggregates API, 8,000 values a second) and a diff against the previous implementation |
| 2026-10-05 | [Care-flow graph: SIH-RD 2019 and 2022 reconciled to TabNet; 34% of admissions away from the residence municipality; Curitiba 2019 explained (one Campo Largo hospital); flow communities keep 6-8 pp more away admissions than the official regions](docs/evaluation/2026-10-05-care-flow-graph.md) | live (national SIH-RD, core data home, 12.2-12.4 M admissions per year) |
| 2026-10-05 | [Population account: 2010→2022 hold-out against the PES-corrected census (0.057 vs 0.079 vital-only), sensitivities, interval calibration by region and band](docs/evaluation/2026-10-05-population-account.md) | hold-out (core data home, 5,559 entities, 100 draws); build in the entry |
| 2026-10-05 | [Population account v2: a lagged-migration regression beats vital-only on 2000→2010 (0.052 vs 0.074) and 2010→2022 (0.056 vs 0.079) with 80% intervals at 0.79/0.84; horizon law checked on the 2007 Contagem; band intervals calibrated; shipped as `population-account-2`](docs/evaluation/2026-10-05-population-account-v2.md) | cross-period hold-out + 2007 Contagem (core data home, 5,472 comparable areas and 5,559 entities, SIDRA 200/202/5938/793) |
| 2026-10-05 | [Population account v3: municipal split (births indicator tested and discarded, 56 real creations against the 2007 Contagem), single ages, race by cohort with reclassification (hold-outs on the 2010 census); pseudo-forecasts to 2030 from bases 2000 and 2010; backcast to 1991 against the Contagem 1996 (SIDRA 306 diagnosed: not a table; 475/472 are); shipped as `population-account-3`, `-4` and `-5`; `-6`: the intercensal residual carried by an age schedule of migration (Contagem 1996 by age; the exposure test's women 20-44 diagnosed against the PES-corrected 2022 census)](docs/evaluation/2026-10-05-population-account-3.md) | 3,583 neighbour pairs, 2007 Contagem, 2010 census race hold-outs (core data home, SIDRA 9606/2093/793); Contagem 1996 hold-out of 4,294 areas, SIM.DOR 1991-95 |
| 2026-10-05 | [Label pack: the minority-kit rule destroyed 12,731 valid runs (SIH CIDX open windows, UNISAU/BR_REG registers, wording-only codebooks); it now drops only the minority kit of a recoded small codebook inside one system and window, which leaves SINASC RACACOR 5 and 6-8 as the only difference from the pack before the rule](docs/evaluation/2026-10-05-label-pack-kit-rule.md) | rebuild from the local catalog (662,108 conflicts) and a run-level and code-level diff against `2a3d192^`; `translate` on SIM/SINASC RACACOR |
| 2026-10-05 | [Census series across 2000, 2010 and 2022 (literacy, sanitation, race, urban, income) as fields: existing fields unchanged, shares equal IBGE's national figures](docs/evaluation/2026-10-05-census-series-fields.md) | live (IBGE aggregates API) and a diff against the previous fields |
| 2026-10-05 | [Completeness of SIM and SINASC by UF (rolling-origin extension of the published ratio, growth balance, census-based SINASC) and the population without private coverage 2021-2023; rebuilt on population-account-2](docs/evaluation/2026-10-05-completeness-and-sus-dependent.md) | rolling origin, growth balance, coherence, cohort check of births (core data home) |
| 2026-10-05 | [SIA APAC families: header-row inventory of 41,832 files; event types for AQ, AR, AN, ATD (events = first or only row of each APAC, equal to the rows of type 1 or 3); the CNS pseudonym recurs across years and families; `AP_MNDIF` was constant and mislabelled](docs/evaluation/2026-10-05-sia-apac-families.md) | live reads (AC, DF slices) on the core data home, mirror |
| 2026-10-05 | [Race bridge for adults: women 15-49 linked to their births as mothers; the control per municipality size; out-of-sample 2015-18 to 2019-22; the infant matrix transported fails for Preta](docs/evaluation/2026-10-05-race-bridge-adult.md) | live (SIM x SINASC 2012-2022, 20,084 pairs in municipalities under 2,000 mother groups; `pegasus_project/data/agent_race_adult/`) |
| 2026-10-05 | [CNES supply fields 2008-2023: 35 December-stock fields (establishments, beds, equipment, professionals, teams) for 5,570 municipalities, 0 unallocated codes, national magnitudes and six places checked; distinct physicians overstate; the 2020 typology and bed steps noted](docs/evaluation/2026-10-05-cnes-supply-fields.md) | `fields` build over 2,160 CNES state files (core data home, mirror) |
| 2026-10-05 | [SIM and SINASC 1996 kit change: 35 same-named codelists differ between eras (19 in meaning: CIRCOBITO 1/3, LOCOCOR 2/4, RACACOR, ...), the later-ingested kit overwrote the other; era windows (ADR-0152), checked against the layout and the records](docs/evaluation/2026-10-05-sim-code-eras.md) | kit comparison, layout `sim2025.txt`, DORRJ/DOAC/DOFET records, fresh-home `translate` |
| 2026-10-08 | [Missing codes declared by the record's own form across SINAN, refined the same day: the form decides where it speaks, the tabulation where it is silent, a code neither defines is a CONFLICT (1,227 columns declared over 54 forms, 39 conflicts by cause); field layouts harvested (2,293 SINAN fields typed); role drafts reviewed for 56 forms; PegaSUS reads 2,714 of 5,335 columns over 62 datasets](docs/evaluation/2026-10-08-declarations-by-form.md) | `scripts/propose_missing.py`, `data/probes/p1/`, `p1b/`, `p1c/`, `review/` |
| 2026-10-08 | [SIH 2008–2010 labels: the label pack chose a codelist's vintage before its system (CIH's SEXO and RACACOR dated 2008–2010 pre-empted SIHSUS's current rows, then were refused as a borrow); fixed, SIH 2008 and 2010 labelled on every record; 378 system-codelists had shadowed years in the pack fallback; 2008–2010 bound in PegaSUS's root](docs/evaluation/2026-10-08-label-pack-vintage-by-system.md) | small reads (SIH-RD AC 2008-06, 2010-01, 2011-01) on PegaSUS's root, `pegasus-data bindings`, `data/probes/p2/` |
| 2026-10-08 | [`translate` throughput, 22 s a call to 0.1 s: the reference-table staleness fingerprint covered role edits (rewrites of about 70 s, two processes rewriting each other's stamps), "anything materialised?" walked 283,000 directories, and "dictionary empty?" counted its rows (`has_rows`)](docs/evaluation/2026-10-08-translate-throughput.md) | cProfile on SINAN columns, the repo data home |
| 2026-10-08 | [Typing every dataset: 100 of 170 catalog datasets carry roles (7,273 columns, no drafts), SIM/SINASC legacy layouts on their 1996+ roles, SIH, CIH and SIA's twenty families (SIA.PR declared); SIH-SP `SP_PF_DOC` is the professional's CNS (11,816 of 11,816 pass the check, the IT's descriptions transposed); SINAN Windows notes that borrowed other forms' meanings corrected from the values; the FTP's `/siasus` documentation tree found](docs/evaluation/2026-10-08-typing-every-dataset.md) | `scripts/role_evidence.py`, `data/probes/review/`, `data/probes/ftp_outside_siasus.txt` |
