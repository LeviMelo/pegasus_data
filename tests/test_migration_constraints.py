"""The migration checker reasoned about columns and nothing else.

`_declared_columns` skips any line beginning with a constraint word — correct
for reading columns, and it meant nothing read them at all. So a changed
composite `PRIMARY KEY (a, b)`, a UNIQUE that came or went, or a foreign key
that moved all looked identical to the checker, and a catalog whose keys no
longer match the code reading it passed as successfully migrated.

Two related holes: a column the schema declares NOT NULL or PRIMARY KEY was
added anyway with the constraint stripped, producing a database weaker than the
schema declares; and the version row was only ever written when absent, so a
catalog upgraded from version 1 reported version 1 forever.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from pegasus_data.catalog.store import (
    SCHEMA_VERSION,
    Catalog,
    CatalogSchemaError,
    _actual_constraints,
    _declared_columns,
    _declared_constraints,
    _missing_columns,
    _structural_mismatches,
)


class TestTheParserReadsTableLevelConstraints:
    def test_a_composite_primary_key_is_read(self):
        schema = (
            "CREATE TABLE IF NOT EXISTS t (\n  a TEXT,\n  b TEXT,\n"
            "  PRIMARY KEY (a, b)\n);"
        )
        assert _declared_constraints(schema)["t"]["pk"] == ["a", "b"]

    def test_key_order_is_preserved(self):
        """A reordered composite key is a different key, not the same set."""
        schema = (
            "CREATE TABLE IF NOT EXISTS t (\n  a TEXT,\n  b TEXT,\n"
            "  PRIMARY KEY (b, a)\n);"
        )
        assert _declared_constraints(schema)["t"]["pk"] == ["b", "a"]

    def test_an_inline_primary_key_is_read_too(self):
        schema = "CREATE TABLE IF NOT EXISTS t (\n  a TEXT PRIMARY KEY,\n  b TEXT\n);"
        assert _declared_constraints(schema)["t"]["pk"] == ["a"]

    def test_unique_constraints_are_read(self):
        schema = (
            "CREATE TABLE IF NOT EXISTS t (\n  a TEXT,\n  b TEXT,\n"
            "  UNIQUE (a, b)\n);"
        )
        assert _declared_constraints(schema)["t"]["unique"] == [["a", "b"]]

    def test_an_inline_unique_constraint_is_read(self):
        schema = "CREATE TABLE IF NOT EXISTS t (\n  a TEXT UNIQUE,\n  b TEXT\n);"
        assert _declared_constraints(schema)["t"]["unique"] == [["a"]]

    def test_a_foreign_key_is_read_without_swallowing_the_reference(self):
        """`FOREIGN KEY (path) REFERENCES files (path)` has two groups, and
        taking everything up to the last `)` made one garbage column name."""
        schema = (
            "CREATE TABLE IF NOT EXISTS t (\n  path TEXT,\n"
            "  FOREIGN KEY (path) REFERENCES files (path)\n);"
        )
        assert _declared_constraints(schema)["t"]["fk"] == [("path", "files", "path")]

    def test_columns_are_still_read_the_same_way(self):
        schema = (
            "CREATE TABLE IF NOT EXISTS t (\n  a TEXT,\n  b INTEGER,\n"
            "  PRIMARY KEY (a)\n);"
        )
        assert set(_declared_columns(schema)["t"]) == {"a", "b"}


class TestItComparesAgainstTheInstalledDatabase:
    @pytest.fixture
    def db(self, tmp_path):
        conn = sqlite3.connect(tmp_path / "t.sqlite")
        yield conn
        conn.close()

    def test_a_matching_composite_key_reads_back_identically(self, db):
        db.execute("CREATE TABLE t (a TEXT, b TEXT, PRIMARY KEY (a, b))")
        assert _actual_constraints(db, "t")["pk"] == ["a", "b"]

    def test_a_reordered_key_reads_back_reordered(self, db):
        db.execute("CREATE TABLE t (a TEXT, b TEXT, PRIMARY KEY (b, a))")
        assert _actual_constraints(db, "t")["pk"] == ["b", "a"]

    def test_a_unique_index_is_seen(self, db):
        db.execute("CREATE TABLE t (a TEXT, b TEXT, UNIQUE (a, b))")
        assert _actual_constraints(db, "t")["unique"] == [["a", "b"]]

    def test_a_foreign_key_is_seen(self, db):
        db.execute("CREATE TABLE files (path TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE t (path TEXT REFERENCES files (path))")
        assert _actual_constraints(db, "t")["fk"] == [("path", "files", "path")]


class TestConstrainedColumnsAreNotQuietlyWeakened:
    @pytest.fixture
    def db(self, tmp_path):
        conn = sqlite3.connect(tmp_path / "t.sqlite")
        conn.execute("CREATE TABLE t (a TEXT)")
        yield conn
        conn.close()

    def test_a_nullable_column_is_still_added(self, db):
        schema = "CREATE TABLE IF NOT EXISTS t (\n  a TEXT,\n  b TEXT\n);"
        assert [m[1] for m in _missing_columns(db, schema)] == ["b"]

    def test_a_not_null_column_is_not_added_with_the_constraint_stripped(self, db):
        """Adding it anyway produces a database weaker than the schema says."""
        schema = "CREATE TABLE IF NOT EXISTS t (\n  a TEXT,\n  b TEXT NOT NULL\n);"
        assert [m[1] for m in _missing_columns(db, schema)] == []

    def test_a_not_null_column_with_a_default_can_be_added(self, db):
        """SQLite accepts that one, and it does not weaken anything."""
        schema = "CREATE TABLE IF NOT EXISTS t (\n  a TEXT,\n  b TEXT NOT NULL DEFAULT ''\n);"
        assert [m[1] for m in _missing_columns(db, schema)] == ["b"]

    def test_a_primary_key_column_is_not_added(self, db):
        schema = "CREATE TABLE IF NOT EXISTS t (\n  a TEXT,\n  b TEXT PRIMARY KEY\n);"
        assert [m[1] for m in _missing_columns(db, schema)] == []


class TestConstraintComparisonIsSymmetric:
    @pytest.fixture
    def db(self, tmp_path):
        conn = sqlite3.connect(tmp_path / "extra.sqlite")
        yield conn
        conn.close()

    def test_an_extra_installed_primary_key_is_a_mismatch(self, db):
        db.execute("CREATE TABLE t (a TEXT PRIMARY KEY, b TEXT)")
        schema = "CREATE TABLE IF NOT EXISTS t (\n  a TEXT,\n  b TEXT\n);"
        assert any("primary key" in p for p in _structural_mismatches(db, schema))

    def test_an_extra_installed_unique_is_a_mismatch(self, db):
        db.execute("CREATE TABLE t (a TEXT UNIQUE, b TEXT)")
        schema = "CREATE TABLE IF NOT EXISTS t (\n  a TEXT,\n  b TEXT\n);"
        assert any("UNIQUE" in p for p in _structural_mismatches(db, schema))

    def test_an_extra_installed_foreign_key_is_a_mismatch(self, db):
        db.execute("CREATE TABLE parent (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE t (a TEXT REFERENCES parent(id), b TEXT)")
        schema = "CREATE TABLE IF NOT EXISTS t (\n  a TEXT,\n  b TEXT\n);"
        assert any("foreign keys" in p for p in _structural_mismatches(db, schema))


class TestTheVersionRow:
    def test_a_fresh_catalog_records_the_current_version(self, tmp_path):
        catalog = Catalog(tmp_path / "c.sqlite")
        try:
            row = catalog.query("SELECT MAX(version) AS v FROM schema_version")
            assert int(row[0]["v"]) == SCHEMA_VERSION
        finally:
            catalog.close()

    def test_an_upgraded_catalog_stops_reporting_the_old_version(self, tmp_path):
        """It only ever inserted when NO row existed, so a database upgraded
        from version 1 reported version 1 forever and the number could not be
        trusted to decide anything."""
        path = tmp_path / "c.sqlite"
        catalog = Catalog(path)
        catalog.close()
        raw = sqlite3.connect(path)
        raw.execute("DELETE FROM schema_version")
        raw.execute("INSERT INTO schema_version (version, applied_at) VALUES (1, '2020-01-01')")
        raw.commit()
        raw.close()

        catalog = Catalog(path)
        try:
            row = catalog.query("SELECT MAX(version) AS v FROM schema_version")
            assert int(row[0]["v"]) == SCHEMA_VERSION
        finally:
            catalog.close()

    def test_a_catalog_from_newer_code_is_refused(self, tmp_path):
        """Reading it with older code means reading columns whose meaning may
        have changed; nothing here can know what it does not know about."""
        path = tmp_path / "c.sqlite"
        catalog = Catalog(path)
        catalog.close()
        raw = sqlite3.connect(path)
        raw.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, '2099-01-01')",
            (SCHEMA_VERSION + 5,),
        )
        raw.commit()
        raw.close()

        with pytest.raises(CatalogSchemaError, match="understands"):
            Catalog(path)


def test_legacy_relation_migration_recovers_authority_and_local_precedence(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "relations.sqlite"
    Catalog(path).close()
    raw = sqlite3.connect(path)
    raw.execute("DROP TABLE semantic_relations")
    raw.execute(
        """
        CREATE TABLE semantic_relations (
          system TEXT NOT NULL, dataset TEXT NOT NULL DEFAULT '', field_name TEXT NOT NULL,
          relation_type TEXT NOT NULL, target_type TEXT NOT NULL,
          target_name TEXT NOT NULL DEFAULT '', artifact TEXT NOT NULL,
          source_namespace TEXT, target_namespace TEXT, valid_from TEXT, valid_to TEXT,
          status TEXT NOT NULL DEFAULT 'adjudicated', evidence TEXT,
          PRIMARY KEY (system, dataset, field_name, relation_type, target_type, target_name)
        )
        """
    )
    raw.executemany(
        "INSERT INTO semantic_relations (system,dataset,field_name,relation_type,"
        "target_type,target_name,artifact,valid_to,status,evidence) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "SIHSUS", "SIH.RD", "DIAG_PRINC", "rollup_to", "chapter",
                "chapter", "CID_SEEDED", "201012", "adjudicated", "shipped",
            ),
            (
                "SIHSUS", "SIH.RD", "FIELD", "rollup_to", "region",
                "region", "LOCAL", None, "adjudicated", "reviewed",
            ),
        ],
    )
    decision = {
        "system": "SIHSUS",
        "dataset": "SIH.RD",
        "field_name": "FIELD",
        "relation_type": "rollup_to",
        "target_type": "region",
        "target_name": "region",
        "artifact": "LOCAL",
        "source_namespace": None,
        "target_namespace": None,
        "valid_from": None,
        "valid_to": None,
        "status": "adjudicated",
        "evidence": "reviewed",
    }
    raw.execute(
        "INSERT INTO adjudication_items "
        "(key,kind,candidates_json,reason_opened,status,resolution,opened_at) "
        "VALUES ('legacy-local','semantic_relation','[]','reviewed','adjudicated',?, '2020')",
        (json.dumps(decision),),
    )
    raw.commit()
    raw.close()

    migrated = Catalog(path)
    try:
        rows = migrated.query(
            "SELECT relation_id, authority, artifact, valid_to FROM semantic_relations "
            "ORDER BY artifact"
        )
        assert len(rows) == 2
        assert all(str(row["relation_id"]).startswith("rel_") for row in rows)
        assert {row["artifact"]: row["authority"] for row in rows} == {
            "CID_SEEDED": "curated",
            "LOCAL": "local",
        }

        import pegasus_data.semantics.relations as relation_module
        from pegasus_data.semantics.relations import (
            RelationType,
            SemanticRelation,
            relations_for,
        )

        monkeypatch.setattr(
            relation_module,
            "load_relations",
            lambda *_args: (
                SemanticRelation(
                    "SIHSUS", "SIH.RD", "FIELD", RelationType.ROLLUP_TO,
                    "region", "region", "SHIPPED_CURRENT",
                ),
            ),
        )
        assert relations_for(
            "SIHSUS", "SIH.RD", "FIELD",
            relation_type=RelationType.ROLLUP_TO, catalog=migrated,
        )[0].artifact == "LOCAL"
    finally:
        migrated.close()


def test_v3_all_local_migration_is_repaired_on_upgrade(tmp_path) -> None:
    path = tmp_path / "v3-relations.sqlite"
    catalog = Catalog(path)
    catalog.execute(
        "INSERT INTO semantic_relations "
        "(relation_id,authority,system,dataset,field_name,relation_type,target_type,"
        "target_name,artifact,status) VALUES "
        "('wrong-v3-id','local','SIHSUS','SIH.RD','FIELD','rollup_to','region',"
        "'region','LEGACY_SEEDED','adjudicated')"
    )
    catalog.close()
    raw = sqlite3.connect(path)
    raw.execute("DELETE FROM schema_version")
    raw.execute(
        "INSERT INTO schema_version (version, applied_at) VALUES (3, '2026-08-23')"
    )
    raw.commit()
    raw.close()

    repaired = Catalog(path)
    try:
        row = repaired.query(
            "SELECT relation_id, authority FROM semantic_relations "
            "WHERE artifact='LEGACY_SEEDED'"
        )[0]
        assert row["authority"] == "curated"
        assert str(row["relation_id"]).startswith("rel_")
        assert row["relation_id"] != "wrong-v3-id"
    finally:
        repaired.close()
