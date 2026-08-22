"""Decode DATASUS data you already have.

A great deal of DATASUS microdata is already sitting on people's disks: exported
from TabNet, pulled with R's **microdatasus**, mailed by a colleague, downloaded
years ago from a link in a paper. It is all coded — `SEXO` is 1 and 3, `RACACOR`
is 01 through 05, `DIAG_PRINC` is `K808` — and the codelists that decode it are
in `.CNV` files nobody parses.

This module has those codelists: 19.9 million rows of them, scoped by system and
by validity window. Requiring someone to re-download data they already have in
order to reach that is an artificial toll. So the dictionary is a service in its
own right:

    translate(df, system="SIHSUS", year=2019)

Same rendering path as :func:`~pegasus_data.api.load` and
:func:`~pegasus_data.retrieve.fetch` — one implementation, so a column labelled
one way in a notebook is labelled the same way everywhere.

**What it will not do is guess.** Passing a table with no `system` is refused:
`SEXO=3` is Feminino in SIHSUS and means nothing in SINASC, so labelling without
knowing which system produced the row is how a wrong label gets published. The
year matters for the same reason, one level down — a code's meaning is a
function of when the row was filed — and a table whose year is not given is
labelled from the current vintage, which is stated in the report rather than
assumed silently.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa

from .config import Settings, load_settings
from .view import RenderReport, render_table

__all__ = ["translate", "TranslationImpossible"]


class TranslationImpossible(ValueError):
    """The table cannot be labelled, and saying why beats labelling it wrongly."""


def _as_arrow(data: Any) -> pa.Table:
    """Accept the shapes people actually have."""
    if isinstance(data, pa.Table):
        return data
    if isinstance(data, pa.RecordBatch):
        return pa.Table.from_batches([data])
    if isinstance(data, (str, Path)):
        path = Path(data)
        suffix = path.suffix.lower()
        if suffix in {".parquet", ".pq"}:
            import pyarrow.parquet as pq

            return pq.read_table(path)
        if suffix in {".csv", ".txt", ".tsv"}:
            import pyarrow.csv as pacsv

            delimiter = "\t" if suffix == ".tsv" else _sniff(path)
            parse = pacsv.ParseOptions(delimiter=delimiter)
            read = pacsv.ReadOptions(encoding="latin-1")
            # Every column as text, named explicitly. A code is not a number:
            # inferred typing reads MUNIC_RES as int64, `012345` becomes `12345`,
            # and the join against a 6-character reference table stops matching —
            # silently, returning unlabelled rows that look like missing data.
            # An empty `column_types` does NOT prevent inference; the columns
            # have to be named, so the header is read first.
            header = _header(path, delimiter)
            return pacsv.read_csv(
                path,
                parse_options=parse,
                read_options=read,
                convert_options=pacsv.ConvertOptions(
                    column_types=dict.fromkeys(header, pa.string()),
                    strings_can_be_null=True,
                ),
            )
        raise TranslationImpossible(f"cannot read {path.name}: unknown format {suffix!r}")
    to_arrow = getattr(data, "to_arrow", None)
    if callable(to_arrow):  # polars
        return to_arrow()
    try:  # pandas
        return pa.Table.from_pandas(data, preserve_index=False)
    except (TypeError, AttributeError) as exc:
        raise TranslationImpossible(
            f"cannot turn {type(data).__name__} into a table; pass an Arrow table, a "
            "pandas or polars DataFrame, or a path to a CSV or Parquet file"
        ) from exc


def _first_line(path: Path, *, sample: int = 65536) -> str:
    raw = path.open("rb").read(sample)
    if raw.startswith(b"\xef\xbb\xbf"):
        # Strip the BOM as bytes, before decoding. Read as latin-1 it becomes
        # three characters glued to the first column's name, and that column
        # then matches nothing.
        raw = raw[3:]
    return raw.decode("latin-1", "replace").split("\n", 1)[0].rstrip("\r")


def _sniff(path: Path) -> str:
    """DATASUS exports use ';' about as often as ','."""
    head = _first_line(path)
    return max((";", ",", "\t", "|"), key=head.count)


def _header(path: Path, delimiter: str) -> list[str]:
    """The column names, so every one of them can be forced to text."""
    return [
        part.strip().strip('"').strip()
        for part in _first_line(path).split(delimiter)
        if part.strip()
    ]


def translate(
    data: Any,
    *,
    system: str,
    series: str | None = None,
    year: int | None = None,
    profile: str = "analysis",
    render: Mapping[str, str] | None = None,
    headers: str | None = None,
    values: str | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    strict: bool = False,
    root: str | Path | None = None,
    settings: Settings | None = None,
    report: bool = False,
) -> pa.Table | tuple[pa.Table, RenderReport]:
    """Label a table of DATASUS data you already have.

    ``data`` may be an Arrow table, a pandas or polars DataFrame, or a path to a
    CSV or Parquet file. ``system`` is required — the same code means different
    things in different systems, and guessing is not available.

    ``year`` selects the vintage of the codelists. Omit it and the current
    vintage is used, which is correct for recent data and wrong for a 1998
    extract; the report says which was applied.

    Returns the labelled table; with ``report=True``, ``(table, RenderReport)``,
    where the report names every column that could not be labelled and why.
    """
    if not system or not str(system).strip():
        raise TranslationImpossible(
            "system is required: SEXO=3 is Feminino in SIHSUS and undefined in "
            "SINASC, so a table cannot be labelled without knowing which system "
            "produced it"
        )
    table = _as_arrow(data)
    if table.num_rows == 0:
        raise TranslationImpossible("the table has no rows to label")

    resolved = settings or load_settings(root=Path(root) if root else None)
    from .catalog.store import Catalog

    if not resolved.catalog_path.exists():
        raise TranslationImpossible(
            f"no catalog at {resolved.catalog_path}: labelling needs the codelists. "
            "Unpack a semantic bundle (`pegasus-data unpack`), or build one with "
            "`pegasus-data crawl && pegasus-data semantics`."
        )
    store = Catalog(resolved.catalog_path, read_only=True)
    try:
        # A local dictionary is no longer required: the package ships a label
        # pack and read_reference_table falls back to it. This used to refuse
        # outright and tell the caller to go and download a bundle they already
        # have — on a root where fetch(labels=True) was labelling happily.
        from .labelpack import seed_bindings

        if not store.count("dictionary"):
            store_rw = Catalog(resolved.catalog_path)
            try:
                seed_bindings(store_rw)
                if not store_rw.count("variable_docs"):
                    from .ontology import CURATION
                    from .semantics.curation import load_curation

                    load_curation(store_rw, CURATION)
            except Exception:  # noqa: BLE001 - degrade to whatever is present
                pass
            finally:
                store_rw.close()
        else:
            _ensure_reference(store, resolved)
        family_id = _family_for(store, system, series, table.column_names)
        rendered, render_report = render_table(
            table,
            store=store,
            lake_root=resolved.lake_dir,
            system=str(system).upper(),
            family_id=family_id,
            profile=profile,
            render=render,
            headers=headers,
            values=values,
            companions=companions,
            derived=derived,
            year=year,
            strict=strict,
        )
        return (rendered, render_report) if report else rendered
    finally:
        store.close()


def _ensure_reference(store, settings: Settings) -> None:
    """Materialise the Parquet lookups the join needs, once."""
    from .persist.reference import available_tables, write_reference_tables

    if available_tables(settings.lake_dir):
        return
    write_reference_tables(store, settings.lake_dir, compression=settings.compression)


def _family_for(store, system: str, series: str | None, columns: Sequence[str]) -> str | None:
    """Which schema generation this table looks like, if one matches exactly.

    Naming the family lets family-scoped bindings apply, which are more specific
    than the system-wide ones. A table that matches nothing — a subset of
    columns, someone's edited extract — gets system-scoped labelling instead,
    which is the honest fallback rather than an error: the codes still mean what
    they mean.
    """
    from .inventory.families import schema_signature

    signature = schema_signature(list(columns))
    clause = " AND series = ?" if series else ""
    params: list[object] = [str(system).upper(), signature]
    if series:
        params.insert(1, str(series).upper())
    rows = store.query(
        f"SELECT family_id FROM families WHERE system = ?{clause} AND schema_signature = ?",
        params,
    )
    return str(rows[0]["family_id"]) if rows else None
