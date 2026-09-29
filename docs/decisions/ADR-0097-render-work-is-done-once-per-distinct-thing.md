## ADR-0097: Rendering does its work once per distinct thing; a field's own codes come before a label reached through another column

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0084, ADR-0094.

**Context.** Measured with cProfile on the live home
(`query("SIASUS-ACF", period=...)`, AC–TO, 2,839 rows a month, 36,817 a year).
- **One month took 43 s.** 25 s of it was YAML: every curation reader parsed
  all 157 files with the pure-Python loader.
- **A cached year took 104 s,** longer than the first, downloading run. Each
  month is its own render group, and the cache key carried the month, so:
  - reference maps were rebuilt 492 times, the 692,004-row establishment
    registry among them;
  - `label_via` built a 692k-entry dict per group (25 s);
  - the presentation formatted 1.4 million cells one by one (34 s under the
    profiler).
- **The documented "no maintainer" could not be labelled.** A maintainer
  CNPJ of all zeros is documented ("ou zeros, caso não a tenha"), but the
  `label_via` branch returned before the field's own codes were consulted.

**Decision.**
- **YAML is parsed once per file version, with libyaml.** `curation.read_yaml`
  is cached on path, mtime and size, and returns a copy; the ontology reader
  uses the C loader too. Parsing all curation takes 0.45 s, down from 10.8 s.
- **Reference maps are cached per process.**
  - `view._lookup_map` and `_contradictions` are keyed on the table's version
    (its lake directory and registry file mtimes).
  - Tables with no vintages (canonical classifications, registries, inline
    codes, `UF_BR`, `CIR_BR`) drop year and month from the key.
- **Work moves into Arrow.**
  - `_contradictions` uses a group-by and brings only the conflicting codes
    into Python. Checked equal to the old result on SEXO, CADGERBR, IDADEDET,
    VINCULO, ICD10 and a synthetic conflict.
  - `_lookup_map` filters nulls and blanks before conversion, keeping
    last-line-wins.
  - `_label_via` is an `index_in`/`take` join.
- **A vintaged kit table's map is built once per distinct content**
  (`view._content_digest`): asked for month by month, it is usually the same
  table twelve times, and the packed copy carries no windows to key on.
- **A field's merged map is built once per process** (`view._merged_lookup`).
  It carries its code widths, and a single-table field is not copied entry by
  entry. Registry parquet reads are cached on the file's mtime
  (`registry._read`).
- **Presentation formats per distinct (code, label) pair**
  (`presentation._render_value`). The pairs are dictionary-encoded in Arrow and
  expanded back with `take`. Codelist selection counts observed values with
  `value_counts`, and registry name patterns are read once
  (`registry._patterns`).
- **A field's own tables label it first; `label_via` fills the rest.** Its own
  tables name the value itself, such as a CNPJ's legal name or a documented
  sentinel. `PA_CNPJMNT`, `AP_CNPJMNT` and `CNPJMNT` declare all zeros as
  "Sem mantenedora", in the 14 and 13 characters the files use.

**Result.**

| query (live home) | before | after |
|---|---:|---:|
| SIASUS-ACF 2023-01 | 43 s | 15 s |
| SIASUS-ACF 2023, files cached, second query in the process | 104 s | 15.2 s |
| the same, first query in a fresh process | — | 25 s |

The two warm runs return identical tables (`Table.equals`). The fresh
process's extra time is one-time work: the curation reload that followed
the YAML edits, and cold caches. What remains is per-group binding decisions
(`label_bindings.decide`, `relations_for`) and catalog reads.

**Also seen in this run.** Maintainer CNPJs now read "UNIVERSIDADE DO ESTADO
DO RIO DE JANEIRO (33540014000157)" and "Sem mantenedora (0000000000000)",
where they read `(?)`.
