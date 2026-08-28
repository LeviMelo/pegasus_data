"""IBGE's territorial ontology, from the authority that defines it.

DATASUS publishes Brazil's geography as `.CNV` codelists, and those tables are
what TabNet tabulates against — so they are the right default when a figure has
to reconcile with the Ministry's own published output. They are not, however,
the authority for what a municipality IS, and measurement shows exactly where
that matters. See `docs/IBGE_LOCALIDADES.md` for the full audit; the short form:

* **DATASUS's microregion table is IBGE's, exactly.** 558 groups against 558,
  and not one municipality assigned differently. Comparing the LABELS suggested
  74% agreement; comparing the PARTITIONS showed they are identical. The
  difference was entirely `.CNV` truncation — "Colorado Oeste" for "Colorado do
  Oeste".
* **The mesoregion table differs on three municipalities**, all in one
  direction: DATASUS files 431936, 432146 and 510619 under "Ignorado" where IBGE
  knows the answer. Nothing is assigned to a *different* region.
* **DATASUS publishes no current hierarchy at all.** IBGE retired mesorregiões
  and microrregiões in 2017 and replaced them with Regiões Geográficas
  Imediatas (510) and Intermediárias (133). Neither appears anywhere in the
  2,348 codelists the label pack ships.
* **Health regions are a Ministry construct** and IBGE has none. Those stay with
  DATASUS, which is why this is a supplement and not a replacement.

So: IBGE for territorial identity and the classifications it owns, DATASUS for
the health-service geography it owns, and each labelled with which is which.

The endpoint is the Localidades API, `/api/v1/localidades`. v1 is current for
localidades — `/v2/` and `/v3/` return 503 for these paths; the v3 that does
exist (`/v3/agregados`) is the statistical-tables service and answers a
different question. One request returns the whole hierarchy per municipality,
which is why no pagination appears below.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "BASE_URL",
    "IBGE_CLASSIFICATIONS",
    "Municipality",
    "fetch_municipalities",
    "load_cached",
    "save_cache",
]

BASE_URL = "https://servicodados.ibge.gov.br/api/v1/localidades"

#: Classifications compiled out of the municipality payload, and what each is.
#: `legacy` marks the two IBGE retired in 2017 but still publishes — they are
#: kept because DATASUS's tables use them and thirty years of health data is
#: tabulated against them.
IBGE_CLASSIFICATIONS: dict[str, dict[str, str]] = {
    "ibge_immediate_region": {
        "what": "Região Geográfica Imediata — the current sub-state grouping "
                "IBGE introduced in 2017 to replace the microrregião.",
        "status": "current",
    },
    "ibge_intermediate_region": {
        "what": "Região Geográfica Intermediária — the current grouping above "
                "the imediata, replacing the mesorregião.",
        "status": "current",
    },
    "ibge_microregion": {
        "what": "Microrregião. Retired by IBGE in 2017 and kept because the "
                "health series is tabulated against it.",
        "status": "legacy",
    },
    "ibge_mesoregion": {
        "what": "Mesorregião. Retired by IBGE in 2017, kept for the same reason.",
        "status": "legacy",
    },
    "uf": {
        "what": "Unidade da Federação. Derivable from the code prefix, and "
                "carried explicitly so the label comes from IBGE rather than a "
                "hard-coded table.",
        "status": "current",
    },
    "ibge_macroregion": {
        "what": "One of the five great regions — Norte, Nordeste, Sudeste, Sul, "
                "Centro-Oeste.",
        "status": "current",
    },
}


@dataclass(frozen=True, slots=True)
class Municipality:
    """One municipality and every grouping IBGE places it in.

    `code6` is the six-digit form DATASUS writes; `code7` is IBGE's own,
    including the check digit. §7.1 is the reason both are carried: a join by
    equality between the two loses every row.
    """

    code7: str
    code6: str
    name: str
    uf_code: str
    uf_sigla: str
    uf_name: str
    macroregion: str
    mesoregion_id: str | None = None
    mesoregion_name: str | None = None
    microregion_id: str | None = None
    microregion_name: str | None = None
    immediate_id: str | None = None
    immediate_name: str | None = None
    intermediate_id: str | None = None
    intermediate_name: str | None = None

    def memberships(self) -> Iterator[tuple[str, str, str]]:
        """`(classification, member_code, member_label)`, skipping what is absent."""
        yield ("uf", self.uf_code, f"{self.uf_sigla} {self.uf_name}")
        yield ("ibge_macroregion", self.uf_code[:1], self.macroregion)
        for classification, code, name in (
            ("ibge_mesoregion", self.mesoregion_id, self.mesoregion_name),
            ("ibge_microregion", self.microregion_id, self.microregion_name),
            ("ibge_immediate_region", self.immediate_id, self.immediate_name),
            ("ibge_intermediate_region", self.intermediate_id, self.intermediate_name),
        ):
            if code and name:
                yield (classification, str(code), str(name))


def _text(node: Any, *path: str) -> str | None:
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return None if node is None else str(node)


def _parse(record: dict[str, Any]) -> Municipality | None:
    code7 = str(record.get("id") or "")
    if len(code7) != 7 or not code7.isdigit():
        return None
    micro = record.get("microrregiao") or {}
    meso = (micro.get("mesorregiao") or {}) if isinstance(micro, dict) else {}
    imediata = record.get("regiao-imediata") or {}
    intermediaria = (imediata.get("regiao-intermediaria") or {}) if isinstance(imediata, dict) else {}
    # The UF hangs off whichever branch exists; IBGE repeats it under both.
    uf = (_text(meso, "UF", "id") and meso["UF"]) or (
        intermediaria.get("UF") if isinstance(intermediaria, dict) else None) or {}
    return Municipality(
        code7=code7,
        code6=code7[:6],
        name=str(record.get("nome") or ""),
        uf_code=str(uf.get("id") or code7[:2]),
        uf_sigla=str(uf.get("sigla") or ""),
        uf_name=str(uf.get("nome") or ""),
        macroregion=_text(uf, "regiao", "nome") or "",
        mesoregion_id=_text(meso, "id"),
        mesoregion_name=_text(meso, "nome"),
        microregion_id=_text(micro, "id"),
        microregion_name=_text(micro, "nome"),
        immediate_id=_text(imediata, "id"),
        immediate_name=_text(imediata, "nome"),
        intermediate_id=_text(intermediaria, "id"),
        intermediate_name=_text(intermediaria, "nome"),
    )


def fetch_municipalities(*, timeout: float = 60.0) -> tuple[Municipality, ...]:
    """Every Brazilian municipality with its full hierarchy, in one request.

    IBGE returns the nested chain per municipality, so there is nothing to
    paginate and nothing to join client-side.
    """
    import httpx

    with httpx.Client(timeout=timeout, headers={"User-Agent": "pegasus-data"}) as client:
        response = client.get(f"{BASE_URL}/municipios")
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):  # pragma: no cover - defensive
        raise RuntimeError(f"{BASE_URL}/municipios did not return a list")
    parsed = tuple(m for m in (_parse(r) for r in payload) if m is not None)
    if len(parsed) < 5_000:  # pragma: no cover - defensive
        raise RuntimeError(
            f"IBGE returned only {len(parsed)} municipalities; Brazil has ~5,570, "
            "so this response is truncated and must not be compiled"
        )
    return parsed


def save_cache(municipalities: tuple[Municipality, ...], path: str | Path) -> Path:
    """Keep the raw answer beside the compiled pack, so a rebuild needs no network."""
    from dataclasses import asdict

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"source": BASE_URL, "count": len(municipalities),
                    "municipalities": [asdict(m) for m in municipalities]},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    return out


def load_cached(path: str | Path) -> tuple[Municipality, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(Municipality(**record) for record in data.get("municipalities") or ())
