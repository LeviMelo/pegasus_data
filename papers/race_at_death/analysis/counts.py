"""The candidate counts the paper analyses, with state, age, sex, cause and year of death (package function
`modelled_race.candidate_counts`), and the one-to-one linkage of infant deaths for every year it is stored.

    python papers/race_at_death/analysis/counts.py [label ...]   -> papers/race_at_death/data/*.parquet   (about an hour)

Labels: children, youth, infants (by state, age, sex, cause, year); children_context, youth_context (also by who certified,
where the death occurred and the mother's schooling on the birth record); linkage; linkage_context (the linkage with columns
of the death and of the birth record for the individual models); delivery (the hospital's record of the mother at delivery). No label: all of them.
"""
import sys
import warnings
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

import pegasus_data
from pegasus_data.config import load_settings
from pegasus_data.linkage.identity import record_ids
from pegasus_data.studies import modelled_race as mr

warnings.simplefilter("ignore")
OUT = Path(__file__).resolve().parents[1] / "data"
OUT.mkdir(exist_ok=True)
settings = load_settings()
log = lambda m: print(m, flush=True)  # noqa: E731


def filed(dataset, year, columns, wanted):
    """The columns of a dataset as filed (codes), for the records of one year whose identity is in ``wanted``."""
    raw = pegasus_data.query(dataset, period=year, geography="BR", select=list(columns), present="codes", provenance="all")
    ids = record_ids(raw).to_pylist()
    values = [raw[c].cast(pa.string()).to_pylist() for c in columns]
    return {i: tuple(v[n] for v in values) for n, i in enumerate(ids) if i in wanted}


def with_columns(table, dataset, years, columns):
    """``table`` (a side's role table) with the filed columns ``columns`` {name: source column} added."""
    ids = record_ids(table).to_pylist()
    wanted, look = set(ids), {}
    for year in years:
        look |= filed(dataset, year, columns.values(), wanted)
        log(f"{dataset} {year}: {len(look)} of {len(ids)} records with {list(columns)}")
    none = (None,) * len(columns)
    for n, name in enumerate(columns):
        table = table.append_column(name, pa.array([look.get(i, none)[n] for i in ids], pa.string()))
    return table


def certifier(years):
    return lambda deaths: with_columns(deaths, "SIM-DO", years, {"certifier": "ATESTANTE", "autopsy": "NECROPSIA"})


def schooling(column):
    return lambda births, year: with_columns(births, "SINASC-DN", [year], {"schooling": column})


JOBS = {
    "children": dict(name="sim_deaths_to_own_birth", years=list(range(2013, 2025)), births_from=2012, births_to=2023, max_age=14),
    "youth": dict(name="sim_deaths_to_own_birth", years=list(range(2014, 2025)), births_from=2000, births_to=2010, max_age=24),
    "infants": dict(name="sim_infant_deaths_to_sinasc", years=list(range(2013, 2024)), births_from=2012, births_to=2023, max_age=None),
    "children_context": dict(name="sim_deaths_to_own_birth", years=list(range(2013, 2025)), births_from=2012, births_to=2023, max_age=14,
                             death_by=("certifier", "autopsy", "death.place"), birth_by=("schooling",), annotate_deaths=certifier(range(2013, 2025)),
                             annotate_births=schooling("ESCMAE")),
    "youth_context": dict(name="sim_deaths_to_own_birth", years=list(range(2014, 2025)), births_from=2000, births_to=2010, max_age=24,
                          death_by=("certifier", "autopsy", "death.place"), birth_by=("schooling",), annotate_deaths=certifier(range(2014, 2025)),
                          annotate_births=schooling("ESCMAE")),
}
WANTED = sys.argv[1:] or [*JOBS, "linkage"]
for label, kw in JOBS.items():
    if label not in WANTED:
        continue
    f = OUT / f"{label}_counts.parquet"
    if not f.exists():
        name = kw.pop("name")
        pq.write_table(mr.candidate_counts(settings, name, kw.pop("years"), log=log, **kw), f)
        print("written", f, flush=True)
f = OUT / "infant_linkage.parquet"
if "linkage" in WANTED and not f.exists():
    parts = []
    for year in range(2013, 2024):
        try:
            t = mr.infant_deaths(settings, "sim_infant_deaths_to_sinasc", [year], [])
        except Exception as e:  # noqa: BLE001 - a year whose stored run does not match the data is reported, not hidden
            print("infant linkage", year, "not read:", type(e).__name__, str(e)[:200], flush=True)
            continue
        parts.append(t)
        print("infant linkage", year, t.num_rows, sum(t["linked"].to_pylist()), flush=True)
    pq.write_table(pa.concat_tables(parts), f)
# the same linkage with the columns of both records the individual models use: the death's certifier, place, establishment
# and cause; the birth's mother's schooling and age, weight, gestation, place and establishment of birth, antenatal visits
DEATH_COLS = {"certifier": "ATESTANTE", "death_place": "LOCOCOR", "death_estab": "CODESTAB", "cause": "CAUSABAS", "autopsy": "NECROPSIA"}
BIRTH_COLS = {"schooling": "ESCMAE", "mother_age": "IDADEMAE", "weight": "PESO", "gestation": "GESTACAO", "birth_place": "LOCNASC",
              "birth_estab": "CODESTAB", "visits": "CONSULTAS", "delivery": "PARTO", "marital": "ESTCIVMAE"}
f = OUT / "infant_linkage_context.parquet"
if "linkage_context" in WANTED and not f.exists():
    parts = []
    for year in range(2013, 2024):
        t = mr.infant_deaths(settings, "sim_infant_deaths_to_sinasc", [year], [], ids=True)
        dids, bids = t["death_id"].to_pylist(), t["birth_id"].to_pylist()
        dl = filed("SIM-DO", year, DEATH_COLS.values(), set(dids))
        bl = {}
        for by in (year - 1, year):
            bl |= filed("SINASC-DN", by, BIRTH_COLS.values(), {b for b in bids if b})
        for n, name in enumerate(DEATH_COLS):
            t = t.append_column(name, pa.array([dl.get(i, (None,) * len(DEATH_COLS))[n] for i in dids], pa.string()))
        for n, name in enumerate(BIRTH_COLS):
            t = t.append_column(name, pa.array([bl.get(b, (None,) * len(BIRTH_COLS))[n] if b else None for b in bids], pa.string()))
        t = t.drop_columns(["death_id", "birth_id"])
        parts.append(t)
        print("infant linkage context", year, t.num_rows, "deaths annotated", sum(i in dl for i in dids), "births annotated",
              sum(b in bl for b in bids if b), flush=True)
    pq.write_table(pa.concat_tables(parts), f)
# the hospital's record of the mother at delivery (link sinasc_births_to_delivery_admission): by facility for every year, and for the mother of
# each linked infant death. The infant rows are those of infant_linkage_context.parquet, in its order (checked field by field).
if "delivery" in WANTED and not (OUT / "delivery_by_facility.parquet").exists():
    import pyarrow.compute as pc

    from pegasus_data.linkage import engine
    from pegasus_data.linkage.roles import role_table

    spec = engine.load_links()["sinasc_births_to_delivery_admission"]
    ctx = pq.read_table(OUT / "infant_linkage_context.parquet")
    infant_parts, fac_parts, mother = [], [], {}
    for year in range(2013, 2024):
        t = mr.infant_deaths(settings, "sim_infant_deaths_to_sinasc", [year], [], ids=True)
        c = ctx.filter(pc.equal(ctx["year"], year))
        for col in ("recorded", "declared", "mun", "age_days", "linked"):
            assert t[col].to_pylist() == c[col].to_pylist(), (year, col)
        infant_parts.append(pa.table({"year": t["year"], "birth_id": t["birth_id"]}))
        print("infant ids", year, t.num_rows, flush=True)
    wanted = {b for p in infant_parts for b in p["birth_id"].to_pylist() if b}
    for byear in range(2012, 2024):
        pairs, _ = mr._stored_pairs(settings, "sinasc_births_to_delivery_admission", byear, [])
        left = role_table(spec.left.dataset, period=byear, geography="BR", roles=["mother.race"], root=settings.root)
        left = left.append_column("_id", record_ids(left)).select(["_id", "mother.race"])
        right = role_table(spec.right.dataset, period=engine.padded_period(byear, spec.right), geography="BR", where=spec.right.where or None,
                           roles=["patient.race", "admission.facility"], root=settings.root)
        right = right.append_column("_id", record_ids(right)).select(["_id", "patient.race", "admission.facility"])
        j = pa.table({"l": pairs["l"], "r": pairs["r"]}).join(left, "l", "_id").join(right, "r", "_id")
        agg = j.group_by(["admission.facility", "mother.race", "patient.race"]).aggregate([("l", "count")])
        agg = agg.append_column("birth_year", pa.array([byear] * agg.num_rows, pa.int64()))
        fac_parts.append(agg)
        keep = j.filter(pc.is_in(j["l"], pa.array(sorted(wanted), pa.string())))
        for l_, h, f in zip(keep["l"].to_pylist(), keep["patient.race"].to_pylist(), keep["admission.facility"].to_pylist(), strict=True):
            mother[l_] = (h, f)
        print("delivery", byear, "pairs", pairs.num_rows, "joined", j.num_rows, "infants' mothers found", keep.num_rows, flush=True)
        del left, right, j
    pq.write_table(pa.concat_tables(fac_parts), OUT / "delivery_by_facility.parquet")
    ids = pa.concat_tables(infant_parts)
    bl = ids["birth_id"].to_pylist()
    out = ctx.append_column("mother_hospital_race", pa.array([mother.get(b, (None, None))[0] if b else None for b in bl], pa.string()))
    out = out.append_column("delivery_facility", pa.array([mother.get(b, (None, None))[1] if b else None for b in bl], pa.string()))
    pq.write_table(out, OUT / "infant_linkage_delivery.parquet")
    print("written delivery", out.num_rows, "with the hospital's record of the mother", sum(1 for b in bl if b in mother), flush=True)
print("DONE", flush=True)
