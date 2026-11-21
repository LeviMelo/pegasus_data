"""A column reached through a key: SIH-SP's sex and age, which SIH-RD files on the same AIH (ADR-0199).

A dataset whose rows are lines of a record another dataset files (SIH-SP: the procedure lines of an admission, the
admission in SIH-RD) can lack the properties a population account stratifies by. Its role file then declares the column
``through: {key: AIH, dataset: SIH-RD}`` (`column_roles`): the column of that name of that dataset, on the row sharing this
record's key. ``curation/joins.yml`` says which column of each side is the key and, where the source repeats a key, which
row stands for it (``principal``). `query` reads such a column when it is selected by name, like any other: `split` takes
it out of the request to the dataset's own files, and `attach` adds it to the result from the source's, read for the
same period and geography (publications select; they never filter records). The event readers (`read_events`,
`count_events`) call `query`, so a count of SP's procedures by sex and age is one request.

What the reading guarantees, because each failure here would be a plausible count and a wrong one:

* the rows of the dataset are the rows delivered: one source row per key is taken, never a join of the two (a join
  multiplies the many lines of an admission by the rows its key repeats), and the count is checked before and after;
* the source row is the key's principal row (RD's IDENT 1, the admission), else the first in file order; where a key's rows
  disagree on the columns read, the number of such keys is reported, not hidden by the choice;
* a record whose key finds no source row for the period has the column null, counted and reported
  (``pegasus.through`` metadata, ``QueryReport.through``, a warning), never filled with a guess, never dropped;
* keys match exactly: no padding, no truncation. Only the whitespace of a fixed-width field is trimmed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from ..ontology import Ontology
from .column_roles import ColumnRole, declared_columns

#: Schema-metadata key of a table with columns read through a key: JSON, one entry per (key, source dataset) read, as
#: `attach` reports it
THROUGH_META = b"pegasus.through"


@dataclass(frozen=True, slots=True)
class Link:
    """One source dataset read through one key for a dataset."""

    key: str
    source: str                                 # as the role files spell it (SIH-RD)
    local: str                                  # the key's column in the reading dataset (SIH-SP's SP_NAIH)
    remote: str                                 # the key's column in the source (SIH-RD's N_AIH)
    principal: tuple[str, tuple[str, ...]] | None   # the source's marker of the row that stands for a repeated key
    columns: tuple[ColumnRole, ...]             # the columns of the reading dataset read through it


def through_columns(dataset: str) -> dict[str, ColumnRole]:
    """``upper-cased column -> role`` of the columns ``dataset`` reads through a key; empty when it declares none."""
    try:
        columns = declared_columns(dataset)
    except Exception:  # noqa: BLE001 - a dataset with no role file reads nothing through a key; the query names an unknown one itself
        return {}
    return {c.column.upper(): c for c in columns if c.through is not None}


def links(dataset: str, asked: Sequence[ColumnRole]) -> list[Link]:
    """The links that read ``asked`` (through columns of ``dataset``), one per (key, source): each side's key column from
    ``curation/joins.yml`` and the source's principal row marker."""
    keys = Ontology.load().keys
    grouped: dict[tuple[str, str], list[ColumnRole]] = {}
    for column in asked:
        grouped.setdefault((column.through.key, column.through.dataset), []).append(column)   # type: ignore[union-attr]
    out = []
    for (key, source), columns in grouped.items():
        mine, theirs = keys[key].member_for(dataset), keys[key].member_for(source)
        if mine is None or theirs is None:           # the role loader refuses these; a dataset spelt another way is one of them
            raise LookupError(f"curation/joins.yml: the {key} key has no member {dataset if mine is None else source}")
        out.append(Link(key, source, mine.column, theirs.column, theirs.principal, tuple(columns)))
    return out


def split(dataset: str, select: Sequence[str] | None) -> tuple[list[str] | None, list[ColumnRole]]:
    """``select`` as the dataset's own files can answer it, and the through columns it names.

    The through columns leave the request, and the key column of each link joins it (the result is read with it, and
    `attach` drops it again unless it was asked for). Without a ``select`` nothing is read through a key: a through
    column costs a read of another dataset, and a full-width read of SP is not a request for RD's."""
    if select is None:
        return None, []
    table = through_columns(dataset)
    asked = [table[str(s).upper()] for s in select if str(s).upper() in table]
    if not asked:
        return list(select), []
    own = [s for s in select if str(s).upper() not in table]
    have = {s.upper() for s in own}
    for link in links(dataset, asked):
        if link.local.upper() not in have:
            own.append(link.local)
            have.add(link.local.upper())
    return own, asked


def attach(table: pa.Table, dataset: str, asked: Sequence[ColumnRole], select: Sequence[str],
           read: Callable[[str, list[str]], pa.Table]) -> tuple[pa.Table, dict[str, dict[str, Any]]]:
    """``table`` (``dataset``'s rows, with the key columns `split` added) with the through columns ``asked`` added, and the
    report of each link read. ``read(source, select)`` returns the source's table for the request's period and geography
    in the canonical form (codes, with a ``<column>_label`` beside each coded one when labels are asked); ``select`` is the
    caller's, to drop the key columns it did not ask for."""
    report: dict[str, dict[str, Any]] = {}
    n = table.num_rows
    wanted = {str(s).upper() for s in select}
    for link in links(dataset, asked):
        names = [c.column for c in link.columns]
        remote = read(link.source, list(dict.fromkeys([link.remote, *([link.principal[0]] if link.principal else []), *names])))
        table, entry = _attach_one(table, dataset, link, remote)
        report[f"{link.key}:{link.source}"] = entry
        if link.local.upper() not in wanted:
            table = table.drop_columns([c for c in (link.local, f"{link.local}_label") if c in table.column_names])
    if table.num_rows != n:
        raise RuntimeError(f"{dataset}: reading columns through a key changed the rows from {n} to {table.num_rows}")
    meta = dict(table.schema.metadata or {})
    meta[THROUGH_META] = json.dumps(report, sort_keys=True).encode()
    return table.replace_schema_metadata(meta), report


def _column(table: pa.Table, name: str) -> str:
    found = next((c for c in table.column_names if c.upper() == name.upper()), None)
    if found is None:
        raise KeyError(f"{name} is not among the columns read: {table.column_names}")
    return found


def _text(table: pa.Table, name: str) -> pa.Array:
    """A column as trimmed text, one chunk."""
    column = pc.utf8_trim_whitespace(pc.cast(table.column(_column(table, name)), pa.string()))
    return column.combine_chunks() if isinstance(column, pa.ChunkedArray) else column


def _one(array: pa.Array | pa.ChunkedArray) -> pa.Array:
    return array.combine_chunks() if isinstance(array, pa.ChunkedArray) else array


def _filled(text: pa.Array) -> pa.Array:
    return pc.fill_null(pc.not_equal(text, ""), False)


def _attach_one(table: pa.Table, dataset: str, link: Link, remote: pa.Table) -> tuple[pa.Table, dict[str, Any]]:
    names = [c.column for c in link.columns]
    here = _text(table, link.local)
    valid_here = _filled(here)

    # One source row per key. Its repeats are the parts one admission is billed in (RD: a principal AIH and its long-stay
    # parts, IDENT 5, in later months): the same patient, so the same sex and age, and each key is looked up, not joined.
    # Measured repeat rates (curation/joins.yml AIH): São Paulo state 2023-01, 56 of 210,161 AIHs, each with a long-stay
    # part; Acre 2023, 20 AIHs and 53 extra rows (0.09%), all a principal and its long-stay parts within one month's file
    # (docs/evaluation/2026-10-24-sp-sex-and-age-through-the-aih.md: Acre 2023-01 1 of 4,164, 2013-06 5 of 4,179, none
    # disagreeing on sex or age).
    there = _text(remote, link.remote)
    keep = _filled(there)
    rows = remote.filter(keep)
    encoded = _one(pc.dictionary_encode(there.filter(keep)))
    code = encoded.indices.to_numpy(zero_copy_only=False).astype(np.int64)
    distinct = len(encoded.dictionary)
    priority = np.ones(rows.num_rows, dtype=np.int8)
    if link.principal is not None and rows.num_rows:
        marker, codes = link.principal
        is_principal = pc.fill_null(pc.is_in(_text(rows, marker), value_set=pa.array(list(codes), pa.string())), False)
        priority = np.where(is_principal.to_numpy(zero_copy_only=False), 0, 1).astype(np.int8)
    order = np.lexsort((np.arange(rows.num_rows), priority, code))      # by key, the principal first, then file order
    first = np.ones(rows.num_rows, dtype=bool)
    first[1:] = code[order][1:] != code[order][:-1]
    chosen = rows.take(pa.array(order[first]))                      # row i is the dictionary's key i: codes run 0..distinct-1
    repeats = np.bincount(code, minlength=distinct)

    # keys whose rows disagree on the columns read: counted, so the choice above is seen to matter or not
    disagree = 0
    if (repeats > 1).any():
        parts = [pc.fill_null(pc.cast(rows.column(_column(rows, name)), pa.string()), "\x01") for name in names]
        signature = _one(pc.dictionary_encode(_one(pc.binary_join_element_wise(*parts, "\x00"))))
        sig = signature.indices.to_numpy(zero_copy_only=False).astype(np.int64)
        low, high = np.full(distinct, np.iinfo(np.int64).max), np.full(distinct, -1)
        np.minimum.at(low, code, sig)
        np.maximum.at(high, code, sig)
        disagree = int((low != high).sum())

    found = pc.index_in(here, value_set=encoded.dictionary)          # null where the key is blank or in no source row
    matched = pc.is_valid(found)
    theirs = {c.upper(): c for c in chosen.column_names}
    for name in names:
        for suffix in ("", "_label"):                                # the code, and its label when labels are asked
            source = theirs.get(f"{name}{suffix}".upper())
            if source is None:
                if not suffix:
                    raise KeyError(f"{link.source} returned no {name}")
                continue
            if f"{name}{suffix}" in table.column_names:
                raise ValueError(f"{dataset} files a column {name}{suffix} itself; it cannot also be read through {link.key}")
            table = table.append_column(f"{name}{suffix}", pc.take(chosen.column(source), found))

    n = table.num_rows
    n_matched = int(pc.sum(pc.cast(matched, pa.int64())).as_py() or 0)
    keys_here = pc.unique(here.filter(valid_here))
    keys_matched = pc.unique(here.filter(matched))
    entry = {
        "source": link.source, "key": link.key, "columns": names, "key_column": link.local, "source_key_column": link.remote,
        "rows": n, "matched": n_matched, "unmatched": n - n_matched, "unmatched_blank_key": int((~valid_here.to_numpy(zero_copy_only=False)).sum()),
        "keys": len(keys_here), "keys_matched": len(keys_matched), "keys_unmatched": len(keys_here) - len(keys_matched),
        "source_rows": remote.num_rows, "source_blank_key": remote.num_rows - rows.num_rows, "source_keys": distinct,
        "source_repeated_keys": int((repeats > 1).sum()), "source_disagreeing_keys": disagree,
        "rule": ("one source row per key: the first with " + f"{link.principal[0]} in {list(link.principal[1])}, else the first in file order"
                 if link.principal else "one source row per key: the first in file order"),
    }
    return table, entry


def describe(entry: dict[str, Any], dataset: str) -> str | None:
    """The sentence that says a link left records without a source row (None when every record found one)."""
    if not entry["unmatched"]:
        return None
    return (f"{dataset}: {entry['unmatched']:,} of {entry['rows']:,} rows ({entry['unmatched'] / max(entry['rows'], 1):.2%}) have no "
            f"{entry['source']} row for their {entry['key']} in the same period and geography ({entry['keys_unmatched']:,} of "
            f"{entry['keys']:,} keys; {entry['unmatched_blank_key']:,} with no key); their {', '.join(entry['columns'])} are null, "
            f"not guessed")
