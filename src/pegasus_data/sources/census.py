"""The Census as a population series: municipality × sex × single year of age (``CENSO``).

IBGE's SIDRA serves both censuses at municipal level by sex and single year of age:

- 2022: table 9514 (variable 93; sex 2 [4 men, 5 women]; age 287; age declaration 286 at its
  total 113635);
- 2010: table 1378, the universe (variable 93; situation 1 and household condition 455 at their
  total 0; sex 2 [4, 5]; age 287);
- 2000: table 1552 (variable 93; situation 1 and age declaration 286 at their total 0; sex 2 with its own ids
  [92956, 92957]; age 287). It is served on the current list of 5,570 municipalities, and the 58 created after
  2000 have no value (SIDRA's ``...``, "not available"): those cells are kept as nulls, never zeros.

Ages are the classification's single-year categories ("Menos de 1 ano" = 0, "n ano(s)",
"100 anos ou mais" = 100); its groups and its sub-year months are not ages and are left out.
SIDRA's symbols are read as IBGE defines them: ``-`` is an absolute zero; ``...`` (not available), ``..`` (not
applicable) and ``X`` (withheld) are no value. The series lands in ``lake/population/CENSO/`` in POPSVS's
schema, so ``load_population(series="CENSO")`` serves it, and every municipality's total is checked against
the table's own total.
"""

from __future__ import annotations

import gzip
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
TABLES = {
    2022: {"table": 9514, "fixed": "286[113635]", "sex": {"4": "1", "5": "2"}, "totals": ("6794", "100362")},
    2010: {"table": 1378, "fixed": "1[0]|455[0]", "sex": {"4": "1", "5": "2"}, "totals": ("0", "0")},
    # 2000 by single age: table 1552 (2000 and 2010), whose sex categories have their own ids
    2000: {"table": 1552, "fixed": "1[0]|286[0]", "sex": {"92956": "1", "92957": "2"}, "totals": ("0", "0")},
}
UA = {"User-Agent": "Mozilla/5.0 (pegasus-data)"}
#: SIDRA answers at most this many values per request (localities × categories × periods).
SIDRA_VALUE_LIMIT = 50_000


def _get(url: str, timeout: float = 300.0, attempts: int = 4) -> Any:
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                body = r.read()
            if body[:2] == bytes((0x1F, 0x8B)):     # IBGE sends gzip without Content-Encoding
                body = gzip.decompress(body)
            if body.lstrip()[:1] == b"<":            # IBGE's firewall answers a rejected URL with HTML, status 200
                raise RuntimeError(f"IBGE rejected the request (HTML page, status 200): {url[:120]}…")
            return json.loads(body.decode("utf-8"))
        except Exception:  # noqa: BLE001 - retried, then raised
            if attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))
    return None


def ages(table: int) -> dict[str, int]:
    """Category id -> single year of age, from the table's own metadata (classification 287)."""
    meta = _get(f"{BASE}/{table}/metadados")
    cats = next(c for c in meta["classificacoes"] if c["id"] == 287)["categorias"]
    out: dict[str, int] = {}
    for c in cats:
        name = c["nome"].strip()
        if name == "Menos de 1 ano":
            out[str(c["id"])] = 0
        elif name == "100 anos ou mais":
            out[str(c["id"])] = 100
        else:
            m = re.fullmatch(r"(\d+) anos?", name)
            if m:
                out[str(c["id"])] = int(m.group(1))
    if sorted(out.values()) != list(range(101)):
        raise ValueError(f"table {table}: single ages are not exactly 0..100: {sorted(out.values())[:5]}…")
    return out


def _answer(table: int, year: int, uf: int, ids: list[str], fixed: str, sexes: list[str]) -> list[Any]:
    """One state's answer for a set of ages. The chunk is planned under SIDRA's value limit; a
    request it still refuses with a server error is split in half and retried (a safety net, not
    the plan: Minas Gerais at 853 × 2 × 34 = 58,004 values was refused, 2026-10-04)."""
    url = (f"{BASE}/{table}/periodos/{year}/variaveis/93?localidades=N6[N3[{uf}]]"
           f"&classificacao=2[{','.join(sexes)}]|287[{','.join(ids)}]|{fixed}")
    try:
        return _get(url, attempts=2)
    except urllib.error.HTTPError as exc:
        if exc.code < 500 or len(ids) == 1:
            raise
        half = len(ids) // 2
        return _answer(table, year, uf, ids[:half], fixed, sexes) + _answer(table, year, uf, ids[half:], fixed, sexes)


#: SIDRA's symbols for a value that is not a number (IBGE's tabulation convention). ``-`` is an
#: absolute zero, a count of nobody; every other symbol is *no value*, and no value is not zero.
SIDRA_ZERO = "-"
SIDRA_NO_VALUE = {"...": "not available", "..": "not applicable", "X": "withheld to protect a respondent",
                  "": "empty", None: "absent"}


def _value(raw: str | None, symbols: dict[str, int]) -> int | None:
    """One SIDRA cell as a count: digits are the count, ``-`` is zero, any other symbol is a recorded gap (None)."""
    if raw is not None and raw.strip().isdigit():
        return int(raw)
    if raw == SIDRA_ZERO:
        return 0
    key = "None" if raw is None else raw
    symbols[key] = symbols.get(key, 0) + 1
    if raw not in SIDRA_NO_VALUE:
        raise ValueError(f"SIDRA returned a value this builder does not know how to read: {raw!r}")
    return None


def _municipalities_per_uf() -> dict[int, int]:
    """Municipalities per state, from IBGE's localities API (the request plan needs them)."""
    data = _get("https://servicodados.ibge.gov.br/api/v1/localidades/municipios")
    out: dict[int, int] = {}
    for m in data:
        uf = int(str(m["id"])[:2])
        out[uf] = out.get(uf, 0) + 1
    return out


def build_census(population_dir: Path, years: list[int] | None = None, log=print) -> dict[str, Any]:
    """Fetch the census by municipality × sex × single age into ``population_dir/CENSO``."""
    out_dir = Path(population_dir) / "CENSO"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for year in years or sorted(TABLES):
        spec = TABLES[year]
        table = spec["table"]
        age_of = ages(table)
        ids = list(age_of)
        rows: list[tuple[int, str, int, int | None]] = []
        symbols: dict[str, int] = {}
        municipalities = _municipalities_per_uf()
        for uf in sorted(municipalities):
            # the chunk is planned from SIDRA's 50,000-value limit: municipalities × 2 sexes × ages
            step = max(1, SIDRA_VALUE_LIMIT // (municipalities[uf] * 2))
            for i in range(0, len(ids), step):
                for result in _answer(table, year, uf, ids[i:i + step], spec["fixed"], list(spec["sex"])):
                    for res in result["resultados"]:
                        cls = {c["id"]: next(iter(c["categoria"])) for c in res["classificacoes"]}
                        sex = spec["sex"][cls["2"]]
                        age = age_of[cls["287"]]
                        for s in res["series"]:
                            n = _value(s["serie"].get(str(year)), symbols)
                            rows.append((int(s["localidade"]["id"]), sex, age, n))
            log(f"CENSO {year} UF {uf}: {len(rows)} cells so far")
        tab = pa.table({"municipality": pa.array([r[0] for r in rows], pa.int64()),
                        "year": pa.array([year] * len(rows), pa.int64()),
                        "sex": pa.array([r[1] for r in rows], pa.string()),
                        "age": pa.array([r[2] for r in rows], pa.int64()),
                        "population": pa.array([r[3] for r in rows], pa.int64()),
                        "_source_path": pa.array([f"sidra:{table}"] * len(rows), pa.string())})
        # the check: every municipality's sum over sex and age against the table's own total
        totals = _get(f"{BASE}/{table}/periodos/{year}/variaveis/93?localidades=N6[all]"
                      f"&classificacao=2[{spec['totals'][0]}]|287[{spec['totals'][1]}]"
                      f"|{spec['fixed']}")
        gaps: dict[int, str] = {}
        published: dict[int, int] = {}
        for s in totals[0]["resultados"][0]["series"]:
            value = _value(s["serie"].get(str(year)), {})
            if value is None:
                gaps[int(s["localidade"]["id"])] = s["serie"].get(str(year)) or "absent"
            else:
                published[int(s["localidade"]["id"])] = value
        import pyarrow.compute as pc

        ours = tab.group_by("municipality").aggregate([("population", "sum")])    # a null cell is skipped
        sums = dict(zip(ours["municipality"].to_pylist(), ours["population_sum"].to_pylist(), strict=True))
        mism = [(m, v, published.get(m)) for m, v in sums.items() if m in published and published[m] != v]
        no_value = sorted({int(m) for m in pc.filter(tab["municipality"], pc.is_null(tab["population"])).to_pylist()})
        pq.write_table(tab, out_dir / f"censo_{year}.parquet", compression="zstd")
        report[year] = {"cells": tab.num_rows, "municipalities": len(published),
                        "population": int(pc.sum(tab["population"]).as_py()),
                        "published_total": sum(published.values()), "mismatched_municipalities": len(mism),
                        "examples": mism[:5], "symbols": symbols, "totals_without_value": len(gaps),
                        "municipalities_with_no_value": len(no_value), "no_value_examples": no_value[:10]}
        log(f"CENSO {year}: {report[year]}")
    return report
