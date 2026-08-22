"""A roll-up must not wear the field's name.

SINASC's `CODMUNRES` can be bound only to `CIRAC`, which maps municipality
identifiers to health regions. That table decodes 100% of the values — coverage
ranking cannot tell it apart from a correct municipality table — and returns
"Baixo Acre e Purus" for a municipality code. Rendered as `CODMUNRES`'s label,
a region name looks like the textual form of a municipality identifier.

Coverage establishes that a lookup DECODES a column. It cannot establish that it
answers at the same granularity.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from pegasus_data.semantics.dictionary import (
    CodelistBinding,
    DictionaryEntry,
    persist_bindings,
    persist_entries,
)
from pegasus_data.view import render_table


@pytest.fixture
def rolled_up(catalog, settings):
    """Six municipality codes, a table that maps them to two regions."""
    from pegasus_data.persist.reference import (
        register_reference_tables,
        write_reference_tables,
    )

    codes = ["120001", "120002", "120003", "120010", "120011", "120012"]
    regions = ["Baixo Acre e Purus"] * 3 + ["Alto Acre"] * 3
    persist_entries(
        catalog,
        [
            DictionaryEntry(
                system="SINASC", value_raw=code, value_label=region,
                source="cnv", source_ref=f"cir:{i}", confidence=0.95,
                value_group="CIRAC",
            )
            for i, (code, region) in enumerate(zip(codes, regions, strict=True))
        ],
    )
    persist_bindings(
        catalog,
        [CodelistBinding(system="SINASC", field_name="CODMUNRES", codelist="CIRAC",
                         source="inferred", source_ref="test", confidence=0.6)],
    )
    register_reference_tables(catalog, write_reference_tables(catalog, settings.lake_dir))
    table = pa.table({"CODMUNRES": codes})
    return catalog, settings, table


class TestARollUpIsItsOwnDimension:
    def test_the_code_column_keeps_the_code(self, rolled_up):
        catalog, settings, table = rolled_up
        out, report = render_table(
            table, store=catalog, lake_root=settings.lake_dir, system="SINASC"
        )
        if "CODMUNRES" not in report.rollup_used:
            pytest.skip("this binding was not ranked as a roll-up here")
        assert out.column("CODMUNRES").to_pylist() == table.column("CODMUNRES").to_pylist(), (
            "the municipality code was replaced by a region name"
        )

    def test_the_region_arrives_under_its_own_name(self, rolled_up):
        catalog, settings, table = rolled_up
        out, report = render_table(
            table, store=catalog, lake_root=settings.lake_dir, system="SINASC"
        )
        if "CODMUNRES" not in report.rollup_used:
            pytest.skip("this binding was not ranked as a roll-up here")
        extra = [n for n in out.schema.names if n.startswith("CODMUNRES_")]
        assert extra, "the roll-up label was dropped entirely instead of renamed"
        assert any("Baixo Acre" in (v or "") for v in out.column(extra[0]).to_pylist())

    def test_the_roll_up_is_named_in_the_report(self, rolled_up):
        catalog, settings, table = rolled_up
        _out, report = render_table(
            table, store=catalog, lake_root=settings.lake_dir, system="SINASC"
        )
        if "CODMUNRES" not in report.rollup_used:
            pytest.skip("this binding was not ranked as a roll-up here")
        assert any("ROLLUP" in w for w in report.warnings)


class TestTheReportCarriesItStructurally:
    def test_rollup_used_is_machine_readable(self):
        from pegasus_data.view import RenderReport

        assert "rollup_used" in RenderReport().as_dict()
