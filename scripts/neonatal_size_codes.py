"""OQ-62: do ICD-10 P07 codes on a newborn's AIH separate same-day births? (ADR-0117)

Usage: python scripts/neonatal_size_codes.py UF   (SIH-RD and SINASC-DN 2022 of that state)
"""
import sys
import warnings

import duckdb

import pegasus_data as pd

warnings.simplefilter("ignore")

geo = sys.argv[1] if len(sys.argv) > 1 else "RR"
sih_cols = ["NASC", "SEXO", "CNES", "DT_INTER", "DIAG_PRINC", "DIAG_SECUN"] + [f"DIAGSEC{i}" for i in range(1, 10)]
sih = pd.query("SIH-RD", period="2022", geography=geo, select=sih_cols, present="codes", allow_partial=True)
sn = pd.query("SINASC-DN", period="2022", geography=geo, select=["DTNASC", "SEXO", "CODESTAB", "PESO", "SEMAGESTAC"],
              present="codes", allow_partial=True)
con = duckdb.connect()
con.register("sih", sih)
con.register("sn", sn)
diag = " || ' ' || ".join(f"coalesce({c}, '')" for c in sih_cols[4:])
con.execute(f"""CREATE TABLE neo AS SELECT row_number() OVER () AS id, strptime(NASC, '%Y%m%d')::DATE AS dob, SEXO AS sex,
    CNES AS cnes, {diag} AS dx FROM sih
    WHERE try_strptime(NASC, '%Y%m%d') IS NOT NULL AND try_strptime(DT_INTER, '%Y%m%d') IS NOT NULL
      AND date_diff('day', strptime(NASC, '%Y%m%d')::DATE, strptime(DT_INTER, '%Y%m%d')::DATE) BETWEEN 0 AND 28""")
con.execute("""CREATE TABLE b AS SELECT try_strptime(DTNASC, '%d%m%Y')::DATE AS dob,
    CASE SEXO WHEN '1' THEN '1' WHEN '2' THEN '3' ELSE NULL END AS sex, CODESTAB AS cnes,
    try_cast(PESO AS INT) AS peso, try_cast(SEMAGESTAC AS INT) AS weeks FROM sn""")
print(con.execute("SELECT sex, count(*) FROM neo GROUP BY 1").fetchall(), con.execute("SELECT sex, count(*) FROM b GROUP BY 1").fetchall())
con.execute("""CREATE TABLE neo2 AS SELECT *,
    CASE WHEN dx LIKE '%P070%' THEN 'P07.0 <1000g' WHEN dx LIKE '%P071%' THEN 'P07.1 1000-2499g'
         WHEN dx LIKE '%P072%' THEN 'P07.2 <28w' WHEN dx LIKE '%P073%' THEN 'P07.3 28-36w' ELSE 'none' END AS p07 FROM neo""")
print("neonatal admissions:", con.execute("SELECT count(*) FROM neo2").fetchone()[0])
print(con.execute("SELECT p07, count(*) FROM neo2 GROUP BY 1 ORDER BY 2 DESC").fetchall())
# candidates on the key alone vs after the ICD-10 definition
rows = con.execute("""
  SELECT n.p07, count(DISTINCT n.id) AS adm,
         avg(k) AS mean_candidates_key, avg(kc) AS mean_candidates_consistent,
         sum(CASE WHEN k = 1 THEN 1 ELSE 0 END) AS unique_key,
         sum(CASE WHEN kc = 1 THEN 1 ELSE 0 END) AS unique_consistent,
         sum(CASE WHEN kc = 0 THEN 1 ELSE 0 END) AS none_consistent
  FROM (SELECT n.id, n.p07, count(b.dob) AS k,
          count(b.dob) FILTER (WHERE (n.p07 = 'P07.0 <1000g' AND b.peso < 1000)
                             OR (n.p07 = 'P07.1 1000-2499g' AND b.peso BETWEEN 1000 AND 2499)
                             OR (n.p07 = 'P07.2 <28w' AND b.weeks < 28)
                             OR (n.p07 = 'P07.3 28-36w' AND b.weeks BETWEEN 28 AND 36)
                             OR n.p07 = 'none') AS kc
        FROM neo2 n LEFT JOIN b ON b.dob = n.dob AND b.sex = n.sex AND b.cnes = n.cnes
        GROUP BY n.id, n.p07) n
  GROUP BY n.p07 ORDER BY adm DESC""").fetchall()
for r in rows:
    print(r)
