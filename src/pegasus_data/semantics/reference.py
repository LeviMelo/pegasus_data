"""Load reference code universes out of the catalog for the detectors.

Everything here is sourced *from the tree*, with the archive member it came from
recorded as provenance. Nothing is bundled with the package, which is the point:
a shipped municipality list with no provenance is exactly the kind of
unattributable claim §13 forbids, and it would go stale silently.
"""

from __future__ import annotations

from ..catalog.store import Catalog
from ..profile.detectors import ReferenceSets

#: Which ``code_tables`` entries feed which reference set. Table ids come from
#: the kit member names, so a prefix match covers the per-UF variants
#: (``TCNESBR``, ``TCNESAC``, …) without enumerating 27 of them.
_TABLE_PREFIXES: dict[str, tuple[str, ...]] = {
    "icd10": ("CID10",),
    "procedures": ("TPROC", "EMUSO", "SIGTAP", "TB_PROCEDIMENTO"),
    "cnes": ("TCNES",),
}


def _codes_for(catalog: Catalog, prefixes: tuple[str, ...]) -> tuple[frozenset[str], str | None]:
    codes: set[str] = set()
    provenance: str | None = None
    for prefix in prefixes:
        rows = catalog.query(
            "SELECT code, source_ref FROM code_tables WHERE table_id LIKE ?", (f"{prefix}%",)
        )
        for row in rows:
            value = str(row["code"]).strip().upper()
            if value:
                codes.add(value)
            if provenance is None:
                provenance = str(row["source_ref"])
    return frozenset(codes), provenance


def _municipalities(catalog: Catalog) -> tuple[frozenset[str], str | None]:
    """Municipality codes, taken from the ``MUNICBR`` codelist in the TAB kits.

    The dictionary holds them as six-digit codes because that is what DATASUS
    writes; the seven-digit IBGE form is derived at normalisation time by joining
    on the first six digits, never by recomputing the check digit (§7.1).
    """
    rows = catalog.query(
        """
        SELECT value_raw, source_ref FROM dictionary
         WHERE value_group IN ('MUNICBR', 'MUNIDB', 'MUNICIPIO')
           AND LENGTH(value_raw) IN (6, 7)
        """
    )
    codes = {str(r["value_raw"]).strip() for r in rows}
    provenance = str(rows[0]["source_ref"]) if rows else None
    return frozenset(c for c in codes if c.isdigit()), provenance


def load_reference_sets(catalog: Catalog) -> ReferenceSets:
    """Build the detectors' reference sets from whatever the catalog knows."""
    icd10, icd_ref = _codes_for(catalog, _TABLE_PREFIXES["icd10"])
    procedures, proc_ref = _codes_for(catalog, _TABLE_PREFIXES["procedures"])
    cnes, cnes_ref = _codes_for(catalog, _TABLE_PREFIXES["cnes"])
    municipalities, mun_ref = _municipalities(catalog)
    provenance = {
        k: v
        for k, v in {
            "icd10": icd_ref,
            "procedures": proc_ref,
            "cnes": cnes_ref,
            "municipalities": mun_ref,
        }.items()
        if v
    }
    return ReferenceSets(
        icd10=icd10,
        municipalities=municipalities,
        procedures=procedures,
        cnes=cnes,
        provenance=provenance,
    )


def reference_summary(catalog: Catalog) -> dict[str, object]:
    refs = load_reference_sets(catalog)
    return {
        "icd10": {"size": len(refs.icd10), "source": refs.provenance.get("icd10")},
        "municipalities": {"size": len(refs.municipalities), "source": refs.provenance.get("municipalities")},
        "procedures": {"size": len(refs.procedures), "source": refs.provenance.get("procedures")},
        "cnes": {"size": len(refs.cnes), "source": refs.provenance.get("cnes")},
    }
