"""The curated variable dictionary: the door for human judgement (§4).

Three times this design created a slot for a person to write into and then left
no way to reach it. ``SOURCE_AUTHORITY['manual'] = 0`` outranked every extracted
source, and nothing could produce a manual entry. ``'layout_doc'`` was declared
authoritative before anything emitted one. The prefix→system map deliberately
holds its first answer against contradicting evidence — correctly, because a
reorganisation and a shared prefix are indistinguishable from one crawl — and
offered no way to adjudicate. All three are the same missing thing.

The split between here and SQLite is by *provenance*, not by size. The extracted
dictionary is machine output: millions of code→label rows, regenerable from the
FTP tree, and nobody should hand-edit it. What a variable **means** is the
opposite — a few thousand assertions, each made by a person or read out of a
document, none of it recomputable. Assertions belong in version control where a
diff shows who changed an interpretation and when. So ``curation/*.yml`` is the
source of truth for meaning, this module loads it, and the catalog holds the
result for querying alongside everything else.

Entries carry the rung of evidence that produced them (§4.5). An inferred
description is useful; an inferred description presented as documented is
precisely the failure this module exists to prevent, so ``source='inferred'``
requires the reasoning to be written out and refuses to load without it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..catalog.store import Catalog, utcnow

#: Rungs of evidence, best first (§4.5). Mirrors ``SOURCE_AUTHORITY`` but names
#: the *documentation* sources rather than the value-label ones.
DOC_SOURCES: tuple[str, ...] = ("manual", "layout_doc", "def", "web", "inferred")

#: A source that asserts rather than reports has to say who is asserting.
_NEEDS_AUTHOR = {"manual", "inferred"}

_CODE_SYSTEMS = {"external", "internal", "none"}


class CurationError(ValueError):
    """A curation file cannot be loaded. Raised rather than partially applied.

    Loading half a file would leave the catalog in a state no file describes,
    which is the one thing version-controlled curation is supposed to rule out.
    """


@dataclass(slots=True)
class VariableDoc:
    system: str
    field_name: str
    official_name: str | None = None
    translated_name: str | None = None
    description: str | None = None
    code_system: str | None = None
    codelist: str | None = None
    multi_valued: bool = False
    token_rule: dict[str, Any] | None = None
    depends_on: list[str] = field(default_factory=list)
    modifies: str | None = None
    derived: list[dict[str, Any]] = field(default_factory=list)
    notes: str | None = None
    source: str = "manual"
    source_ref: str | None = None
    asserted_by: str | None = None
    reasoning: str | None = None

    def as_row(self) -> tuple[object, ...]:
        return (
            self.system, self.field_name, self.official_name, self.translated_name,
            self.description, self.code_system, self.codelist, int(self.multi_valued),
            json.dumps(self.token_rule) if self.token_rule else None,
            json.dumps(self.depends_on) if self.depends_on else None,
            self.modifies,
            json.dumps(self.derived) if self.derived else None,
            self.notes, self.source, self.source_ref, self.asserted_by, utcnow(),
            self.reasoning,
        )


@dataclass(slots=True)
class DatasetDoc:
    dataset_id: str
    system: str | None = None
    series: str | None = None
    what_one_row_is: str | None = None
    unit_of_analysis: str | None = None
    known_biases: str | None = None
    gotchas: list[str] = field(default_factory=list)
    source: str = "manual"
    source_ref: str | None = None
    asserted_by: str | None = None

    def as_row(self) -> tuple[object, ...]:
        return (
            self.dataset_id, self.system, self.series, self.what_one_row_is,
            self.unit_of_analysis, self.known_biases,
            json.dumps(self.gotchas) if self.gotchas else None,
            self.source, self.source_ref, self.asserted_by, utcnow(),
        )


# ------------------------------------------------------------------- parsing


def _require_yaml() -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise CurationError(
            "curation files are YAML; install pyyaml (pip install pyyaml)"
        ) from exc
    return yaml


def _clean(value: object) -> str | None:
    """Collapse YAML block scalars to single-line prose."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def parse_variable_file(path: Path, data: dict[str, Any]) -> list[VariableDoc]:
    """One file per (system, series): a ``system:`` key and a ``variables:`` map."""
    system = data.get("system")
    if not system:
        raise CurationError(f"{path.name}: missing top-level 'system:'")
    variables = data.get("variables") or {}
    if not isinstance(variables, dict):
        raise CurationError(f"{path.name}: 'variables:' must be a mapping of NAME -> fields")

    default_source = data.get("source", "manual")
    default_ref = data.get("source_ref")
    default_author = data.get("asserted_by")

    out: list[VariableDoc] = []
    for name, body in variables.items():
        if body is None:
            body = {}
        if not isinstance(body, dict):
            raise CurationError(f"{path.name}: {name}: expected a mapping, got {type(body).__name__}")
        source = body.get("source", default_source)
        if source not in DOC_SOURCES:
            raise CurationError(
                f"{path.name}: {name}: source '{source}' is not one of {list(DOC_SOURCES)}"
            )
        code_system = body.get("code_system")
        if code_system is not None and code_system not in _CODE_SYSTEMS:
            raise CurationError(
                f"{path.name}: {name}: code_system '{code_system}' is not one of "
                f"{sorted(_CODE_SYSTEMS)}"
            )
        author = body.get("asserted_by", default_author)
        reasoning = _clean(body.get("reasoning"))
        if source in _NEEDS_AUTHOR and not author:
            raise CurationError(
                f"{path.name}: {name}: source '{source}' asserts rather than reports, "
                "so it needs 'asserted_by'"
            )
        if source == "inferred" and not reasoning:
            raise CurationError(
                f"{path.name}: {name}: an inferred meaning must carry 'reasoning'. "
                "An inferred description presented as documented is the failure this "
                "module exists to prevent."
            )
        token_rule = body.get("token_rule")
        if body.get("multi_valued") and not token_rule:
            raise CurationError(
                f"{path.name}: {name}: multi_valued needs a token_rule saying how to split "
                "(e.g. {width: 4} or {delimiter: ';'})"
            )
        if token_rule is not None and (
            not isinstance(token_rule, dict) or not ({"width", "delimiter"} & set(token_rule))
        ):
            raise CurationError(
                f"{path.name}: {name}: token_rule must be a mapping with 'width' or 'delimiter'"
            )
        depends_on = body.get("depends_on") or []
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        out.append(
            VariableDoc(
                system=str(system).upper(),
                field_name=str(name).upper(),
                official_name=_clean(body.get("official_name")),
                translated_name=_clean(body.get("translated_name")),
                description=_clean(body.get("description")),
                code_system=code_system,
                codelist=(str(body["codelist"]).upper() if body.get("codelist") else None),
                multi_valued=bool(body.get("multi_valued", False)),
                token_rule=token_rule,
                depends_on=[str(d).upper() for d in depends_on],
                modifies=(str(body["modifies"]).upper() if body.get("modifies") else None),
                derived=list(body.get("derived") or []),
                notes=_clean(body.get("notes")),
                source=source,
                source_ref=body.get("source_ref", default_ref),
                asserted_by=author,
                reasoning=reasoning,
            )
        )
    return out


def parse_datasets_file(path: Path, data: dict[str, Any]) -> list[DatasetDoc]:
    datasets = data.get("datasets") or {}
    out: list[DatasetDoc] = []
    for dataset_id, body in datasets.items():
        body = body or {}
        gotchas = body.get("gotchas") or []
        if isinstance(gotchas, str):
            gotchas = [gotchas]
        out.append(
            DatasetDoc(
                dataset_id=str(dataset_id).upper(),
                system=body.get("system"),
                series=body.get("series"),
                what_one_row_is=_clean(body.get("what_one_row_is")),
                unit_of_analysis=_clean(body.get("unit_of_analysis")),
                known_biases=_clean(body.get("known_biases")),
                gotchas=[_clean(g) or "" for g in gotchas],
                source=body.get("source", "manual"),
                source_ref=body.get("source_ref"),
                asserted_by=body.get("asserted_by"),
            )
        )
    return out


def iter_curation_files(root: Path) -> Iterator[Path]:
    for pattern in ("variables/*.yml", "variables/*.yaml", "*.yml", "*.yaml"):
        yield from sorted(root.glob(pattern))


# -------------------------------------------------------------------- loading


def load_curation(catalog: Catalog, root: Path) -> dict[str, object]:
    """Seed the catalog from ``curation/``. Replaces what the files own.

    Curated rows are *replaced* rather than merged, for the same reason every
    other derived table is: an entry deleted from the YAML has to disappear from
    the catalog, or the file stops being the source of truth it is supposed to be.
    Only rows whose source is one of the curated rungs are touched — anything the
    harvesters wrote is left alone.
    """
    yaml = _require_yaml()
    if not root.is_dir():
        return {"curation_root": str(root), "files": 0, "variables": 0, "datasets": 0}

    variables: list[VariableDoc] = []
    datasets: list[DatasetDoc] = []
    systems_map: dict[str, str] = {}
    files = 0
    for path in iter_curation_files(root):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise CurationError(f"{path}: {exc}") from exc
        if not isinstance(data, dict):
            raise CurationError(f"{path}: expected a mapping at the top level")
        files += 1
        if "variables" in data:
            variables.extend(parse_variable_file(path, data))
        if "datasets" in data:
            datasets.extend(parse_datasets_file(path, data))
        if "prefix_systems" in data:
            for prefix, system in (data.get("prefix_systems") or {}).items():
                systems_map[str(prefix).upper()] = str(system).upper()

    _replace_variable_docs(catalog, variables)
    _replace_dataset_docs(catalog, datasets)
    bound = _seed_field_codelists(catalog, variables)
    overridden = _apply_prefix_overrides(catalog, systems_map)

    by_source: dict[str, int] = {}
    for v in variables:
        by_source[v.source] = by_source.get(v.source, 0) + 1
    return {
        "curation_root": str(root),
        "files": files,
        "variables": len(variables),
        "datasets": len(datasets),
        "codelists_bound": bound,
        "prefix_overrides": overridden,
        "by_source": by_source,
    }


def _replace_variable_docs(catalog: Catalog, docs: Sequence[VariableDoc]) -> None:
    keep = {(d.system, d.field_name) for d in docs}
    stale = [
        (r["system"], r["field_name"])
        for r in catalog.query("SELECT system, field_name FROM variable_docs")
        if (r["system"], r["field_name"]) not in keep
    ]
    if stale:
        catalog.executemany(
            "DELETE FROM variable_docs WHERE system = ? AND field_name = ?", stale
        )
    catalog.executemany(
        """
        INSERT INTO variable_docs (system, field_name, official_name, translated_name,
            description, code_system, codelist, multi_valued, token_rule, depends_on,
            modifies, derived, notes, source, source_ref, asserted_by, asserted_at, reasoning)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(system, field_name) DO UPDATE SET
            official_name=excluded.official_name, translated_name=excluded.translated_name,
            description=excluded.description, code_system=excluded.code_system,
            codelist=excluded.codelist, multi_valued=excluded.multi_valued,
            token_rule=excluded.token_rule, depends_on=excluded.depends_on,
            modifies=excluded.modifies, derived=excluded.derived, notes=excluded.notes,
            source=excluded.source, source_ref=excluded.source_ref,
            asserted_by=excluded.asserted_by, asserted_at=excluded.asserted_at,
            reasoning=excluded.reasoning
        """,
        [d.as_row() for d in docs],
    )


def _replace_dataset_docs(catalog: Catalog, docs: Sequence[DatasetDoc]) -> None:
    keep = {d.dataset_id for d in docs}
    stale = [
        (r["dataset_id"],)
        for r in catalog.query("SELECT dataset_id FROM dataset_docs")
        if r["dataset_id"] not in keep
    ]
    if stale:
        catalog.executemany("DELETE FROM dataset_docs WHERE dataset_id = ?", stale)
    catalog.executemany(
        """
        INSERT INTO dataset_docs (dataset_id, system, series, what_one_row_is,
            unit_of_analysis, known_biases, gotchas, source, source_ref, asserted_by, asserted_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(dataset_id) DO UPDATE SET
            system=excluded.system, series=excluded.series,
            what_one_row_is=excluded.what_one_row_is,
            unit_of_analysis=excluded.unit_of_analysis, known_biases=excluded.known_biases,
            gotchas=excluded.gotchas, source=excluded.source, source_ref=excluded.source_ref,
            asserted_by=excluded.asserted_by, asserted_at=excluded.asserted_at
        """,
        [d.as_row() for d in docs],
    )


def _seed_field_codelists(catalog: Catalog, docs: Sequence[VariableDoc]) -> int:
    """A curated ``codelist:`` is a binding at the highest authority.

    This is the point of ``SOURCE_AUTHORITY['manual'] = 0``: a person who has read
    the layout document and decided that ``SP_PF_CBO`` draws on CBO-2002 outranks
    every heuristic that guessed otherwise.
    """
    catalog.execute("DELETE FROM field_codelists WHERE source = 'manual'")
    rows = [
        (d.system, "", d.field_name, d.codelist, "manual",
         d.source_ref or f"curation:{d.asserted_by or 'unattributed'}", 1.0)
        for d in docs
        if d.codelist
    ]
    return catalog.executemany(
        """
        INSERT INTO field_codelists (system, family_id, field_name, codelist, source,
                                     source_ref, confidence)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(system, family_id, field_name, codelist) DO UPDATE SET
            source=excluded.source, source_ref=excluded.source_ref,
            confidence=excluded.confidence
        """,
        rows,
    )


def _apply_prefix_overrides(catalog: Catalog, mapping: dict[str, str]) -> int:
    """Manual overrides for the learned prefix map, at full agreement.

    The learned map holds its answer on purpose. A file that names the answer is
    how a person overrides it durably — as opposed to ``prefix-adjudicate``, which
    settles one contradiction in place and leaves no record in version control.
    """
    if not mapping:
        return 0
    return catalog.executemany(
        """
        INSERT INTO prefix_systems (series_prefix, system, file_count, agreement, learned_at)
        VALUES (?,?,0,1.0,?)
        ON CONFLICT(series_prefix) DO UPDATE SET
            system=excluded.system, agreement=1.0, learned_at=excluded.learned_at
        """,
        [(prefix, system, utcnow()) for prefix, system in mapping.items()],
    )


# ------------------------------------------------------------------- coverage


def coverage_by_rung(catalog: Catalog) -> list[dict[str, object]]:
    """Variables documented per system, by which rung of evidence supplied them.

    The denominator is fields the catalog has actually observed, not fields some
    document mentions — a layout PDF describing columns nobody has seen is not
    coverage of anything.
    """
    observed = {
        (str(r["system"]), str(r["field_name"]))
        for r in catalog.query(
            """
            SELECT DISTINCT f.system, vp.field_name
              FROM variable_profiles vp
              JOIN families f ON f.family_id = vp.family_id
            """
        )
    }
    curated: dict[tuple[str, str], str] = {
        (str(r["system"]), str(r["field_name"])): str(r["source"])
        for r in catalog.query("SELECT system, field_name, source FROM variable_docs")
    }
    harvested: dict[tuple[str, str], str] = {}
    for r in catalog.query(
        "SELECT system, field_name, source FROM field_documentation WHERE system IS NOT NULL"
    ):
        harvested.setdefault((str(r["system"]), str(r["field_name"])), str(r["source"]))
    # Rung 2: a .DEF display name is a weaker answer than a record layout — it
    # names a TabNet tabulation axis rather than the column — but it is a name,
    # and counting it as nothing overstates how much is undocumented.
    for r in catalog.query(
        "SELECT DISTINCT system, field_name FROM def_variables WHERE system IS NOT NULL"
    ):
        harvested.setdefault((str(r["system"]), str(r["field_name"])), "def")

    systems = sorted({s for s, _ in observed})
    out: list[dict[str, object]] = []
    for system in systems:
        fields = {f for s, f in observed if s == system}
        counts: dict[str, int] = {}
        documented = 0
        for f in fields:
            rung = curated.get((system, f)) or harvested.get((system, f))
            if rung:
                documented += 1
                counts[rung] = counts.get(rung, 0) + 1
        out.append(
            {
                "system": system,
                "observed_fields": len(fields),
                "documented": documented,
                "coverage": round(documented / len(fields), 3) if fields else 0.0,
                # Every rung, always, zero-filled. A table whose columns depend on
                # which rungs the first row happened to use hides the rest.
                **{f"via_{rung}": counts.get(rung, 0) for rung in DOC_SOURCES},
            }
        )
    return sorted(out, key=lambda r: -int(r["observed_fields"]))


def load_variable_docs(catalog: Catalog, system: str | None = None) -> dict[str, VariableDoc]:
    """Curated docs keyed by field name, for the renderer and the doc generator."""
    clause, params = "", []
    if system:
        clause = " WHERE system = ?"
        params = [system.upper()]
    out: dict[str, VariableDoc] = {}
    for r in catalog.query(f"SELECT * FROM variable_docs{clause}", params):
        out[str(r["field_name"])] = VariableDoc(
            system=str(r["system"]),
            field_name=str(r["field_name"]),
            official_name=r["official_name"],
            translated_name=r["translated_name"],
            description=r["description"],
            code_system=r["code_system"],
            codelist=r["codelist"],
            multi_valued=bool(r["multi_valued"]),
            token_rule=json.loads(r["token_rule"]) if r["token_rule"] else None,
            depends_on=json.loads(r["depends_on"]) if r["depends_on"] else [],
            modifies=r["modifies"],
            derived=json.loads(r["derived"]) if r["derived"] else [],
            notes=r["notes"],
            source=str(r["source"]),
            source_ref=r["source_ref"],
            asserted_by=r["asserted_by"],
            reasoning=r["reasoning"],
        )
    return out
