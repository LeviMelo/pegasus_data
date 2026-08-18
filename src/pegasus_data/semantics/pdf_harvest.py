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
#: A code line: ``1 - Masculino``. Codes are short and alphanumeric; Roman
#: numerals and single letters used as list markers in prose are excluded.
_VALUE_ROW = re.compile(r"^\s*(?P<code>\d{1,6}|[A-Z]\d{1,5})\s*[-=:]\s*(?P<label>\S.{1,80})$")
#: ``SEXO:`` opening a value list.
_SECTION = re.compile(r"^\s*(?P<field>[A-Z][A-Z0-9_]{2,17})\s*[:\-–]\s*$")

#: Roman numerals, which decrees enumerate clauses with and dictionaries do not.
_ROMAN = re.compile(r"^[IVXLCDM]{1,7}$")


@dataclass(slots=True)
class PdfHarvest:
    source_ref: str
    field_descriptions: dict[str, str] = field(default_factory=dict)
    value_labels: list[tuple[str, str, str]] = field(default_factory=list)  # (field, code, label)
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

            value_row = _VALUE_ROW.match(line)
            if value_row and current_field:
                code = value_row.group("code")
                if _ROMAN.match(code):
                    out.rejected += 1
                    continue
                out.value_labels.append((current_field, code, value_row.group("label").strip()))
    return out


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
