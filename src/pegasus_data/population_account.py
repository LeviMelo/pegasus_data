"""The population account: a cohort-component account of every municipality, 2000 onward (modelled tier).

Person-years by place × age × sex between censuses are not observed. They are accounted for here, in the demographic
sense:

    P(t+1, a+1) = P(t, a) − deaths(t, a) + net migration(t, a)        (a > 0)
    P(t+1, 0)   = births(t) − deaths(t, 0) + ...

with the vital events from SIM and SINASC, steps from one census reference date (1 August) to the next (Lexis: half of
the deaths at age a leave the cohort aged a at the step's start, half the cohort aged a−1). Net migration is what the
vital account cannot say, and the model has two parts:

* **inside an intercensal period** the closing census is known: its departure from the vital account is the period's
  net migration (net of coverage), carried along each cohort through the period by an age schedule of migration (``distribute_residual``);
* **after the last census** it is forecast by a regression of the departure on the *previous decade's* cohort net
  migration (the area's own rate shrunk toward the state and micro-region, urban share, GDP per head); the national
  total stays the vital account's. The regression and its intervals were fitted on one intercensal period and scored on
  the other, in both directions (``fit_calibration``; docs/evaluation/2026-10-05-population-account-v2.md).

Every cell carries an interval whose spread was measured out of sample and grows with the horizon. A municipality created
after 2000 is estimated inside its *comparable area* (IPEA's AMC, extended to the five post-2010 creations by their
parents). The first version of the account (Gibbs-sampled hierarchical migration profiles) is kept as the product version
``population-account-1`` and no longer has code (git history, ADR-0145). This module is the account at five-year bands;
``population_tensor.py`` refines it to municipalities, single years of age and race and writes the product
(``population-account-3``, ADR-0151).
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np

#: Single years 0..79 and an open 80+ (SIM's and POPSVS's closure).
A = 81
#: Census reference date is 1 August: a step from year t carries 5/12 of year t's events and 7/12 of t+1's.
W_FIRST, W_SECOND = 5 / 12, 7 / 12
#: Hand-checked lineage of the five municipalities created after the 2010 census (IBGE, Lei estadual 2013):
#: they belong to no published comparable area, so each joins its parents'.
POST_2010_CREATIONS = {
    1504752: [1506807],                      # Mojuí dos Campos <- Santarém
    4212650: [4209409],                      # Pescaria Brava <- Laguna
    4220000: [4207007],                      # Balneário Rincão <- Içara
    4314548: [4302105, 4307906, 4305959],    # Pinto Bandeira <- Bento Gonçalves, Farroupilha, Cotiporã
    5006275: [5003256, 5002951, 5000203],    # Paraíso das Águas <- Costa Rica, Chapadão do Sul, Água Clara
}


# --------------------------------------------------------------------------------------- geography

class PlaceIndex(Protocol):
    """What ``load_census`` and ``load_events`` read of a unit system: ``Places``, or the backcast's comparable areas."""

    @property
    def municipalities(self) -> list[int]: ...
    @property
    def unit_of(self) -> dict[int, int]: ...
    @property
    def entity_of(self) -> dict[int, int]: ...
    @property
    def n_units(self) -> int: ...
    @property
    def n_entities(self) -> int: ...


@dataclass
class Places:
    """The municipalities, their estimation units and their forecast entities.

    A *unit* is a comparable area (estimation: 2000 and 2010 are on the same boundaries there). An
    *entity* is what is forecast and reported: the municipality, except inside a unit touched by a post-2010
    creation, where the whole unit is one entity (the child has no 2010 base of its own).
    """

    municipalities: list[int]                  # 7-digit codes, the current 5,570
    unit_of: dict[int, int]                    # municipality -> unit index
    entity_of: dict[int, int]                  # municipality -> entity index
    entity_members: list[list[int]]
    entity_unit: np.ndarray                    # entity -> unit
    unit_uf: np.ndarray                        # unit -> state code (int)
    unit_micro: np.ndarray                     # unit -> micro-region index
    unit_labels: list[str] = field(default_factory=list)

    @property
    def n_units(self) -> int:
        return len(self.unit_uf)

    @property
    def n_entities(self) -> int:
        return len(self.entity_members)


def build_places(municipalities: list[int]) -> Places:
    """Units from IPEA's 2000–2010 comparable areas plus the post-2010 creations' parents."""
    import pegasus_data as pg

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    area: dict[int, str] = {}
    micro: dict[int, str] = {}
    for m in municipalities:
        ms = pg.memberships(str(m))
        a = ms.get("comparable_area_2000_2010")
        area[m] = f"amc:{a.member_code}" if a else f"new:{m}"
        mr = ms.get("ibge_microregion")
        micro[m] = mr.member_code if mr else f"uf:{str(m)[:2]}"
        find(area[m])
    touched: set[str] = set()
    for child, parents in POST_2010_CREATIONS.items():
        if child not in area:
            continue
        for p in parents:
            union(area[child], area[p])
        touched.add(area[child])
    root_of = {m: find(area[m]) for m in municipalities}
    roots = sorted(set(root_of.values()))
    unit_index = {r: i for i, r in enumerate(roots)}
    unit_of = {m: unit_index[root_of[m]] for m in municipalities}
    touched_units = {unit_index[find(t)] for t in touched}
    entity_members: list[list[int]] = []
    entity_of: dict[int, int] = {}
    entity_unit: list[int] = []
    by_unit: dict[int, list[int]] = defaultdict(list)
    for m in municipalities:
        by_unit[unit_of[m]].append(m)
    for u in sorted(by_unit):
        groups = [by_unit[u]] if u in touched_units else [[m] for m in by_unit[u]]
        for g in groups:
            for m in g:
                entity_of[m] = len(entity_members)
            entity_members.append(g)
            entity_unit.append(u)
    micros = sorted(set(micro.values()))
    micro_index = {m: i for i, m in enumerate(micros)}
    unit_micro = np.zeros(len(roots), dtype=int)
    unit_uf = np.zeros(len(roots), dtype=int)
    for m in municipalities:
        unit_micro[unit_of[m]] = micro_index[micro[m]]
        unit_uf[unit_of[m]] = int(str(m)[:2])
    return Places(municipalities, unit_of, entity_of, entity_members, np.array(entity_unit), unit_uf, unit_micro, roots)


# ------------------------------------------------------------------------------------------ inputs

def load_census(root: str | Path, year: int, places: PlaceIndex, by: str = "unit") -> np.ndarray:
    """The census by (unit or entity) × sex × age 0..79,80+ — a gap (``None``) is not zero: a municipality
    without a value (created after the census) must lie inside a unit whose other members have one."""
    import pegasus_data as pg

    t = pg.load_population(series="CENSO", years=[year], by=("municipality", "year", "sex", "age"), root=root)
    if by == "member":                    # every current municipality on its own: a gap stays a gap
        n, index = len(places.municipalities), {m: i for i, m in enumerate(places.municipalities)}
    else:
        n = places.n_units if by == "unit" else places.n_entities
        index = places.unit_of if by == "unit" else places.entity_of
    out = np.zeros((n, 2, A))
    seen = np.zeros(n, dtype=bool)
    for m, s, a, p in zip(t["municipality"].to_pylist(), t["sex"].to_pylist(), t["age"].to_pylist(),
                          t["population"].to_pylist(), strict=True):
        i = index.get(int(m))
        if i is None:
            continue
        if p is None:
            continue                      # a recorded gap: never counted as zero
        out[i, int(s) - 1, min(int(a), A - 1)] += p
        seen[i] = True
    if not seen.all() and by == "unit":
        raise ValueError(f"census {year}: {int((~seen).sum())} units have no value at all")
    return out


def collect_events(root: str | Path, years: range | list[int], events_dir: str | Path, log=print) -> None:
    """Deaths (residence × sex × age in years) and births (residence × sex) per year, through the public
    API into ``events_dir`` as parquet of raw codes; a year already collected is not fetched again."""
    import warnings

    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    import pegasus_data as pg

    out = Path(events_dir)
    out.mkdir(parents=True, exist_ok=True)
    for y in years:
        for name, dataset, event, by in (("deaths", "SIM.DO", "death", ["CODMUNRES", "SEXO", "IDADE_anos"]),
                                         ("births", "SINASC-DN", "birth", ["CODMUNRES", "SEXO"])):
            f = out / f"{name}_{y}.parquet"
            if f.exists():
                continue
            t0 = time.time()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tab = pg.count_events(dataset, event, period=y, geography="BR", by=by, root=root,
                                      allow_partial=False, max_download=8 * 1024**3)
            tab = pa.table({c: pc.cast(tab[c], pa.string()) for c in by} | {"events": tab["events"]})
            tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")     # whole or absent: a truncated file passed `f.exists()` for good
            pq.write_table(tab, tmp)
            tmp.replace(f)
            log(f"{name} {y}: {tab.num_rows} rows, {pc.sum(tab['events']).as_py()} events, {time.time() - t0:.0f}s")


#: SIM and SINASC of 1991-1998 write the city of Rio de Janeiro as 3345xxx (its administrative regions; about 50,000 deaths a
#: year, and 330455 itself only 700-1,500), and from 1999 as 330455 (49,979 deaths).
LEGACY_CODES = {"3345": 330455}


def _place(codes: list[str | None], keys: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """Index of each residence code's first six digits among the sorted municipality ``keys`` (-1: not a current municipality)."""
    c6 = np.array([LEGACY_CODES.get(c[:4], int(c[:6])) if c and c[:6].isdigit() else -1 for c in codes])
    pos = np.clip(np.searchsorted(keys, c6), 0, len(keys) - 1)
    return np.where(keys[pos] == c6, targets[pos], -1)


def load_events(events_dir: str | Path, years: list[int], places: PlaceIndex, by: str = "unit") -> dict[str, Any]:
    """Deaths ``[Y, n, 2, A]`` and births ``[Y, n, 2]`` per year, with what could not be placed counted, not dropped.

    Deaths of unknown sex or age are spread over the known cells of the same unit and year, in proportion
    (the totals are kept; the allocation is a documented choice); an event whose residence is not a current
    municipality is reported as unplaced."""
    import pyarrow.parquet as pq

    n = places.n_units if by == "unit" else places.n_entities
    index = places.unit_of if by == "unit" else places.entity_of
    order = sorted(index, key=lambda m: int(str(m)[:6]))
    keys = np.array([int(str(m)[:6]) for m in order])
    targets = np.array([index[m] for m in order])
    sex_code = {"1": 0, "M": 0, "2": 1, "F": 1}
    deaths = np.zeros((len(years), n, 2, A))
    births = np.zeros((len(years), n, 2))
    report: dict[str, dict[str, int | None]] = {}
    for k, y in enumerate(years):
        t = pq.read_table(Path(events_dir) / f"deaths_{y}.parquet")
        i = _place(t["CODMUNRES"].to_pylist(), keys, targets)
        sx = np.array([sex_code.get((s or "").strip().upper(), -1) for s in t["SEXO"].to_pylist()])
        ag = np.array([-1.0 if a is None else float(a) for a in t["IDADE_anos"].to_pylist()])
        age = np.where(ag >= 0, np.minimum(np.floor(ag), A - 1), -1).astype(int)
        e = np.array(t["events"].to_pylist(), dtype=float)
        placed = i >= 0
        rep: dict[str, int | None] = {"deaths_total": int(e.sum()), "deaths_unplaced": int(e[~placed].sum()),
               "deaths_sex_unknown": int(e[placed & (sx < 0)].sum()), "deaths_age_unknown": int(e[placed & (age < 0)].sum())}
        full = placed & (sx >= 0) & (age >= 0)
        np.add.at(deaths[k], (i[full], sx[full], age[full]), e[full])
        known = deaths[k].copy()
        m = placed & (sx >= 0) & (age < 0)                 # unknown age: over that sex's ages in the unit
        unk = np.zeros((n, 2))
        np.add.at(unk, (i[m], sx[m]), e[m])
        for s in range(2):
            tot = known[:, s].sum(1)
            share = np.divide(known[:, s], tot[:, None], out=np.full((n, A), 1 / A), where=tot[:, None] > 0)
            deaths[k, :, s] += unk[:, s, None] * share
        m = placed & (sx < 0) & (age >= 0)                  # unknown sex: over the sexes at that age
        unk = np.zeros((n, A))
        np.add.at(unk, (i[m], age[m]), e[m])
        tot = known.sum(1)
        for s in range(2):
            share = np.divide(known[:, s], tot, out=np.full((n, A), 0.5), where=tot > 0)
            deaths[k, :, s] += unk * share
        m = placed & (sx < 0) & (age < 0)                   # unknown both: over the unit's cells
        unk_cells = np.zeros(n)
        np.add.at(unk_cells, i[m], e[m])
        tot = known.sum((1, 2))
        share = np.divide(known, tot[:, None, None], out=np.full((n, 2, A), 1 / (2 * A)), where=tot[:, None, None] > 0)
        deaths[k] += unk_cells[:, None, None] * share
        if not (Path(events_dir) / f"births_{y}.parquet").exists():      # before SINASC (1994): no births, said so
            report[str(y)] = rep | {"births_total": None}
            continue
        t = pq.read_table(Path(events_dir) / f"births_{y}.parquet")
        i = _place(t["CODMUNRES"].to_pylist(), keys, targets)
        sx = np.array([sex_code.get((s or "").strip().upper(), -1) for s in t["SEXO"].to_pylist()])
        e = np.array(t["events"].to_pylist(), dtype=float)
        placed = i >= 0
        rep |= {"births_total": int(e.sum()), "births_unplaced": int(e[~placed].sum()),
                "births_sex_unknown": int(e[placed & (sx < 0)].sum())}
        np.add.at(births[k], (i[placed & (sx >= 0)], sx[placed & (sx >= 0)]), e[placed & (sx >= 0)])
        known = births[k].copy()
        unk_births = np.zeros(n)
        m = placed & (sx < 0)
        np.add.at(unk_births, i[m], e[m])
        tot = known.sum(1)
        births[k] += unk[:, None] * np.divide(known, tot[:, None], out=np.full((n, 2), 0.5), where=tot[:, None] > 0)
        report[str(y)] = rep
    return {"deaths": deaths, "births": births, "report": report, "years": years}


# ------------------------------------------------------------------------------- the account itself

def step_terms(N: np.ndarray, D: np.ndarray, B: np.ndarray | None):
    """One step's pieces. ``dr`` is each starting age's share of the step's deaths (Lexis), ``dr0`` the newborns'."""
    dr = np.zeros_like(N)
    dr[..., :A - 2] = 0.5 * (D[..., :A - 2] + D[..., 1:A - 1])
    dr[..., A - 2] = 0.5 * D[..., A - 2]
    dr[..., A - 1] = D[..., A - 1]
    return dr, 0.5 * D[..., 0]


def advance(N, D, B, mig=None):
    """One step: ``N`` at the start (…, A) to the end; ``mig`` is the annual net migration rate by starting age."""
    dr, dr0 = step_terms(N, D, B)
    surv = N - dr
    if mig is not None:
        surv = surv + N * mig
    nxt = np.zeros_like(N)
    nxt[..., 1:A] = surv[..., 0:A - 1]
    nxt[..., A - 1] += surv[..., A - 1]
    nxt[..., 0] = B - dr0
    return nxt


def step_events(deaths, births, k, weights=(W_FIRST, W_SECOND)):
    return weights[0] * deaths[k] + weights[1] * deaths[k + 1], weights[0] * births[k] + weights[1] * births[k + 1]


def run_account(N0, deaths, births, steps, mig=None, kappa=None, lam=None, keep_path=False):
    """Project from the starting census through ``steps`` steps.

    ``mig`` is the annual net migration rate by starting age, (n,2,A), or a callable (k, N) -> rates;
    ``kappa`` (steps,n,2) and ``lam`` (n,2) are the shares of births and of deaths the systems did not register."""
    N = N0.copy()
    path = [N]
    for k in range(steps):
        D, B = step_events(deaths, births, k)
        if lam is not None:
            D = D * (1 + lam)[:, :, None]
        if kappa is not None:
            B = B * (1 + kappa[k])
        m = mig(k, N) if callable(mig) else mig
        N = advance(N, D, B, m)
        path.append(N)
    return (N, path) if keep_path else N


# ------------------------------------------------------------------------------------------ coverage

BANDS = np.minimum(np.arange(A) // 5, 16)
BAND_LABELS = [f"{5 * g}-{5 * g + 4}" for g in range(16)] + ["80+"]


def to_bands(x: np.ndarray) -> np.ndarray:
    """(…, A) single ages to (…, 17) five-year bands (the last open at 80)."""
    return np.stack([x[..., g == BANDS].sum(-1) for g in range(17)], axis=-1)


def reconciled_coverage(population_root: str | Path, year: int, census: np.ndarray, state_of: np.ndarray) -> np.ndarray:
    """Coverage factors of a census as IBGE's reconciliation implies them: POPSVS / raw count, by state × sex × band,
    expanded to single ages (n, 2, A) for units whose state is ``state_of``. The reconciliation was made with the 2022
    PES, so an account that uses these for 2000 and 2010 is a *sensitivity*, not a hold-out; and POPSVS is modelled,
    not observed."""
    import pegasus_data as pg

    t = pg.load_population(series="POPSVS", years=[year], by=("municipality", "year", "sex", "age"), root=population_root)
    states = sorted(set(int(u) for u in state_of))
    index = {u: i for i, u in enumerate(states)}
    svs = np.zeros((len(states), 2, 17))
    for m, s, a, n in zip(t["municipality"].to_pylist(), t["sex"].to_pylist(), t["age"].to_pylist(),
                          t["population"].to_pylist(), strict=True):
        svs[index[int(str(m)[:2])], int(s) - 1, BANDS[min(int(a), A - 1)]] += n
    raw = np.zeros_like(svs)
    cb = to_bands(census)
    for i, u in enumerate(state_of):
        raw[index[int(u)]] += cb[i]
    g = svs / raw
    return g[[index[int(u)] for u in state_of]][:, :, BANDS]


def pes_coverage(raw_entity: np.ndarray, entity_state: np.ndarray) -> np.ndarray:
    """Coverage factors (corrected / raw) of the 2022 Census by entity × sex × age, from IBGE's PES margins raked onto
    cells (``sources.pes.corrected_census``), applied to the single ages of each band in proportion."""
    from .sources.pes import corrected_census

    rb = to_bands(raw_entity)
    corrected = corrected_census(rb, entity_state)
    return (corrected / np.maximum(rb, 1e-9))[:, :, BANDS]




# ======================================================================================= the model

#: Five-year age groups at a lag's closing census whose cohort net migration is a regressor: ages 10-24, 25-54, 55-69.
LAG_GROUPS = {"young": (2, 3, 4), "adult": (5, 6, 7, 8, 9, 10), "old": (11, 12, 13)}
#: Columns of the total's design matrix, in order (all but the last two are the previous decade's cohort net migration).
FEATURES = ("adult", "young", "old", "state", "micro", "urb", "lgdp")
#: A census count's variance is ``CENSUS_NOISE · N`` (v1's fit); it sets how far an area's own rate is shrunk.
CENSUS_NOISE = 0.95
#: The part of the level the account cannot know: how complete the base census was (IBGE's reconciliation puts 2010 at
#: 2.2% short), as a log sd common to every cell, plus a drift of the national total per year of horizon (the two
#: periods' national truth/vital deviations were +0.2% over 10 years and +1.4% over 12).
NATIONAL_SD = 0.02
NATIONAL_DRIFT = 0.0012
SIZE_CUTS = (5_000, 20_000, 100_000, 500_000)
LEVELS = (0.8, 0.95)
#: The deviation of the truth from the vital account is a random walk of drift ``h · ŷ``: its spread at horizon ``h`` is
#: ``s·√h`` (``s`` per √year), and inside an anchored period of ``T`` years the path wanders from the straight line
#: between its censuses as a Brownian bridge, variance ``TIMING_VARIANCE · s²·T·κ(1−κ)``. The 2007 Contagem measured
#: 0.73-0.91 in the size classes below 20,000 (1 is the bridge) and a spread at 6.7 years 0.78-0.80 of that at 10 (√ law:
#: 0.82; a linear law: 0.67).
TIMING_VARIANCE = 1.0
_SEX_CODE = {"1": 0, "M": 0, "2": 1, "F": 1}
_AGE_GROUP_IDS = (1140, 1141, 1142, 1143, 1144, 1145, 1146, 1147, 1148, 1149, 1150, 1151, 1152, 1153, 1154, 1155, 2503)


# --------------------------------------------------------------------------- the previous decade's migration

def lag_series(root: str | Path, places: Places) -> tuple[dict[int, np.ndarray], dict[int, int], int]:
    """SIDRA table 200 (census population by sex × five-year group) for 1991, 2000 and 2010, summed over the
    1991-2010 comparable areas (IPEA's AMC, extended to the five post-2010 creations by their parents). Returns
    ``{year: (areas, 2, 17)}``, ``{municipality: area index}`` and the number of areas. A municipality not yet created is
    a gap and contributes nothing; its comparable area holds its parent's count. Fetch the table first: ``pegasus-data sidra
    fetch 200 --variables 93 --periods 1991,2000,2010 --level N6 --class 2=4,5 --class 1=0 --class 58=1140,…,1155,2503``."""
    import duckdb

    import pegasus_data as pg

    path = Path(root) / "lake" / "sidra" / "facts" / "table=200" / "*.parquet"
    rows = duckdb.connect().execute(
        f"select cast(locality as bigint), cast(period as int), c2, c58, value from read_parquet('{path.as_posix()}') where value is not null"
    ).fetchall()
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    every = sorted({r[0] for r in rows} | set(places.municipalities))
    area: dict[int, str] = {}
    for m in every:
        a = pg.memberships(str(m)).get("comparable_area_1991_2010")
        area[m] = f"amc:{a.member_code}" if a else f"new:{m}"
        find(area[m])
    for child, parents in POST_2010_CREATIONS.items():
        if child in area:
            for p in parents:
                parent[find(area[child])] = find(area[p])
    roots = sorted({find(area[m]) for m in every})
    index = {r: i for i, r in enumerate(roots)}
    area_of = {m: index[find(area[m])] for m in every}
    gid = {g: i for i, g in enumerate(_AGE_GROUP_IDS)}
    out = {y: np.zeros((len(roots), 2, 17)) for y in (1991, 2000, 2010)}
    for m, y, sex, g, v in rows:
        out[y][area_of[m], 0 if sex == 4 else 1, gid[g]] += v
    return out, area_of, len(roots)


def mortality_rates(events_dir: str | Path, year: int, population: np.ndarray) -> np.ndarray:
    """National death rates by sex × five-year group (2, 17): SIM deaths of ``year`` over ``population`` (2, 17)."""
    import pyarrow.parquet as pq

    t = pq.read_table(Path(events_dir) / f"deaths_{year}.parquet", columns=["SEXO", "IDADE_anos", "events"])
    deaths = np.zeros((2, 17))
    for s, a, e in zip(t["SEXO"].to_pylist(), t["IDADE_anos"].to_pylist(), t["events"].to_pylist(), strict=True):
        s = _SEX_CODE.get((s or "").strip().upper())
        if s is not None and a is not None:
            deaths[s, min(int(float(a)) // 5, 16)] += e
    return deaths / np.maximum(population, 1)


def _survival(m: np.ndarray, sex: int, age0: float, length: float) -> float:
    mid = np.arange(17) * 5 + 2.5
    x = np.arange(0, length, 0.25) + age0 + 0.125
    return float(np.exp(-np.exp(np.interp(x, mid, np.log(np.maximum(m[sex], 1e-6)))).sum() * 0.25))


def cohort_rates(c0: np.ndarray, c1: np.ndarray, length: float, m: np.ndarray, groups) -> tuple[np.ndarray, np.ndarray]:
    """Net migration of the cohorts that close ``length`` years later in five-year groups ``groups`` (survival-ratio):
    observed minus expected survivors, and expected survivors, summed over sex and groups, per area."""
    n = np.zeros(c0.shape[0])
    d = np.zeros(c0.shape[0])
    for s in range(2):
        for h in groups:
            lo, hi = 5 * h - length, 5 * h + 5 - length
            expected = np.zeros(c0.shape[0])
            for g in range(17):
                glo, ghi = 5 * g, (5 * g + 5 if g < 16 else 200)
                overlap = max(0.0, min(hi, ghi) - max(lo, glo)) / 5
                if overlap > 0:
                    expected += overlap * c0[:, s, g]
            expected = expected * _survival(m, s, 5 * h + 2.5 - length, length)
            n += c1[:, s, h] - expected
            d += expected
    return n, d


def _group_mean(v: np.ndarray, w: np.ndarray, idx: np.ndarray) -> np.ndarray:
    ids, inv = np.unique(idx, return_inverse=True)
    return (np.bincount(inv, v * w) / np.maximum(np.bincount(inv, w), 1e-9))[inv]


def _shrunk(n: np.ndarray, d: np.ndarray):
    """Rate, its national mean and the empirical-Bayes shrinkage of each area's rate toward the mean."""
    r = np.where(d > 0, n / np.maximum(d, 1), 0.0)
    mu = n.sum() / d.sum()
    var = np.average((r - mu) ** 2, weights=d)
    tau2 = max(var - np.average(CENSUS_NOISE / np.maximum(d, 1), weights=d), 1e-6)
    return r, mu, mu + d / (d + CENSUS_NOISE / tau2) * (r - mu)


@dataclass
class Lag:
    """The previous decade's migration signals per area (deviations from the national mean, per year of the lag)."""

    own: dict[str, np.ndarray]                      # young / adult / old: the area's shrunk rate
    state: np.ndarray                               # the state's mean adult rate
    micro: np.ndarray                               # the micro-region's mean adult rate less its state's
    band: dict[int, tuple[np.ndarray, np.ndarray]]  # five-year group -> (area's shrunk rate, state mean)


def lag_features(c0: np.ndarray, c1: np.ndarray, length: float, m: np.ndarray, state: np.ndarray, micro: np.ndarray) -> Lag:
    """``c0``, ``c1``: (areas, 2, 17) counts ``length`` years apart; ``state``, ``micro``: the area's codes."""
    own: dict[str, np.ndarray] = {}
    out_state = out_micro = None
    for name, hs in LAG_GROUPS.items():
        n, d = cohort_rates(c0, c1, length, m, hs)
        r, mu, rs = _shrunk(n, d)
        own[name] = (rs - mu) / length
        if name == "adult":
            sm = _group_mean(r, d, state)
            out_state, out_micro = (sm - mu) / length, (_group_mean(r, d, micro) - sm) / length
    band = {}
    for h in range(2, 14):
        n, d = cohort_rates(c0, c1, length, m, (h,))
        r, mu, rs = _shrunk(n, d)
        band[h] = ((rs - mu) / length, (_group_mean(r, d, state) - mu) / length)
    return Lag(own, out_state, out_micro, band)  # type: ignore[arg-type]


def static_covariates(root: str | Path, members: list[list[int]], census_year: int, gdp_year: int, population: np.ndarray):
    """Urban share at the census opening a period (SIDRA 202) and log GDP per head (5938, R$ 1000) of ``gdp_year`` over
    ``population``, per row; both centred on their median. A row with no value takes the median."""
    import duckdb

    base = Path(root) / "lake" / "sidra" / "facts"
    con = duckdb.connect()
    pop = {(m, c1): v for m, c1, v in con.execute(
        f"select cast(locality as bigint), c1, value from read_parquet('{(base / 'table=202' / '*.parquet').as_posix()}') "
        f"where c2 = 0 and period = '{census_year}' and value is not null").fetchall()}
    gdp = dict(con.execute(
        f"select cast(locality as bigint), value from read_parquet('{(base / 'table=5938' / '*.parquet').as_posix()}', union_by_name=true) "
        f"where variable = 37 and period = '{gdp_year}' and value is not null").fetchall())
    urb = np.full(len(members), np.nan)
    lg = np.full(len(members), np.nan)
    for i, mem in enumerate(members):
        tot = sum(pop.get((int(m), 0), 0.0) for m in mem)
        if tot > 0:
            urb[i] = sum(pop.get((int(m), 1), 0.0) for m in mem) / tot
        g = sum(gdp.get(int(m), 0.0) for m in mem)
        if g > 0 and population[i] > 0:
            lg[i] = np.log(g * 1000 / population[i])
    out = []
    for v in (urb, lg):
        v = np.where(np.isfinite(v), v, np.nanmedian(v))
        out.append(v - np.median(v))
    return out[0], out[1]


# ---------------------------------------------------------------------------------------------- a period

@dataclass
class Period:
    """One period's rows: where the vital projection ended, where the census did (``truth``, absent for a projection)
    and the regressors known when it opened. ``vital`` and ``truth`` are (rows, 2, 17); ``T`` is the horizon in years."""

    name: str
    T: float
    state: np.ndarray
    micro: np.ndarray
    size: np.ndarray
    vital: np.ndarray
    truth: np.ndarray | None
    X: np.ndarray
    band_own: dict[int, np.ndarray]
    band_state: dict[int, np.ndarray]
    members: list[list[int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.region = self.state // 10
        self.sizec = np.digitize(self.size, SIZE_CUTS)
        self.w = 1 / (0.05**2 + 1 / np.sqrt(np.maximum(self.size, 100)))

    @property
    def y(self) -> np.ndarray:
        """log(truth / vital) of the total, per year of the period."""
        return np.log(cast(np.ndarray, self.truth).sum((1, 2)) / np.maximum(self.vital.sum((1, 2)), 1)) / self.T


def make_period(name, T, state, micro, size, vital, truth, lag: Lag, root: np.ndarray, urb, lgdp, members=()) -> Period:
    cols = {**{k: v[root] for k, v in lag.own.items()}, "state": lag.state[root], "micro": lag.micro[root], "urb": urb, "lgdp": lgdp}
    return Period(name, T, state, micro, size, vital, truth, np.stack([cols[f] for f in FEATURES], 1),
                  {h: v[0][root] for h, v in lag.band.items()}, {h: v[1][root] for h, v in lag.band.items()}, list(members))


def _wls(X: np.ndarray, y: np.ndarray, w: np.ndarray, ridge: float = 1e-6) -> np.ndarray:
    W = X.T * w
    return np.linalg.solve(W @ X + ridge * np.eye(X.shape[1]), W @ y)


def _centred(P: Period) -> np.ndarray:
    return P.y - np.average(P.y, weights=P.w)


def _stack(Ps: list[Period], f) -> np.ndarray:
    return np.concatenate([f(P) for P in Ps])


def _loro(P: Period, fit) -> np.ndarray:
    """Leave-one-region-out: ``fit(mask)`` returns a predictor for the rows of the held-out region."""
    out = np.full(P.state.shape, np.nan)
    for g in range(1, 6):
        held = P.region == g
        out[held] = fit(~held)(held)
    return out


def _hold(est: np.ndarray, vital: np.ndarray) -> np.ndarray:
    """Internal migration sums to zero and the level is not knowable: each sex × band keeps the vital projection's national total."""
    return est * (vital.sum(0) / np.maximum(est.sum(0), 1e-9))[None]


@dataclass
class Calibration:
    """Everything fitted on one or two periods: coefficients, spreads and quantiles. Spreads are per √year of horizon."""

    b: np.ndarray                  # total: coefficients of FEATURES on the per-year deviation
    s_total: np.ndarray            # (5,) robust sd of the leave-one-region-out residual by size class
    gm: np.ndarray                 # (6,) region multiplier (index 1..5)
    q_total: dict[float, np.ndarray]
    coef: np.ndarray               # (2, 17, 4) band model: 1, total prediction, own rate, state rate
    s_band: np.ndarray             # (5, 17)
    q_band: dict[float, np.ndarray]
    widened: list[str] = field(default_factory=list)
    periods: tuple[str, ...] = ()


def _spread(r: np.ndarray, sizec: np.ndarray) -> np.ndarray:
    out = np.zeros(5)
    for k in range(5):
        x = r[sizec == k]
        x = x[np.isfinite(x)]
        out[k] = 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) else np.nan
    return out


def _quantiles_of(z: np.ndarray) -> dict[float, np.ndarray]:
    z = z[np.isfinite(z)]
    return {lv: np.quantile(z, [(1 - lv) / 2, 1 - (1 - lv) / 2]) for lv in LEVELS}


def _band_design(P: Period, g: int, yhat: np.ndarray) -> np.ndarray:
    h = int(np.clip(g, 2, 13))
    return np.stack([np.ones(len(yhat)), yhat, P.band_own[h], P.band_state[h]], 1)


def _fit_cells(Ps: list[Period], yhats: list[np.ndarray], mask: list[np.ndarray] | None = None) -> np.ndarray:
    """Per sex × band: weighted regression of log(truth/vital)/T on the total's prediction and the band's own lagged rates."""
    coef = np.zeros((2, 17, 4))
    for x in range(2):
        for g in range(17):
            Xs, ys, ws = [], [], []
            for i, (P, yh) in enumerate(zip(Ps, yhats, strict=True)):
                v, t = P.vital[:, x, g], cast(np.ndarray, P.truth)[:, x, g]
                ok = (v > 20) & (t > 20) & (True if mask is None else mask[i])
                Xs.append(_band_design(P, g, yh)[ok])
                ys.append(np.log(t[ok] / v[ok]) / P.T)
                ws.append(v[ok])
            coef[x, g] = _wls(np.concatenate(Xs), np.concatenate(ys), np.concatenate(ws), ridge=1e-4)
    return coef


def fit_calibration(Ps: list[Period]) -> Calibration:
    """Fit the total and band models on ``Ps`` (one period to transfer to the other, or both for the product)."""
    Xs = [P.X for P in Ps]
    ys = [_centred(P) for P in Ps]
    b = _wls(np.concatenate(Xs), np.concatenate(ys), np.concatenate([P.w for P in Ps]))
    yhat_in, resid, s_each = [], [], []
    for P, y in zip(Ps, ys, strict=True):
        pred = _loro(P, lambda tr, P=P, y=y: (lambda held, c=_wls(P.X[tr], y[tr], P.w[tr]): P.X[held] @ c))
        yhat_in.append(pred)
        r_rt = (y - pred) * np.sqrt(P.T)               # per-year deviation × √T: the spread per √year
        resid.append(r_rt)
        s_each.append(_spread(r_rt, P.sizec))
    s_total = np.max(s_each, axis=0)
    gm = np.ones(6)
    z = [r / s_total[P.sizec] for P, r in zip(Ps, resid, strict=True)]
    for g in range(1, 6):
        zz = np.concatenate([zi[P.region == g] for P, zi in zip(Ps, z, strict=True)])
        gm[g] = 1.4826 * np.median(np.abs(zz - np.median(zz)))
    q_total = _quantiles_of(np.concatenate([zi / gm[P.region] for P, zi in zip(Ps, z, strict=True)]))
    coef = _fit_cells(Ps, yhat_in)
    # band residuals out of region, spreads by size × band (the larger of the periods'), shared quantiles
    R = []
    for P, yh in zip(Ps, yhat_in, strict=True):
        r = np.full(P.vital.shape, np.nan)
        for g in range(1, 6):
            held = P.region == g
            c = _fit_cells([P], [yh], [~held])
            for x in range(2):
                for a in range(17):
                    v, t = P.vital[:, x, a], cast(np.ndarray, P.truth)[:, x, a]
                    ok = held & (v > 20) & (t > 20)
                    r[ok, x, a] = (np.log(t[ok] / v[ok]) / P.T - _band_design(P, a, yh)[ok] @ c[x, a]) * np.sqrt(P.T)
        R.append(r)
    s_band = np.zeros((5, 17))
    for a in range(17):
        s_band[:, a] = np.max([_spread(r[:, :, a].ravel(), np.repeat(P.sizec, 2)) for P, r in zip(Ps, R, strict=True)], axis=0)
    zb = np.concatenate([(r[:, :, a] / s_band[P.sizec, a][:, None]).ravel() for P, r in zip(Ps, R, strict=True) for a in range(17)])
    return Calibration(b, s_total, gm, q_total, coef, s_band, _quantiles_of(zb), periods=tuple(P.name for P in Ps))


def predict(P: Period, cal: Calibration, h: float | None = None):
    """The total's and the bands' centres at horizon ``h`` (default the period's own): log-deviation per year ``yhat``
    (national level held), the (rows, 2, 17) population and its total. Nothing of ``truth`` is read."""
    h = P.T if h is None else h
    z = P.X @ cal.b
    yhat = z + np.log(P.vital.sum() / (P.vital.sum((1, 2)) * np.exp(h * z)).sum()) / h
    total = P.vital.sum((1, 2)) * np.exp(h * yhat)
    bands = np.zeros_like(P.vital)
    for x in range(2):
        for g in range(17):
            bands[:, x, g] = P.vital[:, x, g] * np.exp(h * (_band_design(P, g, z) @ cal.coef[x, g]))
    bands = _hold(bands, P.vital)
    return yhat, total, bands


def interval(P: Period, cal: Calibration, centre: np.ndarray, h: float, level: float, *, total: bool,
             timing: float | None = None, band_region: bool = False):
    """Log-scale interval of cells (``total``: rows; otherwise rows × 2 × 17) at horizon ``h`` years from the opening
    census: sd² = national² + spread² · h (a random walk), the spread by size class (and, for the total, a region
    multiplier). Inside an anchored period ``timing`` is the share ``κ = k/T`` already travelled and the horizon term
    is the bridge's, ``TIMING_VARIANCE · spread² · T · κ(1−κ)``."""
    nat = np.sqrt(NATIONAL_SD**2 + (NATIONAL_DRIFT * h) ** 2)
    if total:
        s, q = cal.s_total[P.sizec] * cal.gm[P.region], cal.q_total[level]
    else:
        s, q = cal.s_band[P.sizec][:, None, :], cal.q_band[level]
        if band_region:
            s = s * cal.gm[P.region][:, None, None]
    var = s**2 * h if timing is None else TIMING_VARIANCE * s**2 * P.T * timing * (1 - timing)
    sd = np.sqrt(nat**2 + var)
    base = np.log(np.maximum(centre, 1e-9))
    return base + q[0] * sd, base + q[1] * sd


# ---------------------------------------------------------------------------------------------- the inputs

@dataclass
class Inputs:
    """Everything the model and the product read, assembled once from the lake and the events."""

    places: Places
    A: Period                    # 2000 -> 2010 on comparable areas (the regression's rows)
    B: Period                    # 2010 -> 2022 on entities
    P22: Period                  # the projection's rows: entities opened by the 2022 census, one step ahead
    path_a: np.ndarray           # (11, units, 2, A) vital account from the reconciled 2000 census
    close_a: np.ndarray          # the reconciled 2010 census, (units, 2, A)
    path_b: np.ndarray           # (13, entities, 2, A) vital account from the reconciled 2010 census
    close_b: np.ndarray          # the PES-corrected 2022 census, (entities, 2, A)
    start22: np.ndarray          # the PES-corrected 2022 census (the projection's opening)
    m_rate: np.ndarray           # national death rates used for the lag (2000)
    vit22: np.ndarray            # the vital account one step from the PES-corrected 2022 census, (entities, 2, A) single ages


def assemble(root: str | Path, population_root: str | Path, events_dir: str | Path, log=print) -> Inputs:
    """Load the censuses, bring them to coverage, run the vital account and build the three periods' rows.

    Coverage: 2022 by IBGE's PES (published margins, raked onto cells), 2000 and 2010 by IBGE's reconciliation
    (POPSVS / raw; a sensitivity, since it was made with the PES). The regression's period B opens on the *raw* 2010
    census (the protocol that was scored); the account's interior opens on the reconciled one."""
    import pyarrow.parquet as pq

    t22 = pq.read_table(Path(root) / "lake" / "population" / "CENSO" / "censo_2022.parquet", columns=["municipality"])
    places = build_places(sorted(set(int(m) for m in t22["municipality"].to_pylist())))
    members_u: list[list[int]] = [[] for _ in range(places.n_units)]
    for m in places.municipalities:
        members_u[places.unit_of[m]].append(m)
    ent_state = np.array([int(str(m[0])[:2]) for m in places.entity_members])
    ent_micro = places.unit_micro[places.entity_unit]
    log("censuses and coverage")
    c00u, c10u = load_census(root, 2000, places), load_census(root, 2010, places)
    c10e, c22e = load_census(root, 2010, places, "entity"), load_census(root, 2022, places, "entity")
    c00r = c00u * reconciled_coverage(population_root, 2000, c00u, places.unit_uf)
    c10ur = c10u * reconciled_coverage(population_root, 2010, c10u, places.unit_uf)
    c10er = c10e * reconciled_coverage(population_root, 2010, c10e, ent_state)
    c22t = c22e * pes_coverage(c22e, ent_state)
    log("events")
    ev0 = load_events(events_dir, list(range(2000, 2011)), places, "unit")
    ev1 = load_events(events_dir, list(range(2010, 2024)), places, "entity")
    log("previous decades' migration (SIDRA 200)")
    S, area_of, n_areas = lag_series(root, places)
    state_a, micro_a = np.zeros(n_areas, int), np.zeros(n_areas, int)
    for m in places.municipalities:
        state_a[area_of[m]], micro_a[area_of[m]] = int(str(m)[:2]), places.unit_micro[places.unit_of[m]]
    m00 = mortality_rates(events_dir, 2000, S[2000].sum(0))
    lag_a = lag_features(S[1991], S[2000], 8.92, m00, state_a, micro_a)
    lag_b = lag_features(S[2000], S[2010], 10.0, m00, state_a, micro_a)
    # period A: units
    path_a = run_account(c00r, ev0["deaths"], ev0["births"], 10, keep_path=True)[1]
    root_a = np.array([area_of[mem[0]] for mem in members_u])
    urb, lg = static_covariates(root, members_u, 2000, 2002, c00u.sum((1, 2)))
    A_ = make_period("A", 10, places.unit_uf, places.unit_micro, c00r.sum((1, 2)), to_bands(path_a[-1]), to_bands(c10ur),
                     lag_a, root_a, urb, lg, members_u)
    # period B: entities, opened on the raw 2010 census
    vit_b = run_account(c10e, ev1["deaths"], ev1["births"], 12)
    root_b = np.array([area_of[mem[0]] for mem in places.entity_members])
    urb, lg = static_covariates(root, places.entity_members, 2010, 2010, c10e.sum((1, 2)))
    B_ = make_period("B", 12, ent_state, ent_micro, c10e.sum((1, 2)), to_bands(vit_b), to_bands(c22t), lag_b, root_b, urb, lg,
                     places.entity_members)
    path_b = run_account(c10er, ev1["deaths"], ev1["births"], 12, keep_path=True)[1]
    # the projection: lag 2010 -> 2022 of the entities themselves (raw counts), one step from the PES-corrected 2022 census
    pop_mid = (to_bands(c10e).sum(0) + to_bands(c22e).sum(0)) / 2
    m16 = mortality_rates(events_dir, 2016, pop_mid)
    E = places.n_entities
    lag_p = lag_features(to_bands(c10e), to_bands(c22e), 12.0, m16, ent_state, ent_micro)
    urb, lg = static_covariates(root, places.entity_members, 2010, 2021, c22e.sum((1, 2)))
    vit22 = run_account(c22t, ev1["deaths"][12:], ev1["births"][12:], 1)
    P22 = make_period("2022+", 1, ent_state, ent_micro, c22t.sum((1, 2)), to_bands(vit22), None, lag_p, np.arange(E), urb, lg,
                      places.entity_members)
    return Inputs(places, A_, B_, P22, np.array(path_a), c10ur, np.array(path_b), c22t, c22t, m00, vit22)


# ------------------------------------------------------------------------------------------ the product

#: Smoothness of the migration schedule (weight of the second differences against the cohort residuals).
SCHEDULE_SMOOTH = 30.0


def fit_schedule(periods: list[tuple[np.ndarray, np.ndarray, int]], smooth: float = SCHEDULE_SMOOTH) -> np.ndarray:
    """The age schedule of the net migration (and coverage) that the censuses leave unexplained: ``w[sex, size class, age]``,
    a yearly rate by age at the start of the year (0..79; 80+ is 0), the same for every place of a size class.

    ``periods`` are ``(vital path, closing census, steps)`` triples (the paths are (steps+1, n, 2, A)). The cohort that
    ends a period at age ``a`` has the residual ``closing - vital`` there; it is the sum of the yearly rates over the ages
    the cohort had along the way, ``r(a) = sum_{x = max(0, a-steps)}^{a-1} w(x)``, solved with a second-difference penalty
    (signed: a loss at 15-27, a gain after). Pooled per size class (``SIZE_CUTS`` of the closing population) and averaged
    over the periods. In every decade of 1991-2022 the residual sits at ages 15-27 (small places lose 2-4% of a cohort a
    year at 18-22): it is not spread evenly through the years."""
    out = np.zeros((2, len(SIZE_CUTS) + 1, A))
    for path, close, steps in periods:
        cls = np.digitize(close.sum((1, 2)), SIZE_CUTS)
        M = np.zeros((A - 2, A - 1))
        for a in range(1, A - 1):
            M[a - 1, max(0, a - steps):a] = 1.0
        D = np.diff(np.eye(A - 1), 2, axis=0)
        R = close - path[-1]
        for sx in (0, 1):
            for c in range(len(SIZE_CUTS) + 1):
                m = cls == c
                if not m.any():
                    continue
                r = R[m][:, sx, 1:A - 1].sum(0) / np.maximum(path[-1][m][:, sx, 1:A - 1].sum(0), 1.0)
                w = np.linalg.lstsq(np.vstack([M, np.sqrt(smooth) * D]), np.concatenate([r, np.zeros(len(D))]), rcond=None)[0]
                out[sx, c, :A - 1] += w / len(periods)
    return out


def migration_schedule(inp: Inputs) -> np.ndarray:
    """``fit_schedule`` on the two intercensal periods of ``inp`` (2000-2010 and 2010-2022)."""
    return fit_schedule([(inp.path_a, inp.close_a, 10), (inp.path_b, inp.close_b, 12)])


def schedule_rates(schedule: np.ndarray, size: np.ndarray) -> np.ndarray:
    """The schedule of each place, (n, 2, A), from the place's size class."""
    return schedule[:, np.digitize(size, SIZE_CUTS)].transpose(1, 0, 2)


def distribute_residual(path: np.ndarray, closing: np.ndarray, rates: np.ndarray | None = None) -> np.ndarray:
    """Carry the closing census's departure from a vital account along the cohorts through the period.

    ``path`` (T+1, n, 2, A) is the vital account from the opening census and ``closing`` the census that ends the
    period. The residual of each age at the end is the net migration (and coverage) of the cohort that reached it. With
    ``rates`` (n, 2, A; ``schedule_rates``) the cohort receives, each year, the schedule's rate at its age times its size;
    what the schedule does not explain is given evenly through the period (from the opening census, or from birth), so
    the path leaves the opening census untouched and arrives exactly on the closing one. Without ``rates`` all of it is
    given evenly. The residual of the open 80+ stays at 80+ and is even. A cell that would go negative is set to zero."""
    T = path.shape[0] - 1
    R = closing - path[-1]
    out = path.copy()
    for a_end in range(A):
        k0 = max(0, T - a_end)
        P = np.zeros((T + 1,) + R.shape[:2])
        if rates is not None and a_end < A - 1:
            for j in range(k0, T):
                x = a_end - (T - j)
                P[j + 1] = P[j] + rates[..., x] * path[j][..., x]
        rest = R[..., a_end] - P[T]
        for k in range(k0, T + 1):
            share = k / T if k0 == 0 else (k - k0 + 1) / (T - k0 + 1)
            pos = A - 1 if a_end == A - 1 else min(a_end - (T - k), A - 1)
            out[k][..., pos] += P[k] + share * rest
    return np.maximum(out, 0)


def band_coverage(P: Period, cal: Calibration, bands: np.ndarray, level: float, scale: np.ndarray | None = None,
                  band_region: bool = False) -> np.ndarray:
    """Share of cells (> 20 people, sex × area) of each of the 17 bands that the interval at ``level`` covers, per band."""
    c2 = cal if scale is None else Calibration(cal.b, cal.s_total, cal.gm, cal.q_total, cal.coef,
                                               cal.s_band * scale[None, :], cal.q_band, cal.widened, cal.periods)
    lo, hi = interval(P, c2, bands, P.T, level, total=False, band_region=band_region)
    truth = cast(np.ndarray, P.truth)
    t = np.log(np.maximum(truth, 1e-9))
    ok = (P.vital > 20) & (truth > 20)
    return np.array([float(((t >= lo) & (t <= hi))[:, :, g][ok[:, :, g]].mean()) for g in range(17)])


def widen_to_nominal(cal: Calibration, Ps: list[Period], tol: float = 0.0) -> Calibration:
    """Scale each band's spread (all size classes together, never below 1) until the 80% and 95% intervals cover at
    least their nominal share of that band's cells in every period of ``Ps``. This is in-sample for those periods; the
    bands it moves are the ones the periods disagree about and are listed in ``widened`` with their factor."""
    centres = [predict(P, cal)[2] for P in Ps]
    scale = np.ones(17)
    for g in range(17):
        for s in np.arange(1.0, 3.01, 0.02):
            sc = np.ones(17)
            sc[g] = s
            if all(band_coverage(P, cal, c, lv, sc)[g] >= lv - tol for P, c in zip(Ps, centres, strict=True) for lv in LEVELS):
                scale[g] = s
                break
        else:
            scale[g] = 3.0
    widened = [f"{BAND_LABELS[g]} x{scale[g]:.2f}" for g in range(17) if scale[g] > 1.0]
    return Calibration(cal.b, cal.s_total, cal.gm, cal.q_total, cal.coef, cal.s_band * scale[None, :], cal.q_band, widened,
                       cal.periods)


def birth_registration(inp: Inputs) -> list[dict[str, Any]]:
    """SINASC completeness by state from the cohorts a census counted: the vital account's children against the census.

    A child aged 0-4 (or 5-9) at a closing census was born inside the period, so the vital account (registered births,
    registered deaths) holds exactly that cohort, and the closing (coverage-corrected) census counts it. Their ratio per
    state is the share of births the account saw, net of the census coverage assumed and of the cohort's net migration
    (which is small for children and not separated). Above 1 means the census counted fewer children than were registered
    (a census undercount the coverage assumed did not remove), not registration. The 5-9 cohort carries five more years of
    migration than the 0-4 one."""
    rows: list[dict[str, Any]] = []
    blocks = [("2010", "reconciled 2000 and 2010", inp.path_a[-1], inp.close_a, inp.places.unit_uf, 2005, 2000),
              ("2022", "reconciled 2010 and PES 2022", inp.path_b[-1], inp.close_b,
               np.array([int(str(m[0])[:2]) for m in inp.places.entity_members]), 2017, 2012)]
    for census, basis, vital, close, state, y04, y59 in blocks:
        v, c = to_bands(vital), to_bands(close)
        for g, y0 in ((0, y04), (1, y59)):
            for u in sorted(set(int(s) for s in state)):
                sel = state == u
                ratio = float(v[sel, :, g].sum() / c[sel, :, g].sum())
                rows.append({"uf": u, "system": "SINASC", "period": f"{y0}-{y0 + 4}", "census_basis": basis,
                             "cohort": f"{BAND_LABELS[g]} at the {census} census", "completeness": ratio})
    return rows


def build_registration_completeness(root: str | Path, population_root: str | Path, events_dir: str | Path, *, version: str,
                                    validation: str, log=print) -> dict[str, Any]:
    """Write the ``registration_completeness`` modelled product from ``birth_registration``.

    The 80% interval is the account's 2% census term (``NATIONAL_SD``) joined with the spread between the 0-4 and the 5-9
    cohort of the same census and state (sd of their difference over sqrt 2), which measures what a single cohort's ratio
    carries beyond registration: coverage by age and migration. It is wider than needed where the two cohorts truly
    differ in registration."""
    from types import SimpleNamespace

    import pyarrow as pa

    from . import __version__
    from .modelled import ModelledManifest, write_modelled

    inp = assemble(root, population_root, events_dir, log)
    rows = birth_registration(inp)
    by = {(r["uf"], r["cohort"]): r["completeness"] for r in rows}
    diffs = [v - by[(u, c.replace("0-4", "5-9"))] for (u, c), v in by.items() if c.startswith("0-4")]
    pair_sd = float(np.std(diffs) / np.sqrt(2)) if diffs else 0.0
    sd = float(np.hypot(NATIONAL_SD, pair_sd))
    for r in rows:
        r["completeness_lo"], r["completeness_hi"] = r["completeness"] - 1.2816 * sd, r["completeness"] + 1.2816 * sd
    manifest = ModelledManifest(
        product="registration_completeness", version=version,
        model="vital account's cohorts aged 0-4 and 5-9 at the closing census against the coverage-corrected census, by state; "
              "population_account.py v2",
        estimates={"completeness": ["completeness_lo", "completeness_hi"]},
        inputs={"CENSO 2010, 2022 (raw)": "SIDRA tables 1378, 9514", "SIM.DO deaths and SINASC births 2000-2023": f"pegasus_data {__version__}",
                "PES 2022 net-error margins": "IBGE liv102110 (sources/pes.py)", "population_account": "population-account-2 (same inputs)"},
        validation=validation,
        notes=["Net of the census coverage assumed for the period's censuses: with other coverage, other completeness.",
               "A value above 1 is not registration: the census counted fewer children than the registered births imply.",
               "`period` is the years the cohort was born in (the census date is 1 August; a 0-4 cohort at the 2010 census was born "
               "2005-08 to 2010-07). Births of 2010-2011 and of 2022 are in no cohort. The state's net child migration is not separated.",
               f"Interval: 80%, sd {sd:.4f} = hypot({NATIONAL_SD}, {pair_sd:.4f}), the second the cohort-pair spread (see birth_registration).",
               "SIM (deaths) completeness is not estimated here (see system_completeness)."])
    table = pa.Table.from_pylist(rows)
    out = write_modelled(table, manifest, settings=SimpleNamespace(lake_dir=Path(root) / "lake"))
    return {"path": str(out), "rows": len(rows), "sd": sd, "pair_sd": pair_sd}
