"""The municipality as a unit: its socioeconomic context, its health services and how its death certificates are filled,
one row per municipality (six-digit DATASUS code), into papers/race_at_death/data/municipal_context.parquet.

Sources (all held by pegasus_data; `pegasus-data info` lists them):
  SIDRA 5938 (municipal GDP, 2013-2021 mean), census 2010 series (literacy 15+, low per-capita income, urban population,
  resident population, race of residents), CNES December registers (physicians, beds, family-health teams, 2013-2023
  mean), IBGE memberships (state capital, metropolitan region, immediate and intermediate regions), REGIC is not used;
  the SIM and SINASC lakes (certificates of 2013-2023 by municipality of residence: race left blank, certifier, place of
  death; births: hospital delivery).

    python papers/race_at_death/analysis/context.py      (about two minutes)
"""
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from pegasus_data.config import load_settings
from pegasus_data.fields import load_field
from pegasus_data.geography import memberships

warnings.simplefilter("ignore")
PAPER = Path(__file__).resolve().parents[1]
LAKE = Path(load_settings().lake_dir).as_posix()
con = duckdb.connect()
con.execute("PRAGMA disable_progress_bar; SET memory_limit='6GB'")


def field(name, years):
    """The mean over ``years`` of a field, by six-digit municipality; only rows whose status is a value."""
    t = load_field(name, years=years).to_pandas()
    t = t[t.status.isin(["value", "ok"])]
    return t.groupby("municipality").value.mean().rename(name)


# ------------------------------------------------------------------ socioeconomic and demographic context
YEARS = list(range(2013, 2024))
ctx = pd.concat([field("gdp", list(range(2013, 2022))), field("population_resident_census", [2010]).rename("pop2010"),
                 field("population_resident_census", [2022]).rename("pop2022"), field("persons_15_plus_literate", [2010]),
                 field("persons_15_plus", [2010]), field("persons_low_income", [2010]), field("persons_income_universe", [2010]),
                 field("population_urban", [2010]), field("population_white", [2010]), field("population_brown", [2010]),
                 field("population_black", [2010]), field("population_race_universe", [2010]),
                 field("cnes_physicians_professionals", YEARS), field("cnes_beds_total", YEARS), field("cnes_teams_esf", YEARS)], axis=1)
ctx.index.name = "mun"
pop = (ctx.pop2010 + ctx.pop2022) / 2
ctx = pd.DataFrame({
    "gdp_pc": 1e3 * ctx.gdp / pop,                                         # R$ per person, current prices, mean 2013-2021
    "illiterate": 1 - ctx.persons_15_plus_literate / ctx.persons_15_plus,  # census 2010, aged 15 and over
    "low_income": ctx.persons_low_income / ctx.persons_income_universe,    # census 2010, per-capita income up to half a minimum wage
    "urban": ctx.population_urban / ctx.pop2010,
    "pop2010": ctx.pop2010,
    "census_white": ctx.population_white / ctx.population_race_universe,
    "census_brown": ctx.population_brown / ctx.population_race_universe,
    "census_black": ctx.population_black / ctx.population_race_universe,
    "physicians_1000": 1e3 * ctx.cnes_physicians_professionals / pop,
    "beds_1000": 1e3 * ctx.cnes_beds_total / pop,
    "esf_10000": 1e4 * ctx.cnes_teams_esf / pop,
}).reset_index()

# ------------------------------------------------------------------ geography: capital, metropolitan region, IBGE regions
GEO = ("capital", "metropolitan_region", "ibge_immediate_region", "ibge_intermediate_region")
rows = []
for m in ctx.mun:
    ms = memberships(m)
    rows.append({"mun": m} | {g: (ms.get(g).member_code if ms.get(g) else None) for g in GEO})
geo = pd.DataFrame(rows)
geo["capital"] = geo.capital.notna()
geo["metro"] = geo.metropolitan_region.notna()
ctx = ctx.merge(geo.rename(columns={"ibge_immediate_region": "immediate", "ibge_intermediate_region": "intermediate"}), on="mun", how="left")

# ------------------------------------------------------------------ how the municipality's deaths and births are recorded
SIM = f"read_parquet('{LAKE}/SIM/SIM_DO_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
sim = con.execute(f"""
    SELECT left(trim(CODMUNRES), 6) mun, count(*) deaths,
           avg((trim(RACACOR) NOT IN ('1','2','3','4','5') OR RACACOR IS NULL)::INT) race_blank,
           avg((trim(LOCOCOR) = '1')::INT) died_hospital,
           avg((trim(ATESTANTE) = '3')::INT) FILTER (left(CAUSABAS, 1) IN ('V','W','X','Y')) external_by_iml,
           avg((trim(ATESTANTE) = '4')::INT) FILTER (left(CAUSABAS, 1) NOT IN ('V','W','X','Y')) natural_by_svo,
           avg((trim(ATESTANTE) = '3')::INT) FILTER (left(CAUSABAS, 1) NOT IN ('V','W','X','Y')) natural_by_iml,
           count(*) FILTER (left(trim(IDADE), 1) IN ('0','1','2') OR trim(IDADE) BETWEEN '300' AND '399') infant_deaths,
           avg((trim(RACACOR) NOT IN ('1','2','3','4','5') OR RACACOR IS NULL)::INT) FILTER (left(trim(IDADE), 1) IN ('0','1','2') OR trim(IDADE) BETWEEN '300' AND '399') infant_race_blank
    FROM {SIM} WHERE year BETWEEN 2013 AND 2023 GROUP BY 1""").df()
SN = f"read_parquet('{LAKE}/SINASC/SINASC_DN_*/*/*/*/*.parquet', union_by_name=true, hive_partitioning=true)"
sn = con.execute(f"""SELECT left(trim(CODMUNRES), 6) mun, avg((trim(LOCNASC) = '1')::INT) born_hospital,
                            avg((trim(RACACORMAE) NOT IN ('1','2','3','4','5') OR RACACORMAE IS NULL)::INT) mother_race_blank
                     FROM {SN} WHERE year BETWEEN 2013 AND 2023 GROUP BY 1""").df()
ctx = ctx.merge(sim, on="mun", how="left").merge(sn, on="mun", how="left")
out = PAPER / "data" / "municipal_context.parquet"
ctx.to_parquet(out, index=False)
print("written", out, ctx.shape)
print(ctx.describe().T[["count", "mean", "50%", "min", "max"]].to_string())
print("capitals", int(ctx.capital.sum()), "metropolitan", int(ctx.metro.sum()), "immediate", ctx.immediate.nunique(), "intermediate", ctx.intermediate.nunique())
print("deaths by year check", con.execute(f"SELECT year, count(*) FROM {SIM} WHERE year BETWEEN 2013 AND 2023 GROUP BY 1 ORDER BY 1").fetchall())
assert np.isfinite(ctx.gdp_pc).mean() > 0.99
