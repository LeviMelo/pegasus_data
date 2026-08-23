"""Typed semantic relations and the maintainer adjudication queue."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..catalog.store import Catalog, utcnow
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
) -> list[SemanticRelation]:
    wanted = str(relation_type) if relation_type is not None else None
    return [
        item
        for item in load_relations()
        if item.system in {"*", system.upper()}
        and item.dataset in {"*", dataset.upper()}
        and item.field_name == field.upper()
        and (wanted is None or item.relation_type.value == wanted)
        and item.status == "adjudicated"
    ]


def seed_relations(catalog: Catalog, root: Path | None = None) -> int:
    relations = load_relations(root)
    catalog.executemany(
        """
        INSERT INTO semantic_relations
          (system, dataset, field_name, relation_type, target_type, target_name,
           artifact, source_namespace, target_namespace, valid_from, valid_to,
           status, evidence)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(system, dataset, field_name, relation_type, target_type, target_name)
        DO UPDATE SET artifact=excluded.artifact, source_namespace=excluded.source_namespace,
          target_namespace=excluded.target_namespace, valid_from=excluded.valid_from,
          valid_to=excluded.valid_to, status=excluded.status, evidence=excluded.evidence
        """,
        [
            (
                r.system, r.dataset, r.field_name, r.relation_type.value, r.target_type,
                r.target_name, r.artifact, r.source_namespace, r.target_namespace,
                r.valid_from, r.valid_to, r.status, r.evidence,
            )
            for r in relations
        ],
    )
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
    catalog.execute(
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
    catalog.execute(
        """
        INSERT INTO semantic_relations
          (system, dataset, field_name, relation_type, target_type, target_name,
           artifact, source_namespace, target_namespace, valid_from, valid_to,
           status, evidence)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(system, dataset, field_name, relation_type, target_type, target_name)
        DO UPDATE SET artifact=excluded.artifact, status='adjudicated', evidence=excluded.evidence
        """,
        tuple(seed[name] for name in (
            "system", "dataset", "field_name", "relation_type", "target_type", "target_name",
            "artifact", "source_namespace", "target_namespace", "valid_from", "valid_to", "status", "evidence",
        )),
    )
    catalog.execute(
        "UPDATE adjudication_items SET status='adjudicated', resolution=?, resolved_by=?, "
        "resolved_at=? WHERE key=?",
        (json.dumps(seed, ensure_ascii=False), by, utcnow(), key),
    )
