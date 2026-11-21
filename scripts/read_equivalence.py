"""Are reads the same before and after a change to the read path?

    python scripts/read_equivalence.py record OUT [case ...]   # run the fixed reads, one JSON per case under OUT
    python scripts/read_equivalence.py compare BEFORE AFTER    # EQUAL / DIFFER per case, with the first differences

Thirty real reads against the data home in use: the lake's years of SIH-RD, SIM-DO, SINASC-DN and SINAN-DENG (they
must be held: ``max_download=0``), small published files of SIH-RD, CNES-ST, SIA-PA, SIH-SP and SINAN-TUBE (fetched
once, then cached), a year-level hybrid, and four refusals. A case records its table as a digest per column (type,
nulls, content) and its report whole. Record on the commit before a change and on the commit after. A first run
downloads, so the download and cache counters differ between a cold and a warm run; ``compare`` ignores them.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import traceback
import warnings
from pathlib import Path

import pyarrow as pa

SIH = ["DIAG_PRINC", "SEXO", "IDADE_anos", "MUNIC_RES"]
SEX = [{"role": "patient.sex", "in": ["3"]}]


def cases() -> dict:
    import pegasus_data
    from pegasus_data.api import load, scan
    from pegasus_data.retrieve import fetch

    q = pegasus_data.query
    lake = {"max_download": 0, "return_report": True}
    return {
        # the lake
        "lake_sih_ac": lambda: q("SIH-RD", period="2023-01", geography="AC", **lake),
        "lake_sih_select": lambda: q("SIH-RD", period="2022", geography="AC", select=[*SIH, "VAL_TOT", "DT_INTER"], **lake),
        "lake_sih_codes": lambda: q("SIH-RD", period="2023-02", geography="RR", present="codes", **lake),
        "lake_sih_rows": lambda: q("SIH-RD", period="2023", geography=["AC", "RR"], rows={"DIAG_PRINC": ["J18", "A90"]},
                                   select=["DIAG_PRINC", "SEXO", "MUNIC_RES"], **lake),
        "lake_sih_prov": lambda: q("SIH-RD", period="2023-03", geography="AC", select=["DIAG_PRINC", "SEXO"],
                                   provenance="all", **lake),
        "lake_sih_dim": lambda: q("SIH-RD", period="2023-01", geography="AC", select=["DIAG_PRINC", "MUNIC_RES"],
                                  dimensions=["DIAG_PRINC.chapter"], **lake),
        "lake_sih_multiyear": lambda: q("SIH-RD", period=("2010", "2012"), geography="AC", select=[*SIH, "RACA_COR"], **lake),
        "lake_sim_rows": lambda: q("SIM-DO", period="2022", rows={"CAUSABAS": ["I21"]},
                                   select=["CAUSABAS", "SEXO", "IDADE_anos", "CODMUNRES", "RACACOR", "DTOBITO"], **lake),
        "lake_sim_cond": lambda: q("SIM-DO", period="2022", condition=[{"role": "deceased.sex", "in": ["2"]}],
                                   rows={"CAUSABAS": ["O"]}, select=["CAUSABAS", "SEXO", "IDADE_anos"], **lake),
        "lake_sinasc_cond": lambda: q("SINASC-DN", period="2022",
                                      condition=[{"role": "birth.weight", "op": "<", "value": 1000}],
                                      select=["PESO", "SEXO", "CODMUNRES", "PARTO"], **lake),
        "lake_deng_rows": lambda: q("SINAN-DENG", period="2021", rows={"ID_MN_RESI": ["1200"]}, **lake),
        "load_sih": lambda: load("SIHSUS", "RD", uf="AC", years=[2023], columns=SIH[:3], report=True),
        "load_sih_full_codes": lambda: load("SIHSUS", "RD", uf="RR", years=[2011], labels=False, report=True),
        "load_sih_audit": lambda: load("SIHSUS", "RD", uf="AC", years=[2024], profile="audit",
                                       columns=["DIAG_PRINC", "MUNIC_RES", "CNES", "PROC_REA"], report=True),
        "load_sih_cond": lambda: load("SIHSUS", "RD", uf="AC", years=[2023], columns=["DIAG_PRINC", "SEXO"],
                                      rows={"DIAG_PRINC": ["O"]}, condition=SEX, report=True),
        "scan_sih": lambda: (scan("SIHSUS", "RD", uf="AC", years=[2023], columns=["DIAG_PRINC", "SEXO"]).to_table(), None),
        # the published files (network on a first run; small files)
        "fetch_sih_ac": lambda: q("SIH-RD", period="2009-03", geography="AC", return_report=True),
        "fetch_sih_select": lambda: q("SIH-RD", period="2009-04", geography="AC", select=SIH, provenance="all",
                                      return_report=True),
        "fetch_sih_rows_cond": lambda: q("SIH-RD", period="2009-05", geography="AC", rows={"DIAG_PRINC": ["J", "O"]},
                                         condition=SEX, select=["DIAG_PRINC", "SEXO"], return_report=True),
        "fetch_cnes_st": lambda: q("CNES-ST", period="2023-01", geography="AC", return_report=True),
        "fetch_sia_pa": lambda: q("SIA-PA", period="2023-01", geography="AC",
                                  select=["PA_PROC_ID", "PA_CIDPRI", "PA_SEXO", "PA_QTDAPR", "PA_CODUNI"],
                                  enrich=["CNPJ"], return_report=True),
        "fetch_sp_through": lambda: q("SIH-SP", period="2023-01", geography="AC",
                                      select=["SP_PROCREA", "SEXO", "IDADE_anos"], return_report=True),
        "fetch_direct": lambda: fetch("SIH-RD", uf="AC", years=2009, months=6, report=True, dictionary=True)[:2],
        "fetch_direct_cols": lambda: fetch("SIH-RD", uf="AC", years=2009, months=7, columns=SIH, provenance=True,
                                           rows={"DIAG_PRINC": ["J"]}, condition=[{"role": "patient.sex", "in": ["1"]}],
                                           report=True),
        "fetch_tube": lambda: q("SINAN-TUBE", period="2010", select=["ID_MN_RESI", "CS_SEXO", "NU_IDADE_N", "FORMA"],
                                rows={"ID_MN_RESI": ["12"]}, return_report=True, max_download=None),
        "hybrid_sih": lambda: q("SIH-RD", period=("2009-12", "2010-01"), geography="AC", select=SIH[:3],
                                return_report=True),
        # refusals stay refusals
        "err_unknown_column": lambda: q("SIH-RD", period="2023-01", geography="AC", select=["NOPE"], max_download=0),
        "err_empty_rows": lambda: q("SIH-RD", period="2023-01", geography="AC", rows={"DIAG_PRINC": []}, max_download=0),
        "err_budget": lambda: q("SIA-PA", period="2023", geography="SP", max_download=0),
        "err_unknown_dataset": lambda: q("SIH-ZZ", period="2023-01"),
    }


def _canon(obj: object, depth: int = 0) -> object:
    if depth > 6:
        return "..."
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _canon(getattr(obj, k), depth + 1) for k in sorted(obj.__dataclass_fields__)}
    if isinstance(obj, dict):
        return {str(k): _canon(v, depth + 1) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple, set, frozenset)):
        items = [_canon(v, depth + 1) for v in obj]
        return sorted(items, key=str) if isinstance(obj, (set, frozenset)) else items
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return repr(obj)[:200]


def _digest(table: pa.Table) -> dict:
    out = {}
    for name in table.column_names:
        if name == "_ingested_at":          # when the file was decoded, not what it holds
            continue
        col = table.column(name)
        h = hashlib.blake2b(digest_size=8)
        if pa.types.is_nested(col.type):
            h.update(repr(col.to_pylist()).encode())
        else:
            for chunk in col.cast(pa.string(), safe=False).chunks:
                for v in chunk.to_pylist():
                    h.update(b"\0" if v is None else v.encode())
                    h.update(b"|")
        out[name] = [str(col.type), col.null_count, h.hexdigest()]
    return out


def record(target: str, names: list[str]) -> None:
    warnings.simplefilter("ignore")
    out = Path(target)
    out.mkdir(parents=True, exist_ok=True)
    known = cases()
    for name in names or list(known):
        t0 = time.time()
        rec: dict = {"case": name}
        try:
            res = known[name]()
            table, report = (res if isinstance(res, tuple) else (res, None))[:2]
            rec.update(rows=table.num_rows, columns=table.column_names, digest=_digest(table),
                       metadata={k.decode(): v.decode()[:2000] for k, v in (table.schema.metadata or {}).items()})
            rec["report"] = _canon(report)
        except Exception as e:  # noqa: BLE001 - a refusal is a result to compare
            rec["error"] = f"{type(e).__name__}: {str(e)[:500]}"
            rec["trace"] = traceback.format_exc()[-1500:]
        rec["seconds"] = round(time.time() - t0, 1)
        (out / f"{name}.json").write_text(json.dumps(rec, indent=1, sort_keys=True, default=str), encoding="utf-8")
        print(name, rec.get("rows"), rec.get("error", "ok")[:150], rec["seconds"], flush=True)


IGNORE = {"seconds", "trace", "bytes_downloaded", "bytes_from_cache", "cache_hits", "network_fetches"}


def _strip(o: object) -> object:
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in o.items() if k not in IGNORE and "second" not in k}
    if isinstance(o, list):
        return [_strip(v) for v in o]
    return o


def _diff(x: object, y: object, path: str = ""):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)):
            if k not in x:
                yield f"{path}/{k}: only after"
            elif k not in y:
                yield f"{path}/{k}: only before"
            else:
                yield from _diff(x[k], y[k], f"{path}/{k}")
    elif isinstance(x, list) and isinstance(y, list) and len(x) == len(y) and x != y:
        for i, (a, b) in enumerate(zip(x, y, strict=True)):
            yield from _diff(a, b, f"{path}[{i}]")
    elif x != y:
        yield f"{path}: {str(x)[:140]} != {str(y)[:140]}"


def compare(before: str, after: str) -> int:
    bad = 0
    for f in sorted(Path(before).glob("*.json")):
        g = Path(after) / f.name
        if not g.exists():
            print("MISSING", f.name)
            bad += 1
            continue
        d = list(_diff(_strip(json.loads(f.read_text(encoding="utf-8"))), _strip(json.loads(g.read_text(encoding="utf-8")))))
        print(("EQUAL  " if not d else "DIFFER ") + f.stem)
        for line in d[:8]:
            print("    ", line)
        bad += bool(d)
    print("differing:", bad)
    return bad


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "record":
        record(sys.argv[2], sys.argv[3:])
    elif len(sys.argv) == 4 and sys.argv[1] == "compare":
        sys.exit(1 if compare(sys.argv[2], sys.argv[3]) else 0)
    else:
        sys.exit(__doc__)
