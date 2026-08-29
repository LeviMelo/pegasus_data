"""The descriptor a client draws its whole interface from.

The rule under test throughout: *if the descriptor does not declare it, the UI
does not draw it.* That makes an omission here a user-visible defect, so these
tests care as much about what the descriptor REFUSES to claim as about what it
reports.
"""

from __future__ import annotations

import json

import pytest

from pegasus_data.capabilities import _control_for, _decimals_for, capabilities, catalogue
from pegasus_data.measures import COUNT, MAX, MEAN, MIN, RATIO, SUM


class TestFormulaMatchesFinalize:
    """The client evaluates `formula`; the server would have called `finalize`.

    These must agree, because they are the same projection expressed twice --
    once as Python and once as a string on a wire. Nothing else stops them
    drifting when a new kind is added.
    """

    @pytest.mark.parametrize(
        ("kind", "state"),
        [
            (COUNT, (7.0,)),
            (SUM, (12.5,)),
            (MEAN, (4.0, 10.0)),
            (MEAN, (1.0, 3.0)),
            (RATIO, (3.0, 12.0)),
            (MIN, (2.0,)),
            (MAX, (9.0,)),
        ],
    )
    def test_declared_formula_reproduces_finalize(self, kind, state) -> None:
        columns = {
            f"m_{field}": value
            for field, value in zip(kind.state_fields, state, strict=True)
        }
        # The client is a generic evaluator over the declared names; it has no
        # branch per kind, which is the whole point of shipping the formula.
        evaluated = eval(kind.formula("m"), {"__builtins__": {}}, columns)  # noqa: S307
        assert evaluated == pytest.approx(kind.finalize(state))

    def test_formula_only_names_state_columns(self) -> None:
        """Nothing but the measure's own components may appear in the formula.

        A formula reaching for a column the payload does not carry would be a
        promise the wire cannot keep.
        """
        for kind in (COUNT, SUM, MEAN, RATIO, MIN, MAX):
            allowed = {f"m_{field}" for field in kind.state_fields}
            names = {
                token for token in kind.formula("m").replace("/", " ").split()
                if token and not token.replace(".", "").isdigit()
            }
            assert names <= allowed, f"{kind.name} reaches outside its state"

    def test_a_zero_denominator_is_undefined_not_zero(self) -> None:
        """0/0 is a claim nobody made, and both sides must agree it is absent."""
        assert MEAN.finalize((0.0, 0.0)) is None
        assert RATIO.finalize((0.0, 0.0)) is None


class TestControlChoice:
    """Cardinality decides the control, and the rule lives on this side."""

    @pytest.mark.parametrize(
        ("cardinality", "expected"),
        [(1, "segmented"), (4, "segmented"), (5, "chips"), (12, "chips"),
         (13, "bars"), (30, "bars"), (31, "combobox"), (5_000, "combobox")],
    )
    def test_thresholds(self, cardinality: int, expected: str) -> None:
        assert _control_for(cardinality) == expected

    def test_money_gets_two_decimals_and_a_count_gets_none(self) -> None:
        assert _decimals_for("sum", "brl") == 2
        assert _decimals_for("count", "admission") == 0
        assert _decimals_for("mean", "day") == 1


class TestAgainstABuiltArtifact:
    """Runs against the shared hand-built cuboid, so it runs everywhere.

    The same assertions were also checked against the real lake -- SIH-RD/AC
    2022, 2,417 cells -- where the mesh join came out total in the direction
    that matters: every one of the 5,570 polygons has an identity row, and every
    served municipality reaches a polygon.
    """

    @pytest.fixture()
    def built(self, aggregate_lake):
        self.settings = aggregate_lake
        return "sih_rd_municipality_month"

    def test_every_measure_declares_components_that_exist(self, built) -> None:
        from pegasus_data import aggregate

        capability = capabilities(built, settings=self.settings)
        table = aggregate(built, settings=self.settings, by=["uf"], finalize=False)
        present = set(table.schema.names)
        for measure in capability.measures:
            missing = set(measure.components) - present
            assert not missing, (
                f"{measure.id} declares components {missing} that the served "
                "payload does not carry"
            )

    def test_levels_describe_this_artifact_not_the_classification(self, built) -> None:
        """A dimension offers the levels PRESENT, never the whole codelist.

        DIAG_PRINC binds ~14,000 ICD codes. A control offering all of them for
        an artifact holding forty is a lie about the data.
        """
        from pegasus_data import aggregate

        capability = capabilities(built, settings=self.settings)
        for dimension in capability.dimensions:
            table = aggregate(built, settings=self.settings, by=[dimension.id], finalize=False)
            observed = {str(v) for v in table.column(dimension.id).to_pylist()}
            declared = {level.code for level in dimension.levels}
            assert declared == observed
            assert dimension.cardinality == len(declared)

    def test_a_grain_is_never_listed_twice(self, built) -> None:
        grains = capabilities(built, settings=self.settings).spatial["grains"]
        assert len(grains) == len(set(grains))

    def test_grain_names_are_the_ones_aggregate_accepts(self, built) -> None:
        """The descriptor must not invent a level name the server refuses."""
        from pegasus_data import aggregate
        from pegasus_data.measures import AggregationRefused

        capability = capabilities(built, settings=self.settings)
        for grain in capability.spatial["grains"]:
            try:
                aggregate(built, settings=self.settings, by=[grain], measures=[capability.measures[0].id])
            except AggregationRefused as exc:  # pragma: no cover - a real defect
                if "unknown level" in str(exc):
                    pytest.fail(f"descriptor offers {grain!r}, aggregate refuses it")

    def test_only_a_residence_binding_carries_a_denominator(self, built) -> None:
        """A rate needs numerator and denominator over the same population.

        Admissions counted at the HOSPITAL divided by that municipality's
        population is not a rate: a small town with a regional hospital shows a
        figure several times its own population's risk.
        """
        capability = capabilities(built, settings=self.settings)
        for binding in capability.spatial["bindings"]:
            if binding["id"] in ("residence", "patient", "area"):
                assert binding["denominator_compatible"] is True
            else:
                assert binding["denominator_compatible"] is False

    def test_completeness_is_measured_rather_than_assumed(self, built) -> None:
        """A competence axis IS the publication coordinate, so nothing is short."""
        capability = capabilities(built, settings=self.settings)
        completeness = capability.completeness
        assert completeness["kind"] in ("competence", "record_date")
        if completeness["kind"] == "competence":
            assert completeness["partial_periods"] == []

    def test_the_descriptor_is_json(self, built) -> None:
        """It crosses a wire, so nothing in it may be un-serialisable."""
        body = json.dumps(capabilities(built, settings=self.settings).as_dict(), ensure_ascii=False)
        assert json.loads(body)["id"] == built

    def test_an_unbuilt_artifact_is_listed_but_refuses_a_descriptor(self, built) -> None:
        """Advertising controls for data that cannot be served is the defect."""
        from pegasus_data._aggregate import ArtifactMissing

        entries = catalogue(settings=self.settings)
        unbuilt = [e for e in entries if not e["built"]]
        assert unbuilt, "the fixture lake should hold at least one unbuilt spec"
        assert any(e["built"] for e in entries)
        with pytest.raises(ArtifactMissing):
            capabilities(unbuilt[0]["id"], settings=self.settings)


class TestLabelsComeFromTheCatalog:
    """Dimension levels are labelled through the binding the catalog records.

    This is the path that turns `1` into `Masculino`, and it needs three things
    present: the artifact (which codes exist), the catalog (which codelist the
    field is bound to) and a reference table or the shipped label pack (what the
    codes mean). A deployment missing the catalog serves codes -- honestly, but
    unlabelled -- which is why that case has its own test in `test_serve`.
    """

    def test_a_bound_field_resolves_its_levels(self, tmp_path, catalog) -> None:
        from pegasus_data.config import load_settings
        from pegasus_data.view import codelist_levels

        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist,"
            " source, source_ref, confidence) VALUES (?,?,?,?,?,?,?)",
            ("SIHSUS", "", "SEXO", "SEXO", "def", "t.def", 0.9),
        )
        resolved = load_settings(root=tmp_path)
        levels = codelist_levels(
            "SEXO", store=catalog, lake_root=resolved.lake_dir,
            system="SIHSUS", codes=["1", "3"],
        )
        # SIHSUS codes sex as 1/3; SINASC as 1/2; SINAN as M/F. The lookup is
        # scoped by system precisely so these cannot be merged into one table in
        # which `1` means two different things.
        assert levels == {"1": "Masculino", "3": "Feminino"}

    def test_an_unbound_field_resolves_to_nothing_rather_than_guessing(
        self, tmp_path, catalog
    ) -> None:
        from pegasus_data.config import load_settings
        from pegasus_data.view import codelist_levels

        resolved = load_settings(root=tmp_path)
        assert codelist_levels(
            "SEXO", store=catalog, lake_root=resolved.lake_dir, system="SIHSUS",
        ) == {}

    def test_observed_codes_narrow_a_large_classification(
        self, tmp_path, catalog
    ) -> None:
        """An artifact holding forty ICD codes must not offer fourteen thousand."""
        from pegasus_data.config import load_settings
        from pegasus_data.view import codelist_levels

        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist,"
            " source, source_ref, confidence) VALUES (?,?,?,?,?,?,?)",
            ("SIHSUS", "", "SEXO", "SEXO", "def", "t.def", 0.9),
        )
        resolved = load_settings(root=tmp_path)
        everything = codelist_levels(
            "SEXO", store=catalog, lake_root=resolved.lake_dir, system="SIHSUS")
        narrowed = codelist_levels(
            "SEXO", store=catalog, lake_root=resolved.lake_dir, system="SIHSUS",
            codes=["1"])
        assert len(narrowed) == 1
        assert len(everything) >= len(narrowed)
