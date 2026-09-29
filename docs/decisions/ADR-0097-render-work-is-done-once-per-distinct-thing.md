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
- **Presentation formats per distinct (code, label) pair**
  (`presentation._render_value`).
- **A field's own tables label it first; `label_via` fills the rest.** Its own
  tables name the value itself, such as a CNPJ's legal name or a documented
  sentinel. `PA_CNPJMNT`, `AP_CNPJMNT` and `CNPJMNT` declare all zeros as
  "Sem mantenedora", in the 14 and 13 characters the files use.

**Result.**

| query (live home) | before | after |
|---|---:|---:|
| SIASUS-ACF 2023-01 | 43 s | 15 s |
| SIASUS-ACF 2023, files cached | 104 s | 40 s |

The rows are identical. A year is still not "seconds". What remains is
per-group binding selection (`_select_codelists`) and reading the registry
parquet per group. They are next.
