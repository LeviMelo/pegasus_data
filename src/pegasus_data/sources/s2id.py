"""Disasters recorded in S2iD (MIDR/SEDEC), one row per municipal event, 1991 on.

The source is MIDR's open-data portal, CKAN dataset `s2id_sedec`, resource
"1991 a 2025 - Danos Informados" (the export behind Atlas Digital de
Desastres, CC-BY), with its data dictionary and the COBRADE classification.

MIDR's firewall rejects any path ending in lowercase ``.csv``. CKAN serves an
uploaded resource from its bare ``/download`` route, which passes
(2026-10-03).

Each event keeps:
- what S2iD records: its protocol, the IBGE municipality, the event date,
  the COBRADE code with its typology and group, and the status (a registered
  report or a federally recognised emergency);
- the human-damage counts as reported.

The counts are sums by nature (people), so a municipality-year total is a sum
at use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import fetch_url

DATASET = "https://dadosabertos.mdr.gov.br/dataset/1aabd419-5677-4fa2-a0e3-a1a3e1a42234/resource/{rid}/download"
RESOURCES = {"events.csv": "1c8aac93-f874-4f07-9405-86a0398dadd6",
             "dictionary.csv": "0ad76b1b-3185-4ba2-9ce1-f769dd7fc425",
             "cobrade.pdf": "6d4d7c0b-0b21-45fc-bdf7-d5a25aa3ed63"}
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0"
#: S2iD's human-damage columns -> the field's names.
HUMAN = {"DH_MORTOS": "deaths", "DH_FERIDOS": "injured", "DH_ENFERMOS": "sick",
         "DH_DESABRIGADOS": "homeless", "DH_DESALOJADOS": "displaced", "DH_DESAPARECIDOS": "missing",
         "DH_AFETADOS_SECA_ESTIAGEM": "affected_by_drought", "DH_OUTROS AFETADOS": "other_affected"}

__all__ = ["DATASET", "HUMAN", "RESOURCES", "events", "fetch"]


def fetch(name: str, cache_dir: str | Path, *, timeout: float = 1200.0) -> Path:
    """One resource of the dataset, cached."""
    target = Path(cache_dir) / name
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    data = fetch_url(DATASET.format(rid=RESOURCES[name]), timeout=timeout, agent=USER_AGENT)
    if data.lstrip().startswith(b"<html"):
        raise RuntimeError(f"MIDR returned a page, not {name}: {data[:120]!r}")
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    return target


def events(cache_dir: str | Path) -> Any:
    """Every recorded event as a pyarrow table (municipality7, date, year, COBRADE, status, damages)."""
    import pandas as pd
    import pyarrow as pa

    raw = pd.read_csv(fetch("events.csv", cache_dir), sep=";", encoding="cp1252", dtype=str)
    date = pd.to_datetime(raw["Data_Evento"], format="%d/%m/%Y", errors="coerce")
    frame = pd.DataFrame({
        "protocol": raw["Protocolo_S2iD"], "municipality7": raw["Cod_IBGE_Mun"],
        "municipality": raw["Cod_IBGE_Mun"].str[:6], "event_date": date.dt.date, "year": date.dt.year,
        "cobrade": raw["Cod_Cobrade"], "typology": raw["descricao_tipologia"], "group": raw["grupo_de_desastre"],
        "status": raw["Status"]})
    for column, name in HUMAN.items():
        frame[name] = pd.to_numeric(raw[column], errors="coerce").astype("Int64")
    return pa.Table.from_pandas(frame, preserve_index=False)
