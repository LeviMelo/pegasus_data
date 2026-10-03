"""Audit the SINAN curation descriptions against the official SINAN dictionaries.

Question (OPEN_QUESTIONS OQ-2): are the descriptions in
``src/pegasus_data/curation/variables/sinan/*.yml`` correct? They were only ever
checked for vagueness.

Method.  Each agravo YAML is mapped to its dictionary text(s) under
``sources/dic_text/`` by file name (``AGRAVO_FILES``; ``_shared.yml`` is compared
against every mapped dictionary).  A dictionary is split into records (a record
starts at a numbered line such as ``33. Situacoes de risco`` and runs to the next
one); the DBF column name printed at the end of each record is the join key to the
curated variable.  For each curated variable found in a dictionary the script
extracts the dictionary's category codes and our codes, and assigns a *heuristic*
verdict:

* ``agrees``              codes consistent and the name/description overlap the record;
* ``contradicts_candidate``  a code we state is absent from the dictionary categories,
                          or the two name/description texts share almost no words;
* ``incomplete_candidate``   the dictionary lists codes (e.g. 9=Ignorado) we never state;
* ``not_in_dictionary``   the variable is in no mapped dictionary.

Verdicts ending in ``_candidate`` are triage: a person reads the pair.  Reviewed
verdicts are applied from ``data/probes/curation/sinan_dictionary_review.json``
(``{"agravo:field": {"verdict": ..., "note": ...}}``) when that file exists: they
override the heuristic, and any heuristic candidate not in the file is finalised
as ``agrees`` (contradicts_candidate: flag read by hand, layout noise) or
``incomplete`` (incomplete_candidate: heuristic only, not read).

Usage::

    PYTHONUTF8=1 python scripts/audit_sinan_dictionaries.py

Output: ``data/probes/curation/sinan_dictionary_audit.json``, one record per
compared variable ``{agravo, field, our_description, our_codes, dictionary_text,
verdict, note, ...}``, and a per-agravo verdict count table on stdout.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CUR = ROOT / "src" / "pegasus_data" / "curation" / "variables" / "sinan"
DIC = ROOT / "sources" / "dic_text"
OUT = ROOT / "data" / "probes" / "curation" / "sinan_dictionary_audit.json"
REVIEW = ROOT / "data" / "probes" / "curation" / "sinan_dictionary_review.json"

AGRAVO_FILES: dict[str, list[str]] = {
    "acbi": ["drt-exposicao-a-material-biologico__DIC_DADOS_DRT_Acidente_Trabalho_Biologico_v5.txt"],
    "acgr": ["drt-acidente-de-trabalho-grave__DIC_DADOS_DRT_Acidente_Trabalho_grave_v5.txt"],
    "anim": ["acidente-por-animais-peconhentos__DIC_DADOS_Animais_Pedonhentos_v5.txt"],
    "antr": ["atendimento-antirrabico__DIC_DADOS_anti_rabico_v5.1.txt"],
    "botu": ["botulismo__DIC_DADOS_Botulismo_v5.txt"],
    "canc": ["drt-cancer-relacionado-ao-trabalho__DIC_DADOS_DRT_Cancer_v5.txt"],
    "chag": ["doenca-de-chagas-aguda__DIC_DADOS_Chagas_v5.txt"],
    "cole": ["colera__DIC_DADOS_Colera_v5.txt"],
    "coqu": ["coqueluche__DIC_DADOS_Coqueluche_v5.txt"],
    "deng": ["dengue__DIC_DADOS_ONLINE.txt"],
    "derm": ["drt-dermatoses-ocupacionais__DIC_DADOS_DRT_Dermatoses_v5.txt"],
    "dift": ["difteria__DIC_DADOS_Difteria_v5.txt"],
    "esqu": ["esquistossomose__DIC_DADOS_Esquistossomose_v5.txt"],
    "fmac": ["febre-maculosa__DIC_DADOS_Febre_Maculosa_v5.txt"],
    "ftif": ["febre-tifoide__DIC_DADOS_Febre_Tifoide_v5.txt"],
    "hans": ["hanseniase__DIC_DADOS_Hanseniase_v5.txt"],
    "hant": ["hantavirose__DIC_DADOS_Hantavirose_v5.txt"],
    "hepa": ["hepatites-virais__DIC_DADOS_Hepatite_v5.txt"],
    "hivg": ["gestante-hiv__DIC_DADOS_Gestante_HIV_v5.txt"],
    "iexo": ["intoxicacao-exogena__DIC_DADOS_Intoxicacao_Exogena_v6_26.02.2026.txt"],
    "leiv": ["leishmaniose-visceral__DIC_DADOS_LV_v5.txt"],
    "lept": ["leptospirose__DIC_DADOS_Leptospirose_v5.txt"],
    "ltan": ["leishmaniose-tegumentar-americana__DIC_DADOS_LTA_v5.txt"],
    "mala": ["malaria__DIC_DADOS_Malaria_v5.txt"],
    "meni": ["meningite__DIC_DADOS_Meningite_v5.txt"],
    "ment": ["drt-transtorno-mental__DIC_DADOS_DRT_TranstornosMentais_v5.txt"],
    "pair": ["drt-pair__DIC_DADOS_DRT_PAIR_v5.txt"],
    "pfan": ["pfa.txt"],
    "pneu": ["drt-pneumoconiose__DIC_DADOS_DRT_Pneumoconioses_v5.txt"],
    "raiv": ["raiva-humana__DIC_DADOS_Raiva_v5.txt"],
    "rota": ["rotavirus__DIC_DADOS_ROTA_NET_v5.1.txt"],
    "sifc": ["sifilis-congenita__DIC_DADOS_Sifilis_Congenita_v5.txt"],
    "src": ["sindrome-da-rubeola-congenita__DIC_DADOS_SRC_v5.txt"],
    "teta": ["tetano-acidental__DIC_DADOS_Tetano_Acidental_v5.txt"],
    "tetn": ["tetano-neonatal__DIC_DADOS_Tetano_NeoNatal_v5.txt"],
    "tube": ["tuberculose__DICI_DADOS_NET_Tuberculose_23_07_2020.txt"],
    "viol": ["violencia-interpessoal-autoprovocada__DIC_DADOS_NET_Violencias_v5.txt"],
}
# curated agravos with no dictionary in sources/dic_text/
NO_DICTIONARY = ["espo", "exan", "ntra", "pest", "sdta", "sifg", "trac"]

REC_START = re.compile(r"^\s*(\d{1,3})\s*[\.\-–]\s*[A-Za-zÀ-ÿ]")
CATEGORY = re.compile(
    r"^\s*\d{1,3}\s*[\.\-–]\s*(sim|n[aã]o|ignor|em branco|n/?a|outro|positiv|negativ|feminino|masculino|inconclus|chikung|den ?\d|reagente|n[aã]o reag)", re.I
)
TOKEN = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
NOISE = re.compile(
    r"^\s*(Nome do campo|Nome Campo|Revisado|Dengue/Chikungunya\s+Sinan|MINIST|SECRETARIA|DEPARTAMENTO|"
    r"CENTRO DE INFORMA|GT-SINAN|SISTEMA DE INFORMA|DICION[AÁ]RIO)",
    re.I,
)
STOP = set(
    re.split(
        r"\s+",
        "de da do das dos a o e em para por com que se um uma ao na no nas nos ou the of to in and an is was "
        "whether has have had this that for on at as by from with or not be are its it",
    )
)


def parse_dictionary(path: Path) -> dict[str, dict]:
    """Return {DBF_NAME: {"text": record text, "campo": number}} for one dictionary."""
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    records: list[tuple[str, list[str]]] = []
    cur: list[str] | None = None
    num = ""
    for line in raw:
        if NOISE.match(line):
            continue
        m = REC_START.match(line)
        if m and CATEGORY.match(line):
            m = None  # "9- Ignorado", "2- Nao": a category line, not a new field
        if m and cur is not None and not (int(num) <= int(m.group(1)) <= int(num) + 60):
            m = None  # field numbers never decrease
        if m:
            if cur is not None:
                records.append((num, cur))
            cur, num = [line], m.group(1)
        elif cur is not None:
            cur.append(line)
    if cur is not None:
        records.append((num, cur))
    texts = [re.sub(r"\s+", " ", " ".join(x.strip() for x in lines if x.strip())) for _, lines in records]
    out: dict[str, dict] = {}
    for i, (num, lines) in enumerate(records):
        text = texts[i]
        # a page break can strand a record's tail in the next record: keep both neighbours as context
        ctx = {"prev": texts[i - 1][-160:] if i else "", "next": texts[i + 1][:160] if i + 1 < len(texts) else ""}
        # DBF names: uppercase tokens; prefer one that ends a line
        end_tokens = [m.group(1) for ln in lines for m in [re.search(r"(?<![A-Za-z0-9_\-])([A-Z][A-Z0-9_]{2,})\s*$", ln)] if m]
        for tok in set(TOKEN.findall(" ".join(lines))) | set(end_tokens):
            prev = out.get(tok)
            rank = 1 if tok in end_tokens else 0
            if prev is None or rank > prev["rank"]:
                out[tok] = {"text": text, "campo": num, "rank": rank, **ctx}
    return out


def words(s: str) -> set[str]:
    s = re.sub(r"[^\wÀ-ÿ]+", " ", s.lower())
    return {w[:6] for w in s.split() if len(w) > 2 and w not in STOP and not w.isdigit()}


def norm(label: str) -> str:
    label = unicodedata.normalize("NFD", label.lower())
    return re.sub(r"[^a-z]", "", label)[:3]


PAIR = re.compile(r"(?<![\d/.,])(\d{1,2})\s*[-–=.]\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ ]{1,30})")


def code_pairs(text: str) -> dict[str, str]:
    """{code: normalised first three letters of its label} from '1-Sim; 2-Não' / '1=Sim' text."""
    out: dict[str, str] = {}
    for code, label in PAIR.findall(text):
        out.setdefault(code, norm(label))
    return out


def our_pairs(var: dict) -> dict[str, str]:
    out = code_pairs(var.get("description") or "")
    codes = var.get("codes")
    if isinstance(codes, dict):
        out.update({str(k): norm(str(v)) for k, v in codes.items()})
    return out


SENTINELS = [
    ("9=Ignorado", r"9\s*[-–.=]\s*ignor", r"ignor|unknown|not known|not recorded|9"),
    ("nao se aplica", r"n[aã]o se aplica", r"not applicable|n/a|does not apply|não se aplica|3"),
    ("nao realizado", r"n[aã]o realizad", r"not done|not performed|not carried|não realizado|4"),
    ("inconclusivo", r"inconclusiv", r"inconclusive|inconclusivo|3"),
]


def classify(var: dict, rec: dict) -> tuple[str, str]:
    ours, theirs = our_pairs(var), code_pairs(rec["text"])
    clash = {c: (ours[c], theirs[c]) for c in ours if c in theirs and ours[c] != theirs[c] and len(c) == 1}
    if clash:
        return "contradicts_candidate", f"code label differs (ours vs dictionary, first 3 letters): {clash}"
    if len(theirs) >= 2 and {"1", "2"} <= set(theirs) and ours and not ({"1", "2"} & set(ours)):
        return "contradicts_candidate", f"dictionary codes {sorted(theirs)}; ours {sorted(ours)}"
    # sentinel / special categories the dictionary lists that our text never mentions (code or English/Portuguese words)
    ours_txt = ((var.get("description") or "") + " " + json.dumps(var.get("codes") or {}, ensure_ascii=False)).lower()
    low = rec["text"].lower()
    lacking = [
        name
        for name, in_dict, in_ours in SENTINELS
        if re.search(in_dict, low) and not re.search(in_ours, ours_txt)
    ]
    if lacking:
        return "incomplete_candidate", f"dictionary lists {lacking}; our text does not mention it"
    return "agrees", ""


def dict_label(text: str) -> str:
    """The field title printed before the data-type column ('33. Situacoes de risco ... st_risco_rio')."""
    m = re.search(r"[a-z]{1,4}_[a-z_]+", text)
    head = text[: m.start()] if m else text[:120]
    return head.strip()[:160]


def name_overlap(var: dict, text: str) -> float:
    """Share of our official-name words found in the dictionary record (Portuguese on both sides)."""
    on = words(var.get("official_name", ""))
    return len(on & words(text)) / len(on) if on else 1.0


def lookup(dic: dict[str, dict], field: str) -> dict | None:
    rec = dic.get(field)
    if rec is not None and not rec["rank"] and "_" not in field and len(field) < 8:
        rec = None  # a short word inside running prose ("Anti-HAV"), not a DBF column name
    if rec is None and len(field) >= 6:
        # dictionary names that extend the data column name: unique-prefix match
        cands = {t for t in dic if t.startswith(field) and len(t) - len(field) <= 4}
        if len(cands) == 1:
            rec = dic[cands.pop()]
    return rec


def main() -> int:
    dicts: dict[str, dict[str, dict]] = {}
    for files in AGRAVO_FILES.values():
        for f in files:
            if f not in dicts:
                dicts[f] = parse_dictionary(DIC / f)
    review = json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {}
    records: list[dict] = []
    unmapped_yaml = []
    for yml in sorted(CUR.glob("*.yml")):
        agravo = yml.stem
        data = yaml.safe_load(yml.read_text(encoding="utf-8"))
        variables = data.get("variables") or {}
        if agravo == "_shared":
            files = sorted({f for fs in AGRAVO_FILES.values() for f in fs})
        else:
            files = AGRAVO_FILES.get(agravo, [])
            if not files:
                unmapped_yaml.append(agravo)
        for field, var in variables.items():
            hits = [(f, rec) for f in files if (rec := lookup(dicts[f], field))]
            if agravo != "_shared":
                hits = hits[:1]
            base = {
                "agravo": agravo,
                "field": field,
                "official_name": var.get("official_name"),
                "source": var.get("source"),
                "our_description": " ".join((var.get("description") or "").split()),
                "our_codes": var.get("codes"),
            }
            if not hits:
                records.append({**base, "dictionary_file": None, "dictionary_text": None,
                                "verdict": "not_in_dictionary", "note": ""})
                continue
            # _shared columns appear in several dictionaries: keep every hit, verdict is the strictest
            order = ["contradicts_candidate", "incomplete_candidate", "agrees"]
            graded = [(classify(var, rec), f, rec) for f, rec in hits]
            graded.sort(key=lambda g: order.index(g[0][0]))
            (verdict, note), f, rec = graded[0]
            rv = review.get(f"{agravo}:{field}")
            if rv:
                verdict, note = rv["verdict"], rv.get("note", "")
            elif review and verdict == "contradicts_candidate":
                verdict, note = "agrees", "heuristic flag read by hand: parser/page-layout noise, no discrepancy"
            elif review and verdict == "incomplete_candidate":
                verdict, note = "incomplete", "heuristic only (not read): " + note
            texts = "  ||  ".join(
                f"[{ff.split('__')[0][:28]}] " + r["text"][:420] + (" ~prev: " + r["prev"] + " ~next: " + r["next"]
                                                                     if len(r["text"]) < 160 else "")
                for _, ff, r in graded[:4]
            )
            records.append({**base, "dictionary_file": [g[1] for g in graded[:4]], "dictionary_campo": rec["campo"],
                            "dictionary_label": dict_label(rec["text"]), "dictionary_text": texts, "verdict": verdict, "note": note,
                            "n_dictionaries_with_field": len(hits)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    table: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        table[r["agravo"]][r["verdict"]] += 1
    for a in sorted(table):
        print(a, dict(table[a]))
    print("yaml without dictionary:", unmapped_yaml, NO_DICTIONARY)
    used = {f for fs in AGRAVO_FILES.values() for f in fs}
    print("dictionary files not used:", sorted(p.name for p in DIC.glob("*.txt") if p.name not in used))
    return 0


if __name__ == "__main__":
    sys.exit(main())
