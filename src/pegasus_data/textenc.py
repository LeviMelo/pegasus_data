"""Codepage detection for a 35-year-old, multi-vintage archive.

DATASUS spans DOS-era tooling and Windows-era tooling, so the tree mixes
**cp850** (the DOS Latin-1 codepage TabWin was built on) and **cp1252/latin-1**
without marking which is which. Files carry no BOM, and the DBF language-driver
byte is unreliable across the series.

Trying codepages in order and taking the first that does not raise **does not
work**, because cp850 and latin-1 both map all 256 byte values — neither ever
raises. Measured consequence: ``IDENT.CNV`` from the SIH kit decoded under cp850
gives ``Longa permanÛncia``; the byte is 0xEA, which is ``ê`` in latin-1 and
``Û`` in cp850. The file is latin-1 and the "first that decodes" rule silently
chose wrong.

So candidates are *scored* on how much the result looks like Portuguese: accented
letters that Portuguese actually uses count for, and the box-drawing and shading
glyphs that appear when a codepage is misapplied count against.
"""

from __future__ import annotations

__all__ = ["best_effort_decode", "decode_score", "CANDIDATE_ENCODINGS"]

CANDIDATE_ENCODINGS: tuple[str, ...] = ("cp850", "cp1252", "latin-1", "utf-8")

#: Letters Portuguese genuinely uses. Û/Ù/Ï and friends are excluded on purpose:
#: they are the tell-tale output of a misapplied codepage, not real content.
_PT_ACCENTS = set("áâãàéêíóôõúüçÁÂÃÀÉÊÍÓÔÕÚÜÇºª")

#: Glyphs that only show up when a DOS codepage is read as a Windows one or the
#: reverse: box drawing, block elements, and the odd Icelandic/Nordic letters.
_IMPLAUSIBLE = set("│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌█▄▌▐▀░▒▓■▬")
_IMPLAUSIBLE |= set("ÞþÐðÝýÏïÌìÙùÛûËëÆæØøÅåÑñ¤¦¨¯´¸")


def decode_score(text: str) -> float:
    """Higher is more plausibly Portuguese administrative text."""
    if not text:
        return 0.0
    good = 0
    bad = 0
    control = 0
    for ch in text:
        if ch in _PT_ACCENTS:
            good += 1
        elif ch in _IMPLAUSIBLE:
            bad += 1
        elif ch != "�" and ord(ch) < 32 and ch not in "\r\n\t":
            control += 1
        elif ch == "�":
            bad += 2
    # Bad glyphs are weighted heavily: one misapplied codepage produces many.
    return good - 3.0 * bad - 5.0 * control


def best_effort_decode(
    data: bytes, *, candidates: tuple[str, ...] = CANDIDATE_ENCODINGS, sample: int = 1 << 20
) -> tuple[str, str]:
    """Decode `data`, choosing the codepage whose output reads as Portuguese.

    Returns ``(text, encoding)``. Pure-ASCII payloads short-circuit, since every
    candidate agrees on them and the choice would be arbitrary.
    """
    if not data:
        return "", candidates[0]
    head = data[:sample]
    if head.isascii():
        try:
            return data.decode("ascii"), "ascii"
        except UnicodeDecodeError:
            pass

    best_text: str | None = None
    best_enc = candidates[0]
    best_score = float("-inf")
    for enc in candidates:
        try:
            probe = head.decode(enc)
        except UnicodeDecodeError:
            continue
        score = decode_score(probe)
        # UTF-8 decoding successfully on non-ASCII bytes is strong evidence in
        # itself: the encoding is self-validating and rarely matches by accident.
        if enc == "utf-8":
            score += 5.0
        if score > best_score:
            best_score = score
            best_enc = enc
            best_text = None if len(data) > len(head) else probe
    if best_text is None:
        best_text = data.decode(best_enc, errors="replace")
    return best_text, best_enc
