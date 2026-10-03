"""Why did a pair stored by one run not survive another? Each pair's fate under the current model.

Usage: python scripts/link_pair_fate.py SPEC PERIOD GEO PAIRS.parquet

PAIRS.parquet holds (l, r) record ids, for example pairs a previous run kept
and the current one did not. The current spec is run once (not stored) with
its scoring recorded, and every given pair is classified:
- not a candidate (no block put the two records together);
- scored at or below zero (dropped while streaming);
- below the threshold;
- not the left record's clear best, or not the right record's (with the
  runner-up's margin);
- kept.

Writes data/probes/linkage/pair_fate_<spec>_<geo>_<period>.json.
"""

from __future__ import annotations

import json
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

import pegasus_data.linkage.probabilistic as P
from pegasus_data import link

OUT = Path(__file__).resolve().parents[1] / "data" / "probes" / "linkage"


def main(spec: str, period: str, geo: str, pairs_path: str) -> None:
    warnings.simplefilter("ignore")
    wanted = pq.read_table(pairs_path).select(["l", "r"])
    seen: dict = {}
    original_one_to_one, original_materialise = P._one_to_one, P._materialise

    def materialise(con, name):
        ids = original_materialise(con, name)
        seen[name] = ids
        return ids

    def one_to_one(ls, rs, scores, threshold):
        if threshold != float("-inf") and "real" not in seen:
            seen["real"] = (np.asarray(ls), np.asarray(rs), np.asarray(scores), threshold)
        return original_one_to_one(ls, rs, scores, threshold)

    P._materialise, P._one_to_one = materialise, one_to_one
    try:
        result = link(spec, period=period, geography=geo, method="probabilistic", refresh=True, persist=False,
                      allow_partial=True, allow_not_viable=True)
    finally:
        P._materialise, P._one_to_one = original_materialise, original_one_to_one
    ls, rs, scores, t = seen["real"]
    lid = {v: i for i, v in enumerate(seen["L"].to_pylist())}
    rid = {v: i for i, v in enumerate(seen["R"].to_pylist())}
    order = np.argsort(-scores, kind="stable")
    rank = np.empty(len(scores), np.int64)
    rank[order] = np.arange(len(scores))
    by_pair = {(int(a), int(b)): k for k, (a, b) in enumerate(zip(ls, rs, strict=True))}

    def best_two(key):
        """Per record id, its two highest-ranked candidates (indices)."""
        best: dict = {}
        for k in order:
            got = best.setdefault(int(key[k]), [])
            if len(got) < 2:
                got.append(k)
        return best

    bl, br = best_two(ls), best_two(rs)
    kept = set(zip(result.pairs.column("l").to_pylist(), result.pairs.column("r").to_pylist(), strict=True))
    fates: Counter = Counter()
    examples: list = []
    margins: list = []
    for l_, r_ in zip(wanted.column("l").to_pylist(), wanted.column("r").to_pylist(), strict=True):
        if (l_, r_) in kept:
            fates["kept"] += 1
            continue
        a, b = lid.get(l_), rid.get(r_)
        k = by_pair.get((a, b)) if a is not None and b is not None else None
        if a is None or b is None:
            fates["record not on its side"] += 1
        elif k is None:
            fates["not a candidate, or scored at or below zero"] += 1
        elif scores[k] < t:
            fates["below the threshold"] += 1
            margins.append(float(scores[k] - t))
        elif bl[a][0] != k:
            fates["left record has a better candidate"] += 1
        elif br[b][0] != k:
            fates["right record has a better candidate"] += 1
        elif len(bl[a]) > 1 and scores[k] - scores[bl[a][1]] < P.AMBIGUITY_MARGIN_BITS:
            fates["left runner-up within the margin"] += 1
            if len(examples) < 40:
                k2 = bl[a][1]
                examples.append({"l": l_, "r": r_, "bits": round(float(scores[k]), 2),
                                 "runner_up_r": seen["R"][int(rs[k2])].as_py(), "runner_up_bits": round(float(scores[k2]), 2)})
        elif len(br[b]) > 1 and scores[k] - scores[br[b][1]] < P.AMBIGUITY_MARGIN_BITS:
            fates["right runner-up within the margin"] += 1
        else:
            fates["unexplained"] += 1
    out = {"spec": spec, "scope": f"{geo} {period}", "pairs": wanted.num_rows, "threshold": t,
           "fates": dict(fates.most_common()),
           "below_threshold_by": np.percentile(margins, [5, 25, 50, 75, 95]).round(2).tolist() if margins else [],
           "left_margin_examples": examples}
    print(json.dumps(out, indent=1), flush=True)
    (OUT / f"pair_fate_{spec}_{geo}_{period}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:5])
