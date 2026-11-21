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
from pathlib import Path
from typing import Any

from ..catalog.store import CatalogStore
from ..discovery.ftp_client import FtpClient, ListingUnavailable
from ..normalize.time import add_months
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
        with FtpClient(HOST, timeout=timeout) as client:
            entries, _method = client.list_directory(DOWNLOAD_DIR)
    except (OSError, EOFError, ftplib.Error, ListingUnavailable, RuntimeError) as exc:
        raise SigtapUnavailable(f"could not list {HOST}{DOWNLOAD_DIR}: {type(exc).__name__}: {exc}") from exc

    out: list[SigtapExport] = []
    for entry in entries:
        if entry.is_dir or not _EXPORT.match(entry.name):
            continue
        match = _COMPETENCIA.search(entry.name)
        if not match:
            continue
        out.append(SigtapExport(filename=entry.name, competencia=match.group(1), size=entry.size or 0))
    return sorted(out, key=lambda e: e.competencia)


def fetch_export(export: SigtapExport, *, timeout: int = 120, attempts: int = 4) -> bytes:
    """One export's bytes. A reset or timeout is retried (an export is tens of megabytes on a server that drops
    connections); a refusal by the server (550: no such file) is not."""
    try:
        with FtpClient(HOST, timeout=timeout, max_retries=attempts) as client:
            return client.retrieve(f"{DOWNLOAD_DIR}/{export.filename}")
    except ftplib.error_perm:
        raise
    except (OSError, EOFError, ftplib.Error, RuntimeError) as exc:
        raise SigtapUnavailable(f"{export.filename}: {attempts} attempts failed; last: {type(exc).__name__}: {exc}") from exc


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


def _month_before(competencia: str) -> str:
    """``202406`` -> ``202405``; ``202401`` -> ``202312``."""
    return str(add_months(competencia[:6], -1))


def ingest(
    catalog: CatalogStore,
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

    # A vintage is valid until the month before the next one: windows are inclusive (`labelpack.covers`), so ending at the
    # next competência would put that month under two vintages.
    by_competencia = {e.competencia: e for e in exports}
    ordered = sorted(by_competencia)
    counts: dict[str, Any] = {"exports": [], "entries": 0, "bytes": 0}
    for export in chosen:
        index = ordered.index(export.competencia)
        valid_to = _month_before(ordered[index + 1]) if index + 1 < len(ordered) else None
        data = fetch_export(export, timeout=timeout)
        entries = entries_from_export(data, export, valid_to=valid_to)
        written = persist_entries(catalog, entries)
        catalog.log_event(
            "sigtap",
            f"ingested {export.filename}",
            detail=f"{len(entries)} entries, {written} merged, valid {export.competencia}..{valid_to}",
        )
        counts["exports"].append(
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


# --- the history of the procedure table -------------------------------------------------------------------------------
#
# `ingest` keeps the newest export in the dictionary. A study that spans years needs the table *as it was*: a code exists
# only from the month a portaria created it, and its reimbursement changes. Every export is a complete snapshot of one
# competência, so the history is one pass over them, closing a run whenever a code's attributes change or the code is
# absent from a month. A derived registry, rebuilt from the server at will.

_ATTRIBUTES = (
    "NO_PROCEDIMENTO", "TP_COMPLEXIDADE", "TP_SEXO", "QT_MAXIMA_EXECUCAO", "QT_DIAS_PERMANENCIA", "QT_PONTOS",
    "VL_IDADE_MINIMA", "VL_IDADE_MAXIMA", "QT_TEMPO_PERMANENCIA", "VL_SH", "VL_SA", "VL_SP", "CO_FINANCIAMENTO",
    "CO_RUBRICA", "NO_GRUPO", "NO_SUB_GRUPO", "NO_FORMA_ORGANIZACAO",
)
_INTEGERS = ("QT_MAXIMA_EXECUCAO", "QT_DIAS_PERMANENCIA", "QT_PONTOS", "VL_IDADE_MINIMA", "VL_IDADE_MAXIMA", "QT_TEMPO_PERMANENCIA")
#: Filed in centavos, zero-padded (10 characters to 2015, 12 later): ``0000041589`` is R$ 415,89.
_MONEY = ("VL_SH", "VL_SA", "VL_SP")
HISTORY_FOLDER = "sigtap"
HISTORY_FILE = "procedure_history.parquet"
WINDOWS_FILE = "procedure_windows.parquet"


def _number(raw: str, column: str, code: str, competencia: str) -> int | None:
    if raw == "":
        return None
    if not raw.isdigit():
        raise ValueError(f"SIGTAP {competencia} {code}: {column}={raw!r} is not a number; the layout may have drifted")
    return int(raw)


def _procedures_of(archive: zipfile.ZipFile, competencia: str) -> tuple[dict[str, tuple], str]:
    """One export's procedures as ``{code: attribute tuple}`` (money in reais), plus its layout's column signature."""
    grupo = {r["CO_GRUPO"]: r["NO_GRUPO"] for r in read_table(archive, "tb_grupo")}
    sub_grupo = {r["CO_GRUPO"] + r["CO_SUB_GRUPO"]: r["NO_SUB_GRUPO"] for r in read_table(archive, "tb_sub_grupo")}
    forma = {
        r["CO_GRUPO"] + r["CO_SUB_GRUPO"] + r["CO_FORMA_ORGANIZACAO"]: r["NO_FORMA_ORGANIZACAO"]
        for r in read_table(archive, "tb_forma_organizacao")
    }
    layout = parse_layout(archive.read("tb_procedimento_layout.txt").decode("latin-1"))
    signature = " ".join(f"{c.name}:{c.start}-{c.end}" for c in layout)
    out: dict[str, tuple] = {}
    for row in read_table(archive, "tb_procedimento"):
        code = row["CO_PROCEDIMENTO"]
        if len(code) != 10:
            raise ValueError(f"SIGTAP {competencia}: procedure code {code!r} is not 10 characters")
        stamp = row.get("DT_COMPETENCIA", "")
        if stamp and stamp != competencia:
            raise ValueError(f"SIGTAP {competencia} {code}: row stamped {stamp}; the layout may have drifted")
        if code in out:
            raise ValueError(f"SIGTAP {competencia}: procedure {code} listed twice")
        values: dict[str, object] = {name: row.get(name) or None for name in _ATTRIBUTES}
        for name in _INTEGERS:
            values[name] = _number(row.get(name, ""), name, code, competencia)
        for name in _MONEY:
            cents = _number(row.get(name, ""), name, code, competencia)
            values[name] = None if cents is None else cents / 100
        values["NO_GRUPO"] = grupo.get(code[:2])
        values["NO_SUB_GRUPO"] = sub_grupo.get(code[:4])
        values["NO_FORMA_ORGANIZACAO"] = forma.get(code[:6])
        out[code] = tuple(values[name] for name in _ATTRIBUTES)
    return out, signature


def _version_stamp(export: SigtapExport) -> str:
    match = re.search(r"_v(\d+)", export.filename)
    return match.group(1) if match else ""


def _latest_per_competencia(exports: Sequence[SigtapExport]) -> list[SigtapExport]:
    """A month may carry several files (``_v<yymmddhhmm>`` stamps); the one with the greatest stamp is the latest."""
    best: dict[str, SigtapExport] = {}
    for export in exports:
        held = best.get(export.competencia)
        if held is None or _version_stamp(export) > _version_stamp(held):
            best[export.competencia] = export
    return [best[c] for c in sorted(best)]


def _months_between(first: str, last: str) -> list[str]:
    out, month = [first], first
    while month != last:
        month = str(add_months(month, 1))
        out.append(month)
    return out


def build_history(settings: Any = None, *, timeout: int = 120, progress: Any = None, cache_dir: Any = None) -> dict[str, object]:
    """Read every monthly export once (in memory; nothing is kept) and write the two registries.

    ``procedure_history.parquet``: one row per code and run of identical attributes, ``valid_from``/``valid_to`` inclusive
    (``valid_to`` null when the run reaches the newest export). ``procedure_windows.parquet``: per code the first and last
    competência it is present in and the months absent between them. ``cache_dir`` (optional) keeps the downloaded zips
    so an interrupted build resumes where it stopped; by default nothing is kept.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    from ..config import load_settings

    settings = settings or load_settings()
    listed = list_exports(timeout=timeout)
    if not listed:
        raise SigtapUnavailable(f"no TabelaUnificada exports found under {DOWNLOAD_DIR}")
    exports = _latest_per_competencia(listed)
    months = [e.competencia for e in exports]
    calendar = _months_between(months[0], months[-1])
    runs: list[dict[str, Any]] = []
    open_runs: dict[str, dict[str, Any]] = {}
    present: dict[str, list[str]] = {}
    layouts: dict[str, list[str]] = {}
    previous: str | None = None
    # The server stalls a session after some twenty transfers (a recv that never ends, then a 120 s timeout per file):
    # a fresh connection every eight exports, and a short read timeout so a stall costs seconds.
    client = FtpClient(HOST, timeout=min(timeout, 30), max_retries=4)
    client.connect()
    for position, export in enumerate(exports):
        if position and position % 8 == 0:
            client.close()
            client = FtpClient(HOST, timeout=min(timeout, 30), max_retries=4)
            client.connect()
        cached = None if cache_dir is None else Path(cache_dir) / export.filename
        if cached is not None and cached.is_file() and cached.stat().st_size == export.size:
            data = cached.read_bytes()
        else:
            try:
                data = client.retrieve(f"{DOWNLOAD_DIR}/{export.filename}")
            except (OSError, EOFError, ftplib.Error, RuntimeError) as exc:
                client.close()
                raise SigtapUnavailable(f"{export.filename}: {type(exc).__name__}: {exc}") from exc
            if cached is not None:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(data)
        procedures, signature = _procedures_of(zipfile.ZipFile(io.BytesIO(data)), export.competencia)
        layouts.setdefault(signature, []).append(export.competencia)
        contiguous = previous is not None and str(add_months(previous, 1)) == export.competencia
        for code in [c for c in open_runs if c not in procedures or not contiguous]:
            runs.append(open_runs.pop(code))  # absent this month (or the month before is missing): the run ended
        for code, attributes in procedures.items():
            present.setdefault(code, []).append(export.competencia)
            run = open_runs.get(code)
            if run is not None and run["attributes"] == attributes:
                run["valid_to"] = export.competencia
                continue
            if run is not None:
                runs.append(run)
            open_runs[code] = {"code": code, "valid_from": export.competencia, "valid_to": export.competencia, "attributes": attributes}
        previous = export.competencia
        if progress:
            progress(position + 1, len(exports), export.competencia)
    client.close()
    runs.extend(open_runs.values())
    newest = months[-1]

    rows = []
    for run in sorted(runs, key=lambda r: (r["code"], r["valid_from"])):
        row: dict[str, Any] = {
            "CO_PROCEDIMENTO": run["code"],
            "valid_from": run["valid_from"],
            "valid_to": None if run["valid_to"] == newest else run["valid_to"],
        }
        row.update(zip(_ATTRIBUTES, run["attributes"], strict=True))
        rows.append(row)
    position = {m: i for i, m in enumerate(calendar)}
    windows = []
    for code in sorted(present):
        seen = present[code]
        held = set(seen)
        gaps = [m for m in calendar[position[seen[0]] : position[seen[-1]] + 1] if m not in held]
        windows.append({"CO_PROCEDIMENTO": code, "first": seen[0], "last": seen[-1], "months_present": len(seen), "gaps": gaps})

    folder = settings.registry_dir(HISTORY_FOLDER)
    folder.mkdir(parents=True, exist_ok=True)
    schema_windows = pa.schema([
        ("CO_PROCEDIMENTO", pa.string()), ("first", pa.string()), ("last", pa.string()),
        ("months_present", pa.int32()), ("gaps", pa.list_(pa.string())),
    ])
    for name, table in (
        (HISTORY_FILE, pa.Table.from_pylist(rows)),
        (WINDOWS_FILE, pa.Table.from_pylist(windows, schema=schema_windows)),
    ):
        staged = folder / (name + ".part")
        pq.write_table(table, staged, compression="zstd")
        staged.replace(folder / name)
    return {
        "exports": len(exports), "files_listed": len(listed), "first": months[0], "last": newest,
        "missing_months": [m for m in calendar if m not in set(months)],
        "codes": len(windows), "runs": len(rows), "codes_with_gaps": sum(1 for w in windows if w["gaps"]),
        "layouts": [f"{v[0]}..{v[-1]} ({len(v)} exports): {sig}" for sig, v in layouts.items()],
        "folder": str(folder),
    }


def _history_table(name: str, settings: Any):
    import pyarrow.parquet as pq

    from ..config import load_settings

    path = (settings or load_settings()).registry_dir(HISTORY_FOLDER) / name
    if not path.is_file():
        raise FileNotFoundError(f"{path} is not built; run `pegasus-data sigtap --history`")
    return pq.read_table(path)


def procedure_history(codes: Sequence[str] | None = None, *, settings: Any = None):
    """The SIGTAP procedure table across every monthly export (pyarrow table): one row per code and run of identical
    attributes, with ``valid_from``/``valid_to`` (YYYYMM, inclusive; ``valid_to`` null while it still holds) and the
    attributes of that run (money in reais). ``codes`` keeps only those 10-character codes."""
    import pyarrow as pa
    import pyarrow.compute as pc

    table = _history_table(HISTORY_FILE, settings)
    if codes is None:
        return table
    return table.filter(pc.is_in(table["CO_PROCEDIMENTO"], value_set=pa.array([str(c) for c in codes], type=pa.string())))


def procedure_window(code: str, *, settings: Any = None) -> dict[str, Any] | None:
    """When one procedure exists in SIGTAP: ``{CO_PROCEDIMENTO, first, last, months_present, gaps}`` (competências
    YYYYMM; ``gaps`` are the months absent between first and last), or None when no export ever listed it."""
    import pyarrow.compute as pc

    table = _history_table(WINDOWS_FILE, settings)
    hit = table.filter(pc.equal(table["CO_PROCEDIMENTO"], str(code)))
    return hit.to_pylist()[0] if hit.num_rows else None
