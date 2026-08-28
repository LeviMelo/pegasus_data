"""`query(select=[...])` must not ask a source for columns it synthesises.

The planner adds `_source_path`, `year`, `_competencia` and `_source_resolution`
as hidden dependencies, because the semantic layer needs them. Three of those
four are DERIVED after retrieval by `_with_competence`, out of `_source_path`
and the source report — no DATASUS family carries them.

Passing them to the source projection made every `select=` query refuse:

    MissingColumnError: column '_competencia' is not present in family
    SIHSUS_RD_e2f7244ae5 (also absent: _source_resolution, year)

It only bit with an explicit `select=`, because without one nothing is projected
and every column arrives regardless — which is why it survived a suite that
otherwise exercises this path hard. Found while wiring the aggregate build,
which wanted a narrow projection (FINDINGS §3o).
"""

from __future__ import annotations

from pegasus_data._query_engine.executor import SYNTHESISED_COLUMNS
from pegasus_data._query_engine.planner import plan


def test_the_planner_still_declares_them_as_dependencies() -> None:
    """They ARE needed — the fix is where they are asked for, not whether."""
    hidden = set(plan("SIH-RD", period="2022-01", geography="AC").retrieval.hidden_dependencies)
    assert hidden >= SYNTHESISED_COLUMNS, (
        "the semantic layer still needs these; only the SOURCE projection must "
        "not ask for them"
    )


def test_source_path_is_not_treated_as_synthesised() -> None:
    """It is a real column — `provenance=True` supplies it on the fetch path and
    the lake stores it — and `_with_competence` derives the other three FROM it.
    Dropping it would break the thing that produces them."""
    assert "_source_path" not in SYNTHESISED_COLUMNS


def test_exactly_the_derived_columns_are_excluded() -> None:
    assert {"_competencia", "year", "_source_resolution"} == SYNTHESISED_COLUMNS


def test_a_select_projection_excludes_them() -> None:
    """The assertion that would have caught the defect without a network."""
    query_plan = plan(
        "SIH-RD", period="2022-01", geography="AC",
        select=["ANO_CMPT", "MES_CMPT", "MUNIC_RES", "SEXO"],
    )
    requested = (
        set(query_plan.spec.select or ()) | set(query_plan.retrieval.hidden_dependencies)
    ) - SYNTHESISED_COLUMNS
    assert not (requested & SYNTHESISED_COLUMNS)
    assert {"ANO_CMPT", "MUNIC_RES"} <= requested
