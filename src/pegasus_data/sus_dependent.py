"""The population without private-plan coverage: the population account minus ANS beneficiaries (modelled tier).

SIH and SIA record care paid by the SUS; the people who could appear in them are the residents
**without a private medical-hospital plan**. This product is that population by place × sex ×
five-year band × year, so it is *not* a count of SUS users: a plan holder uses the SUS for part of
their care (the ANS's own reimbursement data, ``beneficiarios_identificados_sus_abi``, identify them),
and a person without a plan may use a private clinic. It is the population a plan does not insure.

    U = max(N − B, 0)        N: the population account (with its own 10-90% interval, ADR-0145)
                             B: ANS medical-hospital beneficiary links (vínculos), December of the year

* **B counts links, not persons**: someone with two medical-hospital plans counts twice, so U is a *lower*
  bound on the uninsured by the duplicates (the bias has one sign; its size is not measured). Dental-only
  plans do not insure hospital care and are left out.
* Beneficiaries whose municipality is unknown (ANS file ``XX``) or whose age is "Informada Incorreta" cannot
  be placed; they are counted and reported, not dropped silently, and not subtracted from any place.
* The interval carries the **population account's** uncertainty only (lognormal, its 10-90% width), drawn
  independently per cell, so the interval of a sum over cells is too narrow (the account's errors are shared
  across ages of a place). The error of the registry is not in it: the cells in which B exceeds the
  population's upper bound are flagged ``registry_exceeds_population`` instead.
* The account's reference date is 1 August and B is December: an offset of 4-5 months, below 0.3% of N.
* ANS data held here begin in December 2021 and the account ends in 2022: two years overlap, and 2023-2025
  need a population row that does not exist (ADR-0145 does not extrapolate).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

BANDS = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59",
         "60-64", "65-69", "70-74", "75-79", "80+"]
#: ANS age labels -> the account's bands (15-17 and 18-19 join; "Informada Incorreta" has no band).
ANS_BAND = {"Menos de 1 ano": "0-4", "1 a 4 anos": "0-4", "5 a 9 anos": "5-9", "10 a 14 anos": "10-14",
            "15 a 17 anos": "15-19", "18 a 19 anos": "15-19", "80 anos ou mais": "80+",
            **{f"{a} a {a + 4} anos": f"{a}-{a + 4}" for a in range(20, 80, 5)}}
Z80 = 1.2815515655446004


def _unplaced(root: str | Path, year: int) -> int:
    """Medical-hospital links of the year's December files that no IBGE municipality holds (the state file XX, whose
    municipality is -1, and a state's "ignored" code 270000): the records cube's own count of what it could not place
    (``unplaced_events``), read from the ANS records in the lake."""
    import json

    from .config import load_settings
    from .cubes import cube

    table = cube("records:ANS-ICB/rows", measure="QT_BENEFICIARIO_ATIVO", where={"COBERTURA_ASSIST_PLAN": {"prefix": ["M"]}},
                 periods=[str(year)], grain="year", settings=load_settings(root=Path(root)))
    return int(json.loads(table.schema.metadata[b"pegasus.cube"])["unplaced_events"])


def load_ans(root: str | Path, years: list[int]) -> tuple[dict[tuple, int], dict[int, dict[str, int]]]:
    """Medical-hospital links per (year, 6-digit municipality, sex, band), and what could not be placed."""
    from .config import load_settings
    from .fields import load_field

    settings = load_settings(root=Path(root))
    cells: dict[tuple, int] = {}
    report: dict[int, dict[str, int]] = {}
    for y in years:
        t = load_field("ans_beneficiaries", years=[y], settings=settings).select(
            ["municipality", "sex", "age_band", "coverage", "value"]).to_pylist()
        unknown = _unplaced(root, y)
        rep = {"medical_total": unknown, "municipality_unknown": unknown, "age_incorrect": 0}
        for r in t:
            if not r["coverage"].startswith("M"):          # the label is stored with a replacement character
                continue
            rep["medical_total"] += int(r["value"])
            band = ANS_BAND.get(r["age_band"])
            if band is None:
                rep["age_incorrect"] += int(r["value"])
                continue
            key = (y, int(r["municipality"]), 1 if r["sex"] == "M" else 2, band)
            cells[key] = cells.get(key, 0) + int(r["value"])
        report[y] = rep
    return cells, report


def build_sus_dependent(root: str | Path, *, version: str, validation: str, draws: int = 200, seed: int = 0,
                        log=print) -> dict[str, Any]:
    import json
    from types import SimpleNamespace

    from .modelled import ModelledManifest, write_modelled

    settings = SimpleNamespace(lake_dir=Path(root) / "lake")
    base = Path(root) / "lake" / "modelled" / "population_account"
    folder = base / "population-account-2"        # band-level intervals; version 3 is single-age (ADR-0151)
    pm = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    years = [2021, 2022, 2023, 2024, 2025]
    pop = pq.read_table(folder / "estimates.parquet", filters=[("year", "in", years), ("place_kind", "=", "municipality")]).to_pandas()
    years = sorted(int(y) for y in pop["year"].unique())
    cells, report = load_ans(root, years)
    log(f"ANS years {years}; unplaced: {report}")
    rng = np.random.default_rng(seed)
    pop = pop[pop["year"].isin(years)].reset_index(drop=True)
    members = [[int(m[:6]) for m in p.split("+")] for p in pop["place"].tolist()]
    b = np.array([sum(cells.get((y, m, s, g), 0) for m in ms) for ms, y, s, g in
                  zip(members, pop["year"].tolist(), pop["sex"].tolist(), pop["age_band"].tolist(), strict=True)],
                 dtype=float)
    n = pop["population"].to_numpy()
    lo, hi = pop["population_lo"].to_numpy(), pop["population_hi"].to_numpy()
    sigma = np.where((lo > 0) & (hi > lo), (np.log(np.maximum(hi, 1e-9)) - np.log(np.maximum(lo, 1e-9))) / (2 * Z80), 0.0)
    q_lo, q_hi, u_lo, u_hi = (np.zeros(len(n)) for _ in range(4))
    step = 20000
    for i in range(0, len(n), step):
        sl = slice(i, i + step)
        nd = n[sl, None] * np.exp(sigma[sl, None] * rng.standard_normal((len(n[sl]), draws)))
        q = np.minimum(b[sl, None] / np.maximum(nd, 1e-9), 1.0)
        u = np.maximum(nd - b[sl, None], 0.0)
        q_lo[sl], q_hi[sl] = np.quantile(q, [0.1, 0.9], axis=1)
        u_lo[sl], u_hi[sl] = np.quantile(u, [0.1, 0.9], axis=1)
    q_pt = np.minimum(b / np.maximum(n, 1e-9), 1.0)
    out = pa.table({
        "place": pop["place"].to_numpy(), "year": pop["year"].to_numpy(), "sex": pop["sex"].to_numpy(),
        "age_band": pop["age_band"].to_numpy(), "population": n, "ans_medical_links": b,
        "private_coverage": q_pt, "private_coverage_lo": q_lo, "private_coverage_hi": q_hi,
        "population_without_private_coverage": np.maximum(n - b, 0.0),
        "population_without_private_coverage_lo": u_lo, "population_without_private_coverage_hi": u_hi,
        "registry_exceeds_population": b > hi,
    })
    manifest = ModelledManifest(
        product="population_without_private_coverage", version=version,
        model="population account (ADR-0145) minus ANS medical-hospital links; sus_dependent.py v1",
        estimates={"private_coverage": ["private_coverage_lo", "private_coverage_hi"],
                   "population_without_private_coverage": ["population_without_private_coverage_lo",
                                                           "population_without_private_coverage_hi"]},
        place="place", period="year", strata=["sex", "age_band"], additive=["population_without_private_coverage"],
        inputs={"population_account": pm["version"], "ans_beneficiaries": f"ANS PDA-024, December {years}"},
        validation=validation,
        notes=["Not SUS users: plan holders use the SUS for part of their care; non-holders may use private care.",
               "B counts links (vínculos): duplicates make the product a lower bound on the uninsured.",
               "Interval = the population account's own interval only, independent per cell; the registry error is not in it.",
               f"Unplaced ANS links (municipality unknown or age incorrect), not subtracted anywhere: {report}"])
    path = write_modelled(out, manifest, settings=settings)
    log(f"written {path} rows={out.num_rows}")
    return {"path": path, "report": report, "rows": out.num_rows}
