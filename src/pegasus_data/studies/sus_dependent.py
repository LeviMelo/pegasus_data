"""The population without private-plan coverage: the population account minus ANS beneficiaries (modelled tier).

SIH and SIA record care paid by the SUS; the people who could appear in them are the residents
**without a private medical-hospital plan**. This product is that population by place × sex ×
five-year band × year, so it is *not* a count of SUS users: a plan holder uses the SUS for part of
their care (the ANS's own reimbursement data, ``beneficiarios_identificados_sus_abi``, identify them),
and a person without a plan may use a private clinic. It is the population a plan does not insure.

    U = max(N − B, 0)        N: the population account (with its own 10-90% interval, ADR-0145)
                             B: ANS medical-hospital beneficiary links (vínculos), December of the year
                                (the quarterly municipal base, TabNet tb_bb: 2000 to the last December published)

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
* The ANS municipality is the residence the operator registered in the SIB, so in a small place B can exceed
  the population (``registry_exceeds_population``, and U is then 0 where B exceeds N).
* Before 2010 the account's places are the comparable areas (``amc:``), not municipalities: B is the sum of the
  municipalities each area holds (`area_members`). From 2010 the municipality rows are used.
* One source throughout (ADR-0235): the PDA-024 consolidation (2021 on) and tb_bb give the same December counts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np
import pyarrow as pa

Z80 = 1.2815515655446004


def _links_field() -> tuple[str, dict, dict]:
    """The field of plan links the product subtracts (``inputs: links`` of its entry in ``curation/products.yml``): the
    medical-hospital beneficiaries, which insure hospital care (a dental-only plan is another field), its declaration (the
    declared ``years``) and its records cube plan (the measure column, the stratum columns by their names)."""
    from ..fields import declared_fields, intake_cube
    from ..semantics.curation import product

    name = str(product("population_without_private_coverage")["inputs"]["links"]["field"])
    spec = declared_fields()[name]
    return name, spec, cast(dict, intake_cube(name, spec))


def age_labels(source: str, alias: str) -> dict[str, str]:
    """The labels of the age codes a source's records cube files (curation/intake.yml, the column's ``codes`` from the
    source's CNV table), by the stratum's name in the field."""
    from ..fields import declared_fields
    from ..semantics.intake_declarations import declared_sources, strata

    spec = declared_fields()[source]
    declaration = declared_sources()[str(spec["intake"])]
    column = next(c for c, a in strata(declaration["fields"][source]) if a == alias)
    return {str(k): str(v) for k, v in (declaration["columns"][str(column)].get("codes") or {}).items()}


def ans_band(label: str | None, labels: list[str]) -> str | None:
    """The population account's five-year band (``population_account.BAND_LABELS``) holding an ANS age label, read from
    the numbers it states ("Menos de 1 ano", "Até 1 ano", "5 a 9 anos", "15 a 17 anos", "80 anos ou mais"); None when the label
    states none or spans two bands (Informada Incorreta, Inconsistente): such links are counted and reported, never placed in a band."""
    import re

    text = str(label or "").lower()
    if (m := re.fullmatch(r"(?:menos de|até) (\d+) anos?", text)):
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


def december_years(root: str | Path) -> list[int]:
    """The years of the links field's declaration whose December file is landed in the lake (the unit ``<year>12``)."""
    from ..config import load_settings
    from ..fields import _years
    from ..intake import _safe
    from ..persist.lake import unit_parts

    _, spec, _ = _links_field()
    lake = load_settings(root=Path(root)).lake_dir
    return [y for y in _years(str(spec["years"])) if unit_parts(lake, "ANS_BB_*", _safe(f"{y}12"))]


def load_ans(root: str | Path, years: list[int]) -> tuple[dict[tuple, int], dict[int, dict[str, int]]]:
    """Medical-hospital links per (year, 7-digit municipality, sex, band), December of each year, and what could not be
    placed: links in no IBGE municipality (the records cube's own count, ``unplaced_events``), with an age no band holds
    (``age_incorrect``) or a sex neither M nor F (``sex_unknown``) are counted in ``medical_total`` and reported, and
    subtracted from no cell."""
    import pyarrow as pa

    from ..config import load_settings
    from ..cubes import cube, manifest
    from ..semantics.categories import canonical_sex
    from .population_account import BAND_LABELS

    name, _, plan = _links_field()
    settings = load_settings(root=Path(root))
    ages = age_labels(name, "age_band")
    column = {alias: c for c, alias in plan["strata"]}
    cells: dict[tuple, int] = {}
    report: dict[int, dict[str, int]] = {}
    for y in years:
        table = cube(plan["source"], by=[column["sex"], column["age_band"]], periods=[f"{y}-12"], grain="month",
                     measure=plan["measure"], where=plan["where"], labels=False, settings=settings)
        unknown = int(manifest(table)["unplaced_events"])
        t = table.select(["place", column["sex"], column["age_band"], "value"]).to_pylist()
        sexes = canonical_sex(pa.array([r[column["sex"]] for r in t], pa.string())).to_pylist()
        rep = {"medical_total": unknown, "municipality_unknown": unknown, "age_incorrect": 0, "sex_unknown": 0}
        for r, sex in zip(t, sexes, strict=True):
            value = int(r["value"])
            rep["medical_total"] += value
            band = ans_band(ages.get(str(r[column["age_band"]])), BAND_LABELS)
            if band is None:
                rep["age_incorrect"] += value
                continue
            if sex is None:
                rep["sex_unknown"] += value
                continue
            key = (y, int(r["place"]), 1 if sex == "M" else 2, band)
            cells[key] = cells.get(key, 0) + value
        report[y] = rep
    return cells, report


def area_members(municipalities: list[int]) -> dict[str, list[int]]:
    """The 7-digit municipalities each comparable area (``amc:<code>``, IPEA's 2000-2010 areas, the account's places before
    2010) holds. A municipality created after the 2010 census belongs to no published area and joins its parents' (the
    account's own rule, `population_account.POST_2010_CREATIONS`: the first parent's area, the areas being united when
    the parents differ)."""
    import pegasus_data as pg

    from .population_account import POST_2010_CREATIONS

    out: dict[str, list[int]] = {}
    for m in municipalities:
        a = pg.memberships(str(m)).get("comparable_area_2000_2010")
        if a:
            out.setdefault(f"amc:{a.member_code}", []).append(m)
    for child, parents in POST_2010_CREATIONS.items():
        if child in municipalities:
            a = pg.memberships(str(parents[0])).get("comparable_area_2000_2010")
            if a:
                out.setdefault(f"amc:{a.member_code}", []).append(child)
    return out


def build_sus_dependent(settings, *, version: str, validation: str, draws: int = 200, seed: int = 0,
                        log=print) -> dict[str, Any]:
    """Write the ``population_without_private_coverage`` modelled product: the population account's version declared in
    `curation/products.yml` minus the ANS medical-hospital links of the years both hold."""
    from ..modelled import ModelledManifest, write_modelled

    root = settings.root
    from ..modelled import read_modelled
    from ..semantics.curation import product

    # the years the links field declares and the lake holds in December; those the account holds are built (it does not
    # extrapolate, ADR-0145)
    years = december_years(root)
    # the account's own five-year-band estimate with its band intervals (`population_account_bands`, the version declared)
    account = product("population_without_private_coverage")["inputs"]["population_account_bands"]["version"]
    estimates, pm = read_modelled("population_account_bands", str(account), settings=settings)
    import pyarrow.compute as pc

    # a year's places are the municipalities when the account has them (2010 on), else its comparable areas
    pop = estimates.filter(pc.is_in(estimates.column("year"), pa.array(years, estimates.column("year").type))).to_pandas()
    municipal = set(pop.loc[pop["place_kind"] == "municipality", "year"].unique())
    pop = pop[(pop["place_kind"] == "municipality") | ~pop["year"].isin(municipal)].reset_index(drop=True)
    years = sorted(int(y) for y in pop["year"].unique())
    cells, report = load_ans(root, years)
    log(f"ANS years {years}; unplaced: {report}")
    rng = np.random.default_rng(seed)
    every = sorted({int(m) for p in pop.loc[pop["place_kind"] == "municipality", "place"].unique() for m in p.split("+")})
    areas = area_members(every)
    members = [[int(m) for m in p.split("+")] if k == "municipality" else areas.get(p, [])
               for p, k in zip(pop["place"].tolist(), pop["place_kind"].tolist(), strict=True)]
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
        "place": pop["place"].to_numpy(), "place_kind": pop["place_kind"].to_numpy(), "year": pop["year"].to_numpy(), "sex": pop["sex"].to_numpy(),
        "age_band": pop["age_band"].to_numpy(), "population": n, "ans_medical_links": b,
        "private_coverage": q_pt, "private_coverage_lo": q_lo, "private_coverage_hi": q_hi,
        "population_without_private_coverage": np.maximum(n - b, 0.0),
        "population_without_private_coverage_lo": u_lo, "population_without_private_coverage_hi": u_hi,
        "registry_exceeds_population": b > hi,
    })
    manifest = ModelledManifest(
        product="population_without_private_coverage", version=version,
        model="population account (ADR-0145) minus ANS medical-hospital links; sus_dependent.py v2",
        estimates={"private_coverage": ["private_coverage_lo", "private_coverage_hi"],
                   "population_without_private_coverage": ["population_without_private_coverage_lo",
                                                           "population_without_private_coverage_hi"]},
        place="place", period="year", strata=["sex", "age_band"], additive=["population_without_private_coverage"],
        inputs={"population_account_bands": pm["version"], "ans_beneficiaries": f"ANS TabNet tb_bb (NR_BENEF_M), December {years}"},
        validation=validation,
        notes=["Not SUS users: plan holders use the SUS for part of their care; non-holders may use private care.",
               "B counts links (vínculos): duplicates make the product a lower bound on the uninsured.",
               "Interval = the population account's own interval only, independent per cell; the registry error is not in it.",
               f"Unplaced ANS links (municipality unknown or age incorrect), not subtracted anywhere: {report}"])
    path = write_modelled(out, manifest, settings=settings)
    log(f"written {path} rows={out.num_rows}")
    return {"path": path, "report": report, "rows": out.num_rows}
