## 2026-08-18 — Codepage detection cannot be "first one that works"

*Split from docs/history/FINDINGS.md §3 on 2026-09-28; text unchanged.*

### Codepage detection cannot be "first one that works"

cp850 and latin-1 both map all 256 byte values, so neither ever raises and "try in order, take the
first that decodes" always returns the first candidate regardless of correctness.

Measured: `IDENT.CNV` decoded as cp850 gives `Longa permanÛncia`. The byte is 0xEA — `ê` in
latin-1, `Û` in cp850. The file is latin-1 and the ordered approach chose wrong, silently, for
every accented label in the kit.

`textenc.py` scores candidates on how much the decoded text looks like Portuguese: letters
Portuguese actually uses count for, and the box-drawing and Nordic glyphs that appear when a DOS
codepage is read as a Windows one count heavily against.
