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

Z80 = 1.2815515655446004


def _links_field() -> tuple[str, dict, dict]:
    """The field of plan links the product subtracts (``inputs: links`` of its entry in ``curation/products.yml``) and its
    declaration: the declared ``where`` names the coverage that insures hospital care, the declared ``years`` the years;
    and its records cube plan (the measure column, the stratum columns by their names)."""
    from .config import curation_root
    from .fields import declared_fields, intake_cube
    from .semantics.curation import read_yaml

    name = str(read_yaml(curation_root() / "products.yml")["products"]["population_without_private_coverage"]["inputs"]["links"]["field"])
    spec = declared_fields()[name]
    return name, spec, intake_cube(name, spec)


def ans_band(label: str | None, labels: list[str]) -> str | None:
    """The population account's five-year band (``population_account.BAND_LABELS``) holding an ANS age label, read from
    the numbers it states ("Menos de 1 ano", "5 a 9 anos", "15 a 17 anos", "80 anos ou mais"); None when the label states
    none or spans two bands (Informada Incorreta): such links are counted and reported, never placed in a band."""
    import re

    text = str(label or "").lower()
    if (m := re.fullmatch(r"menos de (\d+) anos?", text)):
        lo, hi = 0, int(m.group(1)) - 1
    elif (m := re.fullmatch(r"(\d+) a (\d+) anos", text)):
        lo, hi = int(m.group(1)), int(m.group(2))
    elif (m := re.fullmatch(r"(\d+) anos ou mais", text)):
        lo, hi = int(m.group(1)), None
    else:
        return None
    top = len(labels) - 1                                      # the open band (80+) begins at 5 * top
    first = min(lo // 5, top)
    if hi is None:
        return labels[first] if lo // 5 >= top else None
    return labels[first] if min(hi // 5, top) == first else None


def _unplaced(root: str | Path, year: int) -> int:
    """Medical-hospital links of the year's December files that no IBGE municipality holds (the state file XX, whose
    municipality is -1, and a state's "ignored" code 270000): the records cube's own count of what it could not place
    (``unplaced_events``), read from the ANS records in the lake."""
    import json

    from .config import load_settings
    from .cubes import cube

    _, spec, plan = _links_field()
    coverage = {alias: column for column, alias in plan["strata"]}["coverage"]
    table = cube(plan["source"], measure=plan["measure"], where={coverage: [str(spec["where"]["coverage"])]},
                 periods=[str(year)], grain="year", settings=load_settings(root=Path(root)))
    return int(json.loads(table.schema.metadata[b"pegasus.cube"])["unplaced_events"])


def load_ans(root: str | Path, years: list[int]) -> tuple[dict[tuple, int], dict[int, dict[str, int]]]:
    """Medical-hospital links per (year, 6-digit municipality, sex, band), and what could not be placed: links with no
    municipality, with an age no band holds (``age_incorrect``) or a sex neither M nor F (``sex_unknown``) are counted in
    ``medical_total`` and reported, and subtracted from no cell."""
    import pyarrow as pa

    from .config import load_settings
    from .fields import load_field
    from .population_account import BAND_LABELS
    from .semantics.categories import canonical_sex

    name, spec, _ = _links_field()
    settings = load_settings(root=Path(root))
    cells: dict[tuple, int] = {}
    report: dict[int, dict[str, int]] = {}
    for y in years:
        t = load_field(name, years=[y], settings=settings).select(
            ["municipality", "sex", "age_band", "coverage", "value"]).to_pylist()
        sexes = canonical_sex(pa.array([r["sex"] for r in t], pa.string())).to_pylist()
        unknown = _unplaced(root, y)
        rep = {"medical_total": unknown, "municipality_unknown": unknown, "age_incorrect": 0, "sex_unknown": 0}
        for r, sex in zip(t, sexes, strict=True):
            if r["coverage"] != spec["where"]["coverage"]:       # the declared plan coverage, whole (a dental plan is another link)
                continue
            rep["medical_total"] += int(r["value"])
            band = ans_band(r["age_band"], BAND_LABELS)
            if band is None:
                rep["age_incorrect"] += int(r["value"])
                continue
            if sex is None:
                rep["sex_unknown"] += int(r["value"])
                continue
            key = (y, int(r["municipality"]), 1 if sex == "M" else 2, band)
            cells[key] = cells.get(key, 0) + int(r["value"])
        report[y] = rep
    return cells, report


def build_sus_dependent(settings, *, version: str, validation: str, draws: int = 200, seed: int = 0,
                        log=print) -> dict[str, Any]:
    """Write the ``population_without_private_coverage`` modelled product: the population account's version declared in
    `curation/products.yml` minus the ANS medical-hospital links of the years both hold."""
    from .modelled import ModelledManifest, write_modelled

    root = settings.root
    from .config import curation_root
    from .fields import _years
    from .modelled import read_modelled
    from .semantics.curation import read_yaml

    # the years the links field declares; those the account holds are built (it does not extrapolate, ADR-0145)
    years = _years(str(_links_field()[1]["years"]))
    # the account's own five-year-band estimate with its band intervals (`population_account_bands`, the version declared)
    account = read_yaml(curation_root() / "products.yml")["products"]["population_without_private_coverage"]["inputs"]["population_account_bands"]["version"]
    estimates, pm = read_modelled("population_account_bands", str(account), settings=settings)
    import pyarrow.compute as pc

    keep = pc.and_(pc.is_in(estimates.column("year"), pa.array(years, estimates.column("year").type)),
                   pc.equal(estimates.column("place_kind"), "municipality"))
    pop = estimates.filter(keep).to_pandas()
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
        inputs={"population_account_bands": pm["version"], "ans_beneficiaries": f"ANS PDA-024, December {years}"},
        validation=validation,
        notes=["Not SUS users: plan holders use the SUS for part of their care; non-holders may use private care.",
               "B counts links (vínculos): duplicates make the product a lower bound on the uninsured.",
               "Interval = the population account's own interval only, independent per cell; the registry error is not in it.",
               f"Unplaced ANS links (municipality unknown or age incorrect), not subtracted anywhere: {report}"])
    path = write_modelled(out, manifest, settings=settings)
    log(f"written {path} rows={out.num_rows}")
    return {"path": path, "report": report, "rows": out.num_rows}
