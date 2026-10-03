"""Scope invariance test (docs/plans/linkage-theory.md §3.2, step T2).

Usage: python scripts/link_scope_test.py SPEC PERIOD UF [UF ...] [--reuse-national]

Links SPEC nationally (left and right BR), then each UF's left records against
the national right side, and compares each slice's pairs with the national
run's pairs whose left record is in that slice. Invariance holds when they are
the same. Writes data/probes/linkage/scope_test_<spec>_<period>.json.
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import duckdb
import pyarrow as pa

from pegasus_data import link

OUT = Path(__file__).resolve().parents[1] / "data" / "probes" / "linkage"


def main(spec: str, period: str, ufs: list[str]) -> None:
    warnings.simplefilter("ignore")
    t0 = time.time()
    reuse = "--reuse-national" in ufs
    ufs = [u for u in ufs if u != "--reuse-national"]
    national = link(spec, period=period, geography="BR", method="probabilistic", refresh=not reuse,
                    allow_partial=True, allow_not_viable=True)
    out = {"national": {"seconds": round(time.time() - t0, 1), **{k: v for k, v in national.summary().items()
                                                                     if k != "models"}}}
    print("national", json.dumps({k: out["national"][k] for k in ("seconds", "pairs", "fdr_upper95_percent")}),
          flush=True)
    con = duckdb.connect()
    con.register("nat", national.pairs.select(["l", "r"]))
    out["national"]["reused"] = reuse
    for uf in ufs:
        t0 = time.time()
        sl = link(spec, period=period, geography=uf, right_geography="BR", method="probabilistic", refresh=True,
                  persist=False, allow_partial=True, allow_not_viable=True)
        secs = round(time.time() - t0, 1)
        con.register("sl", sl.pairs.select(["l", "r"]))
        # The national pairs whose left record the slice saw.
        from pegasus_data.linkage.engine import load_links
        from pegasus_data.linkage.identity import record_ids
        from pegasus_data.linkage.roles import role_table

        seen = role_table(load_links()[spec].left.dataset, period=period, geography=uf, roles=[],
                          allow_partial=True)
        con.register("seen", pa.table({"id": record_ids(seen)}))
        con.execute("CREATE OR REPLACE TEMP TABLE ids AS SELECT id FROM seen")
        nat_n = con.execute("SELECT count(*) FROM nat WHERE l IN (SELECT id FROM ids)").fetchone()[0]
        same = con.execute("SELECT count(*) FROM sl JOIN nat USING (l, r)").fetchone()[0]
        only_slice = con.execute("SELECT count(*) FROM sl ANTI JOIN nat USING (l, r)").fetchone()[0]
        only_nat = con.execute("""SELECT count(*) FROM nat WHERE l IN (SELECT id FROM ids)
                                  AND (l, r) NOT IN (SELECT (l, r) FROM sl)""").fetchone()[0]
        res = {"seconds": secs, "slice_pairs": sl.pairs.num_rows, "national_pairs_in_slice": nat_n,
               "identical": same, "only_slice": only_slice, "only_national": only_nat,
               "slice_fdr_upper95": sl.summary().get("fdr_upper95_percent")}
        out[uf] = res
        print(uf, json.dumps(res), flush=True)
    (OUT / f"scope_test_{spec}_{period}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
