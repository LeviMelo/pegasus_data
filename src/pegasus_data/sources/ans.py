"""ANS supplementary-health beneficiaries, by municipality, sex and age band.

ANS's open data (``dadosabertos.ans.gov.br/FTP/PDA/informacoes_consolidadas_de_beneficiarios-024/``)
publishes, per month and state since 2021-05, every plan's active
beneficiaries by the beneficiary's municipality, sex and age band, with the
plan's coverage (``COBERTURA_ASSIST_PLAN``: medical-hospital or dental only).

A beneficiary here is a plan LINK (vínculo), not a person: someone with two
plans counts twice. The SUS-dependent population (handoff §7.1) is a modelled
product built from this, never this count itself.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pyarrow as pa

from . import fetch_url

BASE = "https://dadosabertos.ans.gov.br/FTP/PDA/informacoes_consolidadas_de_beneficiarios-024/"
UFS = ("AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE",
       "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO", "XX")
_KEYS = ("CD_MUNICIPIO", "TP_SEXO", "DE_FAIXA_ETARIA", "COBERTURA_ASSIST_PLAN")


def fetch(uf: str, year: int, month: int, cache_dir: str | Path, *, timeout: float = 1800.0) -> Path:
    """One state-month file, downloaded once into the cache."""
    name = f"pda-024-icb-{uf}-{year}_{month:02d}.zip"
    target = Path(cache_dir) / name
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        data = fetch_url(f"{BASE}{year}{month:02d}/{name}", timeout=timeout)
        partial = target.with_suffix(".part")
        partial.write_bytes(data)
        partial.replace(target)
    return target


def beneficiaries(year: int, month: int, cache_dir: str | Path) -> pa.Table:
    """Active beneficiaries of one month, summed by municipality, sex, age band and coverage.

    ``XX`` is ANS's file for beneficiaries with no state; it is read too, and
    its rows keep whatever municipality they carry.
    """
    import pyarrow.csv as pacsv

    parts = []
    for uf in UFS:
        with zipfile.ZipFile(fetch(uf, year, month, cache_dir)) as zf:
            raw = zf.read(zf.namelist()[0])
        table = pacsv.read_csv(
            io.BytesIO(raw),
            read_options=pacsv.ReadOptions(encoding="utf-8"),
            parse_options=pacsv.ParseOptions(delimiter=";"),
            convert_options=pacsv.ConvertOptions(
                include_columns=[*_KEYS, "QT_BENEFICIARIO_ATIVO"],
                column_types={k: pa.string() for k in _KEYS} | {"QT_BENEFICIARIO_ATIVO": pa.int64()}),
        )
        grouped = table.group_by(list(_KEYS)).aggregate([("QT_BENEFICIARIO_ATIVO", "sum")])
        parts.append(grouped.append_column("file_uf", pa.array([uf] * grouped.num_rows, pa.string())))
    whole = pa.concat_tables(parts)
    return whole.rename_columns(["municipality", "sex", "age_band", "coverage", "active", "file_uf"])


def summary(table: pa.Table) -> dict[str, Any]:
    import pyarrow.compute as pc

    out: dict[str, Any] = {"rows": table.num_rows, "total": pc.sum(table.column("active")).as_py()}
    for coverage in sorted(set(table.column("coverage").to_pylist()), key=str):
        part = table.filter(pc.equal(table.column("coverage"), coverage))
        out[str(coverage)] = pc.sum(part.column("active")).as_py()
    return out
