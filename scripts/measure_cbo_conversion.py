"""Measure DATASUS's own CBO-1994 -> CBO-2002 conversion of CNES professionals.

Portaria SAS 370/2007 moved SCNES to CBO 2002 from competence August 2007 and
charged DATASUS with converting the registered records (§2). No table of that
conversion was published, and the Ministry of Labour's own CBO-94 -> CBO-2002
conversion does not carry the SUS extensions CNES used (06105 MEDICOS EM GERAL,
06164 MEDICO PLANTONISTA, 57282 AGENTE COMUNITARIO: 54% of AC's 2006 rows).

The conversion can be observed: the same professional at the same establishment
appears in July 2007 under the old code and in August 2007 under the new one.
Pairs are formed on (establishment, professional) where each month has exactly
one occupation; the professional's identifier is used only to form the pair and
never leaves this script. The output is code -> code counts.

    PEGASUS_DATA_HOME=~/pegasus_fresh python scripts/measure_cbo_conversion.py AC PE BA RJ MG
"""

from __future__ import annotations

import json
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import pegasus_data as p

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "probes" / "cbo_conversion_observed.json"
ID_FIELDS = ("CNS_PROF", "CPF_PROF", "CPFUNICO")


def month(ufs: list[str], period: str) -> dict[tuple[str, str], set[str]]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        table = p.query("CNES-PF", period=period, geography=ufs, present="codes", allow_partial=True)
    ident = next(f for f in ID_FIELDS if f in table.column_names)
    out: dict[tuple[str, str], set[str]] = defaultdict(set)
    for cnes, person, cbo in zip(
        table.column("CNES").to_pylist(), table.column(ident).to_pylist(), table.column("CBO").to_pylist(), strict=True
    ):
        if cnes and person and cbo:
            out[(str(cnes), str(person))].add(str(cbo).strip())
    return out


def main() -> int:
    ufs = sys.argv[1:] or ["AC", "PE", "BA", "RJ", "MG"]
    before, after = month(ufs, "2007-07"), month(ufs, "2007-08")
    pairs: dict[str, Counter] = defaultdict(Counter)
    for key, old in before.items():
        new = after.get(key)
        if len(old) == 1 and new and len(new) == 1:
            o, n = next(iter(old)), next(iter(new))
            if len(o) == 5 and len(n) == 6:
                pairs[o][n] += 1
    result = {
        old: {"total": sum(c.values()), "top": c.most_common(1)[0][0], "share": round(c.most_common(1)[0][1] / sum(c.values()), 4),
              "targets": dict(c.most_common(5))}
        for old, c in sorted(pairs.items())
    }
    OUT.write_text(json.dumps({"states": ufs, "pairs": sum(r["total"] for r in result.values()), "codes": result},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    shares = [r["share"] for r in result.values()]
    print(f"{len(result)} old codes, {sum(r['total'] for r in result.values())} pairs; "
          f"share >= 0.95: {sum(1 for s in shares if s >= 0.95)}, >= 0.8: {sum(1 for s in shares if s >= 0.8)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
