"""IBGE's predominant biome per municipality (Biomas e Sistema Costeiro-Marinho do Brasil, 1:250,000; 2024 table).

IBGE assigns each municipality the biome that covers the largest share of its area: Amazônia, Caatinga, Cerrado, Mata
Atlântica, Pampa or Pantanal. The table is a semicolon-separated UTF-8 CSV (with BOM): ``Geocódigo``, ``Nome do
município``, ``Sigla da UF``, ``Bioma predominante``. A biome's member code is its name, as IBGE gives no code.
IBGE's own note (``LEIA_ME_Sobre_a_relacao_entre_municipios_e_biomas.pdf``) warns that a municipality often spans
several biomes; the predominant one is a classification, not a description of the whole territory.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..transport import download

URL = ("https://geoftp.ibge.gov.br/informacoes_ambientais/estudos_ambientais/biomas/documentos/"
       "Bioma_Predominante_por_Municipio_2024.csv")

__all__ = ["URL", "fetch", "memberships"]


def fetch(cache_dir: str | Path, *, timeout: float = 600.0) -> Path:
    """The 2024 table, downloaded once (about 200 kB)."""
    cache = Path(cache_dir)
    return download(URL, cache / Path(URL).name, timeout=timeout)


def memberships(path: str | Path) -> list[tuple[str, str, str]]:
    """``(municipality code7, member code, member name)`` for every municipality; the member is the biome's name."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    out = []
    for r in rows:
        code = (r.get("Geocódigo") or "").strip()
        biome = (r.get("Bioma predominante") or "").strip()
        if len(code) == 7 and code.isdigit() and biome:
            out.append((code, biome, biome))
    return out
