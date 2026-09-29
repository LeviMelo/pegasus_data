"""Inventory of register-like variables: fields whose value identifies an entity.

An establishment (CNES), a health team (INE), a legal entity (CNPJ), a person
(CPF, CNS), a municipality (IBGE) or an occupation (CBO) is not a category
from a short code table: it points into a registry, and the registry is what
links datasets to one another. This lists every curated field of that kind,
what it is bound to, and flags the ones bound to nothing, so the gaps in
linkage are visible in one place.

    python scripts/registry_fields.py [out.json]
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VARIABLES = ROOT / "src" / "pegasus_data" / "curation" / "variables"

#: (kind, what the name says, what the description says). Order matters: the
#: first kind that matches wins.
KINDS = [
    ("person", r"(^|_)(CPF|CNS)(_|$|PCN|PAC|MED|PROF|EXE|SOL|DIR|RES|AUT|NUMERO)|CNSPCN|CNS_PAC|CPF_PAC|CPFPCN|NUMCNS",
     r"cart[aã]o nacional de sa[uú]de|\bcpf\b"),
    ("team", r"(^|_)INE($|_)|CNES_ESF|ID_EQUIPE|CO_EQUIPE", r"equipe .*\(ine\)|identificador nacional de equipe|\bine\b"),
    ("legal_entity", r"CNPJ|CGC", r"\bcnpj\b"),
    ("establishment", r"CNES|CODUNI|UNISOL|CODESTAB|ID_UNIDADE|ID_UNID|UNI_ATENDE|ESTAB_|LOCAL_UNID|HOSPITAL",
     r"c[oó]digo cnes|cnes (code|do estabelecimento)|establishment'?s? cnes"),
    ("municipality", r"MUN|CODMUN|MUNIC|_MUNI|UFMUN", r"munic[ií]pio"),
    ("occupation", r"CBO|OCUP", r"\bcbo\b|ocupa[cç][aã]o"),
]


def classify(name: str, body: dict) -> str | None:
    text = " ".join(str(body.get(k) or "") for k in ("official_name", "translated_name", "description")).lower()
    for kind, name_re, text_re in KINDS:
        if re.search(name_re, name.upper()) or re.search(text_re, text):
            return kind
    return None


def main() -> int:
    rows = []
    for path in sorted(VARIABLES.rglob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, body in (data.get("variables") or {}).items():
            body = body or {}
            kind = classify(str(name), body)
            if not kind:
                continue
            bound = ([body["codelist"]] if body.get("codelist") else []) + list(body.get("codelists") or [])
            rows.append({
                "system": data.get("system"), "file": f"{path.parent.name}/{path.name}", "field": name,
                "kind": kind, "code_system": body.get("code_system"), "bound": bound,
                "label_via": body.get("label_via"), "inline": bool(body.get("codes")),
            })
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "probes" / "registry_fields.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    by_kind: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        state = "bound" if (r["bound"] or r["label_via"] or r["inline"]) else (
            "identifier (not resolved)" if r["code_system"] == "none" else "UNBOUND")
        by_kind[r["kind"]][state] += 1
    for kind, counts in sorted(by_kind.items()):
        print(f"{kind:14} {dict(counts)}")
    print(f"wrote {out} ({len(rows)} fields)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
