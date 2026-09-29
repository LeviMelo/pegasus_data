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

from collections.abc import Mapping
from dataclasses import dataclass, replace
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


def _plain(code: str) -> str:
    """A code without its punctuation: ``O80.0`` and ``O800`` are one code."""
    return "".join(ch for ch in code if ch.isalnum()).upper()


def _render_values(codes: pa.ChunkedArray | pa.Array, labels: pa.ChunkedArray | pa.Array, p: Presentation) -> pa.Array:
    codes_py = codes.to_pylist()
    labels_py = labels.to_pylist()
    out: list[str | None] = []
    for code, label in zip(codes_py, labels_py, strict=True):
        if code is None or str(code).strip() == "":
            out.append(None)
        elif label is None or str(label).strip() == "":
            out.append(p.unlabelled.format(code=code, label=""))
        else:
            text = str(label)
            # Many tables already write the code into the label: BR_MUNICIPALFA
            # "120001 Acrelândia, AC", CID-10 "O80.0 Parto espontaneo cefalico"
            # for O800. Do not print it twice when the template shows the code.
            if "{code}" in p.values:
                head, _, rest = text.partition(" ")
                if rest and _plain(head) == _plain(str(code)):
                    text = rest.lstrip(" -–")
            out.append(p.values.format(code=code, label=text))
    return pa.array(out, type=pa.string())


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
            column = _render_values(column, table.column(f"{name}{LABEL_SUFFIX}"), p)
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


def documented_names(store: Any, system: str) -> dict[str, tuple[str | None, str | None]]:
    """``COLUMN -> (official_name, translated_name)`` from the curation."""
    from .semantics.curation import load_variable_docs

    return {
        name: (doc.official_name, doc.translated_name)
        for name, doc in load_variable_docs(store, system).items()
    }


__all__ = ["LABEL_SUFFIX", "PRESETS", "Presentation", "documented_names", "present", "resolve"]
