"""Where reference lookups record what they had to substitute.

Two components need this bookkeeping and neither can own it. ``persist.reference``
reads the materialised warehouse and falls back to the shipped label pack;
``labelpack`` reads that pack and must report its own substitutions the same
way. Putting the ledger in either one makes them import each other — a cycle
that only survived because the imports were hidden inside functions, which is a
cycle with the symptom suppressed rather than a design.

So the ledger lives here, importing nothing from either.

What gets recorded is always the same shape: *you were answered, but not with
what you asked for*. A codelist borrowed from another system's copy, or a
vintage that is not the one you named. Neither is visible in the returned data,
which is exactly why it has to be written down somewhere the caller can read.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

__all__ = [
    "HISTORICAL_LABEL_POLICIES",
    "borrowed_tables",
    "historical_label_policy",
    "historical_labels",
    "collecting",
    "fallback_vintages",
    "note_borrowed",
    "note_fallback",
    "note_pack_fallback",
]

#: ``(table_id, requested_system)`` served from a neighbour's copy.
_BORROWED: set[tuple[str, str]] = set()

#: ``(table_id, requested_period, served)`` where `served` is "current" (no
#: window covers the request, the open-ended table stood in), "unresolved"
#: (nothing covers it and there is no open-ended table), or "unwindowed-pack"
#: (the shipped pack carries no validity windows at all, so the request cannot
#: be answered from it even in principle).
_FALLBACK_VINTAGE: set[tuple[str, str, str]] = set()

#: The collector for the render currently running on this thread or task.
#: The module-level sets above are process-lifetime and idempotent, so a caller
#: cannot tell from them whether THIS render borrowed a table or whether some
#: earlier one did — adding a member that is already present does not change a
#: set. Anything reporting per call needs its own box, and a ContextVar gives
#: one per thread and per async task without threading an argument through
#: every reference lookup.
_COLLECTOR: ContextVar[dict[str, set] | None] = ContextVar(
    "pegasus_reference_collector", default=None
)


@contextmanager
def collecting() -> Iterator[dict[str, set]]:
    """Collect the reference decisions made inside this block."""
    box: dict[str, set] = {"borrowed": set(), "fallback": set()}
    token = _COLLECTOR.set(box)
    try:
        yield box
    finally:
        _COLLECTOR.reset(token)


def _record(kind: str, item: tuple) -> None:
    box = _COLLECTOR.get()
    if box is not None:
        box[kind].add(item)


def note_borrowed(table_id: str, requested_system: str) -> None:
    """A codelist answered from a system other than the one asked for."""
    _BORROWED.add((table_id, requested_system))
    _record("borrowed", (table_id, requested_system))


def note_fallback(table_id: str, asked: str, served: str) -> None:
    """A vintage answered by a window other than the one asked for."""
    _FALLBACK_VINTAGE.add((table_id, asked, served))
    _record("fallback", (table_id, asked, served))


def note_pack_fallback(
    table_id: str, asked: str, served: str, *, windowed: bool
) -> None:
    """Record that the SHIPPED PACK could not answer a vintage.

    Separate from the warehouse's own fallback because the cause and the remedy
    differ: a pack built before validity windows existed cannot answer a
    historical question at all, and the fix is to rebuild the pack, not to
    materialise a reference table.
    """
    note_fallback(table_id, asked, served if windowed else "unwindowed-pack")


def borrowed_tables() -> set[tuple[str, str]]:
    """``(table_id, requested_system)`` pairs served from a neighbour's copy."""
    return set(_BORROWED)


def fallback_vintages() -> set[tuple[str, str, str]]:
    """Requests answered by a vintage other than the one asked for.

    A historical label rendered from today's table is not wrong the way a
    borrowed system's table is wrong, but it is not what was asked for either,
    and the caller could otherwise only detect it by reading `valid_from` off
    the result and knowing what to compare it against.
    """
    return set(_FALLBACK_VINTAGE)


#: What to do when a historical vintage is asked for and the only thing
#: available is a mapping that cannot be vintage-correct — in practice, the
#: shipped label pack, which carries no validity windows.
#:
#: "current" is the default because refusing would make the shipped pack
#: useless for its entire purpose: DATASUS publishes with a lag, so essentially
#: ALL real data is historical, and blanket refusal leaves every column
#: unlabelled on a fresh install. Most codelists are stable across decades —
#: SEXO has meant the same thing for thirty years — and throwing all of them
#: away because a few (ICD revisions, procedure tables) genuinely changed is a
#: worse trade than labelling and saying so.
#:
#: Every such substitution is recorded per codelist and warned about, and
#: `strict_labels=True` refuses outright. "refuse" makes that refusal the
#: default for callers who would rather have no label than an unversioned one.
HISTORICAL_LABEL_POLICIES: dict[str, str] = {
    "current": "label with the current mapping, and record that the vintage is unversioned",
    "refuse": "leave the column unlabelled rather than apply a mapping that cannot be vintage-correct",
}

_HISTORICAL: ContextVar[str] = ContextVar("pegasus_historical_labels", default="current")


@contextmanager
def historical_label_policy(policy: str) -> Iterator[None]:
    """Apply a historical-label policy for the duration of this block."""
    if policy not in HISTORICAL_LABEL_POLICIES:
        raise ValueError(
            f"unknown historical_labels policy {policy!r}; choose one of "
            + ", ".join(f"{k!r} ({v})" for k, v in HISTORICAL_LABEL_POLICIES.items())
        )
    token = _HISTORICAL.set(policy)
    try:
        yield
    finally:
        _HISTORICAL.reset(token)


def historical_labels() -> str:
    """The policy in force for this render."""
    return _HISTORICAL.get()
