"""Which linked infant deaths share the candidate estimator's key with their birth record (paper 6, audit finding 6): for every
infant death of 2013-2023 in the order of data/infant_linkage.parquet, whether its linked birth has the same birth date, sex
and residence as the roles the estimator joins on (`modelled_race.candidate_counts`: deceased.birth_date, deceased.sex,
deceased.residence against baby.birth_date, baby.sex, mother.residence).

    python papers/race_at_death/analysis/infant_findable.py   -> papers/race_at_death/data/infant_findable.parquet   (a few minutes)
"""
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
parts = []
for year in range(2013, 2024):
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
    print("infant findable", year, t.num_rows, "linked", sum(t["linked"].to_pylist()), "findable", sum(found), flush=True)
pq.write_table(pa.concat_tables(parts), DATA / "infant_findable.parquet")
print("DONE", flush=True)
