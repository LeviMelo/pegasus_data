"""The three ways a .CNV header was being missed, and what it cost.

A ``.CNV`` opens with ``<count> <width>``. Miss it and two things break at once:
the header line itself is parsed as a category — so its title becomes a "code" —
and the file loses its declared width, which every downstream expansion needs to
zero-pad against.

All four codelists that verify step 16 flagged as holding prose instead of codes
failed here, and all four were bound to real columns, so the wrong thing was
being matched against real records.
"""

from __future__ import annotations

from pegasus_data.semantics.cnv_parser import parse_cnv_bytes


def _parse(text: str):
    return parse_cnv_bytes(text.encode("latin-1"), name="t.cnv", source_ref="t.cnv")


class TestTheHeaderIsFound:
    def test_a_bare_header(self) -> None:
        cnv = _parse("3  6\n     1  ALPHA     000001\n     2  BETA      000002\n")
        assert (cnv.declared_categories, cnv.code_width) == (3, 6)
        assert [c.label for c in cnv.categories] == ["ALPHA", "BETA"]

    def test_a_header_with_a_trailing_flag(self) -> None:
        """``326 7 L`` — the form NHE.cnv and medico02.CNV use."""
        cnv = _parse("2  7 L\n     1  ALPHA     0000001\n     2  BETA      0000002\n")
        assert (cnv.declared_categories, cnv.code_width) == (2, 7)
        assert len(cnv.categories) == 2

    def test_comments_before_the_header_do_not_hide_it(self) -> None:
        """Mun_A_F_P.cnv opens with two ';' lines, then its real header."""
        cnv = _parse(
            "; Municipios com A-Aeroporto ; Patch 4.2\n"
            "; Revisado pela UT-Sinan 2019\n"
            "2  6\n"
            "     1  ALPHA     000001\n"
            "     2  BETA      000002\n"
        )
        assert (cnv.declared_categories, cnv.code_width) == (2, 6)
        assert len(cnv.categories) == 2

    def test_a_comment_never_becomes_a_category(self) -> None:
        cnv = _parse(
            "; a note ; Patch 4.2\n2  6\n     1  ALPHA     000001\n"
            "; another note mid-file\n     2  BETA      000002\n"
        )
        assert [c.label for c in cnv.categories] == ["ALPHA", "BETA"]
        assert not any(";" in c.expression for c in cnv.categories)

    def test_a_data_row_cannot_impersonate_a_flagged_header(self) -> None:
        """``1 000001 A`` is a row; the leading zero says the second field is a code."""
        cnv = _parse("     1  000001 A\n     2  000002 B\n")
        assert cnv.declared_categories is None
        assert len(cnv.categories) == 2

    def test_line_numbers_survive_dropped_comments(self) -> None:
        """Warnings cite a line a human is expected to open the file and read."""
        cnv = _parse("; note\n2  6\n     1  ALPHA     000001\n     2  BETA      000002\n")
        assert [c.line_no for c in cnv.categories] == [3, 4]


class TestTrailingJunkDoesNotBecomeTheCode:
    def test_the_aligned_code_wins_over_the_stray_word(self) -> None:
        """medico02.CNV line 11: the code is XXXXXX; 'vascular' is debris.

        Taking the LAST token, as the fallback used to, chose 'vascular' — a
        word, stored as a code, bound to CNES.CBOUNICO.
        """
        cnv = _parse(
            "3  6\n"
            "     1  GINECO OBSTETRA                                    XXXXXX\n"
            "     2  MEDICO DE FAMILIA                                  XXXXXX"
            "                                        vascular\n"
            "     3  OUTRO                                              223132\n"
        )
        assert [c.expression for c in cnv.categories] == ["XXXXXX", "XXXXXX", "223132"]
        assert cnv.categories[1].label == "MEDICO DE FAMILIA"

    def test_what_was_discarded_is_reported(self) -> None:
        # Three aligned lines: the expression column is inferred from the file as
        # a whole, so a two-line fixture gives it no majority to infer from.
        cnv = _parse(
            "3  6\n"
            "     1  ALPHA                                              000001\n"
            "     2  BETA                                               000002"
            "                                        junk\n"
            "     3  GAMMA                                              000003\n"
        )
        assert any("'junk'" in w and "discarded" in w for w in cnv.warnings)
        assert [c.expression for c in cnv.categories] == ["000001", "000002", "000003"]

    def test_no_category_ends_up_with_a_space_in_its_code(self) -> None:
        cnv = _parse(
            "2  7\n"
            "     1  Laboratorial (S+O)                                 NNNSSSS\n"
            "     2  Laboratorial (Z+D+C+S+O)                           SSSSSSS"
            "                                            NNNSSNS\n"
        )
        assert all(" " not in c.expression for c in cnv.categories)


class TestTheLabelIsContentNotLayout:
    def test_column_padding_inside_a_label_is_collapsed(self) -> None:
        cnv = _parse("1  6\n     1  110012 JI-PARANA               A          110012\n")
        assert cnv.categories[0].label == "110012 JI-PARANA A"
