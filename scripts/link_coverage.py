"""Does the chance that a record has a partner depend on the record's own fields?

Usage: python scripts/link_coverage.py PERIOD GEO [SPEC ...]

For every stored probabilistic link of the scope, each left record's
low-cardinality fields (categories, sex, codes with at most 40 values, and the
state of every municipality) are cross-tabulated against whether the record
was linked and its p_match. The expected true-partner share of a stratum is
sum(p_match) / records. A coverage prior (linkage-theory §3.1) is worth
building only where that share differs between strata far beyond its noise.

Run under the data home that holds the links. Writes
data/probes/linkage/coverage_<geo>_<period>.json.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import duckdb

from pegasus_data import link
from pegasus_data.linkage.engine import _prepare, _roles_needed, load_links
from pegasus_data.linkage.probabilistic import load_probabilistic
from pegasus_data.linkage.roles import dataset_roles, role_table

OUT = Path(__file__).resolve().parents[1] / "data" / "probes" / "linkage"
MAX_VALUES = 40
MIN_STRATUM = 200


def main(period: str, geo: str, specs: list[str]) -> None:
    warnings.simplefilter("ignore")
    out: dict = {}
    for name in specs or list(load_links()):
        spec, prob = load_links()[name], load_probabilistic(name)
        declared = dataset_roles(spec.left.dataset).roles
        inherited = {i.as_ for i in prob.inherit}
        compared = {r for c in prob.compare for r in c.side_roles("left")} - inherited
        candidates = [r for r, d in declared.items() if d.type in ("label", "sex", "code", "municipality")
                      and not r.endswith(".race")]   # race is held out of linking and of its priors
        roles = sorted(set(_roles_needed(spec, "left")) | compared | set(candidates))
        table = role_table(spec.left.dataset, period=period, geography=geo, roles=roles,
                           allow_partial=True, max_download=10**8)
        result = link(name, period=period, geography=geo, method="probabilistic", allow_not_viable=True,
                      allow_partial=True)
        con = duckdb.connect()
        n_left = _prepare(con, "L", table, spec.left)
        con.register("P", result.pairs)
        con.execute("CREATE TEMP TABLE J AS SELECT L.*, P.p_match FROM L LEFT JOIN P ON L._id = P.l")
        overall = con.execute("SELECT count(*), count(p_match), sum(p_match) FROM J").fetchone()
        report: dict = {"left_records": n_left, "linked": overall[1],
                        "expected_true_share": round((overall[2] or 0) / overall[0], 4), "fields": {}}
        for r in candidates:
            if r not in table.column_names:
                continue
            expr = f'substr(CAST("{r}" AS VARCHAR), 1, 2)' if declared[r].type == "municipality" else f'"{r}"'
            if con.execute(f"SELECT count(DISTINCT {expr}) FROM J").fetchone()[0] > MAX_VALUES:
                continue
            rows = con.execute(f"""SELECT CAST({expr} AS VARCHAR) v, count(*) AS n, count(p_match) AS linked,
                    round(sum(coalesce(p_match, 0)) / count(*), 4) AS true_share
                FROM J GROUP BY 1 ORDER BY n DESC""").fetchall()
            big = [x for x in rows if x[1] >= MIN_STRATUM]
            shares = [x[3] for x in big]
            report["fields"][r + (" (state)" if declared[r].type == "municipality" else "")] = {
                "spread": round(max(shares) - min(shares), 4) if shares else None,
                "strata": [list(x) for x in rows],
            }
        out[name] = report
        top = sorted(((k, v["spread"]) for k, v in report["fields"].items() if v["spread"] is not None),
                     key=lambda kv: -kv[1])[:5]
        print(name, json.dumps({"left": n_left, "share": report["expected_true_share"], "widest": top}), flush=True)
    (OUT / f"coverage_{geo}_{period}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str),
                                                       encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
