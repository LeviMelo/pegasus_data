"""Do the contested health regions disagree, and which side is current? (OQ-10)

Usage: python scripts/health_region_conflicts.py

The membership pack reports a municipality's health region as contested when
the publishing systems' own CIRBRN tables name different codes. For each one
this reads the claims in ``resources/geography.parquet`` and compares them with
TabNet's current table (``territorio/br_regsaud.cnv``, cached under the data
home's ``registries/tabnet``).
- SINASC's Santa Catarina table writes a region as UF + two digits
  (``4214``), where SIM and TabNet write UF + three (``42014``). A comparison
  is made in that scheme only; the codes themselves are never rewritten.

Writes data/probes/geography/health_region_conflicts.json.
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import duckdb

from pegasus_data.geography import _MEMBER, memberships
from pegasus_data.semantics.cnv_parser import parse_cnv

PACK = "src/pegasus_data/resources/geography.parquet"
TABNET = "pegasus_data_home/registries/tabnet/br_regsaud.cnv"
OUT = Path("data/probes/geography/health_region_conflicts.json")


def _comparable(code: str) -> str:
    return code[:2] + "0" + code[2:] if len(code) == 4 else code


def main() -> None:
    current: dict[str, tuple[str, str]] = {}
    for category in parse_cnv(TABNET).categories:
        if len(category.codes) == 1 and re.fullmatch(r"\d{6}", category.codes[0]):
            parsed = _MEMBER.match(category.label)
            if parsed:
                current[category.codes[0]] = (parsed.group(1), parsed.group(2))
    municipalities = [row[0] for row in duckdb.sql(
        f"SELECT DISTINCT municipality FROM '{PACK}' WHERE classification = 'health_region'").fetchall()]
    contested = [m for m in municipalities if "health_region" in memberships(m).conflicts]
    claims: dict[str, dict[str, tuple[str, str]]] = collections.defaultdict(dict)
    if contested:
        listed = ",".join(f"'{m}'" for m in contested)
        for municipality, system, code, label in duckdb.sql(
            f"SELECT municipality, system, member_code, member_label FROM '{PACK}' "
            f"WHERE classification = 'health_region' AND municipality IN ({listed})").fetchall():
            claims[municipality][system] = (code, label)
    verdicts = collections.Counter()
    rows = []
    for municipality, by_system in sorted(claims.items()):
        tabnet = current.get(municipality)
        comparable = {system: _comparable(code) for system, (code, _) in by_system.items()}
        if len(set(comparable.values())) == 1:
            verdict = "same region, two code schemes"
        else:
            agree = sorted(s for s, c in comparable.items() if tabnet and c == tabnet[0])
            verdict = f"TabNet = {'+'.join(agree)}" if agree else "TabNet names neither"
        verdicts[verdict] += 1
        rows.append({"municipality": municipality, "claims": by_system, "tabnet": tabnet, "verdict": verdict})
    result = {"contested": len(contested), "verdicts": dict(verdicts),
              "by_uf": dict(collections.Counter(m[:2] for m in claims)), "rows": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
