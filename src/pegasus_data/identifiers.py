"""Identifiers of legal entities and persons: what they are, and keeping them out of labels.

A CNPJ identifies a legal entity; a CPF identifies a person, is never resolved
to a name, and must never appear inside a label (CLAUDE.md §6). DATASUS's
registry tables glue both onto the front of names: ``CNPJ 04.034.526/0013-87-
UNIDADE MISTA …``, ``000.026.159/91-ARNOLDO …`` (a CPF). 558,043 label rows of
the 2026-09 label pack began with one (ADR-0102). Every label map strips them
here, and so does the pack build.
"""

from __future__ import annotations

import re

__all__ = ["ID_PREFIX", "strip_identifier", "valid_cnpj", "valid_cpf"]

#: An identifier, optionally named, at the start of a label:
#: ``CNPJ 00.000.000/0000-00-``, ``CPF 981.489.152/53-``,
#: ``84.306.455/0001-20-``, ``000.026.159/91-`` (a CPF in the kit's layout).
ID_PREFIX = re.compile(
    r"^\s*(?:CNPJ|CPF)?\s*\d{2,3}\.[0-9A-Z]{3}\.[0-9A-Z]{3}[/.]\d{2,4}(?:-\d{2})?\s*-\s*"
)


def strip_identifier(label: object) -> str | None:
    """The label without a leading CNPJ/CPF; None if nothing else is left."""
    if label is None:
        return None
    text = ID_PREFIX.sub("", str(label)).strip()
    return text or None


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def valid_cnpj(value: object) -> bool:
    """A 14-digit CNPJ whose two check digits hold."""
    digits = _digits(value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    numbers = [int(char) for char in digits]
    for length in (12, 13):
        weights = list(range(length - 7, 1, -1)) + list(range(9, 1, -1))
        remainder = sum(n * w for n, w in zip(numbers[:length], weights, strict=True)) % 11
        check = 0 if remainder < 2 else 11 - remainder
        if numbers[length] != check:
            return False
    return True


def valid_cpf(value: object) -> bool:
    """An 11-digit CPF whose two check digits hold."""
    digits = _digits(value)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    numbers = [int(char) for char in digits]
    for length in (9, 10):
        total = sum(n * (length + 1 - i) for i, n in enumerate(numbers[:length]))
        if numbers[length] != (total * 10) % 11 % 10:
            return False
    return True
