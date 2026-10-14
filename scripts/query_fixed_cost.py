"""The fixed cost of a query on a built root: the plan, then the same query repeated, read-only.

A query's own work is the scan of the partitions it selects; the rest (resolving the dataset, the plan, the schema
census, the render's lookups) is what this times. Run it against the code under test (`PYTHONPATH`) and read the first
call (cold) apart from the warm ones; the rows are the same on both sides of a change.

    python scripts/query_fixed_cost.py <label> --root <data root> [case ...]
    python scripts/query_fixed_cost.py --list

Nothing is built, fetched or written (`max_download=0`).
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings

CASES = {
    "sim_do_br_codes": ("SIM-DO", {
        "period": 2019, "geography": "BR", "select": ["CAUSABAS", "SEXO", "IDADE", "CODMUNRES"],
        "rows": {"CAUSABAS": ["I21", "I22"]}, "present": "codes"}),
    "sih_rd_ac_codes": ("SIH-RD", {
        "period": 2019, "geography": "AC", "select": ["DIAG_PRINC", "SEXO", "IDADE", "MUNIC_RES"],
        "rows": {"DIAG_PRINC": ["I21", "I22"]}, "present": "codes"}),
    "sih_rd_ac_labelled": ("SIH-RD", {
        "period": 2019, "geography": "AC", "select": ["DIAG_PRINC", "SEXO", "IDADE", "MUNIC_RES"],
        "rows": {"DIAG_PRINC": ["I21", "I22"]}}),
    "sim_do_br_labelled_2y": ("SIM-DO", {
        "period": (2018, 2019), "geography": "BR", "select": ["CAUSABAS", "SEXO"], "rows": {"CAUSABAS": ["I21"]}}),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("label", nargs="?", default="run")
    parser.add_argument("cases", nargs="*")
    parser.add_argument("--root", help="the data root (catalog and lake) to read")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--calls", type=int, default=6)
    args = parser.parse_args()
    if args.list:
        print("\n".join(CASES))
        return 0
    if not args.root:
        parser.error("--root is required")
    warnings.simplefilter("ignore")
    import pegasus_data as pg
    from pegasus_data._query_engine.planner import plan

    for name in args.cases or CASES:
        dataset, kw = CASES[name]
        plan_kw = {k: v for k, v in kw.items() if k in ("period", "geography", "select")}
        plans = []
        for _ in range(5):
            started = time.perf_counter()
            plan(dataset, root=args.root, **plan_kw)
            plans.append(round((time.perf_counter() - started) * 1000))
        queries, rows = [], None
        for _ in range(args.calls):
            started = time.perf_counter()
            try:
                rows = pg.query(dataset, root=args.root, max_download=0, **kw).num_rows
            except Exception as exc:  # noqa: BLE001 - a case that cannot run says why
                rows = f"{type(exc).__name__}: {str(exc)[:60]}"
            queries.append(round((time.perf_counter() - started) * 1000))
        print(f"[{args.label}] {name}: rows={rows} plan ms={plans} query ms={queries}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
