"""How a result is shown: one declarative step, applied last (ADR-0084).

The engine always produces the CANONICAL form. Every coded column keeps its raw
code, and its decoded label sits beside it as ``<column>_label``. That form
exists for machines: codes join, group and filter stably across vintages, while
labels change wording between editions.

A person wants the opposite: ``Sexo (SEXO)`` as a header and ``Masculino (1)``
as a value, the meaning first and the original code kept in parentheses, so
nothing is lost and anything can be traced back to the filed record. Both are
one :class:`Presentation` applied to the canonical table:

- ``values``: a template for a coded cell, with fields ``{label}`` and ``{code}``;
- ``unlabelled``: the template for a code no table decodes. The default keeps it
  VISIBLY undecoded (``9 (?)``): a guessed or blank label would be worse;
- ``names``: a template for a header, with ``{name}`` (the variable's documented
  name) and ``{code}`` (the column as filed);
- ``language``: ``pt`` names from the layout documents, ``en`` translated ones;
- ``companions``: keep the ``_label`` columns as they are (the canonical form).

Presets cover the usual needs, and any field can be overridden per call or by a
persistent default (``pegasus-data config set presentation <preset>``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any, Literal

import pyarrow as pa

LABEL_SUFFIX = "_label"


@dataclass(frozen=True, slots=True)
class Presentation:
    values: str = "{label} ({code})"
    unlabelled: str = "{code} (?)"
    names: str = "{name} ({code})"
    language: Literal["pt", "en"] = "pt"
    #: Keep ``<column>`` and ``<column>_label`` apart instead of applying the
    #: value template: the canonical, machine-oriented form.
    companions: bool = False
    #: Drop every label: raw codes as filed.
    codes_only: bool = False


PRESETS: dict[str, Presentation] = {
    # The default: meaning first, the original code kept in parentheses.
    "readable": Presentation(),
    # Codes as filed, with each label as a companion column: for analysis code
    # that joins, groups and filters on codes.
    "analysis": Presentation(names="{code}", companions=True),
    # Only labels; the codes are gone from the cells (still in the headers).
    "labels": Presentation(values="{label}", unlabelled="{code} (?)", names="{name}"),
    # Nothing decoded: the records exactly as DATASUS filed them.
    "codes": Presentation(names="{code}", codes_only=True),
}


def resolve(spec: str | Presentation | Mapping[str, Any] | None, default: str = "readable") -> Presentation:
    """A preset name, a :class:`Presentation`, or a mapping of overrides on the default."""
    if spec is None:
        spec = default
    if isinstance(spec, Presentation):
        return spec
    if isinstance(spec, str):
        try:
            return PRESETS[spec]
        except KeyError:
            raise ValueError(f"unknown presentation {spec!r}; presets: {sorted(PRESETS)}") from None
    if isinstance(spec, Mapping):
        base = resolve(spec.get("preset"), default) if "preset" in spec else resolve(default)
        fields = {k: v for k, v in spec.items() if k != "preset"}
        unknown = set(fields) - set(Presentation.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown presentation field(s) {sorted(unknown)}")
        return replace(base, **fields)
    raise TypeError(f"presentation must be a preset name, a Presentation or a mapping, not {type(spec).__name__}")


#: A leading code inside a label: "24 124-4 Município", "159 ATENCAO PRIMARIA",
#: "01 VINCULO …", "70-ESF". Two or more digits, or a hyphen or dot, followed by
#: a CAPITALISED word, so quantities survive: "22 a 27 semanas", "10 dias".
_EMBEDDED_CODE = re.compile(r"^(?:(?:\d{2,}|\d+[.\-]\d*)[\s\-]*)+(?=[A-ZÀ-Ý][A-Za-zÀ-ÿ])")


_PLACEHOLDER = re.compile(r"^\d*([a-zA-Z])\1{2,}\s+")


def clean_label(label: str) -> str:
    """A label without the codes DATASUS tables embed in it, segment by segment.

    ``159 ATENCAO PRIMARIA / 001 ATENCAO PRIMARIA`` becomes ``ATENCAO PRIMARIA /
    ATENCAO PRIMARIA``. Applied when showing a label; the canonical ``_label``
    column keeps the table's text as it is.
    """
    label = _PLACEHOLDER.sub("", label.strip()) or label  # "16eeee AP - …" (a TabWin range mask)
    parts = [_EMBEDDED_CODE.sub("", part.strip()) or part.strip() for part in label.split(" / ")]
    return " / ".join(parts)


def _plain(code: str) -> str:
    """A code without its punctuation: ``O80.0`` and ``O800`` are one code."""
    return "".join(ch for ch in code if ch.isalnum()).upper()


def _render_values(
    codes: pa.ChunkedArray | pa.Array,
    labels: pa.ChunkedArray | pa.Array,
    p: Presentation,
    shown: Mapping[str, str] | None = None,
) -> pa.Array:
    """``shown`` replaces the code printed beside a label (a municipality's
    6-digit code by its 7-digit IBGE code); the label lookup already happened."""
    # Formatted once per distinct (code, label), in Arrow up to that point: a
    # year of a 38-column file is 1.4 million cells and a few thousand
    # distinct pairs (ADR-0097). \x01 stands for null; neither byte occurs in
    # a code or a label.
    import pyarrow.compute as pc

    codes_s = pc.fill_null(pc.cast(codes, pa.string()), "\x01")
    labels_s = pc.fill_null(pc.cast(labels, pa.string()), "\x01")
    pairs = pc.binary_join_element_wise(codes_s, labels_s, "\x00")
    if isinstance(pairs, pa.ChunkedArray):
        pairs = pairs.combine_chunks()
    encoded = pc.dictionary_encode(pairs)
    shown_values: list[str | None] = []
    for pair in encoded.dictionary.to_pylist():
        code, _, label = pair.partition("\x00")
        code_v = None if code == "\x01" else code
        label_v = None if label == "\x01" else label
        if shown and code_v is not None:
            code_v = shown.get(code_v, code_v)
        shown_values.append(_render_value(code_v, label_v, p))
    return pc.take(pa.array(shown_values, type=pa.string()), encoded.indices)


def _render_value(code: object, label: object, p: Presentation) -> str | None:
    """One cell: ``label (code)`` by the template, ``code (?)`` when unlabelled."""
    if code is None or str(code).strip() == "":
        return None
    if label is None or str(label).strip() == "":
        return p.unlabelled.format(code=code, label="")
    text = str(label)
    tail = re.search(r"\(([A-Z0-9]{3,})\)$", text)
    if " | " in text or text.endswith(" (?)") or (tail and tail.group(1) in str(code) and tail.group(1) != str(code)):
        # A multi-valued column already writes each token as
        # "label (code)"; appending the raw string would repeat them.
        return text
    # Many tables already write the code into the label: BR_MUNICIPALFA
    # "120001 Acrelândia, AC", CID-10 "O80.0 Parto espontaneo cefalico"
    # for O800. Do not print it twice when the template shows the code.
    if "{code}" in p.values:
        head, _, rest = text.partition(" ")
        if rest and _plain(head) == _plain(str(code)):
            text = rest.lstrip(" -–")
    return p.values.format(code=code, label=clean_label(text))


def present(
    table: pa.Table,
    spec: str | Presentation | Mapping[str, Any] | None = None,
    *,
    names: Mapping[str, tuple[str | None, str | None]] | None = None,
    default: str = "readable",
) -> pa.Table:
    """Apply a presentation to a canonical table.

    ``names`` maps a column (upper case) to its (Portuguese, English) documented
    name; a column with neither is headed by its code.
    """
    p = resolve(spec, default)
    raw = set(table.schema.names)
    columns: list[pa.ChunkedArray] = []
    headers: list[str] = []
    for name in table.schema.names:
        is_label = name.endswith(LABEL_SUFFIX) and name[: -len(LABEL_SUFFIX)] in raw
        if is_label and not p.companions:
            continue  # folded into its code column below, or dropped
        column = table.column(name)
        base = name[: -len(LABEL_SUFFIX)] if is_label else name
        if not is_label and f"{name}{LABEL_SUFFIX}" in raw and not p.companions and not p.codes_only:
            municipal = name.upper() in getattr(names, "municipal", frozenset())
            column = _render_values(column, table.column(f"{name}{LABEL_SUFFIX}"), p, _ibge7() if municipal else None)
        pt, en = (names or {}).get(base.upper(), (None, None))
        documented = (en or pt) if p.language == "en" else (pt or en)
        header = p.names.format(name=documented or base, code=base) if documented else base
        if is_label:
            header = f"{header}{LABEL_SUFFIX}" if p.names == "{code}" else f"{header} [rótulo]"
        columns.append(column)
        headers.append(header)
    seen: dict[str, int] = {}
    unique: list[str] = []
    for h in headers:
        seen[h] = seen.get(h, 0) + 1
        unique.append(h if seen[h] == 1 else f"{h} [{seen[h]}]")
    return pa.Table.from_arrays(columns, names=unique)


class ColumnNames(dict):  # type: ignore[type-arg]
    """``COLUMN -> (official_name, translated_name)``, plus which columns hold
    municipality codes (their shown code is the 7-digit IBGE code)."""

    municipal: frozenset[str] = frozenset()


#: Tables whose codes are municipalities (DATASUS files the 6-digit form).
_MUNICIPAL_TABLES = ("BR_MUNIC", "MUNIC")


def documented_names(store: Any, system: str) -> ColumnNames:
    """The curated names of a system's columns, and its municipality columns."""
    from .semantics.curation import load_variable_docs

    docs = load_variable_docs(store, system)
    out = ColumnNames({name: (doc.official_name, doc.translated_name) for name, doc in docs.items()})
    out.municipal = frozenset(
        name for name, doc in docs.items()
        if any(str(c).upper().startswith(_MUNICIPAL_TABLES) for c in [doc.codelist, *doc.codelists] if c)
    )
    return out


@lru_cache(maxsize=1)
def _ibge7() -> dict[str, str]:
    """6-digit DATASUS municipality code -> 7-digit IBGE code (with check digit)."""
    from importlib.resources import files as _files

    import pyarrow.parquet as pq

    t = pq.read_table(str(_files("pegasus_data.resources") / "municipalities.parquet"), columns=["code6", "code7"])
    return dict(zip(t.column("code6").to_pylist(), t.column("code7").to_pylist(), strict=True))


__all__ = ["LABEL_SUFFIX", "PRESETS", "ColumnNames", "Presentation", "documented_names", "present", "resolve"]
