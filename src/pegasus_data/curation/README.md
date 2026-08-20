# `curation/` — the human half of the dictionary

Everything under `lake/` and in the catalog's `dictionary` table is **machine
output**: extracted from the FTP tree and regenerable by re-running the pipeline.
Nothing here is. These files hold what a variable *means*, which is not
recomputable and therefore belongs in version control, where a diff shows who
changed an interpretation, when, and on what evidence.

`pegasus-data curate` loads them into `variable_docs`, `dataset_docs`,
`field_codelists` and `prefix_systems`. The load **replaces** what these files
own, so deleting an entry here deletes it from the catalog — that is what makes
the file the source of truth rather than a suggestion.

## Rungs of evidence

Every entry carries a `source`, and they are not interchangeable:

| `source`     | means                                                        |
|--------------|--------------------------------------------------------------|
| `manual`     | a person asserts this. Requires `asserted_by`.                |
| `layout_doc` | read out of a record-layout PDF on the FTP tree.              |
| `def`        | taken from a `.DEF` display name.                             |
| `web`        | from off-tree documentation. Cite it in `source_ref`.         |
| `inferred`   | deduced from values, name and domain. **Requires `reasoning`.** |

`inferred` is last for a reason. An inferred description is useful; an inferred
description presented as documented is the failure this whole module exists to
prevent, so the loader refuses an `inferred` entry that does not write out its
reasoning.

## Files

    curation/variables/<system>_<series>.yml   one per dataset
    curation/datasets.yml                      what one row IS, per dataset
    curation/systems.yml                       prefix -> system overrides

## Fields

`official_name` is Portuguese, as the record layout names the column.
`translated_name` is English and is used **for documentation and export only** —
never to rename a column in the lake, because the lake's column names must stay
the names DATASUS uses or every published query breaks.

`multi_valued` requires a `token_rule` saying how to split: `{width: 4}` for
fixed-width packing, `{delimiter: "*"}` for a separator, or both.

`depends_on` names variables needed to interpret this one. `modifies` is the
inverse: this variable changes another's meaning. `IDADE` is meaningless without
`COD_IDADE`, and the pair is the canonical case.
