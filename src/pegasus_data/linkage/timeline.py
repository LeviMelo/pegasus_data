"""One pregnancy as a timeline of linked events (ADR-0112).

A birth record (SINASC) is the spine. The links in ``curation/links.yml``
attach to it:

* the mother's delivery admission, SUS (``sinasc_births_to_delivery_admission``)
  or not (``sinasc_births_to_ciha_delivery``);
* the baby's own admissions in its first 28 days
  (``sih_neonatal_admissions_to_sinasc``);
* the baby's death before one year (``sim_infant_deaths_to_sinasc``);
* the mother's death from an obstetric cause, through the delivery admission
  (``sim_maternal_deaths_to_admission``).

Every event carries the link that attached it, the method, and (for the
probabilistic method) the pair's evidence in bits, so a reader can see how
sure each connection is. A link that is not viable at the scope attaches
nothing and is named in ``not_viable``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from .engine import LinkNotViable, link
from .roles import role_table

DELIVERY = "sinasc_births_to_delivery_admission"
DELIVERY_PRIVATE = "sinasc_births_to_ciha_delivery"
NEONATAL = "sih_neonatal_admissions_to_sinasc"
INFANT_DEATH = "sim_infant_deaths_to_sinasc"
MATERNAL_DEATH = "sim_maternal_deaths_to_admission"


def _scope(value: object) -> object:
    return tuple(value) if isinstance(value, list) else value


@lru_cache(maxsize=8)
def _records(dataset: str, period: object, geography: object) -> dict[str, dict[str, Any]]:
    """Every record of a scope by id, as its roles (cached per process)."""
    table = role_table(dataset, period=period, geography=geography, allow_partial=True)
    ids = pc.binary_join_element_wise(table.column("_blob_sha256"),
                                      pc.cast(table.column("_row"), pa.string()), ":")
    rows = table.drop_columns(["_blob_sha256", "_row"]).to_pylist()
    return dict(zip(ids.to_pylist(), rows, strict=True))


@lru_cache(maxsize=16)
def _pairs(spec: str, method: str, period: object, geography: object) -> tuple[list[tuple[str, str, float | None]], str]:
    try:
        result = link(spec, period=period, geography=geography, method=method, allow_partial=True)
    except LinkNotViable as exc:
        return [], str(exc.result.summary().get("verdict"))
    t = result.pairs
    bits = t.column("bits").to_pylist() if "bits" in t.column_names else [None] * t.num_rows
    return list(zip(t.column("l").to_pylist(), t.column("r").to_pylist(), bits, strict=True)), str(result.verdict)


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    from ..registry import lookup

    table = lookup("CADGERBR", "CNES")
    if table is None:
        return {}
    return dict(zip(table.column("code").to_pylist(), table.column("label").to_pylist(), strict=True))


def _facility(code: object) -> dict[str, Any] | None:
    if not code:
        return None
    return {"code": code, "name": _names().get(str(code))}


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def timeline(birth_id: str, *, period: object, geography: object, method: str = "probabilistic") -> dict[str, Any]:
    """The events linked to one birth record, in time order."""
    period, geography = _scope(period), _scope(geography)
    births = _records("SINASC-DN", period, geography)
    birth = births.get(birth_id)
    if birth is None:
        raise KeyError(f"no SINASC record {birth_id!r} in {period} {geography}")
    group = sorted(
        rid for rid, r in births.items()
        if r["mother.birth_date"] == birth["mother.birth_date"] and r["birth.facility"] == birth["birth.facility"]
        and r["birth.date"] == birth["birth.date"] and r["mother.birth_date"] is not None
    ) or [birth_id]
    admissions = _records("SIH-RD", period, geography)
    deaths = _records("SIM-DO", period, geography)
    events: list[dict[str, Any]] = []
    not_viable: dict[str, str] = {}
    for rid in group:
        r = births[rid]
        events.append({"kind": "birth", "date": _iso(r["birth.date"]), "record": rid, "facility": _facility(r["birth.facility"]),
                       "details": {"sex": r["baby.sex"], "weight_g": r["birth.weight"], "delivery": r["birth.delivery"],
                                   "plurality": r["birth.plurality"], "gestation_weeks": r["birth.gestation_weeks"],
                                   "mother_age": r["mother.age"], "residence": r["mother.residence"]}})

    delivery_pairs, verdict = _pairs(DELIVERY, method, period, geography)
    if not delivery_pairs and verdict != "viable":
        not_viable[DELIVERY] = verdict
    delivery_ids = [(r, b) for l_id, r, b in delivery_pairs if l_id == group[0]]
    for adm_id, bits in delivery_ids:
        a = admissions.get(adm_id) or {}
        events.append({"kind": "delivery admission", "system": "SIH", "date": _iso(a.get("admission.start")),
                       "end": _iso(a.get("admission.end")),
                       "record": adm_id, "facility": _facility(a.get("admission.facility")),
                       "link": {"spec": DELIVERY, "method": method, "bits": bits},
                       "details": {"diagnosis": a.get("admission.diagnosis"), "procedure": a.get("admission.procedure"),
                                   "ended_in_death": a.get("admission.death") == "1"}})
    # The private sector's twin: a delivery in a non-SUS hospital is in CIHA.
    private_pairs, verdict = _pairs(DELIVERY_PRIVATE, method, period, geography)
    if not private_pairs and verdict != "viable":
        not_viable[DELIVERY_PRIVATE] = verdict
    private = [(r, b) for l_id, r, b in private_pairs if l_id == group[0]]
    if private:
        ciha = _records("CIHA", period, geography)
        for adm_id, bits in private:
            a = ciha.get(adm_id) or {}
            events.append({"kind": "delivery admission", "system": "CIHA", "date": _iso(a.get("admission.start")),
                           "end": _iso(a.get("admission.end")), "record": adm_id,
                           "facility": _facility(a.get("admission.facility")),
                           "link": {"spec": DELIVERY_PRIVATE, "method": method, "bits": bits},
                           "details": {"diagnosis": a.get("admission.diagnosis"), "procedure": a.get("admission.procedure"),
                                       "payer": a.get("admission.payer"), "ended_in_death": a.get("admission.death") == "1"}})

    neonatal_pairs, verdict = _pairs(NEONATAL, method, period, geography)
    if not neonatal_pairs and verdict != "viable":
        not_viable[NEONATAL] = verdict
    for adm_id, rid, bits in neonatal_pairs:
        if rid in group:
            a = admissions.get(adm_id) or {}
            events.append({"kind": "neonatal admission", "date": _iso(a.get("admission.start")), "end": _iso(a.get("admission.end")),
                           "record": adm_id, "birth": rid, "facility": _facility(a.get("admission.facility")),
                           "link": {"spec": NEONATAL, "method": method, "bits": bits},
                           "details": {"diagnosis": a.get("admission.diagnosis"), "procedure": a.get("admission.procedure"),
                                       "ended_in_death": a.get("admission.death") == "1"}})

    infant_pairs, verdict = _pairs(INFANT_DEATH, method, period, geography)
    if not infant_pairs and verdict != "viable":
        not_viable[INFANT_DEATH] = verdict
    for death_id, rid, bits in infant_pairs:
        if rid in group:
            d = deaths.get(death_id) or {}
            events.append({"kind": "infant death", "date": _iso(d.get("death.date")), "record": death_id, "birth": rid,
                           "facility": _facility(d.get("death.facility")),
                           "link": {"spec": INFANT_DEATH, "method": method, "bits": bits},
                           "details": {"cause": d.get("death.cause"), "place": d.get("death.place")}})

    maternal_pairs, verdict = _pairs(MATERNAL_DEATH, method, period, geography)
    if not maternal_pairs and verdict != "viable":
        not_viable[MATERNAL_DEATH] = verdict
    delivered_in = {adm for adm, _b in delivery_ids}
    for death_id, adm_id, bits in maternal_pairs:
        if adm_id in delivered_in:
            d = deaths.get(death_id) or {}
            events.append({"kind": "maternal death", "date": _iso(d.get("death.date")), "record": death_id,
                           "facility": _facility(d.get("death.facility")),
                           "link": {"spec": MATERNAL_DEATH, "method": method, "bits": bits},
                           "details": {"cause": d.get("death.cause"), "place": d.get("death.place")}})

    events.sort(key=lambda e: (e["date"] or "9999", e["kind"] != "delivery admission"))
    return {"birth": birth_id, "period": str(period), "geography": str(geography), "method": method,
            "events": events, "not_viable": not_viable}


def notable_births(*, period: object, geography: object, method: str = "probabilistic", limit: int = 30) -> list[dict[str, Any]]:
    """Births with the most linked events: a starting point for reading timelines."""
    period, geography = _scope(period), _scope(geography)
    counts: dict[str, dict[str, int]] = {}
    for spec, side in ((NEONATAL, "r"), (INFANT_DEATH, "r")):
        pairs, _v = _pairs(spec, method, period, geography)
        for l_id, r_id, _b in pairs:
            key = r_id if side == "r" else l_id
            counts.setdefault(key, {}).setdefault(spec, 0)
            counts[key][spec] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-(INFANT_DEATH in kv[1]), -sum(kv[1].values())))
    births = _records("SINASC-DN", period, geography)
    out = []
    for rid, links in ranked[:limit]:
        r = births.get(rid) or {}
        facility = _facility(r.get("birth.facility"))
        out.append({"birth": rid, "links": links, "date": _iso(r.get("birth.date")), "sex": r.get("baby.sex"),
                    "weight_g": r.get("birth.weight"), "gestation_weeks": r.get("birth.gestation_weeks"),
                    "facility": facility})
    return out


__all__ = ["notable_births", "timeline"]
