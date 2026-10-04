"""Draft `curation/roles/<dataset>.yml`: a role for every column (handoff §2, DESIGN §3.2).

Every column of a dataset (the union of its families' schemas in the catalog)
gets a first guess at three statements, from the typing the project already
holds:

* value kind, from the column's codelists (a classification tree, a
  municipality table, an establishment registry), its inline codes, its DBF
  type, and the linkage role that normalises it;
* model role, from the dataset's semantic axes (time -> when, geography ->
  where), identifier and institution columns, and the linkage roles' entities;
* `entity.property`, from the linkage role when one names the column, else a
  placeholder for review.

The draft is marked `review: draft` per column; a reviewed column drops it.
An existing file is never overwritten: drafts go to `<dataset>.draft.yml`.

    python scripts/draft_column_roles.py [pegasus_data_home/_catalog/catalog.sqlite]
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CURATION = ROOT / "src" / "pegasus_data" / "curation"
OUT = CURATION / "roles"

#: dataset -> (system, series, variables file stem, datasets-yml key, record)
DATASETS = {
    "SIM-DO": ("SIM", "DO", None, "SIM_DO", "death"),
    "SINASC-DN": ("SINASC", "DN", None, "SINASC_DN", "birth"),
    "SIH-RD": ("SIHSUS", "RD", "rd", "SIHSUS_RD", "admission"),
    "CIHA": ("CIHA", "CIHA", "ciha", "CIHA", "admission"),
    **{f"SINAN-{s}": ("SINAN", s, s.lower(), "SINAN", "notification")
       for s in ("DENG", "CHIK", "ZIKA", "TUBE", "HANS", "SIFC", "SIFG", "SIFA", "VIOL", "MENI", "LEPT", "IEXO")},
}

TREES = re.compile(r"^(ICD10|CID10.*|CID9.*|S_CID|SIGTAP|TPROC.*|PROC.*|CBO.*|OCUPA.*|CNAE.*|CID.*)$", re.I)
PLACES = re.compile(r"^(MUNIC.*|MUNICBR|BR_MUNIC.*|CADMUN|UF.*|PAIS.*|TABPAIS|NATURALIDADE|REGIAO.*|CIR.*)$", re.I)
INSTITUTIONS = re.compile(r"^(CADGERBR|CNES.*|ESTAB.*|SIA_UPS_BR|CNPJ.*|UPS.*)$", re.I)
IDENTIFIERS = re.compile(
    r"^(N_AIH|AIH|NUMERODO|NUMERODN|NUMERODV|NU_NOTIFIC|NU_DO|NUMSUS|CNS.*|.*_CNS|CPF.*|.*_CPF|NU_CNS|"
    r"CONTADOR|SEQUENCIA|SEQ_AIH5|NU_LOTE.*|ID_AGRAVO_?|NUDIASINF)$", re.I)
TEXT = re.compile(r"(_DESC|_O|_OUT|DESCR|OBS|_ESP|ESPECIF)$", re.I)


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {} if path.exists() else {}


def _docs(system: str, stem: str | None) -> dict[str, dict]:
    folder = CURATION / "variables" / {"SIHSUS": "sihsus"}.get(system, system.lower())
    out: dict[str, dict] = {}
    for f in [folder / "_shared.yml", *([folder / f"{stem}.yml"] if stem else [])]:
        for name, body in (_yaml(f).get("variables") or {}).items():
            if isinstance(body, dict):
                out[str(name).upper()] = {**out.get(str(name).upper(), {}), **body}
    return out


def _axes(key: str) -> tuple[dict[str, str], dict[str, str]]:
    when: dict[str, str] = {}
    where: dict[str, str] = {}
    for f in (CURATION / "datasets").glob("*.yml"):
        body = (_yaml(f).get("datasets") or {}).get(key)
        if body is None and key == "SINAN":
            body = _yaml(f).get("sinan") or _yaml(f).get("SINAN")
        axes = (body or {}).get("semantic_axes") or {}
        for name, spec in (axes.get("time") or {}).items():
            for col in spec.get("fields") or ():
                when[str(col).upper()] = str(name)
        for name, spec in (axes.get("geography") or {}).items():
            for col in spec.get("fields") or ():
                where[str(col).upper()] = str(name)
    return when, where


def _linkage(dataset: str) -> dict[str, list[str]]:
    body = (_yaml(CURATION / "roles.yml").get("datasets") or {}).get(dataset) or {}
    out: dict[str, list[str]] = {}
    for role, spec in (body.get("roles") or {}).items():
        out.setdefault(str(spec["column"]).upper(), []).append(str(role))
    return out


def _columns(conn: sqlite3.Connection, system: str, series: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    families = conn.execute(
        "SELECT schema_signature, time_min, time_max FROM families WHERE system=? AND series=?", (system, series)
    ).fetchall()
    for signature, lo, hi in families:
        for (name,) in conn.execute("SELECT field_name FROM schema_presence WHERE schema_signature=?", (signature,)):
            seen = out.setdefault(str(name).upper(), {"years": [lo, hi]})
            seen["years"] = [min(x for x in (seen["years"][0], lo) if x is not None) if lo else seen["years"][0],
                             max(x for x in (seen["years"][1], hi) if x is not None) if hi else seen["years"][1]]
    return out


def draft(dataset: str, conn: sqlite3.Connection) -> dict:
    system, series, stem, key, record = DATASETS[dataset]
    docs = _docs(system, stem)
    when, where = _axes(key)
    linked = _linkage(dataset)
    columns: dict[str, dict] = {}
    for name, seen in sorted(_columns(conn, system, series).items()):
        doc = docs.get(name, {})
        lists = [str(c) for c in [doc.get("codelist"), *(doc.get("codelists") or [])] if c]
        roles = linked.get(name, [])
        if name in when:
            kind, model = "date", "when"
        elif name in where:
            kind, model = "place", "where"
        elif IDENTIFIERS.match(name):
            kind, model = "identifier", "link_only"
        elif any(INSTITUTIONS.match(c) for c in lists):
            kind, model = "institution", "institution"
        elif any(PLACES.match(c) for c in lists):
            kind, model = "place", "mark"
        elif any(TREES.match(c) for c in lists):
            kind, model = "code_tree", "mark"
        elif lists or doc.get("codes") or doc.get("code_system") in ("internal", "external"):
            kind, model = "category", "mark"
        elif TEXT.search(name):
            kind, model = "text", "excluded"
        elif re.match(r"^(DT_|DATA|DT)", name):
            kind, model = "date", "mark"
        else:
            kind, model = "number" if doc.get("code_system") == "none" else "category", "mark"
        role = roles[0] if roles else f"{record}.{name.lower()}"
        entry: dict = {"role": role, "kind": kind, "model": model, "review": "draft"}
        if len(roles) > 1:
            entry["also"] = roles[1:]
        hint = doc.get("official_name") or doc.get("translated_name")
        if hint:
            entry["name"] = str(hint)
        if lists:
            entry["codelists"] = lists
        entry["years"] = seen["years"]
        columns[name] = entry
    # Columns the query derives (IDADE_anos, ADR-0070) are columns a user sees.
    for name, roles in sorted(linked.items()):
        if name not in columns:
            columns[name] = {"role": roles[0], "kind": "number", "model": "stratum" if "age" in roles[0] else "mark",
                             "review": "draft", "derived": True, **({"also": roles[1:]} if len(roles) > 1 else {})}
    return {"dataset": dataset, "record": record, "columns": columns}


def main() -> int:
    catalog = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "pegasus_data_home" / "_catalog" / "catalog.sqlite"
    conn = sqlite3.connect(catalog)
    OUT.mkdir(exist_ok=True)
    for dataset in DATASETS:
        body = draft(dataset, conn)
        target = OUT / f"{dataset}.yml"
        if target.exists():
            target = OUT / f"{dataset}.draft.yml"
        target.write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
        print(f"{target.name}: {len(body['columns'])} columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
