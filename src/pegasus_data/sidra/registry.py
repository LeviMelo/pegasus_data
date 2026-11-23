"""The SIDRA metadata registry: every aggregate IBGE publishes, searchable offline.

Built from IBGE's own metadata, never from a hand-kept list: ``/agregados`` names the tables, and
``/agregados/<t>/metadados`` gives each one's variables, units, classifications, categories,
periodicity and territorial levels. The registry is a SQLite file under
``<root>/registries/sidra/registry.sqlite``, derived and rebuildable from the HTTP cache beside it.

The author's curated compendium (``curation/sidra/compendium.yml``) is an overlay: which tables
matter to PegaSUS, at which tier, with which variables kept by default. The overlay never replaces
what IBGE says; ``check_compendium`` reports where the two disagree.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..textenc import fold
from .client import SidraClient, SidraError

__all__ = ["Registry", "open_registry"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS research (id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tab (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, research_id TEXT, research TEXT, subject TEXT, url TEXT,
    frequency TEXT, first_period TEXT, last_period TEXT, levels TEXT,           -- levels: JSON list ["N1","N3","N6",…]
    has_n6 INTEGER, n_variables INTEGER, n_classifications INTEGER,
    cells_per_locality_period INTEGER,                                          -- product of category counts (totals included)
    metadata_sha256 TEXT, metadata_fetched_at TEXT, search TEXT);
CREATE TABLE IF NOT EXISTS variable (
    tab INTEGER, id INTEGER, name TEXT, unit TEXT, summarisation TEXT, keep INTEGER DEFAULT 0, kind TEXT,
    PRIMARY KEY (tab, id));
CREATE TABLE IF NOT EXISTS classification (
    tab INTEGER, id INTEGER, name TEXT, summarises INTEGER, n_categories INTEGER, PRIMARY KEY (tab, id));
CREATE TABLE IF NOT EXISTS category (
    tab INTEGER, class_id INTEGER, id INTEGER, name TEXT, level INTEGER, unit TEXT, is_total INTEGER,
    synthetic INTEGER DEFAULT 0, PRIMARY KEY (tab, class_id, id));
CREATE TABLE IF NOT EXISTS period (
    tab INTEGER, id TEXT, literal TEXT, modified TEXT, PRIMARY KEY (tab, id));
CREATE TABLE IF NOT EXISTS locality_count (
    tab INTEGER, level TEXT, n INTEGER, sha256 TEXT, n_capitals INTEGER, PRIMARY KEY (tab, level));
CREATE TABLE IF NOT EXISTS compendium_variable (tab INTEGER, id INTEGER, kind TEXT, keep INTEGER, PRIMARY KEY (tab, id));
CREATE TABLE IF NOT EXISTS compendium_policy (tab INTEGER, class_id INTEGER, policy TEXT, PRIMARY KEY (tab, class_id));
CREATE TABLE IF NOT EXISTS compendium (
    tab INTEGER PRIMARY KEY, tier TEXT, grp TEXT, role TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS tab_research ON tab(research_id);
CREATE INDEX IF NOT EXISTS category_name ON category(tab, class_id);
"""


@lru_cache(maxsize=1)
def _capital_codes() -> frozenset[str]:
    from ..geography import members

    return frozenset(members("capital"))


def health_researches() -> tuple[str, ...]:
    """The researches whose metadata is read first, in order (``curation/sidra/topics.yml`` ``researches``)."""
    from ..config import curation_root
    from ..semantics.curation import read_yaml

    return tuple(str(r) for r in read_yaml(Path(curation_root()) / "sidra" / "topics.yml").get("researches") or ())


#: The `search` column holds `textenc.fold` text (upper case, no accents, hyphens and runs of spaces as one space), the
#: project's one name folding. A registry written before that (lower-case, accents only) is re-folded on open; the
#: marker is SQLite's `user_version`.
SEARCH_FOLDED = 1

#: Vocabularies compared with folded text are written folded.
_COUNT_UNITS = ("PESSOAS", "UNIDADES", "DOMICILIOS", "FAMILIAS", "ESTABELECIMENTOS", "EMPRESAS", "HABITANTES",
                "CRIANCAS", "NASCIDOS", "OBITOS", "CASOS", "VEICULOS", "CABECAS", "MUNICIPIOS")


def infer_kind(unit: str | None, name: str) -> str:
    """c count · m monetary · p percent/share · md mean or median · r rate or index · o other.

    The compendium's own kinds override this for the tables it covers; this is the fallback and is
    only as good as a unit and a name can say, which is why `kind` is used to refuse summing, never to sum."""
    u, n = fold(unit or ""), fold(name)
    if "%" in u or "PERCENTUAL" in u or "PERCENTUAL" in n or "DISTRIBUICAO PERCENTUAL" in n:
        return "p"
    if any(w in n for w in ("MEDIA", "MEDIANA", "MEDIO", "MEDIANO")):
        return "md"
    if any(w in n for w in ("TAXA", "INDICE", "RAZAO", "PROPORCAO", "COEFICIENTE")):
        return "r"
    if "REAIS" in u or u == "REAL" or "R$" in u or "DOLAR" in u:
        return "m"
    if any(w in u for w in _COUNT_UNITS):
        return "c"
    return "o"


class Registry:
    """The registry file and the questions asked of it."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        if "n_capitals" not in {r[1] for r in self.db.execute("PRAGMA table_info(locality_count)")}:
            self.db.execute("ALTER TABLE locality_count ADD COLUMN n_capitals INTEGER")   # counts read before it are refetched (cached)
        self._fold_search()

    def _fold_search(self) -> None:
        """Re-fold a `search` column written by the older lower-case folding (idempotent: ``fold(old(x)) == fold(x)``)."""
        if self.db.execute("PRAGMA user_version").fetchone()[0] >= SEARCH_FOLDED:
            return
        with self.db:
            rows = self.db.execute("SELECT id, search FROM tab WHERE search IS NOT NULL").fetchall()
            self.db.executemany("UPDATE tab SET search = ? WHERE id = ?", [(fold(s), i) for i, s in rows])
            self.db.execute(f"PRAGMA user_version = {SEARCH_FOLDED}")

    def close(self) -> None:
        self.db.close()

    # -- building --------------------------------------------------------------------------------

    def scan_catalog(self, client: SidraClient) -> int:
        """Record every table ``/agregados`` lists with its research. Returns the number of tables."""
        groups = client.catalog().payload
        n = 0
        with self.db:
            for group in groups:
                self.db.execute("INSERT OR REPLACE INTO research VALUES (?,?)", (group["id"], group["nome"].strip()))
                for item in group["agregados"]:
                    self.db.execute(
                        "INSERT INTO tab (id, name, research_id, research) VALUES (?,?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, research_id=excluded.research_id, "
                        "research=excluded.research", (int(item["id"]), item["nome"].strip(), group["id"], group["nome"].strip()))
                    n += 1
        return n

    def n6_table_ids(self, client: SidraClient) -> list[int]:
        """The tables IBGE itself lists at municipality level (``?nivel=N6``)."""
        return [int(a["id"]) for g in client.catalog(nivel="N6").payload for a in g["agregados"]]

    def scan_order(self, client: SidraClient, *, everything: bool = False) -> list[int]:
        """The order to read metadata in: the curated compendium first, then the researches that bear on health
        (`health_researches`, municipal tables before the rest of each), then the other municipal tables, and,
        with ``everything``, all the remaining tables. A scan that is stopped has read what matters most."""
        n6 = set(self.n6_table_ids(client))
        by_research: dict[str, list[int]] = {}
        for tid, rid in self.db.execute("SELECT id, research_id FROM tab ORDER BY id"):
            by_research.setdefault(rid, []).append(tid)
        order: list[int] = [r[0] for r in self.db.execute("SELECT tab FROM compendium ORDER BY tab")]
        for rid in health_researches():
            ids = by_research.get(rid, [])
            order += [t for t in ids if t in n6] + ([t for t in ids if t not in n6] if everything else [])
        order += sorted(n6)
        if everything:
            order += [t for ids in by_research.values() for t in ids]
        return list(dict.fromkeys(order))

    def scanned(self) -> set[int]:
        return {r[0] for r in self.db.execute("SELECT id FROM tab WHERE metadata_sha256 IS NOT NULL")}

    def load_metadata(self, table: int, meta: dict[str, Any], sha: str, fetched_at: str) -> None:
        """Replace one table's registry rows with what its metadata says (derived state is replaced)."""
        levels = sorted({lv for key in ("Administrativo", "Especial", "IBGE") for lv in (meta["nivelTerritorial"].get(key) or [])})
        classes = meta.get("classificacoes") or []
        cells = 1
        for c in classes:
            cells *= max(1, len(c.get("categorias") or []))
        per = meta.get("periodicidade") or {}
        with self.db:
            for t in ("variable", "classification", "category"):
                self.db.execute(f"DELETE FROM {t} WHERE tab = ?", (table,))
            self.db.execute(
                "UPDATE tab SET name=?, research=COALESCE(?, research), subject=?, url=?, frequency=?, first_period=?, "
                "last_period=?, levels=?, has_n6=?, n_variables=?, n_classifications=?, cells_per_locality_period=?, "
                "metadata_sha256=?, metadata_fetched_at=?, search=? WHERE id=?",
                (meta["nome"].strip(), meta.get("pesquisa"), meta.get("assunto"), meta.get("URL"), per.get("frequencia"),
                 str(per.get("inicio")) if per.get("inicio") is not None else None,
                 str(per.get("fim")) if per.get("fim") is not None else None, json.dumps(levels), int("N6" in levels),
                 len(meta.get("variaveis") or []), len(classes), cells, sha, fetched_at,
                 fold(" ".join([meta["nome"], meta.get("pesquisa") or "", meta.get("assunto") or ""]
                                         + [v["nome"] for v in meta.get("variaveis") or []]
                                         + [c["nome"] for c in classes])), table))
            self.db.executemany("INSERT INTO variable (tab, id, name, unit, summarisation, kind) VALUES (?,?,?,?,?,?)", [
                (table, v["id"], v["nome"].strip(), v.get("unidade"), json.dumps(v.get("sumarizacao") or []), infer_kind(v.get("unidade"), v["nome"]))
                for v in meta.get("variaveis") or []])
            for c in classes:
                cats = c.get("categorias") or []
                summ = c.get("sumarizacao") or {}
                self.db.execute("INSERT INTO classification VALUES (?,?,?,?,?)",
                                (table, c["id"], c["nome"].strip(), int(bool(summ.get("status"))), len(cats)))
                rows = [(table, c["id"], k["id"], k["nome"].strip(), k.get("nivel"), k.get("unidade"),
                         int(k.get("nivel") == 0 and _is_total_name(k["nome"])), 0) for k in cats]
                if not any(r[6] for r in rows):
                    # a Total that IBGE does not place at level 0 (it sits inside a hierarchy) is still the Total
                    rows = [(*r[:6], int(r[3].strip().lower() == "total"), 0) for r in rows]
                if not any(r[6] for r in rows) and all(r[2] != 0 for r in rows):
                    # 68 of 3,105 classifications list no Total, yet a request that leaves them out is answered
                    # with category 0 and an empty name (table 307, measured 2026-10-05): IBGE's implicit total
                    rows.append((table, c["id"], 0, "(implicit total)", 0, None, 1, 1))
                self.db.executemany("INSERT INTO category VALUES (?,?,?,?,?,?,?,?)", rows)

    def scan_metadata(self, client: SidraClient, tables: Iterable[int], *, log: Callable[[str], None] = print,
                      every: int = 100) -> dict[str, int]:
        """Fetch and load the metadata of ``tables`` (resumable: tables already loaded are skipped)."""
        done = self.scanned()
        todo = [t for t in tables if t not in done]
        failed: list[tuple[int, str]] = []
        for i, table in enumerate(todo, 1):
            try:
                response = client.metadata(table)
                self.load_metadata(table, response.payload, response.sha256, response.fetched_at)
            except (SidraError, sqlite3.Error, KeyError, ValueError, TypeError) as exc:    # one odd table must not stop a scan
                failed.append((table, f"{type(exc).__name__}: {str(exc)[:200]}"))
            if i % every == 0:
                log(f"metadata {i}/{len(todo)} (network {client.network_requests}, cached {client.cache_hits}, failed {len(failed)})")
        for table, why in failed:
            log(f"FAILED {table}: {why}")
        return {"requested": len(todo), "loaded": len(todo) - len(failed), "failed": len(failed)}

    def load_periods(self, client: SidraClient, table: int) -> list[dict[str, Any]]:
        rows = client.periods(table).payload
        with self.db:
            self.db.execute("DELETE FROM period WHERE tab = ?", (table,))
            self.db.executemany("INSERT INTO period VALUES (?,?,?,?)", [
                (table, str(p["id"]), "; ".join(p.get("literals") or []), p.get("modificacao")) for p in rows])
        return rows

    def load_locality_count(self, client: SidraClient, table: int, level: str) -> int:
        """The table's localities at ``level`` (IBGE's ``/localidades``), and how many of them are state capitals
        (`geography.members('capital')`, by the six digits of the code): a table whose N6 are exactly the 27 capitals
        is told from one that covers the country by these two numbers."""
        response = client.localities(table, level)
        n = len(response.payload)
        capitals = _capital_codes()
        n_capitals = sum(1 for loc in response.payload if str(loc["id"])[:6] in capitals) if level == "N6" else None
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO locality_count VALUES (?,?,?,?,?)",
                            (table, level, n, response.sha256, n_capitals))
        return n

    def load_compendium(self, entries: dict[str, dict[str, Any]]) -> int:
        """Lay the curated overlay over the registry: tier and group per table, and per variable
        whether it is kept by default and its kind (the compendium's kind outranks the inferred one)."""
        with self.db:
            self.db.execute("DELETE FROM compendium")
            self.db.execute("UPDATE variable SET keep = 0")
            self.db.execute("DELETE FROM compendium_variable")
            self.db.execute("DELETE FROM compendium_policy")
            self.db.executemany("INSERT INTO compendium VALUES (?,?,?,?,?)", [
                (int(t), e.get("tier"), e.get("group"), e.get("role"), e.get("note")) for t, e in entries.items()])
            for t, e in entries.items():
                for class_id, policy in (e.get("categories") or {}).items():
                    self.db.execute("INSERT OR REPLACE INTO compendium_policy VALUES (?,?,?)", (int(t), int(class_id), str(policy)))
                for v in e.get("variables") or []:
                    self.db.execute("INSERT OR REPLACE INTO compendium_variable VALUES (?,?,?,?)",
                                    (int(t), int(v["id"]), v.get("kind"), int(bool(v.get("keep")))))
                    self.db.execute("UPDATE variable SET keep = ?, kind = COALESCE(?, kind) WHERE tab = ? AND id = ?",
                                    (int(bool(v.get("keep"))), v.get("kind"), int(t), int(v["id"])))
        return len(entries)

    # -- questions -------------------------------------------------------------------------------

    def tab(self, table: int) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM tab WHERE id = ?", (table,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["levels"] = json.loads(out["levels"] or "[]")
        out.pop("search", None)
        return out

    def variables(self, table: int) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            "SELECT id, name, unit, kind, keep FROM variable WHERE tab = ? ORDER BY id", (table,))]

    def classifications(self, table: int) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            "SELECT id, name, n_categories FROM classification WHERE tab = ? ORDER BY rowid", (table,))]

    def categories(self, table: int, class_id: int, *, synthetic: bool = False) -> list[dict[str, Any]]:
        """A classification's categories as IBGE lists them; ``synthetic`` adds the implicit total (id 0)
        of a classification that lists no Total, which answers a request but cannot be asked for."""
        return [dict(r) for r in self.db.execute(
            "SELECT id, name, level, is_total FROM category WHERE tab = ? AND class_id = ? "
            + ("" if synthetic else "AND synthetic = 0 ") + "ORDER BY rowid", (table, class_id))]

    def resolve_categories(self, table: int, class_id: int, spec: Any) -> Any:
        """A category policy as the planner takes it: ``all`` and ``total`` as they are; ``non_total`` (every category but
        the Total); ``level:N`` (the Total and the categories down to depth N of IBGE's hierarchy, e.g. an age group but not
        its single years); or a list of ids."""
        if not isinstance(spec, str) or spec in ("all", "total"):
            return spec
        cats = self.categories(table, class_id)
        if spec == "non_total":
            return [c["id"] for c in cats if not c["is_total"]]
        if spec.startswith("level:"):
            depth = int(spec[6:])
            return [c["id"] for c in cats if c["is_total"] or 0 <= (c["level"] if c["level"] is not None else 0) <= depth]
        raise ValueError(f"unknown category policy {spec!r}: all, total, non_total, level:N or a list of ids")

    def policy(self, table: int) -> dict[int, str]:
        """The compendium's category policy for a table: classification id → policy."""
        return {r[0]: r[1] for r in self.db.execute("SELECT class_id, policy FROM compendium_policy WHERE tab = ?", (table,))}

    def total_category(self, table: int, class_id: int) -> int | None:
        """The category that stands for the whole classification (IBGE's ``Total``), if it has one."""
        row = self.db.execute("SELECT id FROM category WHERE tab = ? AND class_id = ? AND is_total = 1 LIMIT 1",
                              (table, class_id)).fetchone()
        return None if row is None else int(row[0])

    def search(self, terms: str, *, level: str | None = None, research: str | None = None,
               compendium_only: bool = False, limit: int = 30) -> list[dict[str, Any]]:
        """Tables whose name, research, subject, variables or classifications contain every term."""
        where, args = ["t.search IS NOT NULL"], []
        for word in fold(terms).split():
            where.append("t.search LIKE ?")
            args.append(f"%{word}%")
        if level:
            where.append("t.levels LIKE ?")
            args.append(f'%"{level}"%')
        if research:
            where.append("t.research LIKE ?")
            args.append(f"%{research}%")
        if compendium_only:
            where.append("c.tab IS NOT NULL")
        rows = self.db.execute(
            "SELECT t.id, t.name, t.research, t.frequency, t.first_period, t.last_period, t.has_n6, "
            "t.n_variables, t.n_classifications, c.tier FROM tab t LEFT JOIN compendium c ON c.tab = t.id "
            f"WHERE {' AND '.join(where)} ORDER BY (c.tier IS NULL), c.tier, t.id LIMIT ?", (*args, limit))
        return [dict(r) for r in rows]

    def scan_summary(self) -> dict[str, Any]:
        q = lambda sql: self.db.execute(sql).fetchone()[0]  # noqa: E731
        return {"tables": q("SELECT COUNT(*) FROM tab"), "with_metadata": q("SELECT COUNT(*) FROM tab WHERE metadata_sha256 IS NOT NULL"),
                "with_n6": q("SELECT COUNT(*) FROM tab WHERE has_n6 = 1"), "categories": q("SELECT COUNT(*) FROM category")}


_TOTAL = re.compile(r"^(total|geral|total geral)\b", re.IGNORECASE)


def _is_total_name(name: str) -> bool:
    return bool(_TOTAL.match(name.strip()))


def load_compendium_file(registry: Registry, curation_dir: Path) -> int:
    """Read ``curation/sidra/compendium.yml`` into the registry's overlay."""
    from ..semantics.curation import read_yaml

    entries = read_yaml(Path(curation_dir) / "sidra" / "compendium.yml").get("tables") or {}
    return registry.load_compendium({str(k): v for k, v in entries.items()})


def compendium_disagreements(registry: Registry) -> list[dict[str, Any]]:
    """Per curated table, what IBGE's metadata does not bear out: not scanned, no municipal level, variables
    the compendium lists that IBGE does not, and variables IBGE lists that the compendium does not mention."""
    out = []
    q = registry.db.execute
    for tab, tier, sha, has_n6, name in q("SELECT c.tab, c.tier, t.metadata_sha256, t.has_n6, t.name FROM compendium c "
                                          "LEFT JOIN tab t ON t.id = c.tab ORDER BY c.tab").fetchall():
        issues: list[str] = []
        if sha is None:
            issues.append("not in the registry (not scanned, or IBGE no longer lists it)")
        else:
            gone = [r[0] for r in q("SELECT id FROM compendium_variable WHERE tab = ? AND id NOT IN "
                                    "(SELECT id FROM variable WHERE tab = ?)", (tab, tab))]
            extra = q("SELECT COUNT(*) FROM variable WHERE tab = ? AND id NOT IN "
                      "(SELECT id FROM compendium_variable WHERE tab = ?)", (tab, tab)).fetchone()[0]
            if not has_n6:
                issues.append("no municipal level (N6)")
            if gone:
                issues.append(f"variables not in IBGE's metadata: {gone}")
            if extra:
                issues.append(f"IBGE variables the compendium does not mention: {extra}")
        if issues:
            out.append({"table": tab, "tier": tier, "name": (name or "")[:60], "issues": "; ".join(issues)})
    return out


def open_registry(root: Path) -> Registry:
    from ..config import load_settings

    return Registry(load_settings(root=root).registry_dir("sidra", "registry.sqlite"))
