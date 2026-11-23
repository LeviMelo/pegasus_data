"""One reading of a category from its label: the canonical sex, and the labels a code carries in a dataset and year.

A code means what its codelist says (SIH codes sex 1/3, SIM and SINASC 1/2, ANS M/F), so a category is read from the
label, and from the whole label: ``curation/categories.yml`` maps each spelling to its category. A label the map does not
hold is unknown (None), never another category (it was read by its first letter: "Menino" was male, a third value
beginning with f was female).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc

from ..catalog.store import CatalogStore
from ..config import curation_root, load_settings
from .curation import read_yaml


def sex_spellings() -> tuple[list[str], list[str]]:
    """``(spellings, categories)`` of ``curation/categories.yml``'s ``sex``: parallel lists, spellings lower case."""
    declared = read_yaml(curation_root() / "categories.yml", shared=True)["sex"]
    pairs = [(str(spelling).lower(), str(category)) for category, spellings in declared.items() for spelling in spellings]
    return [s for s, _ in pairs], [c for _, c in pairs]


def canonical_sex(labels: pa.Array | pa.ChunkedArray) -> pa.Array:
    """Each label as ``M`` or ``F``; null when the label is missing or outside the declared spellings (ignorado)."""
    spellings, categories = sex_spellings()
    text = pc.utf8_lower(pc.utf8_trim_whitespace(pc.cast(labels, pa.string())))
    return pc.take(pa.array(categories, pa.string()), pc.index_in(text, value_set=pa.array(spellings, pa.string())))


def code_labels(dataset: str, column: str, year: int, codes: Sequence[str | None], root: str | Path | None = None) -> dict[str, str]:
    """``code -> label`` of the distinct ``codes`` of ``column`` in ``dataset``'s ``year`` (the codelist the renderer
    chooses for that family and year); a code the codelist does not decode is absent."""
    from .._request import parse_dataset
    from ..view import codelist_levels

    settings = load_settings(root=Path(root) if root else None)
    system, series = parse_dataset(dataset)
    present = sorted({str(c).strip() for c in codes if c is not None and str(c).strip()})
    store = CatalogStore.shared(settings.catalog_path)
    try:
        return codelist_levels(column, store=store, lake_root=settings.lake_dir, system=system,
                               family_id=f"{system}.{series}", year=year, codes=present)
    finally:
        store.close()
