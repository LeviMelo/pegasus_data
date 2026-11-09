"""Live scenarios: pegasus_data used the way a person uses it, against the real
FTP server, on a fresh data home (CLAUDE.md §5).

Each scenario runs in its own subprocess with a timeout, from a working
directory outside the repository, and writes one JSON record to
`data/probes/live/<run>/<scenario>.json`: seconds, rows, columns, how many of
the coded columns came back labelled and how much of each, the warnings a
user saw, and the error if there was one. A run's summary is
`data/probes/live/<run>/summary.json`.

The home is new and empty for each run, then adopted into the one data home and
removed (`adopt --remove`, ADR-0208): what a run downloads is kept once, and no
live home outlives its run. `--home` names a home kept across runs instead.

    python scripts/live.py --list
    python scripts/live.py sih_rd sim_do          # named scenarios
    python scripts/live.py --all                  # every scenario
    python scripts/live.py --home H [--fresh]     # a kept home; --fresh empties it first
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
import tempfile
import time
import traceback
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROBES = ROOT / "data" / "probes" / "live"
#: A home kept across runs; unset, each run makes a new one and adopts it into the one data home after it.
KEPT_HOME = os.environ.get("PEGASUS_LIVE_HOME")
TIMEOUT = int(os.environ.get("PEGASUS_LIVE_TIMEOUT", "1800"))
#: A scenario's own budget where the default is too short for what it must read on a fresh home: the timeline links six
#: RR links against the nation's partner sides (SIH, CIHA, SINASC of two years), 1,846 s on 2026-11-09 (81e9080).
SCENARIO_TIMEOUT = {"timeline": 3600}


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
    if not coverage:
        # The readable presentation (the default since ADR-0084) has no
        # companions: a coded cell reads "Label (code)", or "code (?)" when no
        # table decodes it. Counting the companion columns alone measured 0
        # labelled columns on every default query (2026-09-30).
        import pyarrow.compute as pc

        for name in names:
            col = table.column(name)
            if not pa.types.is_string(col.type) and not pa.types.is_large_string(col.type):
                continue
            filled = pc.drop_null(col)
            if len(filled) == 0:
                continue
            coded = pc.sum(pc.match_substring_regex(filled, r"\([^()]*\)$")).as_py() or 0
            if coded < 0.9 * len(filled):
                continue
            undecoded = pc.sum(pc.ends_with(filled, " (?)")).as_py() or 0
            coverage[name] = round(1 - undecoded / len(filled), 4)
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


#: DATASUS TabNet's published 2019 figures, consulted 2026-10-15: SINASC (sinasc/cnv/nvuf.def, births by the mother's
#: residence), SIM (sim/cnv/obt10uf.def, deaths by residence) and SIH (sih/cnv/niuf.def, the twelve 2019 processing months), the
#: bands summed to the clauses below. What a condition on roles must reproduce.
TABNET_2019 = {
    "BR": {
        "births": 2849146, "weight_under_2500": 247856, "weight_under_1500": 40453, "weight_unknown": 746,
        "caesarean": 1604189, "vaginal": 1243104, "delivery_unknown": 1853, "preterm_band": 315831,
        "gestation_unknown": 36313, "mother_under_20": 419255, "mother_age_unknown": 72, "deaths": 1349801,
        "deaths_under_1y": 35293, "deaths_under_28d": 24504, "deaths_0_6d": 18402, "age_unknown": 2358,
        "home_deaths": 264628, "sih_admissions": 12181726, "sih_under_1": 644887, "sih_60_plus": 3221765,
    },
    "AL": {
        "births": 49803, "weight_under_2500": 3837, "weight_under_1500": 594, "weight_unknown": 3,
        "caesarean": 26085, "vaginal": 23676, "delivery_unknown": 42, "preterm_band": 4531, "gestation_unknown": 841,
        "mother_under_20": 10636, "mother_age_unknown": 0, "deaths": 20287, "deaths_under_1y": 659,
        "deaths_under_28d": 447, "deaths_0_6d": 344, "age_unknown": 1, "home_deaths": 4888, "sih_admissions": 171660,
        "sih_under_1": 10312, "sih_60_plus": 34900,
    },
    "AC": {
        "births": 16280, "weight_under_2500": 1187, "weight_under_1500": 167, "weight_unknown": 115,
        "caesarean": 7232, "vaginal": 9036, "delivery_unknown": 12, "preterm_band": 2234, "gestation_unknown": 468,
        "mother_under_20": 3901, "mother_age_unknown": 1, "deaths": 4098, "deaths_under_1y": 259,
        "deaths_under_28d": 131, "deaths_0_6d": 92, "age_unknown": 18, "home_deaths": 950, "sih_admissions": 44563,
        "sih_under_1": 2165, "sih_60_plus": 6827,
    },
}


def s_conditions() -> dict[str, Any]:
    """Record conditions on roles (ADR-0193) against TabNet's published 2019 figures. With PEGASUS_CONDITIONS_ROOT (a built
    lake, read only: max_download=0, nothing is fetched or written): Brazil's births and deaths and the admissions of Brazil and Alagoas;
    without it, the live home fetches the state files of PEGASUS_CONDITIONS_GEOS (default AC,AL)."""
    from pegasus_data import condition_report, count_events

    root = os.environ.get("PEGASUS_CONDITIONS_ROOT")
    kw: dict[str, Any] = {"root": root, "max_download": 0} if root else {}
    w = lambda op, v: [{"role": "birth.weight", "op": op, "value": v}]  # noqa: E731
    age = lambda op, v, unit=None: [{"role": "deceased.age_years", "op": op, "value": v, **({"unit": unit} if unit else {})}]  # noqa: E731
    cases = [
        ("births", "SINASC-DN", "birth", None, "births", None),
        ("weight < 2500 g", "SINASC-DN", "birth", w("<", 2500), "weight_under_2500", "weight_unknown"),
        ("weight < 1500 g", "SINASC-DN", "birth", w("<", 1500), "weight_under_1500", "weight_unknown"),
        ("caesarean", "SINASC-DN", "birth", [{"role": "birth.delivery", "in": ["2"]}], "caesarean", "delivery_unknown"),
        ("vaginal", "SINASC-DN", "birth", [{"role": "birth.delivery", "in": ["1"]}], "vaginal", "delivery_unknown"),
        ("preterm, gestation band 1-4", "SINASC-DN", "birth", [{"role": "birth.gestation_band", "in": ["1", "2", "3", "4"]}],
         "preterm_band", "gestation_unknown"),
        ("preterm, weeks < 37", "SINASC-DN", "birth", [{"role": "birth.gestation_weeks", "op": "<", "value": 37}],
         "preterm_band", "gestation_unknown"),
        ("mother under 20", "SINASC-DN", "birth", [{"role": "mother.age", "op": "<", "value": 20}], "mother_under_20", "mother_age_unknown"),
        ("deaths", "SIM-DO", "death", None, "deaths", None),
        ("deaths under 1 year", "SIM-DO", "death", age("<", 1), "deaths_under_1y", "age_unknown"),
        ("deaths under 28 days", "SIM-DO", "death", age("<", 28, "days"), "deaths_under_28d", "age_unknown"),
        ("deaths under 7 days", "SIM-DO", "death", age("<", 7, "days"), "deaths_0_6d", "age_unknown"),
        ("deaths at home", "SIM-DO", "death", [{"role": "death.place", "op": "==", "value": "3"}], "home_deaths", None),
    ]
    sih = [("SIH admissions", "SIH-RD", "hospitalisation", None, "sih_admissions", None),
           ("SIH under 1 year", "SIH-RD", "hospitalisation", [{"role": "patient.age_years", "op": "<", "value": 1}], "sih_under_1", None),
           ("SIH 60 years and over", "SIH-RD", "hospitalisation", [{"role": "patient.age_years", "op": ">=", "value": 60}],
            "sih_60_plus", None)]
    out: dict[str, Any] = {}
    plan = ([(geo, cases) for geo in ("BR",)] + [(geo, sih) for geo in ("AL", "BR")] if root
            else [(geo, cases) for geo in os.environ.get("PEGASUS_CONDITIONS_GEOS", "AC,AL").split(",")])
    for geo, rows in plan:
        for label, dataset, event, condition, key, unknown_key in rows:
            t = time.perf_counter()
            result = count_events(dataset, event, period=2019, geography=geo, condition=condition, **kw)
            got = result.to_pylist()[0]
            published = TABNET_2019[geo]
            record: dict[str, Any] = {"events": got["events"], "published": published[key],
                                      "difference": got["events"] - published[key], "seconds": round(time.perf_counter() - t, 1)}
            if condition is not None:
                record["unknown"] = got["unknown"]
                if unknown_key:
                    record["published_unknown"] = published[unknown_key]
                    record["unknown_difference"] = got["unknown"] - published[unknown_key]
                assert (condition_report(result) or {}).get("unknown") == got["unknown"]
            out[f"{geo}: {label}"] = record
    out["differs"] = [k for k, v in out.items() if isinstance(v, dict) and (v["difference"] or v.get("unknown_difference"))]
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
            # The analysis presentation keeps label companions, which is what
            # "labelled" counts; the readable default merges them into one column.
            table = query(code, period=period, geography=geography, present="analysis",
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


def s_linkage() -> dict[str, Any]:
    """Record linkage as a person would run it (ADR-0107): the three spine links on RR 2022, both
    methods, freshly computed; each must be viable, and the report must carry its error, its verdict's reasons and
    which validations are circular. (SIH deaths to SIM's fallback pass keys the hospital's municipality since
    2026-11-09: without it, 76 pairs at 17.11% chance made the link "use with caution".)"""
    from pegasus_data import link

    out: dict[str, Any] = {}
    for spec in ("sih_deaths_to_sim", "sim_infant_deaths_to_sinasc", "sinasc_births_to_delivery_admission"):
        for method in ("deterministic", "probabilistic"):
            t = time.perf_counter()
            result = link(spec, period="2022", geography="RR", method=method, refresh=True, persist=False,
                          allow_not_viable=True)
            s = result.summary()
            s.pop("models", None)
            out[f"{spec}/{method}"] = {
                "seconds": round(time.perf_counter() - t, 1), "left": s["left_records"], "pairs": s["pairs"],
                "linked_share": s["linked_share"], "verdict": s["verdict"],
                "error": s.get("chance_percent", s.get("estimated_fdr_percent")),
                "upper95": s.get("chance_upper95_percent", s.get("fdr_upper95_percent")),
                "validations": {k: v["agreement_percent"] for k, v in s["validations"].items()},
                "circular": sorted(k for k, v in s["validations"].items() if v.get("circular")),
                "reasons": s.get("verdict_reasons") or s.get("reasons"),
            }
            if s["verdict"] != "viable":
                raise AssertionError(f"{spec}/{method} is {s['verdict']} on RR 2022: {out[f'{spec}/{method}']}")
    return out


def s_timeline() -> dict[str, Any]:
    """The pregnancy timeline (linkage.timeline, served at /links/timeline): a birth with a linked infant death."""
    from pegasus_data.linkage import timeline as tl
    from pegasus_data.linkage.engine import link
    from pegasus_data.linkage.timeline import notable_births, timeline

    # A timeline reads stored runs only (a request never computes one; 2026-10-14 review), so every link it reads is
    # linked first. The newborn link inherits the stored delivery link of each year of its padded period (ADR-0121) and
    # its held-out validation from the infant death link (OQ 99), so both are linked before it.
    link(tl.DELIVERY, period="2021", geography="RR", method="probabilistic")
    for spec in (tl.DELIVERY, tl.DELIVERY_PRIVATE, tl.INFANT_DEATH, tl.NEONATAL, tl.MATERNAL_DEATH):
        link(spec, period="2022", geography="RR", method="probabilistic", allow_not_viable=True)
    births = notable_births(period="2022", geography="RR", method="probabilistic", limit=5)
    if not births:
        raise AssertionError("no birth with linked events on RR 2022")
    one = timeline(births[0]["birth"], period="2022", geography="RR", method="probabilistic")
    kinds = [e["kind"] for e in one["events"]]
    if "birth" not in kinds or len(kinds) < 2:
        raise AssertionError(f"timeline has no linked event: {kinds}")
    return {"notable": len(births), "events": kinds, "not_viable": one["not_viable"]}


def s_sp_strata() -> dict[str, Any]:
    """SIH-SP's sex and age, read through the AIH from SIH-RD (ADR-0199), on Acre 2023-01 (override: PEGASUS_SP_PERIOD,
    PEGASUS_SP_GEO): SP's rows in and out, the SP AIHs RD holds, the SP columns RD repeats (municipality, diagnosis,
    admission date, facility) read against the matched RD row, a known drop of RD's AIHs, and the sex and age counts."""
    import pandas as pd
    import pyarrow as pa
    import pyarrow.compute as pc

    from pegasus_data import count_events, query
    from pegasus_data.semantics.through import attach, split

    period, geo = os.environ.get("PEGASUS_SP_PERIOD", "2023-01"), os.environ.get("PEGASUS_SP_GEO", "AC")
    where = {"period": period, "geography": geo}
    own = ["SP_NAIH", "SP_M_PAC", "SP_QT_PROC", "SP_CIDPRI", "SP_DTINTER", "SP_CNES", "SP_U_AIH"]
    out: dict[str, Any] = {"period": period, "geography": geo}

    before = query("SIHSUS-SP", select=own, present="codes", **where)
    after, report = query("SIHSUS-SP", select=[*own, "SEXO", "IDADE_anos"], present="analysis", return_report=True, **where)
    link = report.through["AIH:SIH-RD"]
    out["rows"] = {"sp_before": before.num_rows, "sp_after": after.num_rows, "equal": before.num_rows == after.num_rows,
                   "same_order": after.select(own).equals(before.select(own))}
    out["through"] = link
    out["labelled"] = {c: round(1 - after.column(c).null_count / after.num_rows, 4)
                       for c in ("SEXO", "SEXO_label", "IDADE_anos") if c in after.column_names}
    out["sex_codes"] = {f"{c} {lb}": n for (c, lb), n in
                        Counter(zip(after["SEXO"].to_pylist(), after["SEXO_label"].to_pylist(), strict=True)).items()}

    # the match is of one admission, not of a coincidence of numbers: the columns SP and RD both file must agree on it
    rd = query("SIHSUS-RD", select=["N_AIH", "IDENT", "MUNIC_RES", "DIAG_PRINC", "DT_INTER", "CNES", "SEXO", "IDADE_anos"],
               present="codes", **where).to_pandas()
    sp = before.to_pandas()
    admissions = rd[rd.IDENT == "1"]
    agree = sp.drop_duplicates("SP_NAIH").merge(admissions, left_on="SP_NAIH", right_on="N_AIH", how="left")
    out["agreement_on_the_matched_admission"] = {
        "sp_aihs": len(agree), "with_rd_admission": int(agree.N_AIH.notna().sum()), "rd_admissions_unique": bool(admissions.N_AIH.is_unique),
        **{label: round(float((agree[a].astype(str).str.strip() == agree[b].astype(str).str.strip())[agree.N_AIH.notna()].mean()), 6)
           for label, a, b in (("residence", "SP_M_PAC", "MUNIC_RES"), ("principal_diagnosis", "SP_CIDPRI", "DIAG_PRINC"),
                               ("admission_date", "SP_DTINTER", "DT_INTER"), ("facility", "SP_CNES", "CNES"))}}
    repeated = rd[rd.N_AIH.duplicated(keep=False)]
    out["rd_repeated_aihs"] = {"rows": len(repeated), "aihs": int(repeated.N_AIH.nunique()),
                               "types": {"+".join(k): n for k, n in Counter(map(tuple, repeated.groupby("N_AIH").IDENT.apply(sorted))).items()},
                               "disagree_on_sex_or_age": int((repeated.groupby("N_AIH")[["SEXO", "IDADE_anos"]].nunique(dropna=False) > 1)
                                                            .any(axis=1).sum())}

    # a known answer for the unmatched: remove RD's rows of 50 AIHs from what SP reads through, and SP's rows of exactly
    # those AIHs (counted from SP alone) must come out null and be reported, and every other row must keep its value
    cut = set(sp.SP_NAIH.drop_duplicates().head(50))
    asked_select = [*own, "SEXO", "IDADE_anos"]
    narrowed, asked = split("SIHSUS-SP", asked_select)
    rd_cut = query("SIHSUS-RD", select=["N_AIH", "IDENT", "SEXO", "IDADE_anos"], present="analysis", **where)
    rd_cut = rd_cut.filter(pc.invert(pc.is_in(rd_cut["N_AIH"], value_set=pa.array(sorted(cut)))))
    base = query("SIHSUS-SP", select=narrowed, present="analysis", **where)
    cut_table, cut_report = attach(base, "SIHSUS-SP", asked, asked_select, lambda source, columns: rd_cut)
    entry = cut_report["AIH:SIH-RD"]
    nulls = cut_table["SEXO"].null_count
    out["known_drop"] = {"aihs_removed_from_rd": len(cut), "sp_rows_of_them": int(sp.SP_NAIH.isin(cut).sum()),
                         "unmatched_reported": entry["unmatched"], "keys_unmatched_reported": entry["keys_unmatched"],
                         "null_sex_rows": nulls, "rows_kept": cut_table.num_rows == before.num_rows,
                         "others_equal_the_full_read": bool(
                             cut_table.filter(pc.invert(pc.is_in(cut_table["SP_NAIH"], value_set=pa.array(sorted(cut)))))["IDADE_anos"].equals(
                                 after.filter(pc.invert(pc.is_in(after["SP_NAIH"], value_set=pa.array(sorted(cut)))))["IDADE_anos"]))}

    # the same through the event reader, the way PegaSUS counts: events are SP_QT_PROC, whatever the join does
    by = ["SP_M_PAC", "IDADE_anos", "SEXO"]
    events = count_events("SIHSUS-SP", "procedure", period=period, geography=geo, by=by)
    out["events"] = {"counted": int(pc.sum(events["events"]).as_py()), "sum_of_sp_qt_proc": int(pd.to_numeric(sp.SP_QT_PROC).sum()),
                     "cells": events.num_rows}

    # sex and age of SP's procedures beside RD's admissions, ten-year bands
    sex = {"1": "male", "3": "female"}
    band = lambda age: min(int(age // 10) * 10, 80)  # noqa: E731
    procs = after.to_pandas().assign(sex=lambda d: d.SEXO.map(sex), band=lambda d: d.IDADE_anos.map(band), n=lambda d: pd.to_numeric(d.SP_QT_PROC))
    admits = admissions.assign(sex=lambda d: d.SEXO.map(sex), band=lambda d: d.IDADE_anos.map(band))
    table = pd.DataFrame({
        "sp_procedures": procs.groupby(["sex", "band"]).n.sum(), "sp_aihs": procs.drop_duplicates("SP_NAIH").groupby(["sex", "band"]).size(),
        "rd_admissions": admits.groupby(["sex", "band"]).size()}).fillna(0).astype(int)
    table["procedures_per_admission"] = (table.sp_procedures / table.rd_admissions).round(2)
    out["sex_age"] = {f"{s} {b}": row for (s, b), row in table.to_dict("index").items()}
    out["share_female"] = {"sp_procedures": round(float(procs[procs.sex == "female"].n.sum() / procs.n.sum()), 4),
                           "rd_admissions": round(float((admits.sex == "female").mean()), 4)}
    return out


def s_cnefe_cep() -> dict[str, Any]:
    """CNEFE 2022 places the patient's CEP (ADR-0205): SIH-RD of one state-year (override: PEGASUS_CNEFE_PERIOD, PEGASUS_CNEFE_GEO;
    default 2023, AL) against the per-CEP table. Builds the UF's CNEFE if the home has none, checks it against IBGE's aggregate
    by CEP, then counts: the AIH rows whose CEP is in the CNEFE, whether the CEP's municipality is MUNIC_RES, the AIHs on a
    CEP that is its municipality's only one (which places nobody inside it), and how far a found CEP's addresses spread."""
    import numpy as np
    import pandas as pd

    from pegasus_data import cep_points, load_settings, query
    from pegasus_data.geography import distance_km, great_circle_km, mesh
    from pegasus_data.sources import ibge_cnefe

    period, geo = int(os.environ.get("PEGASUS_CNEFE_PERIOD", "2023")), os.environ.get("PEGASUS_CNEFE_GEO", "AL")
    out: dict[str, Any] = {"period": period, "geography": geo}
    if geo not in ibge_cnefe.built_ufs():
        t = time.perf_counter()
        built = ibge_cnefe.build_cnefe([geo], keep_raw=True)
        out["built_here"] = {"seconds": round(time.perf_counter() - t, 1), "failed": built["failed"], "records": built["records"]}
    out["manifest"] = {k: v for k, v in ibge_cnefe.manifest()["ufs"][geo].items() if k not in ("nulls",)}
    out["aggregate_check"] = ibge_cnefe.check_against_aggregate(None, [geo])

    ceps = cep_points(uf=geo, tracts=False).to_pandas()
    sih = query("SIH-RD", period=period, geography=geo, select=["CEP", "MUNIC_RES", "N_AIH", "IDENT"], present="codes").to_pandas()
    out["sih"] = {"rows": len(sih), "n_aih": int(sih.N_AIH.nunique()), "ident": sih.IDENT.value_counts().to_dict(),
                  "cep_filled": round(float(sih.CEP.notna().mean()), 6), "cep_widths": sih.CEP.str.len().value_counts().to_dict(),
                  "distinct_ceps": int(sih.CEP.nunique())}

    # the CEP's municipalities (six digits, as MUNIC_RES): a CEP spanning municipalities is all of them, never one chosen. The CEPs
    # are looked up in every UF built (a patient can live in another state)
    out["ufs_built"] = len(ibge_cnefe.built_ufs())
    looked_up = cep_points(cep=sorted(sih.CEP.dropna().unique()), tracts=False).to_pandas()
    where = looked_up.groupby("cep").municipality.agg(lambda m: tuple(sorted(m)))
    sih = sih.assign(cnefe_municipalities=sih.CEP.map(where))
    found = sih.cnefe_municipalities.notna()
    agrees = pd.Series([m in ms if ms is not None and ms == ms else False for m, ms in zip(sih.MUNIC_RES, sih.cnefe_municipalities, strict=True)],
                       index=sih.index)
    resident = sih.MUNIC_RES.str[:2] == ibge_cnefe.UF_FILES[geo]
    out["found"] = {"rows_in_cnefe": int(found.sum()), "share": round(float(found.mean()), 5),
                    "distinct_ceps_in_cnefe": int(sih.CEP[found].nunique()), "of_distinct": int(sih.CEP.nunique()),
                    "residents_of_the_state": int(resident.sum()),
                    "share_of_residents": round(float(found[resident].mean()), 5),
                    "share_of_non_residents": round(float(found[~resident].mean()), 5) if (~resident).any() else None}
    kind = np.where(~found, "cep not in the CNEFE", np.where(agrees, "municipality agrees", "municipality differs"))
    out["municipality"] = {k: int(v) for k, v in pd.Series(kind).value_counts().items()}
    seen = sih[found & resident]
    out["municipality_of_residents_found"] = {
        "rows": len(seen), "agree": int(agrees[seen.index].sum()), "share": round(float(agrees[seen.index].mean()), 5),
        "agree_with_a_cep_of_several_municipalities": int((agrees[seen.index] & (seen.cnefe_municipalities.str.len() > 1)).sum())}

    # a test that could not fail says nothing: the same count with the municipalities shuffled among the found rows
    rng = np.random.default_rng(0)
    shuffled = rng.permutation(seen.MUNIC_RES.to_numpy())
    out["placebo_agreement"] = {"shuffled_municipalities_agree": int(sum(m in ms for m, ms in zip(shuffled, seen.cnefe_municipalities, strict=True))),
                                "of": len(seen)}

    # the rows of residents whose CEP the CNEFE does not hold: what they are (the suffix is the last three digits)
    lost = sih[~found & resident]
    band = lambda c: np.where(c.str[5:] == "000", "000", np.where(c.str[5:] >= "900", "900-999", "001-899"))  # noqa: E731
    out["not_found_residents"] = {
        "rows": len(lost), "distinct_ceps": int(lost.CEP.nunique()),
        "suffix_bands_not_found": {k: int(v) for k, v in pd.Series(band(lost.CEP)).value_counts().items()},
        "suffix_bands_found": {k: int(v) for k, v in pd.Series(band(seen.CEP)).value_counts().items()},
        "top_municipalities": {k: int(v) for k, v in lost.MUNIC_RES.value_counts().head(5).items()},
        "top_ceps": {k: int(v) for k, v in lost.CEP.value_counts().head(5).items()}}

    # where they differ: the CEP's own municipality against the patient's, and how far apart the two are
    differs = sih[found & ~agrees]
    pairs = differs.assign(cnefe=differs.cnefe_municipalities.map(lambda ms: ms[0] if len(ms) == 1 else "+".join(ms))
                           ).groupby(["MUNIC_RES", "cnefe"]).size().sort_values(ascending=False)
    km = [distance_km(a, b) for (a, b) in pairs.index if "+" not in b]
    km = np.array([k for k in km if k is not None])
    out["differs"] = {"rows": len(differs), "pairs": len(pairs), "top": {f"{a}->{b}": int(n) for (a, b), n in pairs.head(8).items()},
                      "km_between_municipalities_median": round(float(np.median(km)), 1) if len(km) else None,
                      "share_of_rows_within_50km": round(float(np.average(km <= 50, weights=[pairs[(a, b)] for (a, b) in pairs.index if "+" not in b
                                                                                               and distance_km(a, b) is not None])), 3) if len(km) else None,
                      "other_state": int((differs.MUNIC_RES.str[:2] != ibge_cnefe.UF_FILES[geo]).sum())}

    # the CEPs of one big city and of the small ones
    by_city = sih[resident].groupby("MUNIC_RES").CEP.agg(aihs="size", distinct_ceps="nunique")
    capital = by_city.sort_values("aihs", ascending=False).index[0]
    own = by_city.drop(index=capital)
    out["capital"] = {"municipality": capital, **by_city.loc[capital].astype(int).to_dict(),
                      "cnefe_ceps_of_it": int(ceps[ceps.municipality == capital].cep.nunique())}
    every_city = sih.groupby("MUNIC_RES").CEP.nunique().drop(index=capital)          # whoever the AIH names, patients from other states too
    out["every_municipality_but_the_capital"] = {"count": len(every_city), "distinct_ceps_median": float(every_city.median()),
                                                 "with_one_cep": int((every_city == 1).sum())}
    out["other_municipalities"] = {"count (residents of the state)": len(own), "distinct_ceps_median": float(own.distinct_ceps.median()),
                                   "with_one_cep": int((own.distinct_ceps == 1).sum()), "aihs_with_one_cep": int(own[own.distinct_ceps == 1].aihs.sum())}

    # a CEP that is its municipality's only one places nobody inside it; the dispersion of the others, by AIHs
    keyed = sih[found].merge(looked_up.rename(columns={"cep": "CEP"}), on="CEP", how="left")
    keyed = keyed[keyed.municipality == keyed.MUNIC_RES]                     # the row of the CEP in the patient's own municipality
    keyed = keyed.assign(only=keyed.municipality_ceps == 1, suffix_000=keyed.CEP.str.endswith("000"))
    out["general_cep"] = {"aihs_on_the_only_cep_of_the_municipality": int(keyed.only.sum()),
                          "share_of_all_rows": round(float(keyed.only.sum() / len(sih)), 5),
                          "aihs_on_a_cep_ending_000": int(keyed.suffix_000.sum()),
                          "of_which_the_municipalitys_only": int((keyed.only & keyed.suffix_000).sum()),
                          "of_which_not_the_only": int((~keyed.only & keyed.suffix_000).sum()),
                          "only_cep_municipalities": int(ceps[ceps.municipality_ceps == 1].municipality.nunique())}
    counts = keyed.CEP.value_counts().head(5)
    spread = pd.cut(keyed.radius_p90_m, [-1, 300, 1000, 2000, np.inf], labels=["<=300 m", "300 m-1 km", "1-2 km", ">2 km"])
    out["spread_of_the_patients_cep"] = {
        "rows": len(keyed), "p90_radius_m_quantiles_of_rows": {f"{int(q * 100)}": round(float(keyed.radius_p90_m.quantile(q)), 1)
                                                               for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
        "rows_by_p90_radius": {str(k): int(v) for k, v in spread.value_counts().sort_index().items()},
        "of_which_the_municipalitys_only_cep": {str(k): int(v) for k, v in spread[keyed.only].value_counts().sort_index().items()},
        "rows_on_a_cep_of_one_address": int((keyed.n_addresses == 1).sum()),
        "top_ceps": [{"cep": cep, "municipality": r.municipality, "aihs": int(counts[cep]), "addresses": int(r.n_addresses),
                      "p90_radius_m": round(float(r.radius_p90_m), 1), "municipality_ceps": int(r.municipality_ceps)}
                     for cep, r in keyed.drop_duplicates("CEP").set_index("CEP").loc[counts.index].iterrows()]}

    # the CEPs' medians against the municipal mesh (full resolution): is each inside its own municipality?
    import geopandas as gpd

    polygons = mesh("municipality", "maxima")
    polygons = polygons[polygons.code.str[:2] == ibge_cnefe.UF_FILES[geo]]
    points = gpd.GeoDataFrame(ceps[["cep", "municipality7"]], geometry=gpd.points_from_xy(ceps.lon, ceps.lat), crs="EPSG:4674")
    joined = gpd.sjoin(points, polygons, how="left", predicate="within")
    inside = joined.code == joined.municipality7
    out["median_inside_own_municipality"] = {"cep_rows": len(points), "inside": int(inside.sum()), "share": round(float(inside.mean()), 5),
                                             "in_another_municipality": int((joined.code.notna() & ~inside).sum()),
                                             "in_no_polygon": int(joined.code.isna().sum())}
    import pyarrow.parquet as pq

    records = pq.read_table(load_settings().lake_dir / "cnefe_2022" / f"uf={geo}",
                            columns=["COD_UNICO_ENDERECO", "COD_MUNICIPIO", "LATITUDE", "LONGITUDE"]).to_pandas().drop_duplicates()
    where_at = gpd.sjoin(gpd.GeoDataFrame(records, geometry=gpd.points_from_xy(records.LONGITUDE, records.LATITUDE), crs="EPSG:4674"),
                         polygons, how="left", predicate="within")
    where_at = where_at[~where_at.index.duplicated()]
    own_polygon = where_at.code == where_at.COD_MUNICIPIO
    out["addresses_inside_own_municipality"] = {"addresses": len(where_at), "inside": int(own_polygon.sum()), "share": round(float(own_polygon.mean()), 5),
                                                "in_another_municipality": int((where_at.code.notna() & ~own_polygon).sum()),
                                                "in_no_polygon": int(where_at.code.isna().sum())}

    # the whole country, when every UF is built: the CEPs that span, the municipalities with one CEP, the coordinate levels, and the
    # CEPs of places whose coordinates are known (MASP, Av. Paulista 1578, 01310-200; the Maracanã, 20271-150; the Palácio do Planalto,
    # 70150-900), against São Paulo's 01001-000 (Praça da Sé), a CEP that is not a place: its addresses lie all over the city
    if out["ufs_built"] == len(ibge_cnefe.UF_FILES):
        every = cep_points(tracts=False).to_pandas()
        span = every.groupby("cep").agg(municipalities=("municipality7", "nunique"), ufs=("uf", "nunique"))
        municipalities = every.groupby("municipality7").agg(ceps=("cep", "nunique"), addresses=("n_addresses", "sum"))
        levels = every[[f"n_coord_level_{k}" for k in ibge_cnefe.LEVELS]].sum()
        out["national"] = {
            "cep_rows": len(every), "ceps": len(span), "ceps_in_more_than_one_municipality": int((span.municipalities > 1).sum()),
            "most_municipalities_of_one_cep": int(span.municipalities.max()), "ceps_in_more_than_one_uf": int((span.ufs > 1).sum()),
            "municipalities": len(municipalities), "municipalities_with_one_cep": int((municipalities.ceps == 1).sum()),
            "addresses_in_them": int(municipalities[municipalities.ceps == 1].addresses.sum()), "addresses": int(municipalities.addresses.sum()),
            "address_levels": {k: int(levels[f"n_coord_level_{k}"]) for k in ibge_cnefe.LEVELS},
            "cep_rows_by_p90_radius": {str(k): int(v) for k, v in every.groupby(pd.cut(every.radius_p90_m, [-1, 300, 1000, 2000, np.inf],
                labels=["<=300 m", "300 m-1 km", "1-2 km", ">2 km"]), observed=False).size().items()},
            "addresses_by_p90_radius": {str(k): int(v) for k, v in every.groupby(pd.cut(every.radius_p90_m, [-1, 300, 1000, 2000, np.inf],
                labels=["<=300 m", "300 m-1 km", "1-2 km", ">2 km"]), observed=False).n_addresses.sum().items()},
            "landmarks_m_from_the_known_place": {
                cep: ({"addresses": int(r.n_addresses), "radius_p50_m": round(float(r.radius_p50_m)),
                       "metres": round(float(great_circle_km(r.lon, r.lat, lon, lat) * 1000))} if len(found_row) else "not in the CNEFE")
                for cep, (lat, lon) in {"01310200": (-23.56135, -46.65590), "20271150": (-22.91222, -43.23028),
                                        "70150900": (-15.79975, -47.86078), "70160900": (-15.79974, -47.86437),
                                        "01001000": (-23.55052, -46.63331)}.items()
                for found_row in [every[every.cep == cep]] for r in [found_row.iloc[0] if len(found_row) else None]}}
    return out


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
    "conditions": s_conditions,
    "linkage": s_linkage,
    "timeline": s_timeline,
    "sweep": s_sweep,
    "sp_strata": s_sp_strata,
    "cnefe_cep": s_cnefe_cep,
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
    parser.add_argument("--fresh", action="store_true", help="empty the kept home first")
    parser.add_argument("--home", type=Path, default=Path(KEPT_HOME) if KEPT_HOME else None,
                        help="a home kept across runs (default: a new one per run, adopted and removed after it)")
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
    temporary = args.home is None
    if temporary:
        args.home = Path(tempfile.mkdtemp(prefix="pegasus_live_")) / "home"
    elif args.fresh and args.home.exists():
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
                           cwd=workdir, env=env, timeout=max(TIMEOUT, SCENARIO_TIMEOUT.get(name, 0)))
        except subprocess.TimeoutExpired:
            (out_dir / f"{name}.json").write_text(json.dumps({"scenario": name, "ok": False, "error":
                f"timeout after {max(TIMEOUT, SCENARIO_TIMEOUT.get(name, 0))}s"}), encoding="utf-8")
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
    if temporary:
        # what the run downloaded joins the one home, and the run's home goes (ADR-0208)
        sys.path.insert(0, str(ROOT / "src"))
        from pegasus_data.adopt import adopt
        from pegasus_data.config import load_settings

        summary["adopted"] = adopt(load_settings(), args.home, apply=True, remove=True).summary()
        shutil.rmtree(args.home.parent, ignore_errors=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nrecords: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
