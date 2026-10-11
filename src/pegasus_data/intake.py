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
  publication per file and year, the ontology folds in its system and series, and the curation loader folds in its column
  documentation (``semantics.curation``), so ``query("FA-HUM")`` and ``info()`` serve it like any FTP dataset. Where a source
  is itself an aggregate (a DEMAS endpoint that serves counts) the aggregate is the record.
* **Fields second.** The context fields (``fields:`` of the declaration) are sums and counts by place and period *derived
  from the lake records* and written to ``<lake>/fields/<field>/year=Y/``, where `fields.load_field` reads them, so
  ``contexts: auto`` finds them. A place that is not an IBGE municipality of the universe is *unallocated* (kept in the
  records, left out of the field, counted); a row without a date is year 0 (*undated*); an absent (place, period) is absent,
  not zero.
* **API** (`api_rows`, `read_slice`): paged by the declared style, at most one request per `INTERVAL` per host, a browser
  User-Agent, backoff on 429, 5xx and timeouts; an empty page is the end. A filtered read is cached under
  ``<root>/registries/<source>``; a source with ``snapshot: true`` (a current-stock endpoint) also lands every fresh read in
  the lake with its read date, so a history accrues from the first read.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

__all__ = ["api_rows", "build_source", "check_source", "declared_sources", "get_json", "land_snapshot", "read_slice", "url"]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
#: Seconds between two requests to one host.
INTERVAL = 1.1
#: Pages of an API read landed together as one unit.
PIECE_PAGES = 50
#: Declared types that get a typed column beside the raw one.
TYPED = ("date", "number", "integer", "year", "result")

_last: dict[str, float] = {}
_client: list[httpx.Client] = []


def declared_sources(root: Path | None = None) -> dict[str, dict[str, Any]]:
    from .config import curation_root
    from .ontology import _read_yaml

    doc = _read_yaml((root or curation_root()) / "intake.yml") or {}
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
    with E. coli present over the samples assessed for E. coli, never over every analysis. An outcome condition on a
    column the population also restricts replaces it (present among present-or-absent)."""
    out: dict[str, Any] = {}
    for name, fs in fields.items():
        if not fs.get("outcome"):
            out[name] = fs
            continue
        population = {k: v for k, v in fs.items() if k not in ("outcome", "what")}
        out[f"{name}_assessed"] = {**population, "what": f"The population of {name}: {fs.get('what', '')}".strip()}
        out[name] = {**{k: v for k, v in fs.items() if k != "outcome"}, "where": {**(fs.get("where") or {}), **fs["outcome"]},
                     "over": f"{name}_assessed"}
    return out


def intake_fields(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """The fields the declarations define, in the shape of ``fields.yml`` entries (``source: intake``)."""
    out: dict[str, dict[str, Any]] = {}
    for name, spec in declared_sources(root).items():
        for field, fs in (spec.get("fields") or {}).items():
            # a field's years are its own, else its source's span (the period's valid years): a context is read on them
            years = fs.get("years") or spec.get("years") or (spec.get("period") or {}).get("valid") or ""
            out[field] = {"source": "intake", "intake": name, "unit": fs.get("unit", ""), "what": fs.get("what", spec.get("what", "")),
                          "years": str(years), **({"over": fs["over"]} if fs.get("over") else {}),
                          # its strata as `load_field` names them (`_derive`: lower case)
                          **({"by": [str(c).lower() for c in fs["by"]]} if fs.get("by") else {})}
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
    role is its description, its ``codes`` the inline code list (served as ``CURATED.<SYSTEM>.<FIELD>``)."""
    variable_files, dataset_files = [], []
    for spec in declared_sources(root).values():
        if not spec.get("system"):
            continue
        system, series = str(spec["system"]).upper(), str(spec["series"]).upper()
        reference = spec.get("dictionary") or spec.get("citation")
        variables: dict[str, Any] = {}
        for column, decl in (spec.get("columns") or {}).items():
            body: dict[str, Any] = {"description": str((decl or {}).get("role") or column)}
            if (decl or {}).get("codes"):
                body["codes"] = decl["codes"]
            if (decl or {}).get("type") in TYPED:
                body["notes"] = f"typed as {decl['type']}; the value as filed is {column.upper()}__RAW"
            variables[column.upper()] = body
        variable_files.append({"system": system, "source": "layout_doc", "source_ref": reference, "variables": variables})
        dataset_files.append({"datasets": {f"{system}_{series}": {
            "system": system, "series": series, "what_one_row_is": spec.get("one_row") or spec.get("what"),
            "unit_of_analysis": spec.get("unit_of_analysis"), "gotchas": spec.get("gotchas") or [],
            "source": "web", "source_ref": reference, "asserted_by": "pegasus_data"}}})
    return variable_files, dataset_files


def _cache(source: str, root: str | Path | None, *parts: str) -> Path:
    from .config import load_settings

    path = Path(root or load_settings().root) / "registries" / source
    for part in parts:
        path = path / part
    return path


def _digest(*objects: Any) -> str:
    return hashlib.sha1(json.dumps(objects, sort_keys=True, default=str, ensure_ascii=False).encode("utf8")).hexdigest()[:12]


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")


# --- the API ---------------------------------------------------------------------------------------------------------

def get_json(url: str, params: dict[str, Any] | None = None, retries: int = 4) -> Any:
    """GET json, at most one request per INTERVAL per host, a browser User-Agent, backoff on 429/5xx and timeouts."""
    if not _client:
        _client.append(httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=120, follow_redirects=True))
    host = urlsplit(url).netloc
    for attempt in range(retries + 1):
        wait = INTERVAL - (time.time() - _last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()
        try:
            r = _client[0].get(url, params=params)
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            return r.json()
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == retries:
                raise
            time.sleep(5 * 2 ** attempt)
    raise AssertionError("unreachable")


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
    the ``totalPaginas`` the answer states."""
    paging = _paging(origin)
    url = origin["base"].rstrip("/") + path
    if paging["style"] == "offset":
        offset = start
        while True:
            page = get_json(url, {**params, paging["limit_param"]: paging["size"], paging["offset_param"]: offset}).get(paging["rows"]) or []
            if not page:
                return
            yield page
            offset += paging["size"]
    else:
        number = start // paging["size"] + 1
        while True:
            answer = get_json(url, {**params, paging["page_param"]: number, paging["size_param"]: paging["size"]})
            yield answer.get(paging["rows"]) or []
            if number >= int(answer.get(paging["pages_key"]) or 0):
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
    first = get_json(url, {**params, paging["limit_param"]: paging["size"], paging["offset_param"]: 0}).get(paging["rows"]) or []
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


def _as_table(rows: list[dict], schema: pa.Schema) -> pa.Table:
    clean = [{c: (None if r.get(c) is None else (r[c] if schema.field(c).type == pa.float64() else str(r[c]))) for c in schema.names} for r in rows]
    return pa.Table.from_pylist(clean, schema=schema)


def _as_strings(rows: list[dict], columns: list[str] | None = None) -> pa.Table:
    """Rows as an all-string table over ``columns`` (default: every key seen, in order of appearance)."""
    names = columns or list(dict.fromkeys(k for r in rows for k in r))
    got = lambda r, c: r.get(c, r.get(c.lower()))   # noqa: E731  (the API names its keys in lower case)
    return pa.table({c: pa.array([None if got(r, c) is None else str(got(r, c)) for r in rows], pa.string()) for c in names})


def read_slice(source: str, filters: dict[str, Any], *, root: str | Path | None = None, name: str | None = None, refresh: bool = False) -> pa.Table:
    """The rows of a declared API source that match ``filters`` (the endpoint's own parameters), the declared columns only,
    kept in ``registries/<source>/<name>`` (``name`` defaults to ``slices/<hash of the filters>.parquet``). A source with a
    filter is never paged whole; a past period does not change, the current one does (``refresh``). A source that declares
    a ``partition`` is read by it (see `_complete`); the table's schema metadata ``intake_unstable`` lists the filters that
    could not be and were paged. With ``snapshot: true`` every fresh read is also landed in the lake, dated by its read day."""
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
    table = _as_table(rows, _schema(spec))
    if unstable:
        table = table.replace_schema_metadata({"intake_unstable": json.dumps(unstable)})
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, target)
    if spec.get("snapshot") and table.num_rows:
        land_snapshot(source, table, label, datetime.now(UTC).date().isoformat(), root)
    return table


# --- the lake ----------------------------------------------------------------------------------------------------------

def _settings(root: str | Path | None = None) -> Any:
    from .config import load_settings

    return load_settings(root=Path(root)) if root else load_settings()


def _fold(text: str) -> str:
    import unicodedata

    # accents, case and punctuation between words (SNGPC's BIRITIBA-MIRIM is IBGE's Biritiba Mirim) are not the name
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))
    return " ".join(plain.upper().replace("-", " ").replace("'", " ").split())


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _duck(settings: Any, spec: dict[str, Any]) -> Any:
    """A DuckDB connection bounded in memory, with the IBGE universe (and, for a source that gives a municipality's name and
    its state, the names that resolve to one code) registered."""
    import duckdb

    from .geography import municipalities

    con = duckdb.connect(":memory:")
    work = Path(settings.work_dir) / "duckdb"
    work.mkdir(parents=True, exist_ok=True)
    con.execute("SET memory_limit='2GB'")
    con.execute("SET threads=4")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{work.as_posix()}'")
    universe = municipalities()
    con.register("universe", pa.table({"code": pa.array(sorted(universe), pa.string())}))
    # a state of one municipality (the Distrito Federal: Brasília) holds every place inside it, whatever the source
    # calls the place (SISAGUA codes the DF's administrative regions 530000-530015)
    by_state: dict[str, list[str]] = {}
    for code, row in universe.items():
        by_state.setdefault(row["uf_code"], []).append(code)
    sole = {uf: codes[0] for uf, codes in by_state.items() if len(codes) == 1}
    con.register("sole", pa.table({"uf": pa.array(list(sole), pa.string()), "code": pa.array(list(sole.values()), pa.string()),
                                   "sigla": pa.array([_fold(universe[c]["uf_sigla"]) for c in sole.values()], pa.string())}))
    place = spec.get("place") or {}
    if place.get("type") == "municipality_name":
        keys: dict[tuple[str, str], str | None] = {}
        for code, row in universe.items():
            for state in (row["uf_sigla"], row["uf_name"]):
                key = (_fold(state), _fold(row["name"]))
                keys[key] = None if key in keys and keys[key] != code else code
        found = {k: v for k, v in keys.items() if v}
        con.register("names", pa.table({"key": pa.array([f"{u}|{n}" for (u, n) in found], pa.string()),
                                        "code": pa.array(list(found.values()), pa.string())}))
        con.create_function("fold", _fold, ["VARCHAR"], "VARCHAR", null_handling="special")
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
            alias[re.sub(r"[^A-Z0-9]", "", _fold(spelling))] = name
    actual: dict[str, str] = {}
    for c in columns:
        clean = c.strip().lstrip("\ufeff")
        canonical = alias.get(re.sub(r"[^A-Z0-9]", "", _fold(clean)), clean.upper())
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
                   f"THEN (SELECT code FROM sole WHERE sole.uf = substr({text}, 1, 2)) END AS _MUNICIPALITY")
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
        month = f"CASE WHEN regexp_matches({m}, '^(1[0-2]|[1-9])$') THEN CAST({m} AS INTEGER) END"
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


def _land(settings: Any, source: str, spec: dict[str, Any], unit: dict[str, Any], con: Any, relation: str, read_on: str) -> dict[str, Any]:
    """Convert one relation of the source's rows to lake records (partitioned by record year), register them in the catalog,
    and return the unit's statistics. ``relation`` is a DuckDB table function or view of the rows."""
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
    for stale in target.glob(f"year=*/part-{key}-*.parquet"):
        stale.unlink()
    target.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({sql}) TO '{target.as_posix()}' (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (year), "
                f"FILENAME_PATTERN 'part-{key}-{{i}}', OVERWRITE_OR_IGNORE true, ROW_GROUP_SIZE 262144)")
    parts = sorted(target.glob(f"year=*/part-{key}-*.parquet"))
    pattern = (target / "year=*" / f"part-{key}-*.parquet").as_posix()
    place = spec.get("place") or {}
    placed = place.get("type") in ("municipality", "municipality_name")
    raw_place = _ident((place.get("column") or "").upper())
    stats = {"rows": 0, "undated": 0, "unplaced": 0, "unallocated": 0}
    if parts:
        select = "count(*), count_if(year = 0)"
        if placed:
            select += f", count_if({raw_place} IS NULL), count_if({raw_place} IS NOT NULL AND _MUNICIPALITY IS NULL)"
        row = con.execute(f"SELECT {select} FROM read_parquet('{pattern}', hive_partitioning=true)").fetchone()
        stats.update(rows=row[0], undated=row[1], unplaced=row[2] if placed else 0, unallocated=row[3] if placed else 0)
    _register(settings, source, spec, unit, family, signature, [n for n, _ in described], parts, lake, key)
    return {**stats, "years": sorted({int(p.parent.name.split("=")[1]) for p in parts}), "family": family}


def _register(settings: Any, source: str, spec: dict[str, Any], unit: dict[str, Any], family: str, signature: str, names: list[str],
              parts: list[Path], lake: Any, key: str) -> None:
    """Catalog rows that make the lake records a dataset ``query`` plans over: the family, one publication (file facts) per
    unit and record year, and the lake partitions that cover it. Idempotent for a unit."""
    from .catalog.store import CatalogStore, utcnow

    system, series = str(spec["system"]).upper(), str(spec["series"]).upper()
    now = utcnow()
    by_year: dict[int, list[Path]] = {}
    for part in parts:
        by_year.setdefault(int(part.parent.name.split("=")[1]), []).append(part)
    store = CatalogStore(settings.catalog_path)
    try:
        with store.write() as conn:
            conn.execute("DELETE FROM lake_partitions WHERE family_id=? AND relative_path LIKE ?", (family, f"%/part-{key}-%"))
            for year, files in sorted(by_year.items()):
                if year == 0:
                    continue                                          # undated: in the lake, never a publication
                path = f"{unit['path']}#year={year}"
                conn.execute("INSERT OR REPLACE INTO files (path, logical_id, directory, filename, extension, size, modified, "
                             "listing_method, change_signal, first_seen, last_seen, gone_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
                             (path, path, unit["path"].rsplit("/", 1)[0], path.rsplit("/", 1)[-1],
                              unit.get("extension", ""), int(unit.get("size") or 0), unit.get("modified"), "intake", "size", now, now))
                conn.execute("INSERT OR REPLACE INTO file_facts (path, system, series_prefix, geo_code, date_code, date_format, "
                             "normalized_date, year, grammar, container_format, role, logical_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                             (path, system, series, "BR", str(year), "YYYY", year * 100, year, "intake",
                              unit.get("extension", ""), "data", path))
                conn.execute("INSERT OR REPLACE INTO family_files (family_id, path, member) VALUES (?,?,?)", (family, path, ""))
                for part in files:
                    conn.execute(
                        "INSERT OR REPLACE INTO lake_partitions (family_id, schema_signature, uf, year, relative_path, row_count, "
                        "byte_size, source_paths, written_at, build_fingerprint) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (family, signature, "BR", year, str(part.relative_to(lake.root)).replace("\\", "/"),
                         pq.read_metadata(part).num_rows, part.stat().st_size, json.dumps([path]), now, unit.get("fingerprint")))
            years = [int(r[0]) for r in conn.execute("SELECT DISTINCT year FROM lake_partitions WHERE family_id=? AND year>0", (family,))]
            files_n = conn.execute("SELECT count(*) FROM family_files WHERE family_id=?", (family,)).fetchone()[0]
            conn.execute("INSERT OR REPLACE INTO families (family_id, system, series, schema_signature, field_count, time_min, time_max, "
                         "geo_coverage, file_count, stratum_count, schema_source, label, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (family, system, series, signature, len(names), min(years) if years else None, max(years) if years else None,
                          '["BR"]', files_n, 0, "intake", None, f"intake: {source}"))
            ids = [r[0] for r in conn.execute("SELECT family_id FROM families WHERE system=? AND series=?", (system, series))]
            conn.execute("INSERT OR REPLACE INTO lake_datasets (dataset, system, series, family_ids, description) VALUES (?,?,?,?,?)",
                         (f"{system}_{series}".lower(), system, series, json.dumps(ids), str(spec.get("what", ""))))
    finally:
        store.close()


def _span(text: Any) -> list[int]:
    out: list[int] = []
    for part in str(text).split(","):
        lo, _, hi = part.strip().partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def _units(spec: dict[str, Any], years: list[int] | None) -> list[dict[str, Any]]:
    """The pieces a files origin is read in: each file (with the year it stands for, when the declaration states one)."""
    origin = _origin(spec)
    out: list[dict[str, Any]] = []
    for entry in origin.get("files") or []:
        out.append({"key": entry.get("key") or Path(urlsplit(entry["url"]).path).name, "url": entry["url"], "year": entry.get("year")})
    if origin.get("pattern"):
        for period in _span(origin["years"] if origin.get("years") else origin["months"]):
            if not origin.get("years") and not 1 <= period % 100 <= 12:
                continue                     # a span of YYYYMM months ("201401-202110") holds no month 13 to 00
            out.append({"key": str(period), "url": origin["pattern"].format(year=period, period=period),
                        "year": period if origin.get("years") else int(str(period)[:4])})
    for unit in out:
        unit["path"] = unit["url"]
        unit["extension"] = Path(urlsplit(unit["url"]).path).suffix.lstrip(".").lower()
    return [u for u in out if not years or u["year"] is None or u["year"] in years]


def _fingerprint(spec: dict[str, Any], unit: dict[str, Any]) -> str:
    return _digest({k: spec.get(k) for k in ("columns", "place", "period", "origin")}, unit.get("url"), unit.get("key"))


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


def _file_relation(path: Path, origin: dict[str, Any]) -> tuple[str, Path | None]:
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
            f"encoding='{encoding}', null_padding=true)"), extracted


def _land_unit(settings: Any, source: str, spec: dict[str, Any], unit: dict[str, Any], refresh: bool) -> dict[str, Any]:
    from .sources import download

    root = settings.root
    unit["fingerprint"] = _fingerprint(spec, unit)
    side = _sidecar(source, root, unit["key"])
    if side.is_file() and not refresh:
        known = json.loads(side.read_text(encoding="utf8"))
        if known.get("fingerprint") == unit["fingerprint"]:
            return {**known["stats"], "cached": True}
    origin = _origin(spec)
    raw = download(unit["url"], _cache(source, root, "raw", _safe(unit["key"]) + "." + unit["extension"]))
    extracted = None
    con = _duck(settings, spec)
    try:
        relation, extracted = _file_relation(raw, origin)
        unit["size"] = raw.stat().st_size
        stats = _land(settings, source, spec, unit, con, relation, datetime.now(UTC).date().isoformat())
        if origin.get("format", "csv") == "csv":
            # the independent count: the file's own lines less the header. DuckDB's strict_mode=false dropped 4,007 of
            # SISAGUA 2019's 2,844,261 rows without an error (2026-10-10); a record the reader loses is a recorded gap
            lines = _lines(extracted or raw)
            stats["file_lines"] = lines
            stats["rows_equal_lines"] = stats.get("rows") == lines - 1
            if not stats["rows_equal_lines"]:
                raise ValueError(f"{source} {unit['key']}: {stats.get('rows')} records landed from {lines - 1} lines")
    finally:
        con.close()
        for path in (extracted, None if origin.get("keep") else raw):
            if path is not None and path.is_file():
                path.unlink()
    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_text(json.dumps({"fingerprint": unit["fingerprint"], "stats": stats}), encoding="utf8")
    return stats


def _lines(path: Path) -> int:
    """The newlines of a file (its records plus the header, where no field holds a line break), counted in blocks."""
    n = 0
    with path.open("rb") as f:
        while block := f.read(1 << 24):
            n += block.count(b"\n")
    return n


def _api_units(origin: dict[str, Any]) -> Iterator[tuple[str, str, Any]]:
    """The units a bulk API read is cut into, lazily: (key, path, rows-reader). With a declared ``partition`` a unit is one
    value of its first parameter (a state), read to the end by `_complete`, because offset paging of a table that applies
    its limit before de-duplication loses rows (the health-region list returned 4,870 of 5,571 municipalities unfiltered, all
    of them by state); otherwise a unit is `PIECE_PAGES` pages of offsets."""
    base, endpoint = origin["base"].rstrip("/"), origin["endpoint"]
    size = _paging(origin)["size"]
    if origin.get("partition"):
        level, rest = origin["partition"][0], origin["partition"][1:]
        for value in _partition_values(level, {}):
            yield (f"api-{level['param']}={value}", f"{base}{endpoint}?{level['param']}={value}",
                   lambda value=value: _complete(origin, endpoint, {level["param"]: value}, rest, []))
        return
    start = 0
    while True:
        def read(start: int = start) -> list[dict]:
            rows: list[dict] = []
            for count, page in enumerate(_pages(origin, endpoint, origin.get("params") or {}, start), 1):
                rows += page
                if count == PIECE_PAGES:
                    break
            return rows
        yield f"api-{start:010d}", f"{base}{endpoint}?offset={start}&pages={PIECE_PAGES}", read
        start += size * PIECE_PAGES


def _land_api(settings: Any, source: str, spec: dict[str, Any], refresh: bool) -> dict[str, Any]:
    """A bulk read of an API endpoint, landed unit by unit: an interrupted read resumes at its last unit."""
    origin = _origin(spec)
    total = {"rows": 0, "undated": 0, "unplaced": 0, "unallocated": 0, "units": 0}
    # A table without a period of its own (a reference, a current state) stands for the year it was read.
    year = datetime.now(UTC).year if (spec.get("period") or {}).get("type", "file") == "file" else None
    for key, path, read in _api_units(origin):
        unit = {"key": key, "year": year, "extension": "json", "size": 0, "path": path}
        unit["fingerprint"] = _fingerprint(spec, unit)
        side = _sidecar(source, settings.root, key)
        known = json.loads(side.read_text(encoding="utf8")) if side.is_file() and not refresh else None
        if known and known["fingerprint"] == unit["fingerprint"]:
            stats = known["stats"]
        else:
            rows = read()
            stats = {"rows": 0, "undated": 0, "unplaced": 0, "unallocated": 0}
            if rows:
                con = _duck(settings, spec)
                try:
                    con.register("api_piece", _as_strings(rows))
                    stats = _land(settings, source, spec, unit, con, "api_piece", datetime.now(UTC).date().isoformat())
                finally:
                    con.close()
            side.parent.mkdir(parents=True, exist_ok=True)
            side.write_text(json.dumps({"fingerprint": unit["fingerprint"], "stats": stats}), encoding="utf8")
        for k in ("rows", "undated", "unplaced", "unallocated"):
            total[k] += stats.get(k, 0)
        total["units"] += 1
        if not origin.get("partition") and stats.get("rows", 0) == 0:     # an empty unit is the end of an offset read
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

    con = _duck(settings, spec)
    report: dict[str, Any] = {}
    try:
        con.execute(f"CREATE VIEW rec AS SELECT * FROM read_parquet('{pattern}', union_by_name=true, hive_partitioning=true)")
        for name in names:
            fs = spec["fields"][name]
            keys = ([f"{place_sql} AS {place_name}"] if place else []) + ["year"] + (["_MONTH AS month"] if period.get("grain") == "month" else [])
            keys += [f"{raw_name(c)} AS {_ident(c.lower())}" for c in fs.get("by") or []]
            where = ["year > 0"] + ([f"{place_sql} IS NOT NULL"] if place else [])
            if valid:
                where.append(f"year BETWEEN {valid[0]} AND {valid[-1]}")
            if years:
                where.append(f"year IN ({','.join(str(int(y)) for y in years)})")
            for column, values in (fs.get("where") or {}).items():
                # a list: the raw value is one of them; {prefix: [...]}: it starts with one; {above / below / at_least /
                # at_most: x}: the typed value against a bound (a potability limit: turbidity above 5 uT)
                if isinstance(values, dict):
                    typed_col = _ident(column.upper())
                    bounds = {"above": ">", "below": "<", "at_least": ">=", "at_most": "<="}
                    parts = [f"{typed_col} {op} {float(values[k])}" for k, op in bounds.items() if k in values]
                    parts += [" OR ".join(f"starts_with({raw_name(column)}, {str(v)!r})" for v in values.get("prefix") or [])]
                    where.append("(" + " AND ".join(f"({x})" for x in parts if x) + ")")
                else:
                    where.append(f"{raw_name(column)} IN ({','.join(repr(str(v)) for v in values)})")
            measure = fs["measure"]
            if measure == "count":
                value = "count(*)"
            else:
                if declared.get(measure["sum"].upper(), {}).get("type") not in ("number", "result"):
                    raise ValueError(f"field {name}: sum of {measure['sum']} needs a column declared `type: number` or `result`")
                value = f"sum({_ident(measure['sum'].upper())})"
            group = ", ".join(str(i + 1) for i in range(len(keys)))
            table = con.execute(f"SELECT {', '.join(keys)}, {value} AS value FROM rec WHERE {' AND '.join(where)} GROUP BY {group}").fetch_arrow_table()
            table = table.set_column(table.schema.get_field_index("value"), "value", pc.cast(table.column("value"), pa.float64()))
            report[name] = _write_field(spec, Path(settings.lake_dir) / "fields", name, fs, table, place_name, years)
    finally:
        con.close()
    return report


def _write_field(spec: dict[str, Any], lake: Path, name: str, fs: dict[str, Any], table: pa.Table, place_name: str | None, years: list[int] | None) -> dict[str, Any]:
    import shutil

    from .geography import municipalities

    n = table.num_rows
    if place_name == "municipality":
        universe = municipalities()
        table = table.append_column("municipality7", pa.array([universe[c]["code7"] for c in table.column("municipality").to_pylist()], pa.string()))
    table = table.append_column("status", pa.array(["ok"] * n, pa.string()))
    table = table.append_column("unit", pa.array([str(fs.get("unit", ""))] * n, pa.string()))
    table = table.append_column("source", pa.array([str(spec.get("citation", ""))] * n, pa.string()))
    target = lake / name
    if not years and target.exists():
        for old in target.glob("year=*"):
            shutil.rmtree(old)
    by_year: dict[int, float] = {}
    for year in sorted(set(table.column("year").to_pylist())):
        part = table.filter(pc.equal(table.column("year"), year)).drop_columns(["year"])
        directory = target / f"year={int(year)}"
        directory.mkdir(parents=True, exist_ok=True)
        pq.write_table(part, directory / "part.parquet", compression="zstd")
        by_year[int(year)] = pc.sum(part.column("value")).as_py()
    return {"rows": n, "total": sum(by_year.values()), "by_year": by_year}


def build_source(settings: Any, source: str, names: list[str] | None = None, years: list[int] | None = None, refresh: bool = False) -> dict[str, Any]:
    """Land a declared source's records in the lake and derive its fields from them. Returns, per field, its rows, total and
    totals by year, and under ``units`` what each file or API unit held and what was left out of the fields and why."""
    spec = declared_sources()[source]
    fields = [f for f in spec.get("fields") or {} if not names or f in names]
    report: dict[str, Any] = {"units": {}}
    if _origin(spec)["kind"] == "api":
        report["units"]["api"] = _land_api(settings, source, spec, refresh)
    else:
        for unit in _units(spec, years):
            report["units"][unit["key"]] = _land_unit(settings, source, spec, unit, refresh)
    for k in ("rows", "undated", "unplaced", "unallocated"):
        report[k] = sum(u.get(k, 0) for u in report["units"].values())
    report.update(_derive(settings, spec, fields, years))
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
    from .sources import download

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
