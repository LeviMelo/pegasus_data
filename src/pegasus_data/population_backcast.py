"""The population account before 2000: municipalities 1991-1999 (modelled tier, ``population-account-5``).

Between the 1991 Census and the 2000 Census the account is anchored at both ends, as 2000-2010 is, but its units are
IPEA's 1991-2010 comparable areas (about a thousand municipalities were created in the decade) and its vital events are
deaths only: SINASC starts in 1994 and is incomplete until the end of the decade, so no birth is used. The account is run
**backward** from the coverage-corrected Census 2000 with the deaths of 1991-1999 (a cohort aged ``a+1`` at ``t+1`` was
aged ``a`` at ``t``; those born after 1991 are fixed by the 2000 census alone) and the departure of the 1991 Census from it
is carried along each cohort (``settle``), so the path leaves 2000 untouched and arrives on 1991.

* 1991 is a census by five-year group (SIDRA 200) and not corrected: its coverage is taken as the 2000 census's by state ×
  sex × band (POPSVS starts in 2000), a stated assumption;
* the Contagem of 1996 (SIDRA 475, municipal, five-year groups to 70+) is **held out** of the area estimate and scores it
  (docs/evaluation/2026-10-05-population-account-3.md, "Backcast"); it anchors only the split of an area into municipalities;
* race is not estimated before 2000 (the 1991 census published no race by municipality in SIDRA's tables).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from .population_account import (
    BANDS,
    A,
    Period,
    Places,
    lag_series,
    load_census,
    load_events,
    reconciled_coverage,
    step_events,
    step_terms,
    to_bands,
)

PRE_YEARS = list(range(1991, 2000))              # the product's years before the 2000 census
SPAN = 9                                          # 1 August 1991 to 1 August 2000 (the 1991 census is of 1 September: 8.92 years)
#: Contagem 1996 groups: ids 1140..1153 are the five-year groups 0-4 .. 65-69, 3244 is 70 and over.
CONTAGEM_GROUPS = (1140, 1141, 1142, 1143, 1144, 1145, 1146, 1147, 1148, 1149, 1150, 1151, 1152, 1153, 3244)


def area_places(places: Places, area_of: dict[int, int], n_areas: int) -> SimpleNamespace:
    """What ``load_census`` and ``load_events`` need of a unit system: here the 1991-2010 comparable areas."""
    return SimpleNamespace(n_units=n_areas, unit_of={m: area_of[m] for m in places.municipalities}, n_entities=n_areas,
                           entity_of={m: area_of[m] for m in places.municipalities}, municipalities=places.municipalities)


def _settings(root: str | Path) -> object:
    from .config import load_settings

    return load_settings(root=Path(root))


def load_contagem(root: str | Path, municipalities: list[int]) -> np.ndarray:
    """The Contagem of 1996 by municipality × sex × 15 groups (0-4 .. 65-69, 70+), NaN where the municipality has no count
    (4,974 of the 5,570 existed). SIDRA table 475, variable 93, read as its cube."""
    from .cubes import cube

    t = cube("sidra:475/93", by=["c2", "c58"], where={"c2": [4, 5], "c58": list(CONTAGEM_GROUPS)}, periods=["1996"],
             labels=False, settings=_settings(root))
    rows = [(r["place"], r["c2"], r["c58"], r["value"]) for r in t.select(["place", "c2", "c58", "value"]).to_pylist()
            if r["value"] is not None]
    index = {m: i for i, m in enumerate(municipalities)}
    gid = {g: i for i, g in enumerate(CONTAGEM_GROUPS)}
    out = np.full((len(municipalities), 2, len(CONTAGEM_GROUPS)), np.nan)
    for m, s, g, v in rows:
        i = index.get(int(m))
        if i is not None:
            out[i, 0 if s == 4 else 1, gid[g]] = v
    return out


def retreat(Nn: np.ndarray, D: np.ndarray) -> np.ndarray:
    """One step backward: the population (…, A) one step earlier from the later one ``Nn`` and the step's deaths ``D``.
    ``advance`` run in reverse: ages 0..78 come from the next year's age+1 (plus their deaths); the 80+ class takes what
    the later 80+ lost to deaths less the 79-year-olds that entered it (taken as the later year's 79, plus deaths)."""
    dr, _ = step_terms(Nn, D, None)
    N = np.zeros_like(Nn)
    N[..., :A - 2] = Nn[..., 1:A - 1] + dr[..., :A - 2]
    N[..., A - 2] = Nn[..., A - 2] + dr[..., A - 2]
    N[..., A - 1] = np.maximum(Nn[..., A - 1] + D[..., A - 1] - Nn[..., A - 2], 0.0)
    return N


def backward_path(close: np.ndarray, deaths: np.ndarray) -> np.ndarray:
    """The vital account run backward from ``close`` (n, 2, A), the census of 2000, through the 9 steps; ``deaths`` is the
    1991..2000 stack (10, n, 2, A). Returns (10, n, 2, A) in calendar order: ``path[k]`` is 1 August 1991 + k, ``path[9] = close``."""
    path = [close]
    for k in range(SPAN - 1, -1, -1):
        D, _ = step_events(deaths, np.zeros(deaths.shape[:1] + deaths.shape[1:3]), k)
        path.append(retreat(path[-1], D))
    return np.stack(path[::-1])


def forward_path(open_: np.ndarray, deaths: np.ndarray, steps: int = SPAN) -> np.ndarray:
    """The deaths-only forward account from ``open_`` (n, 2, A): (steps+1, n, 2, A). Ages below ``k`` after ``k`` steps are
    empty (no births are used)."""
    from .population_account import advance

    path = [open_]
    for k in range(steps):
        D, _ = step_events(deaths, np.zeros(deaths.shape[:1] + deaths.shape[1:3]), k)
        path.append(advance(path[-1], D, np.zeros(open_.shape[:2])))
    return np.stack(path)


def split_bands(bands: np.ndarray, like: np.ndarray) -> np.ndarray:
    """Five-year-group counts (n, 2, 17) to single ages (n, 2, A), each band shared over its ages in the proportion of
    ``like`` (a vital path at the same date); a band with nothing in ``like`` shares equally."""
    lb = to_bands(like)
    share = np.divide(like, lb[..., BANDS], out=np.zeros_like(like), where=lb[..., BANDS] > 0)
    width = np.bincount(BANDS, minlength=17)[BANDS]
    share = np.where(lb[..., BANDS] > 0, share, 1.0 / width)
    return bands[..., BANDS] * share


def settle(path: np.ndarray, opening: np.ndarray, rates: np.ndarray | None = None) -> np.ndarray:
    """Carry the departure of the 1991 census ``opening`` from the backward path along the cohorts (zero at 2000, all of it
    at 1991). The cohort aged ``a`` in 1991 is aged ``a+k`` k years later; the 80+ stays 80+. With ``rates`` (n, 2, A; the
    migration schedule of ``population_account.fit_schedule``) the cohort's migration of each year is the schedule's rate
    at its age times its size, and what the schedule leaves is spread evenly; without, all of it is even. A cell that would
    go negative is set to zero."""
    R = opening - path[0]
    out = path.copy()
    for a in range(A):
        P = np.zeros((SPAN + 1,) + R.shape[:2])
        if rates is not None and a < A - 1:
            for j in range(SPAN):
                x = min(a + j, A - 1)
                P[j + 1] = P[j] + rates[..., x] * path[j][..., x]
        rest = -R[..., a] - P[SPAN]                       # the cohort's migration over the period is -R, as the path is anchored at 2000
        for k in range(SPAN):
            pos = min(a + k, A - 1)
            out[k][..., pos] += R[..., a] + P[k] + (k / SPAN) * rest
    return np.maximum(out, 0)


class Pre:
    """Everything the pre-2000 account reads, assembled once."""

    def __init__(self, root: str | Path, population_root: str | Path, events_dir: str | Path, places: Places, log=print) -> None:
        S, self.area_of, self.n_areas = lag_series(root, places)
        self.places = places
        ns = area_places(places, self.area_of, self.n_areas)
        self.ns = ns
        self.state = np.zeros(self.n_areas, int)
        for m in places.municipalities:
            self.state[self.area_of[m]] = int(str(m)[:2])
        self.c00 = load_census(root, 2000, ns, "unit")
        cov = reconciled_coverage(population_root, 2000, self.c00, self.state)
        self.c00r = self.c00 * cov
        self.cov_band = cov[:, :, [int(np.flatnonzero(g == BANDS)[0]) for g in range(17)]]
        self.c91_raw = S[1991]
        self.c91 = S[1991] * self.cov_band                     # the 2000 coverage carried back (an assumption)
        log("deaths 1991-2000")
        ev = load_events(events_dir, PRE_YEARS + [2000], ns, "unit")
        self.deaths, self.report = ev["deaths"], ev["report"]
        self.births = ev["births"]
        self.members = places.municipalities
        self.c96 = load_contagem(root, self.members)
        self.size = self.c00r.sum((1, 2))

    rates: np.ndarray | None = None          # the migration schedule of each area, (n, 2, A); None: even

    def use_schedule(self, schedule: np.ndarray) -> None:
        """Settle the 1991 census with ``population_account.fit_schedule``'s age schedule (by the area's 2000 size class)."""
        from .population_account import schedule_rates

        self.rates = schedule_rates(schedule, self.size)

    def period(self) -> Period:
        """A ``Period`` carrying only what ``interval`` reads (size classes, region, horizon)."""
        n = self.n_areas
        z = np.zeros(n)
        return Period("1991-2000", float(SPAN), self.state, z.astype(int), self.size, np.zeros((n, 2, 17)), None,
                      np.zeros((n, 1)), {}, {})

    def run(self):
        """The one-sided paths and the settled interior: ``(back, forward, interior)`` each (10, n, 2, A)."""
        back = backward_path(self.c00r, self.deaths)
        open_ = split_bands(self.c91, back[0])
        fwd = forward_path(open_, self.deaths)
        return back, fwd, settle(back, open_, self.rates), open_


def area_matrix(values: np.ndarray, area_of: dict[int, int], members: list[int], n_areas: int) -> tuple[np.ndarray, np.ndarray]:
    """Sum member rows ``values`` (M, …) over areas. A member with no count (NaN) did not exist yet: it adds nothing, and the
    area is flagged ``complete`` only when every member has one. Returns the sums and, per area, whether any member counted."""
    out = np.zeros((n_areas,) + values.shape[1:])
    counted = np.zeros(n_areas, dtype=bool)
    for i, m in enumerate(members):
        if np.isfinite(values[i]).all():
            out[area_of[m]] += values[i]
            counted[area_of[m]] = True
    return out, counted


# ------------------------------------------------------------------------------------ municipalities in an area

def member_totals(root: str | Path, municipalities: list[int]) -> dict[str, np.ndarray]:
    """Per municipality (``municipalities`` order): the 1991 census total (SIDRA 200, sample table whose total is the
    universe) and the 1996 Contagem total, NaN where the municipality had no count."""
    from .cubes import cube
    from .population_account import _AGE_GROUP_IDS

    t = cube("sidra:200/93", by=["c2", "c58"], where={"c2": [4, 5], "c58": list(_AGE_GROUP_IDS)}, periods=["1991"],
             labels=False, settings=_settings(root))
    rows: dict[int, float] = {}
    for r in t.select(["place", "value"]).to_pylist():
        if r["value"] is not None:
            rows[r["place"]] = rows.get(r["place"], 0.0) + r["value"]
    return {"t91": np.array([rows.get(m, np.nan) for m in municipalities], dtype=float)}


def trajectory(anchors: dict[int, np.ndarray], g_after: np.ndarray, weight: float) -> tuple[np.ndarray, np.ndarray]:
    """Log-size paths ℓ (10, M) for 1991..2000 through the members' counts at the ``anchors`` years (each (M,)), linear
    between them; before the earliest anchor ℓ moves by ``weight`` of the member's growth per year after it (``g_after``,
    the growth of its first interval, or its 2000-2010 growth when only 2000 anchors). Also the distance in years to the
    nearest anchor, (10,)."""
    years = np.array(sorted(anchors))
    yy = np.arange(1991, 2001, dtype=float)
    L = np.log(np.maximum(np.stack([anchors[y] for y in years]), 1.0))            # (K, M)
    ell = np.stack([np.interp(yy, years, L[:, j]) for j in range(L.shape[1])], 1)
    ell = np.where(yy[:, None] < years[0], L[0][None] + weight * g_after[None] * (yy[:, None] - years[0]), ell)
    dist = np.min(np.abs(yy[:, None] - years[None]), 1)
    return ell, dist


def split_shares(pre: Pre, members_by_area: dict[int, list[int]], t: dict[str, np.ndarray], P00: np.ndarray, t10: np.ndarray,
                 split_cal: dict, sig00: np.ndarray, *, use96: bool, weight: float = 0.5) -> dict[int, dict]:
    """For each area of several municipalities, every member's band shares at 1991..2000 and their logit-share sd.

    Anchors: 2000 (the product's own municipal estimate, ``P00`` (M,2,17); its split sd ``sig00`` carries over), 1991 when every
    member of the area has a 1991 count, and 1996 (``use96``) when every member has a Contagem count. A member missing at an
    anchor means the area's boundaries changed between the anchor and 2000, so that anchor counts none of them."""
    from .population_tensor import member_shares, split_sigma

    out = {}
    t00 = P00.sum((1, 2))
    t96 = np.nansum(pre.c96, (1, 2)) * np.where(np.isfinite(pre.c96).all((1, 2)), 1.0, np.nan)
    for a, mem in members_by_area.items():
        if len(mem) < 2:
            continue
        anchors = {2000: t00[mem]}
        for yr, tot in ((1991, t["t91"]), (1996, t96)):
            if yr == 1996 and not use96:
                continue
            v = tot[mem]
            if np.isfinite(v).all() and (v > 0).all():
                anchors[yr] = v
        first = min(anchors)
        nxt = sorted(anchors)[1] if len(anchors) > 1 else None
        if nxt is not None:
            g = (np.log(np.maximum(anchors[nxt], 1.0)) - np.log(np.maximum(anchors[first], 1.0))) / (nxt - first)
        else:
            g = np.where((t00[mem] > 0) & (t10[mem] > 0), (np.log(np.maximum(t10[mem], 1.0)) - np.log(np.maximum(t00[mem], 1.0))) / 10, 0.0)
        ell, dist = trajectory(anchors, g, weight)
        S = member_shares(P00[mem], ell, ell[-1])
        sig = split_sigma(split_cal, np.maximum(t00[mem], 1.0)[None], dist[:, None], census_year=(dist == 0)[:, None])
        sig = np.sqrt(sig**2 + sig00[mem][None] ** 2)
        out[a] = {"members": mem, "S": S, "sig": sig, "anchors": sorted(anchors)}
    return out


# ------------------------------------------------------------------------------------------------ the product

#: The 1996 hold-out found the cross-period spreads of 2000-2010 and 2010-2022 slightly narrow for 1991-2000 (area-total
#: 80% coverage 0.785, sex-band cells 0.74); this factor on the band spread gives 0.83/0.79 (80%) and 0.94/0.94 (95%).
PRE_SCALE = 1.2
#: Quantiles of the standardized logit-share errors of the split at 1996 (areas whose members were all counted then, split from
#: the 2000 anchor alone, 621 members): larger than 2000-2010's pairs (1.48, 2.76).
PRE_ZQ = {0.8: 2.16, 0.95: 4.58}


def area_arrays(pre: Pre, cal) -> tuple[np.ndarray, dict]:
    """The settled interior of every area for 1991..1999, (9, n, 2, A), and the log offsets of its band intervals (lower,
    upper), each (9, n, 2, 17), per level. The bridge between the two censuses uses the spread of ``cal`` times ``PRE_SCALE``."""
    from .population_account import LEVELS, Calibration, interval

    _, _, interior, _ = pre.run()
    P = pre.period()
    c2 = Calibration(cal.b, cal.s_total, cal.gm, cal.q_total, cal.coef, cal.s_band * PRE_SCALE, cal.q_band, cal.widened, cal.periods)
    X = interior[:SPAN]
    bands = np.stack([to_bands(x) for x in X])
    c = np.log(np.maximum(bands, 1e-9))
    off = {}
    for lv in LEVELS:
        lo, hi = zip(*(interval(P, c2, bands[k], float(SPAN - k), lv, total=False, timing=k / SPAN) for k in range(SPAN)), strict=True)
        off[lv] = (c - np.array(lo), np.array(hi) - c)
    return X, off


def backcast_tables(pre: Pre, cal, S: dict[int, dict], shape_cal: dict, ctx: dict, old: dict, *, chunk: int = 120, log=print):
    """The product's rows for 1991..1999 as pyarrow tables of ``chunk`` municipalities, in the schema of
    ``population_tensor.tensor_tables`` and for the race level ``total`` only (no race is estimated before 2000)."""
    import pyarrow as pa

    from .population_account import LEVELS
    from .population_tensor import AGES, BANDS101, BASIS, RACE_LEVELS, Z, age_cells, shape_at, state_shapes

    shapes = state_shapes(old, ctx["state"], ctx["states"])
    fshape = np.stack([shape_at(shapes, float(y)) for y in PRE_YEARS])                       # (9, S, 2, 21)
    k = np.arange(SPAN)
    ft = np.maximum(k / SPAN * (1 - k / SPAN), 1 / SPAN * (1 - 1 / SPAN))                    # ages are not observed in 1991 either
    Xa, off = area_arrays(pre, cal)
    ms = np.array(pre.members)
    size = np.bincount([pre.area_of[m] for m in pre.members], minlength=pre.n_areas)
    NY = len(PRE_YEARS)
    for c0 in range(0, len(ms), chunk):
        sel = list(range(c0, min(c0 + chunk, len(ms))))
        n = len(sel)
        out = {key: np.zeros((n, NY, 2, AGES), dtype=np.float32) for key in ("pop", "lo", "hi", "lo95", "hi95")}
        basis = np.full((n, NY), 2, dtype=np.int8)                                            # backcast
        for j, i in enumerate(sel):
            a = pre.area_of[int(ms[i])]
            g = S.get(a)
            if g is None:
                sh, sg = np.ones((NY, 2, 17)), np.zeros(NY)
            else:
                mem = g["members"].index(i)
                sh, sg = g["S"][:NY, mem], g["sig"][:NY, mem]
            X, sdsplit, var_sh = age_cells(Xa[:, a], sh, sg, fshape[:, ctx["k_state"][i]], ft, shape_cal)
            out["pop"][j] = X
            for lv, nm in zip(LEVELS, ("", "95"), strict=True):
                lo_b, hi_b = off[lv][0][:, a][..., BANDS101], off[lv][1][:, a][..., BANDS101]
                extra = np.minimum((PRE_ZQ[lv] * sdsplit) ** 2 + Z[lv] ** 2 * var_sh, 4.0)
                out["lo" + nm][j] = X * np.exp(-np.sqrt(lo_b**2 + extra))
                out["hi" + nm][j] = X * np.exp(np.sqrt(hi_b**2 + extra))
            if size[a] == 1:
                basis[j, 0] = 0                                    # 1991: this municipality's own census count
        rows = n * NY * 2 * AGES
        rep = lambda v, r, t_=1: np.tile(np.repeat(v, r), t_)      # noqa: E731
        yield pa.table({
            "municipality": pa.array(np.repeat(ms[sel].astype(np.int32), NY * 2 * AGES)),
            "year": pa.array(rep(np.array(PRE_YEARS, np.int16), 2 * AGES, n)),
            "sex": pa.array(rep(np.array([1, 2], np.int8), AGES, n * NY)),
            "age": pa.array(rep(np.arange(AGES, dtype=np.int16), 1, n * NY * 2)),
            "race": pa.DictionaryArray.from_arrays(pa.array(np.zeros(rows, np.int8)), pa.array(RACE_LEVELS)),
            "population": pa.array(out["pop"].ravel()), "population_lo": pa.array(out["lo"].ravel()),
            "population_hi": pa.array(out["hi"].ravel()), "population_lo95": pa.array(out["lo95"].ravel()),
            "population_hi95": pa.array(out["hi95"].ravel()),
            "basis": pa.DictionaryArray.from_arrays(pa.array(np.repeat(basis.ravel(), 2 * AGES)), pa.array(BASIS)),
        })
        log(f"municipalities {c0}-{c0 + n}")


def write_product(root: str | Path, *, source: str, version: str, validation: str, tables, notes: list[str],
                  tail=None, model_note: str = "") -> dict:
    """Write ``version`` of ``population_account``: the backcast ``tables`` (1991-1999), then every row group of the version
    ``source`` (2000-2030) unchanged, or ``tail`` (tables of the same schema: the rebuilt 2000-2030) when given, with
    ``source``'s manifest as the base and ``model_note`` appended to its model. A version is never overwritten."""
    import json

    import pyarrow.parquet as pq

    from .modelled import ModelledManifest, write_modelled

    base = Path(root) / "lake" / "modelled" / "population_account" / source
    src = pq.ParquetFile(base / "estimates.parquet")
    old = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    first = next(tables)
    if first.schema.remove_metadata() != src.schema_arrow.remove_metadata():
        raise ValueError(f"the backcast rows do not have the schema of {source}:\n{first.schema}\n{src.schema_arrow}")

    def chain():
        yield first
        yield from tables
        if tail is not None:
            yield from tail
            return
        for g in range(src.num_row_groups):
            yield src.read_row_group(g)

    manifest = ModelledManifest(
        product="population_account", version=version,
        model=old["model"] + "; extended back to 1991 by population_backcast.py: the vital account run backward from the "
                             "coverage-corrected Census 2000 with SIM deaths of 1991-1999 and settled on the Census 1991 "
                             "(comparable areas 1991-2010), the municipal split anchored on the 2000 estimate and the Contagem 1996" + model_note,
        estimates=old["estimates"], place="municipality", period="year", strata=["sex", "age", "race"],
        additive=["population"], inputs={**old["inputs"], "Census 1991 by five-year group": "SIDRA table 200",
                                            "Contagem 1996 by five-year group (split anchor, hold-out of the area estimate)": "SIDRA table 475",
                                            "SIM 1991-1995 (corrected base)": "SIM.DOR", "SIM 1996-1999": "SIM.DO"},
        validation=validation, notes=old["notes"] + notes)
    path = write_modelled(chain(), manifest, settings=type("S", (), {"lake_dir": Path(root) / "lake"})())
    return {"path": str(path)}
