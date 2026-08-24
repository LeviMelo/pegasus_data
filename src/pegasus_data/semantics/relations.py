"""Typed semantic relations and the maintainer adjudication queue."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..catalog.store import Catalog, _semantic_relation_id, utcnow
from ..ontology import CURATION, _read_yaml


class RelationType(StrEnum):
    LABEL_OF = "label_of"
    ROLLUP_TO = "rollup_to"
    ATTRIBUTE_OF = "attribute_of"
    CROSSWALK_TO = "crosswalk_to"


@dataclass(frozen=True, slots=True)
class SemanticRelation:
    system: str
    dataset: str
    field_name: str
    relation_type: RelationType
    target_type: str
    target_name: str
    artifact: str
    source_namespace: str | None = None
    target_namespace: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    status: str = "adjudicated"
    evidence: str | None = None
    authority: str = "curated"


def load_relations(root: Path | None = None) -> tuple[SemanticRelation, ...]:
    data = _read_yaml((root or CURATION) / "joins.yml")
    out: list[SemanticRelation] = []
    for body in data.get("relations") or ():
        out.append(
            SemanticRelation(
                system=str(body.get("system", "*")).upper(),
                dataset=str(body.get("dataset", "*")).upper(),
                field_name=str(body.get("field", "")).upper(),
                relation_type=RelationType(str(body.get("relation"))),
                target_type=str(body.get("target_type", "")),
                target_name=str(body.get("target_name", "")),
                artifact=str(body.get("artifact", "")),
                source_namespace=body.get("source_namespace"),
                target_namespace=body.get("target_namespace"),
                valid_from=body.get("valid_from"),
                valid_to=body.get("valid_to"),
                status=str(body.get("status", "adjudicated")),
                evidence=body.get("evidence"),
            )
        )
    return tuple(out)


def relations_for(
    system: str,
    dataset: str,
    field: str,
    *,
    relation_type: RelationType | str | None = None,
    catalog: Catalog | None = None,
    vintage: int | str | None = None,
) -> list[SemanticRelation]:
    """Resolve shipped declarations plus local reviewed overrides.

    Catalog decisions win on the relation identity they share with compiled
    curation. Explicit legacy ``variable_docs.codelist`` rows are exposed as a
    migration bridge to ``label_of``; heuristic/ranked bindings are not.
    """
    wanted = str(relation_type) if relation_type is not None else None
    candidates: list[tuple[int, SemanticRelation]] = [
        (1, item) for item in load_relations()
    ]
    if catalog is not None:
        try:
            for row in catalog.query(
                "SELECT * FROM semantic_relations WHERE status='adjudicated'"
            ):
                item = _relation_from_row(row)
                candidates.append((2 if item.authority == "local" else 1, item))
            for row in catalog.query(
                "SELECT system, field_name, codelist FROM variable_docs "
                "WHERE codelist IS NOT NULL AND codelist<>'' "
                "AND code_system IN ('internal','external')"
            ):
                item = SemanticRelation(
                    system=str(row["system"] or "*").upper(),
                    dataset="*",
                    field_name=str(row["field_name"]).upper(),
                    relation_type=RelationType.LABEL_OF,
                    target_type="coded_identity",
                    target_name="",
                    artifact=str(row["codelist"]),
                    evidence="explicit curated variable codelist (migration bridge)",
                )
                candidates.append((0, item))
        except Exception:  # pragma: no cover - old/read-only partial catalogs
            pass

    requested_vintage = int(vintage) if vintage is not None else None

    def applies(item: SemanticRelation) -> bool:
        if requested_vintage is None:
            return True
        lower = int(item.valid_from) if item.valid_from else 0
        upper = int(item.valid_to) if item.valid_to else 999912
        return lower <= requested_vintage <= upper

    matching = [
        (origin, item)
        for origin, item in candidates
        if item.system in {"*", system.upper()}
        and (
            item.dataset in {"*", dataset.upper()}
            or item.dataset.rpartition(".")[2]
            == dataset.upper().rpartition(".")[2]
        )
        and item.field_name == field.upper()
        and (wanted is None or item.relation_type.value == wanted)
        and item.status == "adjudicated"
        and applies(item)
    ]

    # One semantic target is one override slot. Origin precedence is evaluated
    # after temporal applicability so a bounded local decision overrides shipped
    # curation only inside the period it actually adjudicates.
    grouped: dict[tuple[str, str], list[tuple[int, SemanticRelation]]] = {}
    for origin, item in matching:
        grouped.setdefault(
            (item.relation_type.value, item.target_name), []
        ).append((origin, item))

    resolved: list[SemanticRelation] = []
    for values in grouped.values():
        max_origin = max(origin for origin, _item in values)
        values = [value for value in values if value[0] == max_origin]
        max_dataset = max(int(item.dataset != "*") for _origin, item in values)
        values = [
            value for value in values if int(value[1].dataset != "*") == max_dataset
        ]
        max_system = max(int(item.system != "*") for _origin, item in values)
        values = [
            value for value in values if int(value[1].system != "*") == max_system
        ]
        unique: dict[
            tuple[str, str | None, str | None], SemanticRelation
        ] = {}
        for _origin, item in values:
            unique[(item.artifact, item.valid_from, item.valid_to)] = item
        resolved.extend(unique.values())
    return sorted(
        resolved,
        key=lambda item: (
            item.relation_type.value,
            item.target_name,
            item.valid_from or "",
            item.valid_to or "",
            item.artifact,
        ),
    )


def _relation_from_row(row: Any) -> SemanticRelation:
    return SemanticRelation(
        system=str(row["system"]).upper(),
        dataset=str(row["dataset"] or "*").upper(),
        field_name=str(row["field_name"]).upper(),
        relation_type=RelationType(str(row["relation_type"])),
        target_type=str(row["target_type"]),
        target_name=str(row["target_name"] or ""),
        artifact=str(row["artifact"]),
        source_namespace=row["source_namespace"],
        target_namespace=row["target_namespace"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        status=str(row["status"]),
        evidence=row["evidence"],
        authority=str(row["authority"] or "local"),
    )


def _relation_identity(item: SemanticRelation, authority: str) -> str:
    values = asdict(item)
    values["relation_type"] = item.relation_type.value
    values["authority"] = authority
    return _semantic_relation_id(values)


def _window(item: SemanticRelation) -> tuple[int, int]:
    def boundary(value: str | None, default: int) -> int:
        if value is None or value == "":
            return default
        text = str(value)
        if len(text) != 6 or not text.isdigit() or not 1 <= int(text[-2:]) <= 12:
            raise ValueError(f"invalid semantic relation validity boundary {value!r}")
        return int(text)

    lo = boundary(item.valid_from, 0)
    hi = boundary(item.valid_to, 999912)
    if lo > hi:
        raise ValueError(
            f"semantic relation validity starts after it ends: {item.valid_from}..{item.valid_to}"
        )
    return lo, hi


def _validate_no_overlap(conn: Any, item: SemanticRelation, authority: str) -> None:
    """Reject competing assertions in one authority/semantic/temporal slot."""
    relation_id = _relation_identity(item, authority)
    lo, hi = _window(item)
    rows = conn.execute(
        "SELECT * FROM semantic_relations WHERE authority=? AND system=? AND dataset=? "
        "AND field_name=? AND relation_type=? AND target_type=? AND target_name=? "
        "AND relation_id<>?",
        (
            authority, item.system, item.dataset, item.field_name,
            item.relation_type.value, item.target_type, item.target_name, relation_id,
        ),
    )
    for row in rows:
        other = _relation_from_row(row)
        other_lo, other_hi = _window(other)
        if lo <= other_hi and other_lo <= hi:
            raise ValueError(
                "overlapping temporal relation assertions for "
                f"{item.system}.{item.dataset}.{item.field_name} "
                f"{item.relation_type.value}:{item.target_name}: "
                f"{other.valid_from or '*'}..{other.valid_to or '*'} overlaps "
                f"{item.valid_from or '*'}..{item.valid_to or '*'}"
            )


def _store_relation(conn: Any, item: SemanticRelation, *, authority: str) -> None:
    _validate_no_overlap(conn, item, authority)
    conn.execute(
        """
        INSERT INTO semantic_relations
          (relation_id, authority, system, dataset, field_name, relation_type,
           target_type, target_name, artifact, source_namespace, target_namespace,
           valid_from, valid_to, status, evidence)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(relation_id) DO UPDATE SET artifact=excluded.artifact,
          source_namespace=excluded.source_namespace,
          target_namespace=excluded.target_namespace, status=excluded.status,
          evidence=excluded.evidence
        """,
        (
            _relation_identity(item, authority), authority, item.system, item.dataset,
            item.field_name, item.relation_type.value, item.target_type, item.target_name,
            item.artifact, item.source_namespace, item.target_namespace, item.valid_from,
            item.valid_to, item.status, item.evidence,
        ),
    )


def seed_relations(catalog: Catalog, root: Path | None = None) -> int:
    """Synchronize refreshable curated compiler output, preserving local truth."""
    relations = load_relations(root)
    with catalog.write() as conn:
        # Curated rows are a compiled snapshot, not durable user decisions. A
        # boundary or artifact change must replace the prior snapshot rather
        # than overlap it forever. The surrounding transaction restores the old
        # snapshot if the replacement is internally contradictory.
        conn.execute("DELETE FROM semantic_relations WHERE authority='curated'")
        for relation in relations:
            _store_relation(conn, relation, authority="curated")
    return len(relations)


def ensure_adjudication_item(
    catalog: Catalog,
    *,
    kind: str,
    system: str,
    dataset: str = "",
    family_id: str = "",
    field: str,
    candidates: list[str],
    reason: str,
    observed_summary: dict[str, Any] | None = None,
) -> str:
    identity = json.dumps([kind, system, dataset, family_id, field], separators=(",", ":"))
    key = f"{kind}:{hashlib.sha256(identity.encode()).hexdigest()[:20]}"
    with catalog.write() as conn:
        conn.execute(
            """
            INSERT INTO adjudication_items
              (key, kind, system, dataset, family_id, field_name, candidates_json,
               reason_opened, observed_summary, status, opened_at, curation_target)
            VALUES (?,?,?,?,?,?,?,?,?,'open',?,?)
            ON CONFLICT(key) DO UPDATE SET candidates_json=excluded.candidates_json,
              reason_opened=excluded.reason_opened, observed_summary=excluded.observed_summary
            """,
            (
                key, kind, system, dataset, family_id, field, json.dumps(candidates), reason,
                json.dumps(observed_summary or {}, ensure_ascii=False), utcnow(), "curation/joins.yml",
            ),
        )
    return key


def adjudication_evidence(catalog: Catalog, key: str) -> dict[str, Any]:
    rows = catalog.query("SELECT * FROM adjudication_items WHERE key = ?", (key,))
    if not rows:
        raise KeyError(key)
    result = dict(rows[0])
    for name in ("candidates_json", "observed_summary", "measurement_snapshot", "source_references"):
        value = result.get(name)
        if value:
            try:
                result[name] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return result


def adjudicate(catalog: Catalog, key: str, decision: SemanticRelation, *, by: str) -> None:
    seed = asdict(decision)
    seed["relation_type"] = decision.relation_type.value
    seed["authority"] = "local"
    with catalog.write() as conn:
        _store_relation(conn, decision, authority="local")
        conn.execute(
            "UPDATE adjudication_items SET status='adjudicated', resolution=?, resolved_by=?, "
            "resolved_at=? WHERE key=?",
            (json.dumps(seed, ensure_ascii=False), by, utcnow(), key),
        )
