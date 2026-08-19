"""Derived state must be REPLACED, not accumulated (§3).

Three idempotence bugs had the same shape: a recomputation that could refresh a
row but never retire one. ON CONFLICT DO UPDATE looks like idempotence and is
not — it propagates corrections to rows that still exist and silently keeps every
row that should have disappeared.

The `lake_partitions` case is the worst of the family because it fails *upward*:
a rebuilt partition landed beside its stale predecessor, `ds.dataset()` read the
union, and every row came back twice. An empty result gets noticed. A doubled one
gets published.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.persist.lake import Lake


def _batch(n: int, tag: str) -> pa.RecordBatch:
    return pa.RecordBatch.from_pydict({"id": list(range(n)), "tag": [tag] * n})


@pytest.fixture
def lake(settings, catalog: Catalog) -> Lake:
    return Lake(settings.lake_dir, catalog=catalog, compression="zstd", row_group_size=1000)


class TestPartitionsAreReplaced:
    ARGS = {"system": "SIHSUS", "family_id": "fam1", "schema_signature": "sig113",
            "uf": "AC", "year": 2024}

    def test_a_rebuild_replaces_rather_than_duplicates(self, lake: Lake, catalog: Catalog):
        lake.write_batches([_batch(10, "old")], source_paths=["/a"], **self.ARGS)
        lake.write_batches([_batch(10, "new")], source_paths=["/a"], **self.ARGS)

        table = lake.dataset("SIHSUS", "fam1").to_table()
        assert table.num_rows == 10, "the rebuild must supersede, not accumulate"
        assert set(table.column("tag").to_pylist()) == {"new"}

    def test_the_catalog_agrees_with_the_disk(self, lake: Lake, catalog: Catalog):
        lake.write_batches([_batch(10, "old")], source_paths=["/a"], **self.ARGS)
        lake.write_batches([_batch(4, "new")], source_paths=["/a"], **self.ARGS)

        registered = catalog.scalar("SELECT SUM(row_count) FROM lake_partitions")
        assert registered == 4
        assert catalog.count("lake_partitions") == 1
        on_disk = list(lake.partition_dir(**self.ARGS).glob("*.parquet"))
        assert len(on_disk) == 1, "a stale part left on disk is still read by ds.dataset()"

    def test_a_smaller_rebuild_does_not_leave_a_tail(self, lake: Lake):
        """The dangerous direction: fewer parts than last time."""
        big = [_batch(500, "old") for _ in range(3)]
        lake.write_batches(big, source_paths=["/a"], **self.ARGS)
        first = len(list(lake.partition_dir(**self.ARGS).glob("*.parquet")))
        lake.write_batches([_batch(1, "new")], source_paths=["/a"], **self.ARGS)
        assert lake.dataset("SIHSUS", "fam1").to_table().num_rows == 1
        assert first >= 1

    def test_other_partitions_are_untouched(self, lake: Lake, catalog: Catalog):
        lake.write_batches([_batch(10, "ac")], source_paths=["/a"], **{**self.ARGS, "uf": "AC"})
        lake.write_batches([_batch(7, "sp")], source_paths=["/b"], **{**self.ARGS, "uf": "SP"})
        lake.write_batches([_batch(3, "ac2")], source_paths=["/a"], **{**self.ARGS, "uf": "AC"})
        assert lake.dataset("SIHSUS", "fam1").to_table().num_rows == 10  # 3 + 7
        assert catalog.count("lake_partitions") == 2


class TestOrphanedFamiliesTakeTheirDerivedStateWithThem:
    def test_everything_keyed_on_a_family_is_pruned(self, catalog: Catalog):
        from pegasus_data.inventory.families import persist_families

        for table, cols, vals in (
            ("variable_profiles", "family_id, field_name, schema_signature", ("dead", "F", "s")),
            ("value_frequencies", "family_id, field_name, schema_signature, value, count, percent, rank",
             ("dead", "F", "s", "1", 1, 1.0, 1)),
            ("ledger", "system, family_id, field_name, schema_signature_scope",
             ("SIH", "dead", "F", "s")),
            ("field_codelists", "system, family_id, field_name, codelist, source, source_ref, confidence",
             ("SIH", "dead", "F", "C", "def", "x.def", 0.9)),
            ("lake_partitions", "family_id, schema_signature, uf, year, relative_path",
             ("dead", "s", "AC", 2024, "p.parquet")),
        ):
            catalog.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({','.join('?' * len(vals))})", vals
            )
        catalog.execute(
            "INSERT INTO families (family_id, system, series, schema_signature) VALUES "
            "('dead','SIH','RD','s')"
        )
        persist_families(catalog, [])
        for table in ("variable_profiles", "value_frequencies", "ledger",
                      "field_codelists", "lake_partitions", "families"):
            assert catalog.count(table, "family_id = 'dead'") == 0, table


class TestWithdrawalPropagates:
    def test_a_retired_series_stops_reporting_drift(self, catalog: Catalog):
        from pegasus_data.profile.drift import persist_drift

        catalog.execute(
            "INSERT INTO schema_drift (system, series, observed_strata, schema_signature_count, "
            "union_field_count, drift_status) VALUES ('SIHSUS','CM',1,1,10,'stable')"
        )
        persist_drift(catalog, [])
        assert catalog.count("schema_drift", "system='SIHSUS' AND series='CM'") == 0

    def test_a_field_that_stops_looking_renamed_is_withdrawn(self, catalog: Catalog):
        from pegasus_data.profile.drift import persist_renames

        catalog.execute(
            "INSERT INTO field_renames (system, series, field_name, present_in, absent_in) "
            "VALUES ('SIHSUS','RD','DIAG_SECUN','[]','[]')"
        )
        persist_renames(catalog, [])
        assert catalog.count("field_renames") == 0

    def test_a_withdrawn_def_binding_disappears(self, catalog: Catalog):
        from pegasus_data.semantics.dictionary import bind_codelists_to_fields

        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, source_ref, confidence) "
            "VALUES ('SIHSUS','','GONE','OLDCNV','def','old.def',0.9)"
        )
        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, source_ref, confidence) "
            "VALUES ('SIHSUS','','KEPT','DETECTED','detector','detector:cid',0.7)"
        )
        bind_codelists_to_fields(catalog)
        assert catalog.count("field_codelists", "field_name='GONE'") == 0
        assert catalog.count("field_codelists", "field_name='KEPT'") == 1, (
            "withdrawing def bindings must not touch another source's output"
        )

    def test_a_field_no_longer_profiled_leaves_the_ledger(self, catalog: Catalog):
        from pegasus_data.semantics.ledger import persist_ledger

        catalog.execute(
            "INSERT INTO ledger (system, family_id, field_name, schema_signature_scope, "
            "dictionary_coverage) VALUES ('SIHSUS','fam','DROPPED','sig',1.0)"
        )
        catalog.execute(
            "INSERT INTO ledger (system, family_id, field_name, schema_signature_scope, "
            "dictionary_coverage) VALUES ('SIASUS','fam','UNTOUCHED','sig',1.0)"
        )
        persist_ledger(catalog, [], systems=["SIHSUS"])
        assert catalog.count("ledger", "field_name='DROPPED'") == 0
        assert catalog.count("ledger", "field_name='UNTOUCHED'") == 1, (
            "the delete must respect the scope the build was given"
        )


class TestTheBugItself:
    """Pin the old behaviour, so the fix cannot be quietly undone."""

    ARGS = {"system": "SIHSUS", "family_id": "fam1", "schema_signature": "sig113",
            "uf": "AC", "year": 2024}

    def test_appending_by_part_number_duplicates_every_row(self, lake: Lake):
        """This is exactly what the build used to do, and what it produced.

        `next_part_number` counted the files already in the directory, so a
        rebuild started numbering after its own stale output instead of over it.
        Both parts stayed on disk, both stayed registered, and the dataset read
        the union — a doubled lake reporting a successful build.
        """
        part = lake.next_part_number(**self.ARGS)
        lake.write_batches([_batch(10, "old")], source_paths=["/a"], part=part, replace=False, **self.ARGS)
        part = lake.next_part_number(**self.ARGS)
        assert part == 1, "the second write numbered itself after the first"
        lake.write_batches([_batch(10, "new")], source_paths=["/a"], part=part, replace=False, **self.ARGS)

        doubled = lake.dataset("SIHSUS", "fam1").to_table()
        assert doubled.num_rows == 20, "the bug: 10 rows rebuilt into 20"
        assert sorted(set(doubled.column("tag").to_pylist())) == ["new", "old"]

    def test_the_default_path_does_not(self, lake: Lake):
        lake.write_batches([_batch(10, "old")], source_paths=["/a"], **self.ARGS)
        lake.write_batches([_batch(10, "new")], source_paths=["/a"], **self.ARGS)
        assert lake.dataset("SIHSUS", "fam1").to_table().num_rows == 10
