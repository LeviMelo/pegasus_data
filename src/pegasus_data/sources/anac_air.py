"""Air passengers between Brazilian municipalities by month, from ANAC's "Dados Estatísticos do Transporte Aéreo".

What a row of ``Dados_Estatisticos.csv`` is (ANAC, "Descrição das variáveis" of the Dados Estatísticos, section *Etapa
Básica*): a **flight stage** (*etapa básica*), the operation of an aircraft between one take-off and the next landing,
summed over one company, month, origin and destination aerodrome, nature and flight group. The stage-only columns the
file carries (ASK, RPK, DISTÂNCIA VOADA, DECOLAGENS, HORAS VOADAS) are defined there for the stage and not for the
*etapa combinada* (origin-destination of the passenger, ICAO's OFOD). So a passenger on a flight A-B-C is counted on
A-B and again on B-C: the matrix is the **flow carried on each segment**, not the origin-destination of the traveller.

Columns used (same page):

* ``PASSAGEIROS_PAGOS``: passengers occupying seats offered that generate revenue for the airline (promotional fares,
  loyalty programmes, discounts and preferential fares included).
* ``PASSAGEIROS_GRATIS``: passengers occupying seats offered that generate no revenue (travelling free, airline staff
  at discount, airline staff on duty). Both are people carried, so ``weight = paid + free``; each is kept apart.
* ``DECOLAGENS``: take-offs between the stage's origin and destination (``flights``).
* ``NATUREZA``: "Doméstico" (spelled DOMÉSTICA in the file) only when take-off and landing are in Brazil **and** the operator is Brazilian; otherwise
  "Internacional". A foreign airline flying two Brazilian airports is therefore "Internacional" in the file.
* ``GRUPO_DE_VOO``: REGULAR, NÃO REGULAR (charter, fretamento) or IMPRODUTIVO (no revenue: training, ferry).

Declared rules:

* A leg is **domestic here when both aerodromes are in Brazil** (``..._PAIS`` = BRASIL), whatever the nature, so the
  flows of foreign airlines between Brazilian airports are kept; the passengers of each nature are reported apart.
* **The airport serves the municipality it lies in**: the IBGE municipality whose boundary contains its coordinates
  (`geography.place_points`, IBGE's full-resolution mesh; a runway just off the coast takes the nearest municipality
  within 2 km). The coordinates are the ANAC registers' (``LATGEOPOINT``/``LONGEOPOINT``; a public entry outranks a
  private one); an airport the registers no longer list (closed or re-coded: SBNT Natal-Augusto Severo, in
  Parnamirim, carried 21 M passengers before 2014) takes OurAirports' (public domain, ``ourairports_airports.csv``),
  matched by its ``ident``, ``icao_code`` or ``gps_code``, unique matches only. Neither ANAC register carries an IBGE
  code, and a name is not a place: the register's *Município* (not *Município Servido*) and the statistics file's own
  airport city (ANAC's commercial city, CURITIBA for the airport in São José dos Pinhais) are compared with the
  placement and reported, never used. An airport with no coordinates is counted apart with its passengers.
* A leg whose two ends are the same municipality is not a flow between municipalities and is counted apart.
* Missing is not zero: an empty passenger cell is not a count; the cells that are neither empty nor integers are reported.

The check: ANAC's own *Anuário do Transporte Aéreo* (audited, published the year after) gives the domestic paid
passengers per year; the build compares that with the file's paid passengers of nature "Doméstico".
"""

from __future__ import annotations

import csv
import io
import json
import typing
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

from .. import transport
from ..config import load_settings
from ..geography import municipalities, place_points
from ..persist.kept import write_json_atomic, write_parquet_atomic
from ..proximity import proximity_graph
from ..textenc import fold

__all__ = ["build"]

_ROOT = "https://sistemas.anac.gov.br/dadosabertos/"
STATS_URL = (_ROOT + "Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/Dados%20Estat%C3%ADsticos%20do%20Transporte%20A%C3%A9reo/"
             "Dados_Estatisticos.csv")
_REGISTERS = _ROOT + "Aerodromos/"
GOV = "https://www.gov.br/anac/pt-br/assuntos/dados-e-estatisticas/"
SOURCES: dict[str, str] = {
    "Dados_Estatisticos.csv": STATS_URL,
    "AerodromosPublicos.csv": _REGISTERS + "Aer%C3%B3dromos%20P%C3%BAblicos/Lista%20de%20aer%C3%B3dromos%20p%C3%BAblicos/AerodromosPublicos.csv",
    "AerodromosPrivados.csv": _REGISTERS + "Aer%C3%B3dromos%20Privados/Lista%20de%20aer%C3%B3dromos%20privados/Aerodromos%20Privados/AerodromosPrivados.csv",
    "ourairports_airports.csv": "https://davidmegginson.github.io/ourairports-data/airports.csv",
    "anuario_2019.zip": GOV + "anuario/2019.zip",
    "anuario_2022.zip": GOV + "mercado-do-transporte-aereo/panorama-do-mercado/anuario-transporte-aereo/2022.zip",
}
KIND = "air_passengers"


def _uf_sigla_by_name() -> dict[str, str]:
    return {fold(m["uf_name"]): m["uf_sigla"] for m in municipalities().values()}


def _register(path: Path, ufs: dict[str, str]) -> dict[str, dict[str, str]]:
    """``ICAO -> {municipality, uf, lat, lon}`` of one ANAC aerodrome register (cp1252, a dated first line, ';'; the public
    register writes the UF in full, the private one as a sigla; decimal coordinates with a point or a comma)."""
    lines = path.read_bytes().decode("cp1252", errors="replace").splitlines()[1:]
    found: dict[str, dict[str, str]] = {}
    for row in csv.DictReader(lines, delimiter=";"):
        code = row["Código OACI"].strip().upper()
        if code:
            found[code] = {"municipality": row["Município"].strip(), "uf": ufs.get(fold(row["UF"]), row["UF"].strip().upper()),
                           "lat": row["LATGEOPOINT"].replace(",", "."), "lon": row["LONGEOPOINT"].replace(",", "."),
                           "from": path.name}
    return found


def _ourairports(path: Path) -> dict[str, dict[str, str]]:
    """``code -> {lat, lon}`` for Brazilian airports in OurAirports, under each of its ``ident``, ``icao_code`` and
    ``gps_code``; a code that names two airports is dropped."""
    seen: dict[str, list[dict[str, str]]] = {}
    with path.open(encoding="utf8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["iso_country"] != "BR":
                continue
            entry = {"municipality": row["municipality"], "uf": row["iso_region"][3:], "lat": row["latitude_deg"],
                     "lon": row["longitude_deg"], "from": "ourairports_airports.csv"}
            for code in {row["ident"], row["icao_code"], row["gps_code"]} - {""}:
                seen.setdefault(code.upper(), []).append(entry)
    return {code: hits[0] for code, hits in seen.items() if len(hits) == 1}


def _remote(url: str) -> dict[str, str]:
    """What the server holds now. gov.br refuses HEAD (403), so the first byte is asked for instead."""
    try:
        answer = transport.request(url, method="HEAD")
        size = answer.headers.get("Content-Length", "")
    except transport.SourceAbsent:
        answer = transport.request(url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"})
        size = answer.headers.get("Content-Range", "").rsplit("/", 1)[-1]
    return {"last_modified": answer.headers.get("Last-Modified", ""), "content_length": size, "etag": answer.headers.get("ETag", "")}


#: Windows of the held file compared with the server's to tell a new release from a re-stamped one (ANAC rewrites the
#: statistics file with a new date line and a new Last-Modified on days the data does not change: 2026-10-25 and
#: 2026-11-05 held the same 361,057,599 bytes after the first line)
SAMPLES, SAMPLE_BYTES = 16, 1 << 16


def _changed(url: str, path: Path) -> bool:
    """Whether the server's file differs from ``path`` beyond its first line (the date): its size, or any of `SAMPLES`
    ranged windows spread over the rest."""
    size = path.stat().st_size
    if str(size) != _remote(url)["content_length"]:
        return True
    with path.open("rb") as held:
        first = len(held.readline())
        for k in range(SAMPLES):
            start = first + (size - first - SAMPLE_BYTES) * k // (SAMPLES - 1)
            held.seek(start)
            mine = held.read(SAMPLE_BYTES)
            theirs = transport.request(url, headers={"Range": f"bytes={start}-{start + len(mine) - 1}",
                                                      "Accept-Encoding": "identity"}).content
            if theirs != mine:
                return True
    return False


def _anuario(folder: Path) -> dict[str, dict[int, int]]:
    """Domestic paid passengers per year, from each Anuário edition's own table: `edition -> {year: passengers}`."""
    import openpyxl

    def sheet(name: str, member: str, title: str) -> list[list[Any]]:
        with zipfile.ZipFile(folder / name) as z:
            data = z.read(next(n for n in z.namelist() if n.lower().endswith(".xlsx")))
        ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)[member]
        ws.reset_dimensions()   # these workbooks declare dimension A1, which a read-only pass would honour
        rows = [[c for c in r if c is not None] for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
        assert any(title in str(c).lower() for r in rows[:4] for c in r), (name, member, rows[:2])
        return rows

    out: dict[str, dict[int, int]] = {}
    rows = sheet("anuario_2019.zip", "Fig 3.1", "passageiros pagos")        # Ano, Doméstica, Internacional, Total
    out["Anuário 2019"] = {int(r[0]): int(r[1]) for r in rows if isinstance(r[0], int) and len(r) >= 4 and isinstance(r[1], int)}
    rows = sheet("anuario_2022.zip", "Fig 3.7", "passageiros pagos - mercado doméstico")   # ano, natureza, passageiros pagos
    out["Anuário 2022"] = {int(r[0]): int(r[2]) for r in rows if isinstance(r[0], int) and len(r) == 3}
    return out


def build(root: str | Path | None = None, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Download ANAC's statistics and aerodrome registers once into ``<root>/registries/anac/`` and write
    ``<root>/registries/mobility/air_passengers.parquet`` (``from``, ``to``, ``weight``, ``kind``, ``vintage``, ``flights``,
    ``passengers_paid``, ``passengers_free``); returns the report."""
    say = log or (lambda _: None)
    base = load_settings(root=root).registries_dir
    raw, out = base / "anac", base / "mobility"
    raw.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    held_path = raw / "provenance.json"
    held: dict[str, Any] = json.loads(held_path.read_text(encoding="utf8")) if held_path.is_file() else {}
    refreshed = False
    if (raw / "Dados_Estatisticos.csv").is_file() and _changed(STATS_URL, raw / "Dados_Estatisticos.csv"):
        say("ANAC has released new statistics: downloading them")
        fresh = transport.download(STATS_URL, raw / "Dados_Estatisticos.csv.new")
        fresh.replace(raw / "Dados_Estatisticos.csv")
        held.pop("Dados_Estatisticos.csv", None)
        refreshed = True
    for name, url in SOURCES.items():
        if name not in held or not (raw / name).is_file():
            meta = _remote(url)             # read before the bytes: what the server held when they were taken
            if not (raw / name).is_file():
                say(f"downloading {name}")
                transport.download(url, raw / name)
            held[name] = {"url": url, **meta, "bytes": (raw / name).stat().st_size}
    write_json_atomic(held, held_path, indent=1, ensure_ascii=False)

    ufs = _uf_sigla_by_name()
    registered = _register(raw / "AerodromosPrivados.csv", ufs)
    registered.update(_register(raw / "AerodromosPublicos.csv", ufs))        # a public entry outranks a private one

    con = duckdb.connect()
    con.execute(f"""CREATE VIEW stats AS SELECT * FROM read_csv('{(raw / "Dados_Estatisticos.csv").as_posix()}', delim=';', quote='"',
                    header=true, skip=1, all_varchar=true, encoding='utf-8')""")
    cast = lambda c: f"TRY_CAST({c} AS BIGINT)"  # noqa: E731
    bad = con.execute("SELECT count(*) FROM stats WHERE " + " OR ".join(  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row
        f"({c} <> '' AND {cast(c)} IS NULL)" for c in ("PASSAGEIROS_PAGOS", "PASSAGEIROS_GRATIS", "DECOLAGENS", "ANO", "MES"))).fetchone()[0]
    con.execute(f"""CREATE TABLE legs AS SELECT {cast('ANO')} AS y, {cast('MES')} AS m,
        AEROPORTO_DE_ORIGEM_SIGLA AS o, AEROPORTO_DE_DESTINO_SIGLA AS d,
        AEROPORTO_DE_ORIGEM_NOME AS o_name, AEROPORTO_DE_ORIGEM_UF AS o_uf, AEROPORTO_DE_DESTINO_NOME AS d_name, AEROPORTO_DE_DESTINO_UF AS d_uf,
        AEROPORTO_DE_ORIGEM_PAIS = 'BRASIL' AND AEROPORTO_DE_DESTINO_PAIS = 'BRASIL' AS br, NATUREZA AS nat, GRUPO_DE_VOO AS grp,
        coalesce({cast('PASSAGEIROS_PAGOS')}, 0) AS paid, coalesce({cast('PASSAGEIROS_GRATIS')}, 0) AS free,
        coalesce({cast('DECOLAGENS')}, 0) AS dep FROM stats""")
    total_rows = con.execute("SELECT count(*) FROM legs").fetchone()[0]  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row
    months = con.execute("SELECT min(y*100+m), max(y*100+m), count(DISTINCT y*100+m) FROM legs").fetchone()
    # Each leg names its airports' city and UF as well as their code. ANAC reuses a code for another aerodrome over the
    # years (SNQY: JUAZEIRO DO NORTE/CE in the file, an airfield of Ribeirão Preto in OurAirports today), so a placement
    # by coordinates holds only for the legs whose named city is the placed municipality or a neighbour of it (the
    # commercial city: CURITIBA for the airport in São José dos Pinhais); a named city that is not a municipality checks
    # the UF only. A code's other legs stay unplaced.
    named = con.execute("""SELECT o, o_name, o_uf FROM legs WHERE br UNION SELECT d, d_name, d_uf FROM legs WHERE br""").fetchall()
    used = sorted({a for a, _, _ in named})
    others = _ourairports(raw / "ourairports_airports.csv")
    located = {a: registered.get(a) or others[a] for a in used if a in registered or a in others}
    codes, how = place_points([v["lon"] for v in located.values()], [v["lat"] for v in located.values()], root=root)
    at = {a: c for a, c in zip(located, codes, strict=True) if c}
    pack = {row["code7"]: row for row in municipalities().values()}
    by_name: dict[tuple[str, str], list[str]] = {}
    for row in pack.values():
        by_name.setdefault((fold(row["name"]), row["uf_sigla"]), []).append(row["code7"])
    edges = proximity_graph("contiguity")
    neighbours: dict[str, set[str]] = {}
    for a, b in zip(edges.column("from").to_pylist(), edges.column("to").to_pylist(), strict=True):
        neighbours.setdefault(a, set()).add(b)
    keys: list[tuple[str, str, str, str]] = []
    verdicts: dict[str, int] = {}
    unplaced_why: dict[tuple[str, str, str], str] = {}
    for icao, name, uf in named:
        code = at.get(icao)
        city = by_name.get((fold(name or ""), uf), [])
        if code is None:
            verdict = "no coordinates" if icao not in located else "coordinates in no municipality"
        elif len(city) == 1:
            verdict = "named city" if code == city[0] else "neighbour of the named city" if code in neighbours.get(city[0], ()) else "contradicts the named city"
        else:
            verdict = "same UF (named city not a municipality)" if pack[code]["uf_sigla"] == uf else "contradicts the named UF"
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        if verdict in ("named city", "neighbour of the named city", "same UF (named city not a municipality)"):
            keys.append((icao, name, uf, typing.cast(str, code)))
        else:
            where = located.get(icao)
            unplaced_why[(icao, name, uf)] = verdict + (f": {where['lat']}, {where['lon']} ({where['from']})" + (f" in {pack[code]['name']}/{pack[code]['uf_sigla']}" if code else "") if where else "")
    placement = {
        "airports_in_brazilian_legs": len(used), "with_coordinates": len(located), "in_a_municipality": len(at),
        "coordinates_from": {k: sum(1 for a in at if located[a]["from"] == k) for k in sorted({v["from"] for v in located.values()})},
        "placed_by": {k: sum(1 for c, h in zip(codes, how, strict=True) if c and h == k) for k in set(how) - {None}},
        "airport_names_checked": verdicts,
    }
    con.register("airport_code", pa.table({"icao": [k[0] for k in keys], "name": [k[1] for k in keys], "uf": [k[2] for k in keys],
                                           "code7": [k[3] for k in keys]}))

    def per_year(where: str) -> dict[int, int]:
        return {y: int(v) for y, v in con.execute(f"SELECT y, sum(paid+free) FROM legs WHERE {where} GROUP BY y ORDER BY y").fetchall()}

    international = per_year("NOT br")
    domestic_geo = per_year("br")
    by_nature = {n: int(v) for n, v in con.execute("SELECT nat, sum(paid+free) FROM legs WHERE br GROUP BY nat").fetchall()}
    by_group = {n: int(v) for n, v in con.execute("SELECT grp, sum(paid+free) FROM legs WHERE br GROUP BY grp").fetchall()}

    con.execute("""CREATE TABLE br_legs AS SELECT l.*, a.code7 AS cf, b.code7 AS ct FROM legs l
        LEFT JOIN airport_code a ON a.icao = l.o AND a.name IS NOT DISTINCT FROM l.o_name AND a.uf IS NOT DISTINCT FROM l.o_uf
        LEFT JOIN airport_code b ON b.icao = l.d AND b.name IS NOT DISTINCT FROM l.d_name AND b.uf IS NOT DISTINCT FROM l.d_uf WHERE l.br""")
    unplaced = con.execute("""SELECT ap, nm, uf, sum(p) AS pax, count(*) AS legs FROM (
        SELECT o AS ap, o_name AS nm, o_uf AS uf, paid+free AS p FROM br_legs WHERE cf IS NULL
        UNION ALL SELECT d, d_name, d_uf, paid+free FROM br_legs WHERE ct IS NULL) GROUP BY ALL ORDER BY pax DESC""").fetchall()
    unplaced_pax = int(con.execute("SELECT coalesce(sum(paid+free), 0) FROM br_legs WHERE cf IS NULL OR ct IS NULL").fetchone()[0])  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row
    same = int(con.execute("SELECT coalesce(sum(paid+free), 0) FROM br_legs WHERE cf = ct").fetchone()[0])  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row
    kept = con.execute(f"""SELECT cf AS "from", ct AS "to", sum(paid+free)::DOUBLE AS weight, '{KIND}' AS kind, (y*100+m)::INTEGER AS vintage,
        sum(dep)::BIGINT AS flights, sum(paid)::BIGINT AS passengers_paid, sum(free)::BIGINT AS passengers_free
        FROM br_legs WHERE cf IS NOT NULL AND ct IS NOT NULL AND cf <> ct GROUP BY ALL ORDER BY vintage, "from", "to" """).fetch_arrow_table()
    kept = kept.cast(pa.schema([("from", pa.string()), ("to", pa.string()), ("weight", pa.float64()), ("kind", pa.string()),
                                ("vintage", pa.int32()), ("flights", pa.int64()), ("passengers_paid", pa.int64()),
                                ("passengers_free", pa.int64())]))
    target = out / "air_passengers.parquet"
    write_parquet_atomic(kept, target, compression="zstd")
    kept_year = {y: int(v) for y, v in con.execute("SELECT y, sum(paid+free) FROM br_legs WHERE cf IS NOT NULL AND ct IS NOT NULL AND cf <> ct GROUP BY y ORDER BY y").fetchall()}

    dom_paid = {y: int(v) for y, v in con.execute("SELECT y, sum(paid) FROM legs WHERE nat = 'DOMÉSTICA' GROUP BY y ORDER BY y").fetchall()}
    check: dict[str, dict[int, dict[str, float]]] = {}
    for edition, figures in _anuario(raw).items():
        check[edition] = {y: {"anuario": n, "csv_paid_domestic": dom_paid.get(y, 0), "difference": dom_paid.get(y, 0) - n,
                              "percent": round(100 * (dom_paid.get(y, 0) - n) / n, 3)} for y, n in sorted(figures.items())}
    report = {
        "file": str(target), "rows": kept.num_rows, "source_rows": total_rows, "months": {"first": months[0], "last": months[1], "count": months[2]},  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row
        "source": {n: {k: held[n][k] for k in ("last_modified", "content_length", "bytes")} for n in held},
        "statistics_refreshed": refreshed, "cells_neither_empty_nor_integer": int(bad),
        "weight": "passengers_paid + passengers_free (people carried on the stage)",
        "domestic_by_year": domestic_geo, "domestic_by_nature": by_nature, "domestic_by_group": by_group, "international_by_year": international,
        "assigned_by_year": kept_year, "same_municipality": same, "unplaced_passengers": unplaced_pax,
        "unplaced_airports": [{"icao": a, "named": f"{nm}/{uf}", "passengers": int(p), "legs": int(n),
                               "reason": unplaced_why.get((a, nm, uf))} for a, nm, uf, p, n in unplaced],
        "placement": placement, "register_airports": len(registered), "check": check,
    }
    write_json_atomic(report, raw / "air_passengers_report.json", indent=1, ensure_ascii=False, default=str)
    return report
