"""Build every classification bridge into one resource (ADR-0101, ADR-0104).

A bridge carries a code from a classification that was replaced into the one
that replaced it, so a series spans the change. Each row is one claim: old code,
new code, how strong the claim is, and where it comes from. A code crosses only
when its claim is unique (``view.bridged``):

* ``SIGTAP_A`` / ``SIGTAP_H``: pre-2008 SIA/SIH procedures -> SIGTAP, from the
  official Tabela Unificada (``tb_sia_sih``, ``rl_procedimento_sia_sih``). The
  claim is the official link; an old code with several successors never crosses.
* ``CBO94``: CBO 1994 -> CBO 2002.
  - For the codes CNES used, the conversion DATASUS itself applied to the
    registered professionals in August 2007 (Portaria SAS 370/2007 §2),
    measured by ``scripts/measure_cbo_conversion.py``: the share of paired
    professionals that moved to the new code. It crosses at 95% or more.
  - For other CBO 94 codes, the Ministry of Labour's official conversion
    (``sources/CBO94 - CBO2002 - Conversao.csv``), where it names one code.

    python scripts/build_bridges.py [tabela-unificada.zip] [observed.json]

Writes ``src/pegasus_data/resources/bridges.parquet``.
"""

from __future__ import annotations

import csv
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "pegasus_data" / "resources" / "bridges.parquet"
TUP = ROOT / "sources" / "sigtap" / "new.zip"
OBSERVED = ROOT / "data" / "probes" / "cbo_conversion_observed.json"
MTE = ROOT / "sources" / "CBO94 - CBO2002 - Conversao.csv"


def main() -> int:
    tup = Path(sys.argv[1]) if len(sys.argv) > 1 else TUP
    observed_path = Path(sys.argv[2]) if len(sys.argv) > 2 else OBSERVED
    rows: list[tuple[str, str, str, float, str]] = []  # bridge, old, new, strength, source

    with zipfile.ZipFile(tup) as z:
        links: dict[tuple[str, str], set[str]] = defaultdict(set)
        for line in z.read("rl_procedimento_sia_sih.txt").decode("latin-1").splitlines():
            if line.strip():
                links[(line[10:20].strip(), line[20:21])].add(line[0:10].strip())
    for (old, kind), targets in sorted(links.items()):
        for new in sorted(targets):
            rows.append((f"SIGTAP_{kind}", old, new, 1.0 / len(targets), f"Tabela Unificada {tup.name}"))

    observed = json.loads(observed_path.read_text(encoding="utf-8"))["codes"] if observed_path.is_file() else {}
    for old, claim in sorted(observed.items()):
        for new, count in claim["targets"].items():
            rows.append(("CBO94", old, new, round(count / claim["total"], 4),
                         f"observed: CNES Jul->Aug 2007 conversion, {claim['total']} professionals"))
    mte: dict[str, set[str]] = defaultdict(set)
    for record in list(csv.reader(MTE.open(encoding="latin-1"), delimiter=";"))[1:]:
        if len(record) >= 2 and record[0].strip() and record[1].strip():
            mte[record[0].strip()].add(record[1].strip())
    for old, targets in sorted(mte.items()):
        if old in observed:
            continue  # CNES's own conversion is what its records followed
        for new in sorted(targets):
            rows.append(("CBO94", old, new, 1.0 / len(targets), "MTE official conversion CBO94-CBO2002"))

    pq.write_table(pa.table({
        "bridge": [r[0] for r in rows], "old_code": [r[1] for r in rows], "new_code": [r[2] for r in rows],
        "strength": pa.array([r[3] for r in rows], pa.float64()), "source": [r[4] for r in rows],
    }), OUT, compression="zstd")
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r[0]] += 1
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} claims {dict(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
