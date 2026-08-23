"""HI-19: the lake is a derived-data cache, not just a storage target.

The raw CAS stops us re-downloading an unchanged blob. Nothing stopped us
re-decoding it: a repeated build read every blob, decompressed every DBC,
normalised it and rewrote partitions that were already correct.
"""

from __future__ import annotations

import pytest

from pegasus_data.build import partition_fingerprint
from pegasus_data.normalize.engine import FieldPlan, NormalizePlan, plan_fingerprint
from pegasus_data.normalize.geo import MunicipalityIndex


def _plan(**kw) -> NormalizePlan:
    base = {"family_id": "F1", "system": "SIHSUS", "schema_signature": "sig"}
    base.update(kw)
    return NormalizePlan(**base)  # type: ignore[arg-type]


GROUP = [
    {"path": "/p/RDAL2301.dbc", "member": ""},
    {"path": "/p/RDAL2302.dbc", "member": ""},
]
DIGESTS = {"/p/RDAL2301.dbc": "aaa", "/p/RDAL2302.dbc": "bbb"}


class TestSourceFingerprint:
    def test_the_same_files_in_a_different_order_are_the_same_partition(self):
        assert partition_fingerprint("P", GROUP, DIGESTS) == partition_fingerprint(
            "P", list(reversed(GROUP)), DIGESTS
        )

    def test_republished_content_under_the_same_name_is_a_different_partition(self):
        """DATASUS republishes a competência under the same path with new bytes."""
        moved = dict(DIGESTS, **{"/p/RDAL2302.dbc": "ccc"})
        assert partition_fingerprint("P", GROUP, DIGESTS) != partition_fingerprint(
            "P", GROUP, moved
        )

    def test_a_file_added_to_the_group_changes_it(self):
        bigger = GROUP + [{"path": "/p/RDAL2303.dbc", "member": ""}]
        assert partition_fingerprint("P", GROUP, DIGESTS) != partition_fingerprint(
            "P", bigger, dict(DIGESTS, **{"/p/RDAL2303.dbc": "ddd"})
        )

    def test_an_unresolved_file_contributes_its_absence(self):
        """So a later build that does fetch it does not look unchanged."""
        without = {"/p/RDAL2301.dbc": "aaa"}
        assert partition_fingerprint("P", GROUP, without) != partition_fingerprint(
            "P", GROUP, DIGESTS
        )

    def test_a_different_member_of_the_same_archive_is_a_different_partition(self):
        other = [dict(m, member="X") for m in GROUP]
        assert partition_fingerprint("P", GROUP, DIGESTS) != partition_fingerprint(
            "P", other, DIGESTS
        )


class TestTransformFingerprint:
    def test_it_is_stable_for_an_identical_plan(self):
        assert plan_fingerprint(_plan()) == plan_fingerprint(_plan())

    def test_field_order_does_not_change_it(self):
        a = _plan(fields={"A": FieldPlan(name="A"), "B": FieldPlan(name="B")})
        b = _plan(fields={"B": FieldPlan(name="B"), "A": FieldPlan(name="A")})
        assert plan_fingerprint(a) == plan_fingerprint(b)

    @pytest.mark.parametrize(
        "field_kwargs",
        [
            {"physical_type": "N"},
            {"width": 7},
            {"decimals": 2},
            {"semantic_type": "date"},
            {"aggregation": "summable"},
            {"sentinels": ["9999"]},
            {"labels": {"1": "Masculino"}},
            {"date_order": "DDMMYYYY"},
            {"codelist": "CID10"},
            {"hierarchical": True},
        ],
    )
    def test_every_field_decision_that_changes_output_changes_it(self, field_kwargs):
        plain = _plan(fields={"A": FieldPlan(name="A")})
        changed = _plan(fields={"A": FieldPlan(name="A", **field_kwargs)})
        assert plan_fingerprint(plain) != plan_fingerprint(changed), (
            f"{field_kwargs} changes the normalised output but not the fingerprint, "
            "so a rebuild after changing it would reuse stale partitions"
        )

    def test_emit_labels_and_keep_raw_change_it(self):
        assert plan_fingerprint(_plan()) != plan_fingerprint(_plan(emit_labels=False))
        assert plan_fingerprint(_plan()) != plan_fingerprint(_plan(keep_raw=False))

    def test_the_schema_signature_changes_it(self):
        assert plan_fingerprint(_plan()) != plan_fingerprint(_plan(schema_signature="other"))

    def test_the_transform_version_is_part_of_it(self):
        """The hand-bumped stand-in for 'the normalisation code changed'."""
        import pegasus_data.normalize.engine as engine

        before = plan_fingerprint(_plan())
        original = engine.TRANSFORM_VERSION
        try:
            engine.TRANSFORM_VERSION = original + "-next"
            assert plan_fingerprint(_plan()) != before
        finally:
            engine.TRANSFORM_VERSION = original

    def test_a_mapping_correction_with_the_same_size_invalidates_the_plan(self):
        old = MunicipalityIndex(six_to_seven={"355030": "3550308"})
        corrected = MunicipalityIndex(six_to_seven={"355030": "3550309"})
        assert old.size == corrected.size
        assert plan_fingerprint(_plan(municipalities=old)) != plan_fingerprint(
            _plan(municipalities=corrected)
        )


class TestPartitionIsCurrent:
    def test_a_catalog_row_alone_is_not_enough_evidence(self, tmp_path):
        """A deleted lake with a surviving catalog must not look fully built."""
        from pegasus_data.catalog.store import Catalog
        from pegasus_data.persist.lake import Lake

        catalog = Catalog(tmp_path / "catalog.sqlite")
        lake = Lake(tmp_path / "lake", catalog)
        catalog.execute(
            "INSERT INTO lake_partitions (family_id, schema_signature, uf, year, "
            "relative_path, row_count, byte_size, build_fingerprint) "
            "VALUES ('F1','sig','AL',2023,'SIHSUS/F1/x/part-00000.parquet',1,1,'FP')"
        )
        kw = {
            "system": "SIHSUS", "family_id": "F1", "schema_signature": "sig",
            "uf": "AL", "year": 2023,
        }
        assert not lake.partition_is_current(fingerprint="FP", **kw), (
            "the parquet the row names does not exist"
        )

        target = lake.root / "SIHSUS/F1/x/part-00000.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"not really parquet, but present")
        assert lake.partition_is_current(fingerprint="FP", **kw)
        assert not lake.partition_is_current(fingerprint="OTHER", **kw)
        catalog.close()

    def test_an_unknown_partition_is_never_current(self, tmp_path):
        from pegasus_data.catalog.store import Catalog
        from pegasus_data.persist.lake import Lake

        catalog = Catalog(tmp_path / "catalog.sqlite")
        lake = Lake(tmp_path / "lake", catalog)
        assert not lake.partition_is_current(
            system="SIHSUS", family_id="nope", schema_signature="sig",
            uf="AL", year=2023, fingerprint="FP",
        )
        catalog.close()
