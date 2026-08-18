"""Harvest candidate field definitions from the 46 dictionary PDFs on the tree.

Held at **lower confidence and never overriding** ``.CNV``/``.DEF`` (§6.3). A PDF
layout table is a human artifact: it states intent, not the bytes actually
written, and the two diverge. So what lands in the dictionary from here is always
``source='pdf'``, which loses every conflict against a TabNet source and is
recorded as a conflict rather than dropped.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from .dictionary import DEFAULT_CONFIDENCE, DictionaryEntry

#: A DATASUS layout table row usually looks like one of:
#:   SEXO      1  C  Sexo do paciente
#:   1 - Masculino
#:   1 = Masculino
_FIELD_ROW = re.compile(
    r"^\s*(?P<field>[A-Z][A-Z0-9_]{2,17})\s+(?P<width>\d{1,3})\s+(?P<type>[CNDL])\s+(?P<desc>.{3,120})$"
)
_VALUE_ROW = re.compile(r"^\s*(?P<code>[A-Z0-9]{1,8})\s*[-=:]\s*(?P<label>\S.{1,80})$")
_SECTION = re.compile(r"^\s*(?P<field>[A-Z][A-Z0-9_]{2,17})\s*[:\-–]\s*$")


@dataclass(slots=True)
class PdfHarvest:
    source_ref: str
    field_descriptions: dict[str, str] = field(default_factory=dict)
    value_labels: list[tuple[str, str, str]] = field(default_factory=list)  # (field, code, label)
    pages_read: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.field_descriptions and not self.value_labels


def extract_text(data: bytes) -> Iterator[str]:
    """Yield page text, preferring pdfplumber's layout fidelity when available."""
    try:
        import io

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
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages:
            yield page.extract_text() or ""
    except ImportError as exc:
        raise RuntimeError("pypdf or pdfplumber is required to harvest PDFs") from exc


def harvest_pdf(data: bytes, *, source_ref: str) -> PdfHarvest:
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
                current_field = section.group("field")
                continue
            field_row = _FIELD_ROW.match(line)
            if field_row:
                name = field_row.group("field")
                current_field = name
                description = field_row.group("desc").strip()
                out.field_descriptions.setdefault(name, description)
                continue
            value_row = _VALUE_ROW.match(line)
            if value_row and current_field:
                out.value_labels.append(
                    (current_field, value_row.group("code"), value_row.group("label").strip())
                )
    return out


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
        )
        for field_name, code, label in harvest.value_labels
    ]
