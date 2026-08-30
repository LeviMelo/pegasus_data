"""Shared fixtures.

Tests are offline by default. Anything needing ``ftp.datasus.gov.br`` or the
DEMAS API is marked ``network`` and skipped unless ``PEGASUS_TEST_NETWORK=1``.
"""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
from pathlib import Path

import pyarrow as pa
import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.config import Settings
from pegasus_data.inventory.families import family_id_for, schema_signature
from pegasus_data.persist.lake import Lake
from pegasus_data.semantics.dictionary import (
    CodelistBinding,
    DictionaryEntry,
    persist_bindings,
    persist_entries,
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("PEGASUS_TEST_NETWORK") == "1":
        return
    skip = pytest.mark.skip(reason="set PEGASUS_TEST_NETWORK=1 to run tests that hit the network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _isolated_placement(tmp_path_factory, monkeypatch):
    """No test may read the machine it runs on.

    Placement resolves through config files now — a project one found by walking
    up from the working directory, and a per-user one under %APPDATA% or
    ~/.config. Both are real files on a real developer's machine, and a suite
    that reads them passes or fails depending on whose laptop it is. Pointed at
    an empty temp directory instead, and every placement environment variable
    cleared, so the layers under test are the ones the test sets.
    """
    from pegasus_data.locate import PLACEMENT_KEYS

    empty = tmp_path_factory.mktemp("no-config")
    monkeypatch.setenv("PEGASUS_CONFIG", str(empty / "absent.toml"))
    for env_name, _ in PLACEMENT_KEYS.values():
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.chdir(empty)
    yield


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(root=tmp_path / "home")
    s.ensure_dirs()
    return s


@pytest.fixture
def catalog(settings: Settings) -> Catalog:
    cat = Catalog(settings.catalog_path)
    yield cat
    cat.close()


@pytest.fixture
def fresh_catalog(tmp_path: Path) -> Catalog:
    """A second, empty catalog — the machine that never crawled anything.

    What a bundle is *for*: this one has no files, no profiles and no network,
    and after unpacking it must still be able to say what a code means.
    """
    other = Settings(root=tmp_path / "elsewhere")
    other.ensure_dirs()
    cat = Catalog(other.catalog_path)
    yield cat
    cat.close()


def make_dbf(
    fields: list[tuple[str, str, int, int]], rows: list[list[str]], *, encoding: str = "cp850"
) -> bytes:
    """Build a minimal dBase III file in memory.

    Used instead of a checked-in binary so the expectations are visible in the
    test itself: field widths, the deletion flag, and the record count in the
    header are all things the reader has to get right.
    """
    header_len = 32 + 32 * len(fields) + 1
    record_len = 1 + sum(f[2] for f in fields)
    out = bytearray()
    out += bytes([0x03])
    out += bytes([124, 1, 1])  # yy, mm, dd
    out += struct.pack("<IHH", len(rows), header_len, record_len)
    out += bytes(20)
    for name, ftype, width, decimals in fields:
        out += name.encode("ascii")[:11].ljust(11, b"\x00")
        out += ftype.encode("ascii")
        out += bytes(4)
        out += bytes([width, decimals])
        out += bytes(14)
    out += b"\x0d"
    for row in rows:
        out += b" "
        for (_, _, width, _), value in zip(fields, row, strict=True):
            out += str(value).encode(encoding, errors="replace")[:width].ljust(width, b" ")
    out += b"\x1a"
    return bytes(out)


@pytest.fixture
def sample_dbf() -> bytes:
    return make_dbf(
        [("CODE", "C", 4, 0), ("SEXO", "C", 1, 0), ("VALOR", "N", 8, 2), ("NOME", "C", 12, 0)],
        [
            ["A001", "1", "00012345", "MARIA"],
            ["B992", "2", "00000099", "JOÃO"],
            ["C500", "1", "00500000", "ANTÔNIO"],
        ],
    )

# `built_lake` lives here rather than in test_api.py because test_scan.py needs
# the same thing: a miniature SIH-RD with TWO schema generations, which is what
# makes the missing-column policy and generation-scoped scanning testable.

@pytest.fixture
def built_lake(settings: Settings, catalog: Catalog) -> tuple[Settings, Catalog, str]:
    """A miniature SIH-RD with two schema generations and a decoded SEXO."""
    fields_old = ["MUNIC_RES", "SEXO", "DIAG_SECUN", "VAL_TOT"]
    fields_new = ["MUNIC_RES", "SEXO", "DIAGSEC1", "VAL_TOT"]
    sig_old, sig_new = schema_signature(fields_old), schema_signature(fields_new)
    fam_old = family_id_for("SIHSUS", "RD", sig_old)
    fam_new = family_id_for("SIHSUS", "RD", sig_new)

    catalog.executemany(
        """INSERT INTO families (family_id, system, series, schema_signature, field_count,
           time_min, time_max, geo_coverage, file_count) VALUES (?,?,?,?,?,?,?,?,?)""",
        [
            (fam_old, "SIHSUS", "RD", sig_old, 4, 2008, 2014, '["AL"]', 2),
            (fam_new, "SIHSUS", "RD", sig_new, 4, 2015, 2024, '["AL"]', 2),
        ],
    )
    catalog.executemany(
        "INSERT INTO schema_presence (schema_signature, field_name, field_order) VALUES (?,?,?)",
        [(sig_old, f, i) for i, f in enumerate(fields_old)]
        + [(sig_new, f, i) for i, f in enumerate(fields_new)],
    )
    catalog.executemany(
        """INSERT INTO variable_profiles (family_id, field_name, schema_signature, semantic_type,
           semantic_confidence, semantic_evidence, distinct_count, physical_type, width)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        [
            (fam_new, "SEXO", sig_new, "categorical_undecoded", 0.5, '{"rule":"categorical"}', 2, "C", 1),
            (fam_new, "MUNIC_RES", sig_new, "municipality_code_6", 0.8, '{"rule":"municipality"}', 3, "C", 6),
            (fam_new, "VAL_TOT", sig_new, "money", 0.9, '{"rule":"money"}', 4, "N", 10),
        ],
    )
    catalog.executemany(
        """INSERT INTO value_frequencies (family_id, field_name, schema_signature, value, count, percent, rank)
           VALUES (?,?,?,?,?,?,?)""",
        [
            (fam_new, "SEXO", sig_new, "1", 60, 0.6, 1),
            (fam_new, "SEXO", sig_new, "2", 40, 0.4, 2),
        ],
    )
    persist_entries(
        catalog,
        [
            DictionaryEntry(
                system="SIHSUS", value_raw="1", value_label="Masculino", source="cnv",
                source_ref="TAB_SIH.zip!SEXO.CNV:3", confidence=0.95, value_group="SEXO",
            ),
            DictionaryEntry(
                system="SIHSUS", value_raw="2", value_label="Feminino", source="cnv",
                source_ref="TAB_SIH.zip!SEXO.CNV:4", confidence=0.95, value_group="SEXO",
            ),
            DictionaryEntry(
                system="SIHSUS", value_raw="270430", value_label="Maceió", source="cnv",
                source_ref="TAB_SIH.zip!MUNIC.CNV:9", confidence=0.95, value_group="MUNIC",
            ),
            DictionaryEntry(
                system="SIHSUS", value_raw="271070", value_label="Rio Largo", source="cnv",
                source_ref="TAB_SIH.zip!MUNIC.CNV:10", confidence=0.95, value_group="MUNIC",
            ),
        ],
    )
    persist_bindings(
        catalog, [CodelistBinding("SIHSUS", "SEXO", "SEXO", "def", "TAB_SIH.zip!RD.DEF:12", 0.9)]
    )
    catalog.executemany(
        """INSERT INTO def_variables (def_path, system, usage, display_name, field_name, line_no)
           VALUES (?,?,?,?,?,?)""",
        [("d", "SIHSUS", "L", "Sexo", "SEXO", 12), ("d", "SIHSUS", "I", "Valor Total", "VAL_TOT", 7)],
    )

    from pegasus_data.semantics.ledger import build_ledger, persist_ledger

    persist_ledger(catalog, build_ledger(catalog))

    # The view layer joins labels from lake/reference/ at read time, so the
    # reference tables have to exist for a label to be producible at all.
    from pegasus_data.persist.reference import register_reference_tables, write_reference_tables

    register_reference_tables(catalog, write_reference_tables(catalog, settings.lake_dir))

    # code_system is what decides replace-vs-accompany (§5.2), and it lives in
    # the curated dictionary rather than in a heuristic.
    catalog.executemany(
        """INSERT INTO variable_docs (system, field_name, code_system, codelist, source,
           asserted_by) VALUES (?,?,?,?,?,?)""",
        [
            ("SIHSUS", "SEXO", "internal", "SEXO", "manual", "test"),
            ("SIHSUS", "MUNIC_RES", "external", "MUNIC", "manual", "test"),
            ("SIHSUS", "VAL_TOT", "none", None, "manual", "test"),
        ],
    )

    lake = Lake(settings.lake_dir, catalog)
    table = pa.table(
        {
            "MUNIC_RES": pa.array(["270430", "270430", "271070"]),
            "SEXO": pa.array(["1", "2", "1"]),
            "SEXO_label": pa.array(["Masculino", "Feminino", "Masculino"]),
            "DIAGSEC1": pa.array(["W199", None, "V878"]),
            "VAL_TOT": pa.array([1234.5, 99.0, 7000.0]),
        }
    )
    lake.write_batches(
        table.to_batches(), system="SIHSUS", family_id=fam_new,
        schema_signature=sig_new, uf="AL", year=2020,
    )
    return settings, catalog, fam_new

# The offline SIH-RD fixture. Here rather than in test_retrieve.py because
# test_entry_point_parity.py drives fetch(), load(), scan() and export() over
# ONE fixture on purpose: a guarantee tested only through the door that has it
# is how this project's policies kept diverging.

FIELDS = [("N_AIH", "C", 6, 0), ("SEXO", "C", 1, 0), ("DIAG_PRINC", "C", 4, 0)]
NAMES = [f[0] for f in FIELDS]
SIGNATURE = schema_signature(NAMES)


def one_file(rows: int = 2) -> bytes:
    return make_dbf(
        FIELDS, [[f"A{n:05d}", "1" if n % 2 else "3", "I219"] for n in range(rows)]
    )


class FakeFetcher:
    """Stands in for the FTP fetcher: every path resolves to the same bytes.

    ``missing`` names paths that fail, which is how the undecoded-file reporting
    is exercised without needing a broken file on a real server.
    """

    def __init__(self, missing: set[str] | None = None) -> None:
        self.missing = missing or set()
        self.asked: list[str] = []

    def ensure(self, paths):
        self.asked.extend(paths)
        return {p: f"sha-{p}" for p in paths if p not in self.missing}


class FakeBlobs:
    """A content-addressed store, backed by real files like the real one.

    It used to serve bytes only. The decode path now takes the blob's PATH —
    the blob is already a file, and reading it into RAM to hand the bytes to a
    decoder that writes them straight back out was three copies for nothing —
    so a double that cannot produce a path is no longer a double of anything.
    """

    def __init__(self, payload_for=None) -> None:
        self.payload_for = payload_for or (lambda _digest: one_file())
        self._dir = tempfile.mkdtemp(prefix="pegasus_fakeblobs_")

    def read(self, digest: str) -> bytes:
        return self.payload_for(digest)

    def path_for(self, digest: str) -> Path:
        # The fixtures use readable stand-ins like "sha-/p/RDAL2301.dbc" for
        # digests, so the name is hashed rather than used as a path.
        target = Path(self._dir) / hashlib.sha256(digest.encode()).hexdigest()
        if not target.is_file():
            target.write_bytes(self.payload_for(digest))
        return target


@pytest.fixture
def seeded(settings, monkeypatch):
    """A catalog that already knows one SIH-RD family across two states/years."""
    catalog = Catalog(settings.catalog_path)
    catalog.execute(
        "INSERT INTO families (family_id, system, series, schema_signature, field_count) "
        "VALUES ('F1','SIHSUS','RD',?,3)",
        (SIGNATURE,),
    )
    for path, uf, year, date in (
        ("/p/RDAL2301.dbc", "AL", 2023, 202301),
        ("/p/RDAL2302.dbc", "AL", 2023, 202302),
        ("/p/RDSP2401.dbc", "SP", 2024, 202401),
    ):
        catalog.execute(
            "INSERT INTO files (path, directory, filename, first_seen, last_seen) "
            "VALUES (?,?,?,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')",
            (path, "/p", path.rsplit("/", 1)[-1]),
        )
        catalog.execute(
            "INSERT INTO file_facts (path, system, series_prefix, geo_code, year, "
            "normalized_date, role) VALUES (?,'SIHSUS','RD',?,?,?,'data')",
            (path, uf, year, date),
        )
        catalog.execute(
            "INSERT INTO family_files (family_id, path, member) VALUES ('F1', ?, '')", (path,)
        )
    catalog.close()

    import pegasus_data.retrieve as retrieve

    state: dict[str, object] = {"fetcher": FakeFetcher(), "blobs": FakeBlobs()}

    real_pipeline = retrieve.Pipeline

    def make(settings_arg, *args, **kwargs):
        pipeline = real_pipeline(settings_arg, *args, **kwargs)
        pipeline.fetcher = state["fetcher"]
        pipeline.blobs = state["blobs"]
        return pipeline

    monkeypatch.setattr(retrieve, "Pipeline", make)
    return state


#: A hand-built base cuboid: two Acre municipalities in one health region, one
#: Sao Paulo, two months. Shared by every test that needs an artifact to serve
#: from, because building one by fetching would put DATASUS in the test loop.
# The fixture mirrors the SHIPPED spec's key and state columns exactly --
# widening the spec means widening this, or every capability/serve test runs
# against an artifact the spec no longer describes.
AGGREGATE_CELLS = [
    # municipality, competencia, SEXO, RACA_COR, CAR_INT, MORTE, ESPEC, COMPLEX,
    #   FAIXA_ETARIA, adm, deaths, los_n, los_sum, cost, uti
    ("120040", "202201", "1", "01", "01", "0", "01", "2", "025", 10.0, 1.0, 10.0, 40.0, 1000.0, 3.0),
    ("120040", "202201", "3", "01", "02", "0", "03", "2", "040", 6.0, 0.0, 6.0, 12.0, 600.0, 0.0),
    ("120040", "202202", "1", "02", "01", "1", "01", "3", "080", 4.0, 1.0, 4.0, 8.0, 400.0, 12.0),
    ("120020", "202201", "1", "01", "02", "0", "02", "2", "000", 5.0, 0.0, 5.0, 25.0, 500.0, 0.0),
    ("355030", "202202", "3", "01", "01", "0", "01", "2", "ZIG", 2.0, 0.0, 0.0, 0.0, 200.0, 1.0),
]
AGGREGATE_KEYS = (
    "municipality", "competencia", "SEXO", "RACA_COR", "CAR_INT", "MORTE",
    "ESPEC", "COMPLEX", "FAIXA_ETARIA",
)
AGGREGATE_STATES = (
    "admissions_n", "deaths_sum", "los_n", "los_sum", "cost_sum", "uti_days_sum",
)
AGGREGATE_NAME = "sih_rd_municipality_month"


def write_aggregate(root) -> Settings:
    """Materialise AGGREGATE_CELLS as a built artifact under `root`."""
    import json as _json

    import pyarrow as _pa
    import pyarrow.parquet as _pq

    from pegasus_data._aggregate import artifact_dir
    from pegasus_data.config import load_settings as _load

    resolved = _load(root=root)
    target = artifact_dir(AGGREGATE_NAME, resolved)
    target.mkdir(parents=True, exist_ok=True)
    table = _pa.table({
        **{name: _pa.array([r[i] for r in AGGREGATE_CELLS], _pa.string())
           for i, name in enumerate(AGGREGATE_KEYS)},
        **{name: _pa.array([r[len(AGGREGATE_KEYS) + i] for r in AGGREGATE_CELLS], _pa.float64())
           for i, name in enumerate(AGGREGATE_STATES)},
    })
    _pq.write_table(table, target / "cells.parquet")
    (target / "manifest.json").write_text(_json.dumps({
        "name": AGGREGATE_NAME, "fingerprint": "test",
        "cells": len(AGGREGATE_CELLS), "years": [2022],
        "support": {"2022": {
            "SEXO": "present", "RACA_COR": "present", "CAR_INT": "present",
            "MORTE": "present", "ESPEC": "present", "COMPLEX": "present",
            "FAIXA_ETARIA": "present",
        }},
        "key_columns": list(AGGREGATE_KEYS),
    }), encoding="utf-8")
    return resolved


@pytest.fixture
def aggregate_lake(tmp_path):
    """Settings whose lake holds one built artifact."""
    return write_aggregate(tmp_path)
