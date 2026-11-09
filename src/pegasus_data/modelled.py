"""The modelled tier: estimates, typed as estimates, never in place of an official series.

pegasus_data's observed tier answers what exists and what it means. The
modelled tier answers what was there and how it was recorded: the population
account, system completeness, race misclassification, the SUS-dependent
population (DESIGN §2 and §5 of PegaSUS; ADR-0139). A modelled product is
written and read only through this module, which enforces what makes it one:

* it lives under ``<lake>/modelled/<product>/<version>/``, never beside an
  observed table, and a version is never overwritten;
* its manifest says ``tier: modelled``, the model and its version, the
  observed inputs (with their data versions), the uncertainty columns, and
  the validation evidence;
* every estimate column has its uncertainty columns beside it (an interval or
  draws); a point estimate alone is refused;
* it never takes the name of an official series: POPSVS stays served as
  published (``load_population``), and an estimate of it is a different
  product.

Estimates are floats whose low bits are model noise, which zstd cannot shrink
alone (the population account stored at 0.94 of its raw size): float columns
are written in BYTE_STREAM_SPLIT, which groups each byte position of the
values so the exponent and high mantissa bytes compress (one year of
population-account-6: 0.77 of the size, lossless; 2026-10-10). `reencode`
rewrites a version written before, value for value.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

#: Official series an estimate may sit beside but never be named as.
OFFICIAL_SERIES = frozenset({"POPSVS", "POP", "CENSO", "SIM", "SINASC", "SIH", "SINAN"})
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class ModelledManifest:
    product: str
    version: str
    model: str
    estimates: dict[str, list[str]]      # estimate column -> its uncertainty columns
    inputs: dict[str, str]                # observed input -> its data version
    validation: str                       # where the evidence that it beats the baseline is written
    tier: str = "modelled"
    notes: list[str] = field(default_factory=list)
    #: the axes of a row: the column of its place (a municipality's 7 digits, an area "A+B", or a state's code), of its
    #: period ("" for a product of no period), and its strata; every other column is an estimate, its uncertainty or an
    #: annotation (``basis``, ``horizon``). A cube reads these (`cubes._modelled`), never guesses them.
    place: str = ""
    period: str = ""
    strata: list[str] = field(default_factory=list)
    #: the estimates whose point values add up over places and strata (counts of people); a share or a probability does
    #: not, and no interval bound ever does
    additive: list[str] = field(default_factory=list)


def _root(settings: Any) -> Path:
    return Path(settings.lake_dir) / "modelled"


def write_modelled(table: pa.Table | Iterable[pa.Table], manifest: ModelledManifest, *, settings: Any) -> Path:
    """Write one version of a modelled product, refusing anything that would pass for observed data.

    ``table`` may be an iterator of tables with one schema (a product too large to hold at once): they are written as the
    row groups of one file, and the estimate columns are checked against the first."""
    if not isinstance(table, pa.Table):
        chunks = iter(table)
        first = next(chunks)
        table, rest = first, chunks
    else:
        rest = None
    if not _NAME.match(manifest.product):
        raise ValueError(f"a product name is lower snake_case: {manifest.product!r}")
    if manifest.product.upper() in OFFICIAL_SERIES or manifest.product.upper().split("_")[0] in OFFICIAL_SERIES:
        raise ValueError(f"{manifest.product!r} takes the name of an official series; name the estimate for what it is")
    if not manifest.estimates:
        raise ValueError("a modelled product declares its estimate columns")
    for column, uncertainty in manifest.estimates.items():
        missing = [c for c in (column, *uncertainty) if c not in table.column_names]
        if missing:
            raise ValueError(f"{column}: columns {missing} are not in the table")
        if not uncertainty:
            raise ValueError(f"{column}: an estimate without its uncertainty is refused")
    if not manifest.validation:
        raise ValueError("a modelled product names its validation evidence")
    if not manifest.place:
        raise ValueError("a modelled product declares its axes: the column of its place (and its period and strata)")
    axes = [c for c in (manifest.place, manifest.period, *manifest.strata) if c]
    absent = [c for c in axes if c not in table.column_names]
    if absent or set(manifest.additive) - set(manifest.estimates):
        raise ValueError(f"declared axes {absent} not in the table, or additive {manifest.additive} not estimates")
    import os
    import shutil

    target = _root(settings) / manifest.product / manifest.version
    if target.exists():
        raise FileExistsError(f"{manifest.product} {manifest.version} exists; a version is never overwritten")
    # written in a staging directory and renamed whole: a killed write left `<version>/estimates.parquet` without a
    # footer and no manifest, `FileExistsError` on the rerun and the half-written version the latest `read_modelled`
    # picked (2026-10-14 review)
    staging = target.with_name(f"{manifest.version}.{os.getpid()}.staging")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    meta = {b"tier": b"modelled", b"product": manifest.product.encode(), b"version": manifest.version.encode()}
    schema = table.schema.with_metadata({**(table.schema.metadata or {}), **meta})
    try:
        with pq.ParquetWriter(staging / "estimates.parquet", schema, **_encoding(schema)) as writer:
            writer.write_table(table.replace_schema_metadata(schema.metadata))
            for chunk in rest or ():
                writer.write_table(chunk.replace_schema_metadata(schema.metadata))
        (staging / "manifest.json").write_text(json.dumps(asdict(manifest), indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def read_modelled(product: str, version: str | None = None, *, settings: Any) -> tuple[pa.Table, dict[str, Any]]:
    """A modelled product and its manifest; the latest version unless one is named."""
    base = _root(settings) / product
    versions = sorted((p.name for p in base.iterdir() if (p / "manifest.json").is_file()), key=_version_order) \
        if base.exists() else []
    if not versions:
        raise FileNotFoundError(f"no modelled product {product!r}")
    chosen = version or versions[-1]
    folder = base / chosen
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    return pq.read_table(folder / "estimates.parquet"), manifest


def _version_order(name: str) -> tuple[int, str]:
    """Versions by their trailing number, not as text (``-10`` sorted before ``-6``); only a version with a manifest (a
    complete write) is one."""
    import re

    found = re.search(r"(\d+)$", name)
    return (int(found.group(1)) if found else -1, name)


def _encoding(schema: pa.Schema) -> dict[str, Any]:
    """Parquet writer options: zstd; floats in BYTE_STREAM_SPLIT, every other column dictionary-encoded."""
    floats = [f.name for f in schema if pa.types.is_floating(f.type)]
    return {"compression": "zstd", "compression_level": 9, "use_byte_stream_split": floats or False,
            "use_dictionary": [f.name for f in schema if f.name not in floats]}


def reencode(product: str, version: str, *, settings: Any) -> dict[str, Any]:
    """Rewrite a version's estimates with `_encoding`, row group by row group; the new file replaces the old only when
    every row group reads back equal to the one it was written from. The version's content is unchanged."""
    import os

    path = _root(settings) / product / version / "estimates.parquet"
    src = pq.ParquetFile(path)
    tmp = path.with_name(f"estimates.{os.getpid()}.parquet.tmp")
    before = path.stat().st_size
    with pq.ParquetWriter(tmp, src.schema_arrow, **_encoding(src.schema_arrow)) as writer:
        for g in range(src.num_row_groups):
            writer.write_table(src.read_row_group(g))
    new = pq.ParquetFile(tmp)
    if new.metadata.num_rows != src.metadata.num_rows or new.num_row_groups != src.num_row_groups:
        tmp.unlink()
        raise ValueError(f"{version}: the rewrite does not have the rows of the original")
    for g in range(src.num_row_groups):
        if not new.read_row_group(g).equals(src.read_row_group(g)):
            tmp.unlink()
            raise ValueError(f"{version}: row group {g} differs after the rewrite")
    del new, src
    tmp.replace(path)
    return {"version": version, "bytes_before": before, "bytes_after": path.stat().st_size}
