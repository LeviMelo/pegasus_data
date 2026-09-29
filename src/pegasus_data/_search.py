"""``search()``: find a column, a dataset or a code by what it means.

"Which column is about race" and "which code means Parda" are the same shape
of question, so one call answers both. It reads what every install has: the
catalog's curated variable and dataset documentation (a fresh catalog is the
seed, ADR-0067) and the shipped label pack's 3.65M code labels. It used to need
``docs/dictionary.sqlite``, a 557 MB database that only a maintainer who had run
``pegasus-data dictionary`` possessed, so on a fresh install it raised
``FileNotFoundError`` (live run 2026-09-28).

Diacritics and case are folded on both sides: nobody types *óbito* reliably.
Ranking is plain and stated: an exact name first, then a match in the name,
then a match in the prose; codes rank exact labels before prefix and substring
matches, then shorter labels.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .config import Settings, load_settings

KINDS = ("variable", "dataset", "code")


def _fold(text: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def search(
    query: str,
    *,
    kind: str | None = None,
    system: str | None = None,
    limit: int = 25,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> list[dict[str, object]]:
    """Variables, datasets and codes whose names or meanings mention ``query``.

    Each hit is ``{"system", "kind", "name", "context"}``. ``kind`` narrows to
    ``"variable"``, ``"dataset"`` or ``"code"``; ``system`` to one system
    (``"SIHSUS"``).
    """
    needle = _fold(query).strip()
    if not needle:
        raise ValueError("search needs a non-empty query")
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    resolved = settings or load_settings(root=Path(root) if root else None)
    wanted_system = system.upper() if system else None
    hits: list[tuple[tuple[int, int], dict[str, object]]] = []

    if kind in (None, "variable", "dataset"):
        from .catalog.store import Catalog

        store = Catalog(resolved.catalog_path, read_only=True)
        try:
            if kind in (None, "variable"):
                for r in store.query(
                    "SELECT system, field_name, official_name, translated_name, description "
                    "FROM variable_docs"
                ):
                    if wanted_system and str(r["system"]).upper() != wanted_system:
                        continue
                    names = f"{r['field_name']} {r['official_name'] or ''} {r['translated_name'] or ''}"
                    rank = _rank(needle, str(r["field_name"]), names, str(r["description"] or ""))
                    if rank is not None:
                        hits.append((rank, {
                            "system": r["system"], "kind": "variable", "name": r["field_name"],
                            "context": " — ".join(
                                x for x in (r["official_name"], r["translated_name"]) if x
                            ) or str(r["description"] or "")[:160],
                        }))
            if kind in (None, "dataset"):
                for r in store.query(
                    "SELECT dataset_id, system, series, what_one_row_is, unit_of_analysis, gotchas "
                    "FROM dataset_docs"
                ):
                    if wanted_system and str(r["system"]).upper() != wanted_system:
                        continue
                    prose = " ".join(str(r[c] or "") for c in ("what_one_row_is", "unit_of_analysis", "gotchas"))
                    rank = _rank(needle, str(r["dataset_id"]), str(r["dataset_id"]), prose)
                    if rank is not None:
                        hits.append((rank, {
                            "system": r["system"], "kind": "dataset", "name": r["dataset_id"],
                            "context": str(r["what_one_row_is"] or "")[:160],
                        }))
        finally:
            store.close()

    hits.sort(key=lambda h: h[0])
    out = [h for _, h in hits][:limit]
    if kind in (None, "code") and len(out) < limit:
        out.extend(_code_hits(needle, wanted_system, limit - len(out)))
    return out


def _starts_a_word(needle: str, text: str) -> bool:
    """The match must begin a word: "raca" finds "raça/cor", not "duração"."""
    return re.search(r"(?<![0-9a-z])" + re.escape(needle), _fold(text)) is not None


def _rank(needle: str, exact: str, names: str, prose: str) -> tuple[int, int] | None:
    if _fold(exact) == needle:
        return (0, len(exact))
    if _starts_a_word(needle, names):
        return (1, len(names))
    if _starts_a_word(needle, prose):
        return (2, len(prose))
    return None


def _code_hits(needle: str, system: str | None, limit: int) -> list[dict[str, object]]:
    """Labels in the shipped pack, exact before prefix before substring."""
    from importlib.resources import files

    import duckdb

    from .labelpack import PACK_NAME

    pack = Path(str(files("pegasus_data.resources") / PACK_NAME))
    if not pack.is_file():
        return []
    con = duckdb.connect()
    try:
        folded = "lower(strip_accents(label))"
        rows = con.execute(
            f"""
            SELECT COALESCE(system, '*') AS system, codelist, code_lo, code_hi, label,
                   CASE WHEN {folded} = ? THEN 0 WHEN {folded} LIKE ? THEN 1 ELSE 2 END AS rank
              FROM read_parquet(?)
             WHERE regexp_matches({folded}, ?) AND (? IS NULL OR system = ? OR system IS NULL)
               AND (valid_to IS NULL OR valid_to = '')
             ORDER BY rank, length(label), codelist
             LIMIT ?
            """,
            [needle, f"{needle}%", str(pack), r"(^|[^0-9a-z])" + re.escape(needle), system, system, limit],
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "system": sys_,
            "kind": "code",
            "name": f"{codelist} = {lo}" + (f"..{hi}" if hi and hi != lo else ""),
            "context": label,
        }
        for sys_, codelist, lo, hi, label, _ in rows
    ]
