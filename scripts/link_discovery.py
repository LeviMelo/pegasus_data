"""Measured link discovery over every pair of linkable datasets (linkage/discover.py).

Usage: python scripts/link_discovery.py PERIOD GEO [DATASET ...]

Reads each dataset's comparable roles once (cached under discovery/cache/), measures every key between every
pair, and writes data/probes/linkage/discovery/<left>__<right>_<geo>_<period>.json
(all keys, best first). Run under the data home that holds the data.
"""

from __future__ import annotations

import itertools
import json
import sys
import time
import warnings
from pathlib import Path

import pyarrow.parquet as pq

from pegasus_data.linkage.discover import _comparable, discover_links
from pegasus_data.linkage.roles import role_table

OUT = Path(__file__).resolve().parents[1] / "data" / "probes" / "linkage" / "discovery"
DEFAULT = ["SINASC-DN", "SIM-DO", "SIH-RD", "CIHA"]


def main(period: str, geo: str, datasets: list[str]) -> None:
    warnings.simplefilter("ignore")
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "cache"
    cache.mkdir(exist_ok=True)
    tables = {}
    for ds in datasets:
        t0 = time.time()
        path = cache / f"{ds}_{geo}_{period}.parquet"
        roles = list(_comparable(ds))
        if path.exists() and set(roles) <= set(pq.read_schema(path).names):
            tables[ds] = pq.read_table(path)
        else:
            tables[ds] = role_table(ds, period=period, geography=geo, roles=roles,
                                    allow_partial=True, max_download=10**8).select(roles)
            pq.write_table(tables[ds], path)
        print(f"loaded {ds} {tables[ds].num_rows:,} rows in {time.time() - t0:.0f}s", flush=True)
    for left, right in itertools.combinations(datasets, 2):
        t0 = time.time()
        res = discover_links(left, right, period=period, geography=geo, tables=tables)
        rows = [r.summary() for r in res]
        (OUT / f"{left}__{right}_{geo}_{period}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        best = rows[0]
        share = max(rows, key=lambda r: r["z_right_meets"])
        print(f"{left} ~ {right}: {len(rows)} keys in {time.time() - t0:.0f}s; best {best['key']} "
              f"excess {best['excess_mutual']:,} ({best['excess_share_of_smaller']:.1%} of the smaller side) "
              f"real/placebo {best['real_over_placebo']}; most shared {share['key']} "
              f"right meets {share['real_right_meets']:,} vs placebo {share['placebo_right_meets']:,} (z {share['z_right_meets']})", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or DEFAULT)
