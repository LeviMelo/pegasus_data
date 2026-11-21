"""CNES supply fields: establishments, beds, equipment, professionals and primary-care teams by municipality.

CNES publishes one DBC per dataset, state and month (``Dados/<DS>/<DS><UF><YY><MM>.dbc``, read through the
DATASUS mirror, DATA_SOURCES §1). A field here is the **December** file of each year: a stock at the end of the
year, never a sum of months. Each state file is aggregated once to a small table (municipality x the keys a
field needs) and cached; ``fields.py`` turns those into the declared fields (``curation/fields.yml``, ``cnes:``
holds the code groups).

Four rules keep the layer honest:

* the municipality is the establishment's ``CODUFMUN``, with the Federal District's administrative-region codes
  mapped to Brasília exactly as the ``CODUFMUN_municipio`` derived column does (200508 to 201712);
* a code that is not an IBGE municipality is **unallocated**: counted and reported, never dropped quietly;
* a team or professional is counted from the file that registers it, with no inference about who it serves;
* a municipality that has no establishment at all in a year's ST file is *not in the register* that year (a null
  with a status), not a zero.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from ..transport import download

BASE = "https://datasus-ftp-mirror.nyc3.digitaloceanspaces.com/CNES/200508_/Dados/"
UFS = ("AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE",
       "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO")
DATASETS = ("ST", "LT", "EQ", "EP", "PF")
#: DT_DESAT of a team that is not deactivated (CNES writes a far-future sentinel, 900001).
NOT_DEACTIVATED = ("", "900001")
HOURS = ("HORAOUTR", "HORAHOSP", "HORA_AMB")
_COLUMNS = {
    "ST": ("CNES", "CODUFMUN", "TP_UNID", "VINC_SUS"),
    "LT": ("CODUFMUN", "TP_LEITO", "CODLEITO", "QT_EXIST", "QT_SUS", "QT_NSUS"),
    "EQ": ("CODUFMUN", "TIPEQUIP", "CODEQUIP", "QT_EXIST", "QT_USO", "IND_SUS"),
    "EP": ("CODUFMUN", "IDEQUIPE", "TIPO_EQP", "DT_DESAT"),
    "PF": ("CODUFMUN", "CBO", "CNS_PROF", "PROF_SUS", *HOURS),
}


def groups() -> dict[str, Any]:
    """The ``cnes:`` block of ``curation/fields.yml``: which codes make each group."""
    from ..config import curation_root
    from ..ontology import _read_yaml

    return dict((_read_yaml(curation_root() / "fields.yml") or {}).get("cnes") or {})


def _remap(year: int) -> dict[str, str]:
    """The Federal District's region codes -> 530010, from the ``CODUFMUN_municipio`` derived column."""
    from ..config import curation_root
    from ..ontology import _read_yaml

    shared = _read_yaml(curation_root() / "variables" / "cnes" / "_shared.yml")
    derived = next(d for d in shared["variables"]["CODUFMUN"]["derived"] if d["name"] == "CODUFMUN_municipio")
    window = derived["valid"]
    return dict(derived["remap"]) if window["from"] <= year * 100 + 12 <= window["to"] else {}


def fetch(dataset: str, uf: str, year: int, cache_dir: str | Path) -> Path:
    """One state's December file, downloaded once into the cache (the mirror is byte-identical to the FTP)."""
    name = f"{dataset}{uf}{year % 100:02d}12.dbc"
    return download(f"{BASE}{dataset}/{name}", Path(cache_dir) / "dbc" / name, timeout=1800.0)


def _municipality(table: pa.Table, year: int) -> pa.Table:
    code = table.column("CODUFMUN")
    mapping = _remap(year)
    if mapping:
        code = pc.if_else(pc.is_in(code, value_set=pa.array(list(mapping))),
                          pa.scalar("530010"), code)
    return table.drop_columns(["CODUFMUN"]).add_column(0, "municipality", code)


def _in_group(cbo: pa.Array, prefixes: list[str]) -> pa.Array:
    """Whether each CBO code starts with one of a group's prefixes."""
    hit = pa.array([False] * len(cbo))
    for prefix in prefixes:
        hit = pc.or_(hit, pc.starts_with(cbo, prefix))
    return hit


def _aggregate(dataset: str, table: pa.Table, year: int) -> pa.Table:
    """A state file summed to municipality x the keys its fields need."""
    table = _municipality(table, year)
    if dataset == "ST":
        table = table.group_by(["municipality", "TP_UNID", "VINC_SUS", "CNES"]).aggregate([])  # one row per establishment
        out = table.group_by(["municipality", "TP_UNID", "VINC_SUS"]).aggregate([("CNES", "count")])
        return out.select(["municipality", "TP_UNID", "VINC_SUS", "CNES_count"]).rename_columns(["municipality", "tp_unid", "vinc_sus", "n"])
    sums = {"LT": ["QT_EXIST", "QT_SUS", "QT_NSUS"], "EQ": ["QT_EXIST", "QT_USO"]}
    if dataset in sums:
        keys = {"LT": ["TP_LEITO", "CODLEITO"], "EQ": ["TIPEQUIP", "CODEQUIP", "IND_SUS"]}[dataset]
        for column in sums[dataset]:
            table = table.set_column(table.schema.get_field_index(column), column, pc.cast(table.column(column), pa.int64()))
        out = table.group_by(["municipality", *keys]).aggregate([(c, "sum") for c in sums[dataset]])
        out = out.select(["municipality", *keys, *[f"{c}_sum" for c in sums[dataset]]])
        return out.rename_columns(["municipality", *[k.lower() for k in keys], *[f"{c.lower()}_sum" for c in sums[dataset]]])
    if dataset == "EP":
        table = table.append_column("active", pc.is_in(pc.fill_null(table.column("DT_DESAT"), ""),
                                                       value_set=pa.array(NOT_DEACTIVATED)))
        table = table.group_by(["municipality", "TIPO_EQP", "active", "IDEQUIPE"]).aggregate([])   # one row per team
        out = table.group_by(["municipality", "TIPO_EQP", "active"]).aggregate([("IDEQUIPE", "count")])
        return out.select(["municipality", "TIPO_EQP", "active", "IDEQUIPE_count"]).rename_columns(["municipality", "tipo_eqp", "active", "n"])
    raise KeyError(f"CNES-{dataset}: no aggregate")


def _pf_base(table: pa.Table, year: int) -> tuple[pa.Table, pa.Table]:
    """A PF file (one row per professional x establishment x occupation x contract) reduced to what any grouping of
    occupations needs: (municipality, cbo, hours, hours_sus, jobs) and the distinct (municipality, cbo, cns). The groups
    (curation) are applied afterwards by `_pf_groups`, so a change of a group never needs the 3.8 GB of files again."""
    table = _municipality(table, year)
    table = table.append_column("cbo", pc.fill_null(table.column("CBO"), ""))
    kept = None
    for column in HOURS:
        part = pc.cast(pc.fill_null(table.column(column), "0"), pa.int64())
        kept = part if kept is None else pc.add(kept, part)
    sus = pc.equal(pc.fill_null(table.column("PROF_SUS"), "0"), "1")
    table = table.append_column("hours", kept).append_column("hours_sus", pc.if_else(sus, kept, 0))
    cns = pc.fill_null(table.column("CNS_PROF"), "")
    table = table.append_column("cns", pc.if_else(pc.equal(cns, ""), pa.scalar(None, pa.string()), cns))
    jobs = table.group_by(["municipality", "cbo"]).aggregate([("hours", "sum"), ("hours_sus", "sum"), ("hours", "count")])
    jobs = jobs.select(["municipality", "cbo", "hours_sum", "hours_sus_sum", "hours_count"]).rename_columns(
        ["municipality", "cbo", "hours", "hours_sus", "jobs"])
    people = table.filter(pc.is_valid(table.column("cns"))).group_by(["municipality", "cbo", "cns"]).aggregate([])
    return jobs, people


def _pf_groups(jobs: pa.Table, people: pa.Table) -> pa.Table:
    """The professional groups of the curation applied to `_pf_base`'s tables: (municipality, group, hours, hours_sus,
    jobs, professionals). Groups may nest (ophthalmologists are physicians), so each group is selected on its own and an
    occupation counts in every group it belongs to; within a group a person is counted once."""
    parts = []
    for name, prefixes in groups()["professional_groups"].items():
        j = jobs.filter(_in_group(jobs.column("cbo"), prefixes))
        p = people.filter(_in_group(people.column("cbo"), prefixes))
        sums = j.group_by(["municipality"]).aggregate([("hours", "sum"), ("hours_sus", "sum"), ("jobs", "sum")])
        distinct = p.group_by(["municipality", "cns"]).aggregate([]).group_by(["municipality"]).aggregate([("cns", "count")])
        joined = sums.join(distinct, ["municipality"], join_type="left outer")
        joined = joined.append_column("group", pa.array([name] * joined.num_rows, pa.string()))
        parts.append(joined.select(["municipality", "group", "hours_sum", "hours_sus_sum", "jobs_sum", "cns_count"]))
    return pa.concat_tables(parts).rename_columns(["municipality", "group", "hours", "hours_sus", "jobs", "professionals"])


def _digest(dataset: str, year: int) -> str:
    """What a cached aggregate depends on besides its file: the columns read, the Federal District's remap of the year and,
    for PF, the professional groups of the curation (the other datasets are summed without any group)."""
    depends: dict[str, Any] = {"columns": _COLUMNS[dataset], "remap": _remap(year)}
    if dataset == "PF":
        depends["professional_groups"] = groups().get("professional_groups")
        depends["grouping"] = "nested"     # groups may overlap (ADR-0215); aggregates of the exclusive rule are rebuilt
    return hashlib.sha1(json.dumps(depends, sort_keys=True, default=str).encode()).hexdigest()[:16]


def state_table(dataset: str, uf: str, year: int, cache_dir: str | Path, *, keep_dbc: bool = False) -> pa.Table:
    """One state's December file as its aggregate; read from the cache, or fetched, decoded and cached.

    The aggregate carries the digest of what it was built with (`_digest`) in its metadata; one built under other curation
    is not served. A PF aggregate is re-grouped from the (municipality, occupation) tables kept beside it; the other
    datasets' small files are fetched again. An aggregate written before the digest existed is served as it is, except
    PF's: its groups are curation, and one written under fewer groups would serve a new group as zero everywhere."""
    agg = Path(cache_dir) / "agg"
    cached = agg / f"{dataset}{uf}{year}.parquet"
    digest = _digest(dataset, year)
    if cached.is_file():
        held = (pq.read_metadata(cached).metadata or {}).get(b"curation_digest")
        if (held is None and dataset != "PF") or (held is not None and held.decode() == digest):
            return pq.read_table(cached).replace_schema_metadata(None)
        jobs_file, people_file = agg / f"{dataset}{uf}{year}.jobs.parquet", agg / f"{dataset}{uf}{year}.people.parquet"
        if dataset == "PF" and jobs_file.is_file() and people_file.is_file():
            return _write(cached, _pf_groups(pq.read_table(jobs_file), pq.read_table(people_file)), digest)
    from ..decode.dbc import read_dbc

    path = fetch(dataset, uf, year, cache_dir)
    decoded = read_dbc(path, columns=frozenset(_COLUMNS[dataset]))
    table = decoded.to_table()
    del decoded
    missing = [c for c in _COLUMNS[dataset] if c not in table.schema.names]
    if missing:
        raise KeyError(f"CNES-{dataset} {uf} {year}: columns {missing} are not in the file")
    if dataset == "PF":
        jobs, people = _pf_base(table, year)
        agg.mkdir(parents=True, exist_ok=True)
        pq.write_table(jobs, agg / f"{dataset}{uf}{year}.jobs.parquet", compression="zstd")
        pq.write_table(people, agg / f"{dataset}{uf}{year}.people.parquet", compression="zstd")
        out = _pf_groups(jobs, people)
    else:
        out = _aggregate(dataset, table, year)
    _write(cached, out, digest)
    if not keep_dbc and dataset == "PF":
        path.unlink(missing_ok=True)              # 3.8 GB of professional files: the aggregate is what is kept
    return out


def _write(path: Path, table: pa.Table, digest: str) -> pa.Table:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table.replace_schema_metadata({"curation_digest": digest}), path, compression="zstd")
    return table


def year_tables(year: int, cache_dir: str | Path, log=print) -> dict[str, pa.Table]:
    """The five datasets of one December, all states, as one aggregate each (with the file's state)."""
    out: dict[str, pa.Table] = {}
    for dataset in DATASETS:
        parts = []
        for uf in UFS:
            part = state_table(dataset, uf, year, cache_dir)
            parts.append(part.append_column("file_uf", pa.array([uf] * part.num_rows, pa.string())))
        out[dataset] = pa.concat_tables(parts)
        log(f"CNES-{dataset} {year}: {out[dataset].num_rows} aggregate rows")
    return out


def _in(column: pa.Array, codes: list[str]) -> pa.Array:
    return pc.is_in(column, value_set=pa.array([str(c) for c in codes], pa.string()))


def values(spec: dict[str, Any], tables: dict[str, pa.Table]) -> dict[str, float]:
    """A declared field for one year: municipality (6 digits) -> value, from the year's aggregates."""
    g = groups()
    family = spec["family"]
    if family == "facilities":
        t = tables["ST"]
        listed = [c for codes in g["facility_groups"].values() for c in codes]
        group = spec["group"]
        mask = _in(t.column("tp_unid"), g["facility_groups"][group]) if group != "other" else pc.invert(_in(t.column("tp_unid"), listed))
        sus = pc.equal(t.column("vinc_sus"), "1")
        mask = pc.and_(mask, sus if spec["sector"] == "sus" else pc.invert(sus))
        t, column = t.filter(mask), "n"
    elif family == "beds":
        t = tables["LT"]
        if spec["kind"] in ("icu", "neonatal_icu"):
            t = t.filter(_in(t.column("codleito"), g[f"{spec['kind']}_bed_codes"]))
        column = {"all": "qt_exist_sum", "sus": "qt_sus_sum", "nonsus": "qt_nsus_sum"}[spec["sector"]]
    elif family == "equipment":
        t = tables["EQ"]
        code = pc.binary_join_element_wise(t.column("tipequip"), t.column("codequip"), "")
        t = t.filter(_in(code, g["equipment"][spec["equipment"]]))
        if spec["sector"] == "sus":
            t = t.filter(pc.equal(t.column("ind_sus"), "1"))
        column = "qt_exist_sum"
    elif family == "teams":
        t = tables["EP"]
        t = t.filter(pc.and_(_in(t.column("tipo_eqp"), g["team_groups"][spec["group"]]), t.column("active")))
        column = "n"
    elif family == "professionals":
        t = tables["PF"].filter(pc.equal(tables["PF"].column("group"), spec["group"]))
        column = {"jobs": "jobs", "hours": "hours", "hours_sus": "hours_sus", "professionals": "professionals"}[spec["measure"]]
    else:
        raise KeyError(f"unknown CNES family {family!r}")
    sums = t.group_by(["municipality"]).aggregate([(column, "sum")])
    return dict(zip(sums.column("municipality").to_pylist(), [float(v or 0) for v in sums.column(f"{column}_sum").to_pylist()], strict=True))


def register(tables: dict[str, pa.Table]) -> set[str]:
    """The municipalities with at least one establishment in the year's ST file."""
    return set(tables["ST"].column("municipality").to_pylist())
