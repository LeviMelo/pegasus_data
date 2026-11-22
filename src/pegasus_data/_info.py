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

from .catalog.store import CatalogStore as _Store
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
    #: Declared join keys this node participates in, with each other member's
    #: column and grain. ``rows_per_key == "many"`` is the fan-out warning.
    joins: list[dict[str, Any]] = field(default_factory=list)
    #: A variable several systems document, asked with no system or dataset: one entry per system with that system's
    #: own definition ({system, official_name, translated_name, what_it_is, source, reasoning, datasets}). Systems
    #: file the same name for different things (SEXO is 1/3 in one, 1/2 in another), so no one of them is "the"
    #: definition and none is dropped.
    definitions: list[dict[str, Any]] = field(default_factory=list)
    #: The enrichment targets a dataset's records can take (``query(enrich=[...])``): each declared target of
    #: ``joins.yml`` ``enrichments:`` whose key column the dataset's roles name ({target, route, reads}).
    enrichments: list[dict[str, Any]] = field(default_factory=list)

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
            "joins": self.joins,
            "definitions": self.definitions,
            "enrichments": self.enrichments,
        }

    # Rendering is split by section rather than written as one pass. The
    # sections are independent — a system has children and no schemas, a
    # variable has neither — and finding one of them should not mean reading a
    # hundred and forty lines to work out where it starts.

    def _identity_lines(self) -> list[str]:
        out: list[str] = []
        name = self.identity.get("translated_name") or self.identity.get("official_name")
        out.append(f"{self.kind}: {self.code}" + (f" \u2014 {name}" if name else ""))
        official = self.identity.get("official_name")
        if official and official != name:
            out.append(f"  {official}")
        what = self.identity.get("what_it_is")
        if what:
            out.append("")
            out.extend("  " + line for line in _wrap(what, 76))
        if self.kind == "variable" and what:
            out.extend(self._source_lines())
        return out

    #: How far a description can be trusted, by the rung it came from. An
    #: inferred description printed like a documented one reads as fact
    #: (ORIGEM was one, and wrong; EVALUATION 2026-09-30, omnisus facts).
    _SOURCE_STANDING = {
        "layout_doc": "a DATASUS record layout or dictionary",
        "def": "a TabWin definition file (.DEF)",
        "web": "a published document found on the web",
        "manual": "stated by the project, from a measurement or a review of the documents",
        "inferred": "INFERRED by the project: no document describes this field; unverified",
    }

    def _source_lines(self) -> list[str]:
        source = str(self.evidence.get("source") or "")
        standing = self._SOURCE_STANDING.get(source, source) if source else "not recorded"
        out = ["", f"  source: {standing}"]
        reasoning = self.evidence.get("reasoning")
        if reasoning and source in ("manual", "inferred"):
            lines = _wrap(str(reasoning), 72)
            out.extend("    " + line for line in lines[:8])
            if len(lines) > 8:
                out.append("    ...")
        return out

    def _definition_lines(self) -> list[str]:
        out: list[str] = []
        for d in self.definitions:
            name = d.get("translated_name") or d.get("official_name") or ""
            out.append("")
            out.append(f"  [{d['system']}]" + (f" {name}" if name else ""))
            out.extend("      " + line for line in _wrap(d.get("what_it_is") or "(no description recorded)", 70))
            source = str(d.get("source") or "")
            out.append(f"      source: {self._SOURCE_STANDING.get(source, source) if source else 'not recorded'}")
            datasets = d.get("datasets") or []
            if datasets:
                out.append(f"      in: {', '.join(datasets[:12])}" + (f" and {len(datasets) - 12} more" if len(datasets) > 12 else ""))
        return out

    def _coverage_lines(self) -> list[str]:
        if not self.coverage:
            return []
        out = [""]
        bits = []
        if self.coverage.get("files"):
            bits.append(f"{self.coverage['files']:,} files")
        if self.coverage.get("span"):
            bits.append(f"{self.coverage['span']}")
        if self.coverage.get("schema_generations"):
            bits.append(f"{self.coverage['schema_generations']} schema generations")
        if self.coverage.get("ufs"):
            bits.append(f"{self.coverage['ufs']} UFs")
        if bits:
            out.append("  coverage: " + " \u00b7 ".join(bits))
        if "rows_held" in self.coverage:
            held = self.coverage.get("rows_held")
            span = self.coverage.get("span_held")
            got = int(self.coverage.get("files_downloaded") or 0)
            months = self.coverage.get("months_downloaded")
            # downloaded but not built is held too: CNES's registers are read from the blob store and never built into the
            # lake, and this page said "none" of twelve years of them (an agent read it so, 2026-11-22)
            if held:
                out.append(f"  held in this install: {held:,} rows in the lake" + (f", {span}" if span else ""))
            if got:
                out.append(f"  downloaded in this install: {got:,} files" + (f" (months {months})" if months else "")
                           + (", read without the network" if not held else ""))
            if not held and not got:
                out.append("  held in this install: none (query() fetches what it needs)")

        # How the FILES are split, which is not the same as what the rows hold.
        axes = self.coverage.get("axes")
        if axes is not None and self.kind == "dataset":
            shown = ", ".join(axes) if axes else "nothing \u2014 the files are not split"
            out.append(f"  filterable by: {shown}")
            if self.coverage.get("lake_national_only"):
                out.append("    published one file per state, but held as one national partition: geography= takes BR "
                           "only; filter the state column after reading")
            absent = [a for a in ("uf", "year", "month") if a not in axes
                      and not (a == "uf" and self.coverage.get("lake_national_only"))]
            if absent:
                out.append(
                    f"    NOT split by {', '.join(absent)}; filtering on "
                    f"{'/'.join(absent)} matches no file and returns empty"
                )
        return out

    def _documentation_lines(self) -> list[str]:
        if not self.documentation:
            return []
        out: list[str] = []
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

        questions = self.documentation.get("open_questions") or []
        if questions:
            out.append("")
            out.append(
                f"  open questions ({len(questions)}) \u2014 unsettled, not guessed:"
            )
            for q in list(questions)[:4]:
                out.append(f"    {q.get('key', '')}")
                for line in _wrap(str(q.get("question") or ""), 68):
                    out.append(f"        {line}")
            if len(questions) > 4:
                out.append(f"    ... and {len(questions) - 4} more")

        out.extend(self._gotcha_lines())
        return out

    def _gotcha_lines(self) -> list[str]:
        gotchas = self.documentation.get("gotchas")
        if not gotchas:
            return []
        if isinstance(gotchas, str):
            try:
                import json as _json

                gotchas = _json.loads(gotchas)
            except Exception:  # noqa: BLE001 - a plain string is a single gotcha
                gotchas = [gotchas]
        out = ["", "  gotchas:"]
        for g in list(gotchas)[:8]:
            wrapped = _wrap(str(g), 70)
            out.append(f"    - {wrapped[0]}")
            out.extend("      " + line for line in wrapped[1:])
        return out

    def _join_lines(self) -> list[str]:
        if not self.joins:
            return []
        out = ["", "  joins via:"]
        for join in self.joins:
            asof = f" AS-OF {join['as_of']}" if join.get("as_of") else ""
            grain = {
                "one": "one row per key",
                "many": "MANY rows per key",
            }.get(join["rows_per_key"], "grain unmeasured")
            out.append(f"    {join['key']} on {join['column']} \u2014 {grain}{asof}")
            fans = [w for w in join["with"] if w["rows_per_key"] == "many"]
            if fans:
                names = ", ".join(f"{w['dataset']}.{w['column']}" for w in fans[:4])
                more = f" +{len(fans) - 4}" if len(fans) > 4 else ""
                out.append(f"        fans out to: {names}{more}")
        if self.enrichments:
            by_column: dict[str, list[str]] = {}
            for item in self.enrichments:
                by_column.setdefault(item["reads"], []).append(item["target"])
            out += ["", "  enrich with (query(enrich=[...])):"]
            out += [f"    from {column}: {', '.join(targets)}" for column, targets in by_column.items()]
        return out

    def _schema_lines(self) -> list[str]:
        if not self.schemas:
            return []
        out = ["", f"  schema generations ({len(self.schemas)}), oldest first:"]
        for s in self.schemas[:12]:
            out.append(
                f"    {str(s.get('span', '')):<11} "
                f"{str(s.get('field_count', '?')):>4} cols  "
                f"{s.get('files', 0):>6,} files  "
                f"{s.get('schema_signature', '')[:10]}"
            )
            delta = []
            if s.get("added"):
                delta.append(f"+{len(s['added'])} {' '.join(s['added'][:5])}")
            if s.get("dropped"):
                delta.append(f"-{len(s['dropped'])} {' '.join(s['dropped'][:5])}")
            if delta:
                out.append(f"        {'; '.join(delta)}")
        if len(self.schemas) > 12:
            out.append(f"    ... and {len(self.schemas) - 12} more")
        return out

    def _children_lines(self) -> list[str]:
        if not self.children:
            return []
        out = ["", f"  contains ({len(self.children)}):"]
        for c in self.children[:20]:
            label = c.get("translated_name") or c.get("official_name") or ""
            out.append(f"    {c['code']:<24} {label[:44]}")
        if len(self.children) > 20:
            out.append(f"    ... and {len(self.children) - 20} more")
        return out

    def __repr__(self) -> str:  # pragma: no cover - presentation
        if self.kind == "overview" and self.documentation.get("map"):
            return str(self.documentation["map"])  # the whole map's overview (_compendium.overview)
        if self.kind == "link" and self.documentation.get("text"):
            return str(self.documentation["text"])
        out = self._identity_lines()
        out += self._definition_lines()
        out += self._coverage_lines()
        out += self._documentation_lines()
        out += self._join_lines()
        if self.evidence.get("observed_as"):
            out.append(f"  seen as: {', '.join(self.evidence['observed_as'][:8])}")
        out += self._schema_lines()
        out += self._children_lines()
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


def _refresh_curation(catalog_path: Path) -> None:
    """Bring the catalog's curated text up to the shipped curation before reading it."""
    if not Path(catalog_path).exists():
        return
    try:
        from .config import curation_root
        from .semantics.curation import curation_is_current, ensure_current

        reader = _Store(catalog_path, read_only=True)
        try:
            if curation_is_current(reader, curation_root()):
                return
        finally:
            reader.close()
        writer = _Store(catalog_path)
        try:
            ensure_current(writer, curation_root())
        finally:
            writer.close()
    except Exception:  # noqa: BLE001 - a locked catalog still answers, with what it has
        return


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
    _refresh_curation(cfg.catalog_path)
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
            return _overview(store, onto, cfg)

        found = onto.resolve(text)
        if found is None and _is_link(text):
            return _link(text, cfg)
        if found is None:
            near = onto.suggest(text)
            notes = [f"'{target}' does not resolve to a system, dataset or alias."]
            if near:
                notes.append("Did you mean: " + ", ".join(near) + "?")
            notes.append(f"search({target!r}) finds anything named so: columns, fields, products, links, codes; "
                         "info() with no argument lists everything held and doable.")
            return Info(
                kind="unknown",
                code=text,
                evidence={"suggestions": near},
                notes=notes,
            )
        kind, node = found
        if kind == "system":
            return _system(store, onto, node, cfg)
        return _dataset(store, onto, node, cfg)
    finally:
        store.close()


# ------------------------------------------------------------------ builders


def _is_link(name: str) -> bool:
    from .linkage.engine import load_links

    try:
        return name in load_links()
    except Exception:  # noqa: BLE001 - no links file is no link
        return False


def _run_current(cfg: Settings, name: str, run: dict[str, Any]) -> bool:
    """Whether ``link()`` would serve this stored run: written under the current spec and the current fingerprint (engine
    version, role tables, inherited links). A run that is not current is history; its numbers describe code or data that
    have changed, and a study that read them as the link's present yield was misled (2026-11-22)."""
    from .linkage import store

    try:
        return (run.get("spec_digest") == store._spec_digest(name)
                and run.get("fingerprint") == store._fingerprint_of(cfg, name, str(run.get("period") or "")))
    except Exception:  # noqa: BLE001 - a run that cannot be checked is not served as current
        return False


def _link(name: str, cfg: Settings) -> Info:
    """A declared record link as data: what it joins and how (keys, control, held-out validations, parameters, outcome),
    and every stored run of it, with its scope, verdict, false-match rate and how much it linked. A link is not a
    dataset: it is a measured relation between two, and how far its pairs can be trusted is part of what it is."""
    import json

    from .linkage.engine import load_links

    spec = load_links()[name]
    runs: list[dict[str, Any]] = []
    folder = Path(cfg.lake_dir) / "links" / name
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else ():
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        run = d.get("run") or {}
        rate = d.get("chance_percent") if d.get("chance_percent") is not None else d.get("estimated_fdr_percent")
        upper = d.get("chance_upper95_percent") if d.get("chance_upper95_percent") is not None else d.get("fdr_upper95_percent")
        horizons = [(h.get("days"), h.get("pairs"), h.get("control_pairs"), h.get("verdict")) for h in d.get("horizons") or []]
        runs.append({"current": _run_current(cfg, name, run),
            "method": run.get("method") or d.get("method"), "period": run.get("period"), "geography": run.get("geography"),
            "params": d.get("params"), "verdict": d.get("verdict"), "left": d.get("left_records"), "right": d.get("right_records"),
            "pairs": d.get("pairs"), "linked_share": d.get("linked_share"), "false_match_percent": rate,
            "false_match_upper95": upper, "horizons": horizons, "file": path.name,
        })
    keys = [{"pass": p.name, "keys": [f"{a} = {b}" for a, b in p.keys]} for p in spec.passes]
    validations = [v.name for v in spec.validations]
    lines = [f"link: {name} — {spec.left.dataset} → {spec.right.dataset}", ""]
    lines += ["  " + line for line in _wrap(spec.description, 76)]
    lines += ["", "  what one pair is: " + ("the same event in both datasets" if spec.same_event
                                              else "two events of one person"),
              f"  left: {spec.left.dataset}" + (f" where {spec.left.where}" if spec.left.where else "")
              + (f"; one record per {', '.join(spec.left.group)}" if spec.left.group else ""),
              f"  right: {spec.right.dataset}" + (f" where {spec.right.where}" if spec.right.where else "")
              + (f"; one record per {', '.join(spec.right.group)}" if spec.right.group else "")]
    if spec.params:
        modes = [f"{m} ({r})" for m, r in spec.params.roles.items()]
        also = ", ".join(f"{m}: {r}" for m, r in spec.params.partner.items())
        lines.append(f"  run per set of codes, match= {', '.join(modes)}"
                     + (f"; the codes also filter the other side ({also})" if also else ""))
    if spec.outcome:
        lines.append(f"  follows: {spec.outcome.origin} → {spec.outcome.event}" + (" (the first)" if spec.outcome.first else ""))
    lines += ["", "  passes (exact keys, in order; a pass whose control finds too many pairs is dropped):"]
    for k in keys:
        lines.append(f"    {k['pass']}")
        lines += [f"      {key}" for key in k["keys"]]
    lines += [f"  control: {spec.control_role} shifted by {spec.control_shift_days} days (its pairs are chance)",
              "  held out (fields no pass reads; true pairs agree):"] + [f"    {v}" for v in validations]
    stale = sum(1 for r in runs if not r["current"])
    lines += ["", (f"  stored runs ({len(runs)}" + (f"; {stale} stale" if stale else "") + "):") if runs
              else "  stored runs: none (link() computes and stores one)"]
    for r in runs[:40]:
        share = f"{100 * r['linked_share']:.1f}% linked" if isinstance(r["linked_share"], (int, float)) else ""
        rate = f", chance {r['false_match_percent']:.2f}%" if isinstance(r["false_match_percent"], (int, float)) else ""
        lines.append(f"    {r['method'] or '?':<13} {r['period'] or '':<22} {r['geography'] or '':<8} {r['verdict'] or '':<17} "
                     f"{r['pairs'] or 0:>9,} pairs of {r['left'] or 0:,} {share}{rate}"
                     + ("" if r["current"] else "  [stale: link() recomputes it]"))
        # which codes the run was for, and its horizons: sixteen runs of one spec could not be told apart (2026-11-22)
        params = r["params"] or {}
        if params.get("codes"):
            lines.append(f"      codes {', '.join(map(str, params['codes']))} (match {params.get('match') or 'principal'})")
        if r["horizons"]:
            lines.append("      within " + "; ".join(f"{d} days: {p:,} pairs ({c:,} by chance), {v}" for d, p, c, v in r["horizons"]
                                                     if d is not None and p is not None and c is not None))
    if len(runs) > 40:
        lines.append(f"    ... and {len(runs) - 40} more")
    lines += ["", f"  call: link({name!r}, period=..., geography=...{', codes=[...]' if spec.params else ''}); "
              "a run's pairs and report are kept under lake/links; build_entities() merges links into persons"]
    return Info(kind="link", code=name, identity={"what_it_is": spec.description},
                evidence={"passes": keys, "control": {"role": spec.control_role, "shift_days": spec.control_shift_days},
                          "validations": validations}, coverage={"runs": runs}, documentation={"text": chr(10).join(lines)})


def _map_rows(settings: Settings, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Rows of the home's map (`_compendium.current`, rebuilt when stale)."""
    import sqlite3

    from ._compendium import current

    con = sqlite3.connect(f"file:{current(settings=settings).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


def _overview(store: _Store, onto: Ontology, settings: Settings) -> Info:
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
    from ._compendium import overview

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
        documentation={"map": overview(settings=settings)},
    )


def _system(store: _Store, onto: Ontology, node: SystemNode, settings: Settings) -> Info:
    datasets = onto.datasets_of(node.code)
    # The counts come from the map (_compendium), computed once for every reader of them.
    mapped = {r["code"]: r for r in _map_rows(
        settings, "SELECT code, files, year_min, year_max, rows_held FROM datasets WHERE system = ?", (node.code,))}
    children = []
    for d in datasets:
        got = mapped.get(d.code, {})
        children.append(
            {
                "code": d.code,
                "official_name": d.official_name,
                "translated_name": d.translated_name,
                "files": got.get("files") or 0,
                "span": _span(got.get("year_min"), got.get("year_max")),
                "rows_held": got.get("rows_held") or 0,
                "status": d.status,
            }
        )
    children.sort(key=lambda c: -int(c["files"] or 0))
    total = sum(int(c["files"] or 0) for c in children)
    years = [v for r in mapped.values() for v in (r.get("year_min"), r.get("year_max")) if v]
    y0, y1 = (min(years), max(years)) if years else (None, None)

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
        coverage={"files": total, "span": _span(y0, y1), "datasets": len(datasets),
                  "rows_held": sum(int(c["rows_held"] or 0) for c in children)},
        children=children,
        notes=notes,
    )


def _enrichments(dataset: str) -> list[dict[str, Any]]:
    """The declared enrichment targets whose key column the dataset's roles name (``crosswalk.record_column``)."""
    from .crosswalk import record_column
    from .semantics.curation import declared

    out = []
    for target, body in declared("joins.yml", "enrichments").items():
        column = record_column(dataset, str(body["reads"]))
        if column:
            out.append({"target": str(target), "route": str(body["route"]), "reads": column})
    return out


def _dataset(store: _Store, onto: Ontology, node: DatasetNode, settings: Settings) -> Info:
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

    # Files, years and the columns described come from the map (_compendium), computed once for every reader: its
    # columns include those only the lake or an intake declaration knows (SRAG, SISAGUA), which FTP headers miss.
    mapped = next(iter(_map_rows(
        settings, "SELECT files, year_min, year_max, columns_total, columns_described, rows_held, year_min_held,"
                  " year_max_held, files_downloaded, months_downloaded FROM datasets WHERE code = ?", (node.code,))), {})
    if mapped:
        files, y0, y1 = int(mapped["files"] or 0), mapped["year_min"], mapped["year_max"]
    total_cols = int(mapped.get("columns_total") or 0)
    described = int(mapped.get("columns_described") or 0)

    # What one row IS, if it has been curated: the shipped declaration, the one `dataset_facts` returns.
    facts = dataset_facts(node.code)
    doc = {k: facts[k] for k in ("what_one_row_is", "unit_of_analysis", "known_biases", "gotchas", "use", "why_no_event_type")
           if facts.get(k)}

    questions = _open_questions_for(store, crawled_systems, signatures)

    # How the FILES are split, which is not the same as what the data contains.
    # SIM.DOFET has no per-state files, so uf= matches nothing and returns an
    # empty table that reads like "this state has no fetal deaths".
    try:
        axes = onto.axes_for(store.conn, node.code)
    except Exception:  # pragma: no cover - a locked or partial catalog
        axes = None
    # the axes above are read from the SOURCE files' names; `query` selects by the lake's partitions and publications.
    # A source published per state but landed under one national partition (the intake's ANS files, 2026-11-22) is
    # filterable by state at the source and not through `geography=`: say so, rather than promise a filter that raises
    try:
        held_ufs = {str(r[0]) for r in store.conn.execute(
            "SELECT DISTINCT uf FROM lake_partitions WHERE family_id LIKE ?",
            (node.code.replace(".", "_").replace("-", "_") + "_%",)).fetchall()}
    except Exception:  # pragma: no cover - a locked or partial catalog
        held_ufs = set()
    lake_national_only = bool(axes and "uf" in axes.names and held_ufs == {"BR"})

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
            "rows_held": mapped.get("rows_held") or 0,
            "span_held": _span(mapped.get("year_min_held"), mapped.get("year_max_held")),
            "files_downloaded": mapped.get("files_downloaded") or 0,
            "months_downloaded": mapped.get("months_downloaded"),
            "axes": ([n for n in axes.names if n != "uf"] if lake_national_only else axes.names) if axes else [],
            "lake_national_only": lake_national_only,
            "axes_detail": axes.as_dict() if axes else None,
        },
        enrichments=_enrichments(node.code),
        joins=[
            {
                "key": key.name,
                "column": key.column_for(node.code),
                "as_of": key.as_of,
                "rows_per_key": next(
                    (m.rows_per_key for m in key.members if m.dataset == node.code),
                    "unmeasured",
                ),
                "with": [
                    {"dataset": m.dataset, "column": m.column,
                     "rows_per_key": m.rows_per_key}
                    for m in key.members if m.dataset != node.code
                ],
                "caveats": list(key.caveats),
            }
            for key in onto.keys_of(node.code)
        ],
        schemas=schemas,
        documentation={
            **doc,
            "columns_total": total_cols,
            "columns_described": described,
            "open_questions": questions,
        },
        notes=notes,
    )


def dataset_facts(dataset: str) -> dict[str, Any]:
    """What the curation documents of ``dataset``, with where each statement comes from: read-only and offline.

    * ``what_one_row_is``, ``unit_of_analysis``, ``known_biases``, ``gotchas``: what a row is and what misleads,
      asserted by the project (``asserted_by``, ``curation_file``), from measurements and documents named in the text;
    * ``use`` (one of ``semantics.event_types.USES``: ``event_source`` when the rows become events, else ``context``,
      ``denominator``, ``support``, ``reference`` or ``not_an_event_source``; None: not yet declared) and, for a dataset
      with no event type, ``why_no_event_type``: the reason, with its evidence (ADR-0195);
    * ``implied_sex``: the sex the records imply where the file holds no sex column (``sex`` 1 or 2, ``evidence``), else None;
    * ``time`` and ``geography``: the axes a row can be placed on (``default``, and per axis the ``fields`` and their
      ``encoding``), and ``publication``: how the server files the dataset (``temporal_resolution``, ``physical_geography``);
    * ``events``: what a row becomes when counted (the event types: ``status`` rule with its evidence, ``consolidation``,
      ``note``), each with ``source_notes``: the source's own definition, validity, finality rule, acknowledged errors
      and limitations, with the document (``source``) that states them;
    * ``documents``: every document the ``source_notes`` cite.

    Declared nothing: ``documented`` is False and the statements are empty (not a statement that nothing is
    to be said). It reads the shipped curation, not a catalog: ``info`` shows the same statements.
    """
    from .semantics.event_types import dataset_declaration, dataset_implied_sex, dataset_use, event_types

    declared = dataset_declaration(dataset)
    file, key, body = declared if declared else (None, None, {})
    try:
        events = event_types(dataset)
    except KeyError:
        events = []
    axes = body.get("semantic_axes") or {}
    gotchas = body.get("gotchas") or []

    def clean(text: Any) -> str | None:
        return " ".join(str(text).split()) if text else None

    return {
        "dataset": dataset, "key": key, "documented": bool(declared and (body.get("what_one_row_is") or events)),
        "what_one_row_is": clean(body.get("what_one_row_is")),
        "unit_of_analysis": clean(body.get("unit_of_analysis")),
        "known_biases": clean(body.get("known_biases")),
        "gotchas": [clean(g) for g in ([gotchas] if isinstance(gotchas, str) else gotchas)],
        **dataset_use(dataset), "implied_sex": dataset_implied_sex(dataset),
        "time": {"default": axes.get("default_time"), "axes": axes.get("time") or {}},
        "geography": {"default": axes.get("default_geography"), "axes": axes.get("geography") or {}},
        "publication": {k: v for k, v in (body.get("source_publication") or {}).items()
                        if k in ("temporal_resolution", "physical_geography")},
        "events": events,
        "documents": sorted({e["source_notes"]["source"] for e in events if e.get("source_notes")}),
        "asserted_by": body.get("asserted_by"), "curation_file": file,
    }


def _open_questions_for(
    store: _Store, systems: set[str], signatures: set[str]
) -> list[dict[str, Any]]:
    """Unresolved questions that bear on this dataset.

    "What is not known says so" is the rule the whole project runs on, and
    ``info()`` is the front door — so a dataset with an unsettled question about
    one of its codelists should say so when asked about, not only when someone
    thinks to run ``pegasus-data questions``.

    Questions are keyed by artefact rather than by dataset, so the join goes
    through the codelists this dataset's columns actually bind to. That is a
    real link, not a text match: a mixed-width reference table is a problem for
    exactly the datasets whose columns decode against it.
    """
    if not systems or not signatures:
        return []
    sig_marks = ",".join("?" for _ in signatures)
    cols = {
        str(r["field_name"])
        for r in store.query(
            f"SELECT DISTINCT field_name FROM schema_presence "
            f"WHERE schema_signature IN ({sig_marks})",
            tuple(signatures),
        )
    }
    if not cols:
        return []

    sys_marks = ",".join("?" for _ in systems)
    codelists = {
        str(r["codelist"])
        for r in store.query(
            f"SELECT DISTINCT field_name, codelist FROM field_codelists "
            f"WHERE system IN ({sys_marks})",
            tuple(systems),
        )
        if str(r["field_name"]) in cols
    }
    if not codelists:
        return []

    out: list[dict[str, Any]] = []
    for row in store.query(
        "SELECT key, area, question, blocking FROM open_questions "
        "WHERE status = 'open' ORDER BY key"
    ):
        key = str(row["key"])
        tail = key.rsplit(":", 1)[-1] if ":" in key else ""
        if tail and tail in codelists:
            out.append(
                {
                    "key": key,
                    "area": row["area"],
                    "question": row["question"],
                    "blocking": row["blocking"],
                }
            )
    return out


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

    clause, strata_clause, params = "", "", [name]
    if systems:
        marks = ",".join("?" for _ in systems)
        clause, strata_clause = f" AND system IN ({marks})", f" AND s.system IN ({marks})"
        params += systems

    docs = store.query(
        f"SELECT system, field_name, official_name, translated_name, description, "
        f"source, reasoning FROM variable_docs WHERE field_name = ?{clause} ORDER BY system, source",
        tuple(params),
    )
    if not docs:
        docs = store.query(
            f"SELECT system, field_name, NULL AS official_name, NULL AS translated_name, "
            f"description, source, NULL AS reasoning FROM field_documentation "
            f"WHERE field_name = ?{clause} ORDER BY system, source",
            tuple(params),
        )

    if not docs:
        return Info(
            kind="variable",
            code=name,
            notes=[f"No documentation recorded for {name}" + (f" in {target}" if target else "")],
        )

    # the datasets that carry the field, by the system that files them, within the scope asked
    where = store.query(
        f"SELECT DISTINCT s.system, s.series FROM schema_presence sp "
        f"JOIN strata s ON s.schema_signature = sp.schema_signature "
        f"WHERE sp.field_name = ?{strata_clause} ORDER BY s.system, s.series",
        tuple(params),
    )
    datasets_of: dict[str, set[str]] = {}
    for r in where:
        bound = onto.bind(str(r["system"]), str(r["series"])).dataset
        if bound:
            datasets_of.setdefault(str(r["system"]), set()).add(bound)

    documented_by = list(dict.fromkeys(str(d["system"]) for d in docs))
    if len(documented_by) > 1:
        # no system asked and several document the field: each system's own definition, none preferred
        definitions = []
        for system in documented_by:
            d = next(d for d in docs if str(d["system"]) == system)
            definitions.append({
                "system": system, "official_name": d["official_name"], "translated_name": d["translated_name"],
                "what_it_is": d["description"], "source": d["source"], "reasoning": d["reasoning"],
                "datasets": sorted(datasets_of.get(system, ())),
            })
        example = next((d["datasets"][0] for d in definitions if d["datasets"]), documented_by[0])
        return Info(
            kind="variable",
            code=name,
            evidence={"scope": getattr(scope, "code", None)},
            definitions=definitions,
            notes=[f"{name} is documented by {len(documented_by)} systems ({', '.join(documented_by)}), each with its own "
                   f"definition and codes: they are not one variable. Name a system or dataset (info('{example}', "
                   f"field_name='{name}')) for one."],
        )

    first = docs[0]
    datasets = sorted(set().union(*datasets_of.values())) if datasets_of else []
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
            # sqlite3.Row again: `in first` would test the values.
            "reasoning": first["reasoning"] if "reasoning" in first.keys() else None,  # noqa: SIM118
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
