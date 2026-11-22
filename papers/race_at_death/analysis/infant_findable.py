"""Which linked infant deaths share the candidate estimator's key with their birth record (paper 6, audit finding 6): for every
infant death of 2013-2023 in the order of data/infant_linkage.parquet, whether its linked birth has the same birth date, sex
and residence as the roles the estimator joins on (`modelled_race.candidate_counts`: deceased.birth_date, deceased.sex,
deceased.residence against baby.birth_date, baby.sex, mother.residence).

    python papers/race_at_death/analysis/infant_findable.py   -> papers/race_at_death/data/infant_findable.parquet   (about an hour on a busy machine)
    python papers/race_at_death/analysis/infant_findable.py units   -> only the units and the births cache below (the key comparison is not repeated)

Also (review 2, section 5.1) the units themselves, so that the estimator can be run on exactly the linked units and on the unlinked ones:
data/infant_units.parquet (year, birth date, sex, residence of every death, in the linkage's order) and data/key_cache/births_{year}.parquet
(the births of 2012-2023 by birth date, sex, mother's residence and baby's race code, counted).
"""
import sys
import warnings
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from pegasus_data.config import load_settings
from pegasus_data.linkage import engine
from pegasus_data.linkage.identity import record_ids
from pegasus_data.linkage.roles import role_table
from pegasus_data.studies import modelled_race as mr

warnings.simplefilter("ignore")
DATA = Path(__file__).resolve().parents[1] / "data"
settings = load_settings()
NAME = "sim_infant_deaths_to_sinasc"
spec = engine.load_links()[NAME]
ref = pq.read_table(DATA / "infant_linkage.parquet")
UNITS_ONLY = sys.argv[1:] == ["units"]
BIRTHS_ONLY = sys.argv[1:] == ["births"]
parts, units = [], []
for year in ([] if BIRTHS_ONLY else range(2013, 2024)):
    if UNITS_ONLY:                      # the deaths in the linkage's order (the same role table as infant_deaths reads); aligned by count and recorded colour
        left = role_table(spec.left.dataset, period=year, geography="BR", where=spec.left.where, root=settings.root,
                          roles=["deceased.race", "deceased.birth_date", "deceased.sex", "deceased.residence"])
        r = ref.filter(pc.equal(ref["year"], year))
        assert left.num_rows == r.num_rows and mr._codes(left["deceased.race"]) == r["recorded"].to_pylist(), f"{year}: the role table is not in the linkage's order"
        units.append(pa.table({"year": r["year"], "dn": left["deceased.birth_date"], "sex": left["deceased.sex"].cast(pa.string()),
                               "res": left["deceased.residence"].cast(pa.string())}))
        print("infant units", year, left.num_rows, flush=True)
        continue
    t = mr.infant_deaths(settings, NAME, [year], [], ids=True)
    r = ref.filter(pc.equal(ref["year"], year))
    for col in ("recorded", "declared", "linked"):
        assert t[col].to_pylist() == r[col].to_pylist(), (year, col)
    left = role_table(spec.left.dataset, period=year, geography="BR", where=spec.left.where, root=settings.root,
                      roles=["deceased.birth_date", "deceased.sex", "deceased.residence"])
    right = role_table(spec.right.dataset, period=engine.padded_period(year, spec.right), geography="BR", root=settings.root,
                       roles=["baby.birth_date", "baby.sex", "mother.residence"])

    def keys(table, roles):
        return dict(zip(record_ids(table).to_pylist(), zip(*(table[x].cast(pa.string()).to_pylist() for x in roles), strict=True), strict=True))

    kl = keys(left, ["deceased.birth_date", "deceased.sex", "deceased.residence"])
    kr = keys(right, ["baby.birth_date", "baby.sex", "mother.residence"])
    found = [b is not None and kl.get(d) is not None and kl.get(d) == kr.get(b) for d, b in zip(t["death_id"].to_pylist(), t["birth_id"].to_pylist(), strict=True)]
    parts.append(pa.table({"year": t["year"], "findable": pa.array(found, pa.bool_())}))
    units.append(pa.table({"year": t["year"], "dn": left["deceased.birth_date"], "sex": left["deceased.sex"].cast(pa.string()),
                           "res": left["deceased.residence"].cast(pa.string())}))
    print("infant findable", year, t.num_rows, "linked", sum(t["linked"].to_pylist()), "findable", sum(found), flush=True)
if not UNITS_ONLY and not BIRTHS_ONLY:
    pq.write_table(pa.concat_tables(parts), DATA / "infant_findable.parquet")
if not BIRTHS_ONLY:
    pq.write_table(pa.concat_tables(units), DATA / "infant_units.parquet")
(DATA / "key_cache").mkdir(exist_ok=True)
import duckdb  # noqa: E402

dd = duckdb.connect()
for born in range(2012, 2024):
    b = engine._side_table(spec.right, ["baby.birth_date", "baby.sex", "mother.residence", "baby.race"], period=born, geography="BR", root=settings.root)
    dd.register("b", b)
    g = dd.execute("""SELECT "baby.birth_date" dn, CAST("baby.sex" AS VARCHAR) sex, CAST("mother.residence" AS VARCHAR) mun, CAST("baby.race" AS VARCHAR) j, count(*) n
                      FROM b WHERE "mother.residence" IS NOT NULL AND "baby.sex" IS NOT NULL GROUP BY ALL""").to_arrow_table()
    dd.unregister("b")
    pq.write_table(g, DATA / "key_cache" / f"births_{born}.parquet")
    print("births cache", born, g.num_rows, int(pc.sum(g["n"]).as_py()), "rows read", b.num_rows, flush=True)
print("DONE", flush=True)
