"""Harvest candidate field definitions from the dictionary PDFs on the tree.

Held at **lower confidence and never overriding** ``.CNV``/``.DEF`` (§6.3). A PDF
layout table is a human artifact: it states intent, not the bytes actually
written, and the two diverge. So what lands in the dictionary from here is always
``source='pdf'``, which loses every conflict against a TabNet source and is
recorded as a conflict rather than dropped.

**Why this is off by default.** Measured on the tree, most of the ~46 PDFs are
not layout tables at all — they are legislation, technical notes and population
methodology papers. Run unconstrained against
``SINAN/AUXILIAR/Legislacao_PDF.pdf``, a naive extractor reads the Roman numerals
of a ministerial decree as codes and produces 48 entries like
``I → "A vigilância das doenças transmissíveis"``. Every one of those has perfect
provenance and is still worthless, which is exactly the failure mode §13 is
about: a plausible-looking mapping is worse than a gap, because the gap is
visible.

So harvesting is constrained two ways. A candidate field name must be a column
this catalog has **actually observed** — a PDF can only inform us about columns
that exist — and a candidate code must look like a DATASUS code rather than like
prose. What survives both is worth having; what does not was never a mapping.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from ..catalog.store import Catalog
from .dictionary import DEFAULT_CONFIDENCE, DictionaryEntry

#: A layout-table row: ``SEXO      1  C  Sexo do paciente``
_FIELD_ROW = re.compile(
    r"^\s*(?P<field>[A-Z][A-Z0-9_]{2,17})\s+(?P<width>\d{1,3})\s+(?P<type>[CNDL])\s+(?P<desc>.{3,120})$"
)

#: The record-layout dialect DATASUS's "Instrução Técnica" documents use:
#: ``41 DIAG_PRINC char(4) Código do diagnóstico principal (CID10).``
#: This is the form that actually answers "what is this column called", which
#: ``.DEF`` does not: a ``.DEF`` enumerates TabNet tabulation axes, so it names
#: ``DIAG_PRINC`` only as "Diag CID10 (capit)", "Diag CID10 (grupo)" and the like.
_LAYOUT_ROW = re.compile(
    r"^\s*(?P<ordinal>\d{1,3})\s+(?P<field>[A-Z][A-Z0-9_]{2,17})\s+"
    r"(?P<type>char|varchar|numeric|number|date|int|integer|float|decimal)\s*"
    r"\(\s*(?P<width>\d{1,3})\s*(?:,\s*(?P<decimals>\d{1,2})\s*)?\)\s*"
    r"(?P<desc>\S.{2,150})$",
    re.I,
)
#: The ``Estrutura_*`` dialect CGIAE publishes for SIM, SINASC and their kin.
#: One table row, flattened by text extraction into a single line:
#:
#:     Sexo SEXO Caracter 1 M- Masculino F- Feminino I- Ignorado Sexo do recém nascido
#:     2- Data do óbito DTOBITO Caracter 8 Data no padrão ddmmaaaa Data em que ocorreu
#:
#: The column order is label, DBF name, type, width, valid values, description. That
#: leading label is the one thing no other source carries: ``.DEF`` names TabNet
#: tabulation axes, and the IT_ layout documents give a description but not the
#: form's own wording for the field. Anchoring on NAME + type-word + width is what
#: makes this survive the surrounding noise — these PDFs interleave rotated
#: side-headings into the text stream, so nothing positional would hold.
_ESTRUTURA_ROW = re.compile(
    r"^\s*(?P<label>.{0,60}?)\s*(?P<field>[A-Z][A-Z0-9_]{2,17})\s+"
    r"(?P<type>Caracter|Car[aá]cter|Num[ée]rico|Numerico|Data|Num)\s+"
    r"(?P<width>\d{1,3})\s+(?P<rest>\S.{2,250})$",
    re.I,
)

#: ``1-Fetal; 2-Não Fetal`` / ``M- Masculino F- Feminino`` — the valid-values cell
#: of an Estrutura row, which packs several code→label pairs onto one line.
_INLINE_VALUE = re.compile(
    r"(?<![A-Za-z0-9])(?P<code>\d{1,3}|[A-Z])\s*[-–—]\s*(?P<label>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ /'']{1,40}?)"
    r"(?=\s*(?:;|,|\s(?:\d{1,3}|[A-Z])\s*[-–—]|$))"
)

#: Words that mean "this cell describes a format", not "this is a label".
_NOT_A_VALUE_CELL = re.compile(
    r"n[uú]meros?|padr[aã]o|caselas?|d[ií]gitos?|ddmmaaaa|aaaammdd|branco|conforme|tabela",
    re.I,
)

#: A code line: ``1 - Masculino``. Codes are short and alphanumeric; Roman
#: numerals and single letters used as list markers in prose are excluded.
_VALUE_ROW = re.compile(r"^\s*(?P<code>\d{1,6}|[A-Z]\d{1,5})\s*[-=:]\s*(?P<label>\S.{1,80})$")
#: ``SEXO:`` opening a value list.
_SECTION = re.compile(r"^\s*(?P<field>[A-Z][A-Z0-9_]{2,17})\s*[:\-–]\s*$")

#: Roman numerals, which decrees enumerate clauses with and dictionaries do not.
_ROMAN = re.compile(r"^[IVXLCDM]{1,7}$")

_ESTRUTURA_TYPES = {"car": "char", "num": "numeric", "dat": "date"}

#: Leading enumeration ("2- Data do óbito") and stray single letters left behind
#: by the rotated side-headings these PDFs bake into the text stream.
_LABEL_NOISE = re.compile(r"^\s*(?:\d{1,3}\s*[-–—.]\s*)?(?:[a-z]\s+)*", re.I)


#: Portuguese function words. A cell that ENDS on one was cut mid-phrase by the
#: text extractor — these PDFs wrap cells across lines and interleave rotated
#: side-headings, so a fragment is the normal failure, not a rare one.
_DANGLING = frozenset(
    ["de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "ao", "aos", "a", "o", "e", "ou", "com", "por", "para", "que", "se", "um", "uma", "pelo", "pela", "sobre", "entre", "ate", "até", "conforme"]
)

#: Column spill: the description and "Características" cells run on after the
#: value list, so a label swallows them unless it is cut here.
_SPILL = re.compile(
    r"\s+(?:Campo|Preenchimento|Obrigat[oó]rio|N[aã]o\s+obrigat|"
    r"Informa[cç][aã]o|Somente|Ver|Tabela)",
    re.I,
)


def _looks_truncated(text: str) -> bool:
    """True when the extractor cut this phrase mid-thought.

    Cheap and worth it: an entry like ``OCUP -> "habitual (Código"`` is worse than
    no entry at all, because it will be presented as what the record layout says
    the column is.
    """
    if not text:
        return True
    words = text.split()
    if words[-1].lower().strip(".,;:") in _DANGLING:
        return True
    if text.count("(") != text.count(")"):
        return True
    return bool(words and words[0][:1].islower())


def _accept_value_run(pairs: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """Keep a value cell only if it looks like an enumeration, not a bled ordinal.

    These tables number their rows, and the text extractor folds the *next* row's
    ordinal into the current row's cell. The result is a lone code with a fragment
    attached — ``NATURAL 4 = "Código do"`` is row 4's number and row 4's label,
    landing in row 3's valid-values cell.

    What separates the two is shape, not content. A real enumeration lists several
    codes and starts where enumerations start: ``1-Fetal; 2-Não Fetal``,
    ``M- Masculino F- Feminino``. A bled ordinal arrives alone and carries whatever
    the document's running row counter had reached. So: at least two distinct
    codes, and if they are numeric, a run beginning at 0 or 1 — truncated at the
    first break, since the tail of a good run is where the next ordinal lands.
    """
    if len(pairs) < 2:
        return []
    seen: set[str] = set()
    unique = [(c, lbl) for c, lbl in pairs if not (c in seen or seen.add(c))]
    if len(unique) < 2:
        return []
    if all(c.isdigit() for c, _ in unique):
        numbers = [int(c) for c, _ in unique]
        if numbers[0] not in (0, 1):
            return []
        run = [unique[0]]
        for (code, lbl), previous in zip(unique[1:], numbers, strict=False):
            if int(code) == previous + 1:
                run.append((code, lbl))
            else:
                break
        return _trim_last(run) if len(run) >= 2 else []
    if all(len(c) == 1 and c.isalpha() for c, _ in unique):
        return _trim_last(unique)
    return []


def _trim_last(run: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The final value in a cell is the one that runs into the next column.

    There is no delimiter to stop at — the extractor concatenates the cells — so
    the cut is on shape: a label of more than three words that then starts a new
    capitalised word is two cells joined. ``Outro Condição do médico atestante``
    is the value "Outro" followed by the description. Two-word labels are left
    alone, because ``Sem Escolaridade`` is one value and cutting it would be worse
    than the spill.
    """
    code, label = run[-1]
    words = label.split()
    if len(words) > 3:
        for i, word in enumerate(words[1:], start=1):
            if word[:1].isupper():
                label = " ".join(words[:i])
                break
    return [*run[:-1], (code, label)]


def _clean_label(raw: str) -> str:
    """The form's wording for a field, or empty when only noise is left."""
    label = _LABEL_NOISE.sub("", raw or "").strip(" -–—.	")
    label = " ".join(label.split())
    if len(label) < 3 or label.isdigit():
        return ""
    # A label that is itself all-caps is the DBF name repeated, not a wording.
    if label.replace("_", "").isupper() and " " not in label:
        return ""
    if _looks_truncated(label):
        return ""
    return label


@dataclass(slots=True)
class PdfHarvest:
    source_ref: str
    field_descriptions: dict[str, str] = field(default_factory=dict)
    #: ``field -> (declared type, width, decimals)`` where the layout states it.
    declared_types: dict[str, tuple[str, int, int | None]] = field(default_factory=dict)
    value_labels: list[tuple[str, str, str]] = field(default_factory=list)  # (field, code, label)
    #: The form's own name for the field, where the document states one separately
    #: from the description. Only the ``Estrutura_*`` dialect carries this.
    official_names: dict[str, str] = field(default_factory=dict)
    pages_read: int = 0
    rejected: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.field_descriptions and not self.value_labels


def extract_text(data: bytes) -> Iterator[str]:
    """Yield page text, preferring pdfplumber's layout fidelity when available."""
    import io

    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                yield page.extract_text() or ""
        return
    except ImportError:
        pass
    except Exception:
        pass
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages:
            yield page.extract_text() or ""
    except ImportError as exc:
        raise RuntimeError("pypdf or pdfplumber is required to harvest PDFs") from exc


def harvest_pdf(
    data: bytes, *, source_ref: str, known_fields: Sequence[str] | None = None
) -> PdfHarvest:
    """Read a PDF for field definitions.

    ``known_fields`` is the set of columns this catalog has observed. When given,
    nothing outside it is harvested — which is what keeps a decree's clause
    numbering out of the dictionary.
    """
    allowed = {f.upper() for f in known_fields} if known_fields is not None else None
    out = PdfHarvest(source_ref=source_ref)
    current_field: str | None = None
    try:
        pages = list(extract_text(data))
    except Exception as exc:
        out.warnings.append(f"text extraction failed: {exc}")
        return out
    out.pages_read = len(pages)

    # Which dialect is this? It decides whether a bare ``4- Something`` line is a
    # value or a row header, and the two are indistinguishable line by line.
    # The Estrutura tables number their rows with exactly the syntax a value list
    # uses, so in those documents the loose value-line rule finds the document's
    # own row counter and attributes it to whichever field came last. Values there
    # come only from the valid-values cell, where the enumeration shape can be
    # checked. This is why SIM's causal-chain fields were being told they had a
    # code "40" meaning "Causas da".
    estrutura_lines = sum(
        1 for text in pages for raw in text.splitlines() if _ESTRUTURA_ROW.match(raw.rstrip())
    )
    estrutura_dialect = estrutura_lines >= 3
    if estrutura_dialect:
        out.warnings.append(
            f"Estrutura dialect ({estrutura_lines} layout rows): "
            "standalone value lines ignored, row ordinals share their syntax"
        )

    for text in pages:
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue

            section = _SECTION.match(line)
            if section:
                name = section.group("field")
                current_field = name if (allowed is None or name in allowed) else None
                if current_field is None:
                    out.rejected += 1
                continue

            layout_row = _LAYOUT_ROW.match(line)
            if layout_row:
                name = layout_row.group("field").upper()
                if allowed is not None and name not in allowed:
                    current_field = None
                    out.rejected += 1
                    continue
                current_field = name
                out.field_descriptions.setdefault(name, layout_row.group("desc").strip().rstrip("."))
                out.declared_types[name] = (
                    layout_row.group("type").lower(),
                    int(layout_row.group("width")),
                    int(layout_row.group("decimals")) if layout_row.group("decimals") else None,
                )
                continue

            estrutura_row = _ESTRUTURA_ROW.match(line)
            if estrutura_row:
                name = estrutura_row.group("field").upper()
                if allowed is not None and name not in allowed:
                    current_field = None
                    out.rejected += 1
                    continue
                current_field = name
                label = _clean_label(estrutura_row.group("label"))
                rest = estrutura_row.group("rest").strip()
                if label:
                    out.field_descriptions.setdefault(name, label)
                    out.official_names.setdefault(name, label)
                elif rest:
                    out.field_descriptions.setdefault(name, rest[:150].rstrip("."))
                out.declared_types[name] = (
                    _ESTRUTURA_TYPES.get(estrutura_row.group("type").lower()[:3], "char"),
                    int(estrutura_row.group("width")),
                    None,
                )
                # The valid-values cell carries code->label pairs the .CNV files
                # do not always duplicate. A cell describing a *format* ("Números
                # (04 caselas)") is not a value list and must not become one.
                if not _NOT_A_VALUE_CELL.search(rest):
                    pairs: list[tuple[str, str]] = []
                    for m in _INLINE_VALUE.finditer(rest):
                        code = m.group("code")
                        if _ROMAN.match(code):
                            continue
                        label_text = _SPILL.split(m.group("label").strip(), 1)[0].strip(" .,;")
                        if _looks_truncated(label_text):
                            continue
                        pairs.append((code, label_text))
                    accepted = _accept_value_run(pairs)
                    out.rejected += len(pairs) - len(accepted)
                    out.value_labels.extend((name, c, lbl) for c, lbl in accepted)
                continue

            field_row = _FIELD_ROW.match(line)
            if field_row:
                name = field_row.group("field")
                if allowed is not None and name not in allowed:
                    current_field = None
                    out.rejected += 1
                    continue
                current_field = name
                out.field_descriptions.setdefault(name, field_row.group("desc").strip())
                continue

            value_row = None if estrutura_dialect else _VALUE_ROW.match(line)
            if value_row and current_field:
                code = value_row.group("code")
                if _ROMAN.match(code):
                    out.rejected += 1
                    continue
                out.value_labels.append((current_field, code, value_row.group("label").strip()))
    return out


def documentation_rows(
    harvest: PdfHarvest, *, system: str | None
) -> list[tuple[object, ...]]:
    """Rows for ``field_documentation``: the column's own official description."""
    return [
        (
            system,
            name,
            description,
            harvest.official_names.get(name),
            (harvest.declared_types.get(name) or (None, None, None))[0],
            (harvest.declared_types.get(name) or (None, None, None))[1],
            (harvest.declared_types.get(name) or (None, None, None))[2],
            "layout_doc",
            harvest.source_ref,
            0.85,
        )
        for name, description in harvest.field_descriptions.items()
    ]


def known_field_names(catalog: Catalog) -> list[str]:
    """Columns this catalog has actually seen, from profiles and ``.DEF`` files."""
    rows = catalog.query(
        """
        SELECT DISTINCT field_name FROM variable_profiles
        UNION
        SELECT DISTINCT field_name FROM def_variables
        """
    )
    return [str(r["field_name"]) for r in rows if r["field_name"]]


def entries_from_harvest(harvest: PdfHarvest, *, system: str | None) -> list[DictionaryEntry]:
    return [
        DictionaryEntry(
            system=system,
            family_id=None,
            field_name=field_name,
            schema_signature_scope=None,
            value_raw=code,
            value_label=label,
            source="pdf",
            source_ref=harvest.source_ref,
            confidence=DEFAULT_CONFIDENCE["pdf"],
            # Scoped to the field it was read against, not to a codelist: a PDF
            # describes a column in a form, not a named TabNet codelist.
            value_group=None,
        )
        for field_name, code, label in harvest.value_labels
    ]
