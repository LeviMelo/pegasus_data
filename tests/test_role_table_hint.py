"""An unheld role's error names the same attribute under the dataset's own subject (ABNc t03, 2026-11-24)."""
import pytest

from pegasus_data.linkage.roles import role_table


def test_unheld_role_suggests_the_datasets_own_name():
    with pytest.raises(KeyError, match="did you mean deceased.race"):
        role_table("SIM-DO", period=2019, geography="AL", roles=["patient.race"])
