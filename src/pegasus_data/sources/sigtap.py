"""SIGTAP — the Tabela Unificada, DATASUS's first-party procedure table (§6.4).

Deferred since day one because there was no slot for it: the authority ranking
had no kind for a table fetched from outside the main FTP tree, so there was
nowhere to put the answer even once it was fetched. ``'sigtap'`` now sits between
``def`` and ``dbf_lookup`` — first-party and monthly-versioned, so it outranks a
lookup DBF, and never above a ``.CNV``/``.DEF``, because those are what the
tabulator itself used.

This closes four of the top seven measured gaps and supplies what the TabNet kits
structurally cannot: procedure *attributes*. ``TPROC`` gives a code and a name;
``tb_procedimento`` gives complexity, financing source, sex restriction, age
bounds, permitted quantity and the hospital/ancillary/professional value split.

Two properties make this cheap to read. Every table ships its own layout file —
``tb_procedimento_layout.txt`` names each column with its start and end offset —
so nothing here hardcodes a position, and a layout change is picked up rather
than silently mis-parsed. And each monthly export is a complete snapshot stamped
with its competência, so a vintage maps onto the same ``valid_from``/``valid_to``
windows the TabNet kits already use.

``tb_ocupacao`` is the reason this matters for CBO specifically: it carries
occupation codes at **one** width, where the FTP tree's CBO table mixes 3,000
three-character CBO-1994 codes with 2,813 six-character CBO-2002 codes in a
single file.
"""

from __future__ import annotations

import ftplib
import io
import re
import zipfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from ..catalog.store import Catalog
from ..semantics.dictionary import DictionaryEntry, persist_entries

HOST = "ftp2.datasus.gov.br"
DOWNLOAD_DIR = "/public/sistemas/tup/downloads"

#: Tables worth ingesting, in the priority §6.4 sets, mapped to the columns that
#: make a code→label pair. Everything else in the export is relational detail
#: that belongs in a future join rather than in a value dictionary.
WANTED: dict[str, tuple[str, str]] = {
    "tb_procedimento": ("CO_PROCEDIMENTO", "NO_PROCEDIMENTO"),
    "tb_ocupacao": ("CO_OCUPACAO", "NO_OCUPACAO"),
    "tb_cid": ("CO_CID", "NO_CID"),
    "tb_grupo": ("CO_GRUPO", "NO_GRUPO"),
    "tb_sub_grupo": ("CO_SUB_GRUPO", "NO_SUB_GRUPO"),
    "tb_forma_organizacao": ("CO_FORMA_ORGANIZACAO", "NO_FORMA_ORGANIZACAO"),
    "tb_financiamento": ("CO_FINANCIAMENTO", "NO_FINANCIAMENTO"),
    "tb_modalidade": ("CO_MODALIDADE", "NO_MODALIDADE"),
    "tb_habilitacao": ("CO_HABILITACAO", "NO_HABILITACAO"),
    "tb_servico": ("CO_SERVICO", "NO_SERVICO"),
    "tb_rubrica": ("CO_RUBRICA", "NO_RUBRICA"),
    "tb_tipo_leito": ("CO_TIPO_LEITO", "NO_TIPO_LEITO"),
}

#: Which codelist name each SIGTAP table stands in for, so a field already bound
#: to a TabNet table gets the SIGTAP rows under the same name rather than under a
#: second one nothing is bound to.
CODELIST_ALIASES: dict[str, tuple[str, ...]] = {
    "tb_procedimento": ("TPROC10", "SIGTAP_PROCEDIMENTO"),
    "tb_ocupacao": ("CBO", "SIGTAP_OCUPACAO"),
    "tb_cid": ("CID10", "SIGTAP_CID"),
}

_COMPETENCIA = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_EXPORT = re.compile(r"^tabelaunificada", re.I)


class SigtapUnavailable(RuntimeError):
    """The SIGTAP download could not be reached. Says which failure it was."""


@dataclass(frozen=True, slots=True)
class LayoutColumn:
    name: str
    start: int  # 1-based, inclusive, as the layout file states it
    end: int

    def slice(self, line: str) -> str:
        return line[self.start - 1 : self.end].strip()


@dataclass(slots=True)
class SigtapExport:
    filename: str
    competencia: str  # YYYYMM
    size: int

    @property
    def valid_from(self) -> str:
        return self.competencia


def parse_layout(text: str) -> list[LayoutColumn]:
    """Read a ``*_layout.txt``: ``Coluna,Tamanho,Inicio,Fim,Tipo``.

    Driven entirely by the file rather than by constants here, so a column added
    or moved between competências is read correctly instead of shifting every
    field after it.
    """
    columns: list[LayoutColumn] = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4 or parts[0].lower() == "coluna":
            continue
        try:
            columns.append(LayoutColumn(parts[0].upper(), int(parts[2]), int(parts[3])))
        except ValueError:
            continue
    return columns


def list_exports(*, timeout: int = 90) -> list[SigtapExport]:
    """Every monthly export on the SIGTAP FTP, oldest competência first."""
    try:
        client = ftplib.FTP(HOST, timeout=timeout)
        client.login()
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        raise SigtapUnavailable(
            f"could not connect to {HOST}: {type(exc).__name__}: {exc}"
        ) from exc
    try:
        lines: list[str] = []
        client.retrlines(f"LIST {DOWNLOAD_DIR}", lines.append)
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001 - closing is best-effort
            pass

    out: list[SigtapExport] = []
    for line in lines:
        if line.startswith("d"):
            continue
        parts = line.split()
        name = parts[-1]
        if not _EXPORT.match(name):
            continue
        match = _COMPETENCIA.search(name)
        if not match:
            continue
        size = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
        out.append(SigtapExport(filename=name, competencia=match.group(1), size=size))
    return sorted(out, key=lambda e: e.competencia)


def fetch_export(export: SigtapExport, *, timeout: int = 120) -> bytes:
    client = ftplib.FTP(HOST, timeout=timeout)
    client.login()
    try:
        buffer = io.BytesIO()
        client.retrbinary(f"RETR {DOWNLOAD_DIR}/{export.filename}", buffer.write)
        return buffer.getvalue()
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001 - closing is best-effort
            pass


def read_table(archive: zipfile.ZipFile, table: str) -> Iterator[dict[str, str]]:
    """Yield one dict per row, positions taken from the table's own layout file."""
    try:
        layout_text = archive.read(f"{table}_layout.txt").decode("latin-1")
        body = archive.read(f"{table}.txt").decode("latin-1")
    except KeyError:
        return
    columns = parse_layout(layout_text)
    if not columns:
        return
    for line in body.splitlines():
        if not line.strip():
            continue
        yield {c.name: c.slice(line) for c in columns}


def entries_from_export(
    data: bytes, export: SigtapExport, *, valid_to: str | None = None
) -> list[DictionaryEntry]:
    """Turn one monthly export into dictionary entries, stamped with its vintage."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    entries: list[DictionaryEntry] = []
    for table, (code_column, label_column) in WANTED.items():
        for row in read_table(archive, table):
            code = row.get(code_column, "")
            label = row.get(label_column, "")
            if not code or not label:
                continue
            for group in CODELIST_ALIASES.get(table, (f"SIGTAP_{table[3:].upper()}",)):
                entries.append(
                    DictionaryEntry(
                        system="SIGTAP",
                        value_raw=code,
                        value_label=label,
                        source="sigtap",
                        source_ref=f"{export.filename}!{table}.txt",
                        confidence=0.9,
                        value_group=group,
                        valid_from=export.valid_from,
                        valid_to=valid_to,
                    )
                )
    return entries


def ingest(
    catalog: Catalog,
    *,
    competencias: Sequence[str] | None = None,
    latest: int = 1,
    timeout: int = 120,
) -> dict[str, object]:
    """Ingest SIGTAP exports into the dictionary at ``source='sigtap'``.

    Defaults to the newest export only. The full series is 224 monthly snapshots
    of largely the same table, and ingesting all of them multiplies the
    dictionary without adding much: what earlier vintages give you is the wording
    and the price *as of then*, which matters for a historical join and not for
    labelling. Ask for them explicitly.
    """
    exports = list_exports(timeout=timeout)
    if not exports:
        raise SigtapUnavailable(f"no TabelaUnificada exports found under {DOWNLOAD_DIR}")
    if competencias:
        wanted = {str(c) for c in competencias}
        chosen = [e for e in exports if e.competencia in wanted]
        missing = wanted - {e.competencia for e in chosen}
        if missing:
            raise SigtapUnavailable(
                f"no export for competência(s) {sorted(missing)}; "
                f"available {exports[0].competencia}..{exports[-1].competencia}"
            )
    else:
        chosen = exports[-max(1, latest) :]

    # A vintage is valid until the next one supersedes it, which is exactly how
    # the TabNet kit windows already work.
    by_competencia = {e.competencia: e for e in exports}
    ordered = sorted(by_competencia)
    counts: dict[str, object] = {"exports": [], "entries": 0, "bytes": 0}
    for export in chosen:
        index = ordered.index(export.competencia)
        valid_to = ordered[index + 1] if index + 1 < len(ordered) else None
        data = fetch_export(export, timeout=timeout)
        entries = entries_from_export(data, export, valid_to=valid_to)
        written = persist_entries(catalog, entries)
        catalog.log_event(
            "sigtap",
            f"ingested {export.filename}",
            detail=f"{len(entries)} entries, {written} merged, valid {export.competencia}..{valid_to}",
        )
        counts["exports"].append(  # type: ignore[union-attr]
            {
                "filename": export.filename,
                "competencia": export.competencia,
                "valid_to": valid_to,
                "entries": len(entries),
            }
        )
        counts["entries"] = int(counts["entries"]) + len(entries)
        counts["bytes"] = int(counts["bytes"]) + len(data)
    counts["available"] = f"{exports[0].competencia}..{exports[-1].competencia}"
    counts["available_count"] = len(exports)
    return counts
