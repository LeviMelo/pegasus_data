"""Which columns are the same variable under another name? (OQ-57)

Usage: python scripts/column_renames.py [--root HOME] [--only SYSTEM[.SERIES] ...]
                                        [--max-pairs N] [--max-mb 60] [--rows 200000]
       (data home from --root, else PEGASUS_ROOT; use a FRESH home, not the
       repo's. The schema census must already be in its catalog: run
       pegasus_data.info("SIM.DO", root=HOME) once on a fresh home.)

A dataset (system, series) may have several file layouts (schema signatures in
the census: tables families / schemas / schema_presence). A field present in
one layout and absent in the other may have been renamed. Column position pairs
fields mostly wrongly, and file-level complementary presence pairs every field
unique to one layout with every field unique to the other, so presence alone
cannot choose. This script asks the VALUES.

For every pair of layouts of one dataset that overlap in time, are within a
year of each other, or are consecutive in time order, it takes the fields only
in the older layout (A-set) and only in the newer one (B-set). It fetches one
small file per layout (the same UF in both when it can, the file whose year is
closest to the boundary, smallest first, at most --max-mb), reads up to --rows
records, and for every (a, b) candidate computes:

  tv_sim      1 - total-variation distance between the two value-frequency
              distributions (the main score, 0..1)
  jaccard     of the distinct value sets
  b_in_a      share of b's non-null rows whose value occurs among a's values
  a_in_b      the converse
  pattern     kind (digits / alpha / mixed / date-like) and modal length of each
  null rates  of each (a tail beyond 20,000 distinct values counts as non-overlapping)
  name_sim    difflib ratio of the names (supporting only, not in the score)

Each candidate carries its runner-up: the best rival score of the same a (over
the other B-set fields) and of the same b (over the other A-set fields). A pair
is "strong" only when tv_sim >= 0.8, jaccard >= 0.5, both columns are
informative (>= 2 distinct values, >= 50 non-null rows, patterns compatible),
it is the mutual best match, and it beats both rivals by >= 0.15. A pair is
"weak" when tv_sim >= 0.5 and it is the mutual best but fails a strong
condition; "ambiguous" when a rival is within 0.15 (name_concordant flags name_sim >= 0.7, reported beside the
verdict, never part of it). Fields with no candidate
reaching 0.5 are reported as "disappeared"/"appeared" (no counterpart: not a
rename). Boundaries where only one side has unique fields are pure drops or
additions and need no sampling.

Writes data/probes/schema/column_renames.json (every candidate with its numbers
and runner-up, the per-boundary files read, and the boundaries skipped with the
reason). Sample profiles are cached under <home>/column_renames_cache.json so a
rerun does not refetch.
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

PREFERRED_UFS = ["AC", "RR", "AP", "SE", "RO", "TO", "AL", "PI", "RN", "PB", "MS", "DF"]
STRONG_TV, STRONG_JACC, STRONG_GAP, WEAK_TV = 0.8, 0.5, 0.15, 0.5
MIN_ROWS, MIN_DISTINCT = 50, 2
CAP = 20000  # distinct values kept per column; beyond it the tail is counted as non-overlapping
OUT = Path("data/probes/schema/column_renames.json")


def _kind(values: Counter) -> tuple[str, int]:
    """Dominant shape of a column's values and its modal length."""
    shapes: Counter = Counter()
    lens: Counter = Counter()
    for v, n in values.items():
        if re.fullmatch(r"\d+", v):
            s = "date8" if len(v) == 8 and v[4:6] in {f"{m:02d}" for m in range(1, 13)} else "digits"
        elif re.fullmatch(r"[A-Za-z ]+", v):
            s = "alpha"
        else:
            s = "mixed"
        shapes[s] += n
        lens[len(v)] += n
    return shapes.most_common(1)[0][0], lens.most_common(1)[0][0]


def _norm(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v):
            return None
        v = int(v) if v.is_integer() else v
    s = str(v).strip()
    return s or None


def profile_columns(rows_by_col: dict[str, list]) -> dict[str, dict]:
    out = {}
    for col, vals in rows_by_col.items():
        norm = [_norm(v) for v in vals]
        counts = Counter(x for x in norm if x is not None)
        n = len(norm)
        nn = sum(counts.values())
        entry = {"rows": n, "non_null": nn, "null_rate": round(1 - nn / n, 4) if n else None,
                 "distinct": len(counts)}
        if counts:
            entry["kind"], entry["modal_len"] = _kind(counts)
            top = counts.most_common(CAP)
            entry["freq"] = dict(top)
            entry["freq_truncated"] = len(counts) > CAP
            entry["examples"] = [k for k, _ in counts.most_common(5)]
        out[col] = entry
    return out


def score(pa: dict, pb: dict) -> dict:
    """Value evidence for 'a and b are the same variable'."""
    ev = {"informative": False}
    if not pa.get("non_null") or not pb.get("non_null"):
        ev["reason"] = "a column is entirely null in its sample"
        return ev
    fa, fb = pa["freq"], pb["freq"]
    na, nb = pa["non_null"], pb["non_null"]
    keys = set(fa) | set(fb)
    tail_a = 1 - sum(fa.values()) / na
    tail_b = 1 - sum(fb.values()) / nb
    tv = 0.5 * (sum(abs(fa.get(k, 0) / na - fb.get(k, 0) / nb) for k in keys) + tail_a + tail_b)
    sa, sb = set(fa), set(fb)
    jac = len(sa & sb) / len(sa | sb)
    b_in_a = sum(c for k, c in fb.items() if k in sa) / nb
    a_in_b = sum(c for k, c in fa.items() if k in sb) / na
    compat = pa["kind"] == pb["kind"] and abs(pa["modal_len"] - pb["modal_len"]) <= 1
    informative = (pa["distinct"] >= MIN_DISTINCT and pb["distinct"] >= MIN_DISTINCT
                   and na >= MIN_ROWS and nb >= MIN_ROWS)
    ev.update({
        "informative": informative, "tv_sim": round(1 - tv, 4), "jaccard": round(jac, 4),
        "b_in_a": round(b_in_a, 4), "a_in_b": round(a_in_b, 4), "pattern_compatible": compat,
        "a_kind": [pa["kind"], pa["modal_len"]], "b_kind": [pb["kind"], pb["modal_len"]],
        "a_null": pa["null_rate"], "b_null": pb["null_rate"],
        "a_distinct": pa["distinct"], "b_distinct": pb["distinct"],
        "truncated": bool(pa["freq_truncated"] or pb["freq_truncated"]),
        "a_examples": pa["examples"], "b_examples": pb["examples"],
    })
    if not informative:
        ev["reason"] = "constant/near-empty column: matches anything, proves nothing"
    return ev


# ----------------------------------------------------------------------- plan


def load_plan(catalog_path: Path, only: list[str]):
    db = sqlite3.connect(f"file:{catalog_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    fams = [dict(r) for r in db.execute(
        "select family_id, system, series, schema_signature, time_min, time_max, file_count from families")]
    schemas = {r[0]: json.loads(r[1]) for r in db.execute("select schema_signature, fields_json from schemas")}
    by: dict[tuple, list] = defaultdict(list)
    for f in fams:
        if only and f"{f['system']}.{f['series']}" not in only and f["system"] not in only:
            continue
        by[(f["system"], f["series"])].append(f)
    boundaries = []
    for key, fl in sorted(by.items()):
        fl.sort(key=lambda f: (f["time_min"] or 0, f["time_max"] or 0, f["family_id"]))
        for i, a in enumerate(fl):
            for j in range(i + 1, len(fl)):
                b = fl[j]
                near = (b["time_min"] or 0) <= (a["time_max"] or 0) + 1
                if not (near or j == i + 1):
                    continue
                sa, sb = schemas[a["schema_signature"]], schemas[b["schema_signature"]]
                a_only = [c for c in sa if c not in set(sb)]
                b_only = [c for c in sb if c not in set(sa)]
                if not a_only and not b_only:
                    continue
                boundaries.append({"system": key[0], "series": key[1], "a": a, "b": b,
                                   "a_only": a_only, "b_only": b_only})
    return db, boundaries


def pick_files(db, a: dict, b: dict) -> tuple[str, str, str, str] | None:
    """One file per layout: same UF if possible, year nearest the boundary, smallest."""

    def files(fid):
        q = ("select ff.path, fa.geo_code, fa.year, f.size from family_files ff "
             "join file_facts fa on fa.path = ff.path join files f on f.path = ff.path "
             "where ff.family_id = ? and f.size is not null and f.gone_at is null")
        return [tuple(r) for r in db.execute(q, (fid,))]

    fa_, fb_ = files(a["family_id"]), files(b["family_id"])
    if not fa_ or not fb_:
        return None
    ta, tb = a["time_max"] or 0, b["time_min"] or 0
    t = max(a["time_min"] or 0, tb) if tb <= ta + 0 else (ta + tb) / 2
    ufs_a = {g for _, g, _, _ in fa_ if g}
    ufs_b = {g for _, g, _, _ in fb_ if g}
    common = ufs_a & ufs_b
    order = [u for u in PREFERRED_UFS if u in common] + sorted(common - set(PREFERRED_UFS))
    uf = order[0] if order else None

    def best(fl, geo):
        c = [x for x in fl if (geo is None or x[1] == geo)] or fl
        return min(c, key=lambda x: (abs((x[2] or 0) - t), x[3]))

    pa, pb = best(fa_, uf), best(fb_, uf)
    return pa[0], pb[0], pa[1] or "", pb[1] or ""


# --------------------------------------------------------------------- sample


class _NoFtp:
    """The FTP server is down: serve every path from the mirror without dialling it."""

    def retrieve_to_file(self, *args, **kwargs):
        raise ConnectionError("FTP not used")


class Sampler:
    def __init__(self, root: Path, rows: int, max_mb: float, cache_path: Path):
        from pegasus_data.config import load_settings
        from pegasus_data.pipeline import Pipeline

        self.settings = load_settings(root=root)
        self.pipeline = Pipeline(self.settings)
        self.pipeline.fetcher.mirror_first = True
        self.rows = rows
        self.max_bytes = int(max_mb * 1e6)
        self.cache_path = cache_path
        self.cache: dict = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        self.bytes = 0

    def profile(self, path: str, size: int | None = None) -> dict:
        if path in self.cache:
            return self.cache[path]
        from pegasus_data.decode.service import decode_source

        t0 = time.time()
        res = self.pipeline.fetcher._fetch_one(_NoFtp(), path, force=False)
        digest = res.sha256
        if not digest:
            return {"error": f"fetch failed: {res.error}"}
        blob = self.pipeline.blobs.path_for(digest)
        self.bytes += blob.stat().st_size
        outcome = decode_source(blob, logical_path=path, settings=self.settings, row_limit=self.rows)
        tables = [t for t in getattr(outcome, "tables", []) if getattr(t, "role", "data") == "data"] or getattr(outcome, "tables", [])
        if not tables:
            return {"error": "decode produced no table"}
        table = tables[0]
        cols: dict[str, list] = {n: [] for n in table.field_names}
        total = 0
        for batch in table.batches():
            d = batch.to_pydict()
            for n in cols:
                cols[n].extend(d.get(n, []))
            total += batch.num_rows
            if total >= self.rows:
                break
        prof = {"path": path, "rows_read": total, "bytes": blob.stat().st_size,
                "seconds": round(time.time() - t0, 1), "columns": profile_columns(cols)}
        self.cache[path] = prof
        self.cache_path.write_text(json.dumps(self.cache), encoding="utf-8")
        return prof




# ----------------------------------------------------------------------- main


def rank(cands: list[dict]) -> None:
    """Annotate each candidate with its runner-up and a verdict."""
    by_a, by_b = defaultdict(list), defaultdict(list)
    for c in cands:
        s = c.get("tv_sim", -1) if c["informative"] else -1
        c["_s"] = s
        by_a[c["old"]].append(c)
        by_b[c["new"]].append(c)
    for c in cands:
        ra = [x["_s"] for x in by_a[c["old"]] if x is not c]
        rb = [x["_s"] for x in by_b[c["new"]] if x is not c]
        c["runner_up_old"] = max(ra) if ra else None
        c["runner_up_new"] = max(rb) if rb else None
        rivals = [x for x in (c["runner_up_old"], c["runner_up_new"]) if x is not None]
        gap = c["_s"] - max(rivals) if rivals else c["_s"]
        c["margin"] = round(gap, 4)
        mutual = (c["_s"] >= max(x["_s"] for x in by_a[c["old"]])
                  and c["_s"] >= max(x["_s"] for x in by_b[c["new"]]))
        c["mutual_best"] = mutual
        c["name_sim"] = round(difflib.SequenceMatcher(None, c["old"], c["new"]).ratio(), 3)
        c["name_concordant"] = c["name_sim"] >= 0.7
        if not c["informative"]:
            c["verdict"] = "uninformative"
        elif (c["_s"] >= STRONG_TV and c["jaccard"] >= STRONG_JACC and c["pattern_compatible"]
              and mutual and gap >= STRONG_GAP):
            c["verdict"] = "strong"
        elif c["_s"] >= WEAK_TV and mutual and gap < STRONG_GAP:
            c["verdict"] = "ambiguous"
        elif c["_s"] >= WEAK_TV and mutual:
            c["verdict"] = "weak"
        else:
            c["verdict"] = "no_match"
    for c in cands:
        del c["_s"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("PEGASUS_ROOT"))
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--max-pairs", type=int, default=0)
    ap.add_argument("--max-mb", type=float, default=60)
    ap.add_argument("--rows", type=int, default=200000)
    ap.add_argument("--budget-gb", type=float, default=3.0)
    args = ap.parse_args()
    if not args.root:
        sys.exit("give --root (a fresh data home) or set PEGASUS_ROOT")
    root = Path(args.root)

    from pegasus_data.config import load_settings

    cat = load_settings(root=root).catalog_path
    db, boundaries = load_plan(cat, args.only)
    sampler = Sampler(root, args.rows, args.max_mb, root / "column_renames_cache.json")
    result = {"home": str(root), "boundaries": [], "skipped": [], "pure": []}
    done = 0
    for bd in boundaries:
        a, b = bd["a"], bd["b"]
        tag = f"{bd['system']}.{bd['series']} {a['family_id'][-10:]}->{b['family_id'][-10:]}"
        head = {"dataset": f"{bd['system']}.{bd['series']}", "old_family": a["family_id"],
                "new_family": b["family_id"], "old_years": [a["time_min"], a["time_max"]],
                "new_years": [b["time_min"], b["time_max"]], "old_files": a["file_count"],
                "new_files": b["file_count"], "old_only": bd["a_only"], "new_only": bd["b_only"]}
        if not bd["a_only"] or not bd["b_only"]:
            head["kind"] = "pure_drop" if bd["a_only"] else "pure_addition"
            result["pure"].append(head)
            continue
        if args.max_pairs and done >= args.max_pairs:
            result["skipped"].append({**head, "reason": "--max-pairs reached"})
            continue
        pick = pick_files(db, a, b)
        if not pick:
            result["skipped"].append({**head, "reason": "no catalogued file for a layout"})
            continue
        pa, pb, uf_a, uf_b = pick
        print(tag, pa.split("/")[-1], pb.split("/")[-1], flush=True)
        try:
            profa, profb = sampler.profile(pa), sampler.profile(pb)
        except Exception as exc:  # noqa: BLE001 - a failed sample is a recorded skip
            result["skipped"].append({**head, "reason": f"sample failed: {exc!r}"})
            continue
        if "error" in profa or "error" in profb:
            result["skipped"].append({**head, "reason": f"{profa.get('error') or profb.get('error')}",
                                      "files": [pa, pb]})
            continue
        done += 1
        cands = []
        for oa in bd["a_only"]:
            for nb in bd["b_only"]:
                if oa not in profa["columns"] or nb not in profb["columns"]:
                    continue
                cands.append({"old": oa, "new": nb, **score(profa["columns"][oa], profb["columns"][nb])})
        rank(cands)
        matched_old = {c["old"] for c in cands if c["verdict"] in {"strong", "weak", "ambiguous"}}
        matched_new = {c["new"] for c in cands if c["verdict"] in {"strong", "weak", "ambiguous"}}
        head.update({
            "files": {"old": pa, "new": pb}, "uf": [uf_a, uf_b],
            "rows_read": [profa["rows_read"], profb["rows_read"]],
            "disappeared": [c for c in bd["a_only"] if c not in matched_old],
            "appeared": [c for c in bd["b_only"] if c not in matched_new],
            "candidates": cands,
        })
        result["boundaries"].append(head)
        result["downloaded_bytes"] = sampler.pipeline.blobs.size_on_disk()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
        if result["downloaded_bytes"] > args.budget_gb * 1e9:
            result["skipped"].append({"reason": "download budget reached"})
            break
    result["downloaded_bytes"] = sampler.pipeline.blobs.size_on_disk()
    result["counts"] = {
        "boundaries_sampled": len(result["boundaries"]), "skipped": len(result["skipped"]),
        "pure_drop_or_addition": len(result["pure"]),
        "strong": sum(c["verdict"] == "strong" for bd in result["boundaries"] for c in bd["candidates"]),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result["counts"]), "bytes", result["downloaded_bytes"])


if __name__ == "__main__":
    main()
