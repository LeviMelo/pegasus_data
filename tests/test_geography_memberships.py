"""A municipality's supramunicipal memberships, compiled from the label pack.

The health region that once appeared as a municipality's NAME is now reachable
under its own name, which is the whole point: `CODMUNRES` labels Rio Branco
"Rio Branco, AC" and `memberships("120040").get("health_region")` answers
"AC Baixo Acre e Purus". Both are correct; conflating them was the defect
(FINDINGS §3k).

These tests read the shipped pack and the shipped curation. They do not fetch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pegasus_data.geography import (
    build_geography_pack,
    classifications,
    excluded,
    members,
    memberships,
)

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "src" / "pegasus_data" / "resources" / "labels.parquet"
PACK = ROOT / "src" / "pegasus_data" / "resources" / "geography.parquet"


def test_the_pack_ships() -> None:
    assert PACK.exists(), "geography.parquet is not in resources; run build_geography_pack"


def test_rio_branco_reaches_its_health_region() -> None:
    """`120040` is the code that produced the defect this module answers."""
    got = memberships("120040")
    region = got.get("health_region")
    assert region is not None, "no health region for Rio Branco"
    assert "Baixo Acre" in region.member_label
    assert region.member_code, "a member needs a code, not only a name"


def test_seven_digit_and_six_digit_codes_resolve_to_the_same_municipality() -> None:
    """DATASUS writes six digits, IBGE writes seven. §7.1."""
    six = memberships("355030")
    seven = memberships("3550308")
    assert len(six) > 0
    assert six.as_dict() == seven.as_dict()


@pytest.mark.parametrize(
    "code,classification,expected",
    [
        ("355030", "health_region", "São Paulo"),
        ("355030", "metropolitan_region", "São Paulo"),
        ("120040", "ibge_mesoregion", "Vale do Acre"),
        ("330455", "capital", "Rio de Janeiro"),
    ],
)
def test_known_memberships(code: str, classification: str, expected: str) -> None:
    item = memberships(code).get(classification)
    assert item is not None, f"{code} has no {classification}"
    assert expected.lower() in item.member_label.lower()


def test_a_municipality_in_no_metropolitan_region_simply_has_none() -> None:
    """Partial coverage is absence, not unknown — and must not raise."""
    got = memberships("120001")          # Acrelândia, AC
    assert got.get("metropolitan_region") is None
    assert got.get("health_region") is not None


def test_an_unknown_municipality_returns_an_empty_set_rather_than_guessing() -> None:
    """`123456` is not a municipality code, and inventing a region for it would
    be worse than answering nothing."""
    got = memberships("123456")
    assert len(got) == 0
    assert got.municipality == "123456"


@pytest.mark.parametrize(
    "code,expected",
    [
        ("999999", "Ignorado/Exterior"),   # the national unknown/foreign sentinel
        ("120000", "ignorado"),            # the per-UF "município ignorado" sentinel
    ],
)
def test_sentinels_are_kept_as_members_not_folded_or_dropped(code, expected) -> None:
    """A sentinel is a member and must survive the compile.

    Folding `120000` into a real Acre municipality is the "Baixo Acre e Purus"
    class of error. Dropping it silently biases every count that uses this
    geography, because the rows carrying it do not disappear from the data.
    """
    got = memberships(code)
    assert len(got) > 0, f"{code} was dropped from the compiled pack"
    assert any(expected.lower() in m.member_label.lower() for m in got.memberships), got.as_dict()


def test_members_lists_a_classification_for_a_frontend_control() -> None:
    """The list a UI needs to offer 'group by health region'."""
    regions = members("health_region")
    assert len(regions) > 400, f"only {len(regions)} health regions"
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in regions.items())


class TestTheCurationIsHonestAboutWhatItExcludes:
    """Excluding a classification is a claim about evidence and is checkable."""

    def test_every_declared_classification_names_a_codelist_and_its_evidence(self) -> None:
        declared = classifications()
        assert declared, "curation/geography.yml declares nothing"
        for name, body in declared.items():
            assert body.get("codelist"), f"{name} names no codelist"
            assert body.get("what"), f"{name} says nothing about what it is"
            assert body.get("verified"), f"{name} carries no measurement"

    def test_health_macroregion_is_absent_and_says_why(self) -> None:
        """The honest gap.

        A municipality does belong to a health macroregion. DATASUS publishes no
        table saying which one without contradicting itself — `BR_MACSAUD`
        conflicts on 66% of municipalities and `MSAUDBR` on 4% — so nothing is
        shipped, and the reason is recorded rather than the conflict being
        resolved by picking a system.
        """
        assert "health_macroregion" not in classifications()
        gaps = excluded()
        macro = [k for k, v in gaps.items() if v.get("wanted_as") == "health_macroregion"]
        assert len(macro) >= 2, "both macroregion candidates should be recorded as excluded"
        for key in macro:
            assert gaps[key].get("reason"), f"{key} is excluded with no reason"

    def test_the_two_scheme_codelist_is_excluded(self) -> None:
        """`RSAUDBR` carries DIRES and named regions under one name."""
        gaps = excluded()
        assert "RSAUDBR" in gaps
        assert "DIRES" in gaps["RSAUDBR"]["reason"]


class TestTheCompileIsDeterministic:
    """Scoping is what makes it so; without it the pack would be arbitrary."""

    def test_rebuilding_produces_the_same_pack(self, tmp_path) -> None:
        a = build_geography_pack(tmp_path / "a.parquet", labels_path=LABELS)
        b = build_geography_pack(tmp_path / "b.parquet", labels_path=LABELS)
        assert a["rows"] == b["rows"]
        assert (tmp_path / "a.parquet").read_bytes() == (tmp_path / "b.parquet").read_bytes()

    def test_contested_municipalities_are_counted_not_hidden(self, tmp_path) -> None:
        """46 municipalities really are assigned different health regions.

        The number is small and it is not zero. Reporting it as zero would mean
        the compile had silently picked one system's answer.
        """
        report = build_geography_pack(tmp_path / "g.parquet", labels_path=LABELS)
        health = report["classifications"]["health_region"]
        assert health["municipalities"] > 5_000
        assert 0 < health["contested"] < 100, health

    def test_the_report_counts_municipalities_not_validity_windows(self, tmp_path) -> None:
        """Brazil has ~5,570 municipalities.

        A municipality published under five validity windows is one
        municipality. Counting the windows gave 28,018 for the mesoregion
        classification, which reads as five times more of Brazil than exists.
        """
        report = build_geography_pack(tmp_path / "g.parquet", labels_path=LABELS)
        for name, stat in report["classifications"].items():
            assert stat["municipalities"] <= 6_000, (
                f"{name} reports {stat['municipalities']:,} municipalities; Brazil "
                "has about 5,570, so this is counting (municipality, window) keys"
            )


class TestContestedMembershipsAreFlaggedNotGuessed:
    """When systems disagree, the answer must not be chosen alphabetically.

    Picking `sorted(systems)[0]` is exactly the tie-break that once labelled Rio
    Branco with the name of its health region (FINDINGS §3k). Here it is kept
    only so a caller gets a usable value, and the flag is what says not to trust
    it — a warning nobody can act on is what that defect was made of.
    """

    def test_an_agreed_membership_is_not_flagged(self) -> None:
        item = memberships("355030").get("health_region")
        assert item is not None and item.contested is False

    def test_a_contested_membership_is_flagged_and_named(self) -> None:
        """`420140` is SC Extremo Sul Catarinense to SIM and SC Extremo Sul to
        SINASC — one of 46 municipalities where the published names differ."""
        got = memberships("420140")
        item = got.get("health_region")
        assert item is not None, "a contested membership must still be reachable"
        assert item.contested is True
        assert "health_region" in got.conflicts

    def test_naming_the_system_resolves_it_and_clears_the_flag(self) -> None:
        for system, expected in (("SIM", "Catarinense"), ("SINASC", "Extremo Sul")):
            item = memberships("420140", system=system).get("health_region")
            assert item is not None
            assert item.contested is False, f"{system} is an answer, not a guess"
            assert expected.lower() in item.member_label.lower()

    def test_accent_and_width_variants_are_agreement_not_conflict(self) -> None:
        """`Xanxerê`/`Xanxere` and `42003`/`4203` are the same region.

        Counting them as disagreement would have reported 295 conflicts where
        there are 46, and would have made the honest number useless.
        """
        got = memberships("420010")
        item = got.get("health_region")
        assert item is not None
        assert item.contested is False
        assert got.conflicts == ()


class TestADeclaredRollupMustBeNational:
    """A per-UF table declared as a national roll-up resolves almost nothing.

    `joins.yml` declared `MUNIC_RES -> health_region` with `artifact: CIRAC` —
    Acre's 24-row slice — so `query(dimensions=["MUNIC_RES.health_region"])`
    returned nothing for São Paulo, Rio, Fortaleza or Belo Horizonte, and said
    so nowhere. It is the FINDINGS §3k defect in relation form: the per-UF form
    of a classification that also exists nationally.
    """

    @staticmethod
    def _rollups():
        from pegasus_data.semantics.relations import RelationType, load_relations

        return [
            r for r in load_relations()
            if r.relation_type in (RelationType.ROLLUP_TO, RelationType.ATTRIBUTE_OF)
        ]

    def test_there_are_rollups_to_check(self) -> None:
        assert self._rollups(), "no roll-up relations declared; this test is vacuous"

    def test_every_declared_rollup_artifact_spans_many_states(self) -> None:
        from pegasus_data.labelpack import read_packed

        narrow = []
        for relation in self._rollups():
            if relation.artifact.endswith(".parquet"):
                continue
            system = None if relation.system == "*" else relation.system
            packed = read_packed(relation.artifact, system=system)
            if packed is None or not packed.num_rows:
                narrow.append(f"{relation.field_name}->{relation.target_name}: "
                              f"{relation.artifact} is empty")
                continue
            codes = [str(c) for c in packed.column("code").to_pylist()]
            municipal = [c for c in codes if len(c) == 6 and c.isdigit()]
            if not municipal:
                continue          # not a municipality-keyed roll-up
            states = {c[:2] for c in municipal}
            if len(states) < 20:
                narrow.append(
                    f"{relation.field_name}->{relation.target_name}: "
                    f"{relation.artifact} covers {len(states)} states"
                )
        assert not narrow, (
            "these declared roll-ups use a table that does not cover Brazil, so "
            f"they resolve only inside the states it happens to include: {narrow}"
        )

    def test_the_health_region_rollup_reaches_every_capital(self) -> None:
        from pegasus_data.labelpack import read_packed
        from pegasus_data.semantics.relations import RelationType, relations_for

        declared = [
            r for r in relations_for("SIHSUS", "SIH.RD", "MUNIC_RES",
                                     relation_type=RelationType.ROLLUP_TO)
            if r.target_name == "health_region"
        ]
        assert declared, "SIH.RD MUNIC_RES declares no health_region roll-up"
        packed = read_packed(declared[0].artifact, system="SIHSUS")
        lookup = dict(zip(packed.column("code").to_pylist(),
                          packed.column("label").to_pylist(), strict=True))
        for capital in ("355030", "330455", "230440", "310620", "120040"):
            assert lookup.get(capital), (
                f"{capital} has no health region under "
                f"{declared[0].artifact!r}; a national roll-up that misses a "
                "state capital is a per-UF table wearing a national name"
            )
