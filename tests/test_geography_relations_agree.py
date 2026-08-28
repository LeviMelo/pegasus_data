"""One authority for "which codelist carries this classification".

`curation/geography.yml` says `health_region -> CIRBRN`. `curation/joins.yml`
says it again, as `artifact:` on a `rollup_to` relation. The same fact declared
twice is how `CIRAC` — Acre's 24-row slice — sat in `joins.yml` as the NATIONAL
health-region roll-up while the compiled geography used the national table, and
nothing noticed (FINDINGS §3n).

Removing the duplication outright would mean restructuring `joins.yml`, whose
relations are per (system, dataset, field) while classifications are global.
These tests make the duplication *safe* instead: the two must agree, and drift
is a failure rather than a silent divergence.
"""

from __future__ import annotations

import pytest

from pegasus_data.geography import classifications, excluded
from pegasus_data.semantics.relations import RelationType, load_relations


def _rollups():
    return [r for r in load_relations() if r.relation_type is RelationType.ROLLUP_TO]


def test_there_are_rollups_and_classifications_to_compare() -> None:
    """Guards the tests below against silently matching nothing."""
    assert _rollups(), "no rollup_to relations declared"
    assert classifications(), "curation/geography.yml declares nothing"


def test_a_rollup_naming_a_declared_classification_uses_its_codelist() -> None:
    """The rule that would have caught `artifact: CIRAC`.

    A relation is free to roll up to something geography.yml does not model. But
    if it names a classification that IS declared there, it must use that
    classification's table — otherwise two parts of the package answer the same
    question from different data.
    """
    declared = {name: str(body["codelist"]).upper()
                for name, body in classifications().items()}
    disagreements = [
        f"{r.system}.{r.dataset}.{r.field_name} -> {r.target_name}: "
        f"joins.yml says {r.artifact}, geography.yml says {declared[r.target_name]}"
        for r in _rollups()
        if r.target_name in declared and r.artifact.upper() != declared[r.target_name]
    ]
    assert not disagreements, (
        "joins.yml and geography.yml disagree about which codelist carries a "
        f"classification: {disagreements}"
    )


def test_no_rollup_uses_a_codelist_geography_deliberately_excluded() -> None:
    """`RSAUDBR` carries two regionalisations; `BR_MACSAUD` conflicts on 66%.

    Both were excluded from the compiled geography with a measured reason. A
    relation quietly binding one would reintroduce exactly what the exclusion
    was protecting against.
    """
    barred = {name.upper(): body.get("reason", "") for name, body in excluded().items()}
    used = [
        f"{r.field_name} -> {r.target_name} uses {r.artifact}"
        for r in _rollups()
        if r.artifact.upper() in barred
    ]
    assert not used, (
        f"these relations use a codelist geography.yml excluded: {used}. "
        "If the exclusion is wrong, change geography.yml and its measurement — "
        "not the relation alone."
    )


@pytest.mark.parametrize("classification", sorted(classifications()))
def test_every_declared_classification_is_compiled_into_the_pack(classification: str) -> None:
    """geography.yml must not declare something the pack does not carry."""
    from pegasus_data.geography import members

    assert members(classification), (
        f"{classification} is declared in curation/geography.yml but no member "
        "appears in the compiled pack; rebuild it with build_geography_pack"
    )
