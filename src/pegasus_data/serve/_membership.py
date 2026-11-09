"""``/geo/membership``: the identity service a client joins against.

Built once per (membership pack, system) from the :class:`~pegasus_data.geography.Membership`
objects, kept as bytes, and replayed with an ETag. The handler used to call
``memberships()`` for 5,571 municipalities on every request (2.9 to 4.0 s, 4.1 MB,
no cache header) and dropped what the objects say about disagreement.

A classification the publishing systems disagree about (health_colegiado for 288
municipalities, health_region for 46, metropolitan_region for 13, 347 in all) is
listed under ``conflicts`` for that municipality: with no ``system`` named, its
value in ``memberships`` is ONE of several defensible answers, and the client is
told so instead of joining on it as if it were the answer.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any

from ._cache import ByteCache

_CACHE = ByteCache(64 * 1024 * 1024)

BASIS_NEUTRAL = (
    "no system named: where the publishing systems disagree about a classification, `memberships` carries "
    "a system-neutral answer if the pack has one, else the first system's alphabetically (arbitrary), and the "
    "classification is listed in `conflicts`; pass system=<one of `systems`> for that system's own answer"
)
BASIS_SYSTEM = (
    "memberships are the named system's own; a classification that system does not publish falls back to "
    "the system-neutral or first-sorted answer and is listed in `conflicts` when systems disagree about it"
)


def _pack() -> tuple[str, int]:
    from ..geography import _pack_mtime, _pack_path

    path = _pack_path(None)
    return (str(path), _pack_mtime(str(path))) if path is not None else ("", 0)


def systems() -> tuple[str, ...]:
    """The publishing systems the membership pack holds (`geography.membership_systems`, the pack's owner)."""
    from ..geography import membership_systems

    return membership_systems()


def canonical_system(system: str | None) -> str | None:
    """The pack's own spelling of a system, or None for no system; ValueError when the pack has no such system."""
    if not system:
        return None
    for known in systems():
        if known.upper() == system.upper():
            return known
    raise ValueError(f"unknown system {system!r}; the membership pack holds {list(systems())}")


@lru_cache(maxsize=4)
def _entries(path: str, mtime_ns: int, system: str | None) -> dict[str, dict[str, Any]]:
    from ..geography import memberships, municipalities

    out: dict[str, dict[str, Any]] = {}
    for code6, row in municipalities().items():
        found = memberships(code6, system=system)
        out[row["code7"]] = {
            "code6": code6,
            "name": row["name"],
            "uf": row["uf_sigla"],
            "uf_name": row["uf_name"],
            "uf_code": row["uf_code"],
            "macroregion": row["macroregion"],
            "memberships": found.as_dict(),
            "conflicts": list(found.conflicts),
        }
    return out


def membership_body(system: str | None, uf: str | None) -> tuple[bytes, str]:
    """``(body, etag)`` for one request; ValueError when ``system`` is not one of the pack's."""
    import orjson

    chosen = canonical_system(system)
    path, mtime_ns = _pack()
    wanted = uf.upper() if uf else None
    key = (path, mtime_ns, chosen, wanted)

    def build() -> tuple[bytes, int]:
        entries = _entries(path, mtime_ns, chosen)
        out = {code: e for code, e in entries.items() if wanted is None or e["uf"].upper() == wanted}
        body = orjson.dumps({
            "count": len(out),
            "system": system,
            "systems": list(systems()),
            "basis": BASIS_SYSTEM if chosen else BASIS_NEUTRAL,
            "contested": sum(1 for e in out.values() if e["conflicts"]),
            "membership": out,
        })
        return body, len(body)

    body = _CACHE.once(key, build)
    return body, '"' + hashlib.sha1(repr(key).encode()).hexdigest()[:20] + '"'
