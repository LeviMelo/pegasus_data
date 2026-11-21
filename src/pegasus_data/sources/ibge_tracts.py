"""The Census 2022 by tract: who lives in each census tract, by sex and age, as IBGE publishes it (ADR-0203).

**The product** (IBGE, *Agregados por Setores Censitários*, ``SOURCE``; dictionary of 2026-05-20): one CSV per theme
for Brazil's 472,780 tracts. Two are read:

* **básico** (Windows-1252; "." is "not applicable", read as null): the tract's identity (``CD_SETOR``, 15 digits whose first 7 are the municipality; urban or
  rural situation ``SITUACAO``/``CD_SIT``, type, area in km², district, subdistrict, neighbourhood, urban nucleus, favela
  and urban community, agglomeration, intermediate and immediate regions, urban concentration) and all nine of its variables,
  ``v0001`` (residents) to ``v0009`` (households by kind), ``v0005`` (mean residents per occupied private household) and
  ``v0006`` (share of them imputed) as decimals; IBGE's dictionary has no other variable (no income) in this file;
* **demografia** (458,772 tracts, the ones with residents): ``V01006`` residents, ``V01007``/``V01008`` men and women,
  ``V01009``-``V01019`` men and ``V01020``-``V01030`` women in eleven bands (0-4, 5-9, 10-14, 15-19, 20-24, 25-29,
  30-39, 40-49, 50-59, 60-69, 70 or more).

**Disclosure.** IBGE suppresses a count that could identify someone and writes ``X``; it is a missing value with its
reason (``suppressed``), never a zero, and never filled from the tract's other counts (CLAUDE.md §6). IBGE's own municipal
file of the theme is the sum of the same published cells, so it falls short too; the tract's residents in the basic file
(``v0001``) are never suppressed, and the people the bands leave out are measured against them (`municipal_check`) and
reported, not spread.

Five more themes are read the same way (`tract_aggregates`): literacy (``alfabetizacao``, V00644-V01005), the household's
characteristics in three parts (``domicilio1`` V00001-V00089, ``domicilio2`` V00090-V00495, ``domicilio3`` V00496-V00643) and
colour or race (``cor_ou_raca``, V01317-V01411). Each is one wide table, a column per variable as IBGE publishes it (about
1.4 billion long rows would cost ten times the disk for nothing); an ``X`` is the only null, so null *is* the suppressed flag.
`tract_dictionary` carries each variable's theme, unit (people or households) and IBGE's own description, which states the
universe (IBGE publishes no separate universe field and none is inferred).

**Stored** once per data home in ``registries/ibge_tracts/``: the zips, ``tracts_2022.parquet`` (identity and counts),
``tract_population_2022.parquet`` (long: tract, sex, band, people, suppressed), ``tract_aggregates_<topic>_2022.parquet``
and ``tract_dictionary_2022.parquet``. The tract polygons are IBGE's tract
mesh with the basic counts, ``registries/ibge_points/tracts.gpkg`` (`tract_mesh`), where the points pack had kept it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from ..persist.kept import write_parquet_atomic
from ..semantics.curation import declared

SOURCE = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/"
FILES = {"basico": declared("published_tables.yml", "ibge_tracts", "basic_file"),
         "demografia": "Agregados_por_Setor_csv/Agregados_por_setores_demografia_BR.zip",
         "municipios_demografia": "Agregados_por_Municipio_csv/Agregados_por_municipios_demografia_BR.zip"}
#: The themes read wide: topic -> (zip under ``Agregados_por_Setor_csv/``, IBGE's theme name in the dictionary), declared in ``curation/published_tables.yml``
AGGREGATES = {k: tuple(v) for k, v in declared("published_tables.yml", "ibge_tracts", "aggregate_files").items()}
DICTIONARY_FILE = declared("published_tables.yml", "ibge_tracts", "dictionary_file")
MESH = "malha_com_atributos/setores/gpkg/BR/BR_setores_CD2022.gpkg"
#: The eleven bands of the demography file, as (from, to) in years; None is open
BANDS = ((0, 4), (5, 9), (10, 14), (15, 19), (20, 24), (25, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, None))
#: The variables of each sex's bands, in BANDS order (declared with the dictionary's source in ``curation/published_tables.yml``)
SEX_BANDS = declared("published_tables.yml", "ibge_tracts", "sex_band_variables")
COUNTS = ("v0001", "v0002", "v0003", "v0004", "v0007", "v0008", "v0009")
DECIMALS = ("v0005", "v0006")     # a mean and a share, written with a decimal comma
IDENTITY = ("CD_SETOR", "SITUACAO", "CD_SIT", "CD_TIPO", "AREA_KM2", "CD_MUN", "NM_MUN", "CD_DIST", "NM_DIST", "CD_SUBDIST",
            "NM_SUBDIST", "CD_BAIRRO", "NM_BAIRRO", "CD_NU", "NM_NU", "CD_FCU", "NM_FCU", "CD_AGLOM", "NM_AGLOM", "CD_RGINT", "NM_RGINT",
            "CD_RGI", "NM_RGI", "CD_CONCURB", "NM_CONCURB")

__all__ = ["BANDS", "build", "build_aggregates", "tract_aggregates", "tract_dictionary", "tract_mesh", "tract_population", "tracts"]


def _directory(root: str | Path | None) -> Path:
    from ..config import load_settings

    return load_settings(root=root).registry_dir("ibge_tracts")


def _csv(zip_path: Path, encoding: str) -> Any:
    """The one CSV of an IBGE zip as strings (a pyarrow table), every value kept as written."""
    import zipfile

    import pyarrow as pa
    import pyarrow.csv as pacsv

    with zipfile.ZipFile(zip_path) as archive:
        member = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        with archive.open(member) as handle:
            table = pacsv.read_csv(handle, read_options=pacsv.ReadOptions(encoding=encoding),
                                   parse_options=pacsv.ParseOptions(delimiter=";"),
                                   convert_options=pacsv.ConvertOptions(column_types={}, strings_can_be_null=False,
                                                                        auto_dict_encode=False, quoted_strings_can_be_null=False))
    return table.cast(pa.schema([pa.field(n, pa.string()) for n in table.column_names]))


def _count(column: Any) -> tuple[Any, Any]:
    """An IBGE count column as (int64 with nulls, suppressed flag): ``X`` is suppressed; any other non-number raises."""
    import pyarrow as pa
    import pyarrow.compute as pc

    suppressed = pc.equal(column, "X")
    numeric = pc.match_substring_regex(column, r"^[0-9]+$")
    odd = pc.invert(pc.or_(suppressed, numeric))
    if pc.any(odd).as_py():
        raise ValueError(f"unexpected values in an IBGE count: {pc.unique(pc.filter(column, odd)).to_pylist()[:5]}")
    value = pc.cast(pc.if_else(numeric, column, pa.scalar(None, pa.string())), pa.int64())
    return value, suppressed


def build(root: str | Path | None = None) -> dict[str, Any]:
    """Download the basic and demography files (once) and write the two tables. Returns the tracts, the residents in
    each file, the suppressed cells and the check of the tracts' sums against IBGE's municipal file."""
    import pyarrow as pa
    import pyarrow.compute as pc

    from ..transport import download

    directory = _directory(root)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {k: download(SOURCE + v, directory / Path(v).name, timeout=3600) for k, v in FILES.items()}

    basic = _csv(paths["basico"], "cp1252")
    columns: dict[str, Any] = {"tract": basic.column("CD_SETOR"), "municipality7": pc.utf8_slice_codeunits(basic.column("CD_SETOR"), 0, 7)}
    for name in IDENTITY[1:]:          # "." is IBGE's "not applicable" (a tract in no urban nucleus, a lagoon's municipality)
        column = basic.column(name)
        columns[name.lower()] = pc.if_else(pc.equal(column, "."), pa.scalar(None, pa.string()), column)
    columns["area_km2"] = pc.cast(pc.replace_substring(basic.column("AREA_KM2"), ",", "."), pa.float64())
    suppressed_basic = 0
    for name in COUNTS:
        value, suppressed = _count(basic.column(name))
        columns[name] = value
        suppressed_basic += int(pc.sum(suppressed).as_py() or 0)
    for name in DECIMALS:          # "0,0923": a decimal comma; "." is null
        column = pc.replace_substring(basic.column(name), ",", ".")
        columns[name] = pc.cast(pc.if_else(pc.equal(column, "."), pa.scalar(None, pa.string()), column), pa.float64())
    identity = pa.table(columns)
    # a tract code begins with its municipality's; the two lagoons (4300001, 4300002: no municipality) have none
    if pc.any(pc.fill_null(pc.not_equal(identity.column("municipality7"), identity.column("cd_mun")), False)).as_py():
        raise ValueError("a tract code does not begin with its municipality's")

    demo = _csv(paths["demografia"], "utf8")
    tract = demo.column("CD_setor")
    parts, suppressed_cells = [], 0
    for sex, names in SEX_BANDS.items():
        for (low, high), name in zip(BANDS, names, strict=True):
            value, suppressed = _count(demo.column(name))
            suppressed_cells += int(pc.sum(suppressed).as_py() or 0)
            n = len(tract)
            parts.append(pa.table({"tract": tract, "municipality7": pc.utf8_slice_codeunits(tract, 0, 7),
                                   "sex": pa.array([sex] * n), "age_from": pa.array([low] * n, pa.int16()),
                                   "age_to": pa.array([high] * n, pa.int16()), "people": pc.cast(value, pa.int32()),
                                   "suppressed": suppressed}))
    population = pa.concat_tables(parts).sort_by([("tract", "ascending"), ("sex", "ascending"), ("age_from", "ascending")])
    residents, residents_suppressed = _count(demo.column("V01006"))
    for table, name in ((identity, "tracts_2022.parquet"), (population, "tract_population_2022.parquet")):
        write_parquet_atomic(table, directory / name, compression="zstd")
    return {"tracts": identity.num_rows, "tracts_with_demography": len(tract),
            "residents_basic": int(pc.sum(identity.column("v0001")).as_py()),
            "residents_demography_unsuppressed": int(pc.sum(residents).as_py()),
            "tracts_residents_suppressed": int(pc.sum(residents_suppressed).as_py()),
            "sex_band_cells": population.num_rows, "sex_band_cells_suppressed": suppressed_cells,
            "basic_counts_suppressed": suppressed_basic, "aggregates": build_aggregates(root),
            "municipal_check": municipal_check(root)}


def _dictionary(root: str | Path | None) -> Any:
    """IBGE's dictionary of the tract aggregates (its xlsx, downloaded once) as a table: variable, topic, theme, unit, label."""
    import openpyxl
    import pyarrow as pa

    from ..transport import download

    path = download(SOURCE + DICTIONARY_FILE, _directory(root) / DICTIONARY_FILE, timeout=600)
    book = openpyxl.load_workbook(path, read_only=True)
    rows: list[dict[str, Any]] = [{"variable": str(r[1]).strip().upper(), "topic": "basico", "theme": str(r[0]).strip(), "unit": None,
                                   "label": str(r[2]).replace("\xa0", " ").strip()}
                                  for r in list(book["Dicionário Básico"].iter_rows(values_only=True))[1:] if r[1]]
    by_theme = {theme: topic for topic, (_, theme) in AGGREGATES.items()}
    for kind, theme, variable, label in list(book["Dicionário não PCT"].iter_rows(values_only=True))[1:]:
        if variable and theme in by_theme:
            rows.append({"variable": str(variable).strip(), "topic": by_theme[theme], "theme": theme,
                         "unit": {"Pessoas": "people", "Domicílio": "households"}.get(kind, kind),
                         "label": str(label).replace("\xa0", " ").strip()})
    return pa.Table.from_pylist(rows, schema=pa.schema([pa.field(n, pa.string()) for n in ("variable", "topic", "theme", "unit", "label")]))


def build_aggregates(root: str | Path | None = None) -> dict[str, Any]:
    """Read each wide theme (``AGGREGATES``) in batches into ``tract_aggregates_<topic>_2022.parquet`` (tract, municipality7 and
    one int32 column per variable, an ``X`` null) and write the dictionary. The header must be the dictionary's variables, in
    order. Returns per topic the tracts, variables, cells and suppressed cells."""
    import zipfile

    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.csv as pacsv
    import pyarrow.parquet as pq

    from ..persist.kept import write_atomic, write_parquet_atomic
    from ..transport import download

    directory = _directory(root)
    dictionary = _dictionary(root)
    write_parquet_atomic(dictionary, directory / "tract_dictionary_2022.parquet", compression="zstd")
    report: dict[str, Any] = {"dictionary_variables": dictionary.num_rows}
    for topic, (name, _) in AGGREGATES.items():
        archive_path = download(SOURCE + "Agregados_por_Setor_csv/" + name, directory / name, timeout=3600)
        expected = [v for v, t in zip(dictionary.column("variable").to_pylist(), dictionary.column("topic").to_pylist(), strict=True)
                    if t == topic]
        counts = {"tracts": 0, "cells": 0, "suppressed": 0}
        with zipfile.ZipFile(archive_path) as archive, archive.open(next(n for n in archive.namelist() if n.lower().endswith(".csv"))) as handle:
            first = handle.readline().decode("utf8").strip().split(";")
            tract_name, header = first[0].strip('"'), [c.strip('"') for c in first[1:]]
            if header != expected:
                raise ValueError(f"{name}: the header's variables are not the dictionary's {topic} variables")
            schema = pa.schema([pa.field("tract", pa.string()), pa.field("municipality7", pa.string())]
                               + [pa.field(v, pa.int32()) for v in header])
            reader = pacsv.open_csv(handle, read_options=pacsv.ReadOptions(block_size=32 << 20, column_names=[tract_name, *header]),
                                    parse_options=pacsv.ParseOptions(delimiter=";"),
                                    convert_options=pacsv.ConvertOptions(column_types={c: pa.string() for c in [tract_name, *header]},
                                                                         strings_can_be_null=False, quoted_strings_can_be_null=False))

            def _write(tmp: Path, reader: Any = reader, schema: Any = schema, header: list[str] = header,
                       tract_name: str = tract_name, counts: dict[str, int] = counts) -> None:
                with pq.ParquetWriter(tmp, schema, compression="zstd") as writer:
                    for batch in reader:
                        tract = batch.column(tract_name)
                        columns = [tract, pc.utf8_slice_codeunits(tract, 0, 7)]
                        for variable in header:
                            value, suppressed = _count(batch.column(variable))
                            columns.append(pc.cast(value, pa.int32()))
                            counts["suppressed"] += int(pc.sum(suppressed).as_py() or 0)
                        counts["tracts"] += batch.num_rows
                        counts["cells"] += batch.num_rows * len(header)
                        writer.write_table(pa.Table.from_arrays(columns, schema=schema))

            write_atomic(directory / f"tract_aggregates_{topic}_2022.parquet", _write)
        report[topic] = {**counts, "variables": len(expected), "suppressed_share": round(counts["suppressed"] / counts["cells"], 4)}
    return report


def municipal_check(root: str | Path | None = None) -> dict[str, Any]:
    """What suppression leaves out, measured two ways. IBGE's municipal demography file against the tracts' unsuppressed
    sums (it is built from the same cells, so a difference would be a reading error), and the tracts' residents
    (``v0001`` of the basic file, never suppressed) against the sum of their published sex-band cells: per municipality the
    people the bands leave out. Reported, never spread back."""
    import duckdb

    from ..transport import download

    directory = _directory(root)
    path = download(SOURCE + FILES["municipios_demografia"], directory / Path(FILES["municipios_demografia"]).name)
    con = duckdb.connect()
    con.register("m", _csv(path, "cp1252"))
    population = (directory / "tract_population_2022.parquet").as_posix()
    identity = (directory / "tracts_2022.parquet").as_posix()
    long = " UNION ALL ".join(f"SELECT CD_MUN AS municipality7, '{sex}' AS sex, {low} AS age_from, TRY_CAST({name} AS BIGINT) AS people FROM m"
                              for sex, names in SEX_BANDS.items() for (low, _), name in zip(BANDS, names, strict=True))
    file_row = con.execute(f"""WITH pub AS ({long}),
        tr AS (SELECT municipality7, sex, age_from, sum(people) AS people FROM read_parquet('{population}') GROUP BY ALL)
        SELECT sum(pub.people), sum(coalesce(tr.people, 0)), count(*) FILTER (WHERE pub.people <> coalesce(tr.people, 0))
        FROM pub LEFT JOIN tr USING (municipality7, sex, age_from)""").fetchone()
    short = con.execute(f"""WITH r AS (SELECT municipality7, sum(v0001) AS residents FROM read_parquet('{identity}')
                                       WHERE municipality7 NOT IN ('4300001', '4300002') GROUP BY 1),
        b AS (SELECT municipality7, sum(people) AS banded FROM read_parquet('{population}') GROUP BY 1)
        SELECT sum(residents), sum(coalesce(banded, 0)), count(*) FILTER (WHERE residents > coalesce(banded, 0)),
               count(*) FILTER (WHERE residents > 0 AND 1 - coalesce(banded, 0) / residents > 0.05),
               max(1 - coalesce(banded, 0) / residents) FILTER (WHERE residents > 0)
        FROM r LEFT JOIN b USING (municipality7)""").fetchone()
    return {"municipal_file_people": file_row[0], "tracts_unsuppressed_people": file_row[1], "cells_differing": file_row[2],  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row
            "residents": short[0], "residents_in_published_bands": short[1], "municipalities_short": short[2],  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row
            "municipalities_short_over_5pct": short[3], "largest_share_short": round(float(short[4] or 0), 4)}  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row


def _where(municipality: Any, uf: Any) -> str:
    clauses = []
    if municipality is not None:
        values = [str(v).strip() for v in ([municipality] if isinstance(municipality, (str, int)) else municipality)]
        from ..geography import place_municipalities

        placed = place_municipalities(values)
        if None in placed:
            raise ValueError(f"not municipality codes (6 or 7 digits naming a municipality): "
                             f"{[v for v, p in zip(values, placed, strict=True) if p is None]}")
        clauses.append("municipality7 IN (" + ",".join(repr(str(p)) for p in sorted(cast("set[str]", set(placed)))) + ")")
    if uf is not None:
        from ..config import UF_NUMERIC

        # a state by its IBGE code or its abbreviation: "AC" matched no tract and returned an empty table (2026-11-21)
        by_name = {name: code for code, name in UF_NUMERIC.items()}
        given = [str(s).strip().upper() for s in ([uf] if isinstance(uf, (str, int)) else uf)]
        states = [by_name.get(s, s) for s in given]
        unknown = [g for g, s in zip(given, states, strict=True) if s not in UF_NUMERIC]
        if unknown:
            raise ValueError(f"not states (an abbreviation such as AC or an IBGE code such as 12): {unknown}")
        clauses.append("substr(municipality7, 1, 2) IN (" + ",".join(repr(s) for s in states) + ")")
    return ("WHERE " + " AND ".join(clauses)) if clauses else ""


def _read(name: str, municipality: Any, uf: Any, root: str | Path | None) -> Any:
    import duckdb

    path = _directory(root) / name
    if not path.is_file():
        raise FileNotFoundError(f"the tract tables are not built in {path.parent}; run `pegasus-data tracts`")
    return duckdb.connect().execute(f"SELECT * FROM read_parquet('{path.as_posix()}') {_where(municipality, uf)}").to_arrow_table()


def tracts(*, municipality: Any = None, uf: Any = None, root: str | Path | None = None) -> Any:
    """The Census 2022 tracts (a pyarrow table): identity, urban/rural situation, area, the places they belong to and the
    basic counts (``v0001`` residents …), a suppressed count null."""
    return _read("tracts_2022.parquet", municipality, uf, root)


def tract_population(*, municipality: Any = None, uf: Any = None, root: str | Path | None = None) -> Any:
    """Residents of each tract by sex (``1`` men, ``2`` women) and age band (``age_from``, ``age_to``; 70+ open), long; a
    count IBGE suppressed is null with ``suppressed`` true, never 0."""
    return _read("tract_population_2022.parquet", municipality, uf, root)


def tract_aggregates(topic: str, variables: Any = None, *, municipality: Any = None, uf: Any = None,
                     root: str | Path | None = None) -> Any:
    """One theme of the Census 2022 tract aggregates (a pyarrow table, wide): ``tract``, ``municipality7`` and one int32 column per
    variable (``V00644`` ...), as IBGE publishes them. A count IBGE suppressed (``X``) is null, never 0, and is never filled.
    ``topic`` is ``alfabetizacao``, ``domicilio1``, ``domicilio2``, ``domicilio3`` or ``cor_ou_raca`` (the basic theme is
    `census_tracts`); ``variables`` selects columns by the dictionary's codes (`tract_dictionary`)."""
    if topic not in AGGREGATES:
        raise ValueError(f"unknown topic {topic!r}; one of {sorted(AGGREGATES)}")
    select = "*"
    if variables is not None:
        wanted = [variables] if isinstance(variables, str) else list(variables)
        known = set(tract_dictionary(topic, root=root).column("variable").to_pylist())
        if unknown := [v for v in wanted if v not in known]:
            raise ValueError(f"not variables of {topic!r} (see tract_dictionary({topic!r})): {unknown[:5]}")
        select = ", ".join(["tract", "municipality7", *wanted])
    import duckdb

    path = _directory(root) / f"tract_aggregates_{topic}_2022.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"the tract aggregates are not built in {path.parent}; run `pegasus-data tracts`")
    return duckdb.connect().execute(f"SELECT {select} FROM read_parquet('{path.as_posix()}') {_where(municipality, uf)}").to_arrow_table()


def tract_dictionary(topic: str | None = None, *, root: str | Path | None = None) -> Any:
    """IBGE's dictionary of the tract variables (a pyarrow table): ``variable``, ``topic``, IBGE's ``theme``, ``unit`` (people or
    households) and ``label``, IBGE's own description (it carries the universe: "Domicílios Particulares Permanentes Ocupados, ...").
    The basic theme's variables are ``V0001`` ... (the columns ``v0001`` of `census_tracts`)."""
    import duckdb

    path = _directory(root) / "tract_dictionary_2022.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"the tract dictionary is not built in {path.parent}; run `pegasus-data tracts`")
    where = "" if topic is None else f"WHERE topic = '{topic.replace(chr(39), '')}'"
    return duckdb.connect().execute(f"SELECT * FROM read_parquet('{path.as_posix()}') {where}").to_arrow_table()


def tract_mesh(*, municipality: Any = None, uf: Any = None, root: str | Path | None = None) -> Any:
    """IBGE's 2022 tract polygons (a GeoDataFrame, SIRGAS 2000), one row per tract (a tract in several pieces is merged:
    the file repeats its counts on each piece), from ``registries/ibge_points/tracts.gpkg`` (downloaded once)."""
    import geopandas as gpd

    from ..config import load_settings
    from ..transport import download

    path = download(SOURCE + MESH, load_settings(root=root).registry_dir("ibge_points", "tracts.gpkg"),
                    timeout=7200)
    where = _where(municipality, uf).replace("WHERE ", "").replace("municipality7", "CD_MUN") or None
    frame = gpd.read_file(path, where=where, columns=["CD_SETOR", "CD_MUN", "SITUACAO"])
    return frame.dissolve(by="CD_SETOR", aggfunc="first").reset_index()


#: The public names (`pegasus_data.tract_population`, `census_tracts`, `tract_aggregates`, `tract_dictionary`)
census_tracts = tracts
