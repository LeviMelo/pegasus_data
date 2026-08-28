"""Semantic axes: what a dataset's geography and time actually mean.

`semantic_axes` names which column carries the municipality and which carries
the date, and what each ROLE is — that `MUNIC_RES` is where the patient lives
and `MUNIC_MOV` is where they were treated. The columns themselves are
identifiable from their curated codelist binding; the role is not in the bytes
and has to be stated.

These tests exist because a mistake here is silent. A declared field that does
not exist produces an aggregate with no rows and no error, which is the same
shape of failure as the phantom codelists in FINDINGS §3k — curation claiming
something the data cannot honour.
"""

from __future__ import annotations

import pytest

yaml = pytest.importorskip("yaml")

from pathlib import Path

from pegasus_data.semantics.curation import dataset_semantics, parse_grain, semantics_for

ROOT = Path(__file__).resolve().parents[1]
VARIABLES = ROOT / "src" / "pegasus_data" / "curation" / "variables"


def _curated_fields() -> dict[str, set[str]]:
    """`system -> every column name curation knows about`."""
    out: dict[str, set[str]] = {}
    for path in sorted(VARIABLES.glob("*/*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        system = str(doc.get("system") or path.parent.name).upper()
        names = {str(n).upper() for n in (doc.get("variables") or {})}
        out.setdefault(system, set()).update(names)
        # curation folders are named for the crawled system; datasets may use
        # the institutional spelling, so index both.
        out.setdefault(path.parent.name.upper(), set()).update(names)
    return out


CURATED = _curated_fields()
DECLARED = dataset_semantics()


def _fields_of(axes: dict) -> list[tuple[str, str, str]]:
    out = []
    for kind in ("geography", "time"):
        for role, body in (axes.get(kind) or {}).items():
            for field in (body or {}).get("fields") or ():
                out.append((kind, str(role), str(field).upper()))
    return out


class TestEveryDeclaredFieldExists:
    """A typo here is an aggregate that silently returns nothing."""

    def test_there_are_axes_to_check(self) -> None:
        with_axes = [d for d in DECLARED.values() if d.axes]
        assert len(with_axes) >= 80, (
            f"only {len(with_axes)} datasets carry semantic axes; the family "
            "declarations should reach ~90"
        )

    @pytest.mark.parametrize(
        "dataset_id",
        sorted(d for d, s in DECLARED.items() if s.axes),
    )
    def test_declared_axis_fields_are_columns_curation_knows(self, dataset_id) -> None:
        semantics = DECLARED[dataset_id]
        system = str(semantics.system or "").upper()
        known = CURATED.get(system) or set()
        if not known:
            pytest.skip(f"no curated variables for system {system!r}")
        missing = [
            f"{kind}.{role} -> {field}"
            for kind, role, field in _fields_of(semantics.axes)
            if field not in known
        ]
        assert not missing, (
            f"{dataset_id} declares axis fields that do not exist in {system} "
            f"curation: {missing}. A declared column that is absent produces an "
            "aggregate with no rows and no error."
        )


class TestTheDefaultsPointSomewhere:
    @pytest.mark.parametrize(
        "dataset_id", sorted(d for d, s in DECLARED.items() if s.axes)
    )
    def test_declared_defaults_name_a_declared_role(self, dataset_id) -> None:
        semantics = DECLARED[dataset_id]
        geo, time = semantics.geography_bindings(), semantics.time_bindings()
        if geo:
            assert semantics.default_geography() in geo, dataset_id
        if time:
            assert semantics.default_time() in time, dataset_id

    @pytest.mark.parametrize(
        "dataset_id", sorted(d for d, s in DECLARED.items() if s.axes)
    )
    def test_every_role_names_at_least_one_field(self, dataset_id) -> None:
        for kind in ("geography", "time"):
            for role, body in (DECLARED[dataset_id].axes.get(kind) or {}).items():
                assert (body or {}).get("fields"), f"{dataset_id} {kind}.{role} names no field"


class TestInheritance:
    """Declared once per family, because the families really are uniform."""

    def test_one_declaration_covers_all_of_sinan(self) -> None:
        """58 agravos share the notification block; restating it 58 times is how
        one file drifts and answers differently from its siblings."""
        sinan = [s for s in DECLARED.values() if str(s.system).upper() == "SINAN" and s.axes]
        assert len(sinan) >= 55, f"only {len(sinan)} SINAN datasets inherited axes"
        assert {s.default_geography() for s in sinan} == {"residence"}
        assert {s.default_time() for s in sinan} == {"notification"}

    def test_a_dataset_may_override_its_family(self) -> None:
        """SIH.RD declares its own axes in core.yml and must keep them."""
        rd = semantics_for("SIH-RD")
        assert rd is not None
        assert "facility" in rd.geography_bindings()
        assert rd.default_time() == "competence"

    def test_grain_is_never_inherited(self) -> None:
        """CNES datasets share a geography column and have DIFFERENT grains.

        Inheriting grain would make `COUNT(*)` mean one thing across
        establishment-month, professional-establishment-month and
        establishment-bed type-month, which is the assumption the aggregate
        algebra exists to refuse.
        """
        cnes = {d: s for d, s in DECLARED.items() if str(s.system).upper() == "CNES"}
        grains = {s.grain.counts() for s in cnes.values() if s.grain.analysable}
        assert len(grains) > 1, f"CNES grains collapsed to {grains}"
        assert "establishment-month" in grains

    def test_families_do_not_all_share_one_time_role(self) -> None:
        """SINAN notifies, SIM records a death, CNES has a competence.

        A single inherited vocabulary across systems would be the fragility this
        design is meant to avoid.
        """
        roles = {frozenset(s.time_bindings()) for s in DECLARED.values() if s.axes}
        assert len(roles) > 3, roles


class TestGrainStaysDerived:
    def test_the_prose_still_parses_for_almost_every_dataset(self) -> None:
        analysable = [s for s in DECLARED.values() if s.grain.analysable]
        assert len(analysable) >= 120, f"only {len(analysable)} of {len(DECLARED)}"

    def test_period_bearing_grains_are_detected(self) -> None:
        period = [s for s in DECLARED.values() if s.grain.is_period_bearing]
        assert len(period) >= 15, f"only {len(period)} period-bearing grains found"

    def test_no_grain_was_hand_written_that_the_prose_already_states(self) -> None:
        """An explicit `grain:` is for prose that does not parse. Restating what
        derivation already gets right is the duplication REQUEST.md forbids."""
        redundant = [
            d for d, s in DECLARED.items()
            if s.grain.declared and parse_grain(s.grain.prose).components == s.grain.components
        ]
        assert not redundant, f"these declare a grain derivation already gets: {redundant}"
