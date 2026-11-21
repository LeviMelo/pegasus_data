"""IBGE's CNEFE 2022: every address of the Census, georeferenced, to place a CEP inside its municipality (ADR-0205).

A hospital record files the patient's CEP (SIH-RD ``CEP``, eight digits) and the municipality of residence, and nothing
that says where in the municipality the CEP lies. The Cadastro Nacional de Endereços para Fins Estatísticos is the
Census's own list of addresses (111,102,875 records of 106,814,877 addresses in 931,499 CEPs; a record is an address
*species*: a dwelling and the shop under it are two records of one address), each with its CEP, its municipality and census
tract, and a coordinate.

**The files.** One zip per UF (``27_AL.zip`` ... ``35_SP.zip``, 3.9 GB in all) holding one ``;``-separated UTF-8 CSV of
34 columns, and the dictionary ``Dicionario_CNEFE_Censo_2022.xls`` that gives the codes (read, not guessed): ``NV_GEO_COORD``
(1 original coordinate of the Census, 2 modified for apartments sharing a number, 3 estimated where the address had none
or an invalid one, 4 the block face, 5 the locality, 6 the census tract) and ``COD_ESPECIE`` (1 private household ...
8 religious establishment). The last column's header is cut in the 22 zips kept, ``COD_TIPO_ESPECI``, where the
dictionary says ``COD_TIPO_ESPECIE`` (its values, 101 to 104, are the dictionary's dwelling types): it is landed under the
dictionary's name, and any other header is refused.

**Landed whole** (`land_uf`): every record, every column, under ``<lake>/cnefe_2022/uf=<UF>/`` as zstd Parquet, in the order
of the file. Identifiers, geography codes, ``CEP`` and the other ``COD_*`` and ``NV_GEO_COORD`` are strings of the width
filed; ``NUM_QUADRA``, ``NUM_FACE`` and ``NUM_ENDERECO`` are integers and the coordinates doubles (a value that does not
convert stops the landing, nothing is nulled). An empty field is null. ``NUM_ENDERECO`` 0 with ``DSC_MODIFICADOR`` ``SN`` is
"sem número" and stays as filed. The rows written are counted against the file's own newlines (read from the zip stream, not
from the parser) and its uncompressed size; the zip's CRC is verified by reading to the end; a UF is replaced, never added to.
The raw zip is kept under ``<root>/registries/ibge_cnefe/`` unless the disk is short (`MIN_FREE_GB`), when it is deleted once
its UF is landed and counted; its size and sha256 stay in ``manifest.json`` with the server's validators.

**Derived per CEP** (`derive_ceps`, ``<lake>/cnefe_2022_cep/uf=<UF>/``), one row per CEP and municipality: a CEP that spans
municipalities is several rows, never one chosen. From the addresses (one point per ``COD_UNICO_ENDERECO``, which every
record of the address repeats with the same CEP, tract and coordinate): the count of addresses (IBGE's own ``TOT_END``) and
of records, the records of each species (``n_private_households`` is IBGE's ``TOT_DP``), the median latitude and longitude
(each coordinate's median), the distance in metres from that median within which 50% and 90% of the addresses lie
(haversine), the addresses at each ``NV_GEO_COORD`` level (counts: a share is formed at use, CLAUDE.md §6), and the census
tracts with their address counts. ``municipality_addresses`` and ``municipality_ceps`` give the municipality's totals, so a
CEP that is the municipality's only one (a general CEP, which places nobody inside it) shows as such without a threshold.

**Checked** against IBGE's own aggregate by CEP (`check_against_aggregate`, ``Agregados_por_CEP_CNEFE_Censo_2022.zip``:
counts only, no coordinates): all 931,499 CEPs are in both and equal on the 13 columns the records can reproduce.

**Read** with `cep_points` (``pegasus-data cep-points``). A CEP is a centre and a spread, not always a place: 01001-000 (São Paulo)
holds 6,973 addresses with half of them within 17.8 km of its median.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import time
import warnings
import zipfile
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..config import UF_NUMERIC, Settings, load_settings
from ..persist.kept import write_atomic, write_json_atomic
from ..semantics.curation import declared
from ..transport import download, request

if TYPE_CHECKING:
    import pyarrow as pa

__all__ = ["AGGREGATE", "LEVELS", "SPECIES", "UF_FILES", "CnefeNotBuilt", "build_cnefe", "built_ufs", "cep_points",
           "check_against_aggregate", "derive_ceps", "land_uf", "manifest"]

BASE = "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/"
UF_URL = BASE + "Arquivos_CNEFE/CSV/UF/{code}_{uf}.zip"
#: What is read besides the 27 zips: the dictionaries (the evidence for `LEVELS` and `SPECIES`) and IBGE's aggregate by CEP.
DICTIONARY = ("Dicionario_CNEFE_Censo_2022.xls", BASE + "Arquivos_CNEFE/CSV/Dicionario_CNEFE_Censo_2022.xls")
AGGREGATE_DICTIONARY = ("Dicionario_Agregados_por_CEP_CNEFE_Censo_2022.xls",
                        BASE + "Agregados_por_CEP/Dicionario_Agregados_por_CEP_CNEFE_Censo_2022.xls")
AGGREGATE = ("Agregados_por_CEP_CNEFE_Censo_2022.zip", BASE + "Agregados_por_CEP/Agregados_por_CEP_CNEFE_Censo_2022.zip")

#: The 27 UF files: IBGE's numeric code and the abbreviation the lake partitions by.
UF_FILES: dict[str, str] = {abbreviation: code for code, abbreviation in UF_NUMERIC.items()}

#: The dictionary's codes (``curation/published_tables.yml``, ``ibge_cnefe:``, with the dictionary and the date): ``NV_GEO_COORD``
#: levels, the ``COD_ESPECIE`` species and, for each species, the derived column that counts its records (IBGE's ``TOT_DP`` ...).
LEVELS: dict[str, str] = declared("published_tables.yml", "ibge_cnefe", "levels")
_SPECIES_TABLE: dict[str, dict[str, str]] = declared("published_tables.yml", "ibge_cnefe", "species")
SPECIES: dict[str, str] = {k: v["label"] for k, v in _SPECIES_TABLE.items()}
SPECIES_COLUMNS: dict[str, str] = {k: v["column"] for k, v in _SPECIES_TABLE.items()}

#: The 34 columns of the file, in order, with the type each lands as ("s" string of the width filed, "i" integer, "d" double).
COLUMNS: list[tuple[str, str]] = [
    ("COD_UNICO_ENDERECO", "s"), ("COD_UF", "s"), ("COD_MUNICIPIO", "s"), ("COD_DISTRITO", "s"), ("COD_SUBDISTRITO", "s"),
    ("COD_SETOR", "s"), ("NUM_QUADRA", "i"), ("NUM_FACE", "i"), ("CEP", "s"), ("DSC_LOCALIDADE", "s"),
    ("NOM_TIPO_SEGLOGR", "s"), ("NOM_TITULO_SEGLOGR", "s"), ("NOM_SEGLOGR", "s"), ("NUM_ENDERECO", "i"), ("DSC_MODIFICADOR", "s"),
    *[(f"{kind}_COMP_ELEM{n}", "s") for n in range(1, 6) for kind in ("NOM", "VAL")],
    ("LATITUDE", "d"), ("LONGITUDE", "d"), ("NV_GEO_COORD", "s"), ("COD_ESPECIE", "s"), ("DSC_ESTABELECIMENTO", "s"),
    ("COD_INDICADOR_ESTAB_ENDERECO", "s"), ("COD_INDICADOR_CONST_ENDERECO", "s"), ("COD_INDICADOR_FINALIDADE_CONST", "s"),
    ("COD_TIPO_ESPECIE", "s")]
#: A header the files write otherwise than the dictionary (the 22 zips kept, 2026-10-24): the file's name for the dictionary's.
HEADER_ALIASES = {"COD_TIPO_ESPECI": "COD_TIPO_ESPECIE"}
#: Free disk (GB) under which a landed UF's zip is deleted (CLAUDE.md §3: this machine had 32 GB on 2026-10-24).
MIN_FREE_GB = 15.0
#: Rows per Parquet row group.
ROW_GROUP = 1 << 20
#: DuckDB's memory and threads for the derivation: the machine is shared with other work.
DUCKDB_MEMORY_GB = 8
DUCKDB_THREADS = 8


class CnefeNotBuilt(FileNotFoundError):
    """A read asked for a UF whose CNEFE tables are not built: not an absence of addresses."""


# ------------------------------------------------------------------------------------------------------------- places


def _source_dir(settings: Settings) -> Path:
    return Path(settings.registries_dir) / "ibge_cnefe"


def _records_dir(settings: Settings) -> Path:
    return Path(settings.lake_dir) / "cnefe_2022"


def _ceps_dir(settings: Settings) -> Path:
    return Path(settings.lake_dir) / "cnefe_2022_cep"


def _uf(value: str | int) -> str:
    """A UF as the lake names it (``AL``) from its abbreviation or IBGE's numeric code (``27``)."""
    text = str(value).strip().upper()
    if text in UF_FILES:
        return text
    if text in UF_NUMERIC:
        return UF_NUMERIC[text]
    raise ValueError(f"{value!r} is no UF (abbreviation or IBGE code); the CNEFE has {sorted(UF_FILES)}")


def manifest(settings: Settings | None = None) -> dict[str, Any]:
    """What was landed, from where, with what counts (``<root>/registries/ibge_cnefe/manifest.json``); empty before the first landing."""
    path = _source_dir(settings or load_settings()) / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"ufs": {}, "files": {}}


def _save_manifest(settings: Settings, data: dict[str, Any]) -> None:
    path = _source_dir(settings) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(data, path, indent=1, ensure_ascii=False, sort_keys=True)


def built_ufs(settings: Settings | None = None) -> list[str]:
    """The UFs whose per-CEP table is on disk."""
    base = _ceps_dir(settings or load_settings())
    return sorted(p.name[3:] for p in base.glob("uf=*") if (p / "part-0.parquet").is_file()) if base.is_dir() else []


# ---------------------------------------------------------------------------------------------------------- fetching


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 24):
            digest.update(chunk)
    return digest.hexdigest()


def _validators(url: str) -> dict[str, Any]:
    """What the server says of the file now: size, Last-Modified, ETag (a HEAD)."""
    headers = request(url, method="HEAD").headers
    return {"server_bytes": int(headers.get("Content-Length") or 0) or None, "last_modified": headers.get("Last-Modified"),
            "etag": headers.get("ETag")}


def _fetch(url: str, target: Path) -> Path:
    """The file at ``url``, kept at ``target`` (the project's one transport: resumed, retried, a browser User-Agent)."""
    return download(url, target)


def fetch_references(settings: Settings | None = None) -> dict[str, Path]:
    """The dictionary, the aggregate's dictionary and the aggregate by CEP, in ``<root>/registries/ibge_cnefe/``."""
    settings = settings or load_settings()
    return {name: _fetch(url, _source_dir(settings) / name) for name, url in (DICTIONARY, AGGREGATE_DICTIONARY, AGGREGATE)}


# --------------------------------------------------------------------------------------------------------- landing


class _Counted(io.RawIOBase):
    """A zip member read through: the bytes and the newlines seen, counted here and not by the CSV parser."""

    def __init__(self, raw: Any) -> None:
        super().__init__()
        self.raw, self.bytes, self.newlines, self.last = raw, 0, 0, b""

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        count = self.raw.readinto(buffer)
        if count:
            data = bytes(memoryview(buffer)[:count])
            self.bytes += count
            self.newlines += data.count(b"\n")
            self.last = data[-1:]
        return count


def _arrow_types() -> dict[str, Any]:
    import pyarrow as pa

    return {"s": pa.string(), "i": pa.int64(), "d": pa.float64()}


def _convert(archive: Path, staged: Path) -> dict[str, Any]:
    """The zip's CSV streamed to one Parquet file at ``staged``. Returns the counts: rows written, the file's own lines, bytes and
    the zip member's size, and the nulls and malformed CEPs seen. Raises when the header is not the dictionary's, when a value
    does not convert, when the rows are not the lines or when the bytes are not the member's size."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.csv as pacsv
    import pyarrow.parquet as pq

    kinds = _arrow_types()
    types = {name: kinds[kind] for name, kind in COLUMNS}
    file_types = {**types, **{old: types[new] for old, new in HEADER_ALIASES.items()}}
    schema = pa.schema([(name, types[name]) for name, _ in COLUMNS])
    with zipfile.ZipFile(archive) as zipped:
        members = [m for m in zipped.infolist() if not m.is_dir()]
        if len(members) != 1 or not members[0].filename.lower().endswith(".csv"):
            raise ValueError(f"{archive.name}: one CSV expected, found {[m.filename for m in members]}")
        member = members[0]
        with zipped.open(member) as raw:
            counted = _Counted(raw)
            reader = pacsv.open_csv(
                counted, read_options=pacsv.ReadOptions(block_size=1 << 25),
                parse_options=pacsv.ParseOptions(delimiter=";", quote_char=False),
                convert_options=pacsv.ConvertOptions(column_types=file_types, null_values=[""], strings_can_be_null=True, check_utf8=True))
            header = [HEADER_ALIASES.get(n, n) for n in reader.schema.names]
            if header != [name for name, _ in COLUMNS]:
                raise ValueError(f"{archive.name}: the header is not the dictionary's: {reader.schema.names}")
            rows, malformed = 0, 0
            nulls = dict.fromkeys(("COD_UNICO_ENDERECO", "COD_MUNICIPIO", "COD_SETOR", "CEP", "LATITUDE", "LONGITUDE", "NV_GEO_COORD",
                                   "COD_ESPECIE"), 0)
            pending: list[pa.RecordBatch] = []
            pending_rows = 0
            with pq.ParquetWriter(staged, schema, compression="zstd") as writer:
                def flush() -> None:
                    nonlocal pending, pending_rows
                    if pending:
                        writer.write_table(pa.Table.from_batches(pending, schema=schema), row_group_size=ROW_GROUP)
                        pending, pending_rows = [], 0

                for batch in reader:
                    batch = pa.RecordBatch.from_arrays(batch.columns, schema=schema)
                    rows += batch.num_rows
                    for name in nulls:
                        nulls[name] += batch.column(name).null_count
                    cep = batch.column("CEP")
                    malformed += batch.num_rows - cep.null_count - int(pc.sum(pc.match_substring_regex(cep, r"^[0-9]{8}$")).as_py() or 0)
                    pending.append(batch)
                    pending_rows += batch.num_rows
                    if pending_rows >= ROW_GROUP:
                        flush()
                flush()
            if raw.read(1):
                raise ValueError(f"{archive.name}: the CSV was not read to its end")
    lines = counted.newlines + (0 if counted.last == b"\n" else 1) - 1      # the header is a line, not a record
    if rows != lines:
        raise ValueError(f"{archive.name}: {rows} records written from {lines} lines")
    if counted.bytes != member.file_size:
        raise ValueError(f"{archive.name}: {counted.bytes} bytes read of the {member.file_size} the zip lists")
    return {"member": member.filename, "csv_bytes": counted.bytes, "csv_lines": lines, "rows": rows, "nulls": nulls,
            "cep_not_8_digits": malformed}


def land_uf(uf: str | int, settings: Settings | None = None, *, keep_raw: bool | None = None, force: bool = False,
            log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Land one UF's CNEFE records and derive its per-CEP table. Idempotent: a UF in the manifest with its files is not read again
    unless ``force``. ``keep_raw``: True keeps the zip, False deletes it once the UF is landed and counted, None (the default) deletes
    it only when the free disk is under `MIN_FREE_GB`. The old records of the UF are replaced only after the new ones are counted."""
    settings = settings or load_settings()
    uf = _uf(uf)
    say = log or (lambda text: None)
    record = manifest(settings)
    held = record["ufs"].get(uf)
    target = _records_dir(settings) / f"uf={uf}"
    if held and not force and any(target.glob("*.parquet")):
        if not (_ceps_dir(settings) / f"uf={uf}" / "part-0.parquet").is_file():
            held["ceps"] = derive_ceps(uf, settings, log=log)
            record["ufs"][uf] = held
            _save_manifest(settings, record)
        return {**held, "skipped": True}
    name = f"{UF_FILES[uf]}_{uf}.zip"
    archive = _source_dir(settings) / name
    url = UF_URL.format(code=UF_FILES[uf], uf=uf)
    started = time.perf_counter()
    fresh = not archive.is_file()
    say(f"{uf}: {'downloading' if fresh else 'using'} {name}")
    kept = {k: v for k, v in (record["files"].get(name) or {}).items() if k in ("server_bytes", "last_modified", "etag")}
    validators = _validators(url) if force or not kept else kept
    if force and archive.is_file():
        archive.unlink()
    _fetch(url, archive)
    fetched = time.perf_counter() - started
    size, digest = archive.stat().st_size, _sha256(archive)
    if validators.get("server_bytes") and validators["server_bytes"] != size:
        raise ValueError(f"{name}: {size} bytes on disk, {validators['server_bytes']} on the server")
    staging = Path(settings.work_dir) / "cnefe" / uf
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        say(f"{uf}: converting")
        counts = _convert(archive, staging / "part-0.parquet")
        parquet_bytes = (staging / "part-0.parquet").stat().st_size
        shutil.rmtree(target, ignore_errors=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(target))
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    record["files"][name] = {"url": url, "bytes": size, "sha256": digest, **{k: v for k, v in validators.items() if v is not None}}
    entry = {"file": name, **counts, "parquet_bytes": parquet_bytes, "landed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "seconds_fetch": round(fetched, 1), "seconds_convert": round(time.perf_counter() - started - fetched, 1)}
    record["ufs"][uf] = entry
    _save_manifest(settings, record)                        # the records are landed and counted; the per-CEP table follows
    entry["ceps"] = derive_ceps(uf, settings, log=log)
    free = shutil.disk_usage(archive.parent).free / 2**30
    if keep_raw is False or (keep_raw is None and free < MIN_FREE_GB):
        archive.unlink()
        entry["raw_deleted"] = f"{size} bytes, sha256 {digest[:12]}; free {free:.1f} GB"
        say(f"{uf}: {name} deleted (free disk {free:.1f} GB)")
    record["ufs"][uf] = entry
    _save_manifest(settings, record)
    say(f"{uf}: {counts['rows']:,} records, {entry['ceps']['rows']:,} CEP rows in {time.perf_counter() - started:.0f} s")
    return entry


# -------------------------------------------------------------------------------------------------------- deriving


def _connect(settings: Settings) -> Any:
    import duckdb

    spill = Path(settings.work_dir) / "duckdb_spill" / "cnefe"
    spill.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{DUCKDB_MEMORY_GB}GB'")
    con.execute(f"SET threads={DUCKDB_THREADS}")
    con.execute(f"SET temp_directory='{spill.as_posix()}'")
    return con


def derive_ceps(uf: str | int, settings: Settings | None = None, *, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """The per-CEP table of one landed UF, ``<lake>/cnefe_2022_cep/uf=<UF>/part-0.parquet`` (columns in the module docstring)."""
    settings = settings or load_settings()
    uf = _uf(uf)
    source = _records_dir(settings) / f"uf={uf}"
    if not any(source.glob("*.parquet")):
        raise CnefeNotBuilt(f"the CNEFE records of {uf} are not landed: run `pegasus-data cnefe --uf {uf}`")
    started = time.perf_counter()
    con = _connect(settings)
    glob = (source / "*.parquet").as_posix()
    con.execute(f"CREATE VIEW rec AS SELECT COD_UNICO_ENDERECO AS id, CEP AS cep, COD_MUNICIPIO AS m, COD_SETOR AS tract, LATITUDE AS lat, "
                f"LONGITUDE AS lon, NV_GEO_COORD AS level, COD_ESPECIE AS species FROM read_parquet('{glob}')")
    # an address is repeated by each of its records with the same attributes; a difference would leave it twice, and is counted
    con.execute("CREATE TABLE addr AS SELECT id, cep, m, tract, lat, lon, level FROM rec WHERE cep IS NOT NULL GROUP BY ALL")
    stats = con.execute("SELECT (SELECT count(*) FROM rec), (SELECT count(*) FROM rec WHERE cep IS NULL), (SELECT count(*) FROM addr), "
                        "(SELECT count(DISTINCT id) FROM addr)").fetchone()
    levels = ", ".join(f"count(*) FILTER (WHERE level = '{k}') AS n_coord_level_{k}" for k in LEVELS)
    species = ", ".join(f"count(*) FILTER (WHERE species = '{k}') AS {name}" for k, name in SPECIES_COLUMNS.items())
    metres = ("2 * 6371008.8 * asin(sqrt(least(1.0, pow(sin(radians(a.lat - c.lat) / 2), 2) "
              "+ cos(radians(c.lat)) * cos(radians(a.lat)) * pow(sin(radians(a.lon - c.lon) / 2), 2))))")
    target = _ceps_dir(settings) / f"uf={uf}"
    target.mkdir(parents=True, exist_ok=True)
    def copy_out(tmp: Path) -> None:
        con.execute(f"""
            COPY (
              WITH point AS (
                SELECT cep, m, count(*) AS n_addresses, median(lat) AS lat, median(lon) AS lon, {levels} FROM addr GROUP BY cep, m),
              spread AS (
                SELECT a.cep, a.m, quantile_cont({metres}, 0.5) AS radius_p50_m, quantile_cont({metres}, 0.9) AS radius_p90_m
                FROM addr a JOIN point c ON a.cep = c.cep AND a.m = c.m GROUP BY a.cep, a.m),
              kinds AS (
                SELECT cep, m, count(*) AS n_records, {species} FROM rec WHERE cep IS NOT NULL GROUP BY cep, m),
              tracts AS (
                SELECT cep, m, count(*) AS n_tracts, list({{'tract': tract, 'n_addresses': n}} ORDER BY n DESC, tract) AS tracts
                FROM (SELECT cep, m, tract, count(*) AS n FROM addr GROUP BY cep, m, tract) GROUP BY cep, m)
              SELECT cep, m AS municipality7, substr(m, 1, 6) AS municipality, n_addresses, n_records, {", ".join(SPECIES_COLUMNS.values())},
                     lat, lon, radius_p50_m, radius_p90_m, {", ".join(f"n_coord_level_{k}" for k in LEVELS)}, n_tracts, tracts,
                     (sum(n_addresses) OVER (PARTITION BY m))::BIGINT AS municipality_addresses, count(*) OVER (PARTITION BY m) AS municipality_ceps
              FROM point JOIN spread USING (cep, m) JOIN kinds USING (cep, m) JOIN tracts USING (cep, m)
              ORDER BY cep, m
            ) TO '{tmp.as_posix()}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 100000)""")

    try:
        write_atomic(target / "part-0.parquet", copy_out)
    finally:
        con.close()
    rows = _count(target / "part-0.parquet")
    return {"rows": rows, "records": stats[0], "records_without_cep": stats[1], "addresses": stats[3], "address_rows": stats[2],
            "addresses_with_differing_attributes": stats[2] - stats[3], "seconds": round(time.perf_counter() - started, 1)}


def _count(path: Path) -> int:
    import pyarrow.parquet as pq

    return pq.ParquetFile(path).metadata.num_rows


# ---------------------------------------------------------------------------------------------------------- building


def build_cnefe(ufs: Iterable[str | int] | None = None, settings: Settings | None = None, *, keep_raw: bool | None = None,
                force: bool = False, log: Callable[[str], None] | None = None, check: bool = True) -> dict[str, Any]:
    """Land the CNEFE for ``ufs`` (all 27 by default) and, with ``check``, compare the result with IBGE's aggregate by CEP.

    The next UF's zip is fetched while the current one is converted (one connection at a time: the transport spaces the requests).
    A UF that fails is reported and the others go on; the result lists them under ``failed``."""
    settings = settings or load_settings()
    wanted = [_uf(u) for u in (ufs if ufs is not None else UF_FILES)]
    say = log or (lambda text: None)
    result: dict[str, Any] = {"ufs": {}, "failed": {}}
    fetch_references(settings)
    with ThreadPoolExecutor(max_workers=1) as pool:
        def prefetch(uf: str) -> Any:
            held = manifest(settings)["ufs"].get(uf)
            archive = _source_dir(settings) / f"{UF_FILES[uf]}_{uf}.zip"
            if force or not (held and any((_records_dir(settings) / f"uf={uf}").glob("*.parquet"))):
                return pool.submit(_fetch, UF_URL.format(code=UF_FILES[uf], uf=uf), archive)
            return None

        ahead = prefetch(wanted[0]) if wanted else None
        for i, uf in enumerate(wanted):
            current, ahead = ahead, (prefetch(wanted[i + 1]) if i + 1 < len(wanted) else None)
            try:
                if current is not None:
                    current.result()                      # land_uf finds the zip on disk
                result["ufs"][uf] = land_uf(uf, settings, keep_raw=keep_raw, force=force, log=say)
            except Exception as exc:  # noqa: BLE001 - one UF's failure is reported, the others go on
                result["failed"][uf] = f"{type(exc).__name__}: {exc}"[:600]
                say(f"{uf}: FAILED {result['failed'][uf]}")
        if ahead is not None:
            ahead.result()
    landed = [uf for uf in wanted if uf in result["ufs"]]
    result["records"] = sum(result["ufs"][uf]["rows"] for uf in landed)
    result["cep_rows"] = sum(result["ufs"][uf]["ceps"]["rows"] for uf in landed)
    if check and landed:
        try:
            result["check"] = check_against_aggregate(settings, landed)
        except Exception as exc:  # noqa: BLE001 - the landing stands; the check can be run again
            result["check"] = {"error": f"{type(exc).__name__}: {exc}"[:600]}
        record = manifest(settings)
        record["check"] = result["check"]
        _save_manifest(settings, record)
    return result


# --------------------------------------------------------------------------------------------------------- checking


def _aggregate_table(settings: Settings) -> pa.Table:
    import pyarrow as pa
    import pyarrow.csv as pacsv

    archive = fetch_references(settings)[AGGREGATE[0]]
    with zipfile.ZipFile(archive) as zipped:
        (member,) = [m for m in zipped.infolist() if m.filename.lower().endswith(".csv")]
        with zipped.open(member) as raw:
            header = raw.readline().decode("utf-8").strip().split(";")
        types = {name: (pa.string() if name == "CEP" else pa.int64()) for name in header}
        with zipped.open(member) as raw:
            return pacsv.read_csv(raw, parse_options=pacsv.ParseOptions(delimiter=";"), convert_options=pacsv.ConvertOptions(column_types=types))


#: IBGE's aggregate columns that count the records of a species of ``COD_ESPECIE`` (``TOT_END`` counts distinct addresses), and its
#: dwelling-type columns by ``COD_TIPO_ESPECIE`` (declared in ``curation/published_tables.yml``).
_AGGREGATE_SPECIES = declared("published_tables.yml", "ibge_cnefe", "aggregate_species")
_AGGREGATE_TYPES = declared("published_tables.yml", "ibge_cnefe", "aggregate_types")


def check_against_aggregate(settings: Settings | None = None, ufs: Iterable[str | int] | None = None) -> dict[str, Any]:
    """The landed CNEFE of ``ufs`` (the built ones by default) against IBGE's own count by CEP, an independent figure computed by IBGE
    from the same Census: per CEP, the addresses (``TOT_END`` = distinct ``COD_UNICO_ENDERECO``), the records of each species and the
    dwellings of each type. The first two are read from the per-CEP table (the landing and the derivation together), the types from
    the records. A CEP spanning municipalities or UFs is summed over all of them. Returns, per column, the CEPs compared and equal and
    the two totals, and the CEPs only here and only in the aggregate (the latter is expected for a subset of UFs)."""
    settings = settings or load_settings()
    chosen = [_uf(u) for u in ufs] if ufs is not None else built_ufs(settings)
    missing = [u for u in chosen if u not in built_ufs(settings)]
    if not chosen or missing:
        raise CnefeNotBuilt(f"the CNEFE of {missing or 'any UF'} is not landed: run `pegasus-data cnefe`")
    aggregate = _aggregate_table(settings)
    con = _connect(settings)
    try:
        con.register("agg", aggregate)
        derived = ", ".join(f"'{(_ceps_dir(settings) / f'uf={uf}' / 'part-0.parquet').as_posix()}'" for uf in chosen)
        records = ", ".join(f"'{(_records_dir(settings) / f'uf={uf}' / '*.parquet').as_posix()}'" for uf in chosen)
        by_species = {col: SPECIES_COLUMNS[k] for col, k in _AGGREGATE_SPECIES.items()}
        con.execute("CREATE TABLE mine AS SELECT cep AS CEP, sum(n_addresses)::BIGINT AS TOT_END, sum(n_records)::BIGINT AS records, "
                    + ", ".join(f"sum({column})::BIGINT AS {col}" for col, column in by_species.items())
                    + f" FROM read_parquet([{derived}]) GROUP BY cep")
        con.execute("CREATE TABLE types AS SELECT CEP, " + ", ".join(
            f"count(*) FILTER (WHERE COD_TIPO_ESPECIE = '{k}') AS {col}" for col, k in _AGGREGATE_TYPES.items())
            + f" FROM read_parquet([{records}]) WHERE CEP IS NOT NULL AND COD_ESPECIE IN ('1', '2') GROUP BY CEP")
        con.execute("CREATE TABLE here AS SELECT mine.*, " + ", ".join(f"coalesce(types.{col}, 0) AS {col}" for col in _AGGREGATE_TYPES)
                    + " FROM mine LEFT JOIN types USING (CEP)")
        columns: dict[str, Any] = {}
        for name in ["TOT_END", *by_species, *_AGGREGATE_TYPES]:
            compared, equal, here, theirs = con.execute(
                f"SELECT count(*), count(*) FILTER (WHERE m.{name} = a.{name}), sum(m.{name}), sum(a.{name}) FROM here m JOIN agg a USING (CEP)").fetchone()
            columns[name] = {"ceps": compared, "equal": equal, "here": int(here or 0), "ibge": int(theirs or 0)}
        records_equal = con.execute("SELECT count(*) FILTER (WHERE m.records = a.TOT_END) FROM here m JOIN agg a USING (CEP)").fetchone()
        both = con.execute("SELECT count(*) FROM here JOIN agg USING (CEP)").fetchone()[0]
        here_n = con.execute("SELECT count(*) FROM here").fetchone()[0]
        return {"ufs": chosen, "ceps_here": here_n, "ceps_ibge": aggregate.num_rows, "ceps_in_both": both,
                "ceps_only_here": here_n - both, "ceps_only_in_ibge": aggregate.num_rows - both, "columns": columns,
                "ceps_whose_records_equal_TOT_END": records_equal[0]}
    finally:
        con.close()


# ------------------------------------------------------------------------------------------------------------ reading


def _municipality_filter(values: str | int | Iterable[str] | None) -> tuple[list[str], list[str]]:
    """Municipality codes as filed by DATASUS (six digits) or by IBGE (seven), each matched against its own column, as given."""
    if values is None:
        return [], []
    codes = [values] if isinstance(values, (str, int)) else list(values)
    six: list[str] = []
    seven: list[str] = []
    for code in codes:
        text = str(code).strip()
        if not text.isdigit() or len(text) not in (6, 7):
            raise ValueError(f"{code!r} is no municipality code (six digits as DATASUS writes it, or IBGE's seven)")
        (six if len(text) == 6 else seven).append(text)
    return six, seven


def cep_points(*, municipality: str | int | Iterable[str] | None = None, uf: str | int | Iterable[str | int] | None = None,
               cep: str | Iterable[str] | None = None, tracts: bool = True, shares: bool = True,
               settings: Settings | None = None) -> pa.Table:
    """Where each CEP lies: one row per CEP and municipality of the CNEFE 2022, filtered by ``municipality`` (a six-digit DATASUS
    code or IBGE's seven, one or several), ``uf`` (abbreviation or IBGE code) and ``cep`` (eight-digit strings, exact).

    Columns: ``uf``, ``cep``, ``municipality7``, ``municipality``, ``n_addresses`` (IBGE's ``TOT_END``), ``n_records``, the records of
    each species (``n_private_households`` is ``TOT_DP``), ``lat`` and ``lon`` (the median of the addresses' coordinates), ``radius_p50_m``
    and ``radius_p90_m`` (the distance from that median within which half and nine tenths of the addresses lie), ``n_coord_level_1`` ...
    ``_6`` (the addresses at each ``NV_GEO_COORD`` level, `LEVELS`; with ``shares`` also ``share_coord_level_k`` and
    ``share_address_coordinates``, levels 1 to 3), ``n_tracts`` and, with ``tracts``, ``tracts`` (census tract and its addresses),
    ``municipality_addresses`` and ``municipality_ceps``. A CEP with one address has radii 0 and says so by ``n_addresses``; a CEP
    that is the only one of its municipality (``municipality_ceps`` = 1) places nobody inside it.

    A UF not built raises `CnefeNotBuilt`; with no ``uf`` and fewer than 27 built, a CEP not found may belong to an unbuilt UF and a
    warning says so; a place filter that matches no CEP raises (an absent place is not an empty answer)."""
    import duckdb

    settings = settings or load_settings()
    built = built_ufs(settings)
    six, seven = _municipality_filter(municipality)
    if uf is not None:
        asked = [uf] if isinstance(uf, (str, int)) else list(uf)
        wanted = sorted({_uf(u) for u in asked})
    elif six or seven:
        wanted = sorted({UF_NUMERIC[c[:2]] for c in [*six, *seven] if c[:2] in UF_NUMERIC})
        if not wanted:
            raise ValueError(f"no UF holds the municipality code(s) {[*six, *seven]}")
    else:
        wanted = built
    missing = [u for u in wanted if u not in built]
    if missing or not wanted:
        raise CnefeNotBuilt(f"the CNEFE per-CEP table of {missing or 'any UF'} is not built: run `pegasus-data cnefe"
                            + (f" --uf {' --uf '.join(missing)}" if missing else "") + "`")
    if uf is None and not (six or seven) and len(built) < len(UF_FILES):
        warnings.warn(f"only {len(built)} of {len(UF_FILES)} UFs have their CNEFE built ({', '.join(built)}): a CEP not found "
                      f"here may belong to another", stacklevel=2)
    paths = [(_ceps_dir(settings) / f"uf={u}" / "part-0.parquet").as_posix() for u in wanted]
    conditions: list[str] = []
    params: list[Any] = []
    if six or seven:
        parts = []
        if six:
            parts.append(f"municipality IN ({', '.join('?' * len(six))})")
            params += six
        if seven:
            parts.append(f"municipality7 IN ({', '.join('?' * len(seven))})")
            params += seven
        conditions.append("(" + " OR ".join(parts) + ")")
    asked_ceps: list[str] = []
    if cep is not None:
        asked_ceps = [str(cep)] if isinstance(cep, (str, int)) else [str(c) for c in cep]
        conditions.append(f"cep IN ({', '.join('?' * len(asked_ceps))})")
        params += asked_ceps
    columns = "* EXCLUDE (tracts)" if not tracts else "*"
    extra = ""
    if shares:
        extra = ", " + ", ".join(f"n_coord_level_{k} / n_addresses AS share_coord_level_{k}" for k in LEVELS)
        extra += ", (n_coord_level_1 + n_coord_level_2 + n_coord_level_3) / n_addresses AS share_address_coordinates"
    con = duckdb.connect()
    try:
        table = con.execute(
            f"SELECT {columns}{extra} FROM read_parquet([{', '.join(repr(p) for p in paths)}], hive_partitioning = true) "
            + (("WHERE " + " AND ".join(conditions)) if conditions else "") + " ORDER BY uf, cep, municipality7", params).to_arrow_table()
    finally:
        con.close()
    if table.num_rows == 0 and not asked_ceps and (six or seven or uf is not None):
        raise LookupError(f"the CNEFE holds no CEP for municipality {[*six, *seven] or '(any)'} in {wanted}")
    return table


def record_places(ceps: Sequence[str | None], municipalities: Sequence[str | None], *, max_radius_m: float = 2000.0,
                  settings: Settings | None = None) -> pa.Table:
    """Where a record's person lives, at the finest place the record supports: one row per input pair, in order.

    A record (an admission, a notification) carries the residence CEP and the residence municipality. The CEP places the
    person at its addresses' median point (CNEFE 2022, `cep_points`) only when it is **specific**: found in the CNEFE
    within the record's own municipality, not a generic municipal CEP (``xxxxx-000``, written for a whole town), and its
    addresses within ``max_radius_m`` (their p90 radius). Otherwise the place is the municipality's population centre
    (`geography.municipality_point`). Neurosurgical and TBI admissions of 2023-2024 had a generic CEP on 39% and 47%, a CEP
    in one census tract on 17%, and an address spread under 600 m for half and over 9 km for a quarter (evaluation
    2026-11-21-record-places): a CEP's point is precise for about half of a national cohort and absent, not at random,
    for the rest (small and rural places write the town's CEP), so the municipality is the place every record has.

    Columns: ``cep``, ``municipality`` (as given), ``lat``, ``lon``, ``source`` ("cep", "municipality" or null when neither
    places it), ``radius_p90_m`` (the CEP's spread, when it is the source), ``n_tracts`` (census tracts the CEP's
    addresses lie in; with `cep_points(..., tracts=True)` they are named)."""
    import pyarrow as pa

    from ..geography import municipality_point, place_six

    if len(ceps) != len(municipalities):
        raise ValueError("record_places: one municipality per CEP")
    munis = [None if m is None else str(m).strip() for m in municipalities]
    six = place_six([m for m in munis if m])
    six_of = dict(zip([m for m in munis if m], six, strict=True))
    clean = [str(c).strip() if c is not None else "" for c in ceps]
    wanted = sorted({c for c in clean if len(c) == 8 and c.isdigit() and not c.endswith("000")})
    found: dict[tuple[str, str], dict[str, Any]] = {}
    if wanted:
        try:
            table = cep_points(cep=wanted, tracts=False, shares=False, settings=settings)
        except ValueError:   # no CEP of them is in the CNEFE: every record falls back to its municipality
            table = None
        if table is not None:
            for row in table.select(["cep", "municipality", "lat", "lon", "radius_p90_m", "n_tracts"]).to_pylist():
                found[(str(row["cep"]), str(row["municipality"]))] = row
    centres: dict[str, tuple[float, float] | None] = {}
    out: dict[str, list[Any]] = {k: [] for k in ("cep", "municipality", "lat", "lon", "source", "radius_p90_m", "n_tracts")}
    for c, m in zip(clean, munis, strict=True):
        m6 = six_of.get(m) if m else None
        hit = found.get((c, str(m6))) if m6 else None
        out["cep"].append(c or None)
        out["municipality"].append(m)
        if hit is not None and hit["radius_p90_m"] is not None and float(hit["radius_p90_m"]) <= max_radius_m:
            out["lat"].append(hit["lat"]); out["lon"].append(hit["lon"]); out["source"].append("cep")  # noqa: E702
            out["radius_p90_m"].append(hit["radius_p90_m"]); out["n_tracts"].append(hit["n_tracts"])  # noqa: E702
            continue
        if m6 and m6 not in centres:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                centres[m6] = municipality_point(m6)
        point = centres.get(m6) if m6 else None
        out["lat"].append(point[1] if point else None); out["lon"].append(point[0] if point else None)  # noqa: E702
        out["source"].append("municipality" if point else None)
        out["radius_p90_m"].append(None); out["n_tracts"].append(None)  # noqa: E702
    return pa.table(out)
