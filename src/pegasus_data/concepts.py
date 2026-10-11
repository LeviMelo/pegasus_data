"""The concept index: which sources hold a condition's codes, in which role, measured on what they publish.

PegaSUS resolves a study's scope from it (its ARCHITECTURE §4, BACKLOG 4.1). Three tables, each read once and kept in
the data home's ``registries/concepts``:

* :func:`condition_codes` — every record's own condition code where the roles declare one (a column whose role model
  is ``event_type`` on ICD-10: SINAN's ``ID_AGRAVO``), counted in the latest lake year: the sources' own map from
  event type to ICD-10, never a curated one (SINAN-TOXG holds O98.6 and also B58 and P37.1, entered wrongly as Nota
  Técnica 133/2022 says).
* :func:`procedure_compatibility` — SIGTAP's ``rl_procedimento_cid``: the procedures the Tabela Unificada allows
  under each ICD-10 code, with the procedure's name, from the latest monthly export.
* :func:`concept_index` — for ICD-10 codes (any level, prefix-matched): the SINAN datasets holding them with counts, the
  compatible procedures, and the ICD-10 labels that match a term (a label match is the weakest evidence, flagged).

* :func:`dispensed` — the medicines authorised under a code: SIA's APAC AM (the specialised component), each
  authorisation naming its diagnosis (``AP_CIDPRI``) and its medicine (``AP_PRIPAL``, SIGTAP group 06), counted as the
  event type declares (one APAC once); and, for a medicine whose CATMAT code is known, what BNAFAR shows of its
  stock (`sources.bnafar`).
"""

from __future__ import annotations

import functools
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


_SUBSTANCE_KEYS = {"name", "reads", "catmat", "use"}


def treatments(codes: list[str]) -> list[dict[str, Any]]:
    """The declared treatments (`curation/treatments.yml`) of any of ICD-10 ``codes`` (a code holds its subcodes, as
    B58 holds B58.0, and a subcode reaches its category's treatment): each with its conditions, source and substances
    (their names in SNGPC and CATMAT). A treatment is read from the document it cites, never from records."""
    from .config import curation_root
    from .semantics.curation import read_yaml

    asked = [_norm(c) for c in codes]
    out = []
    for key, t in (read_yaml(curation_root() / "treatments.yml").get("treatments") or {}).items():
        if not str(t.get("source") or "").strip() or not t.get("substances") or not t.get("conditions"):
            raise ValueError(f"treatments.yml {key}: a treatment needs its conditions, substances and source")
        for sub in t["substances"]:
            if set(sub) - _SUBSTANCE_KEYS or not sub.get("name") or not ({"reads", "catmat"} & set(sub)):
                raise ValueError(f"treatments.yml {key}: a substance has a name and its CATMAT word or reads, "
                                 f"keys {sorted(_SUBSTANCE_KEYS)}")
            for read in sub.get("reads") or ():
                _check_read(read, f"treatments.yml {key} {sub['name']}")
        conditions = [_norm(c) for c in t["conditions"]]
        if any(a.startswith(c) or c.startswith(a) for a in asked for c in conditions):
            out.append({"treatment": key, "conditions": conditions, "source": " ".join(str(t["source"]).split()),
                        "note": " ".join(str(t.get("note") or "").split()), "substances": list(t["substances"])})
    return out


def _check_read(read: dict[str, Any], where: str) -> None:
    """A substance's read: a declared field, a filter on the columns it is stratified by, and a denominator that is
    ``population`` or another declared field."""
    from .fields import declared_fields

    fields = declared_fields()
    spec = fields.get(read.get("field"))
    if spec is None:
        raise ValueError(f"{where}: reads {read.get('field')!r}, no declared field")
    by = set(spec.get("by") or ())            # its strata as `load_field` returns them
    if not read.get("where") or set(read["where"]) - by:
        raise ValueError(f"{where}: filters {sorted(read.get('where') or {})}, not among {read['field']}'s strata {sorted(by)}")
    if read.get("over") not in (None, "population") and read["over"] not in fields:
        raise ValueError(f"{where}: over {read['over']!r} is neither population nor a declared field")


def condition_codes(root: str | Path | None = None, refresh: bool = False, download: bool = False) -> pa.Table:
    """(dataset, column, year, code, events): for every event type whose records name the condition they are of (a role
    whose model is ``event_type`` on an ICD-10 codelist: SINAN's ``ID_AGRAVO``), that column's codes in the latest year
    the lake holds, with their counts. A dataset with no lake year is listed in the table's metadata ``not_in_lake``;
    with ``download`` its latest published year is read instead (one national file each)."""
    import json

    from ._explore import explore, lake_coverage
    from .semantics.column_roles import roles
    from .semantics.event_types import count_events, event_types, load_event_types

    target = _cache(root) / "condition_codes.parquet"
    if target.is_file() and not refresh:
        return pq.read_table(target)
    rows, missing = [], []
    for name in sorted(load_event_types()):
        try:
            cols = [r["column"] for r in roles(name)
                    if r.get("model") == "event_type" and "ICD10" in (r.get("codelists") or [])]
        except Exception:  # noqa: BLE001 - a dataset without roles names no condition column
            continue
        if not cols:
            continue
        years = sorted(lake_coverage(name, root=root))
        if not years and download:
            years = sorted(int(r["year"]) for r in explore(name, root=root).rows)[-1:]
        if not years:
            missing.append(name)
            continue
        event = event_types(name)[0]["name"]
        for col in cols:
            t = count_events(name, event, period=years[-1], geography="BR", by=[col], root=root,
                             **({} if download else {"max_download": 0}))
            rows += [{"dataset": name, "column": col, "year": years[-1], "code": _norm(r[col]), "events": int(r["events"])}
                     for r in t.to_pylist() if r.get(col)]
    table = pa.Table.from_pylist(rows, schema=pa.schema([("dataset", pa.string()), ("column", pa.string()),
                                                         ("year", pa.int16()), ("code", pa.string()),
                                                         ("events", pa.int64())]))
    table = table.replace_schema_metadata({"not_in_lake": json.dumps(missing)})
    pq.write_table(table, target)
    return table


def _archive(export: Any) -> zipfile.ZipFile:
    from .sources.sigtap import fetch_export

    return zipfile.ZipFile(io.BytesIO(fetch_export(export)))


def procedure_names(root: str | Path | None = None, refresh: bool = False) -> dict[str, str]:
    """SIGTAP procedure code -> name (``tb_procedimento`` of the latest monthly export; cached)."""
    from .sources.sigtap import list_exports, read_table

    cache = _cache(root)
    hits = sorted(cache.glob("procedure_names_*.parquet"))
    if hits and not refresh:
        t = pq.read_table(hits[-1])
        return dict(zip(t.column("procedure").to_pylist(), t.column("name").to_pylist(), strict=True))
    export = list_exports()[-1]
    names = {r["CO_PROCEDIMENTO"]: r["NO_PROCEDIMENTO"] for r in read_table(_archive(export), "tb_procedimento")}
    pq.write_table(pa.table({"procedure": list(names), "name": list(names.values())}),
                   cache / f"procedure_names_{export.competencia}.parquet")
    return names


def procedure_compatibility(root: str | Path | None = None, refresh: bool = False) -> pa.Table:
    """(procedure, procedure_name, cid, competencia): SIGTAP's procedure↔ICD-10 compatibility of the latest monthly
    export (``rl_procedimento_cid``; the export is fetched once, ~5 MB)."""
    from .sources.sigtap import list_exports, read_table

    cache = _cache(root)
    hits = sorted(cache.glob("procedure_cid_*.parquet"))
    if hits and not refresh:
        return pq.read_table(hits[-1])
    export = list_exports()[-1]
    archive = _archive(export)
    names = {r["CO_PROCEDIMENTO"]: r["NO_PROCEDIMENTO"] for r in read_table(archive, "tb_procedimento")}
    rows = [{"procedure": r["CO_PROCEDIMENTO"], "procedure_name": names.get(r["CO_PROCEDIMENTO"]),
             "cid": _norm(r["CO_CID"]), "competencia": export.competencia}
            for r in read_table(archive, "rl_procedimento_cid")]
    if not rows:
        raise LookupError(f"SIGTAP {export.filename}: no rl_procedimento_cid rows")
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, cache / f"procedure_cid_{export.competencia}.parquet")
    return table


def authorisations(year: int, root: str | Path | None = None, refresh: bool = False, download: bool = False,
                   dataset: str = "SIASUS-AM") -> pa.Table:
    """(cid, procedure, apacs, year): the APAC medicine authorisations of one year, nationally, by their diagnosis
    (``AP_CIDPRI``) and medicine procedure (``AP_PRIPAL``), each APAC once (the event type's rule: the row of its first
    month; continuation rows are not new authorisations). Read from the lake; with ``download`` the year's files are
    fetched (a national AM year is 1.4-1.9 GiB of DBC) and kept there."""
    from .semantics.event_types import count_events, event_types

    target = _cache(root) / f"authorisations_{dataset}_{year}.parquet"
    if target.is_file() and not refresh:
        return pq.read_table(target)
    event = event_types(dataset)[0]["name"]
    t = count_events(dataset, event, period=(f"{year}-01", f"{year}-12"), geography="BR",
                     by=["AP_CIDPRI", "AP_PRIPAL"], root=root, **({"max_download": None} if download else {"max_download": 0}))
    rows = [{"cid": _norm(r["AP_CIDPRI"] or ""), "procedure": str(r["AP_PRIPAL"] or ""), "apacs": int(r["events"]), "year": year}
            for r in t.to_pylist()]
    table = pa.Table.from_pylist(rows, schema=pa.schema([("cid", pa.string()), ("procedure", pa.string()),
                                                         ("apacs", pa.int64()), ("year", pa.int16())]))
    pq.write_table(table, target)
    return table


def dispensed(codes: list[str], years: list[int] | None = None, root: str | Path | None = None,
              download: bool = False, dataset: str = "SIASUS-AM") -> dict[str, Any]:
    """The medicines authorised under ICD-10 ``codes`` (any level) in SIA's APAC AM: per SIGTAP medicine procedure
    (group 06), its name and the APACs naming a held code as their principal diagnosis, with the codes they name.

    ``years`` default to the latest year the lake holds (``download``: the latest complete published year). The
    count is APACs begun in those years, not patients, doses or the stock delivered; only the specialised component
    is in AM (what the basic component dispenses is BNAFAR's, `sources.bnafar`). Returns ``{"years", "medicines":
    [{"procedure", "name", "apacs", "by_cid": {cid: apacs}}], "apacs", "scanned": {"apacs", "cids"}}``, medicines by
    descending APACs. No medicine is a measured absence, not a gap: ``scanned`` is what was searched (the year's
    APACs and diagnoses), so ``medicines == []`` with ``scanned.apacs > 0`` says the source holds no APAC under the
    codes."""
    from ._explore import explore, lake_coverage

    prefixes = [_norm(c) for c in codes]
    if not years:
        held = sorted(lake_coverage(dataset, root=root))
        if not held and download:
            held = sorted(int(r["year"]) for r in explore(dataset, root=root).rows if int(r["months"]) == 12)
        if not held:
            raise LookupError(f"{dataset}: no year in the lake; pass years= with download=True")
        years = held[-1:]
    names = procedure_names(root)
    meds: dict[str, dict] = {}
    scanned = {"apacs": 0, "cids": set()}
    for y in years:
        for r in authorisations(y, root, download=download, dataset=dataset).to_pylist():
            scanned["apacs"] += r["apacs"]
            scanned["cids"].add(r["cid"])
            if not (r["procedure"].startswith("06") and any(r["cid"].startswith(p) for p in prefixes)):
                continue
            m = meds.setdefault(r["procedure"], {"procedure": r["procedure"], "name": names.get(r["procedure"]),
                                                 "apacs": 0, "by_cid": {}})
            m["apacs"] += r["apacs"]
            m["by_cid"][r["cid"]] = m["by_cid"].get(r["cid"], 0) + r["apacs"]
    medicines = sorted(meds.values(), key=lambda m: -m["apacs"])
    return {"years": list(years), "medicines": medicines, "apacs": sum(m["apacs"] for m in medicines),
            "scanned": {"apacs": scanned["apacs"], "cids": len(scanned["cids"])}}


def stock_by_state(substances: list[str], year: int, root: str | Path | None = None, keep: Any = None) -> dict[str, Any]:
    """What BNAFAR (the Hórus stock reports) shows of the drugs whose CATMAT name holds each of ``substances``, by
    state and month of ``year``: ``{"products": [...], "monthly": [(catmat, description, anomes, uf, rows,
    establishments, lots, quantity)]}``. ``keep(product) -> bool`` drops products that are not the medicine meant (a
    drug name also names its topical or veterinary item). Read by filter (one CATMAT code and month per request), so a
    first call is minutes; see `sources.bnafar` for the stock rule and the code form."""
    from .sources import bnafar

    found = [p for s in substances for p in bnafar.products(s, root)]
    if keep:
        found = [p for p in found if keep(p)]
    table = bnafar.monthly(sorted({p["code"] for p in found}), year, root=root)
    return {"products": found, "monthly": table.to_pylist()}


def _fold(text: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c)).lower()


def label_matches(terms: list[str] | tuple[str, ...], structure: str = "ICD10") -> list[dict]:
    """The codes of ``structure`` whose label holds one of ``terms``, accents and case ignored ("toxoplasm" finds
    "Toxoplasmose"): (code, label, level, term)."""
    import pyarrow.compute as pc

    table, folded_labels = _folded_labels(structure)
    hit = pa.nulls(table.num_rows, pa.string())
    for term in reversed(list(terms)):          # the first term matching a label names it, as before
        f = _fold(term)
        if f:
            hit = pc.if_else(pc.match_substring(folded_labels, f), pa.scalar(term), hit)
    keep = pc.is_valid(hit)
    rows = table.filter(keep).to_pylist()
    return [{"code": r["code"], "label": r["label"], "level": r["level"], "term": h}
            for r, h in zip(rows, hit.filter(keep).to_pylist(), strict=True)]


@functools.cache
def _folded_labels(structure: str) -> tuple[pa.Table, pa.Array]:
    """A code structure and its labels folded (accents and case), once per process: every `label_matches` folded
    every label again (ICD-10 and SIGTAP, a quarter of a `concept_index`, 2026-10-11)."""
    from .semantics.code_structures import code_structure

    table = code_structure(structure)
    return table, pa.array([_fold(x or "") for x in table.column("label").to_pylist()], pa.string())


def concept_index(codes: list[str], terms: list[str] | tuple[str, ...] = (), root: str | Path | None = None,
                  substances: list[str] | None = None, stock_year: int | None = None, keep: Any = None,
                  years: list[int] | None = None, download: bool = False) -> dict[str, Any]:
    """Where ICD-10 ``codes`` (any level: B58 holds B58.0-B58.9) are held:

    * ``conditions``: the event types whose records name them as their condition (`condition_codes`), with the
      column and its counts in the lake year read;
    * ``procedures``: the SIGTAP procedures compatible with them;
    * ``labels``: ICD-10 codes and SIGTAP procedures whose label matches a term (the weakest evidence: a name, not a
      declaration; it finds what no compatibility table ties to a code: toxoplasma serology);
    * ``treatments``: the medicines an official document gives for the codes (`treatments`);
    * ``dispensed``: ``{"apac": dispensed(...)}``, the specialised-component medicines authorised under the codes, or
      ``{"apac": None, "reason": ...}`` when no SIA AM year is in the lake (``download`` fetches one); and, when
      ``stock_year`` is given, ``"stock"``: BNAFAR's stock of ``substances`` (names a CATMAT PDM holds; by default
      the declared treatments' CATMAT names) by state and month (`stock_by_state`; ``keep`` filters its products).
    """
    import pyarrow.compute as pc

    prefixes = [_norm(c) for c in codes]

    def held(table: pa.Table, column: str) -> list[dict]:
        """The rows whose ``column`` starts with a prefix, filtered in Arrow (a Python pass over SIGTAP's 82,000
        compatibility pairs at each call)."""
        if not prefixes or table.num_rows == 0:
            return []
        col = pc.cast(table.column(column), pa.string())
        mask = pc.starts_with(col, prefixes[0])
        for pfx in prefixes[1:]:
            mask = pc.or_(mask, pc.starts_with(col, pfx))
        return table.filter(pc.fill_null(mask, False)).to_pylist()

    found = held(condition_codes(root), "code")
    by_ds: dict[tuple, dict] = {}
    for r in found:
        d = by_ds.setdefault((r["dataset"], r["column"]), {"dataset": r["dataset"], "column": r["column"],
                                                          "year": r["year"], "codes": {}, "events": 0})
        d["codes"][r["code"]] = r["events"]
        d["events"] += r["events"]
    procedures = held(procedure_compatibility(root), "cid")
    labels = [{**r, "structure": st} for st in ("ICD10", "SIGTAP") for r in label_matches(terms, st)] if terms else []
    try:
        disp: dict[str, Any] = {"apac": dispensed(codes, years, root, download)}
    except LookupError as exc:
        disp = {"apac": None, "reason": str(exc)}
    treated = treatments(codes)
    if substances is None:
        substances = [s["catmat"] for t in treated for s in t["substances"] if s.get("catmat")]
    if substances and stock_year:
        disp["stock"] = stock_by_state(substances, stock_year, root, keep)
    return {"codes": prefixes, "conditions": sorted(by_ds.values(), key=lambda d: -d["events"]),
            "procedures": procedures, "labels": labels, "treatments": treated, "dispensed": disp}
