"""Schema drift across strata (D2) — and the silent renames it exposes.

Two rules, both from §13:

* **Never report ``stable`` where n = 1.** With one sampled file, drift is
  undetectable by construction; the honest answer is ``insufficient_evidence``.
* **Never let a missing column pass silently.** SIH-RD carries ``DIAG_SECUN`` in
  its 2008–2014 generation and replaces it with ``DIAGSEC1..9`` from 2017. A
  query asking for ``DIAG_SECUN`` against a 2020 file returns empty with no
  error, and an empty result looks legitimate. :func:`detect_renames` records
  exactly which generations hold which field so the loader can raise instead.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field

from ..catalog.store import Catalog


@dataclass(slots=True)
class DriftReport:
    system: str
    series: str
    observed_strata: int
    signatures: list[str]
    union_fields: list[str]
    always_present: list[str]
    sometimes_present: list[str]
    drift_status: str

    @property
    def signature_count(self) -> int:
        return len(self.signatures)


def analyse_drift(catalog: Catalog) -> list[DriftReport]:
    rows = catalog.query(
        """
        SELECT system, series, stratum_id, year, schema_signature
          FROM strata
         WHERE sample_status='ok' AND schema_signature IS NOT NULL
        """
    )
    fields_by_sig: dict[str, list[str]] = {}
    for r in catalog.query("SELECT schema_signature, fields_json FROM schemas"):
        fields_by_sig[r["schema_signature"]] = json.loads(r["fields_json"])

    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for r in rows:
        grouped[(r["system"], r["series"] or "")].append(dict(r))

    reports: list[DriftReport] = []
    for (system, series), members in grouped.items():
        signatures = sorted({str(m["schema_signature"]) for m in members})
        per_sig_fields = [set(fields_by_sig.get(s, [])) for s in signatures]
        union: set[str] = set().union(*per_sig_fields) if per_sig_fields else set()
        always = set.intersection(*per_sig_fields) if per_sig_fields else set()
        sometimes = union - always

        if len(members) < 2:
            status = "insufficient_evidence"
        elif len(signatures) == 1:
            status = "stable"
        else:
            status = "drifting"

        reports.append(
            DriftReport(
                system=system,
                series=series,
                observed_strata=len(members),
                signatures=signatures,
                union_fields=sorted(union),
                always_present=sorted(always),
                sometimes_present=sorted(sometimes),
                drift_status=status,
            )
        )
    return reports


def persist_drift(catalog: Catalog, reports: list[DriftReport]) -> int:
    catalog.executemany(
        """
        INSERT INTO schema_drift (system, series, observed_strata, schema_signature_count,
            signatures_json, union_field_count, always_present_json, sometimes_present_json, drift_status)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(system, series) DO UPDATE SET
            observed_strata=excluded.observed_strata,
            schema_signature_count=excluded.schema_signature_count,
            signatures_json=excluded.signatures_json,
            union_field_count=excluded.union_field_count,
            always_present_json=excluded.always_present_json,
            sometimes_present_json=excluded.sometimes_present_json,
            drift_status=excluded.drift_status
        """,
        [
            (
                r.system, r.series, r.observed_strata, r.signature_count,
                json.dumps(r.signatures), len(r.union_fields),
                json.dumps(r.always_present), json.dumps(r.sometimes_present), r.drift_status,
            )
            for r in reports
        ],
    )
    return len(reports)


#: Families of fields whose base name is shared but whose arity changes across
#: generations — the shape a silent rename takes in DATASUS.
_NUMBERED = re.compile(r"^(?P<base>[A-Z_]+?)(?P<index>\d{1,2})$")


@dataclass(slots=True)
class RenameCandidate:
    system: str
    series: str
    old_field: str
    new_fields: list[str] = field(default_factory=list)
    old_signatures: list[str] = field(default_factory=list)
    new_signatures: list[str] = field(default_factory=list)


def detect_renames(catalog: Catalog) -> list[RenameCandidate]:
    """Find fields that vanish while a numbered family with a related stem appears.

    Deliberately conservative and *evidence-only*: this records a candidate for a
    human to confirm. It never rewrites a query or aliases one column to another,
    because an unverified alias is exactly the kind of invisible wrong answer §13
    forbids.
    """
    fields_by_sig: dict[str, list[str]] = {}
    for r in catalog.query("SELECT schema_signature, fields_json FROM schemas"):
        fields_by_sig[r["schema_signature"]] = json.loads(r["fields_json"])

    out: list[RenameCandidate] = []
    for row in catalog.query(
        "SELECT system, series, signatures_json, sometimes_present_json FROM schema_drift WHERE drift_status='drifting'"
    ):
        signatures = json.loads(row["signatures_json"])
        sometimes = set(json.loads(row["sometimes_present_json"]))
        if not sometimes:
            continue
        presence = {
            f: [s for s in signatures if f in set(fields_by_sig.get(s, []))] for f in sometimes
        }
        numbered_bases: dict[str, list[str]] = defaultdict(list)
        for f in sometimes:
            m = _NUMBERED.match(f)
            if m:
                numbered_bases[m.group("base").rstrip("_")].append(f)

        for f in sorted(sometimes):
            if _NUMBERED.match(f):
                continue
            stem = f.replace("_", "")
            for base, members in numbered_bases.items():
                base_stem = base.replace("_", "")
                if len(members) < 2:
                    continue
                if not (base_stem.startswith(stem[:5]) or stem.startswith(base_stem[:5])):
                    continue
                old_sigs = presence.get(f, [])
                new_sigs = sorted({s for m in members for s in presence.get(m, [])})
                if old_sigs and new_sigs and not set(old_sigs) & set(new_sigs):
                    out.append(
                        RenameCandidate(
                            system=row["system"],
                            series=row["series"],
                            old_field=f,
                            new_fields=sorted(members),
                            old_signatures=old_sigs,
                            new_signatures=new_sigs,
                        )
                    )
    return out


def persist_renames(catalog: Catalog, candidates: list[RenameCandidate]) -> int:
    rows: list[tuple[object, ...]] = []
    for c in candidates:
        rows.append((c.system, c.series, c.old_field, json.dumps(c.old_signatures), json.dumps(c.new_signatures), None, None))
        for nf in c.new_fields:
            rows.append((c.system, c.series, nf, json.dumps(c.new_signatures), json.dumps(c.old_signatures), None, None))
    catalog.executemany(
        """
        INSERT INTO field_renames (system, series, field_name, present_in, absent_in, first_year, last_year)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(system, series, field_name) DO UPDATE SET
            present_in=excluded.present_in, absent_in=excluded.absent_in
        """,
        rows,
    )
    return len(rows)


def field_availability(catalog: Catalog, system: str, series: str, field_name: str) -> dict[str, object]:
    """Where a field exists and where it does not — the loader's guard rail."""
    row = catalog.query(
        "SELECT signatures_json FROM schema_drift WHERE system=? AND series=?", (system, series)
    )
    if not row:
        return {"known": False}
    signatures = json.loads(row[0]["signatures_json"])
    present: list[str] = []
    for sig in signatures:
        fields = catalog.query(
            "SELECT fields_json FROM schemas WHERE schema_signature=?", (sig,)
        )
        if fields and field_name in json.loads(fields[0]["fields_json"]):
            present.append(sig)
    families = catalog.query(
        "SELECT family_id, schema_signature, time_min, time_max FROM families WHERE system=? AND series=?",
        (system, series),
    )
    return {
        "known": True,
        "field": field_name,
        "present_in": present,
        "absent_in": [s for s in signatures if s not in present],
        "generations": [
            {
                "family_id": f["family_id"],
                "schema_signature": f["schema_signature"],
                "years": [f["time_min"], f["time_max"]],
                "has_field": f["schema_signature"] in present,
            }
            for f in families
        ],
    }
