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
from collections.abc import Iterable, Mapping
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


#: A leading code inside a path segment: "159 ATENCAO PRIMARIA / 001 ATENCAO PRIMARIA". Two or more digits, or a
#: hyphen or dot, followed by a CAPITALISED word, so quantities survive: "22 a 27 semanas", "10 dias".
_EMBEDDED_CODE = re.compile(r"^(?:(?:\d{2,}|\d+[.\-]\d*)[\s\-]*)+(?=[A-ZÀ-Ý][A-Za-zÀ-ÿ])")


_PLACEHOLDER = re.compile(r"^\d*([a-zA-Z])\1{2,}\s+")


def clean_label(label: str) -> str:
    """A label without the codes DATASUS tables embed in the segments of a path.

    ``159 ATENCAO PRIMARIA / 001 ATENCAO PRIMARIA`` becomes ``ATENCAO PRIMARIA /
    ATENCAO PRIMARIA``. Only the segments of a " / " path lose a leading number: the
    number that heads a one-segment label is the label's own text (``10 Horas`` for code 10,
    one of fourteen hours), and `_render_value` takes it off exactly when it is the row's own
    code and the template prints that code. Applied when showing a label; the canonical
    ``_label`` column keeps the table's text as it is.
    """
    label = _PLACEHOLDER.sub("", label.strip()) or label  # "16eeee AP - …" (a TabWin range mask)
    if " / " not in label:
        return label
    return " / ".join(_EMBEDDED_CODE.sub("", part.strip()) or part.strip() for part in label.split(" / "))


_QUANTITY = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+")


def _plain(code: str) -> str:
    """A code without its punctuation: ``O80.0`` and ``O800`` are one code."""
    return "".join(ch for ch in code if ch.isalnum()).upper()


def _render_values(
    codes: pa.ChunkedArray | pa.Array,
    labels: pa.ChunkedArray | pa.Array,
    p: Presentation,
    shown: Mapping[str, str] | None = None,
) -> pa.ChunkedArray:
    """``shown`` replaces the code printed beside a label (a municipality's
    6-digit code by its 7-digit IBGE code); the label lookup already happened.

    A ``string`` ChunkedArray at any size (`lookups.expand`): the cells of 58.6 million rows are more than the 2 GiB of
    characters one array holds."""
    # Formatted once per distinct (code, label), in Arrow up to that point: a
    # year of a 38-column file is 1.4 million cells and a few thousand
    # distinct pairs (ADR-0097). A pair is told apart as two integers, the
    # position of its code among the distinct codes and of its label among
    # the distinct labels, with one more position than there are values for a
    # null: no row's code and label are ever joined into a string, which for
    # SNGPC-IND 2014 (58.6 million rows) was 2.4 GB of characters made only to
    # be counted.
    import pyarrow.compute as pc

    from .lookups import dictionary_of, expand

    code_values, code_at = dictionary_of(pc.cast(codes, pa.string()))
    label_values, label_at = dictionary_of(pc.cast(labels, pa.string()))
    no_code, no_label = len(code_values), len(label_values)
    width = no_label + 1
    pair_at = pc.add(
        pc.multiply(pc.cast(pc.fill_null(code_at, no_code), pa.int64()), width),
        pc.cast(pc.fill_null(label_at, no_label), pa.int64()),
    )
    pairs, indices = dictionary_of(pair_at)
    distinct_codes, distinct_labels = code_values.to_pylist(), label_values.to_pylist()
    shown_values: list[str | None] = []
    for pair in pairs.to_pylist():
        code_at_pair, label_at_pair = divmod(pair, width)
        code_v = None if code_at_pair == no_code else distinct_codes[code_at_pair]
        label_v = None if label_at_pair == no_label else distinct_labels[label_at_pair]
        if shown and code_v is not None:
            code_v = shown.get(code_v, code_v)
        shown_values.append(_render_value(code_v, label_v, p))
    return expand(pa.array(shown_values, type=pa.string()), indices)


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
    # A head written as a number ("1,60 m" for 160, "2.500 g" for 2500) is the value, not the code repeated.
    if "{code}" in p.values:
        head, _, rest = text.partition(" ")
        if rest and _plain(head) == _plain(str(code)) and (head == str(code) or not _QUANTITY.fullmatch(head)):
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


#: ``codelist -> whether its codes are municipalities``, read once per process from the shipped pack.
_MUNICIPAL: dict[str, bool] = {}


def municipal_codelists(names: Iterable[str]) -> frozenset[str]:
    """The codelists among ``names`` whose codes are municipalities: a majority of the single codes the shipped label
    pack lists for one are IBGE municipality codes (6 or 7 digits, the current division). Read off the codes, not the
    name: of the codelists the catalog binds, 378 are 99-100% municipality codes, the lowest of them 0.53 (CAPITAL),
    while no other reaches 0.26 (MUNICDF and MUNIC_DF, whose codes are the Federal District's administrative regions;
    CBO's 6-digit occupations meet a municipality code 6% of the time), measured 2026-11-21. Name prefixes (BR_MUNIC*,
    MUNIC*) had missed the tables keyed by municipality and labelled with its region (SP_REGSAUD, CIRSP, BR_TERRCID)."""
    import pyarrow.dataset as pads

    from .geography import municipalities
    from .labelpack import _dataset

    wanted = {str(n).upper() for n in names if n}
    todo = sorted(wanted - set(_MUNICIPAL))
    dataset = _dataset() if todo else None
    if dataset is not None:
        places = {str(r["code7"]) for r in municipalities().values()}
        places |= {code[:6] for code in places}
        rows = dataset.to_table(columns=["codelist", "code_lo", "code_hi"],
                                filter=pads.field("codelist").isin(todo + [t.lower() for t in todo]))
        codes: dict[str, set[str]] = {}
        for codelist, lo, hi in zip(*(rows.column(c).to_pylist() for c in ("codelist", "code_lo", "code_hi")),
                                    strict=True):
            if lo == hi and lo is not None:
                codes.setdefault(str(codelist).upper(), set()).add(str(lo))
        for name in todo:
            held = codes.get(name, set())
            _MUNICIPAL[name] = bool(held) and 2 * len(held & places) > len(held)
    return frozenset(name for name in wanted if _MUNICIPAL.get(name))


def documented_names(store: Any, system: str) -> ColumnNames:
    """The curated names of a system's columns, and its municipality columns (bound to a codelist of municipalities)."""
    from .semantics.curation import load_variable_docs

    docs = load_variable_docs(store, system)
    out = ColumnNames({name: (doc.official_name, doc.translated_name) for name, doc in docs.items()})
    bound = {name: [c for c in [doc.codelist, *doc.codelists] if c] for name, doc in docs.items()}
    municipal = municipal_codelists(c for cs in bound.values() for c in cs)
    out.municipal = frozenset(name for name, cs in bound.items() if any(str(c).upper() in municipal for c in cs))
    return out


@lru_cache(maxsize=1)
def _ibge7() -> dict[str, str]:
    """6-digit DATASUS municipality code -> 7-digit IBGE code (with check digit)."""
    from .geography import municipalities

    return {code6: row["code7"] for code6, row in municipalities().items()}


__all__ = ["LABEL_SUFFIX", "PRESETS", "ColumnNames", "Presentation", "documented_names", "present", "resolve"]
