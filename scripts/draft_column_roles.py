"""Draft `curation/roles/<dataset>.yml`: a role for every column (handoff §2, DESIGN §3.2).

Every column of a dataset (the union of its families' schemas in the catalog)
gets a first guess at three statements, from the typing the project already
holds:

* value kind, from the column's codelists (a classification tree, a
  municipality table, an establishment registry), its inline codes, the
  form's own layout where its dictionary was harvested (a date, a number,
  free text, a code list, a code table it names: `harvest_codes.py`), and the
  linkage role that normalises it; a column the form documents is typed by
  the form, never by its name;
* model role, from the dataset's semantic axes (time -> when, geography ->
  where), identifier and institution columns, and the linkage roles' entities;
* `entity.property`, from the linkage role when one names the column; else,
  for a SINAN form, the notification block's own declaration
  (`roles/SINAN-_notification.yml`) or the reviewed role the same column has
  on another form that documents it alike (the same codes, or the same type
  where neither prints codes): one meaning, one statement; else a placeholder
  for review.

The draft is marked `review: draft` per column; a reviewed column drops it,
and a role taken from the block or a precedent says which in its `note`. An
existing file is never overwritten: drafts go to `<dataset>.draft.yml`.
Every SINAN form the catalog holds is a dataset (its series), not a list.

    python scripts/draft_column_roles.py [DATASET ...]
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import yaml

from pegasus_data.config import label_build_catalog
from pegasus_data.semantics.curation import harvested_field

ROOT = Path(__file__).resolve().parent.parent
CURATION = ROOT / "src" / "pegasus_data" / "curation"
OUT = CURATION / "roles"

#: dataset -> (system, series, variables file stem, datasets-yml key, record); SINAN's forms are added from the catalog
DATASETS = {
    "SIM-DO": ("SIM", "DO", None, "SIM_DO", "death"),
    "SINASC-DN": ("SINASC", "DN", None, "SINASC_DN", "birth"),
    "SIH-RD": ("SIHSUS", "RD", "rd", "SIHSUS_RD", "admission"),
    "CIHA": ("CIHA", "CIHA", "ciha", "CIHA", "admission"),
}


#: What a record of each system is about: the entity of its event properties. A dataset whose row is something else
#: says so in its review (CNES's equipment rows, SIA's production lines).
RECORDS = {"SIM": "death", "SINASC": "birth", "SIHSUS": "admission", "CIH": "admission", "CIHA": "admission",
           "SIASUS": "procedure", "CNES": "establishment", "SISCAN": "exam", "PNI": "vaccination", "RESP": "notification",
           "ESUSNOTIFICA": "notification", "PCE": "survey", "PAINEL_ONCOLOGIA": "case", "SISPRENATAL": "pregnancy",
           "IBGE": "area", "DADOS_ABERTOS": "procedure", "SINAN": "notification"}
#: The ontology's name for a system, under which `datasets/declared.yml` declares the axes it shares.
ONTOLOGY = {"SIASUS": "SIA", "SIHSUS": "SIH"}


def _datasets(conn: sqlite3.Connection) -> dict[str, tuple]:
    """`DATASETS` and every other dataset the catalog holds (a system's series), keyed ``SYSTEM-SERIES``."""
    out = dict(DATASETS)
    known = {(v[0], v[1]) for v in DATASETS.values()}
    for system, series in conn.execute("SELECT DISTINCT system, series FROM families ORDER BY system, series"):
        if (system, series) in known:
            continue
        stem = str(series).lower()
        folder = CURATION / "variables" / str(system).lower()
        out[f"{system}-{series}"] = (system, series, stem if (folder / f"{stem}.yml").exists() else None,
                                     f"{system}_{series}" if system != "SINAN" else "SINAN", RECORDS.get(system, "record"))
    return out


def _label(field: dict) -> str:
    """A form's label of a field, compared case, accents, numbering and spacing aside."""
    import unicodedata

    text = unicodedata.normalize("NFKD", str(field.get("label") or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text).split())


def _sibling_precedents(system: str, series: str) -> dict[str, tuple[dict, str]]:
    """Outside SINAN a column is documented once for its system (`variables/<system>/_shared.yml`), its meaning the
    same in every file of the system: the reviewed role a sibling dataset gives it is its role, where the siblings
    agree (SIM's DOEXT, DOINF and DOMAT are subsets of the death certificate SIM-DO reads; SIH's RJ is the AIH of RD).
    A column a sibling's own series file documents differently is no precedent."""
    from pegasus_data.semantics.curation import inherited

    names = {system.upper(), *(p.upper() for p in inherited(system)), *(
        k for k, v in {"SIH": "SIHSUS"}.items() if v == system.upper())}
    keys: dict[str, set] = {}
    first: dict[str, tuple[dict, str]] = {}
    for path in sorted(OUT.glob("*.yml")):
        if path.name.endswith(".draft.yml"):
            continue
        body = _yaml(path)
        ds = str(body.get("dataset") or path.stem).upper()
        if ds.split("-")[0] not in names or ds == f"{system}-{series}".upper():
            continue
        for col, entry in (body.get("columns") or {}).items():
            if entry.get("review") == "draft" or entry.get("derived"):
                continue
            keys.setdefault(col, set()).add((entry["role"], entry["kind"], entry["model"]))
            first.setdefault(col, (entry, ds))
    return {c: first[c] for c, found in keys.items() if len(found) == 1}


def _precedents(system: str, series: str) -> dict[str, tuple[dict, str]]:
    """The reviewed roles the system's other forms give each column, kept when the forms document it alike: the
    column -> (entry, the form it comes from). The block's declaration first; a column two forms read differently
    (EVOLUCAO, OUTRAS) has no precedent."""
    if system != "SINAN":
        return _sibling_precedents(system, series)
    out: dict[str, tuple[dict, str]] = {}
    block = (_yaml(OUT / "SINAN-_notification.yml").get("columns") or {})
    for col, entry in block.items():
        out[col] = (entry, "the notification block")
    keys: dict[str, set] = {}
    first: dict[str, tuple[dict, str]] = {}
    for path in sorted(OUT.glob("SINAN-*.yml")):
        other = path.stem.split("-", 1)[1]
        if other in (series, "_notification") or path.name.endswith(".draft.yml"):
            continue
        for col, entry in (_yaml(path).get("columns") or {}).items():
            if col in block or entry.get("review") == "draft":
                continue
            here, there = harvested_field("SINAN", series, col) or {}, harvested_field("SINAN", other, col) or {}
            if not there:
                continue                    # a form that does not document the column is no evidence either way
            # alike: the same label, and the same printed codes or the same type. Neither alone is a meaning: every
            # yes/no shares 1 Sim / 2 Não / 9 Ignorado (TOSSE is "cough and/or diarrhoea" on LEIV's form), and
            # DT_COLETA is the blood bank's sample on HEPA's. A column neither form documents is not evidence
            # (CON_DOENCA: a disease on DENG's 2000-2006 layout, a yes/no on LEIV's)
            alike = _label(here) == _label(there) != "" and (
                (bool(here.get("codes")) and here.get("codes") == there.get("codes"))
                or (not here.get("codes") and not there.get("codes") and here.get("type") == there.get("type")))
            keys.setdefault(col, set()).add((entry["role"], entry["kind"], entry["model"]) if alike else None)
            first.setdefault(col, (entry, f"SINAN-{other}"))
    for col, found in keys.items():
        if len(found) == 1 and None not in found:
            out[col] = first[col]
    return out


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
    """A system's variable docs: its parent's where it republishes them (`curation.inherited`: Dados Abertos' APAC
    exports carry SIA's columns), its shared file, then the series' own."""
    from pegasus_data.semantics.curation import inherited

    out: dict[str, dict] = {}
    files = []
    for parent in inherited(system):
        files += sorted((CURATION / "variables" / parent.lower()).glob("*.yml"))
    folder = CURATION / "variables" / {"SIHSUS": "sihsus"}.get(system, system.lower())
    files += [folder / "_shared.yml", *([folder / f"{stem}.yml"] if stem else [])]
    for f in files:
        for name, body in (_yaml(f).get("variables") or {}).items():
            if isinstance(body, dict):
                out[str(name).upper()] = {**out.get(str(name).upper(), {}), **body}
    return out


def _axes(key: str, system: str = "") -> tuple[dict[str, str], dict[str, str]]:
    when: dict[str, str] = {}
    where: dict[str, str] = {}
    for f in (CURATION / "datasets").glob("*.yml"):
        body = (_yaml(f).get("datasets") or {}).get(key)
        if body is None and key == "SINAN":
            body = _yaml(f).get("sinan") or _yaml(f).get("SINAN")
        if body is None and system:          # the axes a system's datasets share (`declared.yml`)
            body = (_yaml(f).get("shared_by_system") or {}).get(ONTOLOGY.get(system, system))
        axes = (body or {}).get("semantic_axes") or {}
        for name, spec in (axes.get("time") or {}).items():
            for col in spec.get("fields") or ():
                when[str(col).upper()] = str(name)
        for name, spec in (axes.get("geography") or {}).items():
            for col in spec.get("fields") or ():
                where[str(col).upper()] = str(name)
    return when, where


def _linkage(dataset: str) -> dict[str, list[str]]:
    path = CURATION / "roles" / f"{dataset}.yml"
    columns = (_yaml(path).get("columns") or {}) if path.is_file() else {}
    return {str(column).upper(): [str(r) for r in (body.get("compare") or {})]
            for column, body in columns.items() if isinstance(body, dict) and body.get("compare")}


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
    system, series, stem, key, record = _datasets(conn)[dataset]
    docs = _docs(system, stem)
    when, where = _axes(key, system)
    linked = _linkage(dataset)
    precedents = _precedents(system, series)
    columns: dict[str, dict] = {}
    for name, seen in sorted(_columns(conn, system, series).items()):
        if name in precedents and name not in linked:
            entry, source = precedents[name]
            keep = ("years", "note") if system == "SINAN" else ("years", "note", "review")
            columns[name] = {**{k: v for k, v in entry.items() if k not in keep + (("missing",) if system == "SINAN" else ())},
                             "years": seen["years"], "note": f"role from {source}"}
            continue
        doc = docs.get(name, {})
        lists = [str(c) for c in [doc.get("codelist"), *(doc.get("codelists") or [])] if c]
        roles = linked.get(name, [])
        form = harvested_field(system, series, name) or {}
        table = str(form.get("table") or "")
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
        elif form.get("type") == "date":
            kind, model = "date", "mark"
        elif re.search(r"munic|UF|pa[ií]s|estado", table, re.I):
            kind, model = "place", "mark"
        elif re.search(r"CBO|ocupa|CID", table, re.I):
            kind, model = "code_tree", "mark"
        elif re.search(r"CNES|unidade|estabelecimento", table, re.I):
            kind, model = "institution", "institution"
        elif form.get("codes") or lists or doc.get("codes") or doc.get("code_system") in ("internal", "external"):
            kind, model = "category", "mark"
        elif form.get("type") == "number":
            kind, model = "number", "mark"
        elif form.get("type") == "text" and (form.get("width") or 99) > 2:
            # the form prints no codes and names no table: what is typed in (two characters hold no free text: a
            # code list the harvest could not read, left to the rules below)
            kind, model = "text", "excluded"
        elif TEXT.search(name):
            kind, model = "text", "excluded"
        elif re.match(r"^(DT_|DATA|DT)", name):
            kind, model = "date", "mark"
        else:
            kind, model = "number" if doc.get("code_system") == "none" else "category", "mark"
        role = roles[0] if roles else f"{record}.{name.lower()}"
        entry: dict = {"role": role, "kind": kind, "model": model, "review": "draft"}
        if kind == "place":
            # until a reviewer places it a drafted place is the record's (the one no field or flow reads); the dataset's
            # geography axis is where its events are placed
            entry["place_of"] = "event" if model == "where" else "record"
        if len(roles) > 1:
            entry["also"] = roles[1:]
        hint = doc.get("official_name") or doc.get("translated_name")
        if hint:
            entry["name"] = str(hint)
        if lists:
            entry["codelists"] = lists
        if form:
            entry["note"] = f"typed by the form ({form.get('source_ref')}): " + ", ".join(
                f"{k} {form[k]}" for k in ("type", "width", "table") if form.get(k)) + (
                f", {len(form['codes'])} codes" if form.get("codes") else "")
        entry["years"] = seen["years"]
        columns[name] = entry
    # Columns the query derives (IDADE_anos, ADR-0070) are columns a user sees: the linkage roles', and for a SINAN
    # form the notification block's own (its age stratum), where the form carries the column they are derived from.
    if system == "SINAN":
        block = (_yaml(OUT / "SINAN-_notification.yml").get("columns") or {})
        for name, entry in block.items():
            if entry.get("derived") and name not in columns and "NU_IDADE_N" in columns:
                columns[name] = {**entry, "note": f"{entry.get('note') or ''} (role from the notification block)".strip()}
    for name, roles in sorted(linked.items()):
        if name not in columns:
            columns[name] = {"role": roles[0], "kind": "number", "model": "stratum" if "age" in roles[0] else "mark",
                             "review": "draft", "derived": True, **({"also": roles[1:]} if len(roles) > 1 else {})}
    return {"dataset": dataset, "record": record, "columns": columns}


def main() -> int:
    conn = sqlite3.connect(label_build_catalog())
    OUT.mkdir(exist_ok=True)
    for dataset in sys.argv[1:] or _datasets(conn):
        body = draft(dataset, conn)
        target = OUT / f"{dataset}.yml"
        if target.exists():
            target = OUT / f"{dataset}.draft.yml"
        target.write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
        print(f"{target.name}: {len(body['columns'])} columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
