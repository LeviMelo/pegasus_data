"""How much of DATASUS is described and translatable, measured field by field (ADR-0085).

The standard is total: every variable of every family described from a source,
and every code of every coded variable translatable. This module measures the
distance to that standard, for every (family, field) in the catalog. It does
not estimate:

- a field's DESCRIPTION comes from the curation (``variable_docs``): documented
  from a source, inferred, or missing;
- a field's CODING comes from the compiled label decision (``label_bindings``),
  which weighed the bound tables against real sample files. ``share`` is the
  fraction of the codes observed in those samples that the chosen table decodes.

Each row is classified:

``description``
    ``documented`` · ``inferred`` · ``missing``
``coding``
    ``not_coded``  the curation says the values are numbers, dates or text;
    ``decoded``    every observed code has a label;
    ``partial``    some observed codes have none (``share`` < 1);
    ``undecoded``  coded, and no table decodes it;
    ``unmeasured`` coded and bound, but no sample was read to measure it;
    ``unknown``    no curation entry says whether it is coded.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from ..catalog.store import Catalog
from .curation import load_variable_docs

#: A share at or above this is "decoded": rounding in the stored share only.
DECODED = 0.9999


@dataclass(frozen=True, slots=True)
class FieldCoverage:
    system: str
    series: str
    family_id: str
    field_name: str
    files: int
    description: str
    source: str | None
    coding: str
    codelists: str | None
    share: float | None
    observed: int | None
    reason: str | None


def measure(store: Catalog, systems: list[str] | None = None) -> list[FieldCoverage]:
    """One row per (family, field), for every family in the catalog."""
    wanted = {s.upper() for s in systems} if systems else None
    families = store.query(
        """
        SELECT f.family_id, f.system, f.series, s.fields_json,
               (SELECT COUNT(*) FROM family_files ff WHERE ff.family_id = f.family_id) AS files
          FROM families f JOIN schemas s ON s.schema_signature = f.schema_signature
        """
    )
    decisions: dict[tuple[str, str], Any] = {
        (str(r["family_id"]), str(r["field_name"]).upper()): r
        for r in store.query(
            "SELECT family_id, field_name, codelists, basis, share, observed, reason FROM label_bindings"
        )
    }
    docs_by_system: dict[str, dict[str, Any]] = {}
    rows: list[FieldCoverage] = []
    for fam in families:
        system = str(fam["system"])
        if wanted and system.upper() not in wanted:
            continue
        docs = docs_by_system.setdefault(system, load_variable_docs(store, system))
        fields = [f["name"] if isinstance(f, dict) else f for f in json.loads(fam["fields_json"] or "[]")]
        for name in fields:
            field = str(name).upper()
            doc = docs.get(field)
            if doc is None or not (doc.description or doc.official_name):
                description, source = "missing", None
            elif doc.source == "inferred":
                description, source = "inferred", doc.source
            else:
                description, source = "documented", doc.source
            decision = decisions.get((str(fam["family_id"]), field))
            codelists = None
            share = observed = None
            reason = None
            if decision is not None:
                codelists = ",".join(json.loads(decision["codelists"] or "[]")) or None
                share = decision["share"]
                observed = decision["observed"]
                reason = decision["reason"]
            coded = doc is not None and doc.code_system in ("internal", "external")
            if decision is not None and codelists:
                if share is None:
                    coding = "unmeasured"
                elif share >= DECODED:
                    coding = "decoded"
                else:
                    coding = "partial"
            elif coded or (decision is not None and decision["basis"] == "none"
                           and reason != "no codelist is bound to this field"):
                coding = "undecoded"
            elif doc is not None:
                coding = "not_coded"
            else:
                coding = "unknown"
            rows.append(FieldCoverage(
                system, str(fam["series"] or ""), str(fam["family_id"]), field, int(fam["files"] or 0),
                description, source, coding, codelists, share, observed, reason,
            ))
    return rows


def summarise(rows: list[FieldCoverage]) -> list[dict[str, Any]]:
    """Per system: distinct fields by description and by coding state."""
    by_system: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: {"description": Counter(), "coding": Counter()})
    seen: set[tuple[str, str]] = set()
    worst: dict[tuple[str, str], tuple[str, str]] = {}
    rank = {"undecoded": 0, "unknown": 1, "partial": 2, "unmeasured": 3, "decoded": 4, "not_coded": 5}
    for r in rows:
        key = (r.system, r.field_name)
        # A field counts once per system, at its WORST state across families.
        prior = worst.get(key)
        if prior is None or rank[r.coding] < rank[prior[1]]:
            worst[key] = (r.description, r.coding)
        seen.add(key)
    for (system, _field), (description, coding) in worst.items():
        by_system[system]["description"][description] += 1
        by_system[system]["coding"][coding] += 1
    out = []
    for system in sorted(by_system):
        d, c = by_system[system]["description"], by_system[system]["coding"]
        out.append({
            "system": system, "fields": sum(d.values()),
            "documented": d["documented"], "inferred": d["inferred"], "missing": d["missing"],
            "decoded": c["decoded"], "partial": c["partial"], "undecoded": c["undecoded"],
            "unmeasured": c["unmeasured"], "unknown": c["unknown"], "not_coded": c["not_coded"],
        })
    return out


def as_records(rows: list[FieldCoverage]) -> list[dict[str, Any]]:
    return [asdict(r) for r in rows]
