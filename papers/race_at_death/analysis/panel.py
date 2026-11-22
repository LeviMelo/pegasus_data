"""The municipality-year lattice: what the certificate of each municipality's linked infant deaths records each year, beside
what the municipality was that year (composition of its births, wealth, physicians, how its deaths are certified and
recorded), and the two censuses (2010, 2022) as two time points of composition, literacy and urbanisation.
Writes papers/race_at_death/data/panel_mun_year.parquet and data/panel_census.parquet; models.R stage `panel` fits them.

Sources (all held by pegasus_data): the infant linkage (data/infant_linkage_context.parquet); SINASC and SIM lakes by
municipality of residence and year; SIDRA 5938 (GDP, yearly); POPSVS (population, yearly); CNES December registers
(physicians, yearly); census tables 9605 (race), 9542 / 3149 (literacy), 9923 / 202 (urban) for 2010 and 2022.

    python papers/race_at_death/analysis/panel.py      (about two minutes)
"""
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from pegasus_data import load_population
from pegasus_data.config import load_settings
from pegasus_data.fields import load_field

warnings.simplefilter("ignore")
PAPER = Path(__file__).resolve().parents[1]
LAKE = Path(load_settings().lake_dir).as_posix()
YEARS = list(range(2013, 2024))
con = duckdb.connect()
con.execute("PRAGMA disable_progress_bar; SET memory_limit='6GB'")


def yearly(name, years):
    """A field by six-digit municipality and year; only rows whose status is a value."""
    t = load_field(name, years=years).to_pandas()
    t = t[t.status.isin(["value", "ok"])]
    return t.groupby(["municipality", "year"]).value.sum().rename(name)


# ------------------------------------------------------------------ the outcome: linked infant deaths by the mother's declaration and the certificate
L = pd.read_parquet(PAPER / "data" / "infant_linkage_context.parquet", columns=["year", "mun", "linked", "declared", "recorded", "age_days"])
L = L[L.linked & (L.age_days >= 0)]
L["mun"] = L.mun.astype(str).str[:6]
out = []
for key, dec, rec in (("PW", "4", "1"), ("KK", "2", "2"), ("WW", "1", "1"), ("PP", "4", "4")):
    g = L[L.declared == dec].groupby(["mun", "year"])
    out.append(pd.DataFrame({f"n_{key}": g.size(), f"y_{key}": g.recorded.apply(lambda s, r=rec: int((s == r).sum()))}))
Y = pd.concat(out, axis=1).fillna(0).astype(int).reset_index()

# ------------------------------------------------------------------ the municipality each year
SN = f"read_parquet('{LAKE}/SINASC/SINASC_DN_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
births = con.execute(f"""SELECT left(trim(CODMUNRES), 6) mun, CAST(year AS INT) AS "year", count(*) births,
       count(*) FILTER (trim(RACACORMAE) IN ('1','2','3','4','5')) births_race, count(*) FILTER (trim(RACACORMAE) = '1') births_white
       FROM {SN} WHERE year BETWEEN 2013 AND 2023 GROUP BY 1, 2""").df()
SIM = f"read_parquet('{LAKE}/SIM/SIM_DO_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
deaths = con.execute(f"""SELECT left(trim(CODMUNRES), 6) mun, CAST(year AS INT) AS "year", count(*) deaths,
       count(*) FILTER (trim(RACACOR) NOT IN ('1','2','3','4','5') OR RACACOR IS NULL) race_blank_n,
       count(*) FILTER (left(CAUSABAS, 1) NOT IN ('V','W','X','Y')) natural_n,
       count(*) FILTER (left(CAUSABAS, 1) NOT IN ('V','W','X','Y') AND trim(ATESTANTE) = '4') natural_svo_n,
       count(*) FILTER (left(CAUSABAS, 1) IN ('V','W','X','Y')) external_n,
       count(*) FILTER (left(CAUSABAS, 1) IN ('V','W','X','Y') AND trim(ATESTANTE) = '3') external_iml_n,
       count(*) FILTER (trim(LOCOCOR) = '1') hospital_n
       FROM {SIM} WHERE year BETWEEN 2013 AND 2023 GROUP BY 1, 2""").df()
pop = load_population(years=YEARS, by=["municipality"]).to_pandas()
pop = pop.assign(mun=pop.municipality.astype(str).str[:6]).groupby(["mun", "year"]).population.sum().rename("population")
gdp = yearly("gdp", YEARS)
phys = yearly("cnes_physicians_professionals", YEARS)
X = pd.concat([gdp, phys], axis=1)
X.index.names = ["mun", "year"]
P = (births.merge(deaths, on=["mun", "year"], how="outer").merge(pop.reset_index(), on=["mun", "year"], how="left")
     .merge(X.reset_index(), on=["mun", "year"], how="left").merge(Y, on=["mun", "year"], how="left"))
P = P[P.mun.str.match(r"^\d{6}$") & (P.mun.str[2:] != "0000")]
for c in [c for c in P if c.startswith(("n_", "y_"))]:
    P[c] = P[c].fillna(0).astype(int)
P["white_births"] = P.births_white / P.births_race
P["gdp_pc"] = 1e3 * P.gdp / P.population
P["physicians_1000"] = 1e3 * P.cnes_physicians_professionals / P.population
P["race_blank"] = P.race_blank_n / P.deaths
P["natural_svo"] = P.natural_svo_n / P.natural_n
P["external_iml"] = P.external_iml_n / P.external_n
P["died_hospital"] = P.hospital_n / P.deaths
ctx = pd.read_parquet(PAPER / "data" / "municipal_context.parquet", columns=["mun", "immediate", "intermediate", "capital", "metro"])
P = P.merge(ctx, on="mun", how="left")
P["uf"] = P.mun.str[:2].astype(int)
P.to_parquet(PAPER / "data" / "panel_mun_year.parquet", index=False)

# ------------------------------------------------------------------ two census time points
C = {}
for nm in ("population_white", "population_race_universe", "persons_15_plus_literate", "persons_15_plus", "population_urban", "population_resident_census"):
    t = load_field(nm, years=[2010, 2022]).to_pandas()
    t = t[t.status.isin(["value", "ok"])]
    C[nm] = t.groupby(["municipality", "year"]).value.sum()
C = pd.DataFrame(C).reset_index().rename(columns={"municipality": "mun"})
C["census_white"] = C.population_white / C.population_race_universe
C["literate"] = C.persons_15_plus_literate / C.persons_15_plus
C["urban"] = C.population_urban / C.population_resident_census
C = C.pivot(index="mun", columns="year", values=["census_white", "literate", "urban"])
C.columns = [f"{a}_{b}" for a, b in C.columns]
C.reset_index().to_parquet(PAPER / "data" / "panel_census.parquet", index=False)

# ------------------------------------------------------------------ checks: coverage and the size of the within variation
print("municipality-years", len(P), "municipalities", P.mun.nunique(), "years", sorted(P.year.unique()))
print("Brown mothers' linked infant deaths", int(P.n_PW.sum()), "of", int((L.declared == "4").sum()), "; Black", int(P.n_KK.sum()))
for c in ("white_births", "gdp_pc", "physicians_1000", "race_blank", "natural_svo", "external_iml"):
    print(c, "missing", round(P[c].isna().mean(), 4), "median", round(P[c].median(), 4))
assert P.n_PW.sum() == (L.declared == "4").sum() - L[(L.declared == "4") & ~L.mun.isin(P.mun)].shape[0]
print(C.describe().T[["count", "mean", "min", "max"]])
