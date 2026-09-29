## 2026-08-23 — Source selection and analytical filtering are different products

*Split from docs/history/FINDINGS.md §3o (first) on 2026-09-28; text unchanged.*

## 3o. Source selection and analytical filtering are different products (2026-08-23)

The replacement review adjudicated a scope ambiguity left by §3m–§3n:
Pegasus-Data retrieves, decodes, harmonizes and semantically serves DATASUS
publications; the researcher defines the analytical population afterward.

The resulting rules are durable:

1. **Publication coordinates may select observations; fact meanings may not.**
   `period="2024-03"` selects the March publication when one exists. It does not
   mean `DT_INTER`, `DTOBITO` or another event date falls in March. Likewise a
   publication UF never becomes a `MUNIC_RES`/`MUNIC_MOV` predicate.
2. **Source competence is immutable provenance.** `_competencia` may choose a
   monthly lake slice or historical semantic relation, but no ordinary record
   field may overwrite it. Annual source enclosure has no invented month; its
   safe semantic vintage is the coarse January–December interval.
3. **Completeness belongs to logical source units.** The required key is at
   least `(family, logical publication, archive member)`. Path-only lake
   provenance cannot prove a multi-member archive complete; alternate physical
   representations remain equivalent when that complete key agrees.
4. **Reconciliation precedes family execution.** A logical publication split
   across two schema families is still one representation decision. An open
   conflict blocks even when a later family sees only one candidate.
5. **Unknown historical validity resolves to null, not “current”.** Temporal
   relation windows and packed mappings require source vintage unless explicitly
   time-invariant. Local adjudication then outranks shipped curation, which
   outranks the legacy bridge, with dataset/system specificity deterministic.
6. **Runtime resources have one resolution interface.** Optional CNES artifacts
   carry local manifest identity, checksum and exact covered years and are opened
   through `ResourceManager`. Static packs validate there; lake-backed resources
   delegate integrity/completeness to lake catalogs and fingerprints. Registry
   lookup follows the CNES identifiers and validity period in the selected slice,
   not the fact publication's UF.
7. **Planning is metadata-only.** Catalog/inventory/schema/resource metadata may
   be scanned during planning; fact rows are opened only for requested-slice ETL
   or an explicit bounded resource/maintainer operation.

The old `time_by`, `geography_by` and `unresolved_time` query switches were
removed. Their semantic knowledge remains under `semantic_axes` in curation for
`describe()`, documentation and future opt-in analytical helpers. The compact
`query_capabilities.json` is now compiled from separate `source_publication`
curation and carries no record-field predicates.

The closing real-resource audit re-read the shipped 1,774,993-row crosswalk and
reproduced all published cardinalities, including 1,816 and 13,923 pairwise
overlaps. The current 92.8 MB working catalog (not the historical recovered
15 GB evidence warehouse measured in §3m) contained 3,716 logical publications
with alternatives, 12,323 physical files in those groups and 8,607 avoidable
decodes. A metadata-only `plan("SIH-RD", period="2023-01", geography="AL")`
completed against that catalog without opening fact data.
