# Municipality and procedure dimensions, checked against TabNet

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`, uncommitted work of ADR-0130 and ADR-0131;
- data home `C:\Users\Galaxy\pegasus_linkage` (its 2022 lake);
- membership pack `resources/geography.parquet` as committed (before the
  TabNet and IPEA classifications were compiled into it).

**Why.** A dimension is only useful if it lands every record in the right
group. What is counted: the rows each dimension leaves null, and the group
totals against TabNet's own tabulation of the same publication.

## Municipality roll-ups (ADR-0130)

SIM-DO SE 2022, 14,791 deaths, in 14 s:

| dimension | null | top values |
|---|---|---|
| `CODMUNRES.health_region` | 0 | SE Aracaju 5,187; SE Nossa Senhora do Socorro 2,095 |
| `CODMUNOCOR.ibge_immediate_region` | 0 | Aracaju 8,577; Itabaiana 1,532 |
| `CODMUNRES.ibge_mesoregion` | 1 | Leste Sergipano 9,698 |
| `CODMUNRES.capital` | 10,806 | Aracaju 3,985 |

- **The one null mesoregion is `280000`,** "Município ignorado – SE",
  rightly unresolved.
- **`capital` is null outside capitals,** as the old `CAPITAL` relation was.
- **None contested.** SIM names its own table, so its claim is chosen.

## Procedure roll-ups (ADR-0131)

SIH-RD SE 2022-01 (file RDSE2201), 8,512 AIH, 6.1 s for four dimensions.
Every row resolved. Against TabNet (`sih/cnv/qise.def`, `qise2201.dbf`,
"Internações" by "Grupo procedimento"):

| group | pegasus_data, all AIH | of which `IDENT` 5 (long stay) | pegasus_data without `IDENT` 5 | TabNet |
|---|---|---|---|---|
| 02 Diagnostic | 10 | 0 | 10 | 10 |
| 03 Clinical | 5,187 | 51 | 5,136 | 5,136 |
| 04 Surgical | 3,293 | 0 | 3,293 | 3,293 |
| 05 Transplants | 22 | 0 | 22 | 22 |
| total | 8,512 | 51 | 8,461 | 8,461 |

- **Every group matches TabNet once continuation AIHs are excluded.**
  TabNet's "Internações" counts admissions; an `IDENT` 5 AIH continues one.
  The dimension is right; the difference is the measure.
- **Subgroups agree where read,** for example 0303 Tratamentos clínicos
  (outras especialidades): 2,906 in TabNet.

## Found on the way

`_apply_dimensions` resolved the effective relations per row, querying the
catalog for every month of every row. The first SIH run did not finish in
two minutes. The relations are now cached per vintage interval, and the run
takes 6.1 s.
