"""``info()`` — metadata on any node of the ontology.

``explore()`` answers "what is out there to fetch". ``describe()`` answers "what
does this column mean". ``info()`` sits between them and answers "what IS this
thing", for any level of the ontology: a system, a dataset, a schema generation,
or a variable.

Every answer separates three things that are easy to blur and expensive to
confuse:

``identity``
    What the node IS, as an institution declares it. Stable. Does not change when
    DATASUS reorganises the FTP tree.

``evidence``
    How the crawl has actually seen it — which ``(system, series)`` pairs bind to
    it, under which rule, and how many files. Derived and disposable.

``coverage``
    What is actually held: years, states, schema generations, file counts.

So a dataset can be fully described and hold no files (declared, not yet
published), or hold a great many files and be thinly described. Those are
different problems and the caller should be able to tell them apart at a glance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .catalog.store import Catalog as _Store
from .config import Settings, load_settings
from .ontology import DatasetNode, Ontology, SystemNode


@dataclass
class Info:
    """One answer from :func:`info`."""

    kind: str
    code: str
    identity: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    schemas: list[dict[str, Any]] = field(default_factory=list)
    children: list[dict[str, Any]] = field(default_factory=list)
    documentation: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "code": self.code,
            "identity": self.identity,
            "evidence": self.evidence,
            "coverage": self.coverage,
            "schemas": self.schemas,
            "children": self.children,
            "documentation": self.documentation,
            "notes": self.notes,
        }

    def __repr__(self) -> str:  # pragma: no cover - presentation
        out: list[str] = []
        name = self.identity.get("translated_name") or self.identity.get("official_name")
        out.append(f"{self.kind}: {self.code}" + (f" — {name}" if name else ""))

        official = self.identity.get("official_name")
        if official and official != name:
            out.append(f"  {official}")
        what = self.identity.get("what_it_is")
        if what:
            out.append("")
            out.extend("  " + line for line in _wrap(what, 76))

        if self.coverage:
            out.append("")
            bits = []
            if self.coverage.get("files"):
                bits.append(f"{self.coverage['files']:,} files")
            span = self.coverage.get("span")
            if span:
                bits.append(f"{span}")
            if self.coverage.get("schema_generations"):
                bits.append(f"{self.coverage['schema_generations']} schema generations")
            if self.coverage.get("ufs"):
                bits.append(f"{self.coverage['ufs']} UFs")
            if bits:
                out.append("  coverage: " + " · ".join(bits))

        if self.documentation:
            described = self.documentation.get("columns_described")
            total = self.documentation.get("columns_total")
            if total:
                pct = 100.0 * (described or 0) / total
                out.append(f"  columns: {described or 0}/{total} described ({pct:.0f}%)")

            row = self.documentation.get("what_one_row_is")
            if row:
                out.append("")
                out.append("  one row is:")
                out.extend("    " + line for line in _wrap(str(row), 74))
                unit = self.documentation.get("unit_of_analysis")
                if unit:
                    out.append(f"    unit of analysis: {unit}")

            bias = self.documentation.get("known_biases")
            if bias:
                out.append("")
                out.append("  known biases:")
                out.extend("    " + line for line in _wrap(str(bias), 74))

            gotchas = self.documentation.get("gotchas")
            if gotchas:
                if isinstance(gotchas, str):
                    try:
                        import json as _json

                        gotchas = _json.loads(gotchas)
                    except Exception:
                        gotchas = [gotchas]
                out.append("")
                out.append("  gotchas:")
                for g in list(gotchas)[:8]:
                    wrapped = _wrap(str(g), 70)
                    out.append(f"    - {wrapped[0]}")
                    out.extend("      " + line for line in wrapped[1:])

        if self.evidence.get("observed_as"):
            out.append(f"  seen as: {', '.join(self.evidence['observed_as'][:8])}")

        if self.schemas:
            out.append("")
            out.append(f"  schema generations ({len(self.schemas)}), oldest first:")
            for s in self.schemas[:12]:
                line = (
                    f"    {str(s.get('span', '')):<11} "
                    f"{str(s.get('field_count', '?')):>4} cols  "
                    f"{s.get('files', 0):>6,} files  "
                    f"{s.get('schema_signature', '')[:10]}"
                )
                out.append(line)
                delta = []
                if s.get("added"):
                    delta.append(f"+{len(s['added'])} {' '.join(s['added'][:5])}")
                if s.get("dropped"):
                    delta.append(f"-{len(s['dropped'])} {' '.join(s['dropped'][:5])}")
                if delta:
                    out.append(f"        {'; '.join(delta)}")
            if len(self.schemas) > 12:
                out.append(f"    ... and {len(self.schemas) - 12} more")

        if self.children:
            out.append("")
            out.append(f"  contains ({len(self.children)}):")
            for c in self.children[:20]:
                label = c.get("translated_name") or c.get("official_name") or ""
                out.append(f"    {c['code']:<24} {label[:44]}")
            if len(self.children) > 20:
                out.append(f"    ... and {len(self.children) - 20} more")

        for note in self.notes:
            out.append(f"  ! {note}")
        return "\n".join(out)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------------------


def info(
    target: str | None = None,
    *,
    field_name: str | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> Info:
    """Describe any node of the ontology.

    ``info()`` with no target returns the overview. ``info("SIH")`` a system,
    ``info("SIH.RD")`` a dataset, ``info("SIH.RD", field_name="DIAG_PRINC")`` or
    ``info("SIH.RD.DIAG_PRINC")`` a variable. System aliases resolve, so
    ``SIHSUS`` and ``SIH`` are the same node, and a bare dataset code works when
    it is unambiguous.
    """
    cfg = settings or load_settings(root=Path(root) if root else None)
    store = _Store(cfg.catalog_path, read_only=True)
    onto = Ontology.load()
    try:
        text = str(target or "").strip()

        # "SIH.RD.DIAG_PRINC" — a field qualified by its dataset.
        if text and field_name is None and text.count(".") >= 2:
            head, tail = text.rsplit(".", 1)
            if onto.resolve(head) and tail.isupper():
                text, field_name = head, tail

        if field_name:
            return _variable(store, onto, text, field_name)
        if not text:
            return _overview(store, onto)

        found = onto.resolve(text)
        if found is None:
            return Info(
                kind="unknown",
                code=text,
                notes=[
                    f"'{target}' does not resolve to a system, dataset or alias. "
                    "Try info() for the list."
                ],
            )
        kind, node = found
        if kind == "system":
            return _system(store, onto, node)
        return _dataset(store, onto, node)
    finally:
        store.close()


# ------------------------------------------------------------------ builders


def _overview(store: _Store, onto: Ontology) -> Info:
    rows = store.query(
        "SELECT system, series, SUM(file_count) AS files FROM strata "
        "WHERE system IS NOT NULL AND series IS NOT NULL GROUP BY 1, 2"
    )
    files_by_system: dict[str, int] = {}
    for r in rows:
        binding = onto.bind(str(r["system"]), str(r["series"]))
        key = binding.system or str(r["system"])
        files_by_system[key] = files_by_system.get(key, 0) + int(r["files"] or 0)

    children = []
    for code, node in sorted(onto.systems.items()):
        children.append(
            {
                "code": code,
                "official_name": node.official_name,
                "translated_name": node.translated_name,
                "kind": node.kind,
                "datasets": len(onto.datasets_of(code)),
                "files": files_by_system.get(code, 0),
            }
        )
    children.sort(key=lambda c: -int(c["files"] or 0))
    return Info(
        kind="overview",
        code="*",
        identity={
            "translated_name": "DATASUS data ontology",
            "what_it_is": (
                "Systems and the datasets they publish. A system is an institution's "
                "information system; a dataset is one of its published subfamilies, "
                "such as SIH.RD. Ask info('SIH') or info('SIH.RD') for detail."
            ),
        },
        coverage={"files": sum(files_by_system.values())},
        children=children,
    )


def _system(store: _Store, onto: Ontology, node: SystemNode) -> Info:
    datasets = onto.datasets_of(node.code)
    rows = store.query(
        "SELECT system, series, SUM(file_count) AS files, MIN(year) AS y0, MAX(year) AS y1 "
        "FROM strata WHERE system IS NOT NULL AND series IS NOT NULL GROUP BY 1, 2"
    )
    per_dataset: dict[str, dict[str, Any]] = {}
    total = 0
    y0 = y1 = None
    for r in rows:
        binding = onto.bind(str(r["system"]), str(r["series"]))
        if binding.system != node.code or not binding.dataset:
            continue
        slot = per_dataset.setdefault(binding.dataset, {"files": 0, "y0": None, "y1": None})
        slot["files"] += int(r["files"] or 0)
        total += int(r["files"] or 0)
        for key, val in (("y0", r["y0"]), ("y1", r["y1"])):
            if val is None:
                continue
            cur = slot[key]
            slot[key] = val if cur is None else (min(cur, val) if key == "y0" else max(cur, val))
        if r["y0"] is not None:
            y0 = r["y0"] if y0 is None else min(y0, r["y0"])
        if r["y1"] is not None:
            y1 = r["y1"] if y1 is None else max(y1, r["y1"])

    children = []
    for d in datasets:
        got = per_dataset.get(d.code, {})
        children.append(
            {
                "code": d.code,
                "official_name": d.official_name,
                "translated_name": d.translated_name,
                "files": got.get("files", 0),
                "span": _span(got.get("y0"), got.get("y1")),
                "status": d.status,
            }
        )
    children.sort(key=lambda c: -int(c["files"] or 0))

    notes = []
    if node.kind == "tooling":
        notes.append("This is tooling shipped on the tree, not data.")
    if node.kind == "reference":
        notes.append("A reference source rather than an activity system.")

    return Info(
        kind="system",
        code=node.code,
        identity={
            "official_name": node.official_name,
            "translated_name": node.translated_name,
            "what_it_is": node.what_it_is,
            "authority": node.authority,
            "kind": node.kind,
            "status": node.status,
        },
        evidence={"crawled_as": list(node.crawled_as) or [node.code]},
        coverage={"files": total, "span": _span(y0, y1), "datasets": len(datasets)},
        children=children,
        notes=notes,
    )


def _dataset(store: _Store, onto: Ontology, node: DatasetNode) -> Info:
    rows = store.query(
        "SELECT system, series, SUM(file_count) AS files, MIN(year) AS y0, MAX(year) AS y1 "
        "FROM strata WHERE system IS NOT NULL AND series IS NOT NULL GROUP BY 1, 2"
    )
    pairs: list[dict[str, Any]] = []
    files = 0
    y0 = y1 = None
    for r in rows:
        binding = onto.bind(str(r["system"]), str(r["series"]))
        if binding.dataset != node.code:
            continue
        files += int(r["files"] or 0)
        pairs.append(
            {
                "system": str(r["system"]),
                "series": str(r["series"]),
                "rule": binding.rule,
                "files": int(r["files"] or 0),
            }
        )
        if r["y0"] is not None:
            y0 = r["y0"] if y0 is None else min(y0, r["y0"])
        if r["y1"] is not None:
            y1 = r["y1"] if y1 is None else max(y1, r["y1"])

    crawled_systems = {p["system"] for p in pairs}
    schemas: list[dict[str, Any]] = []
    signatures: set[str] = set()
    if crawled_systems:
        marks = ",".join("?" for _ in crawled_systems)
        for r in store.query(
            f"SELECT family_id, system, series, schema_signature, field_count, "
            f"time_min, time_max, file_count, geo_coverage, schema_source "
            f"FROM families WHERE system IN ({marks})",
            tuple(crawled_systems),
        ):
            binding = onto.bind(str(r["system"]), str(r["series"]))
            if binding.dataset != node.code:
                continue
            signatures.add(str(r["schema_signature"]))
            schemas.append(
                {
                    "family_id": r["family_id"],
                    "schema_signature": str(r["schema_signature"]),
                    "field_count": r["field_count"],
                    "time_min": r["time_min"],
                    "time_max": r["time_max"],
                    "files": int(r["file_count"] or 0),
                    "schema_source": r["schema_source"],
                }
            )
    schemas = _generations(store, schemas)

    # Documentation coverage, counted over the columns this dataset actually has.
    described = total_cols = 0
    if signatures:
        marks = ",".join("?" for _ in signatures)
        cols = {
            str(r["field_name"])
            for r in store.query(
                f"SELECT DISTINCT field_name FROM schema_presence "
                f"WHERE schema_signature IN ({marks})",
                tuple(signatures),
            )
        }
        total_cols = len(cols)
        if cols and crawled_systems:
            sys_marks = ",".join("?" for _ in crawled_systems)
            done = {
                str(r["field_name"])
                for r in store.query(
                    f"SELECT field_name FROM field_documentation "
                    f"WHERE system IN ({sys_marks}) AND description IS NOT NULL "
                    f"AND TRIM(description) <> '' "
                    f"UNION "
                    f"SELECT field_name FROM variable_docs "
                    f"WHERE system IN ({sys_marks}) AND description IS NOT NULL "
                    f"AND TRIM(description) <> ''",
                    tuple(crawled_systems) * 2,
                )
            }
            described = len(cols & done)

    # What one row IS, if it has been curated.
    doc = {}
    for r in store.query(
        "SELECT what_one_row_is, unit_of_analysis, known_biases, gotchas "
        "FROM dataset_docs WHERE UPPER(dataset_id) = ? OR "
        "(UPPER(system) = ? AND UPPER(series) = ?) LIMIT 1",
        (node.code, node.system, node.short_code),
    ):
        doc = {k: r[k] for k in r.keys() if r[k] is not None}

    notes = []
    if node.confidence != "high":
        notes.append(f"Identity asserted with {node.confidence} confidence — verify before relying on it.")
    if node.status == "retired":
        notes.append("Retired: the series does not continue to the present.")
    if node.status == "tooling":
        notes.append("Tooling, not data.")
    if not files:
        notes.append("Declared but not observed in the crawl — no files bind to this node.")

    return Info(
        kind="dataset",
        code=node.code,
        identity={
            "system": node.system,
            "official_name": node.official_name,
            "translated_name": node.translated_name,
            "what_it_is": node.what_it_is,
            "status": node.status,
            "confidence": node.confidence,
        },
        evidence={
            "observed_as": list(node.observed_as),
            "bound_pairs": sorted(pairs, key=lambda p: -p["files"])[:12],
            "crawled_systems": sorted(crawled_systems),
        },
        coverage={
            "files": files,
            "span": _span(y0, y1),
            "schema_generations": len(schemas),
        },
        schemas=schemas,
        documentation={
            **doc,
            "columns_total": total_cols,
            "columns_described": described,
        },
        notes=notes,
    )


def _generations(store: _Store, families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse families into schema generations, and say what changed between them.

    Two separate jobs, both of which the raw family list gets wrong.

    *Grouping.* One schema signature can appear under several families, because
    the same schema is reached through several spellings of the series. Listing
    them separately showed SIH.RD's 113-column generation twice, as though the
    schema had changed and changed back. A generation is a signature, not a
    family.

    *Diffing.* A generation is only meaningful next to its neighbour: "113
    columns, 2014-2025" says nothing, while "added 6, dropped 1 against the
    previous generation" is the fact an analyst needs before pooling years across
    the boundary. The columns come from the header census, so this costs a
    lookup rather than a decode.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for fam in families:
        sig = str(fam["schema_signature"])
        slot = grouped.setdefault(
            sig,
            {
                "schema_signature": sig,
                "field_count": fam["field_count"],
                "files": 0,
                "families": 0,
                "time_min": None,
                "time_max": None,
                "schema_source": fam["schema_source"],
            },
        )
        slot["files"] += int(fam["files"] or 0)
        slot["families"] += 1
        for key, op in (("time_min", min), ("time_max", max)):
            val = fam[key]
            if val is None:
                continue
            slot[key] = val if slot[key] is None else op(slot[key], val)

    order = sorted(
        grouped.values(),
        key=lambda g: (g["time_min"] is None, g["time_min"], g["schema_signature"]),
    )
    if not order:
        return []

    fields: dict[str, set[str]] = {}
    sigs = [g["schema_signature"] for g in order]
    marks = ",".join("?" for _ in sigs)
    for row in store.query(
        f"SELECT schema_signature, field_name FROM schema_presence "
        f"WHERE schema_signature IN ({marks})",
        tuple(sigs),
    ):
        fields.setdefault(str(row["schema_signature"]), set()).add(str(row["field_name"]))

    previous: set[str] | None = None
    for gen in order:
        here = fields.get(gen["schema_signature"], set())
        gen["span"] = _span(gen.pop("time_min"), gen.pop("time_max"))
        if previous is None:
            gen["added"], gen["dropped"] = [], []
            gen["is_first"] = True
        else:
            gen["added"] = sorted(here - previous)
            gen["dropped"] = sorted(previous - here)
            gen["is_first"] = False
        previous = here
    return order


def _variable(store: _Store, onto: Ontology, target: str, field_name: str) -> Info:
    name = field_name.upper()
    found = onto.resolve(target) if target else None
    systems: list[str] = []
    scope = None
    if found:
        kind, node = found
        scope = node
        systems = list(node.crawled_as) or [node.code] if kind == "system" else []
        if kind == "dataset":
            systems = sorted(
                {
                    b.observed_system
                    for b in [
                        onto.bind(str(r["system"]), str(r["series"]))
                        for r in store.query(
                            "SELECT DISTINCT system, series FROM strata "
                            "WHERE system IS NOT NULL AND series IS NOT NULL"
                        )
                    ]
                    if b.dataset == node.code
                }
            )

    clause, params = "", [name]
    if systems:
        clause = f" AND system IN ({','.join('?' for _ in systems)})"
        params += systems

    docs = store.query(
        f"SELECT system, field_name, official_name, translated_name, description, "
        f"source, reasoning FROM variable_docs WHERE field_name = ?{clause}",
        tuple(params),
    )
    if not docs:
        docs = store.query(
            f"SELECT system, field_name, NULL AS official_name, NULL AS translated_name, "
            f"description, source, NULL AS reasoning FROM field_documentation "
            f"WHERE field_name = ?{clause}",
            tuple(params),
        )

    if not docs:
        return Info(
            kind="variable",
            code=name,
            notes=[f"No documentation recorded for {name}" + (f" in {target}" if target else "")],
        )

    first = docs[0]
    where = store.query(
        "SELECT DISTINCT s.system, s.series FROM schema_presence sp "
        "JOIN strata s ON s.schema_signature = sp.schema_signature "
        "WHERE sp.field_name = ? LIMIT 200",
        (name,),
    )
    datasets = sorted(
        {
            b.dataset
            for b in [onto.bind(str(r["system"]), str(r["series"])) for r in where]
            if b.dataset
        }
    )
    return Info(
        kind="variable",
        code=name,
        identity={
            "official_name": first["official_name"],
            "translated_name": first["translated_name"],
            "what_it_is": first["description"],
            "system": first["system"],
        },
        evidence={
            "source": first["source"],
            "reasoning": first["reasoning"] if "reasoning" in first.keys() else None,
            "scope": getattr(scope, "code", None),
        },
        children=[{"code": d, "translated_name": ""} for d in datasets],
    )


def _span(y0: Any, y1: Any) -> str:
    if y0 is None and y1 is None:
        return ""
    if y0 == y1 or y1 is None:
        return str(y0)
    if y0 is None:
        return str(y1)
    return f"{y0}–{y1}"
