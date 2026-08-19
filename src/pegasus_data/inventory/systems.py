"""Which information system a file belongs to — decided by its name, not its place.

``system_from_path`` reads the system out of the path's second segment. That is
correct today and fragile by construction: DATASUS reorganises, and a directory
rename would re-label every file under it. Because ``stratum_id`` and
``family_id`` are hashes of ``(system, series, …)``, a rename would silently
re-derive every stratum and every family, and thirty-five years of continuity
would restart under new identifiers with no error anywhere.

So the filename becomes primary. ``RDAL2401.dbc`` is SIH's reduced AIH file
wherever it sits, because ``RD`` is what says so. The path corroborates, and a
disagreement between the two is **recorded as a finding**, not resolved silently
and not treated as an error — it is either a reorganisation in progress or a
prefix genuinely shared between systems, and both are worth knowing.

The prefix→system map is *learned* from a healthy crawl rather than hard-coded.
Hard-coding it would mean inventing the answer for prefixes nobody has checked;
learning it means the catalog states what it observed, with the level of
agreement attached, and can then hold that answer against a later move.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from ..catalog.store import Catalog, utcnow

#: Below this level of agreement a prefix is not treated as identifying a system:
#: it is genuinely ambiguous and the path stays authoritative for it.
MIN_AGREEMENT = 0.9

#: A prefix seen fewer times than this is too thin to learn from.
MIN_OBSERVATIONS = 5


@dataclass(slots=True)
class PrefixSystem:
    series_prefix: str
    system: str
    file_count: int
    agreement: float

    @property
    def trustworthy(self) -> bool:
        return self.agreement >= MIN_AGREEMENT and self.file_count >= MIN_OBSERVATIONS


def learn_prefix_systems(
    observations: Sequence[tuple[str | None, str | None]],
) -> list[PrefixSystem]:
    """Learn ``series_prefix → system`` from ``(prefix, system_by_path)`` pairs.

    The majority system wins, and the share holding that majority is kept as
    ``agreement``. A prefix split evenly across two systems is reported with low
    agreement rather than assigned to whichever appeared first.
    """
    by_prefix: dict[str, Counter[str]] = defaultdict(Counter)
    for prefix, system in observations:
        if prefix and system:
            by_prefix[prefix.upper()][system.upper()] += 1

    out: list[PrefixSystem] = []
    for prefix, counts in by_prefix.items():
        total = sum(counts.values())
        system, hits = counts.most_common(1)[0]
        out.append(
            PrefixSystem(
                series_prefix=prefix,
                system=system,
                file_count=total,
                agreement=hits / total if total else 0.0,
            )
        )
    return sorted(out, key=lambda p: (-p.file_count, p.series_prefix))


def persist_prefix_systems(catalog: Catalog, learned: Sequence[PrefixSystem]) -> dict[str, int]:
    """Store the map. An established answer is **held**, not relearned.

    This is the whole point of the map, and the reason it is not simply recomputed
    each run. If the mapping were relearned from whatever the current crawl saw,
    a wholesale reorganisation would teach it the new answer — ``RD → SIH_NOVO``
    — and identity would move with the files, which is exactly the failure this
    exists to prevent. Every stratum and family would re-derive under new ids and
    thirty-five years of lineage would restart silently.

    So a prefix that already has a system keeps it. Contradicting evidence is
    recorded as an open question for a person to adjudicate, because "DATASUS
    reorganised" and "this prefix is shared by two systems" look identical from
    one crawl and have opposite correct responses.
    """
    existing = {
        str(r["series_prefix"]): (str(r["system"]), int(r["file_count"]), float(r["agreement"]))
        for r in catalog.query("SELECT series_prefix, system, file_count, agreement FROM prefix_systems")
    }
    payload: list[tuple[object, ...]] = []
    contradictions = 0
    for p in learned:
        prior = existing.get(p.series_prefix)
        if prior is None:
            payload.append((p.series_prefix, p.system, p.file_count, p.agreement, utcnow()))
            continue
        prior_system, prior_count, prior_agreement = prior
        if prior_system != p.system:
            contradictions += 1
            catalog.note_question(
                f"inventory.prefix_system_changed:{p.series_prefix}",
                area="inventory",
                question=(
                    f"Series prefix {p.series_prefix} was established as belonging to "
                    f"{prior_system} ({prior_count} files); this crawl finds its files under "
                    f"{p.system} ({p.file_count} files, {p.agreement:.0%} agreement). The stored "
                    f"mapping is being held, so identity and lineage are preserved."
                ),
                verification_procedure=(
                    "Check whether the tree was reorganised (in which case update prefix_systems "
                    f"to {p.system} deliberately, accepting that strata and families re-derive) "
                    "or whether the prefix is genuinely shared between two systems (in which case "
                    "it is not a reliable identifier and the path should stay authoritative)."
                ),
                blocking=f"stable identity for {p.series_prefix} files",
            )
            continue
        # Same system: refresh the evidence, keeping the stronger observation.
        if p.file_count >= prior_count or p.agreement > prior_agreement:
            payload.append((p.series_prefix, p.system, p.file_count, p.agreement, utcnow()))
    written = catalog.executemany(
        """
        INSERT INTO prefix_systems (series_prefix, system, file_count, agreement, learned_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(series_prefix) DO UPDATE SET
            system=excluded.system, file_count=excluded.file_count,
            agreement=excluded.agreement, learned_at=excluded.learned_at
        """,
        payload,
    )
    return {"written": written, "contradictions": contradictions}


def load_prefix_systems(catalog: Catalog) -> dict[str, PrefixSystem]:
    return {
        str(r["series_prefix"]): PrefixSystem(
            series_prefix=str(r["series_prefix"]),
            system=str(r["system"]),
            file_count=int(r["file_count"]),
            agreement=float(r["agreement"]),
        )
        for r in catalog.query("SELECT * FROM prefix_systems")
    }


def resolve_system(
    *,
    series_prefix: str | None,
    system_by_path: str | None,
    learned: dict[str, PrefixSystem],
) -> tuple[str | None, str | None]:
    """Decide the system, returning ``(resolved, disagreement_or_None)``.

    The filename wins where its prefix is a trustworthy identifier. Where it is
    not — an ambiguous prefix, an unparsed name, a prefix seen only a handful of
    times — the path stays authoritative, because a weak signal must not
    override a working one.
    """
    by_name = None
    if series_prefix:
        entry = learned.get(series_prefix.upper())
        if entry and entry.trustworthy:
            by_name = entry.system

    if by_name is None:
        return (system_by_path.upper() if system_by_path else None), None
    if system_by_path and by_name != system_by_path.upper():
        # The name is authoritative, but the disagreement is the interesting part.
        return by_name, system_by_path.upper()
    return by_name, None


def record_disagreements(
    catalog: Catalog, rows: Sequence[tuple[str, str | None, str, str, str]]
) -> int:
    """Persist filename-vs-path disagreements as findings."""
    return catalog.executemany(
        """
        INSERT INTO system_disagreements
            (path, series_prefix, system_by_name, system_by_path, resolved_to, noted_at)
        VALUES (?,?,?,?,?, datetime('now'))
        ON CONFLICT(path) DO UPDATE SET
            system_by_name=excluded.system_by_name,
            system_by_path=excluded.system_by_path,
            resolved_to=excluded.resolved_to
        """,
        rows,
    )


def disagreement_summary(catalog: Catalog) -> list[dict[str, object]]:
    return [
        dict(r)
        for r in catalog.query(
            """
            SELECT system_by_name, system_by_path, COUNT(*) AS files,
                   MIN(path) AS example
              FROM system_disagreements
             GROUP BY system_by_name, system_by_path
             ORDER BY files DESC
            """
        )
    ]


def low_trust_prefixes(catalog: Catalog) -> list[dict[str, object]]:
    """Prefixes the name-first rule will not use, ranked by how much they carry.

    A prefix is low-trust when it is genuinely ambiguous (agreement below
    ``MIN_AGREEMENT``) or too thinly observed to learn from (fewer than
    ``MIN_OBSERVATIONS`` files). For those, the path stays authoritative — which
    is the old, fragile behaviour, kept deliberately because a weak signal must
    not override a working one.

    The point of ranking by file count is to show whether that fallback still
    covers anything material. A hundred prefixes holding four files each is a
    rounding error; one prefix holding forty thousand is a hole in the identity
    guarantee, and the two look identical in a count of prefixes.
    """
    rows = []
    for r in catalog.query(
        """
        SELECT p.series_prefix, p.system, p.file_count, p.agreement,
               (SELECT COUNT(*) FROM file_facts ff
                  JOIN files f ON f.path = ff.path
                 WHERE f.gone_at IS NULL AND ff.series_prefix = p.series_prefix) AS files_now
          FROM prefix_systems p
         ORDER BY p.file_count DESC
        """
    ):
        entry = PrefixSystem(
            series_prefix=str(r["series_prefix"]),
            system=str(r["system"]),
            file_count=int(r["file_count"]),
            agreement=float(r["agreement"]),
        )
        if entry.trustworthy:
            continue
        rows.append(
            {
                "series_prefix": entry.series_prefix,
                "majority_system": entry.system,
                "files": int(r["files_now"] or 0),
                "agreement": round(entry.agreement, 3),
                "reason": (
                    "ambiguous" if entry.agreement < MIN_AGREEMENT else "too few observations"
                ),
            }
        )
    return sorted(rows, key=lambda r: (-int(r["files"]), str(r["series_prefix"])))


def adjudicate_prefix(catalog: Catalog, prefix: str, system: str) -> dict[str, object]:
    """Settle a held contradiction by deciding what a prefix means.

    :func:`persist_prefix_systems` deliberately refuses to relearn an established
    mapping, because "the tree was reorganised" and "this prefix is shared" look
    identical from one crawl. That refusal needs a way out, or the first crawl to
    guess wrong owns the answer forever — and the first crawl is the *most* likely
    to guess wrong, since a partial tree is exactly what produces a mapping learned
    from a handful of files.

    Accepting a new mapping re-derives every stratum and family under the affected
    prefix on the next inventory, which is the cost of correcting identity and the
    reason this is a deliberate command rather than an automatic reconciliation.
    """
    prefix = prefix.upper()
    system = system.upper()
    prior = catalog.query(
        "SELECT system, file_count, agreement FROM prefix_systems WHERE series_prefix = ?",
        (prefix,),
    )
    if not prior:
        raise KeyError(f"no learned mapping for series prefix {prefix!r}")
    was = str(prior[0]["system"])
    catalog.execute(
        "UPDATE prefix_systems SET system = ?, learned_at = ? WHERE series_prefix = ?",
        (system, utcnow(), prefix),
    )
    catalog.resolve_question(
        f"inventory.prefix_system_changed:{prefix}",
        resolution=f"adjudicated: {prefix} means {system} (was {was})",
        evidence=f"prior_file_count={prior[0]['file_count']}, prior_agreement={prior[0]['agreement']}",
    )
    affected = catalog.scalar(
        "SELECT COUNT(*) FROM file_facts ff JOIN files f ON f.path = ff.path "
        "WHERE ff.series_prefix = ? AND f.gone_at IS NULL",
        (prefix,),
    )
    catalog.log_event(
        "inventory",
        f"adjudicated prefix {prefix}: {was} -> {system}",
        detail=f"{affected} files will re-derive their stratum and family on the next inventory",
    )
    return {"series_prefix": prefix, "was": was, "now": system, "files_affected": affected}
