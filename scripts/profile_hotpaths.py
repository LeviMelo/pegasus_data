"""Peak memory and wall time of the read hot paths, process tree included.

    PY scripts/profile_hotpaths.py query SIM.DO 2022 CODMUNRES,SEXO,IDADE,CAUSABAS,DTOBITO
    PY scripts/profile_hotpaths.py query SIH-RD 2022 MUNIC_RES,SEXO,IDADE,DIAG_PRINC --labels
    PY scripts/profile_hotpaths.py stream SIM.DO 2022 CODMUNRES,SEXO,IDADE,CAUSABAS,DTOBITO
    PY scripts/profile_hotpaths.py narrow SIM.DO 2022 CODMUNRES,SEXO,IDADE,CAUSABAS,DTOBITO

Each mode runs in a child process whose tree (decode workers included) is sampled
every 0.2 s; the last line is JSON. Run one at a time on a shared machine.

* ``query``  one national ``query(select=..., present="codes")``: the baseline.
* ``stream`` the same rows, one UF at a time, folded into a DuckDB table as they
  arrive (peak = one state's columns, not the nation's); prints the identical
  checksum so equality with ``query`` can be asserted.
* ``narrow`` the baseline table, then the same columns dictionary-encoded:
  Arrow bytes of both (the saving of narrowing low-cardinality string columns).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

import psutil

from pegasus_data.config import load_settings

#: The one data home (ADR-0200: PEGASUS_DATA_HOME or the user's config), never a path of this machine
ROOT = str(load_settings().root)

CHILD = r'''
import sys, time, warnings, json
warnings.simplefilter("ignore")
import pyarrow as pa, pyarrow.compute as pc
import pegasus_data as pg
from pegasus_data.config import UF_ABBREVIATIONS
mode, dataset, year, cols = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4].split(",")
present = "labels" if "--labels" in sys.argv else "codes"
root = sys.argv[sys.argv.index("--root") + 1]
kw = dict(period=year, select=cols, present=present, root=root, max_download=8 * 1024**3)
t0 = time.time()

def checksum(table):
    # row count and an order-independent hash-free digest: group counts of the first column
    g = table.group_by(cols[0]).aggregate([([], "count_all")])
    return {"rows": table.num_rows, "groups": g.num_rows, "sum": pc.sum(g.column(1)).as_py()}

if mode == "query":
    table = pg.query(dataset, geography="BR", **kw)
    print(json.dumps({"mode": mode, "arrow_MB": table.nbytes >> 20, **checksum(table)}))
elif mode == "stream":
    import duckdb
    con = duckdb.connect()
    ufs = list(UF_ABBREVIATIONS)
    made, biggest = False, 0
    for uf in ufs:
        part = pg.query(dataset, geography=uf, **kw)
        biggest = max(biggest, part.nbytes)
        con.register("part", part)
        con.execute("INSERT INTO t SELECT * FROM part" if made else "CREATE TABLE t AS SELECT * FROM part")
        con.unregister("part"); made = True
    rows = con.execute("select count(*) from t").fetchone()[0]
    g = con.execute(f'select count(*), sum(c) from (select count(*) c from t group by "{cols[0]}")').fetchone()
    print(json.dumps({"mode": mode, "largest_state_MB": biggest >> 20, "rows": rows, "groups": g[0], "sum": g[1]}))
elif mode == "narrow":
    table = pg.query(dataset, geography="BR", **kw)
    enc = pa.table({n: pc.dictionary_encode(table.column(n)) for n in table.column_names})
    print(json.dumps({"mode": mode, "plain_MB": table.nbytes >> 20, "dictionary_MB": enc.nbytes >> 20,
                      "distinct": {n: pc.count_distinct(table.column(n)).as_py() for n in table.column_names}}))
print(json.dumps({"seconds": round(time.time() - t0, 1)}))
'''


def main() -> int:
    mode, dataset, year, cols, *rest = sys.argv[1:]
    free = psutil.virtual_memory().available / 2**30
    floor = float(os.environ.get("PEGASUS_PROFILE_MIN_FREE_GB", "12"))
    if free < floor:
        print(f"only {free:.1f} GB free; wait for {floor:.0f} GB (shared machine)", file=sys.stderr)
        return 2
    env = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.Popen([sys.executable, "-c", CHILD, mode, dataset, year, cols, *rest, "--root", ROOT],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf8", errors="replace")
    peak = {"rss": 0, "private": 0, "procs": 0}
    done = threading.Event()

    def sample() -> None:
        root = psutil.Process(proc.pid)
        while not done.is_set():
            rss = private = 0
            try:
                tree = [root, *root.children(recursive=True)]
            except psutil.Error:
                break
            for p in tree:
                try:
                    info = p.memory_info()
                    rss += info.rss
                    private += info.private
                except psutil.Error:
                    pass
            peak["rss"], peak["private"] = max(peak["rss"], rss), max(peak["private"], private)
            peak["procs"] = max(peak["procs"], len(tree))
            time.sleep(0.2)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    started = time.time()
    out = proc.communicate()[0]
    done.set()
    sampler.join()
    print(out.strip()[-1500:])
    print(json.dumps({"scenario": [mode, dataset, year, cols, *rest], "wall_s": round(time.time() - started, 1),
                      "peak_tree_rss_MB": peak["rss"] >> 20, "peak_tree_private_MB": peak["private"] >> 20,
                      "max_processes": peak["procs"]}))
    return proc.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
