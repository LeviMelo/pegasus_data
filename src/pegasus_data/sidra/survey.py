"""What SIDRA offers, scored for health inference: the registry read as a survey.

Everything here reads the registry only (no request). A table is scored on four things the registry knows:

- **reach**: the finest level it is published at. ``N6`` is "municipal" in IBGE's metadata but also means a
  *subset* of municipalities (PNS publishes the 27 capitals as N6): the count behind the level, from the
  table's ``/localidades/N6`` (`Registry.load_locality_count`), tells which; a table whose count is unknown is
  reported as such, not assumed to be complete;
- **time**: periods covered and how often;
- **subject**: the topics of `curation/sidra/topics.yml` found in its name, subject, variables and
  classifications (what an epidemiologist would adjust for or stratify by);
- **comparability**: tables with the same normalised title and different periods are one *vintage family*
  (the censuses, the yearly releases of a survey): a series across vintages starts from such a family.

The score orders a reading list; it decides nothing. A table enters PegaSUS by being declared (fields.yml,
series.yml), with its meaning checked.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .client import SidraClient
from .registry import Registry, normalise_text

__all__ = ["rank", "survey", "vintage_families"]


def _topics() -> dict[str, dict[str, Any]]:
    import yaml

    from ..config import curation_root

    return (yaml.safe_load((Path(curation_root()) / "sidra" / "topics.yml").read_text("utf-8")) or {}).get("topics") or {}


def survey(registry: Registry) -> list[dict[str, Any]]:
    """Per research: tables, scanned, reaching N6, reaching N3, curated, and the periods they span."""
    rows = registry.db.execute(
        "SELECT research, COUNT(*) n, SUM(metadata_sha256 IS NOT NULL) scanned, SUM(has_n6) n6, "
        "SUM(levels LIKE '%\"N3\"%') n3, SUM(id IN (SELECT tab FROM compendium)) curated, "
        "MIN(first_period) first, MAX(last_period) last FROM tab GROUP BY research ORDER BY n DESC")
    return [dict(r) for r in rows]


def _n6_known(registry: Registry, table: int, level: str = "N6") -> int | None:
    row = registry.db.execute("SELECT n FROM locality_count WHERE tab = ? AND level = ?", (table, level)).fetchone()
    return None if row is None else int(row[0])


def rank(registry: Registry, *, level: str = "N6", topics: list[str] | None = None, outside_compendium: bool = True,
         limit: int = 40, client: SidraClient | None = None) -> list[dict[str, Any]]:
    """Scanned tables published at ``level``, best first, with the topics that matched.

    With a ``client`` the locality count behind ``level`` is fetched (once, cached) for the best ``3 × limit``
    candidates and the ranking redone, so a table that lists N6 for 27 capitals no longer outranks one that
    covers the country."""
    wanted = _topics()
    if topics:
        wanted = {k: v for k, v in wanted.items() if k in topics}
    patterns = {k: [normalise_text(w) for w in v["words"]] for k, v in wanted.items()}
    weights = {k: float(v.get("weight", 1)) for k, v in wanted.items()}
    query = ("SELECT id, name, research, subject, frequency, first_period, last_period, search, "
             "id IN (SELECT tab FROM compendium) AS curated FROM tab "
             "WHERE metadata_sha256 IS NOT NULL AND levels LIKE ?")
    base = []
    for r in registry.db.execute(query, (f'%"{level}"%',)):
        if outside_compendium and r["curated"]:
            continue
        hit = [k for k, words in patterns.items() if any(w in r["search"] for w in words)]
        if hit:
            span = _years(r["first_period"], r["last_period"])
            base.append((sum(weights[k] for k in hit) + (1.0 if span >= 2 else 0) + (0.5 if r["frequency"] == "anual" else 0), r, hit))
    base.sort(key=lambda x: (-x[0], x[1]["id"]))
    out = []
    for score, r, hit in base[:3 * limit if client else limit]:
        if client is not None and _n6_known(registry, r["id"], level) is None:
            registry.load_locality_count(client, r["id"], level)
        n = _n6_known(registry, r["id"], level)
        adjusted = score + (2.0 if (n or 0) >= 5000 else (0.0 if n is None else -1.0))
        out.append({"table": r["id"], "score": round(adjusted, 1), "research": r["research"], "name": r["name"][:90],
                    "periods": f"{r['first_period']}-{r['last_period']} {r['frequency']}", level: n, "topics": ",".join(hit)})
    out.sort(key=lambda x: (-x["score"], x["table"]))
    return out[:limit]


def _years(first: str | None, last: str | None) -> int:
    a, b = (re.match(r"\d{4}", x or "") for x in (first, last))
    return 0 if not (a and b) else int(b.group()) - int(a.group()) + 1


def vintage_families(registry: Registry, research: str = "Censo Demográfico") -> list[dict[str, Any]]:
    """Tables of one research that ask the same question in different periods: the same classifications (by name)
    and the same variables (by name), with different periods. Each is a candidate series across vintages."""
    families: dict[tuple[str, ...], list[tuple[int, str, str]]] = defaultdict(list)
    for r in registry.db.execute("SELECT id, first_period, last_period FROM tab WHERE research = ? AND metadata_sha256 IS NOT NULL", (research,)).fetchall():
        names = [normalise_text(x[0]) for x in registry.db.execute("SELECT name FROM classification WHERE tab = ?", (r["id"],))]
        variables = [re.sub(r"\s+", " ", normalise_text(x[0])) for x in registry.db.execute("SELECT name FROM variable WHERE tab = ? AND id < 1000000", (r["id"],))]
        families[(*sorted(names), "|", *sorted(variables))].append((r["id"], r["first_period"], r["last_period"]))
    out = []
    for key, tables in families.items():
        if len(tables) > 1 and len({(t[1], t[2]) for t in tables}) > 1:
            out.append({"classifications_and_variables": " / ".join(key)[:110], "tables": json.dumps([t[0] for t in tables]),
                        "periods": ", ".join(sorted({f"{t[1]}-{t[2]}" for t in tables}))})
    return sorted(out, key=lambda f: -len(json.loads(f["tables"])))
