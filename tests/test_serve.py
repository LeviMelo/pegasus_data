"""The HTTP surface: what it serves, what it refuses, and what it never sends.

The transport must not become a second place where analysis happens. These
tests are mostly about that boundary holding: state crosses the wire, not
finished values; codes cross with a codelist, not a label per row; a refusal
from the algebra arrives as a refusal rather than as an empty result.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from pegasus_data.serve import create_app  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore")

NAME = "sih_rd_municipality_month"
ARTIFACT = f"/api/v1/artifacts/{NAME}"


@pytest.fixture
def client(tmp_path, aggregate_lake):
    return TestClient(create_app(root=tmp_path))


class TestShape:
    def test_health_counts_what_is_built(self, client) -> None:
        body = client.get("/api/v1/health").json()
        assert body["artifacts"] >= 1
        assert body["built"] >= 1
        assert body["records_enabled"] is False

    def test_datasets_lists_unbuilt_specs_too(self, client) -> None:
        """Hiding them would leave an operator wondering why one never appears."""
        body = client.get("/api/v1/datasets").json()
        assert {e["id"] for e in body} >= {NAME}
        assert any(e["built"] is False for e in body)

    def test_geography_column_is_named_geo_at_every_grain(self, client) -> None:
        """A client with a branch per grain is a client the descriptor failed."""
        for grain in ("municipality", "uf", "health_region"):
            body = client.get(ARTIFACT, params={"by": f"{grain},year"}).json()
            assert "geo" in body["data"], grain
            assert body["keys"]["geo"] == grain
            assert grain not in body["data"]

    def test_municipalities_cross_the_wire_as_seven_digits(self, client) -> None:
        """The mesh keys on seven and the seventh is a check digit.

        A client cannot compute it, so if the server does not normalise, the
        join silently matches nothing.
        """
        body = client.get(ARTIFACT, params={"by": "municipality"}).json()
        assert body["columns"]["geo"]["type"] == "code7"
        assert all(len(code) == 7 for code in body["data"]["geo"])
        labels = {row["code"]: row["label"] for row in body["codelists"]["geo"]}
        assert labels["1200401"] == "Rio Branco, AC"

    def test_state_travels_and_finished_values_do_not(self, client) -> None:
        """Invariant 3. A mean on the wire is a mean the client can only re-average."""
        body = client.get(ARTIFACT, params={"by": "uf", "measures": "los"}).json()
        assert set(body["data"]) >= {"los_n", "los_sum"}
        assert "los" not in body["data"]

    def test_labels_travel_once_in_a_codelist(self, client) -> None:
        """Repeating a label per row is most of the payload and lets rows disagree."""
        body = client.get(ARTIFACT, params={"by": "municipality,SEXO"}).json()
        assert [row["code"] for row in body["codelists"]["SEXO"]] == ["1", "3"]
        assert set(body["data"]["SEXO"]) <= {"1", "3"}

    def test_an_unlabelled_level_shows_its_own_code(self, client) -> None:
        """Never invent a label.

        Dimension labels come from the catalog's field bindings. A deployment
        with an artifact but no catalog is a real configuration -- and there the
        honest answer is the code itself, not a prettified guess that reads like
        a translation nobody made. `test_capabilities` covers the labelled path.
        """
        body = client.get(ARTIFACT, params={"by": "SEXO"}).json()
        for row in body["codelists"]["SEXO"]:
            assert row["label"] == row["code"]

    def test_months_are_iso_periods(self, client) -> None:
        body = client.get(ARTIFACT, params={"by": "municipality,month"}).json()
        assert all("-" in period for period in body["data"]["time"])
        assert body["data"]["time"][0].count("-") == 1


class TestFilteringIsNotMarginalising:
    def test_a_dim_filter_restricts_without_becoming_an_axis(self, client) -> None:
        filtered = client.get(ARTIFACT, params={"by": "uf", "dim.SEXO": "1"}).json()
        assert "SEXO" not in filtered["data"]
        assert filtered["keys"]["dimensions"] == []

        everyone = client.get(ARTIFACT, params={"by": "uf"}).json()
        assert sum(filtered["data"]["admissions_n"]) < sum(everyone["data"]["admissions_n"])

    def test_total_equals_the_sum_of_its_parts(self, client) -> None:
        """The one invariant the single base cuboid exists to guarantee."""
        total = client.get(ARTIFACT, params={"by": "brazil", "measures": "admissions"}).json()
        parts = client.get(
            ARTIFACT, params={"by": "brazil,SEXO", "measures": "admissions"}).json()
        assert sum(parts["data"]["admissions_n"]) == pytest.approx(
            total["data"]["admissions_n"][0])


class TestRefusals:
    def test_an_unknown_level_is_422_and_says_what_exists(self, client) -> None:
        response = client.get(ARTIFACT, params={"by": "nonsense"})
        assert response.status_code == 422
        assert "nonsense" in response.json()["error"]
        assert "municipality" in response.json()["error"]

    def test_an_unknown_artifact_is_404(self, client) -> None:
        assert client.get("/api/v1/artifacts/no_such_thing").status_code == 404

    def test_an_unbuilt_artifact_has_no_capabilities(self, client) -> None:
        response = client.get("/api/v1/datasets/cnes_st_municipality_month/capabilities")
        assert response.status_code == 404

    def test_a_missing_mesh_names_how_to_build_it(self, client) -> None:
        response = client.get("/api/v1/geo/mesh/municipality")
        assert response.status_code == 404
        assert "build" in response.json()["error"]


class TestMicrodataIsOffUntilSomebodySaysOtherwise:
    """Exposing identifiable rows over a network is the operator's decision.

    Nothing here masks, hashes or drops a personal identifier -- that rule is
    unchanged. What changes is that the endpoint does not exist unless asked for.
    """

    def test_records_is_forbidden_by_default(self, client) -> None:
        response = client.get(
            "/api/v1/records", params={"dataset": "SIH-RD", "period": "2022-01"})
        assert response.status_code == 403
        assert "--allow-records" in response.json()["error"]

    def test_the_flag_is_reported_in_health(self, tmp_path, aggregate_lake) -> None:
        opened = TestClient(create_app(root=tmp_path, allow_records=True))
        assert opened.get("/api/v1/health").json()["records_enabled"] is True


class TestGeography:
    def test_membership_is_keyed_on_the_join_key(self, client) -> None:
        body = client.get("/api/v1/geo/membership", params={"uf": "AC"}).json()
        assert body["count"] == 22
        assert all(len(code) == 7 for code in body["membership"])
        entry = body["membership"]["1200401"]
        assert entry["name"] == "Rio Branco"
        assert entry["uf"] == "AC"
        assert entry["code6"] == "120040"

    def test_identity_and_containment_do_not_collide(self, client) -> None:
        """Both call something `uf` and they are different things.

        Identity's `uf` is the sigla the UF mesh joins on; the `uf`
        classification's member label is `AC Acre`. Flattened into one object,
        the classification overwrote the sigla and every UF join broke.
        """
        entry = client.get(
            "/api/v1/geo/membership", params={"uf": "AC"}).json()["membership"]["1200401"]
        assert entry["uf"] == "AC"
        assert entry["memberships"]["uf"] == "AC Acre"
        assert "health_region" in entry["memberships"]

    def test_hierarchies_say_which_authority_answered(self, client) -> None:
        body = client.get("/api/v1/geo/hierarchies").json()["classifications"]
        assert body["health_region"]["authority"] == "datasus"
        assert body["ibge_mesoregion"]["authority"] == "ibge"
        # `capital` is an attribute, not a containment: a roll-up to it is not a
        # partition of Brazil.
        assert body["capital"]["attribute"] is True
