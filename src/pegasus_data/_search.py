"""``search()``: find anything pegasus_data holds or can do, by what it means.

"Which column is about race", "is there rainfall by municipality", "can I link
admissions to deaths" and "which code means Parda" are the same shape of
question, so one call answers all of them. It reads the home's compendium
(`_compendium.current`: the one map, rebuilt when what it describes has changed)
and the shipped label pack's code labels. Every hit carries ``how``: the call
that gets the thing (``query("SIH.RD", select=["RACA_COR"])``,
``load_field("rainfall_monthly")``, ``pegasus-data link sih_deaths_to_sim``).

Diacritics and case are folded on both sides: nobody types *óbito* reliably.
Every word of the query must begin a word of the entry. Ranking is plain and
stated: an exact name first, then every word in the name or title, then in the
prose; shorter entries before longer. Codes rank exact labels before prefix and
substring matches, then shorter labels.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .config import Settings, load_settings
from .textenc import fold, fold_sql

KINDS = ("dataset", "variable", "field", "role", "event", "link", "aggregate", "operation", "sidra", "code")


def search(
    query: str,
    *,
    kind: str | None = None,
    system: str | None = None,
    limit: int = 25,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> list[dict[str, object]]:
    """Datasets, variables, context fields, roles, events, links, aggregates, operations, SIDRA tables and codes whose
    names or meanings mention every word of ``query``.

    Each hit is ``{"system", "kind", "name", "context", "how"}``. ``kind`` narrows to one of :data:`KINDS`;
    ``system`` to one system (``"SIHSUS"``).
    """
    needle = fold(query).strip()
    if not needle:
        raise ValueError("search needs a non-empty query")
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    words = needle.split()
    wanted_system = system.upper() if system else None
    out: list[dict[str, object]] = []

    if kind != "code":
        from ._compendium import current

        resolved = settings or load_settings(root=Path(root) if root else None)
        path = current(settings=resolved)
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            clause = " AND ".join("folded LIKE ?" for _ in words)
            params: list[object] = [f"%{w}%" for w in words]
            if kind:
                clause += " AND kind = ?"
                params.append(kind)
            if wanted_system:
                clause += " AND UPPER(COALESCE(system, '')) = ?"
                params.append(wanted_system)
            hits = []
            for kind_, system_, name, title, prose, how, folded_name, folded in con.execute(
                f"SELECT kind, system, name, title, prose, how, folded_name, folded FROM entries WHERE {clause}",
                params,
            ):
                rank = _rank(words, needle, str(name), folded_name, folded)
                if rank is not None:
                    hits.append((rank, {
                        "system": system_, "kind": kind_, "name": name,
                        "context": str(title or prose or "")[:160], "how": how,
                    }))
        finally:
            con.close()
        hits.sort(key=lambda h: h[0])
        out = [h for _, h in hits][:limit]
    if kind in (None, "code") and len(out) < limit:
        out.extend(_code_hits(needle, wanted_system, limit - len(out)))
    return out


def _begins(word: str, folded: str) -> bool:
    """The word must begin a word: "raca" finds "raça/cor", not "duração"."""
    return re.search(r"(?<![0-9A-Z])" + re.escape(word), folded) is not None


def _rank(words: list[str], needle: str, name: str, folded_name: str, folded: str) -> tuple[int, int] | None:
    if fold(name) == needle:
        return (0, len(name))
    if all(_begins(w, folded_name) for w in words):
        return (1, len(folded_name))
    if all(_begins(w, folded) for w in words):
        return (2, len(folded))
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
        folded = fold_sql("label")
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
            [needle, f"{needle}%", str(pack), r"(^|[^0-9A-Z])" + re.escape(needle), system, system, limit],
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "system": sys_,
            "kind": "code",
            "name": f"{codelist} = {lo}" + (f"..{hi}" if hi and hi != lo else ""),
            "context": label,
            "how": f'load_reference("{codelist}")',
        }
        for sys_, codelist, lo, hi, label, _ in rows
    ]
