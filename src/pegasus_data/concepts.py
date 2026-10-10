"""The concept index: which sources hold a condition's codes, in which role, measured on what they publish.

PegaSUS resolves a study's scope from it (its ARCHITECTURE §4, BACKLOG 4.1). Three tables, each read once and kept in
the data home's ``registries/concepts``:

* :func:`sinan_codes` — every SINAN dataset's ``ID_AGRAVO`` codes (ICD-10, the agravo the notification is of) in its
  latest lake year, with their counts: the sources' own SINAN↔ICD map, never a curated one (SINAN-TOXG holds O98.6
  and also B58 and P37.1, entered wrongly as Nota Técnica 133/2022 says).
* :func:`procedure_compatibility` — SIGTAP's ``rl_procedimento_cid``: the procedures the Tabela Unificada allows
  under each ICD-10 code, with the procedure's name, from the latest monthly export.
* :func:`concept_index` — for ICD-10 codes (any level, prefix-matched): the SINAN datasets holding them with counts, the
  compatible procedures, and the ICD-10 labels that match a term (a label match is the weakest evidence, flagged).

Medicines dispensed under a code (SIA's APAC AM by ``AP_CIDPRI``) are counted from the lake where it holds them.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


def _cache(root: str | Path | None) -> Path:
    from .config import load_settings

    path = Path(root or load_settings().root) / "registries" / "concepts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _norm(code: str) -> str:
    return str(code).replace(".", "").strip().upper()


def sinan_codes(root: str | Path | None = None, refresh: bool = False, download: bool = False) -> pa.Table:
    """(dataset, year, code, events): each SINAN dataset's ``ID_AGRAVO`` codes in the latest year its lake holds. A
    dataset with no lake year is left out and listed in the table's metadata ``not_in_lake``; with ``download`` its
    latest published year is read instead (one national file per agravo)."""
    import json

    from ._explore import lake_coverage
    from .semantics.event_types import count_events, event_types, load_event_types

    target = _cache(root) / "sinan_codes.parquet"
    if target.is_file() and not refresh:
        return pq.read_table(target)
    rows, missing = [], []
    for ds in sorted(k for k in load_event_types() if k.upper().startswith("SINAN")):
        name = ds
        years = sorted(lake_coverage(name, root=root))
        if not years and download:
            from ._explore import explore

            years = sorted(int(r["year"]) for r in explore(name, root=root).rows)[-1:]
        if not years:
            missing.append(name)
            continue
        event = event_types(name)[0]["name"]
        t = count_events(name, event, period=years[-1], geography="BR", by=["ID_AGRAVO"], root=root,
                         **({} if download else {"max_download": 0}))
        for r in t.to_pylist():
            if r.get("ID_AGRAVO"):
                rows.append({"dataset": name, "year": years[-1], "code": _norm(r["ID_AGRAVO"]), "events": int(r["events"])})
    table = pa.Table.from_pylist(rows, schema=pa.schema([("dataset", pa.string()), ("year", pa.int16()),
                                                         ("code", pa.string()), ("events", pa.int64())]))
    table = table.replace_schema_metadata({"not_in_lake": json.dumps(missing)})
    pq.write_table(table, target)
    return table


def procedure_compatibility(root: str | Path | None = None, refresh: bool = False) -> pa.Table:
    """(procedure, procedure_name, cid, competencia): SIGTAP's procedure↔ICD-10 compatibility of the latest monthly
    export (``rl_procedimento_cid``; the export is fetched once, ~5 MB)."""
    from .sources.sigtap import fetch_export, list_exports, read_table

    cache = _cache(root)
    hits = sorted(cache.glob("procedure_cid_*.parquet"))
    if hits and not refresh:
        return pq.read_table(hits[-1])
    export = list_exports()[-1]
    archive = zipfile.ZipFile(io.BytesIO(fetch_export(export)))
    names = {r["CO_PROCEDIMENTO"]: r["NO_PROCEDIMENTO"] for r in read_table(archive, "tb_procedimento")}
    rows = [{"procedure": r["CO_PROCEDIMENTO"], "procedure_name": names.get(r["CO_PROCEDIMENTO"]),
             "cid": _norm(r["CO_CID"]), "competencia": export.competencia}
            for r in read_table(archive, "rl_procedimento_cid")]
    if not rows:
        raise LookupError(f"SIGTAP {export.filename}: no rl_procedimento_cid rows")
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, cache / f"procedure_cid_{export.competencia}.parquet")
    return table


def _fold(text: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c)).lower()


def label_matches(terms: list[str] | tuple[str, ...], structure: str = "ICD10") -> list[dict]:
    """The codes of ``structure`` whose label holds one of ``terms``, accents and case ignored ("toxoplasm" finds
    "Toxoplasmose"): (code, label, level, term)."""
    from .semantics.code_structures import code_structure

    folded = [(t, _fold(t)) for t in terms]
    out = []
    for r in code_structure(structure).to_pylist():
        label = _fold(r.get("label") or "")
        hit = next((t for t, f in folded if f and f in label), None)
        if hit:
            out.append({"code": r["code"], "label": r["label"], "level": r["level"], "term": hit})
    return out


def concept_index(codes: list[str], terms: list[str] | tuple[str, ...] = (), root: str | Path | None = None) -> dict[str, Any]:
    """Where ICD-10 ``codes`` (any level: B58 holds B58.0-B58.9) are held:

    * ``sinan``: the SINAN datasets whose notifications carry them, with their counts in the lake year read;
    * ``procedures``: the SIGTAP procedures compatible with them;
    * ``labels``: ICD-10 codes and SIGTAP procedures whose label matches a term (the weakest evidence: a name, not a
      declaration; it finds what no compatibility table ties to a code: toxoplasma serology).
    """
    prefixes = [_norm(c) for c in codes]

    def held(code: str) -> bool:
        return any(code.startswith(p) for p in prefixes)

    sinan = [r for r in sinan_codes(root).to_pylist() if held(r["code"])]
    by_ds: dict[str, dict] = {}
    for r in sinan:
        d = by_ds.setdefault(r["dataset"], {"dataset": r["dataset"], "year": r["year"], "codes": {}, "events": 0})
        d["codes"][r["code"]] = r["events"]
        d["events"] += r["events"]
    procedures = [r for r in procedure_compatibility(root).to_pylist() if held(r["cid"])]
    labels = [{**r, "structure": st} for st in ("ICD10", "SIGTAP") for r in label_matches(terms, st)] if terms else []
    return {"codes": prefixes, "sinan": sorted(by_ds.values(), key=lambda d: -d["events"]),
            "procedures": procedures, "labels": labels}
