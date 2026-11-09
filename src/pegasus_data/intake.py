"""Intake of the sources that are not on the DATASUS FTP: one mechanism, declared (ADR-0162).

A source is an entry of ``curation/intake.yml``: where it lives (the DEMAS open-data API, or files of the Portal de Dados
Abertos), the columns with their roles and code lists as the source's own dictionary gives them, the keys a context is served
by (a place and a period) and its measures, which are sums and counts and never means. This module reads a declaration and
does everything else, so a source adds no code:

* **Records first.** `build_source` lands the source's *records* in the lake as Parquet, every column kept: the raw value
  under the source's name (upper-cased, as the FTP datasets) and, where the declaration types the column (date, number,
  integer, year), the typed value under that name and the raw one beside it as ``<NAME>__RAW``. The conversion is streamed
  by DuckDB (``read_csv(..., all_varchar=true)`` into zstd Parquet; a zip member is extracted to a temporary file, never
  held in memory) and the file is deleted after it. The dataset is registered in the catalog as a family with one
  publication per file and year (a file filed by month, a ``months:`` pattern, is the publication of its month), the
  ontology folds in its system and series, and the curation loader folds in its column
  documentation (``semantics.curation``), so ``query("FA-HUM")`` and ``info()`` serve it like any FTP dataset. Where a source
  is itself an aggregate (a DEMAS endpoint that serves counts) the aggregate is the record.
* **Fields second.** The context fields (``fields:`` of the declaration) are sums and counts by place and period *derived
  from the lake records* and written to ``<lake>/fields/<field>/year=Y/``, where `fields.load_field` reads them, so
  ``contexts: auto`` finds them. A place that is not an IBGE municipality of the universe is *unallocated* (kept in the
  records, left out of the field, counted); a row without a date is year 0 (*undated*); an absent (place, period) is absent,
  not zero.
* **API** (`api_rows`, `read_slice`): paged by the declared style, every byte through `transport` (one request per interval
  per host, a browser User-Agent, backoff on transient failures, `SourceAbsent` at once on any other 4xx); a page whose list is
  present and empty is the end, an answer without the declared list raises. A filtered read is cached under
  ``<root>/registries/<source>`` (never an empty one, unless the declaration says ``cache_empty``); a source with
  ``snapshot: true`` (a current-stock endpoint) also lands every fresh read in the lake with its read date, so a history
  accrues from the first read.

**The landing contract** (ADR-0172): a unit (a file, an API piece, a snapshot) is *replaced*, never added to. It is converted
into a staging folder, counted against the file's own lines, and only then swapped into the lake in place of every part it
had in every schema family of its (system, series); the catalog rows follow in one transaction. A failure at any step leaves
the previous records and their catalog rows as they were; a unit's sidecar (`units/<key>.json`) is removed before the swap and
written after the registration, so a missing sidecar means "land again". An API piece that ended short of its size is
*incomplete* (the endpoint may grow) and is read again, unless the source is declared ``static: true``.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
import shutil
import zipfile
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .normalize.time import month_of, year_of
from .persist.lake import SLICE, unit_parts
from .textenc import fold
from .transport import SourceAbsent, download, get_json

__all__ = ["api_rows", "build_source", "check_source", "declared_sources", "land_snapshot", "read_slice", "register_periods", "rows_of", "url"]

#: Pages of an API read landed together as one unit.
PIECE_PAGES = 50
#: Columns above which a landing writes smaller row groups (see `_land`).
WIDE = 100
#: Declared types that get a typed column beside the raw one.
TYPED = ("date", "number", "integer", "year", "result")
#: A declared type that rewrites the column in place and keeps the value as filed beside it (`<NAME>__RAW`): ``int_code``, a
#: code filed as a float's text ('5.0' or '5.'; SRAG's CLASSI_FIN is '5.0' in the 2019 and 2020 files and '5' in the others), read as '5'.
#: A condition on it (`where`) reads the rewritten code.
REWRITTEN = ("int_code",)


def declared_sources(root: Path | None = None) -> dict[str, dict[str, Any]]:
    from .config import curation_root
    from .semantics.curation import read_yaml

    doc = read_yaml((root or curation_root()) / "intake.yml", missing_ok=True) or {}
    dictionaries = doc.get("dictionaries") or {}
    out = {}
    for name, spec in (doc.get("sources") or {}).items():
        shared = dictionaries.get(spec.get("dictionary_columns")) if spec.get("dictionary_columns") else None
        if spec.get("dictionary_columns") and shared is None:
            raise KeyError(f"intake.yml: {name} names the dictionary {spec['dictionary_columns']!r}, which is not declared")
        if shared:
            # a shared dictionary's columns are optional (a file holds those it holds); the source's own stay required
            spec = {**spec, "columns": {**{c: {**(d or {}), "optional": True} for c, d in shared.items()}, **(spec.get("columns") or {})}}
        out[name] = {**spec, "fields": _with_populations(spec.get("fields") or {})}
    return out


def _with_populations(fields: dict[str, Any]) -> dict[str, Any]:
    """A field that declares an ``outcome`` beside its ``where`` counts the records of its population (``where``) with
    the outcome; its population is a field of its own, ``<name>_assessed``, named as its denominator (``over``): samples
    with E. coli present over the samples assessed for E. coli, never over every analysis. The field keeps its ``outcome``
    and `_derive` counts it over the population's own groups, so it has a row (0 where none had the outcome) wherever its
    population has one: a place-month with samples and no positive is a true zero, one without samples is missing."""
    out: dict[str, Any] = {}
    for name, fs in fields.items():
        if not fs.get("outcome"):
            out[name] = fs
            continue
        # the population is a field of its own and names itself (`population_label`): it must not inherit its outcome's label
        population = {k: v for k, v in fs.items() if k not in ("outcome", "what", "label", "population_label")}
        out[f"{name}_assessed"] = {**population, "what": f"The population of {name}: {fs.get('what', '')}".strip(),
                                   **({"label": fs["population_label"]} if fs.get("population_label") else {})}
        out[name] = {**{k: v for k, v in fs.items() if k != "population_label"}, "over": f"{name}_assessed"}
    return out


def intake_fields(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """The fields the declarations define, in the shape of ``fields.yml`` entries (``source: intake``)."""
    out: dict[str, dict[str, Any]] = {}
    for name, spec in declared_sources(root).items():
        for field, fs in (spec.get("fields") or {}).items():
            # a field's years are its own, else its source's span (the period's valid years): a context is read on them
            years = fs.get("years") or spec.get("years") or (spec.get("period") or {}).get("valid") or ""
            # what the field says about itself to its readers (fields.yml's keys: `where`, the rows that make it one value
            # per place; `icd10`, `harm`...) is `declares`; the rest is derived from the declaration
            # a time-varying field says so: `grain: month` rows carry a `month`; its measures are sums and counts, so `law: sum`
            # is exact at every coarser grain (a year is the sum of its months, a numerator and its denominator alike)
            out[field] = {**({"grain": spec["period"]["grain"]} if (spec.get("period") or {}).get("grain") else {}),
                          **({"law": "sum"} if fs.get("measure") or fs.get("unpivot") else {}),
                          **(fs.get("declares") or {}),
                          "source": "intake", "intake": name, "unit": fs.get("unit", ""), "what": fs.get("what", spec.get("what", "")),
                          **({"label": fs["label"]} if fs.get("label") else {}),
                          "years": str(years), **({"over": fs["over"]} if fs.get("over") else {}),
                          # its strata as `load_field` names them (`_derive`)
                          **({"by": [alias for _, alias in _strata(fs)]} if fs.get("by") or fs.get("unpivot") else {})}
    return out


def ontology_nodes(root: Path | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """(systems, datasets) in the shape of ``ontology.yml``: each source with a ``system`` is a dataset ``<SYSTEM>.<series>``;
    the system's own names come from the sources that carry ``system_name``."""
    systems: dict[str, dict[str, Any]] = {}
    datasets: dict[str, dict[str, Any]] = {}
    for spec in declared_sources(root).values():
        if not spec.get("system"):
            continue
        code, series = str(spec["system"]).upper(), str(spec["series"]).upper()
        systems.setdefault(code, {"kind": "data", "crawled_as": [code]}).update(spec.get("system_name") or {})
        datasets[f"{code}.{series}"] = {"system": code, "official_name": spec.get("official_name"), "translated_name": spec.get("translated_name"),
                                        "what_it_is": spec.get("what"), "observed_as": [series]}
    return systems, datasets


def curation_docs(root: Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The documentation the declarations carry, as ``variables:`` and ``datasets:`` files of the curation loader: a column's
    ``description`` is its description, its ``codes`` the inline code list (served as ``CURATED.<SYSTEM>.<FIELD>``)."""
    variable_files, dataset_files = [], []
    for spec in declared_sources(root).values():
        if not spec.get("system"):
            continue
        system, series = str(spec["system"]).upper(), str(spec["series"]).upper()
        reference = spec.get("dictionary") or spec.get("citation")
        variables: dict[str, Any] = {}
        for column, decl in (spec.get("columns") or {}).items():
            body: dict[str, Any] = {"description": str((decl or {}).get("description") or column)}
            if (decl or {}).get("codes"):
                body["codes"] = decl["codes"]
            if (decl or {}).get("codelist"):
                # a standard or a DATASUS table the package ships (ICD10, CBO2002): the column's code system is external
                body["codelist"] = decl["codelist"]
                body["code_system"] = "external"
            if (decl or {}).get("label_from"):
                # the record names its own code in a sibling column (ADR-0090): no table to choose
                body["label_from"] = str(decl["label_from"]).upper()   # columns land upper-cased: the sibling's name too
                body["code_system"] = "internal"
            if (decl or {}).get("derived"):
                body["derived"] = decl["derived"]       # a column made from this one (SRAG's IDADE_anos from the age and its unit)
            if (decl or {}).get("type") in TYPED:
                body["notes"] = f"typed as {decl['type']}; the value as filed is {column.upper()}__RAW"
            elif (decl or {}).get("type") in REWRITTEN:
                body["notes"] = f"a code filed as a float's text is read as its integer ('5.0' as '5'); the value as filed is {column.upper()}__RAW"
            variables[column.upper()] = body
        variable_files.append({"system": system, "source": "layout_doc", "source_ref": reference, "variables": variables})
        dataset_files.append({"datasets": {f"{system}_{series}": {
            "system": system, "series": series, "what_one_row_is": spec.get("one_row") or spec.get("what"),
            "unit_of_analysis": spec.get("unit_of_analysis"), "known_biases": spec.get("known_biases"),
            "gotchas": spec.get("gotchas") or [], "use": spec.get("use"), "why_no_event_type": spec.get("why_no_event_type"),
            "source": "web", "source_ref": reference, "asserted_by": "pegasus_data"}}})
    return variable_files, dataset_files


def _cache(source: str, root: str | Path | None, *parts: str) -> Path:
    from .config import load_settings

    path = load_settings(root=root).registry_dir(source)
    for part in parts:
        path = path / part
    return path


def _digest(*objects: Any) -> str:
    return hashlib.sha1(json.dumps(objects, sort_keys=True, default=str, ensure_ascii=False).encode("utf8")).hexdigest()[:12]


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")


# --- the API ---------------------------------------------------------------------------------------------------------

def rows_of(answer: Any, key: str, where: str = "") -> list[dict]:
    """The list an answer carries under ``key``. A list that is present and empty is an empty page (the end of a read); an
    answer without the key (an error object, a renamed key, a maintenance page) is not an empty page and raises, naming the
    keys it has: a read must never end silently on an answer it did not understand."""
    if not isinstance(answer, dict) or key not in answer:
        seen = sorted(answer)[:20] if isinstance(answer, dict) else type(answer).__name__
        raise ValueError(f"{where or 'the answer'} has no {key!r} (the declared list of rows); it has: {seen}")
    return answer[key] or []


def _origin(spec: dict[str, Any], which: str = "origin") -> dict[str, Any]:
    origin = spec.get(which) or {}
    if origin.get("base") is None and origin.get("kind") == "api":
        from .config import DEMAS_BASE_URL

        origin = {**origin, "base": DEMAS_BASE_URL}
    return origin


def _paging(origin: dict[str, Any]) -> dict[str, Any]:
    return {"style": "offset", "limit_param": "limit", "offset_param": "offset", "size": 1000, "rows": "parametros", **(origin.get("paging") or {})}


def _pages(origin: dict[str, Any], path: str, params: dict[str, Any], start: int = 0) -> Iterator[list[dict]]:
    """The pages of one request. ``offset`` style (DEMAS): ``limit`` and a row ``offset`` until an empty page, because a short
    page is not the end where the limit is applied before de-duplication; ``page`` style (Compras.gov.br): page numbers up to
    the ``totalPaginas`` the answer states. An answer without the declared list (or, in ``page`` style, without the page
    count) raises (`rows_of`): only a list that is present and empty ends an offset read."""
    paging = _paging(origin)
    url = origin["base"].rstrip("/") + path
    if paging["style"] == "offset":
        offset = start
        while True:
            answer = get_json(url, {**params, paging["limit_param"]: paging["size"], paging["offset_param"]: offset})
            page = rows_of(answer, paging["rows"], url)
            if not page:
                return
            yield page
            offset += paging["size"]
    else:
        if not paging.get("pages_key"):
            raise KeyError(f"{url}: a `page` style origin must declare `pages_key`, the answer's count of pages")
        number = start // paging["size"] + 1
        while True:
            answer = get_json(url, {**params, paging["page_param"]: number, paging["size_param"]: paging["size"]})
            yield rows_of(answer, paging["rows"], url)
            if paging["pages_key"] not in answer:
                raise ValueError(f"{url}: the answer has no {paging['pages_key']!r} (the declared page count); it has: {sorted(answer)[:20]}")
            if number >= int(answer[paging["pages_key"]] or 0):
                return
            number += 1


def url(source: str, path: str | None = None) -> str:
    """The URL of a declared API source's endpoint (or of ``path`` under its base)."""
    origin = _origin(declared_sources()[source])
    return origin["base"].rstrip("/") + (path or origin["endpoint"])


def api_rows(source: str, path: str | None = None, params: dict[str, Any] | None = None, *, spec: dict[str, Any] | None = None) -> list[dict]:
    """Every row of one request of a declared API source (``path`` defaults to the declaration's ``endpoint``)."""
    spec = spec or declared_sources()[source]
    origin = _origin(spec)
    rows: list[dict] = []
    for page in _pages(origin, path or origin["endpoint"], params or {}):
        rows += page
    return rows


def _partition_values(level: dict[str, Any], params: dict[str, Any]) -> list[str]:
    """The values a partition parameter takes: IBGE's state codes (`uf_code`) or municipality codes (`municipality`, those of
    the state `within` names), from the geography pack."""
    from .geography import municipalities

    universe = municipalities()
    if level["values"] == "uf_code":
        return sorted({row["uf_code"] for row in universe.values()})
    if level["values"] == "uf_sigla":
        return sorted({row["uf_sigla"] for row in universe.values()})
    inside = str(params.get(level.get("within"), ""))
    return sorted(code for code in universe if code.startswith(inside))


def _complete(origin: dict[str, Any], path: str, params: dict[str, Any], partition: list[dict[str, Any]], unstable: list[str]) -> list[dict]:
    """Every row a filter matches, by partition rather than by offset where the table is not stable under paging.

    BNAFAR's stock table is read without an ORDER BY while it changes: the same request returns different rows, and
    consecutive 1,000-row pages overlapped by a third (TOXO programme, 2026-10-10: 3,862 rows paged, 2,572 and 2,807 distinct
    in two reads; split by state, 3,862 distinct and identical on a second read). A short first page is the whole answer
    (`short_page_is_end`, checked on every state of that read); a full one is split by the next partition parameter, and a
    slice still full after the last (or with none declared) is paged by offset and named in ``unstable`` so the table says it
    may be incomplete.
    """
    paging = _paging(origin)
    url = origin["base"].rstrip("/") + path
    first = rows_of(get_json(url, {**params, paging["limit_param"]: paging["size"], paging["offset_param"]: 0}), paging["rows"], url)
    if len(first) < paging["size"] and paging.get("short_page_is_end"):
        return first
    partition = [level for level in partition if level["param"] not in params]       # a filter already given is not split again
    if partition:
        level, rest = partition[0], partition[1:]
        rows: list[dict] = []
        for value in _partition_values(level, params):
            rows += _complete(origin, path, {**params, level["param"]: value}, rest, unstable)
        return rows
    unstable.append(json.dumps(params, sort_keys=True))
    return [r for page in _pages(origin, path, params) for r in page]


def _schema(spec: dict[str, Any]) -> pa.Schema:
    return pa.schema([(c, pa.float64() if (d or {}).get("type") == "number" else pa.string()) for c, d in spec["columns"].items()])


def _get(row: dict[str, Any], column: str) -> Any:
    """A row's value of a column; the API names its keys in lower case, so the lower-case key answers where the declared name
    (upper) is absent."""
    return row[column] if column in row else row.get(column.lower())


def _as_table(rows: list[dict], schema: pa.Schema, required: list[str] | tuple[str, ...] = ()) -> pa.Table:
    """Rows as a table of the declared schema. A declared column that is not optional and that no row carries raises: an API
    that renames or re-cases a column must not turn into a table of nulls (the bulk path's `_records_sql` raises too)."""
    absent = [c for c in required if rows and not any(c in r or c.lower() in r for r in rows)]
    if absent:
        raise KeyError(f"declared columns in no row of the answer: {absent}; the rows carry: {sorted({k for r in rows[:50] for k in r})[:30]}")
    clean = [{c: (None if _get(r, c) is None else (_get(r, c) if schema.field(c).type == pa.float64() else str(_get(r, c)))) for c in schema.names}
             for r in rows]
    return pa.Table.from_pylist(clean, schema=schema)


def _as_strings(rows: list[dict], columns: list[str] | None = None) -> pa.Table:
    """Rows as an all-string table over ``columns`` (default: every key seen, in order of appearance)."""
    names = columns or list(dict.fromkeys(k for r in rows for k in r))
    return pa.table({c: pa.array([None if _get(r, c) is None else str(_get(r, c)) for r in rows], pa.string()) for c in names})


def read_slice(source: str, filters: dict[str, Any], *, root: str | Path | None = None, name: str | None = None, refresh: bool = False) -> pa.Table:
    """The rows of a declared API source that match ``filters`` (the endpoint's own parameters), the declared columns only,
    kept in ``registries/<source>/<name>`` (``name`` defaults to ``slices/<hash of the filters>.parquet``). A source with a
    filter is never paged whole; a past period does not change, the current one does (``refresh``). A source that declares
    a ``partition`` is read by it (see `_complete`); the table's schema metadata ``intake_unstable`` lists the filters that
    could not be and were paged. An empty answer is returned and not kept, unless the declaration says ``cache_empty: true``
    (an empty answer may be a transient one; a kept one is final). With ``snapshot: true`` every fresh read is also landed
    in the lake, dated by its read day."""
    spec = declared_sources()[source]
    label = name or f"slices/{_digest(filters)}.parquet"
    target = _cache(source, root, *label.split("/"))
    if target.is_file() and not refresh:
        return pq.read_table(target)
    origin = _origin(spec)
    unstable: list[str] = []
    if origin.get("partition"):
        rows = _complete(origin, origin["endpoint"], filters, origin["partition"], unstable)
    else:
        rows = api_rows(source, params=filters, spec=spec)
    required = [c for c, d in spec["columns"].items() if not (d or {}).get("optional")]
    table = _as_table(rows, _schema(spec), required)
    if unstable:
        table = table.replace_schema_metadata({"intake_unstable": json.dumps(unstable)})
    if table.num_rows or spec.get("cache_empty"):
        target.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, target)
    if spec.get("snapshot") and table.num_rows:
        land_snapshot(source, table, label, datetime.now(UTC).date().isoformat(), root)
    return table


# --- the lake ----------------------------------------------------------------------------------------------------------

def _settings(root: str | Path | None = None) -> Any:
    from .config import load_settings

    return load_settings(root=Path(root)) if root else load_settings()


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sql_text(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _duck(settings: Any, spec: dict[str, Any]) -> Any:
    """A DuckDB connection bounded in memory, with the IBGE universe (and, for a source that gives a municipality's name and
    its state, the names that resolve to one code) registered."""
    import duckdb

    from .geography import municipalities

    con = duckdb.connect(":memory:")
    work = Path(settings.work_dir) / "duckdb"
    work.mkdir(parents=True, exist_ok=True)
    # a decode slot's share of the machine (`decode.admission`: total RAM over the slots), not a fixed 2 GB: SRAG's ~190
    # columns of text ran out of memory re-landing a year under 2 GB (the parquet writer's buffers do not spill, 2026-10-24)
    import psutil

    from .decode.admission import slot_count

    con.execute(f"SET memory_limit='{max(2, psutil.virtual_memory().total // slot_count() // 2**30)}GB'")
    con.execute("SET threads=4")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{work.as_posix()}'")
    from .geography import placing_rule

    # the one placing rule's facts (`geography.placing_rule`), as tables: the universe, a state of one municipality
    # (the Distrito Federal: Brasília, whatever the source calls the place: SISAGUA codes its administrative regions
    # 530000-530015), and the declared legacy codes (Rio de Janeiro's 3345xxx)
    universe = municipalities()
    rule = placing_rule()
    con.register("universe", pa.table({"code": pa.array(sorted(universe), pa.string())}))
    sole = {uf: str(code7)[:6] for uf, code7 in rule["sole"].items()}
    con.register("sole", pa.table({"uf": pa.array(list(sole), pa.string()), "code": pa.array(list(sole.values()), pa.string()),
                                   "sigla": pa.array([fold(universe[c]["uf_sigla"]) for c in sole.values()], pa.string())}))
    con.register("legacy", pa.table({"prefix": pa.array([p for p, _ in rule["legacy"]], pa.string()),
                                     "code": pa.array([str(c)[:6] if c else None for _, c in rule["legacy"]], pa.string())}))
    place = spec.get("place") or {}
    if place.get("type") == "municipality_name":
        keys: dict[tuple[str, str], str | None] = {}
        for code, row in universe.items():
            for state in (row["uf_sigla"], row["uf_name"]):
                key = (fold(state), fold(row["name"]))
                keys[key] = None if key in keys and keys[key] != code else code
        found = {k: v for k, v in keys.items() if v}
        con.register("names", pa.table({"key": pa.array([f"{u}|{n}" for (u, n) in found], pa.string()),
                                        "code": pa.array(list(found.values()), pa.string())}))
        con.create_function("fold", fold, ["VARCHAR"], "VARCHAR", null_handling="special")
    return con


def _typed(expr: str, decl: dict[str, Any]) -> str | None:
    """The SQL of a column's typed value from its raw (VARCHAR, NULL when empty) expression."""
    kind = decl.get("type")
    if kind == "date":
        value = f"substr({expr}, 1, {int(decl['take'])})" if decl.get("take") else expr
        formats = decl.get("formats") or [decl.get("format", "%Y-%m-%d")]
        # several declared formats (a column filed as 2023/01/17 in one table and 17/01/2023 in another): the first that reads
        tried = ", ".join(f"try_strptime({value}, '{f}')" for f in formats)
        return f"CAST(coalesce({tried}) AS DATE)" if len(formats) > 1 else f"CAST(try_strptime({value}, '{formats[0]}') AS DATE)"
    if kind == "number":
        return f"try_cast(replace({expr}, ',', '.') AS DOUBLE)" if decl.get("decimal") == "," else f"try_cast({expr} AS DOUBLE)"
    if kind in ("integer", "year"):
        return f"CAST(try_cast({expr} AS DOUBLE) AS BIGINT)"
    if kind == "int_code":
        # a code the source files as a float's text ('5.0', '5.', or '6.0000000000' from a decimal(38,10) column): the integer's digits.
        # The value as filed stays in `<NAME>__RAW`; a code with any other decimal part (or any text) is left as it is
        return f"regexp_replace({expr}, '^([0-9]+)\\.0*$', '\\1')"
    if kind == "result":
        # a measurement as filed: a number only where it is one unambiguously (digits, a decimal comma); "1.544,00" and
        # the like (a dot of no fixed meaning) stay unparsed, never guessed; the flag says what the text is (`_flag`)
        return (f"CASE WHEN regexp_matches({expr}, '^-?[0-9]+(,[0-9]+)?$') "
                f"THEN CAST(replace({expr}, ',', '.') AS DOUBLE) END")
    return None


def _flag(expr: str, decl: dict[str, Any]) -> str:
    """A result's kind: ``numeric``, a declared token's meaning (``tokens: {MENOR_LD: below_ld, PRESENTE: present}``),
    ``censored`` for a leading "<", ``empty``, else ``unparsed``."""
    tokens = decl.get("tokens") or {}
    whens = "".join(f"WHEN upper({expr}) = '{str(k).upper()}' THEN '{v}' " for k, v in tokens.items())
    return (f"CASE WHEN {expr} IS NULL THEN 'empty' WHEN regexp_matches({expr}, '^-?[0-9]+(,[0-9]+)?$') THEN 'numeric' "
            f"{whens}WHEN starts_with({expr}, '<') THEN 'censored' ELSE 'unparsed' END")


def _records_sql(spec: dict[str, Any], columns: list[str], unit: dict[str, Any], source_path: str, read_on: str) -> str:
    """The SELECT that turns a relation ``raw`` (all VARCHAR, the source's own column names) into the lake's records."""
    declared = {c.upper(): (d or {}) for c, d in (spec.get("columns") or {}).items()}
    # a header is read under its canonical name: the declared name, or any of its ``aliases`` (another header generation
    # of the same column: "Código IBGE" for CO_MUNICIPIO_IBGE), compared without case, accents or punctuation
    alias = {}
    for name, d in declared.items():
        for spelling in [name, *(d.get("aliases") or [])]:
            alias[re.sub(r"[^A-Z0-9]", "", fold(spelling))] = name
    actual: dict[str, str] = {}
    for c in columns:
        clean = c.strip().lstrip("\ufeff")
        canonical = alias.get(re.sub(r"[^A-Z0-9]", "", fold(clean)), clean.upper())
        if canonical in actual:
            raise KeyError(f"{unit['key']}: two headers read as {canonical}: {actual[canonical]!r} and {c!r}")
        actual[canonical] = c
    missing = [c for c, d in declared.items() if c not in actual and not d.get("optional")]
    if missing:
        raise KeyError(f"{unit['key']}: declared columns absent from the file: {missing}")
    raw = {u: f"NULLIF(trim(raw.{_ident(c)}), '')" for u, c in actual.items()}
    out: list[str] = []
    for upper, expr in raw.items():
        decl = declared.get(upper, {})
        typed = _typed(expr, decl)
        if typed:
            out.append(f"{typed} AS {_ident(upper)}")
            out.append(f"{expr} AS {_ident(upper + '__RAW')}")
            if decl.get("type") == "result":
                out.append(f"{_flag(expr, decl)} AS {_ident(upper + '__FLAG')}")
        else:
            out.append(f"{expr} AS {_ident(upper)}")
    place, period = spec.get("place") or {}, spec.get("period") or {"type": "file"}
    joins = ""
    if place.get("type") == "municipality":
        text = f"regexp_replace({raw[place['column'].upper()]}, '\\.0+$', '')"
        out.append(f"CASE WHEN regexp_matches({text}, '^[0-9]{{6,7}}$') AND substr({text}, 1, 6) IN (SELECT code FROM universe) "
                   f"THEN substr({text}, 1, 6) WHEN regexp_matches({text}, '^[0-9]{{6,7}}$') "
                   f"THEN coalesce((SELECT code FROM sole WHERE sole.uf = substr({text}, 1, 2)), "
                   f"(SELECT code FROM legacy WHERE starts_with({text}, legacy.prefix) LIMIT 1)) END AS _MUNICIPALITY")
    elif place.get("type") == "municipality_name":
        joins = f" LEFT JOIN names ON names.key = fold({raw[place['uf'].upper()]}) || '|' || fold({raw[place['column'].upper()]})"
        out.append(f"coalesce(names.code, (SELECT code FROM sole WHERE sole.sigla = fold({raw[place['uf'].upper()]}))) "
                   "AS _MUNICIPALITY")
    elif place:
        out.append(f"{raw[place['column'].upper()]} AS {_ident('_' + (place.get('as') or place['column']).upper())}")
    kind = period.get("type", "file")
    if kind == "date":
        column = period["column"].upper()
        date = _typed(raw[column], declared[column])
        year, month = f"year({date})", f"month({date})"
    elif kind == "parts":
        y = f"regexp_replace({raw[period['year'].upper()]}, '\\.0+$', '')"
        year = f"CASE WHEN regexp_matches({y}, '^[0-9]{{4}}$') THEN CAST({y} AS INTEGER) END"
        m = f"regexp_replace({raw[period['month'].upper()]}, '\\.0+$', '')" if period.get("month") else "NULL"
        # "01"-"09" as filed by SISAGUA and SNGPC are months; read without the zero they landed as no month (PERIOD_DERIVATION)
        month = f"CASE WHEN regexp_matches({m}, '^(0?[1-9]|1[0-2])$') THEN CAST({m} AS INTEGER) END"
    elif kind == "month":
        ym = raw[period["column"].upper()]
        year = f"CASE WHEN regexp_matches({ym}, '^[0-9]{{6}}$') THEN CAST(substr({ym}, 1, 4) AS INTEGER) END"
        month = f"CASE WHEN regexp_matches({ym}, '^[0-9]{{6}}$') THEN CAST(substr({ym}, 5, 2) AS INTEGER) END"
    elif kind == "year":
        y = f"regexp_replace({raw[period['column'].upper()]}, '\\.0+$', '')"
        year, month = f"CASE WHEN regexp_matches({y}, '^[0-9]{{4}}$') THEN CAST({y} AS INTEGER) END", "NULL"
    else:                                            # the file's own year
        year, month = (str(int(unit["year"])) if unit.get("year") else "NULL"), "NULL"
    out.append(f"CAST({month} AS INTEGER) AS _MONTH")
    out.append(f"'{source_path}' AS _SOURCE_PATH")
    out.append(f"'{read_on}' AS _READ_ON")
    out.append(f"CAST(COALESCE({year}, 0) AS INTEGER) AS year")
    return "SELECT " + ", ".join(out) + f" FROM raw{joins}"


class _LostRecords(ValueError):
    """The records a landing wrote are fewer (or more) than the source's own lines: nothing was swapped in."""


def _land(settings: Any, source: str, spec: dict[str, Any], unit: dict[str, Any], con: Any, relation: str, read_on: str, *,
          sidecar: Path | None = None, expect_rows: int | None = None) -> dict[str, Any]:
    """Convert one relation of the source's rows to lake records (partitioned by record year) and *replace the unit* with them
    (ADR-0172): converted into a staging folder, counted (against ``expect_rows``, the independent figure, when given), and only
    then swapped in for the unit's parts in every family of the dataset and registered in the catalog. A failure before the
    swap leaves the lake and the catalog as they were. ``relation`` is a DuckDB table function or view of the rows; ``sidecar``
    is the unit's cache note, removed just before the swap. Returns the unit's statistics."""
    from .persist.lake import Lake

    con.execute(f"CREATE OR REPLACE VIEW raw0 AS SELECT * FROM {relation}")
    columns = [r[0] for r in con.execute("DESCRIBE raw0").fetchall()]
    # A header ending in a separator makes the parser name an empty column "columnN": dropped when it holds nothing.
    columns = [c for c in columns if not (re.fullmatch(r"column\d+", c) and con.execute(f"SELECT count({_ident(c)}) FROM raw0").fetchone()[0] == 0)]
    con.execute("CREATE OR REPLACE VIEW raw AS SELECT " + ", ".join(f"CAST({_ident(c)} AS VARCHAR) AS {_ident(c)}" for c in columns) + " FROM raw0")
    sql = _records_sql(spec, columns, unit, unit["path"], read_on)
    described = [(r[0], r[1]) for r in con.execute(f"DESCRIBE {sql}").fetchall() if r[0] != "year"]
    signature = hashlib.sha256(json.dumps(described).encode()).hexdigest()[:16]
    system, series = str(spec["system"]).upper(), str(spec["series"]).upper()
    family = f"{system}_{series}_{signature[:10]}"
    lake = Lake(settings.lake_dir)
    target = lake.family_dir(system, family, signature) / "uf=BR"
    key = _safe(unit["key"])
    # staged beside the working files, never inside a family: readers glob every parquet under a family folder
    staging = Path(settings.work_dir) / "intake" / f"{family}-{key}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.parent.mkdir(parents=True, exist_ok=True)
    # A row group is built in memory by each thread: INEP's school table (408 columns) ran the 2 GB limit out at 20,000 rows a
    # group on four threads. A table wider than a hundred columns writes groups of about three million cells, on two threads.
    wide = len(described) > WIDE
    group = max(2048, 3_000_000 // len(described)) if wide else 262144
    if wide:
        con.execute("SET threads=2")
    # Rows written in place and month order: like rows sit together, so zstd stores them about 30% smaller (SI-PNI's June
    # 2020: 489 MB unsorted, 344 MB sorted, nothing removed or changed), and a query for one municipality skips the row
    # groups whose statistics exclude it. The order is the lake's own derived keys, which every placed or dated source has.
    names = {n for n, _ in described}
    order = [k for k in ("_MUNICIPALITY", "_MONTH") if k in names]
    if order:
        sql = f"SELECT * FROM ({sql}) ORDER BY {', '.join(order)}"
    try:
        con.execute(f"COPY ({sql}) TO '{staging.as_posix()}' (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (year), "
                    f"FILENAME_PATTERN 'part-{key}-{{i}}', OVERWRITE_OR_IGNORE true, ROW_GROUP_SIZE {group})")
        staged = sorted(staging.glob(f"year=*/part-{key}-*.parquet"))
        place = spec.get("place") or {}
        placed = place.get("type") in ("municipality", "municipality_name")
        raw_place = _ident((place.get("column") or "").upper())
        stats = {"rows": 0, "undated": 0, "unplaced": 0, "unallocated": 0}
        if staged:
            select = "count(*), count_if(year = 0)"
            if placed:
                select += f", count_if({raw_place} IS NULL), count_if({raw_place} IS NOT NULL AND _MUNICIPALITY IS NULL)"
            pattern = (staging / "year=*" / f"part-{key}-*.parquet").as_posix()
            row = con.execute(f"SELECT {select} FROM read_parquet('{pattern}', hive_partitioning=true)").fetchone()
            stats.update(rows=row[0], undated=row[1], unplaced=row[2] if placed else 0, unallocated=row[3] if placed else 0)
        landed = {n for n, _ in described}
        typed = [c.upper() for c, d in (spec.get("columns") or {}).items()
                 if (d or {}).get("type") in ("date", "number", "integer", "year") and f"{c.upper()}__RAW" in landed]
        if staged and typed:
            # a value that is there and that its declared type does not read (a date as 31/02, a count as "n/d") is null in the
            # typed column and kept in `__RAW`: counted per column, never silent
            pattern = (staging / "year=*" / f"part-{key}-*.parquet").as_posix()
            counts = con.execute("SELECT " + ", ".join(f"count_if({_ident(c + '__RAW')} IS NOT NULL AND {_ident(c)} IS NULL)" for c in typed)
                                 + f" FROM read_parquet('{pattern}', hive_partitioning=true)").fetchone()
            unparsed = {c: n for c, n in zip(typed, counts, strict=True) if n}
            if unparsed:
                stats["unparsed"] = unparsed
        if expect_rows is not None and stats["rows"] != expect_rows:
            raise _LostRecords(f"{source} {unit['key']}: {stats['rows']} records landed from {expect_rows} lines")
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    parts = _commit(settings, source, spec, unit, key, staging=staging, target=target, family=family, signature=signature,
                    names=[n for n, _ in described], sidecar=sidecar)
    return {**stats, "years": sorted({int(p.parent.name.split("=")[1]) for p in parts}), "family": family}


def _prune(folder: Path, stop: Path) -> None:
    """Remove ``folder`` and its parents below ``stop`` while they are empty."""
    while folder != stop and stop in folder.parents:
        try:
            folder.rmdir()
        except OSError:
            return
        folder = folder.parent


def _commit(settings: Any, source: str, spec: dict[str, Any], unit: dict[str, Any], key: str, *, staging: Path, target: Path,
            family: str, signature: str, names: Sequence[str], sidecar: Path | None) -> list[Path]:
    """The swap of a landing (ADR-0172): the unit's cache note goes first (a unit with no note is landed again), then its parts
    in *every* schema family of (system, series) (a unit re-landed under another signature must not stay in the old family and
    count twice), then the staged parts move into ``target``, then the catalog follows. Returns the parts now in the lake."""
    system, series = str(spec["system"]).upper(), str(spec["series"]).upper()
    lake_root = Path(settings.lake_dir)
    if sidecar is not None:
        sidecar.unlink(missing_ok=True)
    mine = re.compile(rf"^part-{re.escape(key)}-\d+\.parquet$")
    kind = re.compile(rf"^{re.escape(system)}_{re.escape(series)}_[0-9a-f]{{10}}$")      # the dataset's families, not a series that starts alike
    if (lake_root / system).is_dir():
        for folder in sorted(p for p in (lake_root / system).iterdir() if p.is_dir() and kind.match(p.name)):
            for old in folder.glob("schema_signature=*/uf=BR/year=*/part-*.parquet"):
                if mine.match(old.name):
                    old.unlink()
                    _prune(old.parent, lake_root / system)
    parts: list[Path] = []
    for staged in sorted(staging.glob("year=*/*.parquet")):
        destination = target / staged.parent.name / staged.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), str(destination))
        parts.append(destination)
    shutil.rmtree(staging, ignore_errors=True)
    _register(settings, source, spec, unit, key, family, signature, list(names), parts, lake_root)
    return parts


def _dated(unit: dict[str, Any], year: int) -> tuple[str, str, int]:
    """``(date_code, date_format, normalized_date)`` of the publication of ``unit`` for the records of ``year``: the unit's
    own month (``YYYYMM``) when it is filed by month (a ``months`` pattern, `_units`) and ``year`` is the year of that
    month; else the year (``YYYY``, normalised ``year * 100``).

    A publication is dated by the period its file is filed for, which is what the planner selects by (its resolution, the
    part files a month's query opens), never read back from the records' own month column. Records of a monthly unit dated
    in another year are a publication of that year, at year resolution, so a month's query does not serve them."""
    month = int(unit.get("month") or 0)
    if month_of(month) and year_of(month) == year:
        return str(month), "YYYYMM", month
    return str(year), "YYYY", year * 100


def register_periods(settings: Any, source: str | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Date the catalog's publications of the declared file sources by their units' periods (`_dated`), landing nothing.

    A unit is dated when it is registered (`_register`); the units registered before a month was one of its facts are dated
    here, from the declaration, and the lake is not touched: one UPDATE of ``file_facts`` per publication whose date differs.
    Idempotent, and it goes both ways (a source declared by months again by years is dated by year again). ``dry_run`` counts.
    Returns, per source, the publications read and the ones dated differently."""
    from .catalog.store import CatalogStore

    out: dict[str, Any] = {}
    store = CatalogStore(settings.catalog_path)
    try:
        with store.write() as conn:
            for name, spec in declared_sources().items():
                if (source and name != source) or _origin(spec)["kind"] != "files":
                    continue
                read, changed = 0, 0
                for unit in _units(spec, None):
                    prefix = f"{unit['path']}{SLICE}"
                    for path, year, date in conn.execute("SELECT path, year, normalized_date FROM file_facts WHERE grammar='intake' "
                                                         "AND path >= ? AND path < ?", (prefix, prefix + "\x7f")).fetchall():
                        read += 1
                        code, form, dated = _dated(unit, int(year))
                        if dated != date:
                            changed += 1
                            if not dry_run:
                                conn.execute("UPDATE file_facts SET date_code=?, date_format=?, normalized_date=? WHERE path=?",
                                             (code, form, dated, path))
                out[name] = {"publications": read, "dated": changed}
    finally:
        store.close()
    return out


def _register(settings: Any, source: str, spec: dict[str, Any], unit: dict[str, Any], key: str, family: str, signature: str,
              names: list[str], parts: list[Path], lake_root: Path) -> None:
    """Catalog rows that make the lake records a dataset ``query`` plans over: the family, one publication (file facts) per
    unit and record year, dated by the unit's period (`_dated`), and the lake partitions that cover it. Replaces
    the unit: its partitions and publications in every family of (system, series) go first, a family left with no partition
    is dropped, and the dataset's family list is recomputed."""
    from .catalog.store import CatalogStore, utcnow

    system, series = str(spec["system"]).upper(), str(spec["series"]).upper()
    now = utcnow()
    mine = re.compile(rf"^part-{re.escape(key)}-\d+\.parquet$")
    prefix = f"{unit['path']}{SLICE}"
    by_year: dict[int, list[Path]] = {}
    for part in parts:
        by_year.setdefault(int(part.parent.name.split("=")[1]), []).append(part)
    store = CatalogStore(settings.catalog_path)
    try:
        with store.write() as conn:
            touched: set[str] = set()
            for (fam,) in conn.execute("SELECT family_id FROM families WHERE system=? AND series=?", (system, series)).fetchall():
                # LIKE only narrows (its `_` matches any character); the exact name decides
                held = conn.execute("SELECT relative_path FROM lake_partitions WHERE family_id=? AND relative_path LIKE ?",
                                    (fam, f"%/part-{key}-%")).fetchall()
                gone = [r[0] for r in held if mine.match(r[0].rsplit("/", 1)[-1])]
                if gone:
                    touched.add(fam)
                    conn.executemany("DELETE FROM lake_partitions WHERE family_id=? AND relative_path=?", [(fam, p) for p in gone])
            upper = prefix + "\x7f"                    # every `<unit>#year=<digits>`
            before = conn.execute("SELECT family_id, path FROM family_files WHERE path >= ? AND path < ?", (prefix, upper)).fetchall()
            conn.execute("DELETE FROM family_files WHERE path >= ? AND path < ?", (prefix, upper))
            touched |= {r[0] for r in before}
            published: set[str] = set()
            for year, files in sorted(by_year.items()):
                path = f"{prefix}{year}"
                if year:
                    # a dated year is a publication of the unit; the undated rows (year 0) are records in the lake and
                    # a listed partition (`load()` of every year returns them), never a publication a period can ask for
                    published.add(path)
                    conn.execute("INSERT OR REPLACE INTO files (path, logical_id, directory, filename, extension, size, modified, "
                                 "listing_method, change_signal, first_seen, last_seen, gone_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
                                 (path, path, unit["path"].rsplit("/", 1)[0], path.rsplit("/", 1)[-1],
                                  unit.get("extension", ""), int(unit.get("size") or 0), unit.get("modified"), "intake", "size", now, now))
                    code, form, dated = _dated(unit, year)
                    conn.execute("INSERT OR REPLACE INTO file_facts (path, system, series_prefix, geo_code, date_code, date_format, "
                                 "normalized_date, year, grammar, container_format, role, logical_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (path, system, series, "BR", code, form, dated, year, "intake", unit.get("extension", ""), "data", path))
                    conn.execute("INSERT OR REPLACE INTO family_files (family_id, path, member) VALUES (?,?,?)", (family, path, ""))
                for part in files:
                    conn.execute(
                        "INSERT OR REPLACE INTO lake_partitions (family_id, schema_signature, uf, year, relative_path, row_count, "
                        "byte_size, source_paths, written_at, build_fingerprint) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (family, signature, "BR", year, str(part.relative_to(lake_root)).replace("\\", "/"),
                         pq.read_metadata(part).num_rows, part.stat().st_size, json.dumps([path] if year else []), now,
                         unit.get("fingerprint")))
            # a year the unit no longer has is no longer a publication
            conn.executemany("DELETE FROM files WHERE path=?", [(p,) for p in {r[1] for r in before} - published])
            touched.add(family)
            for fam in sorted(touched):
                if not conn.execute("SELECT 1 FROM lake_partitions WHERE family_id=? LIMIT 1", (fam,)).fetchone():
                    conn.execute("DELETE FROM families WHERE family_id=?", (fam,))
                    conn.execute("DELETE FROM family_files WHERE family_id=?", (fam,))
                    continue
                years = [int(r[0]) for r in conn.execute("SELECT DISTINCT year FROM lake_partitions WHERE family_id=? AND year>0", (fam,))]
                files_n = conn.execute("SELECT count(*) FROM family_files WHERE family_id=?", (fam,)).fetchone()[0]
                if fam == family:
                    conn.execute("INSERT OR REPLACE INTO families (family_id, system, series, schema_signature, field_count, time_min, "
                                 "time_max, geo_coverage, file_count, stratum_count, schema_source, label, notes) "
                                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (fam, system, series, signature, len(names), min(years) if years else None, max(years) if years else None,
                                  '["BR"]', files_n, 0, "intake", None, f"intake: {source}"))
                else:
                    conn.execute("UPDATE families SET time_min=?, time_max=?, file_count=? WHERE family_id=?",
                                 (min(years) if years else None, max(years) if years else None, files_n, fam))
            ids = [r[0] for r in conn.execute("SELECT family_id FROM families WHERE system=? AND series=? ORDER BY family_id", (system, series))]
            dataset = f"{system}_{series}".lower()
            if ids:
                conn.execute("INSERT OR REPLACE INTO lake_datasets (dataset, system, series, family_ids, description) VALUES (?,?,?,?,?)",
                             (dataset, system, series, json.dumps(ids), str(spec.get("what", ""))))
            else:
                conn.execute("DELETE FROM lake_datasets WHERE dataset=?", (dataset,))
    finally:
        store.close()


def register_held(settings: Any, source: str | None = None) -> dict[str, Any]:
    """Catalog rows for every landed unit of the declared file sources, from the unit's own parts in the lake: nothing is
    read from the source and nothing is rewritten. For a catalog that lost them: `pegasus-data families` deleted every
    family it did not derive from the crawl until 2026-11-08, the intake's among them, and their records became unreachable
    by `query`. A unit counts as landed when its sidecar names its family (`_land`) and its parts are in that family's folder.
    Returns, per source, the units registered and the ones whose sidecar or parts were not found."""
    import pyarrow.parquet as pq

    lake_root = Path(settings.lake_dir)
    out: dict[str, Any] = {}
    for name, spec in declared_sources().items():
        if (source and name != source) or not spec.get("system"):
            continue
        if _origin(spec).get("kind") != "files":
            result = _register_held_pieces(settings, name, spec, lake_root)
            if result["registered"] or result["missing"]:
                out[name] = result
            continue
        registered, missing = 0, []
        for unit in _units(spec, None):
            side = _sidecar(name, settings.root, unit["key"])
            if not side.is_file():
                continue
            family = (json.loads(side.read_text(encoding="utf8")).get("stats") or {}).get("family")
            parts = sorted(unit_parts(lake_root, family, _safe(unit["key"]))) if family else []
            if not parts:
                missing.append(unit["key"])
                continue
            signature = parts[0].parents[2].name.split("=", 1)[1]
            names = [n for n in pq.read_schema(parts[0]).names if n != "year"]
            unit["fingerprint"] = _fingerprint(spec, unit)
            _register(settings, name, spec, unit, unit["key"], family, signature, names, parts, lake_root)
            registered += 1
        if registered or missing:
            out[name] = {"registered": registered, "missing": missing}
    return out



def _register_held_pieces(settings: Any, name: str, spec: dict[str, Any], lake_root: Path) -> dict[str, Any]:
    """`register_held` for an API source's pieces and a snapshot's reads, whose units are not a pattern to enumerate: each
    unit is found by the publication the catalog still records for it (``files``, which the families stage never
    deleted), its key read back from that path as the landing wrote it (`_api_units`, `land_snapshot`)."""
    from urllib.parse import parse_qs, urlsplit

    import pyarrow.parquet as pq

    from .catalog.store import CatalogStore

    system, series = str(spec["system"]).upper(), str(spec["series"]).upper()
    store = CatalogStore(settings.catalog_path, read_only=True)
    try:
        paths = {str(r["path"]).split(SLICE)[0] for r in store.query(
            "SELECT path FROM file_facts WHERE system = ? AND series_prefix = ? AND grammar = 'intake'", (system, series))}
    finally:
        store.close()
    registered, missing = 0, []
    for path in sorted(paths):
        query = {k: v[0] for k, v in parse_qs(urlsplit(path).query).items()}
        if "slice" in query and "read" in query:
            key = f"{query['slice']}@{query['read']}"
        elif "offset" in query:
            key = f"api-{int(query['offset']):010d}"
        elif len(query) == 1:
            param, value = next(iter(query.items()))
            key = f"api-{param}={value}"
        else:
            missing.append(path)
            continue
        found = unit_parts(lake_root, f"{_safe(system)}_{_safe(series)}_*", _safe(key))
        if not found:
            missing.append(key)
            continue
        families: dict[Path, list[Path]] = {}
        for part in found:
            families.setdefault(part.parents[3], []).append(part)
        newest = max(families, key=lambda fam: max(q.stat().st_mtime for q in families[fam]))
        parts = sorted(families[newest])
        unit = {"key": key, "year": None, "extension": "json", "size": 0, "path": path}
        unit["fingerprint"] = _fingerprint(spec, unit)
        _register(settings, name, spec, unit, key, newest.name, parts[0].parents[2].name.split("=", 1)[1],
                  [n for n in pq.read_schema(parts[0]).names if n != "year"], parts, lake_root)
        registered += 1
    return {"registered": registered, "missing": missing}

def _span(text: Any) -> list[int]:
    out: list[int] = []
    for part in str(text).split(","):
        lo, _, hi = part.strip().partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


#: The month as the Portal de Dados Abertos spells it in file names (PNI/csv/vacinacao_jan_2023_csv.zip): `{month_pt}`.
MONTHS_PT = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _units(spec: dict[str, Any], years: list[int] | None) -> list[dict[str, Any]]:
    """The pieces a files origin is read in: each file (with the year it stands for, when the declaration states one).

    A pattern declared by ``months`` files its units by month: a unit carries its ``month`` (YYYYMM), the period of the
    publication it is (`_register`). A pattern declared by ``years``, and a listed file, are filed by year or not dated: no
    ``month``, whatever month column their records hold.
    """
    origin = _origin(spec)
    out: list[dict[str, Any]] = []
    for entry in origin.get("files") or []:
        out.append({"key": entry.get("key") or Path(urlsplit(entry["url"]).path).name, "url": entry["url"], "year": entry.get("year"),
                    "extension": entry.get("extension")})
    if origin.get("pattern"):
        # `across` names further axes of the pattern (ANS files each month by state: {uf: [AC, AL, ...]}): one unit per combination
        across = origin.get("across") or {}
        for period in _span(origin["years"] if origin.get("years") else origin["months"]):
            if not origin.get("years") and month_of(period) is None:
                continue                     # a span of YYYYMM months ("201401-202110") holds no month 13 to 00
            year = period if origin.get("years") else year_of(period)
            for combination in itertools.product(*across.values()):
                axes = dict(zip(across, map(str, combination), strict=True))
                out.append({"key": "-".join([str(period), *axes.values()]),
                            "url": origin["pattern"].format(year=year, period=period, month=f"{period % 100:02d}",
                                                            month_pt="" if origin.get("years") else MONTHS_PT[period % 100 - 1],
                                                            **axes), "year": year,
                            "month": None if origin.get("years") else period})
    for unit in out:
        unit["path"] = unit["url"]
        unit["extension"] = unit.get("extension") or Path(urlsplit(unit["url"]).path).suffix.lstrip(".").lower()
    return [u for u in out if not years or u["year"] is None or u["year"] in years]


#: The version of each period derivation (`_records_sql`): bump a kind when its SQL changes what the lake's `_MONTH` and `year`
#: hold, so the units landed by the old one are landed again (the fingerprint carries it). `parts` 2: a month part accepts
#: "01"-"09" (SISAGUA's and SNGPC's months 1-9 had landed as no month, 2026-10-14). A kind not listed has never changed.
PERIOD_DERIVATION = {"parts": 2}


#: The keys of a column's declaration that change what is landed: how its typed value, raw and flag are read (`_typed`,
#: `_flag`), the spellings its header is found by, whether it may be absent. Its description and its code table are read
#: with the lake, so editing them lands nothing again (until 2026-10-19 the whole declaration was digested, and any
#: curation edit to a source's columns downloaded the source again: SNGPC-IND's 94 months for a code table, OQ-90).
LANDED_KEYS = ("type", "take", "format", "formats", "decimal", "tokens", "aliases", "optional")


def _fingerprint(spec: dict[str, Any], unit: dict[str, Any]) -> str:
    """What a landed unit is a function of: the file or piece, the columns' `LANDED_KEYS`, the place, the period, the
    origin, and the period derivation's version."""
    version = PERIOD_DERIVATION.get((spec.get("period") or {}).get("type"))
    columns = {c: {k: (d or {})[k] for k in LANDED_KEYS if (d or {}).get(k) is not None} for c, d in (spec.get("columns") or {}).items()}
    return _digest({"columns": columns, **{k: spec.get(k) for k in ("place", "period", "origin")}}, unit.get("url"), unit.get("key"),
                   *([{"period_derivation": version}] if version else []))


def _current(side: Path, known: dict[str, Any], spec: dict[str, Any], unit: dict[str, Any]) -> bool:
    """Whether a unit's sidecar says it was landed as the declaration now lands it. A sidecar written before 2026-10-19 holds
    the digest of the whole declaration: equal to it under the current declaration, it is current, and is rewritten with
    `_fingerprint`; differing, the unit is landed again, as it was then."""
    if known.get("fingerprint") == unit["fingerprint"]:
        return True
    version = PERIOD_DERIVATION.get((spec.get("period") or {}).get("type"))
    whole = _digest({k: spec.get(k) for k in ("columns", "place", "period", "origin")}, unit.get("url"), unit.get("key"),
                    *([{"period_derivation": version}] if version else []))
    if known.get("fingerprint") != whole:
        return False
    side.write_text(json.dumps({**known, "fingerprint": unit["fingerprint"]}), encoding="utf8")
    return True


def _sidecar(source: str, root: Path | str | None, key: str) -> Path:
    return _cache(source, root, "units", f"{_safe(key)}.json")


#: a lone byte that is not valid UTF-8, as Windows-1252 reads it
_CP1252 = {b: bytes([b]).decode("cp1252", "replace") for b in range(128, 256)}
_LONE = re.compile("[\udc80-\udcff]")


def _transcode_mixed(src: Any, dst: Any) -> None:
    """``encoding: mixed``: a file that mixes UTF-8 and Windows-1252, even within one line (SISAGUA's), rewritten as
    UTF-8 in blocks: a valid UTF-8 sequence is read as such, a lone byte as its Windows-1252 character. A U+FFFD already
    in the source is kept (the source's, not ours)."""
    pending = b""
    while True:
        block = src.read(64 << 20)
        data = pending + block
        cut = data.rfind(b"\n") + 1 if block else len(data)
        chunk, pending = data[:cut], data[cut:]
        text = chunk.decode("utf-8", "surrogateescape")
        for lone in set(_LONE.findall(text)):
            text = text.replace(lone, _CP1252[ord(lone) - 0xDC00])
        dst.write(text.encode("utf-8"))
        if not block:
            break


def _file_relation(path: Path, origin: dict[str, Any], unit: dict[str, Any]) -> tuple[str, Path | None]:
    """A DuckDB relation over a downloaded file; a zip's CSV member is extracted beside it (returned, to delete)."""
    if origin.get("format", "csv") == "parquet":
        return f"read_parquet('{path.as_posix()}')", None
    csv = origin.get("csv") or {}
    mixed = csv.get("encoding") == "mixed"
    source, extracted = path, None
    if path.suffix.lower() == ".zip" or mixed:
        opener, name = (path.open, path.name) if path.suffix.lower() != ".zip" else (None, None)
        if path.suffix.lower() == ".zip":
            archive = zipfile.ZipFile(path)
            members = [m for m in archive.namelist() if m.lower().endswith((".csv", ".txt"))]
            if csv.get("member"):         # the zip holds more than one table (INEP's: the schools and a supplement): the one named
                wanted = str(csv["member"]).format(year=unit.get("year")).lower()
                members = [m for m in members if m.lower().endswith(wanted)]
            if len(members) != 1:
                raise ValueError(f"{path.name}: expected one CSV member, found {members}")
            name = Path(members[0]).name

            def opener(mode="rb", archive=archive, member=members[0]):
                return archive.open(member)
        extracted = path.with_name(name + (".utf8.csv" if mixed else ""))
        with opener("rb") as src, extracted.open("wb") as dst:
            if mixed:
                _transcode_mixed(src, dst)
            else:
                while chunk := src.read(1 << 24):
                    dst.write(chunk)
        source = extracted
    encoding = "utf-8" if mixed else {"latin1": "latin-1", "latin-1": "latin-1", "utf8": "utf-8", "utf-8": "utf-8"}.get(
        csv.get("encoding", "utf8"), csv.get("encoding"))
    return (f"read_csv('{source.as_posix()}', all_varchar=true, header=true, delim='{csv.get('sep', ',')}', quote='\"', "
            f"encoding='{encoding}', null_padding=true{', parallel=false' if csv.get('multiline') else ''})"), extracted


def _land_unit(settings: Any, source: str, spec: dict[str, Any], unit: dict[str, Any], refresh: bool,
               fetch: bool = True) -> dict[str, Any]:
    root = settings.root
    unit["fingerprint"] = _fingerprint(spec, unit)
    side = _sidecar(source, root, unit["key"])
    if side.is_file() and not refresh:
        known = json.loads(side.read_text(encoding="utf8"))
        if _current(side, known, spec, unit):
            return {**known["stats"], "cached": True}
    if not refresh:
        # a unit the declaration now reads differently, whose records are in the lake with every value as filed: derived
        # again from them, nothing downloaded (SNGPC's 94 months and SISAGUA's control files after the month fix, 2026-10-24)
        held = _held_records(settings, spec, unit)
        if held is not None:
            return _reland(settings, source, spec, unit, side, held)
    if not fetch:
        return {"not_held": True, "url": unit["url"]}
    origin = _origin(spec)
    raw = download(unit["url"], _cache(source, root, "raw", _safe(unit["key"]) + "." + unit["extension"]))
    extracted = None
    counted = origin.get("format", "csv") == "csv"
    if counted and raw.suffix.lower() != ".zip":
        with raw.open("rb") as handle:
            head = handle.read(120)
        if head.lstrip()[:1] == b"<":         # a firewall's page answered with status 200 (MIDR's): not the file, and not kept
            raw.unlink()
            raise ValueError(f"{unit['url']} answered a page, not the file: {head!r}")
    con = _duck(settings, spec)

    def land(relation: str, extracted: Path | None) -> dict[str, Any]:
        # The independent count: the file's own lines less the header. DuckDB's strict_mode=false dropped 4,007 of SISAGUA
        # 2019's 2,844,261 rows without an error (2026-10-10); a record the reader loses is a recorded gap. It is checked
        # before the swap (`_land`), so a unit that lost records is never registered.
        path = extracted or raw
        csv = origin.get("csv") or {}
        expected: int | None = None
        found: dict[str, Any] = {}
        if counted and csv.get("multiline"):
            # a field holds line breaks (free text in quotes): the lines are not the records, a second parser counts them
            expected = _records(path, csv, transcoded=path.name.endswith(".utf8.csv"))
            found = {"file_records": expected, "rows_equal_lines": True}
        elif counted:
            lines = _lines(path)
            expected, found = lines - 1, {"file_lines": lines, "rows_equal_lines": True}
        return {**_land(settings, source, spec, unit, con, relation, datetime.now(UTC).date().isoformat(), sidecar=side, expect_rows=expected), **found}

    try:
        relation, extracted = _file_relation(raw, origin, unit)
        unit["size"] = raw.stat().st_size
        try:
            stats = land(relation, extracted)
        except Exception as exc:
            # a month published in another encoding than the source declares (SNGPC's latin-1 files hold UTF-8 months
            # among 2014-2018's, 2026-10-11): read as mixed, each line's valid UTF-8 kept and stray bytes as cp1252
            csv = origin.get("csv") or {}
            if isinstance(exc, _LostRecords) or not counted or csv.get("encoding") == "mixed" or "encoded" not in str(exc):
                raise
            if extracted is not None and extracted.is_file():
                extracted.unlink()
            relation, extracted = _file_relation(raw, {**origin, "csv": {**csv, "encoding": "mixed"}}, unit)
            stats = land(relation, extracted)
            stats["encoding"] = f"mixed (the declared {csv.get('encoding')} failed: {str(exc).splitlines()[0][:120]})"
    finally:
        con.close()
        for path in (extracted, None if origin.get("keep") else raw):
            if path is not None and path.is_file():
                path.unlink()
    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_text(json.dumps({"fingerprint": unit["fingerprint"], "stats": stats}), encoding="utf8")
    return stats


def _held_records(settings: Any, spec: dict[str, Any], unit: dict[str, Any]) -> tuple[list[str], str, int, list[str]] | None:
    """The unit's records in the lake, when they can stand for its file: every part read from the unit's own path on one
    day, holding every declared column's value as filed (the column itself, or its `__RAW` beside a typed or rewritten
    one). Returns (parts, read day, rows, the columns as filed), else None: a unit landed from another file, before a column
    was declared, or never landed is read from the source."""
    import duckdb

    system, series = str(spec["system"]), str(spec["series"])
    found_parts = unit_parts(settings.lake_dir, f"{_safe(system.upper())}_{_safe(series.upper())}_*", _safe(unit["key"]))
    if not found_parts:
        return None
    # A landing keeps a unit in one family (`_land` removes its parts from the others), so parts in two families are a
    # stale copy: only the family written last stands for the unit. Reading both landed FA-HUM's 2,912 records twice
    # (2026-10-24).
    by_family: dict[Path, list[Path]] = {}
    for f in found_parts:
        by_family.setdefault(f.parents[3], []).append(f)
    newest = max(by_family, key=lambda fam: max(p.stat().st_mtime for p in by_family[fam]))
    parts = sorted(str(f) for f in by_family[newest])
    con = duckdb.connect(":memory:")
    try:
        con.execute("SET memory_limit='1GB'")
        relation = f"read_parquet({parts!r}, hive_partitioning=false, union_by_name=true)"
        names = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()]
        if "_SOURCE_PATH" not in names or "_READ_ON" not in names:
            return None
        found = con.execute(f"SELECT DISTINCT _SOURCE_PATH, _READ_ON FROM {relation}").fetchall()
        if len(found) != 1 or found[0][0] != unit["path"]:
            return None
        rows = con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
    finally:
        con.close()
    filed = [n for n in names if not n.startswith("_") and not n.endswith(("__RAW", "__FLAG"))]
    declared = [c.upper() for c, d in (spec.get("columns") or {}).items() if not (d or {}).get("optional")]
    if any(c not in filed for c in declared):
        return None
    return parts, str(found[0][1]), int(rows), [f"{n}__RAW" if f"{n}__RAW" in names else n for n in filed]


def _reland(settings: Any, source: str, spec: dict[str, Any], unit: dict[str, Any], side: Path,
            held: tuple[list[str], str, int, list[str]]) -> dict[str, Any]:
    """Land a unit again from its own records (`_held_records`): their values as filed, under their own names, through the
    declaration as it stands, replacing the unit's parts (`_land`) only when every record came back."""
    parts, read_on, rows, columns = held
    con = _duck(settings, spec)
    copy = Path(settings.work_dir) / "intake" / f"reland-{_safe(source)}-{_safe(unit['key'])}.parquet"
    copy.parent.mkdir(parents=True, exist_ok=True)
    try:
        # copied out first: the swap removes the parts this read would otherwise still hold open
        select = ", ".join(f"{_ident(c)} AS {_ident(c.removesuffix('__RAW'))}" for c in columns)
        con.execute(f"COPY (SELECT {select} FROM read_parquet({parts!r}, hive_partitioning=false, union_by_name=true)) "
                    f"TO '{copy.as_posix()}' (FORMAT parquet)")
        stats = _land(settings, source, spec, unit, con, f"read_parquet('{copy.as_posix()}')", read_on, sidecar=side,
                      expect_rows=rows)
    finally:
        con.close()
        copy.unlink(missing_ok=True)
    stats["relanded_from_lake"] = True
    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_text(json.dumps({"fingerprint": unit["fingerprint"], "stats": stats}), encoding="utf8")
    return stats


def _records(path: Path, csv: dict[str, Any], transcoded: bool = False) -> int:
    """The records of a CSV file whose fields may hold line breaks, counted by a second parser (pyarrow's, which reads the
    quoted breaks as part of the value): every row after the header, a row with the wrong number of fields included."""
    import csv as csvmodule

    import pyarrow.csv as pcsv

    sep = csv.get("sep", ",")
    encoding = "utf8" if transcoded or csv.get("encoding") == "mixed" else csv.get("encoding", "utf8")
    with path.open("rb") as handle:
        header = next(csvmodule.reader([handle.readline().decode("utf-8" if encoding == "utf8" else encoding, "replace")], delimiter=sep))
    skipped = 0

    def count_invalid(row: Any) -> str:
        nonlocal skipped
        skipped += 1
        return "skip"

    reader = pcsv.open_csv(
        path, read_options=pcsv.ReadOptions(encoding=encoding, skip_rows=1, column_names=[f"c{i}" for i in range(len(header))], block_size=1 << 26),
        parse_options=pcsv.ParseOptions(delimiter=sep, newlines_in_values=True, invalid_row_handler=count_invalid),
        convert_options=pcsv.ConvertOptions(include_columns=["c0"], column_types={"c0": pa.string()}))
    return sum(batch.num_rows for batch in reader) + skipped


def _lines(path: Path) -> int:
    """The newlines of a file (its records plus the header, where no field holds a line break), counted in blocks."""
    n = 0
    with path.open("rb") as f:
        while block := f.read(1 << 24):
            n += block.count(b"\n")
    return n


def _api_units(origin: dict[str, Any]) -> Iterator[tuple[str, str, Any]]:
    """The units a bulk API read is cut into, lazily: (key, path, reader), the reader returning (rows, unstable, complete).
    With a declared ``partition`` a unit is one value of its first parameter (a state), read to the end by `_complete`
    (always complete; ``unstable`` names the filters that could only be paged), because offset paging of a table that applies
    its limit before de-duplication loses rows (the health-region list returned 4,870 of 5,571 municipalities unfiltered, all
    of them by state); otherwise a unit is `PIECE_PAGES` pages of offsets, complete when it holds all of them and nothing
    can be added to it later (its last page is full, or a page follows), incomplete when the answer ended inside it or at
    its short last page (the endpoint may grow)."""
    base, endpoint = origin["base"].rstrip("/"), origin["endpoint"]
    size = _paging(origin)["size"]
    if origin.get("partition"):
        level, rest = origin["partition"][0], origin["partition"][1:]
        for value in _partition_values(level, {}):
            def read_partition(value: str = value) -> tuple[list[dict], list[str], bool]:
                unstable: list[str] = []
                return _complete(origin, endpoint, {level["param"]: value}, rest, unstable), unstable, True
            yield f"api-{level['param']}={value}", f"{base}{endpoint}?{level['param']}={value}", read_partition
        return
    start = 0
    while True:
        def read(start: int = start) -> tuple[list[dict], list[str], bool]:
            rows: list[dict] = []
            pages = _pages(origin, endpoint, origin.get("params") or {}, start)
            for count, page in enumerate(pages, 1):
                rows += page
                if count == PIECE_PAGES:
                    # all of the unit's pages were read; it is final if its last page is full (a growing table appends
                    # beyond it) or another page follows (a short page inside the table: the limit applies before de-duplication)
                    return rows, [], len(page) >= size or next(pages, None) is not None
            return rows, [], False
        yield f"api-{start:010d}", f"{base}{endpoint}?offset={start}&pages={PIECE_PAGES}", read
        start += size * PIECE_PAGES


def _is_complete(known: dict[str, Any], capacity: int | None) -> bool:
    """Whether a unit's sidecar says the unit held everything its range holds. A sidecar written before the flag existed is
    read by its rows: an offset unit short of a full piece may be the end of a table that has grown since."""
    if "complete" in known:
        return bool(known["complete"])
    return capacity is None or known["stats"].get("rows", 0) >= capacity


def _land_api(settings: Any, source: str, spec: dict[str, Any], refresh: bool) -> dict[str, Any]:
    """A bulk read of an API endpoint, landed unit by unit: an interrupted read resumes at its last unit. A unit that ended
    short of its range is *incomplete* and read again on every run (the endpoint may have grown since), unless the origin
    declares ``static: true``; the units whose filters could only be paged are listed under ``unstable``."""
    origin = _origin(spec)
    total: dict[str, Any] = {"rows": 0, "undated": 0, "unplaced": 0, "unallocated": 0, "units": 0, "incomplete": [], "unstable": [],
                             "empty_answers": []}
    capacity = None if origin.get("partition") else _paging(origin)["size"] * PIECE_PAGES
    static = bool(origin.get("static"))
    # A table without a period of its own (a reference, a current state) stands for the year it was read.
    year = datetime.now(UTC).year if (spec.get("period") or {}).get("type", "file") == "file" else None
    for key, path, read in _api_units(origin):
        unit = {"key": key, "year": year, "extension": "json", "size": 0, "path": path}
        unit["fingerprint"] = _fingerprint(spec, unit)
        side = _sidecar(source, settings.root, key)
        previous = json.loads(side.read_text(encoding="utf8")) if side.is_file() else None
        known = None if refresh else previous
        if known and _current(side, known, spec, unit) and (static or _is_complete(known, capacity)):
            stats, complete = known["stats"], _is_complete(known, capacity)
        else:
            rows, unstable, complete = read()
            if not rows and previous and previous["stats"].get("rows", 0) > 0:
                # an empty answer where the unit held rows is an anomaly (a gateway that answers empty under load), not a
                # table that emptied: the unit keeps what it holds, its note stays as it was, and the report says so
                stats, complete = previous["stats"], _is_complete(previous, capacity)
                total["empty_answers"].append(key)
            else:
                if rows:
                    con = _duck(settings, spec)
                    try:
                        con.register("api_piece", _as_strings(rows))
                        stats = _land(settings, source, spec, unit, con, "api_piece", datetime.now(UTC).date().isoformat(), sidecar=side)
                    finally:
                        con.close()
                else:
                    stats = {"rows": 0, "undated": 0, "unplaced": 0, "unallocated": 0}
                if unstable:
                    stats["unstable"] = unstable
                side.parent.mkdir(parents=True, exist_ok=True)
                side.write_text(json.dumps({"fingerprint": unit["fingerprint"], "stats": stats, "complete": complete}), encoding="utf8")
        for k in ("rows", "undated", "unplaced", "unallocated"):
            total[k] += stats.get(k, 0)
        total["units"] += 1
        total["unstable"] += stats.get("unstable", [])
        if not complete:
            total["incomplete"].append(key)
        # an empty unit, or one the answer ended inside, is the end of an offset read
        if not origin.get("partition") and (stats.get("rows", 0) == 0 or not complete):
            return total
    return total


def land_snapshot(source: str, table: pa.Table, label: str, read_on: str, root: str | Path | None = None) -> dict[str, Any]:
    """Land a fresh read of a current-state endpoint in the lake as records dated by their read day (``_READ_ON``), so the
    history accrues from the first read; the unit is the slice's name and the day."""
    settings = _settings(root)
    spec = declared_sources()[source]
    unit = {"key": f"{label}@{read_on}", "year": None, "extension": "json", "size": table.nbytes,
            "path": f"{url(source)}?slice={label}&read={read_on}"}
    unit["fingerprint"] = _fingerprint(spec, unit)
    con = _duck(settings, spec)
    try:
        con.register("snapshot", _as_strings(table.to_pylist()))
        return _land(settings, source, spec, unit, con, "snapshot", read_on)
    finally:
        con.close()


# --- the fields --------------------------------------------------------------------------------------------------------

def _strata(fs: dict[str, Any]) -> list[tuple[str | None, str]]:
    """The extra keys of a field as (column, name in the field): ``by: [COL]`` names the key as the column in lower case,
    ``by: [{COL: name}]`` as ``name``; an ``unpivot`` field has the two keys it declares (``as``), taken from no column."""
    if fs.get("unpivot"):
        return [(None, str(k)) for k in fs["unpivot"]["as"]]
    out: list[tuple[str | None, str]] = []
    for entry in fs.get("by") or []:
        column, alias = next(iter(entry.items())) if isinstance(entry, dict) else (entry, str(entry).lower())
        out.append((str(column), str(alias)))
    return out


def _derive(settings: Any, spec: dict[str, Any], names: list[str], years: list[int] | None) -> dict[str, Any]:
    """The declared fields, derived from the lake records of the source: counts and sums by place and period."""
    system, series = str(spec["system"]).upper(), str(spec["series"]).upper()
    pattern = (Path(settings.lake_dir) / system / f"{system}_{series}_*" / "schema_signature=*" / "uf=BR" / "year=*" / "*.parquet").as_posix()
    declared = {c.upper(): (d or {}) for c, d in (spec.get("columns") or {}).items()}
    place, period = spec.get("place") or {}, spec.get("period") or {"type": "file"}
    by_place = place.get("type") in ("municipality", "municipality_name")
    place_sql = "_MUNICIPALITY" if by_place else (_ident("_" + (place.get("as") or place["column"]).upper()) if place else None)
    place_name = "municipality" if by_place else ((place.get("as") or place.get("column")) if place else None)
    valid = _span(period["valid"]) if period.get("valid") else None

    def raw_name(column: str) -> str:
        return _ident(column.upper() + ("__RAW" if declared.get(column.upper(), {}).get("type") in TYPED else ""))

    def numeric(column: str, field: str) -> str:
        if declared.get(column.upper(), {}).get("type") not in ("number", "result", "integer"):
            raise ValueError(f"field {field}: sum of {column} needs a column declared `type: number`, `integer` or `result`")
        return _ident(column.upper())

    def conditions(wanted: dict[str, Any]) -> list[str]:
        # a list: the raw value is one of them; {prefix: [...]}: it starts with one; {above / below / at_least / at_most: x}:
        # the typed value against a bound (a potability limit: turbidity above 5 uT)
        out = []
        for column, values in wanted.items():
            if isinstance(values, dict):
                typed_col = _ident(column.upper())
                bounds = {"above": ">", "below": "<", "at_least": ">=", "at_most": "<="}
                parts = [f"{typed_col} {op} {float(values[k])}" for k, op in bounds.items() if k in values]
                parts += [" OR ".join(f"starts_with({raw_name(column)}, {str(v)!r})" for v in values.get("prefix") or [])]
                out.append("(" + " AND ".join(f"({x})" for x in parts if x) + ")")
            else:
                out.append(f"{raw_name(column)} IN ({','.join(repr(str(v)) for v in values)})")
        return out

    con = _duck(settings, spec)
    report: dict[str, Any] = {}
    try:
        con.execute(f"CREATE VIEW rec AS SELECT * FROM read_parquet('{pattern}', union_by_name=true, hive_partitioning=true)")
        for name in names:
            fs = spec["fields"][name]
            keys = ([f"{place_sql} AS {place_name}"] if place else []) + ["year"] + (["_MONTH AS month"] if period.get("grain") == "month" else [])
            keys += [f"{raw_name(c)} AS {_ident(alias)}" for c, alias in _strata(fs) if c]
            where = ["year > 0"] + ([f"{place_sql} IS NOT NULL"] if place else [])
            if valid:
                where.append(f"year BETWEEN {valid[0]} AND {valid[-1]}")
            if years:
                where.append(f"year IN ({','.join(str(int(y)) for y in years)})")
            where += conditions(fs.get("where") or {})
            filtered = f"FROM rec WHERE {' AND '.join(where)}"
            if fs.get("rows"):
                # one row per record, the declared columns of the lake records under the declared names (an event register read
                # as events: the field is a view of the records, nothing is summed)
                table = con.execute(f"SELECT {', '.join(f'{_ident(col)} AS {_ident(alias)}' for alias, col in fs['rows'].items())}, year {filtered}").fetch_arrow_table()
                report[name] = _write_rows(settings, name, table, years)
                continue
            if fs.get("unpivot"):
                # a source that files its strata as columns (enrolments by sex, by race, by age band): one row per column, the
                # two keys named by `as` ([margin, category]) and the column's own as declared in `columns`
                group = ", ".join(str(i + 1) for i in range(len(keys)))
                for column, labels in fs["unpivot"]["columns"].items():
                    if not all(isinstance(v, str) for v in labels):      # YAML reads 0_3 as the number 3
                        raise ValueError(f"field {name}: the labels of {column} must be text (quote them): {labels}")
                parts = [f"SELECT {', '.join(keys)}, {', '.join(f'{_sql_text(v)} AS {_ident(k)}' for k, v in zip(fs['unpivot']['as'], labels, strict=True))}, "
                         f"sum({numeric(column, name)}) AS value {filtered} GROUP BY {group}"
                         for column, labels in fs["unpivot"]["columns"].items()]
                table = con.execute(" UNION ALL ".join(parts)).fetch_arrow_table()
            else:
                measure = fs["measure"]
                value = "count(*)" if measure == "count" else f"sum({numeric(measure['sum'], name)})"
                if fs.get("outcome"):
                    # the population's rows that have the outcome: every (place, month) of the population has a row, 0 where
                    # none of its samples did (a true zero), while a place-month without samples has none (missing)
                    value = f"count(*) FILTER (WHERE {' AND '.join(conditions(fs['outcome']))})"
                group = ", ".join(str(i + 1) for i in range(len(keys)))
                table = con.execute(f"SELECT {', '.join(keys)}, {value} AS value {filtered} GROUP BY {group}").fetch_arrow_table()
            table = table.set_column(table.schema.get_field_index("value"), "value", pc.cast(table.column("value"), pa.float64()))
            report[name] = _write_field(spec, settings, name, fs, table, place_name, years)
    finally:
        con.close()
    return report


def _write_rows(settings: Any, name: str, table: pa.Table, years: list[int] | None) -> dict[str, Any]:
    """A field of records (``rows``): the table split by its ``year`` (`fields._write_by_year`); a build of every year
    replaces the field."""
    from .fields import _write_by_year

    return {"rows": _write_by_year(table, name, settings, prune=not years)}


def _write_field(spec: dict[str, Any], settings: Any, name: str, fs: dict[str, Any], table: pa.Table, place_name: str | None, years: list[int] | None) -> dict[str, Any]:
    from .fields import _write_by_year
    from .geography import municipalities

    n = table.num_rows
    if place_name == "municipality":
        universe = municipalities()
        table = table.append_column("municipality7", pa.array([universe[c]["code7"] for c in table.column("municipality").to_pylist()], pa.string()))
    table = table.append_column("status", pa.array(["ok"] * n, pa.string()))
    table = table.append_column("unit", pa.array([str(fs.get("unit", ""))] * n, pa.string()))
    table = table.append_column("source", pa.array([str(spec.get("citation", ""))] * n, pa.string()))
    sums = table.group_by("year").aggregate([("value", "sum")])
    by_year = {int(y): v for y, v in zip(sums.column("year").to_pylist(), sums.column("value_sum").to_pylist(), strict=True)}
    _write_by_year(table, name, settings, prune=not years)
    return {"rows": n, "total": sum(by_year.values()), "by_year": dict(sorted(by_year.items()))}


def build_source(settings: Any, source: str, names: list[str] | None = None, years: list[int] | None = None, refresh: bool = False,
                 fetch: bool = True) -> dict[str, Any]:
    """Land a declared source's records in the lake and derive its fields from them. Returns, per field, its rows, total and
    totals by year, and under ``units`` what each file or API unit held and what was left out of the fields and why.
    ``fetch=False`` downloads nothing: units whose records the lake holds are derived again where the declaration changed,
    the others are reported ``not_held``."""
    spec = declared_sources()[source]
    if _origin(spec).get("on_request") and not years:
        raise ValueError(f"{source} is declared on request (too large to land whole): name the years to build")
    fields = [f for f in spec.get("fields") or {} if not names or f in names]
    report: dict[str, Any] = {"units": {}}
    if _origin(spec)["kind"] == "api":
        report["units"]["api"] = _land_api(settings, source, spec, refresh)
    else:
        absent: dict[str, SourceAbsent] = {}
        for unit in _units(spec, years):
            try:
                report["units"][unit["key"]] = _land_unit(settings, source, spec, unit, refresh, fetch)
            except SourceAbsent as exc:            # a month not yet published: a recorded gap, not the end of the build
                absent[unit["key"]] = exc
                report["units"][unit["key"]] = {"absent": exc.status, "url": exc.url}
        if absent and len(absent) == len(report["units"]):
            first = next(iter(absent.values()))
            raise SourceAbsent(first.url, first.status, f"{source}: all {len(absent)} units are absent")
        report["absent"] = sorted(absent)
    for k in ("rows", "undated", "unplaced", "unallocated"):
        report[k] = sum(u.get(k, 0) for u in report["units"].values())
    unparsed: dict[str, int] = {}
    for unit_stats in report["units"].values():
        for column, n in (unit_stats.get("unparsed") or {}).items():
            unparsed[column] = unparsed.get(column, 0) + n
    if unparsed:
        report["unparsed"] = unparsed
    # A field that is a records cube is built as one (kept under lake/cubes by its data's fingerprint), not copied
    # into lake/fields (ADR-0217); the others are still derived here.
    from .fields import declared_fields, intake_cube, load_field, margins_view, rows_view

    declared = declared_fields()
    served = [f for f in fields if f in declared
              and any(view(f, declared[f]) is not None for view in (intake_cube, rows_view, margins_view))]
    for name in served:
        table = load_field(name, years=years, settings=settings)
        total = float(pc.sum(table.column("value")).as_py() or 0) if "value" in table.column_names else None
        report[name] = {"rows": table.num_rows, "total": total, "cube": True}
    report.update(_derive(settings, spec, [f for f in fields if f not in served], years))
    return report


# --- the check -------------------------------------------------------------------------------------------------------

def _stream_batches(path: Path, origin: dict[str, Any], columns: list[str]) -> Iterator[pa.Table]:
    """The given columns of a file as string tables, batch by batch (a zip's CSV members are read in place, a parquet by row
    group). A column the file lacks raises (a missing column must never look like an empty one)."""
    import pyarrow.csv as pcsv

    if origin.get("format", "csv") == "parquet":
        reader = pq.ParquetFile(path)
        names = {n.lower(): n for n in reader.schema_arrow.names}
        missing = [c for c in columns if c.lower() not in names]
        if missing:
            raise KeyError(f"{path.name}: columns absent: {missing}")
        for batch in reader.iter_batches(columns=[names[c.lower()] for c in columns], batch_size=1 << 18):
            table = pa.Table.from_batches([batch])
            yield pa.table({c: pc.cast(table.column(names[c.lower()]), pa.string()) for c in columns})
        return
    csv = origin.get("csv") or {}

    def read(handle: Any) -> Iterator[pa.Table]:
        reader = pcsv.open_csv(handle, read_options=pcsv.ReadOptions(encoding=csv.get("encoding", "utf8"), block_size=1 << 26),
                               parse_options=pcsv.ParseOptions(delimiter=csv.get("sep", ",")),
                               convert_options=pcsv.ConvertOptions(strings_can_be_null=True, null_values=[""]))
        names = {n.strip().lstrip("﻿").lower(): n for n in reader.schema.names}
        missing = [c for c in columns if c.lower() not in names]
        if missing:
            raise KeyError(f"{path.name}: columns absent: {missing}")
        while True:
            try:
                batch = reader.read_next_batch()
            except StopIteration:
                return
            table = pa.Table.from_batches([batch])
            yield pa.table({c: pc.cast(table.column(names[c.lower()]), pa.string()) for c in columns})

    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            for member in [m for m in archive.namelist() if m.lower().endswith((".csv", ".txt"))]:
                with archive.open(member) as handle:
                    yield from read(handle)
    else:
        with path.open("rb") as handle:
            yield from read(handle)


def _clean(array: pa.ChunkedArray | pa.Array) -> pa.Array:
    out = pc.utf8_trim_whitespace(array)
    return pc.if_else(pc.equal(out, ""), pa.scalar(None, pa.string()), out)


def _profile(source: str, spec: dict[str, Any], which: str, columns: list[str], root: str | Path | None) -> tuple[pa.Table, int]:
    """The rows of an origin as (the given columns..., n): how many rows hold each combination of values, and the row total.
    A file is streamed (and deleted), an API read paged to its end; values are trimmed and a trailing ``.0`` dropped, so
    ``29`` and ``29.0`` are one value."""
    origin = _origin(spec, which)
    mapping = origin.get("map") or {}
    own = [mapping.get(c, c) for c in columns]
    parts: list[pa.Table] = []
    total = 0

    def add(batch: pa.Table) -> None:
        nonlocal total
        total += batch.num_rows
        clean = {c: pc.replace_substring_regex(_clean(batch.column(o)), r"\.0+$", "") for c, o in zip(columns, own, strict=True)}
        parts.append(pa.table(clean).group_by(columns).aggregate([([], "count_all")]))

    if origin["kind"] == "api":
        for page in _pages(origin, origin["endpoint"], origin.get("params") or {}):
            add(_as_strings(page, own))
    else:
        for entry in origin.get("files") or []:
            path = download(entry["url"], _cache(source, root, "raw", Path(urlsplit(entry["url"]).path).name))
            try:
                for batch in _stream_batches(path, origin, own):
                    add(batch)
            finally:
                path.unlink(missing_ok=True)
    grouped = pa.concat_tables(parts).group_by(columns).aggregate([("count_all", "sum")]).rename_columns([*columns, "n"])
    return grouped, total


def check_source(source: str, root: str | Path | None = None, columns: list[str] | None = None) -> dict[str, Any]:
    """The used origin against the declared ``compare`` origin, row for row: the row counts, and on the given columns (the
    place and period columns by default) the combinations of values that differ and by how many rows. The `compare` origin
    names its columns differently with ``map: {used column: its column}``. Equal counts alone prove little: DEMAS'
    yellow-fever cases hold the same rows as the Portal's file plus one copy of the first case."""
    spec = declared_sources()[source]
    if not spec.get("compare"):
        raise KeyError(f"{source}: no `compare` origin declared")
    place, period = spec.get("place") or {}, spec.get("period") or {}
    columns = columns or list(dict.fromkeys(c for c in [place.get("column"), place.get("uf"), period.get("column"), period.get("year"), period.get("month")] if c))
    mine, n_mine = _profile(source, spec, "origin", columns, root)
    other, n_other = _profile(source, spec, "compare", columns, root)
    joined = mine.join(other, keys=columns, join_type="full outer", left_suffix="_a", right_suffix="_b")
    a, b = pc.fill_null(joined.column("n_a"), 0), pc.fill_null(joined.column("n_b"), 0)
    differ = joined.filter(pc.not_equal(a, b))
    return {"rows_used": n_mine, "rows_compare": n_other, "columns": columns, "combinations_differing": differ.num_rows,
            "rows_in_excess_in_used": int(pc.sum(pc.max_element_wise(pc.subtract(a, b), 0)).as_py() or 0),
            "rows_in_excess_in_compare": int(pc.sum(pc.max_element_wise(pc.subtract(b, a), 0)).as_py() or 0),
            "examples": differ.slice(0, 5).to_pylist()}
