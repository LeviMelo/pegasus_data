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
    target = _root(settings) / manifest.product / manifest.version
    if target.exists():
        raise FileExistsError(f"{manifest.product} {manifest.version} exists; a version is never overwritten")
    target.mkdir(parents=True)
    meta = {b"tier": b"modelled", b"product": manifest.product.encode(), b"version": manifest.version.encode()}
    schema = table.schema.with_metadata({**(table.schema.metadata or {}), **meta})
    with pq.ParquetWriter(target / "estimates.parquet", schema, compression="zstd") as writer:
        writer.write_table(table.replace_schema_metadata(schema.metadata))
        for chunk in rest or ():
            writer.write_table(chunk.replace_schema_metadata(schema.metadata))
    (target / "manifest.json").write_text(json.dumps(asdict(manifest), indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    return target


def read_modelled(product: str, version: str | None = None, *, settings: Any) -> tuple[pa.Table, dict[str, Any]]:
    """A modelled product and its manifest; the latest version unless one is named."""
    base = _root(settings) / product
    versions = sorted(p.name for p in base.iterdir()) if base.exists() else []
    if not versions:
        raise FileNotFoundError(f"no modelled product {product!r}")
    chosen = version or versions[-1]
    folder = base / chosen
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    return pq.read_table(folder / "estimates.parquet"), manifest
