"""Build the canonical ICD-10 table every ICD field in every system decodes with (ADR-0087).

Sources, best first:

1. DATASUS's official CID-10 tables (V2008, www2.datasus.gov.br/cid10,
   ``sources/cid10csv_v2008.zip``): chapters, groups, 3-character categories
   and subcategories, with FULL descriptions ("Síndrome nefrítica crônica -
   anormalidade glomerular minor"). The TabWin .CNV copies each system ships
   carry the abbreviated forms ("N03.9 NE"), which say nothing on their own.
2. DATASUS's own CID-10 v2019 tables (``CNVS_CID10_v2019.rar``, published
   2025-10-13 under ``ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/TAB/``;
   extract ``CID10_01.CNV`` ... ``CID10_22.CNV`` to ``sources/cnvs_cid10_v2019/``):
   the codes WHO added after 2008 and DATASUS now files (A97 dengue, R65 SIRS,
   K64 haemorrhoids, C86, U09, U10 ...), with DATASUS's full Portuguese
   descriptions. A code the 2008 edition already has keeps its 2008 label (a
   rewording is not a new meaning, and some labels of the v2019 files are cut
   at a column width). Checked against WHO's ICD-10 2019 browser for A97, K64,
   C86 and R65.
3. Codes added after 2008 that neither of those carries (U07.1 COVID-19 and
   others), taken from the newest kit tables in the maintainer catalog's
   dictionary, labelled from the longest description found, with any leading
   code stripped.
4. SIM's filler: a 3-character category is also written ``I64X``. Each
   category gets that form too.

Writes ``src/pegasus_data/resources/icd10.parquet`` with columns code, label,
level (category, subcategory) and source. (Chapters and groups are not written here; the docstring said they were until 2026-10-04.)

    python scripts/build_icd10.py [catalog]
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from pegasus_data.config import label_build_catalog

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "sources" / "cid10csv_v2008.zip"
OUT = ROOT / "src" / "pegasus_data" / "resources" / "icd10.parquet"
CATALOG = label_build_catalog()
V2019 = ROOT / "sources" / "cnvs_cid10_v2019"


def _rows(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = zf.read(name).decode("latin-1")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def official() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    with zipfile.ZipFile(SOURCE) as zf:
        for r in _rows(zf, "CID-10-CATEGORIAS.CSV"):
            out[r["CAT"].strip()] = (r["DESCRICAO"].strip(), "category")
        for r in _rows(zf, "CID-10-SUBCATEGORIAS.CSV"):
            code = r["SUBCAT"].strip()
            # The subcategory file also lists undivided 3-character codes (I64);
            # the level follows the code, not the file.
            out[code] = (r["DESCRICAO"].strip(), "subcategory" if len(code) == 4 else "category")
    return out


#: A line of DATASUS's CID10_NN.CNV: sequence, an optional marker (``&`` new, ``@`` reworded, ``#`` retired,
#: as the files print it), the code, the label, the code again in the match column.
_CNV_LINE = re.compile(r"^\s*\d+\s+[#&@]?([A-Z]\d{2,3})\s+(.*)$")


def datasus_v2019(known: set[str]) -> dict[str, tuple[str, str]]:
    """The codes of DATASUS's CID-10 v2019 tables that ``known`` (the 2008 edition) lacks."""
    out: dict[str, tuple[str, str]] = {}
    if not V2019.is_dir():
        raise FileNotFoundError(f"{V2019}: extract CNVS_CID10_v2019.rar there (see the module docstring)")
    for path in sorted(V2019.iterdir()):
        if not re.fullmatch(r"CID10_\d\d\.cnv", path.name, re.I):
            continue
        for line in path.read_bytes().decode("cp1252").splitlines():
            m = _CNV_LINE.match(line)
            if not m or m.group(1) in known:
                continue
            code = m.group(1)
            label = re.sub(r"\s*" + code + r"\s*,?\s*$", "", m.group(2).rstrip()).strip()
            out[code] = (label, "subcategory" if len(code) == 4 else "category")
    return out


_LEADING_CODE = re.compile(r"^[A-Z]\d{2}(\.\d)?[\s\-]+")


def later_codes(catalog: Path, known: set[str]) -> dict[str, tuple[str, str]]:
    """Codes the kits carry that the 2008 edition lacks, e.g. U07.1."""
    if not catalog.exists():
        return {}
    con = sqlite3.connect(f"file:{catalog}?mode=ro", uri=True)
    best: dict[str, str] = {}
    for code, label in con.execute(
        "SELECT value_raw, value_label FROM dictionary "
        "WHERE value_group IN ('CID10', 'CID1017', 'CID10_3D') AND value_label IS NOT NULL"
    ):
        code = str(code).strip().upper().replace(".", "")
        if not re.fullmatch(r"[A-Z]\d{2,3}", code) or code in known:
            continue
        text = _LEADING_CODE.sub("", str(label).strip())
        if len(text) > len(best.get(code, "")):
            best[code] = text
    return {c: (lbl, "subcategory" if len(c) == 4 else "category") for c, lbl in best.items()}


#: WHO emergency codes added after the 2008 edition, as DATASUS's SIM codes COVID-19 deaths from 2020 (WHO ICD-10
#: updates, 2020-2021). They keep their own source, ``who_update``: the code-tree build dates them 2020-01, and
#: DATASUS's v2019 tables print the same titles.
SUPPLEMENT = {
    "U071": "COVID-19, vírus identificado",
    "U072": "COVID-19, vírus não identificado",
    "U099": "Condição pós-COVID-19, não especificada",
    "U109": "Síndrome inflamatória multissistêmica associada à COVID-19, não especificada",
}


def main() -> int:
    catalog = Path(sys.argv[1]) if len(sys.argv) > 1 else CATALOG
    table = official()
    source = dict.fromkeys(table, "cid10_v2008")
    for code, label in SUPPLEMENT.items():
        if code not in table:
            table[code] = (label, "subcategory")
            source[code] = "who_update"
    for code, value in datasus_v2019(set(table)).items():
        table[code] = value
        source[code] = "datasus_cid10_v2019"
    # A kit label already shipped stays: the kit text varies with what the catalog holds, and the longest is not
    # always the same one.
    if OUT.is_file():
        for r in pq.read_table(OUT).to_pylist():
            if r["source"] == "kit" and r["code"] not in table:
                table[r["code"]] = (r["label"], r["level"])
                source[r["code"]] = "kit"
    for code, value in later_codes(catalog, set(table)).items():
        table[code] = value
        source[code] = "kit"
    # SIM writes a category as I64X; the filler form decodes as its category.
    for code, (label, level) in list(table.items()):
        if level == "category" and f"{code}X" not in table:
            table[f"{code}X"] = (label, level)
            source[f"{code}X"] = source[code] + "+filler"
    codes = sorted(table)
    pq.write_table(
        pa.table({
            "code": codes,
            "label": [table[c][0] for c in codes],
            "level": [table[c][1] for c in codes],
            "source": [source[c] for c in codes],
        }),
        OUT, compression="zstd",
    )
    # The bundled resource is checked against the manifest's checksum when it is read.
    manifest_path = OUT.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["resources"]["icd10"]
    entry.update(bytes=OUT.stat().st_size, sha256=hashlib.sha256(OUT.read_bytes()).hexdigest(), rows=len(codes))
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    levels: dict[str, int] = {}
    for c in codes:
        levels[source[c]] = levels.get(source[c], 0) + 1
    print(f"wrote {OUT.relative_to(ROOT)}: {len(codes)} codes {levels}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
