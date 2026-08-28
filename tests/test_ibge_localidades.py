"""IBGE as the authority for territorial identity.

`docs/IBGE_LOCALIDADES.md` is the audit. These tests hold the two decisions it
reached: that IBGE supplies the classifications it defines, and that DATASUS
keeps the health-service geography it invented — because IBGE has none.

Only the parsing and the compiled result are tested. The live endpoint is not
called: a test suite that needs `servicodados.ibge.gov.br` fails when a network
is absent, and what matters here is what got compiled, not that IBGE is up.
"""

from __future__ import annotations

import pytest

from pegasus_data.geography import classifications, excluded, members, memberships
from pegasus_data.sources.ibge_localidades import (
    BASE_URL,
    IBGE_CLASSIFICATIONS,
    Municipality,
    _parse,
)

#: One real record, shape-for-shape as the endpoint returns it.
RECORD = {
    "id": 1100015,
    "nome": "Alta Floresta D'Oeste",
    "microrregiao": {
        "id": 11006, "nome": "Cacoal",
        "mesorregiao": {
            "id": 1102, "nome": "Leste Rondoniense",
            "UF": {"id": 11, "sigla": "RO", "nome": "Rondônia",
                   "regiao": {"id": 1, "sigla": "N", "nome": "Norte"}},
        },
    },
    "regiao-imediata": {
        "id": 110005, "nome": "Cacoal",
        "regiao-intermediaria": {
            "id": 1102, "nome": "Ji-Paraná",
            "UF": {"id": 11, "sigla": "RO", "nome": "Rondônia",
                   "regiao": {"id": 1, "sigla": "N", "nome": "Norte"}},
        },
    },
}


class TestParsingTheEndpoint:
    def test_it_uses_the_current_api_version(self) -> None:
        """`v1` is the only version for localidades; v2 and v3 return 503.

        The v3 that exists on `servicodados` is `/v3/agregados`, the statistical
        tables service, which answers a different question entirely.
        """
        assert BASE_URL == "https://servicodados.ibge.gov.br/api/v1/localidades"

    def test_both_code_forms_are_carried(self) -> None:
        """IBGE writes seven digits, DATASUS six. A join by equality between
        them matches nothing — §7.1, and the commonest way an analysis loses its
        denominator."""
        m = _parse(RECORD)
        assert m is not None
        assert m.code7 == "1100015"
        assert m.code6 == "110001"

    def test_one_record_carries_the_whole_hierarchy(self) -> None:
        """Which is why the client makes one request and joins nothing."""
        m = _parse(RECORD)
        got = dict((c, label) for c, _code, label in m.memberships())
        assert got["uf"] == "RO Rondônia"
        assert got["ibge_macroregion"] == "Norte"
        assert got["ibge_mesoregion"] == "Leste Rondoniense"
        assert got["ibge_microregion"] == "Cacoal"
        assert got["ibge_intermediate_region"] == "Ji-Paraná"
        assert got["ibge_immediate_region"] == "Cacoal"

    def test_both_hierarchies_are_present_at_once(self) -> None:
        """The legacy chain and the 2017 replacement, in the same record."""
        m = _parse(RECORD)
        assert m.mesoregion_id and m.microregion_id          # retired 2017
        assert m.immediate_id and m.intermediate_id          # current

    def test_a_malformed_record_is_skipped_rather_than_guessed(self) -> None:
        assert _parse({"id": 999, "nome": "not a municipality"}) is None
        assert _parse({}) is None

    def test_a_municipality_missing_a_branch_still_parses(self) -> None:
        """IBGE has occasionally omitted one hierarchy; losing the other too
        would be worse than carrying what is there."""
        thin = {"id": 5300108, "nome": "Brasília",
                "regiao-imediata": {"id": 530001, "nome": "Brasília",
                    "regiao-intermediaria": {"id": 5301, "nome": "Brasília",
                        "UF": {"id": 53, "sigla": "DF", "nome": "Distrito Federal",
                               "regiao": {"id": 5, "nome": "Centro-Oeste"}}}}}
        m = _parse(thin)
        assert m is not None and m.uf_sigla == "DF"
        assert m.mesoregion_id is None
        assert dict((c, l) for c, _k, l in m.memberships())["ibge_immediate_region"] == "Brasília"


class TestWhatEachAuthorityOwns:
    """The decision the audit reached, held in place."""

    def test_ibge_supplies_territorial_identity(self) -> None:
        ibge = classifications(authority="ibge")
        for name in ("uf", "ibge_macroregion", "ibge_mesoregion",
                     "ibge_microregion", "ibge_immediate_region",
                     "ibge_intermediate_region"):
            assert name in ibge, name

    def test_datasus_keeps_the_health_service_geography(self) -> None:
        """IBGE publishes no health regions, which is why this is a supplement
        and not a replacement."""
        datasus = classifications(authority="datasus")
        assert "health_region" in datasus
        assert "health_region" not in classifications(authority="ibge")

    def test_no_classification_is_claimed_by_both(self) -> None:
        assert not (set(classifications(authority="datasus"))
                    & set(classifications(authority="ibge")))

    def test_the_superseded_datasus_tables_are_recorded_with_their_measurement(self) -> None:
        """`MESOBR`/`MICROBR` are superseded, NOT wrong — the partitions match.

        Recording the distinction matters: someone re-reading this later should
        not conclude DATASUS got the geography wrong, because it did not.
        """
        gaps = excluded()
        for codelist in ("MESOBR", "MICROBR"):
            assert codelist in gaps, codelist
            assert "Superseded" in gaps[codelist]["reason"]
            assert gaps[codelist]["measured"]["groups_split_by_ibge"] == 0


class TestTheCompiledResult:
    def test_the_current_hierarchy_datasus_never_published_is_now_reachable(self) -> None:
        """IBGE retired meso/micro in 2017; DATASUS ships only those."""
        assert len(members("ibge_intermediate_region")) > 100
        assert len(members("ibge_immediate_region")) > 400

    def test_every_ibge_membership_says_who_says_so(self) -> None:
        got = memberships("355030")
        by_authority = {m.classification: m.authority for m in got.memberships}
        assert by_authority["ibge_microregion"] == "ibge"
        assert by_authority["health_region"] == "datasus"

    def test_ibge_resolves_a_municipality_datasus_files_as_ignorado(self) -> None:
        """`431936` is `4300 Ignorado RS` in MESOBR and Noroeste Rio-grandense
        at IBGE. One of the three that made IBGE the better source."""
        item = memberships("431936").get("ibge_mesoregion")
        assert item is not None
        assert "Noroeste" in item.member_label
        assert "ignorado" not in item.member_label.lower()

    def test_ibge_memberships_are_system_neutral(self) -> None:
        """IBGE publishes one division for the country, so there is no
        per-system disagreement to scope away — which is the argument for
        sourcing identity there rather than from thirty `.CNV` variants."""
        for item in memberships("355030").memberships:
            if item.authority == "ibge":
                assert item.system == "", item

    @pytest.mark.parametrize("name,body", sorted(IBGE_CLASSIFICATIONS.items()))
    def test_each_declared_ibge_classification_says_what_and_whether_current(
        self, name, body
    ) -> None:
        assert body["what"]
        assert body["status"] in ("current", "legacy")
