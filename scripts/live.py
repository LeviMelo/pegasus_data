"""Live scenarios: pegasus_data used the way a person uses it, against the real
FTP server, on a fresh data home (CLAUDE.md §5).

Each scenario runs in its own subprocess with a timeout, from a working
directory outside the repository (so the repo's own `pegasus_data_home/` is
never adopted), and writes one JSON record to
`data/probes/live/<run>/<scenario>.json`: seconds, rows, columns, how many of
the coded columns came back labelled and how much of each, the warnings a
user saw, and the error if there was one. A run's summary is
`data/probes/live/<run>/summary.json`.

    python scripts/live.py --list
    python scripts/live.py sih_rd sim_do          # named scenarios
    python scripts/live.py --all [--fresh]        # every scenario; --fresh empties the home first
    python scripts/live.py --show <run>           # print a past run's summary

The unit that binds is the user's: did the call work, how long did it take,
and does the table carry its meaning. Label coverage is measured per column as
the share of non-empty raw values whose `_label` is non-null.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROBES = ROOT / "data" / "probes" / "live"
DEFAULT_HOME = Path(os.environ.get("PEGASUS_LIVE_HOME", Path.home() / "pegasus_live" / "home"))
TIMEOUT = int(os.environ.get("PEGASUS_LIVE_TIMEOUT", "1800"))


# ----------------------------------------------------------------- measuring


def table_metrics(table: Any) -> dict[str, Any]:
    """What a person would check first: shape, and whether codes carry labels."""
    import pyarrow as pa

    if not isinstance(table, pa.Table):
        try:
            table = pa.Table.from_pandas(table, preserve_index=False)
        except Exception:  # noqa: BLE001 - measurement must not fail the scenario
            return {"type": type(table).__name__}
    names = table.column_names
    coverage: dict[str, float] = {}
    for name in names:
        if not name.endswith("_label"):
            continue
        base = name[: -len("_label")]
        if base not in names:
            continue
        raw = table.column(base).to_pylist()
        lab = table.column(name).to_pylist()
        present = [(r, lb) for r, lb in zip(raw, lab, strict=False) if r is not None and str(r).strip()]
        if present:
            coverage[base] = round(sum(1 for _, lb in present if lb is not None) / len(present), 4)
    return {
        "type": type(table).__name__,
        "rows": table.num_rows,
        "columns": len(names),
        "labelled_columns": len(coverage),
        "label_coverage": coverage,
        "sample": dict(table.slice(0, 1).to_pylist()[0]) if table.num_rows else {},
    }


def summarise_warnings(caught: list[warnings.WarningMessage]) -> dict[str, Any]:
    kinds = Counter(w.category.__name__ for w in caught)
    return {"count": len(caught), "by_category": dict(kinds), "first": [str(w.message)[:240] for w in caught[:8]]}


# ----------------------------------------------------------------- scenarios
#
# Each returns a dict of what it observed. Raise to record a failure.


def s_metadata() -> dict[str, Any]:
    """The README's first five minutes: what exists, what is this, did you mean."""
    from pegasus_data import explore, info, search

    out: dict[str, Any] = {}
    for label, call in [
        ("info()", lambda: info()),
        ("info(SIH.RD)", lambda: info("SIH.RD")),
        ("info(dengue)", lambda: info("dengue")),
        ("explore()", lambda: explore()),
        ("explore(SIH.RD)", lambda: explore("SIH.RD")),
        ("search(diabetes)", lambda: search("diabetes")),
    ]:
        t = time.perf_counter()
        try:
            text = str(call())
            out[label] = {"ok": True, "seconds": round(time.perf_counter() - t, 2), "head": text[:400]}
        except Exception as exc:  # noqa: BLE001
            out[label] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]}
    out["failed"] = [k for k, v in out.items() if isinstance(v, dict) and not v.get("ok")]
    return out


def _query(dataset: str, **kwargs: Any) -> dict[str, Any]:
    from pegasus_data import query

    table, report = query(dataset, return_report=True, **kwargs)
    out = table_metrics(table)
    out["report_warnings"] = len(getattr(report, "warnings", []) or [])
    out["report"] = str(report)[:1500]
    return out


def s_sih_rd() -> dict[str, Any]:
    return _query("SIH-RD", period="2023-01", geography="AL")


def s_sim_do() -> dict[str, Any]:
    return _query("SIM-DO", period=2022, geography="AL")


def s_sinasc() -> dict[str, Any]:
    return _query("SINASC-DN", period=2022, geography="AL")


def s_cnes_st() -> dict[str, Any]:
    return _query("CNES-ST", period="2023-01", geography="AL")


def s_sia_pa() -> dict[str, Any]:
    return _query("SIA-PA", period="2023-01", geography="AC")


def s_sinan_deng() -> dict[str, Any]:
    return _query("SINAN-DENG", period=2022)


def s_sinan_tube() -> dict[str, Any]:
    return _query("SINAN-TUBE", period=2022)


def s_fetch_sih() -> dict[str, Any]:
    """The direct, source-shaped door the README also documents."""
    from pegasus_data.retrieve import fetch  # the internal source engine (ADR-0073)

    table, report = fetch("SIH-RD", uf="AL", years=2023, months=1, report=True)
    out = table_metrics(table)
    out["render_warnings"] = len(getattr(getattr(report, "render", None), "warnings", []) or [])
    return out


def s_cli_query() -> dict[str, Any]:
    """The command line a person would type from the README (ADR-0073)."""
    cmd = [sys.executable, "-m", "pegasus_data.cli", "query", "SIH.RD", "--period", "2023-01", "--geo", "AL",
           "--out", "cli_sih.csv", "--dictionary", "cli_sih_dictionary.md"]
    t = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    out: dict[str, Any] = {"returncode": proc.returncode, "seconds": round(time.perf_counter() - t, 2),
                           "stdout": proc.stdout[-1500:], "stderr": proc.stderr[-1500:]}
    csv = Path("cli_sih.csv")
    if csv.exists():
        out["csv_bytes"] = csv.stat().st_size
        out["csv_head"] = csv.read_text(encoding="utf-8", errors="replace")[:600]
    book = Path("cli_sih_dictionary.md")
    if book.exists():
        out["dictionary_head"] = book.read_text(encoding="utf-8", errors="replace")[:800]
    if proc.returncode != 0:
        raise RuntimeError(f"exit {proc.returncode}: {proc.stderr[-400:]}")
    return out


def s_sih_2016() -> dict[str, Any]:
    """SIH-RD 2016 is published twice (MHJ_14_16/ and 200801_/Dados/): the newest edition must be read."""
    from pegasus_data import query

    table, report = query("SIH-RD", period="2016-05", geography="AC", return_report=True)
    out = table_metrics(table)
    source = report.source_report
    out["read"] = list(getattr(source, "source_facts", {}) or {})
    out["superseded"] = list(getattr(source, "representations_deduplicated", []) or [])
    return out


def s_sia_sp_parts() -> dict[str, Any]:
    """SIA-PA São Paulo is split into parts (PASP2301a/b/c): every part must be selected."""
    from pegasus_data import explore

    files = explore("SIA-PA", year=2023, uf="SP")
    names = sorted(str(r["path"]).rsplit("/", 1)[-1] for r in files.rows)
    january = [n for n in names if n.upper().startswith("PASP2301")]
    if len(january) < 2:
        raise AssertionError(f"expected the split parts of PASP2301, found {january}")
    return {"files_2023": len(names), "january_parts": january}


def s_age() -> dict[str, Any]:
    """IDADE_anos in fractional years, per system: distribution and infant precision (ADR-0070)."""
    import pyarrow.compute as pc

    from pegasus_data import query

    out: dict[str, Any] = {}
    for dataset, period, geo in (("SIH-RD", "2023-01", "AL"), ("SIM-DO", 2022, "AL"), ("SINAN-TUBE", 2022, None)):
        table = query(dataset, period=period, geography=geo)
        years = table.column("IDADE_anos")
        valid = pc.drop_null(years)
        infants = pc.filter(valid, pc.less(valid, 1.0))
        out[dataset] = {
            "rows": table.num_rows,
            "null": table.num_rows - len(valid),
            "min": pc.min(valid).as_py(), "median": float(pc.approximate_median(valid).as_py()),
            "max": pc.max(valid).as_py(),
            "under_1": len(infants),
            "under_1_distinct": len(pc.unique(infants)),
        }
    return out


def s_sweep() -> dict[str, Any]:
    """Every declared dataset, queried for its cheapest publication: does it return labelled rows?"""
    from pegasus_data import PublishedEmpty, explore, plan, query
    from pegasus_data.ontology import Ontology

    only = [x.strip().upper() for x in os.environ.get("PEGASUS_SWEEP", "").split(",") if x.strip()]
    # A hard download budget (user, 2026-09-28: never tens of gigabytes again).
    # Per file, and for the whole sweep; a dataset whose cheapest publication is
    # over the per-file cap is recorded as skipped, not fetched.
    per_file_mb = float(os.environ.get("PEGASUS_SWEEP_MAX_MB", "25"))
    budget_mb = float(os.environ.get("PEGASUS_SWEEP_BUDGET_MB", "800"))
    spent_mb = 0.0
    results: dict[str, Any] = {}
    datasets = Ontology.load().datasets
    for code in sorted(datasets):
        if only and code not in only:
            continue
        if datasets[code].status in ("tooling", "retired"):
            # Software and retired nodes are not data (TABDOS.APP is the DOS tabulator).
            continue
        entry: dict[str, Any] = {}
        t = time.perf_counter()
        try:
            rows = list(explore(code, role="data").rows)
            # explore(dataset) gives coverage by year; pick the year, then the cheapest file of it.
            years = sorted({int(r["year"]) for r in rows if r.get("year")})
            if not years:
                entry["skip"] = "no dated files"
                results[code] = entry
                continue
            year = years[-1]
            files = explore(code, year=year).rows
            cheapest = min(files, key=lambda r: float(r.get("megabytes") or 0))
            entry["file"] = cheapest["path"]
            entry["megabytes"] = cheapest.get("megabytes")
            size_mb = float(cheapest.get("megabytes") or 0)
            if size_mb > per_file_mb:
                entry["skip"] = f"cheapest file is {size_mb:.0f} MB, over the {per_file_mb:.0f} MB cap"
                results[code] = entry
                continue
            if spent_mb + size_mb > budget_mb:
                entry["skip"] = f"sweep budget of {budget_mb:.0f} MB reached"
                results[code] = entry
                continue
            month = int(cheapest.get("yyyymm") or 0) % 100
            period = f"{year}-{month:02d}" if month else str(year)
            uf = cheapest.get("uf")
            geography = uf if uf and uf != "BR" else None
            # The cap is enforced on what the QUERY would move, not on the file
            # picked: SIA-PA's cheapest 2026 file was PAPR2604b (0.5 MB), and
            # its month also read PAPR2604a (158 MB) (live, 2026-09-28).
            planned = plan(code, period=period, geography=geography).retrieval
            new_mb = ((planned.download_bytes or 0) - (planned.cached_bytes or 0)) / 2**20
            entry["download_mb"] = round(new_mb, 1)
            if new_mb > per_file_mb or spent_mb + new_mb > budget_mb:
                entry["skip"] = f"query would download {new_mb:.0f} MB (cap {per_file_mb:.0f}, spent {spent_mb:.0f})"
                results[code] = entry
                continue
            spent_mb += new_mb
            table = query(code, period=period, geography=geography,
                          max_download=int((per_file_mb + 1) * 2**20))
            labelled = [c for c in table.column_names if c.endswith("_label")]
            entry.update(ok=True, period=period, uf=uf, rows=table.num_rows, columns=table.num_columns,
                         labelled=len(labelled))
        except PublishedEmpty as exc:
            entry.update(ok=True, empty=True, rows=0, note=str(exc)[:200])
        except Exception as exc:  # noqa: BLE001 - the sweep records every failure
            entry.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:400])
        entry["seconds"] = round(time.perf_counter() - t, 1)
        results[code] = entry
        print(f"  {code:28s} {'ok ' if entry.get('ok') else ('skip' if 'skip' in entry else 'FAIL')} "
              f"{entry.get('rows')} rows {entry.get('labelled')} labelled {entry.get('seconds')}s "
              f"{entry.get('error') or entry.get('skip') or ''}"[:220], flush=True)
    ok = sum(1 for v in results.values() if v.get("ok"))
    failed = {k: v["error"] for k, v in results.items() if v.get("ok") is False}
    skipped = {k: v["skip"] for k, v in results.items() if "skip" in v}
    return {"downloaded_mb_at_most": round(spent_mb, 1), "datasets": len(results), "ok": ok, "failed": len(failed), "skipped": len(skipped),
            "failures": failed, "skips": skipped, "results": results}


SCENARIOS = {
    "metadata": s_metadata,
    "sih_rd": s_sih_rd,
    "fetch_sih": s_fetch_sih,
    "sim_do": s_sim_do,
    "sinasc": s_sinasc,
    "cnes_st": s_cnes_st,
    "sia_pa": s_sia_pa,
    "sinan_deng": s_sinan_deng,
    "sinan_tube": s_sinan_tube,
    "cli_query": s_cli_query,
    "sih_2016": s_sih_2016,
    "sia_sp_parts": s_sia_sp_parts,
    "age": s_age,
    "sweep": s_sweep,
}


# ----------------------------------------------------------------- running


def run_one(name: str, out_dir: Path) -> None:
    """Child process: run one scenario and write its record."""
    record: dict[str, Any] = {"scenario": name, "doc": (SCENARIOS[name].__doc__ or "").strip()}
    t = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            record["result"] = SCENARIOS[name]()
            record["ok"] = True
        except Exception as exc:  # noqa: BLE001
            record["ok"] = False
            record["error"] = f"{type(exc).__name__}: {exc}"[:2000]
            record["traceback"] = traceback.format_exc()[-4000:]
    record["seconds"] = round(time.perf_counter() - t, 2)
    record["warnings"] = summarise_warnings(caught)
    (out_dir / f"{name}.json").write_text(json.dumps(record, indent=2, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True).stdout.strip() + (
            "+dirty" if subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "src"],
                                       capture_output=True, text=True).stdout.strip() else "")
    except OSError:
        return "?"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="empty the live data home first")
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    parser.add_argument("--run", help="run id (default: timestamp)")
    parser.add_argument("--show")
    parser.add_argument("--one", help=argparse.SUPPRESS)
    parser.add_argument("--out", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.one:
        run_one(args.one, args.out)
        return 0
    if args.list:
        for name, fn in SCENARIOS.items():
            print(f"{name:12s} {(fn.__doc__ or '').strip().splitlines()[0] if fn.__doc__ else ''}")
        return 0
    if args.show:
        print((PROBES / args.show / "summary.json").read_text(encoding="utf-8"))
        return 0

    names = list(SCENARIOS) if args.all else args.names
    unknown = [n for n in names if n not in SCENARIOS]
    if not names or unknown:
        parser.error(f"name scenarios or --all; unknown: {unknown}; known: {list(SCENARIOS)}")
    if args.fresh and args.home.exists():
        shutil.rmtree(args.home)
    args.home.mkdir(parents=True, exist_ok=True)
    run_id = args.run or time.strftime("%Y%m%d-%H%M%S")
    out_dir = PROBES / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir = args.home.parent  # outside the repository: nothing adopts the repo's home
    env = {**os.environ, "PEGASUS_DATA_HOME": str(args.home), "PYTHONUTF8": "1",
           "PYTHONPATH": str(ROOT / "src")}

    summary: dict[str, Any] = {"run": run_id, "commit": git_head(), "home": str(args.home),
                               "started": time.strftime("%Y-%m-%d %H:%M:%S"), "scenarios": {}}
    for name in names:
        t = time.perf_counter()
        try:
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--one", name, "--out", str(out_dir)],
                           cwd=workdir, env=env, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            (out_dir / f"{name}.json").write_text(json.dumps({"scenario": name, "ok": False,
                                                              "error": f"timeout after {TIMEOUT}s"}), encoding="utf-8")
        path = out_dir / f"{name}.json"
        rec = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"ok": False, "error": "no record"}
        res = rec.get("result") or {}
        line = {
            "ok": rec.get("ok"),
            "seconds": round(time.perf_counter() - t, 1),
            "rows": res.get("rows"),
            "labelled": res.get("labelled_columns"),
            "warnings": (rec.get("warnings") or {}).get("count"),
            "error": rec.get("error"),
        }
        summary["scenarios"][name] = line
        print(f"{name:12s} {'ok  ' if line['ok'] else 'FAIL'} {line['seconds']:>7}s rows={line['rows']} "
              f"labelled={line['labelled']} warnings={line['warnings']} {line['error'] or ''}"[:300], flush=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nrecords: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
