"""TUSS, the supplementary-health terminology of ANS's TISS standard, and its official correspondence to SIGTAP.

Two published files, both ANS's:

* ``pda-049-tuss.zip``, the open-data terminology (dadosabertos.ans.gov.br, PDA 049): one CSV per TUSS table, each term with
  its start of validity. The tables a TISS item names by ``CD_TABELA_REFERENCIA`` are 22 (procedures and health events,
  8-digit codes), 63 (groups of procedures, 3 digits), 19 (OPME) and 20 (medicines); 22 and 63 are read here.
* ``padraotiss_mapeamento_tuss_sigtap.zip``, the TUSS table 22 to SIGTAP mapping the Ministry of Health and ANS made
  (workbook "MAPEAMENTO TUSS x SIGTAP 2017 04", the TUSS of June 2016 and the SIGTAP of that time), one row per
  TUSS-SIGTAP pair with a degree of equivalence.

Labelling: a TISS item is a code of a table, and a code of one table can equal one of another, so the label is looked up
by the pair, the table (two digits) in front of the code: ``2210101012``. ``resources/tuss.parquet`` is that table (the
canonical ``TUSS`` classification) and the registry's ``code_windows.parquet`` dates each code (``codelists.yml``).
``pegasus-data tuss`` builds the registry in the data home; ``--ship`` also rewrites the shipped table.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

TERMS_URL = "https://dadosabertos.ans.gov.br/FTP/PDA/terminologia_unificada_saude_suplementar_TUSS-049/pda-049-tuss.zip"
MAPPING_URL = ("https://www.gov.br/ans/pt-br/arquivos/assuntos/prestadores/padrao-para-troca-de-informacao-de-saude-suplementar-tiss/"
               "padrao-tiss-tabelas-relacionadas/padraotiss_mapeamento_tuss_sigtap.zip")
FOLDER = "tuss"
WINDOWS_FILE = "code_windows.parquet"
TERMS_FILE = "terms.parquet"
MAPPING_FILE = "tuss_sigtap.parquet"
RESOURCE = "tuss.parquet"
#: The TUSS tables read: the number the TISS files carry in CD_TABELA_REFERENCIA, and the member of the zip that holds it.
TABLES = {"22": "tabela_22_", "63": "tabela_63_"}
#: The degrees of equivalence the workbook defines (its sheet Tabela_Equivalência).
EQUIVALENCE = {1: "same meaning, lexically and conceptually", 2: "same meaning with a synonym",
               3: "TUSS is less specific than SIGTAP", 4: "TUSS is more specific than SIGTAP", 5: "cannot be mapped"}


def _month(date: str) -> str | None:
    return date[:4] + date[5:7] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or "") else None


def read_terms(archive: zipfile.ZipFile) -> list[dict[str, Any]]:
    """The terms of the tables read, one row per code: ``code`` (the table's two digits and the term's code, the key a TISS
    item's pair makes), ``table``, ``term``, ``name``, ``valid_from`` and ``valid_to`` (YYYYMM of its validity,
    ``valid_to`` null while it holds), ``implemented`` (the month ANS made it mandatory)."""
    rows: list[dict[str, Any]] = []
    for table, stem in TABLES.items():
        member = next(n for n in archive.namelist() if stem in n)
        reader = csv.DictReader(io.TextIOWrapper(io.BytesIO(archive.read(member)), encoding="utf-8-sig"), delimiter=";")
        for r in reader:
            name = r.get("NM_TERMO") or r.get("DS_TERMO_DETALHADO") or ""
            first = _month(r["DT_INICIO_VIGENCIA"])
            if not (r["CD_TERMO"].strip() and name.strip() and first):
                raise ValueError(f"TUSS table {table}: a term with no code, name or start of validity: {r}")
            rows.append({"code": table + r["CD_TERMO"].strip(), "table": table, "term": r["CD_TERMO"].strip(), "name": name.strip(),
                         "valid_from": first, "valid_to": _month(r["DT_FIM_VIGENCIA"]), "implemented": _month(r["DT_FIM_IMPLANTACAO"])})
    return rows


def read_mapping(workbook: bytes) -> list[dict[str, Any]]:
    """The mapping sheet's rows as ``tuss_code``, ``tuss_term``, ``sigtap_code`` (10 digits; null when the TUSS term has none),
    ``sigtap_name``, ``mapping`` (``mapped``, ``not_in_sigtap`` or ``not_yet_mapped``: the sheet's own status, or none), ``equivalence``
    (1-5, null when unrated or doubtful), ``doubtful`` and ``validated_ms`` (the Ministry of Health validated the pair)."""
    import pandas as pd

    sheet = pd.read_excel(io.BytesIO(workbook), sheet_name="Mapeamento ativos", dtype=str)
    if sheet.shape[1] != 7:
        raise ValueError(f"the TUSS x SIGTAP mapping sheet has {sheet.shape[1]} columns, not the 7 it had; the layout drifted")
    sheet.columns = ["tuss_code", "tuss_term", "sigtap_code", "sigtap_name", "status", "grade", "validated"]
    rows = []
    for r in sheet.to_dict("records"):
        status = {"Mapeado": "mapped", "Não existe na Sigtap": "not_in_sigtap"}.get(r["status"], "not_yet_mapped")
        if isinstance(r["status"], str) and status == "not_yet_mapped":
            raise ValueError(f"unknown mapping status {r['status']!r}")
        sigtap = r["sigtap_code"] if status == "mapped" else None
        grade = r["grade"] if isinstance(r["grade"], str) else None
        if grade is not None and grade != "dúvida" and grade not in {str(k) for k in EQUIVALENCE}:
            raise ValueError(f"unknown degree of equivalence {grade!r}")
        rows.append({
            "tuss_code": str(r["tuss_code"]).strip(), "tuss_term": r["tuss_term"], "sigtap_code": sigtap.strip().zfill(10) if sigtap else None,
            "sigtap_name": r["sigtap_name"] if status == "mapped" else None, "mapping": status,
            "equivalence": int(grade) if grade and grade.isdigit() else None, "doubtful": grade == "dúvida",
            "validated_ms": r["validated"] == "Validado pelo MS"})
    return rows


def build(settings: Any, *, ship: bool = False) -> dict[str, Any]:
    """Download both files and write the registry (``registries/tuss``: ``code_windows``, ``terms``, ``tuss_sigtap``); with
    ``ship`` also the package's own ``resources/tuss.parquet``. Returns what was read."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    from ..transport import download

    folder = settings.registry_dir(FOLDER)
    raw = folder / "raw"
    terms_zip = download(TERMS_URL, raw / "pda-049-tuss.zip")
    mapping_zip = download(MAPPING_URL, raw / "padraotiss_mapeamento_tuss_sigtap.zip")
    with zipfile.ZipFile(terms_zip) as archive:
        terms = read_terms(archive)
    with zipfile.ZipFile(mapping_zip) as archive:
        member = next(n for n in archive.namelist() if n.lower().endswith(".xlsx"))
        mapping = read_mapping(archive.read(member))
    known = {r["term"] for r in terms if r["table"] == "22"}
    mapped = {r["tuss_code"] for r in mapping}
    # ANS lists each code once, as its current version: a term revised in 2024-06 starts then, though the code was used from its
    # implementation (2010-10): a code is valid from the earlier of its start and its implementation
    windows = [{"code": r["code"], "first": min(r["valid_from"], r["implemented"] or r["valid_from"]), "last": r["valid_to"] or "999912"}
               for r in terms]
    labels = [{"code": r["code"], "label": r["name"]} for r in terms]
    tables = {
        WINDOWS_FILE: pa.Table.from_pylist(windows, schema=pa.schema([("code", pa.string()), ("first", pa.string()), ("last", pa.string())])),
        TERMS_FILE: pa.Table.from_pylist(terms),
        MAPPING_FILE: pa.Table.from_pylist(mapping, schema=pa.schema([
            ("tuss_code", pa.string()), ("tuss_term", pa.string()), ("sigtap_code", pa.string()), ("sigtap_name", pa.string()),
            ("mapping", pa.string()), ("equivalence", pa.int8()), ("doubtful", pa.bool_()), ("validated_ms", pa.bool_())])),
    }
    for name, table in tables.items():
        pq.write_table(table, folder / name, compression="zstd")
    if ship:
        pq.write_table(pa.Table.from_pylist(labels), Path(__file__).resolve().parents[1] / "resources" / RESOURCE, compression="zstd")
    return {"terms": {t: sum(1 for r in terms if r["table"] == t) for t in TABLES}, "mapping_rows": len(mapping),
            "mapped_pairs": sum(1 for r in mapping if r["mapping"] == "mapped"), "tuss_codes_in_mapping": len(mapped),
            "table22_codes_in_mapping": len(mapped & known), "table22_codes_unmapped_by_the_workbook": len(known - mapped),
            "folder": str(folder), "shipped": ship}


def _table(name: str, settings: Any):
    import pyarrow.parquet as pq

    from ..config import load_settings

    path = (settings or load_settings()).registry_dir(FOLDER) / name
    if not path.is_file():
        raise FileNotFoundError(f"{path} is not built; run `pegasus-data tuss`")
    return pq.read_table(path)


def tuss_terms(codes: Sequence[str] | None = None, *, table: str = "22", settings: Any = None):
    """The TUSS terms of one table (22: procedures and health events; 63: groups) as ANS publishes them
    (pyarrow table: ``code`` (table and term), ``table``, ``term``, ``name``, ``valid_from``, ``valid_to`` (YYYYMM; null while valid),
    ``implemented``). ``codes`` keeps only those terms (the item's ``CD_PROCEDIMENTO``, without the table)."""
    import pyarrow as pa
    import pyarrow.compute as pc

    found = _table(TERMS_FILE, settings)
    found = found.filter(pc.equal(found["table"], str(table)))
    if codes is None:
        return found
    return found.filter(pc.is_in(found["term"], value_set=pa.array([str(c) for c in codes], type=pa.string())))


def tuss_sigtap(codes: Sequence[str] | None = None, *, sigtap: Sequence[str] | None = None, mapped_only: bool = True,
                settings: Any = None):
    """ANS's correspondence of TUSS table 22 to SIGTAP (pyarrow table, one row per pair): ``tuss_code``, ``tuss_term`` (its name),
    ``sigtap_code`` (10 digits) and ``sigtap_name``, ``mapping`` (``mapped``; ``not_in_sigtap``: ANS found no SIGTAP procedure
    for the term; ``not_yet_mapped``: the workbook has no answer), ``equivalence`` (1 same meaning, 2 same meaning with a synonym,
    3 the TUSS term is less specific than SIGTAP's, 4 more specific, 5 not mappable; null when unrated or ``doubtful``) and
    ``validated_ms``. One term maps to several procedures and a procedure from several terms: a pair is not a conversion.
    ``codes`` keeps the TUSS terms, ``sigtap`` the SIGTAP procedures; ``mapped_only=False`` keeps the terms with no pair too.
    The workbook is of April 2017 (TUSS of June 2016): later terms and later SIGTAP codes are not in it."""
    import pyarrow as pa
    import pyarrow.compute as pc

    found = _table(MAPPING_FILE, settings)
    if mapped_only:
        found = found.filter(pc.equal(found["mapping"], "mapped"))
    if codes is not None:
        found = found.filter(pc.is_in(found["tuss_code"], value_set=pa.array([str(c) for c in codes], type=pa.string())))
    if sigtap is not None:
        found = found.filter(pc.is_in(found["sigtap_code"], value_set=pa.array([str(c).zfill(10) for c in sigtap], type=pa.string())))
    return found
