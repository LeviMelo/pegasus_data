"""The Census as populations, read from the SIDRA fact store.

``census_age_sex`` is the series ``CENSO``: municipality × sex × single year of age in POPSVS's schema
(plus ``status``). It is a projection of the stitched series ``population_age_sex``
(`curation/sidra/series.yml`; tables 1552 for 2000, 1378 for 2010, 9514 for 2022), so the planning, the
caching, the symbols (a cell IBGE did not publish is a null with its status, never a zero) and the
check against each table's own totals are the general interface's, not a second mechanism.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from .series import build_series, fetch_series, validate_series
from .session import Sidra

__all__ = ["build_census", "census_age_sex"]

_SEX_CODE = {"male": "1", "female": "2"}


def census_age_sex(sidra: Sidra, year: int) -> pa.Table:
    """The year's municipality × sex × age table, in POPSVS's schema, from stored facts."""
    series = build_series(sidra, "population_age_sex", only=[f"census_{year}"])
    series = series.filter(pc.equal(series.column("period"), str(year)))
    if series.num_rows == 0:
        raise LookupError(f"no census facts for {year}; run `pegasus-data sidra series population_age_sex --fetch`")
    sex = pc.take(pa.array(list(_SEX_CODE.values()), pa.string()),
                  pc.index_in(series.column("sex"), pa.array(list(_SEX_CODE), pa.string())))
    return pa.table({
        "municipality": pc.cast(series.column("locality"), pa.int64()),
        "year": pa.array([year] * series.num_rows, pa.int64()),
        "sex": sex,
        "age": pc.cast(series.column("age"), pa.int64()),
        "population": pc.cast(series.column("value"), pa.int64()),    # counts; a null stays null
        "status": series.column("status"),
        "_source_path": pc.binary_join_element_wise(pa.scalar("sidra:"), pc.cast(series.column("table"), pa.string()), ""),
    })


def build_census(sidra: Sidra, population_dir: Path, years: list[int] | None = None, log=print) -> dict[int, Any]:
    """Fetch the Census by municipality × sex × single age (SIDRA tables 1552, 1378, 9514) and write the series
    ``CENSO`` to ``population_dir/CENSO/censo_<year>.parquet`` in POPSVS's schema, checked against each table's own totals.

    A cell IBGE did not publish is a null in ``population`` (its reason is ``status`` in the fact store), never a zero.
    """
    import pyarrow.parquet as pq

    out_dir = Path(population_dir) / "CENSO"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[int, Any] = {}
    for year in years or (2000, 2010, 2022):
        only = [f"census_{year}"]
        fetch_series(sidra, "population_age_sex", log=log, only=only)
        table = census_age_sex(sidra, year)
        check = validate_series(sidra, "population_age_sex", only=only)[0]
        symbols = {k: v for k, v in zip(*[table.column("status").value_counts().field(i).to_pylist() for i in (0, 1)], strict=True)
                   if k not in ("value", "zero")}
        pq.write_table(table.drop_columns(["status"]), out_dir / f"censo_{year}.parquet", compression="zstd")
        report[year] = {"cells": table.num_rows, "municipalities": check["checked"] + check["total_missing"],
                        "population": int(pc.sum(table.column("population")).as_py()),
                        "mismatched_municipalities": check["mismatched"], "examples": check["examples"],
                        "totals_without_value": check["total_missing"], "symbols": symbols}
        log(f"CENSO {year}: {report[year]}")
    return report
