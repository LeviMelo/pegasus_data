"""IBGE's Arranjos Populacionais e Concentrações Urbanas do Brasil, 2nd edition (2016), as municipal memberships.

A population arrangement is two or more municipalities strongly integrated by daily commuting to work or study (Census
2010 sample) or by the contiguity of their main urban areas; an urban concentration is an arrangement or an isolated
municipality above 100,000 inhabitants, medium (100,000-750,000) or large (above 750,000). IBGE publishes the
per-municipality composition only inside a Personal Geodatabase (Access ``.mdb``), table
``ComposicaoRecortes_01_PorMunicipio``; its attribute columns are read with ``access-parser``, the geometry is not.
An arrangement's code is its core municipality's code; ``<Null>`` is the table's own blank.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from ..transport import download

URL = ("https://geoftp.ibge.gov.br/organizacao_do_territorio/divisao_regional/arranjos_populacionais/base_de_dados_2ed/"
       "ArranjosPopulacionais_mbd_2ed.zip")
TABLE = "ComposicaoRecortes_01_PorMunicipio"
#: classification -> the column stem in `TABLE` (``Cod<stem>``, ``Nom[e]<stem>``)
COLUMNS = {
    "population_arrangement": "ArranjoPop",
    "urban_concentration_medium": "MediaConcUrbana",
    "urban_concentration_large": "GrandeConcUrbana",
}

__all__ = ["COLUMNS", "URL", "fetch", "memberships"]


def fetch(cache_dir: str | Path, *, timeout: float = 1800.0) -> Path:
    """The 2nd edition's geodatabase, downloaded once (88 MB zipped) and unpacked beside it."""
    cache = Path(cache_dir)
    zipped = download(URL, cache / Path(URL).name, timeout=timeout)
    with zipfile.ZipFile(zipped) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".mdb"))
        target = cache / Path(name).name
        if not target.is_file():
            archive.extract(name, cache)
    return target


def memberships(path: str | Path) -> dict[str, list[tuple[str, str, str]]]:
    """Per classification in `COLUMNS`, ``(municipality code7, member code, member name)`` for every municipality IBGE
    places in one; municipalities in none are absent, not given a member."""
    from access_parser import AccessParser

    table = AccessParser(str(path)).parse_table(TABLE)
    codes = table["CodMunT"]
    out: dict[str, list[tuple[str, str, str]]] = {}
    for name, stem in COLUMNS.items():
        member = table[f"Cod{stem}"]
        label = table[f"Nome{stem}"] if f"Nome{stem}" in table else table[f"Nom{stem}"]
        out[name] = [(str(codes[i]), str(member[i]), str(label[i]))
                     for i in range(len(codes)) if member[i] and str(member[i]) != "<Null>"]
    return out
