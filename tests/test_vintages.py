"""Codelists are versioned, and decoding against the wrong vintage is silent.

The same MUNICBR code carries different labels in the 1992-1997 kit and in the
current one, because municipalities were created, merged and renamed in between.
Decoding a 1998 extract against today's table resolves every code — to the wrong
name. Nothing errors, nothing is empty, and the output looks right.

A research group reading a compendium asked for versioned code dictionaries as a
first-class concern. translate(year=) already selects the vintage; what was
missing was any way to SEE that a codelist is versioned without pulling the
optional codes table, which runs to 425 MB.
"""

from __future__ import annotations

from pegasus_data.semantics.tabkit import kit_validity


class TestTheCompetenceWindowIsFoundWhereverItIs:
    def test_a_window_in_the_filename(self) -> None:
        assert kit_validity(
            "/dissemin/publicos/SIHSUS/Auxiliar/TAB_SIH_199201-199712.zip"
        ) == ("199201", "199712")

    def test_a_window_in_a_parent_directory(self) -> None:
        """DATASUS dates the FOLDER as readily as the file.

        Reading only the filename dated CIH's 2008-2010 mappings "current" — the
        one thing they are certainly not.
        """
        assert kit_validity(
            "/dissemin/publicos/CIH/200801_201012/Auxiliar/TAB_CIH.zip"
        ) == ("200801", "201012")

    def test_the_filename_wins_over_the_directory(self) -> None:
        """The more specific claim governs when a path carries both."""
        assert kit_validity(
            "/dissemin/publicos/SIH/199201_200712/TAB_SIH_201001-201512.zip"
        ) == ("201001", "201512")

    def test_a_bare_kit_is_current_and_says_nothing(self) -> None:
        """None means open-ended current, which is a fact, not a gap."""
        assert kit_validity("/dissemin/publicos/SIHSUS/Auxiliar/TAB_SIH.zip") == (
            None,
            None,
        )
