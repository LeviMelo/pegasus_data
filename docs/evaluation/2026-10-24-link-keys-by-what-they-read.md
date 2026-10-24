# A role table's key names what it reads, not the label pack (2026-10-24)

**Regime.** Branch from `4c7fbfd` plus this change; a scratch data home (a copy of the real catalog, junctions to the real
lake's CIHA, SIM, SINAN, SINASC and SIHSUS, its own `roles/`); the real home only read. Scripts outside the repository.

**The defect.** `roles.table_key` hashed the content of four resource files (`labels.parquet` and three others), so
8d43fbf (CIH's 199,831 rows re-windowed: only `valid_to` of rows with `system = 'CIH'`, 138 codelists) re-keyed every role
table and, through `store.fingerprint`, every stored link run of every dataset.

**What a role table reads.** Only a sex, a place, a facility and a category (`_READS_LABELS`) are read from the rendered label;
every other role is read as filed, a derived age from the raw columns. Tracing the codelists the render labelled them with
(`RenderReport.codelist_used`) and the files opened:

| dataset, 2022 | labelled columns | labelled with | named by the key |
|---|---|---|---|
| SINAN-TOXC, TOXG | 4 | `SEXO`; seven municipality-axis tables; `UNIDANET` + `CADGERBR` | 10 |
| SIM-DO | 11 | `CURATED.SIM.DO.*` (form dictionary), `CURATED.SIM.RACACOR`; `BR_MUNICIPALFA` + `MUNICBR`; `CADGERBR` | 22 |
| SINASC-DN | 9 | `CURATED.SINASC.*`, `GRAVIDEZ`, `PARTO`, `RACACORMAE` + `RACA`, `BR_MUNICIPALFA` + `CIR*`; `CADGERBR` | 15 |
| SIH-RD | 5 | `SEXO`, `RACACOR`, `BR_MUNICIPALFA` + `MUNICBR`; `CADGERBR` | 5 |
| CIHA | 4 | `SEXO`, `BR_MUNICIPALFA` + `BR_MUNICIP` + `BR_REGIAO` + ...; `CADGERBR` | 8 |

Of the four resource files, `labels.parquet` is the only one opened; `labels_crosswalk.parquet` and `code_lists.parquet` serve
enrichments and code structures, which a role table does not ask for. The tables are the system's own pack rows, curated tables of
the curation, and the CNES registry of the data home. SIH-RD also opens `sigtap.parquet` and `bridges.parquet`, for the derived
procedure columns that no role takes. None of the 692,005 labels of `CADGERBR` contains "ignorad", the only thing a facility
role asks of a label.

**The key.** Version, dataset, year; the record kind and roles; the lake partition files; for each codelist the labelled columns
can be labelled with in the year's families (`label_bindings.label_candidates`: the curated doc, the form's dictionary, and, where
the curation does not decide, the stored decisions or the bound tables), its name and `reference_fingerprint`: the pack rows of
the dataset's system and the shared ones in every window, or the curated table. `setting` moved to the run's fingerprint. The
label work of a key is 1.2-1.7 ms beside a file listing of 2-84 ms; the first key of a process, which reads the catalog and
the curation, takes 0.01-0.96 s.

**Does the key move?** Old (whole files) against new, 2022, on the shipped pack with one label edited in a scratch copy:

| change | SIM-DO | SINASC-DN | SIH-RD | CIHA | TOXC | TOXG |
|---|---|---|---|---|---|---|
| the incident: `8d43fbf~1` to `8d43fbf` (CIH re-windowed) | same | same | same | same | same | same |
| CIH `SEXO`; SIM `CID10`; SIHSUS `CID10` | same | same | same | same | same | same |
| SIHSUS `SEXO`; SIHSUS `MUNICBR` | same | same | **moved** | same | same | same |
| SIM `SEXO`; SIM `MUNICBR` | **moved** | same | same | same | same | same |
| CIHA `SEXO` | same | same | same | **moved** | same | same |
| SINAN `SEXO` | same | same | same | same | **moved** | **moved** |

The old key moved on every row of the table. A curated table edited (`CURATED.SIM.DO.SEXO`, never in the key before) moves SIM-DO
only. End to end in the scratch home: `sinan_toxc_to_sim` 2022 made under the pack of `8d43fbf~1` is current under `8d43fbf`,
stale (`inputs changed since the run`) under an edited SINAN `SEXO`, current again with the shipped pack.

**Is the table the same?** Built through `role_table` under the new key and compared with the national table cached in the real
home under the old key (`Table.equals`, metadata included): SINAN-TOXC 4,583 rows, SINAN-TOXG 12,447, SIM-DO 1,544,266 (10 s),
SINASC-DN 2,561,922 (29 s), CIHA 20,549,661 (147 s, 518,249,575 bytes in both): equal. Six datasets build with the check
passing; a candidate set without `MUNICBR` makes the SIH-RD build raise, naming `MUNIC_RES` and `MUNIC_MOV`.

**Stored runs.** 198 reports (`links/*/*.json` less `_params`). Under the old scheme, with the pack of `8d43fbf~1`: 53 were
current before the re-window (ciha_deaths_to_sim 9, sih_admissions_to_sim 12, sih_deaths_to_sim 10,
sih_toxoplasmosis_admissions_to_sim 4, sim_maternal_deaths_to_admission 9, sinan_toxc_to_sih_admission 5, sinan_toxc_to_sim 4);
114 were stale before it (reason not examined); 31 are of a spec edited since. The new scheme re-keys all 198 once; the 53
are the ones a mass re-make would have to redo for the re-window alone (`pegasus-data link <spec> --period ... --geo ...` each).

**Left.** `_aggregate._fingerprint` hashes `geography.parquet` whole and the whole curation's digest: other artifacts, read whole
for roll-ups, not changed here. A registry's content is not in the key (it never was).
