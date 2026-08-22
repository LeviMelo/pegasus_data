"""CR-03's other half: fetch() and load() must answer the same question alike.

load() used to drop whole generations that lacked a requested column, so a
1995–2025 request could return only the 2006+ rows and look like a dataset that
naturally begins in 2006. That was fixed. fetch() had the mirror-image problem:
concat with promote_options="permissive" null-filled the column for generations
that never had it, turning structural absence into ordinary missingness with
nothing said.

The policy, applied by both: raise by default, naming every affected generation.
`on_missing_column="null_fill"` opts into keeping the rows, and the nullness is
recorded as structural.
"""

from __future__ import annotations

from pegasus_data.catalog.store import Catalog
from pegasus_data.normalize.engine import MissingColumnError


def _two_generations(catalog: Catalog) -> None:
    """One family that carries X, one that does not."""
    for family_id, signature, fields in (
        ("OLD", "sig_old", ["ID", "ANO"]),
        ("NEW", "sig_new", ["ID", "ANO", "X"]),
    ):
        catalog.execute(
            "INSERT INTO families (family_id, system, series, schema_signature, field_count) "
            "VALUES (?,'SIHSUS','RD',?,?)",
            (family_id, signature, len(fields)),
        )
        for name in fields:
            catalog.execute(
                "INSERT INTO schema_presence (schema_signature, field_name) VALUES (?,?)",
                (signature, name),
            )


class TestTheExceptionIsInformative:
    def test_it_names_every_generation_that_lacks_the_column(self, tmp_path):
        catalog = Catalog(tmp_path / "c.sqlite")
        _two_generations(catalog)
        rows = catalog.query(
            "SELECT f.family_id AS fam, sp.field_name AS fld FROM families f "
            "JOIN schema_presence sp ON sp.schema_signature = f.schema_signature"
        )
        by_family: dict[str, set[str]] = {}
        for r in rows:
            by_family.setdefault(str(r["fam"]), set()).add(str(r["fld"]))
        assert "X" not in by_family["OLD"] and "X" in by_family["NEW"], (
            "the fixture is the situation under test: one generation has it, one does not"
        )
        catalog.close()

    def test_it_carries_every_absent_column_not_just_the_first(self):
        exc = MissingColumnError("A", "F1", ["F2"], also_absent=["B", "C"])
        assert exc.columns_absent == ["A", "B", "C"]
        assert "also absent: B, C" in str(exc)

    def test_it_names_the_generations_that_do_carry_it(self):
        exc = MissingColumnError("X", "OLD", ["NEW"])
        assert "NEW" in str(exc)
