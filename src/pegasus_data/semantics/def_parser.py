"""TabNet ``.DEF`` parser (D7).

A ``.DEF`` declares one TabNet tabulation: which files it reads, which variables
exist, what each is **officially called**, and which ``.CNV`` or lookup ``.DBF``
decodes it. It is the only artifact in the whole tree that states a column's
official name, which makes it the single highest-value input to the ledger.

Grammar, read off ``RD.DEF`` (547 lines) in ``TAB_SIH_199201-199712.zip``::

    ;Movimento de AIH - Arquivos Reduzidos - Brasil     ← title comment
    A..\\DADOS\\RD_AIH_Reduzida\\RD*.DBC                  ← the data glob
    ?\\TAB\\RD.HLP                                       ← help file
    IValor Total       ,VAL_TOT                        ← Incremento (a measure)
    LRegião int        ,MUNIC_MOV ,1        ,REGIAO.CNV ← Linha
    CRegião int        ,MUNIC_MOV ,1        ,REGIAOC.CNV← Coluna
    SUF - ZI           ,UF_ZI     ,1        ,UFALFA.CNV ← Seleção
    XCapital int       ,MUNIC_MOV ,1        ,CAPITAL.CNV← available everywhere
    LHospital BR (CNES),CNES      ,RAZAO    ,TCNESBR.DBF← DBF lookup, label column

The line prefix says where TabNet may use the variable: ``L``inha, ``C``oluna,
``S``eleção, ``X`` (all three) — and ``I`` for an *incremento*.

That ``I`` prefix is worth more than it looks: it is the Ministry's own statement
that a variable is **summable**. ``IValor Total,VAL_TOT``, ``IÓbitos,MORTE``,
``IPermanência,DIAS_PERM`` are all declared additive by the people who publish the
data, which is exactly what ``ledger.aggregation`` needs and what stops a
downstream consumer from averaging a rate (§6.3).

The ``A`` line matters too: its glob binds this dictionary to the data files it
describes, so a ``.DEF`` can be attached to a family instead of guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from ..textenc import best_effort_decode

__all__ = ["DefVariable", "DefFile", "parse_def", "parse_def_bytes", "USAGE_LABELS"]

USAGE_LABELS = {
    "L": "linha",
    "C": "coluna",
    "S": "selecao",
    "X": "linha_coluna_selecao",
    "I": "incremento",
}

#: Variables declared with ``I`` are counts or amounts the Ministry itself sums.
ADDITIVE_USAGE = "I"


@dataclass(slots=True)
class DefVariable:
    usage: str            # 'L' | 'C' | 'S' | 'X' | 'I'
    display_name: str     # the official Portuguese label
    field_name: str       # the physical column
    category_arg: str | None = None   # '1', 'RAZAO', a width, …
    lookup_ref: str | None = None     # CNV or DBF that decodes it
    line_no: int = 0

    @property
    def is_measure(self) -> bool:
        return self.usage == ADDITIVE_USAGE

    @property
    def lookup_kind(self) -> str | None:
        if not self.lookup_ref:
            return None
        suffix = PureWindowsPath(self.lookup_ref).suffix.lower()
        return {".cnv": "cnv", ".dbf": "dbf"}.get(suffix)


@dataclass(slots=True)
class DefFile:
    name: str
    source_ref: str
    title: str | None = None
    data_glob: str | None = None
    help_ref: str | None = None
    variables: list[DefVariable] = field(default_factory=list)
    encoding: str = "cp850"
    warnings: list[str] = field(default_factory=list)

    @property
    def measures(self) -> list[DefVariable]:
        return [v for v in self.variables if v.is_measure]

    @property
    def dimensions(self) -> list[DefVariable]:
        return [v for v in self.variables if not v.is_measure]

    def official_names(self) -> dict[str, str]:
        """``field → official display name``, preferring a dimension declaration.

        A field often appears many times under different usages and labels
        (``UF - ZI`` as L, C and S). The shortest label is taken as the canonical
        one because TabNet's longer variants are display decorations of the same
        variable ("Região int" vs "Região e UF int").
        """
        best: dict[str, str] = {}
        for v in self.variables:
            current = best.get(v.field_name)
            if current is None or len(v.display_name) < len(current):
                best[v.field_name] = v.display_name
        return best

    def lookups_for(self, field_name: str) -> list[str]:
        seen: list[str] = []
        for v in self.variables:
            if v.field_name == field_name and v.lookup_ref and v.lookup_ref not in seen:
                seen.append(v.lookup_ref)
        return seen

    def file_pattern(self) -> str | None:
        """The bare filename glob from the ``A`` line, e.g. ``RD*.DBC``."""
        if not self.data_glob:
            return None
        return PureWindowsPath(self.data_glob.replace("/", "\\")).name or None


_VALID_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")


def parse_def_bytes(data: bytes, *, name: str, source_ref: str) -> DefFile:
    text, encoding = best_effort_decode(data)
    out = DefFile(name=name, source_ref=source_ref, encoding=encoding)
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        marker = line[0]
        body = line[1:]
        if marker == ";":
            if out.title is None and body.strip():
                out.title = body.strip()
            continue
        if marker == "A":
            out.data_glob = body.strip()
            continue
        if marker == "?":
            out.help_ref = body.strip()
            continue
        if marker not in USAGE_LABELS:
            # Unknown markers are recorded, not silently dropped: an unhandled
            # line is a gap in the grammar and should be visible as one.
            out.warnings.append(f"line {line_no}: unrecognised marker {marker!r}")
            continue
        parts = [p.strip() for p in body.split(",")]
        if len(parts) < 2:
            out.warnings.append(f"line {line_no}: variable line has no field name")
            continue
        display_name = parts[0].strip()
        field_name = parts[1].strip().upper()
        if not _VALID_FIELD.match(field_name):
            out.warnings.append(f"line {line_no}: implausible field name {field_name!r}")
            continue
        category_arg = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
        lookup_ref = parts[3].strip() if len(parts) > 3 and parts[3].strip() else None
        out.variables.append(
            DefVariable(
                usage=marker,
                display_name=display_name,
                field_name=field_name,
                category_arg=category_arg,
                lookup_ref=lookup_ref,
                line_no=line_no,
            )
        )
    if not out.variables:
        out.warnings.append("no variables parsed")
    return out


def parse_def(path: str | Path) -> DefFile:
    p = Path(path)
    return parse_def_bytes(p.read_bytes(), name=p.name, source_ref=str(p))
