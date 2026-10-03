"""Are SIH monetary fields in one unit across eras? (OQ-21)

Usage: python scripts/sih_money_units.py [UF] [FIRST_YEAR LAST_YEAR]
       (default AC 1992 2023)

SIH may bill in centavos in some eras and reais in others. For each year of
the SIH-RD microdata of one state (files by processing month, RD<UF>YYMM.dbc,
read directly from the HTTPS mirror of the DATASUS tree) the
script sums VAL_TOT and US_TOT, counts AIH rows, takes the median VAL_TOT per
AIH, and compares rows and money with TabNet's own totals for the same state
and the same processing year: "Morbidade Hospitalar do SUS - por local de
internacao" (hospital's state), form sih/cnv/miac.def (1984-2007, measures
Internacoes / Valor_Total) and sih/cnv/niac.def (2008 on, Internacoes /
Valor_total), row Ano_processamento, all files. Another state needs its own
form prefix (mi<uf>, ni<uf>). A ratio microdata/TabNet near 1 means one unit;
near 100 means centavos against reais.

Writes data/probes/sih/money_units_<UF>.json.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
import tempfile
import urllib.request
from pathlib import Path

from pegasus_data.decode.dbc import read_dbc
from pegasus_data.sources.tabnet import tabulate

OUT = Path(__file__).resolve().parents[1] / "data" / "probes" / "sih"
MIRROR = "https://datasus-ftp-mirror.nyc3.digitaloceanspaces.com"
CACHE = Path(tempfile.gettempdir()) / "sih_money_units"
FORMS = (("mi", "Valor_Total"), ("ni", "Valor_total"))


def _number(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def tabnet_series(uf: str) -> dict[int, dict[str, float]]:
    """{year: {"internacoes", "valor_total", "form"}} from both TabNet forms."""
    out: dict[int, dict[str, float]] = {}
    for prefix, money in FORMS:
        definition = f"sih/cnv/{prefix}{uf.lower()}.def"
        page = urllib.request.urlopen(f"http://tabnet.datasus.gov.br/cgi/deftohtm.exe?{definition}",
                                      timeout=60).read().decode("latin-1")
        block = re.search(r'<select[^>]*name="Arquivos"[^>]*>(.*?)</select>', page, re.S | re.I).group(1)
        files = re.findall(r'<option[^>]*value="([^"]*)"', block, re.I)
        for measure, key in (("Interna\xe7\xf5es", "internacoes"), (money, "valor_total")):
            for label, value in tabulate(definition, row="Ano_processamento", files=files, measure=measure)[1:]:
                if label.isdigit():
                    out.setdefault(int(label), {"form": definition})[key] = _number(value)
    return out


def _dbc(uf: str, year: int, month: int) -> Path | None:
    """The month's RD file from the HTTPS mirror (cached), None when absent."""
    yy = f"{year % 100:02d}{month:02d}"
    folder = "199201_200712" if year < 2008 else "200801_"
    name = f"RD{uf}{yy}.dbc"
    target = CACHE / name
    if not target.exists():
        url = f"{MIRROR}/SIHSUS/{folder}/Dados/{name}"
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
        except Exception:  # noqa: BLE001 - absent on the mirror is a result
            return None
        CACHE.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return target


def micro_year(uf: str, year: int) -> dict:
    """Rows and money of one processing year, read straight from the mirror's DBC files.

    ``query`` is avoided on purpose: for 2008-2014 it plans the XML/CSV
    representations, which the mirror does not hold, so those years would
    come back empty.
    """
    vals: dict[str, list[float]] = {"VAL_TOT": [], "US_TOT": []}
    rows, present, missing, columns = 0, [], [], set()
    for month in range(1, 13):
        path = _dbc(uf, year, month)
        if path is None:
            missing.append(month)
            continue
        present.append(month)
        table = read_dbc(path)
        columns.update(table.field_names)
        for batch in table.batches():
            rows += batch.num_rows
            for col in vals:
                if col in batch.schema.names:
                    vals[col] += [float(v) for v in batch.column(col).to_pylist() if v not in (None, "")]
    row: dict = {"rows": rows, "months_read": present, "months_missing": missing,
                 "has_VAL_TOT": "VAL_TOT" in columns, "has_US_TOT": "US_TOT" in columns}
    for col, series in vals.items():
        if series:
            row["sum_" + col] = sum(series)
            row["median_" + col] = statistics.median(series)
            row["n_" + col] = len(series)
    return row


def main() -> None:
    uf = sys.argv[1] if len(sys.argv) > 1 else "AC"
    first, last = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (1992, 2023)
    official = tabnet_series(uf)
    years = {}
    for year in range(first, last + 1):
        row = micro_year(uf, year)
        tab = official.get(year, {})
        row["tabnet"] = tab
        if tab and row.get("rows"):
            row["ratio_rows"] = row["rows"] / tab["internacoes"]
            if "sum_VAL_TOT" in row and tab.get("valor_total"):
                row["ratio_VAL_TOT"] = row["sum_VAL_TOT"] / tab["valor_total"]
        years[year] = row
        print(year, {k: v for k, v in row.items() if k != "tabnet"}, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"money_units_{uf}.json").write_text(json.dumps({"uf": uf, "source": MIRROR, "years": years},
                                                           indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
