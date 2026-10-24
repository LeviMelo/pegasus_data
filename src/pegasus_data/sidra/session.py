"""`Sidra`: the registry, the client and the fact store behind one object.

    s = Sidra(root)                       # <root>/registries/sidra/ (registry, HTTP cache), <root>/lake/sidra/ (facts)
    s.describe(9606)                      # what the table holds, from IBGE's metadata
    sel = s.selection(9606, variables=[93], periods=[2022], classifications={86: "all", 2: "all", 287: "all"})
    s.plan(sel)                           # the requests, under SIDRA's limits
    s.fetch(sel)                          # fetch what is not yet stored, resumably
    s.facts(9606, periods=["2022"])       # the long fact table
    s.series("population_total")          # a series stitched across tables and censuses (curation/sidra/series.yml)
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import pyarrow as pa

from . import planner, store
from .client import SidraClient, SidraRefused
from .planner import ALL, Chunk, PlanError, Selection
from .registry import Registry, open_registry

__all__ = ["Sidra"]

MIN_FREE_BYTES = 4 * 2**30


def _version() -> str:
    try:
        return version("pegasus-data")
    except PackageNotFoundError:
        return "unknown"


class Sidra:
    def __init__(self, root: Path | str | None = None, *, settings: Any = None, delay: float = 0.3) -> None:
        """``root``: the data home; or ``settings`` (a `config.Settings`), which also places the lake."""
        from ..config import load_settings

        settings = settings or load_settings(root=Path(root) if root else None)
        self.root = Path(settings.root)
        self.lake = Path(settings.lake_dir)
        self.client = SidraClient(self.root / "registries" / "sidra" / "http", delay=delay)
        self.registry: Registry = open_registry(self.root)

    # -- the registry ----------------------------------------------------------------------------

    def ensure(self, table: int) -> dict[str, Any]:
        """The table's registry row, fetching its metadata if the registry does not have it yet."""
        tab = self.registry.tab(table)
        if tab is None or tab["metadata_sha256"] is None:
            response = self.client.metadata(table)
            if tab is None:
                self.registry.db.execute("INSERT OR IGNORE INTO tab (id, name) VALUES (?, ?)", (table, response.payload["nome"]))
            self.registry.load_metadata(table, response.payload, response.sha256, response.fetched_at)
            tab = self.registry.tab(table)
        assert tab is not None
        return tab

    def describe(self, table: int) -> dict[str, Any]:
        """The table's registry row, what its numbers rest on (``basis``: universe, sample, mixed by period or unknown,
        with IBGE's passage; `sidra.notes`), its variables and classifications."""
        from .notes import basis

        tab = self.ensure(table)
        return {**tab, "basis": basis(table, self.registry), "variables": self.registry.variables(table),
                "classifications": self.registry.classifications(table)}

    def periods(self, table: int) -> list[str]:
        self.ensure(table)
        rows = self.registry.db.execute("SELECT id FROM period WHERE tab = ? ORDER BY id", (table,)).fetchall()
        if not rows:
            self.registry.load_periods(self.client, table)
            rows = self.registry.db.execute("SELECT id FROM period WHERE tab = ? ORDER BY id", (table,)).fetchall()
        return [r[0] for r in rows]

    def per_state(self, table: int) -> dict[str, int]:
        """Municipalities of the table in each state, from the table's own ``/localidades/N6``."""
        counts: dict[str, int] = {}
        for loc in self.client.localities(table, "N6").payload:
            counts[str(loc["id"])[:2]] = counts.get(str(loc["id"])[:2], 0) + 1
        return counts

    # -- selecting, planning, fetching -----------------------------------------------------------

    def selection(self, table: int, *, variables: Sequence[int] | None = None, periods: Sequence[int | str] | str = ALL,
                  level: str = "N6", scope: str | Sequence[str] = ALL, states: bool = False,
                  classifications: dict[int, Any] | None = None) -> Selection:
        """A `Selection` with defaults resolved: variables left out are the ones the table's compendium entry
        keeps (or all but its derived shares); periods ``"all"`` or ``"latest"`` come from the table's period list."""
        self.ensure(table)
        have = [v["id"] for v in self.registry.variables(table)]
        if variables is None:
            kept = [r[0] for r in self.registry.db.execute(
                "SELECT id FROM variable WHERE tab = ? AND keep = 1 ORDER BY id", (table,))]
            # no curated choice: every variable but the percentages IBGE derives from another variable of the
            # table (its id is 1,000,000 + that variable's: 1000093 is 93 as a share of the total)
            have_set = set(have)
            variables = kept or [v for v in have if not (v > 1_000_000 and v - 1_000_000 in have_set)] or have
        known = self.periods(table)
        if periods == ALL:
            chosen = known
        elif periods == "latest":
            chosen = known[-1:]
        else:
            chosen = [str(p) for p in periods]
            missing = [p for p in chosen if p not in known]
            if missing:
                raise PlanError(f"table {table} has no period(s) {missing}; it has {known[:3]}…{known[-3:]}")
        resolved = {cid: self.registry.resolve_categories(table, cid, spec) for cid, spec in (classifications or {}).items()}
        return Selection(table, list(variables), chosen, level, scope, resolved, states)

    def curated(self, *, group: str | None = None, tier: str | None = None, tables: Sequence[int] | None = None) -> list[int]:
        """The compendium's tables, optionally of one group, one tier, or from a list."""
        where, args = ["1=1"], []
        for column, value in (("grp", group), ("tier", tier)):
            if value:
                where.append(f"{column} = ?")
                args.append(value)
        ids = [r[0] for r in self.registry.db.execute(f"SELECT tab FROM compendium WHERE {' AND '.join(where)} ORDER BY tab", args)]
        return [t for t in ids if not tables or t in set(tables)]

    def curated_selection(self, table: int) -> Selection:
        """What the compendium wants of a table: its kept variables, every period, every locality at N6 (the
        finest level it is published at otherwise), every category of every classification (Totals included,
        so cells can be checked against them) unless the compendium names a policy for the classification
        (``categories:`` in compendium.yml; `Registry.resolve_categories`) because the full cube is not wanted."""
        tab = self.ensure(table)
        level = "N6" if "N6" in tab["levels"] else ("N3" if "N3" in tab["levels"] else tab["levels"][0])
        policy = self.registry.policy(table)
        classes = {c["id"]: policy.get(c["id"], ALL) for c in self.registry.classifications(table)}
        return self.selection(table, level=level, classifications=classes)

    def estimate(self, selection: Selection) -> dict[str, int]:
        """Requests and values a selection would cost, without fetching any values."""
        chunks = self.plan(selection)
        return {"requests": len(chunks), "values": sum(c.values for c in chunks)}

    def plan(self, selection: Selection) -> list[Chunk]:
        per_state = total = None
        if selection.level == "N6" and (selection.scope == ALL or selection.states):
            per_state = self.per_state(selection.table)
        elif selection.scope == ALL:
            total = len(self.client.localities(selection.table, selection.level).payload)
        return planner.plan(selection, self.registry, per_state=per_state, locality_total=total)

    def fetch(self, selection: Selection, *, log: Callable[[str], None] = print, every: int = 10) -> dict[str, Any]:
        """Fetch what the selection needs and is not stored. Resumable: a request whose part exists is skipped."""
        import psutil

        waited = 0
        while psutil.virtual_memory().available < MIN_FREE_BYTES:       # other jobs on the machine: wait, then say so
            if waited >= 600:
                raise MemoryError("less than 4 GB of RAM has been free for ten minutes; not starting a SIDRA fetch")
            time.sleep(30)
            waited += 30
        meta_sha = self.ensure(selection.table)["metadata_sha256"]
        class_ids = [c["id"] for c in self.registry.classifications(selection.table)]
        chunks = self.plan(selection)
        report: dict[str, Any] = {"table": selection.table, "chunks": len(chunks), "expected_values": sum(c.values for c in chunks),
                                  "stored": 0, "fetched": 0, "from_http_cache": 0, "rows": 0, "refused_and_split": 0,
                                  "symbols": {}, "shortfalls": []}
        started = time.monotonic()
        queue = list(chunks)
        done = 0
        while queue:
            chunk = queue.pop(0)
            path = store.part_path(self.lake, chunk.table, chunk.url)
            if path.exists():
                report["stored"] += 1
                done += 1
                continue
            try:
                response = self.client.values(chunk.url)
            except SidraRefused as exc:
                if exc.status < 500:
                    raise
                pieces = split_chunk(chunk, self.registry)
                report["refused_and_split"] += 1
                log(f"refused ({chunk.values} values, {len(chunk.url)} chars): split in {len(pieces)}")
                queue = pieces + queue
                continue
            _, rows, symbols = store.write_part(self.lake, chunk.table, response, class_ids, metadata_sha=meta_sha, version=_version())
            report["fetched"] += 0 if response.from_cache else 1
            report["from_http_cache"] += 1 if response.from_cache else 0
            report["rows"] += rows
            for key, n in symbols.items():
                report["symbols"][key] = report["symbols"].get(key, 0) + n
            if rows != chunk.values:
                report["shortfalls"].append({"url": chunk.url[:160], "expected": chunk.values, "rows": rows})
            done += 1
            if done % every == 0:
                log(f"{selection.table}: {done}/{len(chunks)} requests, {report['rows']} rows, {time.monotonic() - started:.0f}s")
        report["seconds"] = round(time.monotonic() - started, 1)
        return report

    def series(self, name: str, *, fetch: bool = False, log: Callable[[str], None] = print) -> pa.Table:
        """A declared series (``curation/sidra/series.yml``) from the stored facts; ``fetch`` first fetches its sources."""
        from .series import build_series, fetch_series

        if fetch:
            fetch_series(self, name, log=log)
        return build_series(self, name)

    def rebuild(self, table: int, *, log: Callable[[str], None] = print) -> int:
        """Re-derive a table's parts from the responses kept in the HTTP cache (derived state is replaced, never
        accumulated): after a change to how responses are read, no request is made. Returns the parts rewritten."""
        meta_sha = self.ensure(table)["metadata_sha256"]
        class_ids = [c["id"] for c in self.registry.classifications(table)]
        n = 0
        for entry in store.provenance(self.lake, table):
            response = self.client.get("values", entry["url"])
            if not response.from_cache:
                log(f"table {table}: {entry['url'][:100]} was not in the cache and was fetched again")
            store.write_part(self.lake, table, response, class_ids, metadata_sha=meta_sha, version=_version())
            n += 1
        return n

    def facts(self, table: int, **filters: Any) -> pa.Table:
        return store.load_facts(self.lake, table, **filters)

    def slice(self, table: int, *, variables: Sequence[int], periods: Sequence[str],
              picks: Mapping[int, Sequence[int]] | None = None, level: str = "N6") -> pa.Table:
        """Stored facts cut to ``picks`` (classification id → categories wanted) and, for every classification
        not named, to IBGE's Total of it, which is what the server returns for a classification left out. The
        store may hold other selections of the same table; this is how one analysis reads only its own."""
        import pyarrow.compute as pc

        facts = self.facts(table, variables=list(variables), periods=[str(p) for p in periods], level=level, light=True)
        picks = picks or {}
        for c in self.registry.classifications(table):
            chosen = list(picks.get(c["id"]) or [])
            if not chosen:
                total = self.registry.total_category(table, c["id"])
                if total is None:
                    raise LookupError(f"table {table}: classification {c['id']} has no Total; name the categories wanted")
                chosen = [total]
            facts = facts.filter(pc.is_in(facts.column(f"c{c['id']}"), pa.array(chosen, pa.int64())))
        return facts

    def labelled(self, table: int, **filters: Any) -> pa.Table:
        """The stored facts with the registry's words joined on: ``variable_name``, ``unit``, ``kind``, ``basis`` (universe
        or sample, per period where it changes; unknown where IBGE's note was not read or says nothing) with the table's
        `sidra.notes.basis` in the schema metadata (``pegasus.basis``), and for each classification ``c<id>_label`` and
        ``c<id>_total`` (is this IBGE's Total of that classification).
        Labels are joined here and never stored in the lake."""
        import pyarrow.compute as pc

        def take(column: pa.ChunkedArray, ids: list[int], values: pa.Array) -> pa.Array:
            position = pc.index_in(column, pa.array(ids, column.type))
            if position.null_count:
                raise LookupError(f"table {table}: {position.null_count} facts carry a code the registry does not know")
            return pc.take(values, position)

        from .notes import basis

        facts = self.facts(table, **filters)
        # what each fact rests on, by its period where the table's note gives each census its own; never assumed a count
        stated = basis(table, self.registry)
        periods = facts.column("period").to_pylist()
        per_period = stated["by_period"] or {}
        facts = facts.append_column("basis", pa.array([per_period.get(str(p), stated["basis"]) for p in periods], pa.string()))
        facts = facts.replace_schema_metadata({**(facts.schema.metadata or {}),
                                               b"pegasus.basis": json.dumps(stated, ensure_ascii=False).encode("utf-8")})
        variables = self.registry.variables(table)
        ids = [v["id"] for v in variables]
        for source, name in (("name", "variable_name"), ("unit", "unit"), ("kind", "kind")):
            facts = facts.append_column(name, take(facts.column("variable"), ids, pa.array([v[source] for v in variables], pa.string())))
        for c in self.registry.classifications(table):
            cats = self.registry.categories(table, c["id"], synthetic=True)
            column = facts.column(f"c{c['id']}")
            cat_ids = [k["id"] for k in cats]
            facts = facts.append_column(f"c{c['id']}_label", take(column, cat_ids, pa.array([k["name"] for k in cats], pa.string())))
            facts = facts.append_column(f"c{c['id']}_total", take(column, cat_ids, pa.array([bool(k["is_total"]) for k in cats], pa.bool_())))
        return facts


def split_chunk(chunk: Chunk, registry: Registry) -> list[Chunk]:
    """Halve a refused request along its widest explicit dimension (the safety net: the plan is the rule)."""
    classes: dict[int, list[int] | str] = {}
    if chunk.classification:
        for part in chunk.classification.split("|"):
            cid, _, rest = part.partition("[")
            body = rest.rstrip("]")
            classes[int(cid)] = ([c["id"] for c in registry.categories(chunk.table, int(cid))] if body == ALL
                                 else [int(x) for x in body.split(",")])
    dims: list[tuple[int, str, Any]] = [(len(v), "class", k) for k, v in classes.items() if len(v) > 1]
    dims += [(len(chunk.periods), "periods", None), (len(chunk.variables), "variables", None)]
    dims = [d for d in dims if d[0] > 1]
    if chunk.localities.startswith("N6[N3[") and "," in chunk.localities:
        states = chunk.localities[len("N6[N3["):-2].split(",")
        dims.append((len(states), "states", None))
    ids: list[str] = []
    prefix = ""
    if not chunk.localities.startswith("N6[N3[") and not chunk.localities.endswith("[all]"):
        prefix, _, body = chunk.localities.partition("[")
        ids = body.rstrip("]").split(",")
        if len(ids) > 1:
            dims.append((len(ids), "ids", None))
    if not dims:
        raise PlanError(f"SIDRA refused a request that cannot be cut further: {chunk.url[:200]}")
    _, kind, key = max(dims, key=lambda d: d[0])

    def halves(items: list[Any]) -> tuple[list[Any], list[Any]]:
        mid = len(items) // 2
        return items[:mid], items[mid:]

    def text(cls: dict[int, list[int] | str]) -> str:
        return "|".join(f"{k}[{','.join(map(str, v))}]" for k, v in cls.items())

    out: list[Chunk] = []
    for half in (0, 1):
        periods, variables, localities, cls = list(chunk.periods), list(chunk.variables), chunk.localities, dict(classes)
        if kind == "class":
            cls[key] = halves(list(cls[key]))[half]
        elif kind == "periods":
            periods = halves(periods)[half]
        elif kind == "variables":
            variables = halves(variables)[half]
        elif kind == "states":
            localities = f"N6[N3[{','.join(halves(states)[half])}]]"
        else:
            localities = f"{prefix}[{','.join(halves(ids)[half])}]"
        share = 1 / 2
        out.append(Chunk(chunk.table, tuple(variables), tuple(periods), localities, text(cls), math.ceil(chunk.values * share)))
    return out

