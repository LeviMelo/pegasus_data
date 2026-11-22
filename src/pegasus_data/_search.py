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
prose; shorter entries before longer. Codes take up to a quarter of the list
(all of it with ``kind="code"``), exact labels before prefix and substring
matches, then shorter labels.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import cast

from .config import Settings, load_settings
from .textenc import fold, fold_sql

KINDS = ("dataset", "variable", "field", "product", "role", "event", "link", "aggregate", "operation", "sidra", "code")


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
    if kind == "code":
        return [{k: v for k, v in c.items() if k != "_rank"} for c in _code_hits(needle, wanted_system, limit)]
    if kind is None:
        # Codes share the list: label matches that are exact or begin the label, at least a quarter of it and every
        # slot the other kinds leave empty ("neurocirurgia" found six codes and hid the HABILITA accreditations
        # 1606-1618 behind an empty list, 2026-11-21).
        # A word inside a label ("NEUROCIRURGIA ENDOVASCULAR/TROMBECTOMIA MECANICA" for "trombectomia") fills only
        # what the labels that begin with the words leave.
        room = max(3, limit // 4, limit - len(out))
        found = _code_hits(needle, wanted_system, limit)
        ranked = [c for c in found if cast(int, c["_rank"]) < 2] + (
            [c for c in found if cast(int, c["_rank"]) >= 2] if room > limit // 4 else [])
        codes = [{k: v for k, v in c.items() if k != "_rank"} for c in ranked][:room]
        out = out[: max(0, limit - len(codes))] + codes
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
    """Codes whose label or whose code matches, exact before prefix before substring: the shipped pack's labels, every
    window of them (a code that ended is still a code of its years, with its window said), and the classifications
    whose codes carry their own validity windows (``codelists.yml`` ``code_windows``: SIGTAP's 5,785 procedures from its
    monthly exports, the source of the manual's ``codes/SIGTAP.md``). The pack's labels were matched by their text only
    and only while current: a SIGTAP code ended in 2019 or created since the pack's kits was not found (reported by the
    ABNc study, 2026-11-22)."""
    from importlib.resources import files

    import duckdb

    from .labelpack import PACK_NAME

    hits: list[dict[str, object]] = []
    con = duckdb.connect()
    try:
        folded = fold_sql("label")
        pattern = r"(^|[^0-9A-Z])" + re.escape(needle)
        pack = Path(str(files("pegasus_data.resources") / PACK_NAME))
        if pack.is_file():
            rows = con.execute(
                f"""
                SELECT COALESCE(system, '*'), codelist, code_lo, code_hi, label, valid_from, valid_to,
                       CASE WHEN upper(code_lo) = ? OR {folded} = ? THEN 0
                            WHEN upper(code_lo) LIKE ? OR {folded} LIKE ? THEN 1 ELSE 2 END AS rank
                  FROM read_parquet(?)
                 WHERE (regexp_matches({folded}, ?) OR upper(code_lo) LIKE ?)
                   AND (? IS NULL OR system = ? OR system IS NULL)
                 ORDER BY rank, (valid_to IS NOT NULL AND valid_to <> ''), length(label), codelist
                 LIMIT ?
                """,
                [needle, needle, f"{needle}%", f"{needle}%", str(pack), pattern, f"{needle}%", system, system, limit],
            ).fetchall()
            for sys_, codelist, lo, hi, label, vfrom, vto, rank in rows:
                window = "" if not (vfrom or vto) else f" [{vfrom or '…'}-{vto or 'current'}]"
                hits.append({"system": sys_, "kind": "code",
                             "name": f"{codelist} = {lo}" + (f"..{hi}" if hi and hi != lo else ""),
                             "context": f"{label}{window}", "how": f'load_reference("{codelist}")', "_rank": rank})
        hits += _windowed_code_hits(con, needle, limit)
    finally:
        con.close()
    hits.sort(key=lambda h: (h["_rank"], len(str(h["context"]))))
    seen: set[tuple[object, object]] = set()
    out = []
    for h in hits:
        key = (h["name"], h["context"])
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out[:limit]


def _windowed_code_hits(con: object, needle: str, limit: int) -> list[dict[str, object]]:
    """Codes of the classifications that date their codes (``code_windows``), each with its latest name and its window."""
    import pyarrow.parquet as pq

    from .config import load_settings
    from .view import _declared_code_windows

    settings = load_settings()
    out: list[dict[str, object]] = []
    for classification, decl in _declared_code_windows().items():
        windows = Path(settings.registry_dir(decl["registry"], decl["file"]))
        names_file = windows.with_name(decl["names"]) if decl.get("names") else None
        if not windows.is_file():
            continue
        code = decl["code"]
        name_sql = (f"(SELECT {decl['name']} FROM read_parquet('{names_file.as_posix()}') h WHERE h.{code} = w.{code} "
                    f"ORDER BY valid_from DESC LIMIT 1)") if names_file and names_file.is_file() else "NULL"
        rows = con.execute(  # type: ignore[attr-defined]
            f"""SELECT w.{code}, {name_sql} AS label, w.first, w.last,
                       CASE WHEN w.{code} = ? THEN 0 WHEN w.{code} LIKE ? THEN 1 ELSE 2 END AS rank
                  FROM read_parquet('{windows.as_posix()}') w
                 WHERE w.{code} LIKE ? OR upper(coalesce({name_sql}, '')) LIKE ?
                 ORDER BY rank LIMIT ?""",
            [needle, f"{needle}%", f"{needle}%", f"%{needle}%", limit]).fetchall()
        newest = pq.read_metadata(windows).num_rows and con.execute(  # type: ignore[attr-defined]
            f"SELECT max(last) FROM read_parquet('{windows.as_posix()}')").fetchone()[0]
        for value, label, first, last, rank in rows:
            window = f"{first}-{'current' if last == newest else last}"
            out.append({"system": classification, "kind": "code", "name": f"{classification} = {value}",
                        "context": f"{label or '(no name recorded)'} [{window}]",
                        "how": f"manual codes/{classification}.md; sources.sigtap.procedure_window('{value}')"
                               if classification == "SIGTAP" else f"manual codes/{classification}.md", "_rank": rank})
    return out
