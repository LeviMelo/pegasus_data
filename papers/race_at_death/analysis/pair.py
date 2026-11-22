"""The second validation pair of the estimator (paper 6): admissions that ended in death (SIH-RD) looked for among the
death certificates (SIM-DO) of the same year by birth date, sex and residence alone (`modelled_race.pair_candidate_counts`),
against the stored probabilistic link `sih_deaths_to_sim`, which also uses the day of death and the hospital
(`modelled_race.pair_truth`). The control is scaled within the municipality (``mun``) or within the state (``uf``).

    python papers/race_at_death/analysis/pair.py [year ...]   -> papers/race_at_death/data/pair_counts_{mun,uf}.parquet, pair_truth.parquet
"""
import sys
import warnings
from pathlib import Path

import pyarrow.parquet as pq

from pegasus_data.config import load_settings
from pegasus_data.studies import modelled_race as mr

warnings.simplefilter("ignore")
OUT = Path(__file__).resolve().parents[1] / "data"
YEARS = [int(y) for y in sys.argv[1:]] or list(range(2016, 2023))
settings = load_settings()
log = lambda m: print(m, flush=True)  # noqa: E731
kw = {"unit": mr.SIH_DEATH, "register": mr.SIM_DEATH}
for label, scale in (("mun", "mun"), ("uf", "substr(mun, 1, 2)")):
    pq.write_table(mr.pair_candidate_counts(settings, "sih_deaths_to_sim", YEARS, scale=scale, log=log, **kw), OUT / f"pair_counts_{label}.parquet")
notes: list[str] = []
truth = mr.pair_truth(settings, "sih_deaths_to_sim", YEARS, notes=notes, **kw)
pq.write_table(truth, OUT / "pair_truth.parquet")
print(truth.num_rows, "units;", sum(truth["linked"].to_pylist()), "linked;", *sorted(set(notes)), sep="\n", flush=True)
print("DONE", flush=True)
