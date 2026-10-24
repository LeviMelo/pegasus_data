# ADR-0202: a role table's key names the codelists its labelled columns can be labelled with, and a build is refused any other

**Date:** 2026-10-24. **Status:** accepted. Builds on ADR-0167 (a run is served while its fingerprint is current) and
ADR-0186 (the key reads content).

**Context.** A record's identity is a hash of its normalised fields, so a change to what a role table holds makes every stored id
match nothing: the fingerprint of a link run is the keys of the role tables it read. Those keys hashed the content of four
resource files, `labels.parquet` (every system's codelists) among them. On 2026-10-23 CIH's 199,831 label rows were re-windowed
(`valid_to` only, 138 codelists, all `system = 'CIH'`): CIH is a dataset no link reads, and every role table and all 198 stored
runs went stale, each run costing 8 to 12 minutes and up to 11 GB to make again (53 of them were current until then).

**Decision.**
- **A role table's key is what the table is computed from.** `roles.table_key`: version, dataset, year; the dataset's record
  kind and roles (the table holds every role, in their order); the year's lake partition files; and, for the labels, the
  codelists the labelled columns can be labelled with (`_labelled_columns`: the roles of a sex, a place, a facility and a
  category; the others are read as filed), each by name and `reference_fingerprint`. A role's `setting` is no table's content and
  moved to `store._fingerprint_of`.
- **The names are those the labelling ladder can return** (`label_bindings.label_candidates`, beside `decide`): the field's curated
  doc and the form's own dictionary always; where the curation does not decide, the reviewed adjudications and the stored
  decisions of the year's families, or the bound tables `weigh` would weigh. A superset of any outcome, whatever the values.
- **The digest is of what `read_reference_table` reads for the system** (`persist.reference.reference_fingerprint`, in its order
  of sources): the pack's rows of the system and the shared ones in every window (`labelpack.packed_fingerprint`, sorted), a
  curated table's codes and windows, a canonical file's content. Another system's rows, and every other codelist, are not in it.
  Without a catalog to name the codelists, the whole pack, as before.
- **A build that labelled a column from a name outside the set raises** (`roles._check_labels_named`, from the render's
  `codelist_used`): were a rung of the ladder missing from `label_candidates`, the table would be cached and the runs left current
  while their labels could change. It is an error at the first build, naming the column and the codelist.
- **Not in the key:** the CNES registry (the data home's, built from the server's kit, never in it). Role tables read a facility's
  label to ask whether it says "ignorado", and none of CADGERBR's 692,005 labels does.

**Evidence** (docs/evaluation/2026-10-24-link-keys-by-what-they-read.md). The incident's two packs, a CIH `SEXO` edit and a SIM and
a SIHSUS `CID10` edit leave the new keys of SIM-DO, SINASC-DN, SIH-RD, CIHA, SINAN-TOXC and TOXG 2022 as they were (the old
keys all moved); an edit of a codelist the columns can be labelled with moves only the datasets that name it. Role tables built
under the new key equal the cached ones cell for cell, metadata included: SINAN-TOXC 4,583 rows, TOXG 12,447, SIM-DO 1,544,266,
SINASC-DN 2,561,922, CIHA 20,549,661.

**Stored runs and caches.** Every key changes: the cached national role tables (rebuilt on use; a year's other keys are removed
by `_national_year`) and all stored runs are stale once and then stay current under changes to codelists no role reads. The 53
runs that were current before the re-window are listed in the evaluation; the others were stale already or are of an edited spec.
`ROLE_TABLE_VERSION` stays 1: what a table holds did not change.

**What would reverse it.** `_check_labels_named` raising on a real build: a source of names the ladder uses that
`label_candidates` lacks, to be added there. Role tables reading more of a registry than "ignorado" would put the registry's
content in the key. A cheaper way to know a render's codelists before it runs would replace the catalog read.
