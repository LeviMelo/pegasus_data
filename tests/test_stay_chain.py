"""SIH-RD's declared stay chain (curation/datasets/core.yml, `semantics.event_types.chain_sql`): which discharge reasons
continue a stay. No test covered the chain until COBRANCA 51 was found splitting stays (t08, 2026-11-24)."""
import duckdb

from pegasus_data.semantics.event_types import chain_sql


def _stays(rows):
    c = duckdb.connect()
    c.execute("""CREATE TABLE aihs(N_AIH VARCHAR, NASC VARCHAR, SEXO VARCHAR, CEP VARCHAR, DT_INTER VARCHAR,
                 DT_SAIDA VARCHAR, COBRANCA VARCHAR, CNES VARCHAR, IDENT VARCHAR)""")
    c.executemany("INSERT INTO aihs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    out = c.execute(f"SELECT N_AIH, __chain FROM ({chain_sql('aihs', 'SIH-RD', 'stay')}) ORDER BY N_AIH").fetchall()
    return dict(out)


P = ("19500101", "1", "57000000")


def test_administrative_closure_continues_the_stay():
    s = _stays([("1", *P, "20190101", "20190110", "51", "2118661", "1"),
                ("2", *P, "20190111", "20190120", "12", "2118661", "1")])
    assert s["1"] == s["2"]


def test_a_discharge_ends_the_stay():
    s = _stays([("1", *P, "20190101", "20190110", "12", "2118661", "1"),
                ("2", *P, "20190111", "20190120", "12", "2118661", "1")])
    assert s["1"] != s["2"]


def test_a_permanence_reason_continues_and_a_gap_breaks():
    s = _stays([("1", *P, "20190101", "20190110", "27", "2118661", "1"),
                ("2", *P, "20190110", "20190115", "51", "2118661", "1"),
                ("3", *P, "20190125", "20190130", "12", "2118661", "1")])
    assert s["1"] == s["2"] != s["3"]
