"""The second validation pair of the estimator (paper 6): admissions that ended in death (SIH-RD) looked for among the
death certificates (SIM-DO) of the same year by birth date, sex and residence alone (`modelled_race.pair_candidate_counts`),
against the stored probabilistic link `sih_deaths_to_sim`, which also uses the day of death and the hospital
(`modelled_race.pair_truth`). The control is scaled within the municipality (``mun``) or within the state (``uf``).

    python papers/race_at_death/analysis/pair.py [year ...]   -> papers/race_at_death/data/pair_counts_{mun,uf}.parquet, pair_truth.parquet
    python papers/race_at_death/analysis/pair.py units        -> data/key_cache/pair_units_{year}.parquet, pair_reg_{year}.parquet

``units`` (review 2, section 5.1) writes, per year, the units grouped by birth date, sex, residence and recorded colour with whether the stored link
paired them and the partner's colour (the rows of pair_truth with the birth date it does not hold), and the certificates by the same key, so that the
estimator can be run on exactly the linked units, on the unlinked ones, on one sex, or with the key date shifted (analysis/estimator.py).
"""
import sys
import warnings
from pathlib import Path

import pyarrow.parquet as pq

from pegasus_data.config import load_settings
from pegasus_data.studies import modelled_race as mr

warnings.simplefilter("ignore")
OUT = Path(__file__).resolve().parents[1] / "data"
UNITS = "units" in sys.argv[1:]
YEARS = [int(y) for y in sys.argv[1:] if y != "units"] or list(range(2016, 2023))
settings = load_settings()
log = lambda m: print(m, flush=True)  # noqa: E731
kw = {"unit": mr.SIH_DEATH, "register": mr.SIM_DEATH}
if UNITS:
    import pyarrow as pa
    import pyarrow.compute as pc

    from pegasus_data.linkage import engine

    spec = engine.load_links()["sih_deaths_to_sim"]
    truth_all = pq.read_table(OUT / "pair_truth.parquet")
    (OUT / "key_cache").mkdir(exist_ok=True)
    roles = ("birth_date", "sex", "residence", "race", "date")
    u, g = kw["unit"], kw["register"]
    for year in YEARS:
        left = engine._side_table(spec.left, [u[r] for r in roles], period=year, geography="BR", root=settings.root)
        left = left.filter(pc.equal(pc.year(left[u["date"]]), year))                    # the rows of pair_truth, in its order
        t = truth_all.filter(pc.equal(truth_all["year"], year))
        assert t.num_rows == left.num_rows and t["mun"].to_pylist() == left[u["residence"]].cast(pa.string()).to_pylist()             and t["recorded"].to_pylist() == left[u["race"]].to_pylist(), f"pair_truth {year} is not aligned"
        units = pa.table({"dn": left[u["birth_date"]], "sex": left[u["sex"]].cast(pa.string()), "mun": t["mun"], "k": t["recorded"], "age": t["age"],
                          "linked": t["linked"], "findable": t["findable"], "declared": t["declared"]})
        units = units.filter(pc.and_(pc.is_valid(units["dn"]), pc.is_valid(units["mun"])))
        units = units.filter(pc.is_in(units["sex"], pa.array(["M", "F"])))
        grp = units.group_by(["dn", "sex", "mun", "k", "linked", "findable", "declared"]).aggregate([([], "count_all")])
        grp = grp.rename_columns(["dn", "sex", "mun", "k", "linked", "findable", "declared", "n"])
        pq.write_table(grp, OUT / "key_cache" / f"pair_units_{year}.parquet")
        right = engine._side_table(spec.right, [g[r] for r in roles], period=year, geography="BR", root=settings.root)
        right = right.filter(pc.equal(pc.year(right[g["date"]]), year))
        rg = pa.table({"dn": right[g["birth_date"]], "sex": right[g["sex"]].cast(pa.string()), "mun": right[g["residence"]].cast(pa.string()), "j": right[g["race"]]})
        rg = rg.filter(pc.and_(pc.is_valid(rg["dn"]), pc.is_valid(rg["mun"])))
        rg = rg.filter(pc.is_in(rg["sex"], pa.array(["M", "F"])))
        rg = rg.group_by(["dn", "sex", "mun", "j"]).aggregate([([], "count_all")]).rename_columns(["dn", "sex", "mun", "j", "n"])
        pq.write_table(rg, OUT / "key_cache" / f"pair_reg_{year}.parquet")
        log(f"units {year}: {units.num_rows} units, {rg.num_rows} register cells")
    print("DONE", flush=True)
    sys.exit(0)
for label, scale in (("mun", "mun"), ("uf", "substr(mun, 1, 2)")):
    pq.write_table(mr.pair_candidate_counts(settings, "sih_deaths_to_sim", YEARS, scale=scale, log=log, **kw), OUT / f"pair_counts_{label}.parquet")
notes: list[str] = []
truth = mr.pair_truth(settings, "sih_deaths_to_sim", YEARS, notes=notes, **kw)
pq.write_table(truth, OUT / "pair_truth.parquet")
print(truth.num_rows, "units;", sum(truth["linked"].to_pylist()), "linked;", *sorted(set(notes)), sep="\n", flush=True)
print("DONE", flush=True)
