"""Measurements behind record linkage (docs/plans/linkage.md, phase A2).

Every quantity is computed on roles (``curation/roles.yml``), so it is about
the property a column states, not the column:

    python scripts/linkage_study.py bits SINASC-DN 2022
    python scripts/linkage_study.py bits SIH-RD 2022
    python scripts/linkage_study.py channels SIASUS-PS 2022
    python scripts/linkage_study.py flows SIH-RD 2022
    python scripts/linkage_study.py coverage 2022-01
    python scripts/linkage_study.py joins 2023-01 SP

``bits``: how much identifying information each role carries (entropy), how
much combinations carry together (joint entropy), the share of records a key
makes unique, and the mutual information between residence and care place.
``channels``: how the same person's values disagree across records sharing an
exact identifier (SIA's encrypted CNS): the error model linkage must tolerate.
``flows``: where people are treated relative to where they live, by care type.
``coverage``: SIH and CIHA admissions side by side: CIHA's admissions share,
payers, and records that appear in both.

Scopes are read state by state for datasets published per state, so memory is
bounded by the largest state. Output: ``data/probes/linkage/<study>_<dataset>_<period>.json``.
"""

from __future__ import annotations

import json
import math
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

from pegasus_data.linkage.roles import dataset_roles, role_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "probes" / "linkage"
UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
NATIONAL_FILE = {"SINASC-DN", "SIM-DO"}

#: The key a linkage would build, one role at a time, strongest first.
KEYS = {
    "SINASC-DN": ["baby.birth_date", "baby.sex", "mother.residence", "mother.birth_date", "birth.weight", "birth.facility"],
    "SIM-DO": ["deceased.birth_date", "deceased.sex", "deceased.residence", "death.date", "death.facility"],
    "SIH-RD": ["patient.birth_date", "patient.sex", "patient.residence", "admission.end", "admission.facility"],
    "CIHA": ["patient.birth_date", "patient.sex", "patient.residence", "admission.end", "admission.facility"],
    "SIASUS-PS": ["patient.birth_date", "patient.sex", "patient.residence", "care.facility"],
}
PAIRS = {
    "SINASC-DN": [("mother.residence", "birth.facility")],
    "SIM-DO": [("deceased.residence", "death.facility")],
    "SIH-RD": [("patient.residence", "admission.facility"), ("patient.residence", "admission.facility_municipality")],
    "CIHA": [("patient.residence", "admission.facility")],
    "SIASUS-PS": [("patient.residence", "care.facility")],
}


def read(dataset: str, period: object, roles: list[str], extra: list[str] | None = None) -> pa.Table:
    wanted = list(dict.fromkeys(roles + (extra or [])))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if dataset in NATIONAL_FILE:
            return role_table(dataset, period=period, geography="BR", roles=wanted, allow_partial=True)
        from pegasus_data.retrieve import NothingPublished

        parts, missing = [], []
        for uf in UFS:
            t0 = time.time()
            try:
                part = role_table(dataset, period=period, geography=uf, roles=wanted, allow_partial=True)
            except NothingPublished:
                # A state with no publication is a recorded gap, not an error
                # and not a zero (CLAUDE.md §6).
                missing.append(uf)
                print(f"  {dataset} {period} {uf}: not published", flush=True)
                continue
            parts.append(part.append_column("_uf", pa.array([uf] * part.num_rows)))
            print(f"  {dataset} {period} {uf}: {part.num_rows} rows ({time.time() - t0:.0f}s)", flush=True)
        table = pa.concat_tables(parts, promote_options="default")
        return table.replace_schema_metadata({**(table.schema.metadata or {}), b"missing_states": ",".join(missing).encode()})


def q(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


def cols(names: list[str]) -> str:
    return ", ".join(f'"{n}"' for n in names)


def entropy(con: duckdb.DuckDBPyConnection, names: list[str], where: str = "") -> tuple[float, float]:
    """Joint entropy in bits, and the share of rows whose combination is unique."""
    (h, unique, n) = q(con, f"""
        WITH g AS (SELECT count(*) c FROM t {where} GROUP BY {cols(names)}),
             s AS (SELECT sum(c) n FROM g)
        SELECT -sum(c / n * log2(c / n)), sum(CASE WHEN c = 1 THEN 1 ELSE 0 END), max(n) FROM g, s""")[0]
    return float(h or 0), (float(unique) / float(n)) if n else 0.0


def bits(dataset: str, period: str) -> dict[str, Any]:
    keys = KEYS[dataset]
    pair_roles = sorted({r for pair in PAIRS[dataset] for r in pair})
    extra = ["admission.modality"] if dataset == "CIHA" else []
    table = read(dataset, period, keys + pair_roles, extra)
    con = duckdb.connect()
    con.register("t", table)
    where = "WHERE \"admission.modality\" = '02'" if dataset == "CIHA" else ""
    n = q(con, f"SELECT count(*) FROM t {where}")[0][0]
    result: dict[str, Any] = {"dataset": dataset, "period": period, "records": n, "bits_to_single_out": math.log2(n) if n else 0}
    result["roles"] = {}
    for role in keys + [r for r in pair_roles if r not in keys]:
        h, _ = entropy(con, [role], where)
        nulls = q(con, f'SELECT avg(CASE WHEN "{role}" IS NULL THEN 1.0 ELSE 0 END) FROM t {where}')[0][0]
        result["roles"][role] = {"bits": round(h, 2), "missing_share": round(float(nulls or 0), 4)}
    result["cumulative"] = []
    for i in range(1, len(keys) + 1):
        h, uniq = entropy(con, keys[:i], where)
        result["cumulative"].append({"key": keys[:i], "bits": round(h, 2), "unique_share": round(uniq, 4)})
    result["mutual_information"] = []
    for a, b in PAIRS[dataset]:
        both = f"{where + ' AND' if where else 'WHERE'} \"{a}\" IS NOT NULL AND \"{b}\" IS NOT NULL"
        ha, _ = entropy(con, [a], both)
        hb, _ = entropy(con, [b], both)
        hab, _ = entropy(con, [a, b], both)
        result["mutual_information"].append({"a": a, "b": b, "bits_a": round(ha, 2), "bits_b": round(hb, 2),
                                             "joint": round(hab, 2), "mutual_information": round(ha + hb - hab, 2)})
    if "_uf" in table.column_names:
        result["by_state"] = []
        for uf in UFS:
            w = f"{where + ' AND' if where else 'WHERE'} _uf = '{uf}'"
            m = q(con, f"SELECT count(*) FROM t {w}")[0][0]
            if not m:
                continue
            h, uniq = entropy(con, keys[:3], w)
            result["by_state"].append({"uf": uf, "records": m, "bits_to_single_out": round(math.log2(m), 2),
                                       "key": keys[:3], "bits": round(h, 2), "unique_share": round(uniq, 4)})
    return result


# Keys a slipping finger reaches: the numeric keypad and the top row.
_PAD = {"7": "84", "8": "795", "9": "86", "4": "751", "5": "8462", "6": "953", "1": "42", "2": "5130", "3": "62", "0": "2"}


def _adjacent(x: str, y: str) -> bool:
    return y in _PAD.get(x, "") or abs(int(x) - int(y)) == 1


def date_error(a: str, b: str) -> str:
    """How two birth dates of one person differ, as typed (DDMMYYYY)."""
    diff = [i for i in range(8) if a[i] != b[i]]
    part = lambda i: "day" if i < 2 else "month" if i < 4 else "year"  # noqa: E731
    if len(diff) == 1:
        i = diff[0]
        return f"one digit, {part(i)}, {'adjacent key' if _adjacent(a[i], b[i]) else 'other key'}"
    if len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]:
        return f"neighbouring digits swapped, {part(diff[0])}"
    if a[:2] == b[2:4] and a[2:4] == b[:2] and a[4:] == b[4:]:
        return "day and month swapped"
    if a[:4] == b[:4] and abs(int(a[4:]) - int(b[4:])) == 1:
        return "year off by one"
    if a[:4] == b[:4] and a[6:] == b[6:]:
        return "century differs"
    if a[:4] == b[:4]:
        return "year differs otherwise"
    if a[4:] == b[4:] and a[2:4] == b[2:4]:
        return "day differs by more than one digit"
    if a[4:] == b[4:]:
        return "day and month differ, same year"
    return "unrelated dates"


def channels(dataset: str, period: str) -> dict[str, Any]:
    """Disagreements between records that share an exact person identifier."""
    table = read(dataset, period, ["patient.id", "patient.birth_date", "patient.sex", "patient.residence"])
    con = duckdb.connect()
    con.register("t", table)
    people = q(con, 'SELECT count(DISTINCT "patient.id") FROM t WHERE "patient.id" IS NOT NULL')[0][0]
    multi = q(con, """SELECT count(*) FROM (SELECT "patient.id" FROM t WHERE "patient.id" IS NOT NULL
                      GROUP BY 1 HAVING count(*) > 1)""")[0][0]
    out: dict[str, Any] = {"dataset": dataset, "period": period, "records": table.num_rows,
                           "people": people, "people_with_several_records": multi}
    for role in ("patient.birth_date", "patient.sex", "patient.residence"):
        n = q(con, f"""SELECT count(*) FROM (SELECT "patient.id" FROM t WHERE "patient.id" IS NOT NULL
                       AND "{role}" IS NOT NULL GROUP BY 1 HAVING count(DISTINCT "{role}") > 1)""")[0][0]
        out[f"{role} disagrees"] = {"people": n, "share_of_people_with_several": round(n / multi, 5) if multi else None}
    pairs = q(con, """SELECT strftime(min("patient.birth_date"), '%d%m%Y'), strftime(max("patient.birth_date"), '%d%m%Y')
                      FROM t WHERE "patient.id" IS NOT NULL AND "patient.birth_date" IS NOT NULL
                      GROUP BY "patient.id" HAVING count(DISTINCT "patient.birth_date") = 2""")
    kinds: dict[str, int] = {}
    for a, b in pairs:
        kind = date_error(a, b)
        kinds[kind] = kinds.get(kind, 0) + 1
    out["birth_date_error_kinds"] = dict(sorted(kinds.items(), key=lambda kv: -kv[1]))
    single = {k: v for k, v in kinds.items() if k.startswith("one digit")}
    near = sum(v for k, v in single.items() if "adjacent" in k)
    out["one_digit_errors"] = {"total": sum(single.values()), "adjacent_key": near,
                               "adjacent_share": round(near / sum(single.values()), 3) if single else None,
                               "adjacent_share_if_random": round(sum(len(v) for v in _PAD.values()) / 90, 3)}
    if "_uf" in table.column_names:
        out["people_in_several_states"] = q(con, """SELECT count(*) FROM (SELECT "patient.id" FROM t
            WHERE "patient.id" IS NOT NULL GROUP BY 1 HAVING count(DISTINCT _uf) > 1)""")[0][0]
    return out


CARE = {
    "delivery": "(\"admission.procedure\" LIKE '0310%' OR \"admission.procedure\" LIKE '0411%')",
    "oncology": "\"admission.diagnosis\" LIKE 'C%'",
    "infection": "(\"admission.diagnosis\" LIKE 'A%' OR \"admission.diagnosis\" LIKE 'B%' OR \"admission.diagnosis\" LIKE 'J1%')",
    "all": "TRUE",
}


def flows(dataset: str, period: str) -> dict[str, Any]:
    """Residence → place of care, by care type."""
    table = read(dataset, period, ["patient.residence", "admission.facility_municipality",
                                   "admission.facility", "admission.procedure", "admission.diagnosis"])
    con = duckdb.connect()
    con.register("t", table)
    out: dict[str, Any] = {"dataset": dataset, "period": period, "records": table.num_rows, "care": {}}
    base = '"patient.residence" IS NOT NULL AND "admission.facility_municipality" IS NOT NULL'
    for name, cond in CARE.items():
        where = f"WHERE {base} AND {cond}"
        n, same_mun, same_uf = q(con, f"""SELECT count(*),
              avg(CASE WHEN "patient.residence" = "admission.facility_municipality" THEN 1.0 ELSE 0 END),
              avg(CASE WHEN substr("patient.residence",1,2) = substr("admission.facility_municipality",1,2) THEN 1.0 ELSE 0 END)
              FROM t {where}""")[0]
        ha, _ = entropy(con, ["patient.residence"], where)
        hb, _ = entropy(con, ["admission.facility_municipality"], where)
        hab, _ = entropy(con, ["patient.residence", "admission.facility_municipality"], where)
        top = q(con, f"""SELECT substr("patient.residence",1,2) o, substr("admission.facility_municipality",1,2) d, count(*) c
                         FROM t {where} AND o <> d GROUP BY o, d ORDER BY c DESC LIMIT 12""")
        out["care"][name] = {"admissions": n, "same_municipality": round(float(same_mun or 0), 4),
                             "same_state": round(float(same_uf or 0), 4),
                             "bits_residence": round(ha, 2), "bits_place": round(hb, 2),
                             "mutual_information": round(ha + hb - hab, 2),
                             "top_interstate_flows": [{"from": o, "to": d, "admissions": c} for o, d, c in top]}
    return out


def coverage(period: str) -> dict[str, Any]:
    """CIHA beside SIH-RD for one month: admissions, payers, and records in both."""
    key = ["patient.birth_date", "patient.sex", "admission.facility", "admission.start", "admission.end"]
    ciha = read("CIHA", period, key, ["admission.modality", "admission.payer", "patient.residence"])
    sih = read("SIH-RD", period, key)
    con = duckdb.connect()
    con.register("c", ciha)
    con.register("s", sih)
    out: dict[str, Any] = {"period": period, "ciha_records": ciha.num_rows, "sih_admissions": sih.num_rows}
    out["ciha_by_modality"] = dict(q(con, 'SELECT "admission.modality", count(*) FROM c GROUP BY 1 ORDER BY 2 DESC'))
    out["ciha_admissions_by_payer"] = dict(q(con, """SELECT "admission.payer", count(*) FROM c
        WHERE "admission.modality" = '02' GROUP BY 1 ORDER BY 2 DESC"""))
    out["ciha_admissions_residence_missing"] = q(con, """SELECT avg(CASE WHEN "patient.residence" IS NULL THEN 1.0 ELSE 0 END)
        FROM c WHERE "admission.modality" = '02'""")[0][0]
    out["ciha_states_not_published"] = (ciha.schema.metadata or {}).get(b"missing_states", b"").decode()
    cond = " AND ".join(f'c."{k}" = s."{k}"' for k in key)
    out["ciha_admissions_also_in_sih"] = q(con, f"""SELECT count(DISTINCT (c._blob_sha256, c._row)) FROM c JOIN s ON {cond}
        WHERE c."admission.modality" = '02'""")[0][0]
    out["also_in_sih_by_payer"] = dict(q(con, f"""SELECT c."admission.payer", count(DISTINCT (c._blob_sha256, c._row))
        FROM c JOIN s ON {cond} WHERE c."admission.modality" = '02' GROUP BY 1 ORDER BY 2 DESC"""))
    return out


def joins(period: str, uf: str) -> dict[str, Any]:
    """Rows per key for every member of curation/joins.yml's AIH and APAC keys (OQ-20)."""
    import yaml

    from pegasus_data import query
    from pegasus_data.retrieve import NothingPublished

    spec = yaml.safe_load((ROOT / "src" / "pegasus_data" / "curation" / "joins.yml").read_text(encoding="utf-8"))
    out: dict[str, Any] = {"period": period, "uf": uf, "keys": {}}
    for key in ("AIH", "APAC"):
        members = {}
        for member in spec["keys"][key]["members"]:
            dataset, column = member["dataset"].replace(".", "-"), member["column"]
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    table = query(dataset, period=period, geography=uf, select=[column], present="codes",
                                  allow_partial=True)
            except (NothingPublished, KeyError, ValueError) as exc:
                members[member["dataset"]] = {"declared": member["rows_per_key"], "error": type(exc).__name__}
                continue
            con = duckdb.connect()
            con.register("t", table)
            rows, keys, top, multi = q(con, f"""WITH g AS (SELECT "{column}" k, count(*) c FROM t
                                          WHERE "{column}" IS NOT NULL GROUP BY 1)
                                          SELECT sum(c), count(*), max(c), sum(CASE WHEN c > 1 THEN 1 ELSE 0 END) FROM g""")[0]
            members[member["dataset"]] = {
                "declared": member["rows_per_key"], "rows": rows, "keys": keys,
                "rows_per_key_mean": round(rows / keys, 3) if keys else None, "max": top,
                "keys_with_several_rows": multi,
                "measured": None if not keys else ("one" if multi == 0 else "many"),
            }
            print(f"  {key} {member['dataset']}: {members[member['dataset']]}", flush=True)
        out["keys"][key] = members
    return out


def main() -> int:
    study = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if study == "coverage":
        dataset, period = "CIHA+SIH-RD", sys.argv[2]
        result = coverage(period)
    elif study == "joins":
        dataset, period = f"joins-{sys.argv[3]}", sys.argv[2]
        result = joins(period, sys.argv[3])
    else:
        dataset, period = sys.argv[2].upper(), sys.argv[3]
        dataset_roles(dataset)  # an undeclared dataset fails before anything downloads
        if study == "bits":
            result = bits(dataset, period)
        elif study == "channels":
            result = channels(dataset, period)
        elif study == "flows":
            result = flows(dataset, period)
        else:
            raise SystemExit(f"unknown study {study!r}")
    result["seconds"] = round(time.time() - t0, 1)
    path = OUT / f"{study}_{dataset}_{period}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "by_state"}, ensure_ascii=False, indent=1, default=str))
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
