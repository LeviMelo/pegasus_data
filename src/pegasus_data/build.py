"""Build stages: normalise into the lake, ingest denominators, ingest the API.

Kept apart from :mod:`pegasus_data.pipeline` because these stages *write data*
rather than metadata, and because they are the ones a user is most likely to run
repeatedly with narrow scopes (one system, one UF, a range of years).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, fields
from pathlib import PurePosixPath
from typing import Any

import pyarrow as pa

from .catalog.store import CatalogStore, utcnow
from .config import Settings
from .decode.base import DecodeError, logical_source_id
from .decode.isolation import IsolatedDecodeError
from .decode.registry import ReaderRegistry
from .decode.service import (
    ABSENT,
    FAILED,
    decode_source,
    member_verdict,
    record_decode_failure,
    short_body_note,
)
from .normalize.engine import (
    NormalizePlan,
    build_plan,
    normalize_table,
    plan_fingerprint,
)
from .normalize.geo import MunicipalityIndex
from .persist.lake import Lake
from .persist.staging import staged_tree
from .pipeline import Pipeline, StageResult
from .progress import ItemTimeout
from .semantics.dictionary import DictionaryCache
from .sources import demas_api, ibge


@dataclass(slots=True)
class BuildStats:
    families: int = 0
    #: Files the build OPENED. Not files that contributed rows: a family can
    #: claim a file whose schema does not fit its plan, and that file is still
    #: attempted. The distinction is the zero-row bug's signature, so the two
    #: are counted apart rather than conflated under one hopeful name.
    files: int = 0
    #: Files that matched the plan and whose rows reached a partition.
    files_contributing: int = 0
    #: Files opened and decoded whose schema did not fit the family's plan.
    files_mismatched: int = 0
    rows: int = 0
    partitions: int = 0
    #: Partitions left alone because rebuilding them would reproduce the same
    #: bytes. Reported, because "0 partitions written" must be legible as
    #: "nothing changed" rather than "the build did nothing".
    partitions_reused: int = 0
    bytes_written: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    representations_deduplicated: int = 0
    representation_conflicts: list[str] = field(default_factory=list)

    def merge(self, other: BuildStats) -> None:
        """Add another build's counts (a partition built on another thread)."""
        for f in fields(other):
            name, value = f.name, getattr(other, f.name)
            mine = getattr(self, name)
            if isinstance(mine, list):
                mine.extend(value)
            else:
                setattr(self, name, mine + value)

    def as_dict(self) -> dict[str, object]:
        return {
            "families": self.families,
            "files_attempted": self.files,
            "files_contributing": self.files_contributing,
            "files_mismatched": self.files_mismatched,
            # Kept under the old key too: it is what every existing caller and
            # log line reads. It has always meant "attempted".
            "files": self.files,
            "rows": self.rows,
            "partitions": self.partitions,
            "partitions_reused": self.partitions_reused,
            "bytes_written": self.bytes_written,
            "skipped": self.skipped[:20],
            "errors": self.errors[:20],
            "representations_deduplicated": self.representations_deduplicated,
            "representation_conflicts": self.representation_conflicts[:20],
        }


def partition_fingerprint(
    plan_digest: str, group: Sequence[dict[str, object]], digests: dict[str, str]
) -> str:
    """What this partition would be built FROM and BY.

    Sources are identified by CONTENT, not by path or mtime: DATASUS republishes
    a competência under the same name with different bytes, and the CAS already
    turns that into a different digest. Ordered, so the same set of files in a
    different listing order is the same fingerprint.
    """
    h = hashlib.sha256()
    h.update(b"pegasus.partition.v1\x00")
    h.update(plan_digest.encode())
    h.update(b"\x00")
    for m in sorted(group, key=lambda x: str(x["path"])):
        path = str(m["path"])
        h.update(path.encode())
        h.update(b"\x00")
        # A file the fetcher could not resolve has no digest. It contributes its
        # ABSENCE, so a later build that does get it has a different fingerprint.
        h.update((digests.get(path) or "<unresolved>").encode())
        h.update(b"\x00")
        h.update(str(m["member"] or "").encode())
        h.update(b"\x00")
    return h.hexdigest()


@dataclass
class _PartitionTally:
    """What materialising one partition did, per level of the old nesting.

    Separate fields because they count different things and used to be five
    `+= 1`s at four nesting levels: a file can be decoded and not match, match
    and contribute no rows, or be missing entirely.
    """

    rows: int = 0
    partitions: int = 0
    decoded: int = 0
    contributing: int = 0
    mismatched: int = 0
    undecoded: int = 0


class Builder:
    """Turns catalogued families into Parquet partitions."""

    def __init__(self, pipeline: Pipeline) -> None:
        self.pipeline = pipeline
        self.settings: Settings = pipeline.settings
        self.catalog: CatalogStore = pipeline.catalog
        self.lake = Lake(
            self.settings.lake_dir,
            self.catalog,
            compression=self.settings.compression,
            row_group_size=self.settings.row_group_size,
        )

    def _partition_workers(self) -> int:
        """How many partitions build at once: as many as the decoder pool has
        processes (decode_source sizes it the same way). In-process decoding
        holds the GIL, so it stays one at a time."""
        if not self.settings.decode_isolation:
            return 1
        from .decode.admission import decode_workers

        return self.settings.decode_workers or decode_workers()

    # ------------------------------------------------------------------ build

    def _materialise_partition(
        self,
        *,
        family: Mapping[str, Any],
        family_id: str,
        plan: NormalizePlan,
        uf: str,
        year: int,
        group: Sequence[Mapping[str, Any]],
        digests: Mapping[str, str],
        registry: ReaderRegistry,
        fingerprint: str,
        stats: BuildStats,
        on_file: Callable[[str, str], None] | None,
    ) -> _PartitionTally:
        """Decode one (uf, year) group and write it as one partition.

        The materialisation step. It was the deepest nesting in the tree — over
        groups, over members, over decoded tables, over batches, inside the
        family loop — and every accounting defect this review found in the build
        lived at that depth, where it is genuinely hard to see which counter
        belongs to which level.
        """
        tally = _PartitionTally()
        sources: list[str] = []
        members_by_digest: dict[str, set[str]] = {}
        for item in group:
            digest = digests.get(str(item["path"]))
            if digest:
                members_by_digest.setdefault(digest, set()).add(
                    str(item["member"] or "")
                )
        decoded_outcomes: dict[str, Any] = {}
        #: digest -> why the decoder could not take it, so its other members are not decoded (and failed) again.
        failed_digests: dict[str, str] = {}

        def _undecodable(path: str, member: str, *, reason: str, outcome: Any = None) -> None:
            """The one record of a source that was acquired and could not be read: the gap, the error, the count. The
            file is not counted as decoded, and the partition is marked after it is written so the next build tries
            it again."""
            why = record_decode_failure(self.catalog, path, outcome=outcome, member=member, reason=reason)
            stats.errors.append((logical_source_id(path, member), f"decode: {why}"))
            tally.undecoded += 1

        #: How many members of this partition still need each decoded source. A source's decoded tables (the spool of an
        #: Arrow IPC copy on disk) were kept until the whole partition was written: twelve decoded months at once, times
        #: the partitions built in parallel.
        remaining: dict[str, int] = {}
        for item in group:
            digest = digests.get(str(item["path"]))
            if digest:
                remaining[digest] = remaining.get(digest, 0) + 1

        def _release(digest: str | None) -> None:
            if not digest:
                return
            remaining[digest] -= 1
            if remaining[digest] > 0:
                return
            outcome = decoded_outcomes.pop(digest, None)
            if outcome is None:
                return
            for owner in (outcome, *getattr(outcome, "tables", ())):
                keeper = getattr(owner, "retains", None)
                if hasattr(keeper, "cleanup"):
                    try:
                        keeper.cleanup()
                    except OSError:  # pragma: no cover - Windows may still hold a handle; the janitor takes it
                        pass

        def _member(m: Mapping[str, Any]) -> Iterator[pa.RecordBatch]:
            """Decode and normalise one member, YIELDING as we go."""
            path = str(m["path"])
            digest = digests.get(path)
            if not digest:
                stats.skipped.append(path)
                tally.undecoded += 1
                return
            if on_file:
                on_file(family_id, path)
            wanted_member = str(m["member"] or "")
            source_id = logical_source_id(path, wanted_member)
            if digest in failed_digests:
                _undecodable(path, wanted_member, reason=failed_digests[digest])
                return
            outcome = decoded_outcomes.get(digest)
            if outcome is None:
                selected_members = members_by_digest[digest]
                try:
                    outcome = decode_source(
                        self.pipeline.blobs.path_for(digest),
                        logical_path=path,
                        settings=self.settings,
                        members=(
                            None if "" in selected_members else sorted(selected_members)
                        ),
                        row_limit=registry.row_limit,
                    )
                except (ItemTimeout, IsolatedDecodeError, DecodeError, OSError) as exc:
                    # A decoder that timed out or died on this source is this source's gap, not the build's end:
                    # the exception used to leave `pool.map`, abort every partition and store no outcome row.
                    failed_digests[digest] = f"{type(exc).__name__}: {exc}"
                    _undecodable(path, wanted_member, reason=failed_digests[digest])
                    return
                decoded_outcomes[digest] = outcome
            verdict, why = member_verdict(outcome, wanted_member)
            if verdict == ABSENT:
                # Listed archive without this member: the state published nothing for that component.
                stats.skipped.append(f"{source_id} (not in the archive)")
                return
            if verdict == FAILED:
                _undecodable(path, wanted_member, reason=why, outcome=outcome)
                return
            matched_here = False
            for table in outcome.tables:
                if wanted_member and table.member != wanted_member:
                    continue
                if not _matches_schema(table.field_names, plan):
                    continue
                matched_here = True
                if (short := short_body_note(table)) is not None:
                    # Its rows are written, and the partition is short of what the file's own header declares: said
                    # (exit 1), not left as a warning string nobody reads.
                    stats.errors.append((source_id, f"short: {short}"))
                normalized_date = m.get("normalized_date")
                competencia = (
                    int(normalized_date)
                    if normalized_date is not None
                    and int(normalized_date) % 100
                    else None
                )
                source_resolution = (
                    "month" if competencia is not None else
                    "year" if normalized_date is not None
                    and int(normalized_date) % 100 == 0 else
                    "unknown"
                )
                for batch in normalize_table(table, plan, blob_sha256=digest):
                    # Internal semantic provenance: a codelist can change
                    # in July, which a year-only partition cannot recover.
                    enriched = batch.append_column(
                        "_competencia",
                        pa.array([competencia] * batch.num_rows, type=pa.int32()),
                    )
                    yield enriched.append_column(
                        "_source_resolution",
                        pa.array([source_resolution] * batch.num_rows, type=pa.string()),
                    )
            stats.files += 1
            tally.decoded += 1
            if not matched_here:
                # The family claims this file but its schema does not fit
                # the plan. This is the zero-row bug's signature, and it has
                # to be counted rather than skipped past.
                tally.mismatched += 1
                stats.files_mismatched += 1
                # NOT added to `sources`. That list becomes the partition's
                # recorded provenance, and a file that contributed no rows
                # did not provenance anything — it made the partition look
                # derived from evidence it does not contain.
                return
            sources.append(source_id)
            stats.files_contributing += 1
            tally.contributing += 1

        def _normalised() -> Iterator[pa.RecordBatch]:
            """Decode and normalise one member at a time, YIELDING as we go.

            A generator, not a list. The whole state-year partition used to be
            accumulated here and only then handed to the writer, so the storage
            layer's streaming was preceded by materialising exactly what it was
            streaming to avoid. `sources` and `tally` fill as this is consumed;
            `write_batches` records provenance only after the batches are
            written, so both are complete by the time it reads them.
            """
            for m in group:
                try:
                    yield from _member(m)
                finally:
                    _release(digests.get(str(m["path"])))

        # No `if not batches` pre-check: knowing whether there are any would
        # mean consuming the generator, which is the materialisation this
        # removed. write_batches returns None when the stream yields no rows.

        # No part number: this build owns the whole partition, and write_batches
        # replaces it. Numbering from the files already there is what let a
        # rebuild land beside its own stale output.
        written = self.lake.write_batches(
            _normalised(),
            system=str(family["system"]),
            family_id=family_id,
            schema_signature=str(family["schema_signature"]),
            uf=uf,
            year=year,
            source_paths=sources,
            build_fingerprint=fingerprint,
        )
        if written:
            stats.partitions += 1
            stats.rows += written.row_count
            stats.bytes_written += written.byte_size
            tally.rows += written.row_count
            tally.partitions += 1
            if tally.undecoded:
                # The partition is short of the files that could not be read. Its fingerprint hashes their digests,
                # so left alone the next build would find it current and never try them again.
                self.catalog.execute(
                    "UPDATE lake_partitions SET build_fingerprint = ? "
                    "WHERE family_id = ? AND schema_signature = ? AND uf = ? AND year = ?",
                    (f"<undecodable>:{fingerprint}", family_id, str(family["schema_signature"]), uf, year),
                )
        return tally

    def build(
        self,
        *,
        systems: Sequence[str] | None = None,
        series: Sequence[str] | None = None,
        ufs: Sequence[str] | None = None,
        years: Sequence[int] | None = None,
        family_ids: Sequence[str] | None = None,
        max_files_per_family: int | None = None,
        keep_raw: bool | None = None,
        emit_labels: bool = True,
        rebuild: bool = False,
        on_file: Callable[[str, str], None] | None = None,
    ) -> StageResult:
        """Decode and normalise into the lake.

        ``rebuild=True`` forces every selected partition to be written again.
        The default skips a partition whose sources and normalisation plan are
        unchanged and whose file is still on disk — the raw CAS already stops
        us re-downloading, and this stops us re-decoding.
        """
        stats = BuildStats()
        # trees a killed build left half-written (their process gone) are removed before this one writes beside them
        from .persist.staging import prune_dead_staging

        prune_dead_staging(self.lake.root)
        run_id = uuid.uuid4().hex[:12]
        outcomes: list[tuple[object, ...]] = []

        def record_outcome(row: tuple[object, ...]) -> None:
            """One family's outcome, written as it finishes: a failure in a later family used to lose every earlier
            family's row (written once at the end), and the error row carried 9 values for 10 placeholders."""
            outcomes.append(row)
            self.catalog.executemany(
                """
                INSERT INTO build_outcomes (run_id, family_id, system, files_selected, files_decoded,
                                            files_matched, rows_written, partitions, reason,
                                            recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(run_id, family_id) DO UPDATE SET
                    files_selected=excluded.files_selected, files_decoded=excluded.files_decoded,
                    files_matched=excluded.files_matched,
                    rows_written=excluded.rows_written, partitions=excluded.partitions,
                    reason=excluded.reason, recorded_at=excluded.recorded_at
                """,
                [row],
            )

        municipalities = MunicipalityIndex.from_catalog(self.catalog)
        registry = ReaderRegistry()
        cache = DictionaryCache(self.catalog)

        clauses: list[str] = []
        params: list[object] = []
        if systems:
            clauses.append(f"system IN ({','.join('?' * len(systems))})")
            params.extend(systems)
        if series:
            clauses.append(f"series IN ({','.join('?' * len(series))})")
            params.extend(series)
        if family_ids:
            clauses.append(f"family_id IN ({','.join('?' * len(family_ids))})")
            params.extend(family_ids)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        families = self.catalog.query(
            f"SELECT family_id, system, series, schema_signature FROM families{where}", params
        )

        selected_units: set[tuple[str, str, str]] = set()
        selected_family_ids = [str(family["family_id"]) for family in families]
        if selected_family_ids:
            marks = ",".join("?" for _ in selected_family_ids)
            rows = self.catalog.query(
                f"""
                SELECT ff.family_id, ff.path, ff.member, fa.geo_code, fa.year,
                       fa.normalized_date, fa.logical_id, fa.container_format,
                       files.size, families.schema_signature
                  FROM family_files ff
                  JOIN families ON families.family_id=ff.family_id
                  LEFT JOIN file_facts fa ON fa.path=ff.path
                  LEFT JOIN files ON files.path=ff.path
                 WHERE ff.family_id IN ({marks})
                """,
                tuple(selected_family_ids),
            )
            uf_set = set(ufs or ())
            year_set = set(years or ())
            candidates = [
                dict(row)
                for row in rows
                if (not uf_set or (row["geo_code"] or "") in uf_set)
                and (not year_set or row["year"] in year_set)
            ]
            from .representations import choose_representations

            choice = choose_representations(self.catalog, candidates)
            selected_units = {
                (
                    str(row["family_id"]),
                    str(row["path"]),
                    str(row.get("member") or ""),
                )
                for row in choice.selected
            }
            stats.representations_deduplicated += len(choice.dropped)
            stats.representation_conflicts.extend(choice.conflicts)

        for family in families:
            family_id = family["family_id"]
            try:
                plan = build_plan(
                    self.catalog, family_id=family_id, municipalities=municipalities, cache=cache
                )
            except KeyError as exc:
                stats.errors.append((family_id, str(exc)))
                record_outcome((run_id, family_id, family["system"], 0, 0, 0, 0, 0,
                                f"no normalisation plan: {exc}", utcnow()))
                continue
            plan.keep_raw = True if keep_raw is None else keep_raw
            plan.emit_labels = emit_labels

            members = self.catalog.query(
                """
                SELECT ff.path, ff.member, fa.geo_code, fa.year, fa.normalized_date,
                       fa.logical_id, fa.container_format, files.size
                  FROM family_files ff
                  LEFT JOIN file_facts fa ON fa.path = ff.path
                  LEFT JOIN files ON files.path = ff.path
                 WHERE ff.family_id = ?
                 ORDER BY fa.year, ff.path
                """,
                (family_id,),
            )
            selected = [
                dict(m)
                for m in members
                if (not ufs or (m["geo_code"] or "") in set(ufs))
                and (not years or (m["year"] in set(years)))
                and (
                    str(family_id),
                    str(m["path"]),
                    str(m["member"] or ""),
                ) in selected_units
            ]
            if not ufs:
                # A year DATASUS publishes as one national file is built from it
                # alone: SIM and SINASC also publish every state's file, and
                # building both stored each record twice (22,196 SIM rows were
                # measured in both, 2026-10-04). Asking for states builds them.
                national_years = {m["year"] for m in selected if str(m["geo_code"] or "") == "BR"}
                selected = [m for m in selected
                            if str(m["geo_code"] or "") == "BR" or m["year"] not in national_years]
            if max_files_per_family:
                selected = selected[:max_files_per_family]
            if not selected:
                record_outcome((
                    run_id, family_id, family["system"], 0, 0, 0, 0, 0,
                    f"no files matched the requested filters (uf={list(ufs or [])}, "
                    f"years={list(years or [])}) out of {len(members)} in the family",
                    utcnow(),
                ))
                continue

            stats.families += 1
            grouped: dict[tuple[str, int], list[dict[str, object]]] = {}
            for m in selected:
                uf = str(m["geo_code"] or "NA")
                year = int(m["year"]) if m["year"] is not None else 0
                grouped.setdefault((uf, year), []).append(m)

            plan_digest = plan_fingerprint(plan)
            # Partitions already built from the files' current digests are
            # reused before anything is fetched: after `pegasus-data prune` the
            # bytes are gone, and checking a partition must not download them.
            known = self.pipeline.fetcher.known_current([str(m["path"]) for m in selected])
            current: set[tuple[str, int]] = set()
            if not rebuild and len(known) == len(selected):
                for (uf, year), group in grouped.items():
                    if self.lake.partition_is_current(
                        system=str(family["system"]), family_id=family_id,
                        schema_signature=str(family["schema_signature"]), uf=uf, year=year,
                        fingerprint=partition_fingerprint(plan_digest, group, known),
                    ):
                        current.add((uf, year))
            stats.partitions_reused += len(current)
            grouped = {key: group for key, group in grouped.items() if key not in current}
            digests = self.pipeline.fetcher.ensure([str(m["path"]) for group in grouped.values() for m in group])
            # A file that could not be fetched is reported with its cause. The
            # build used to say only "skipped" and exit 0 with no errors, so a
            # failed download of DNBR2021 read as a successful empty build
            # (2026-10-03).
            fetch_stats = getattr(self.pipeline.fetcher, "last_stats", None)
            stats.errors.extend((path, f"fetch: {error}") for path, error in getattr(fetch_stats, "errors", []))
            family_rows = 0
            family_parts = 0
            # Decoded vs matched, apart. A mismatched file WAS decoded; folding
            # it into one number is what let "files_decoded" read as evidence
            # that a zero-row family had nothing to give.
            family_decoded = 0
            family_files = 0
            undecoded = 0
            schema_mismatch = 0

            jobs = []
            for (uf, year), group in sorted(grouped.items()):
                fingerprint = partition_fingerprint(plan_digest, group, digests)
                if not rebuild and self.lake.partition_is_current(
                    system=str(family["system"]),
                    family_id=family_id,
                    schema_signature=str(family["schema_signature"]),
                    uf=uf,
                    year=year,
                    fingerprint=fingerprint,
                ):
                    stats.partitions_reused += 1
                    continue
                jobs.append((uf, year, group, fingerprint))

            def build_one(job: tuple, family=family, family_id=family_id, plan=plan,
                          digests=digests) -> tuple[_PartitionTally, BuildStats]:
                uf, year, group, fingerprint = job
                local = BuildStats()
                try:
                    tally = self._materialise_partition(
                        family=family, family_id=family_id, plan=plan, uf=uf, year=year, group=group,
                        digests=digests, registry=registry, fingerprint=fingerprint, stats=local, on_file=on_file,
                    )
                except Exception as exc:  # noqa: BLE001 - one partition that could not be written is not the run
                    # An exception left `pool.map` whole: the other partitions were waited for, `build()` raised and no
                    # `build_outcomes` row of any family of the run was stored.
                    local.errors.append((f"{family_id} uf={uf} year={year}", f"{type(exc).__name__}: {exc}"))
                    tally = _PartitionTally(undecoded=len(group))
                return tally, local

            # Partitions are independent (their own files, their own Parquet
            # directory; the catalog serialises its writes): decode them on
            # the decoder pool's processes at once. One at a time, a national
            # SIH year took 298 s on a 20-core machine, decode-bound.
            workers = self._partition_workers() if len(jobs) > 1 else 1
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="partition") as pool:
                results = list(pool.map(build_one, jobs))
            for tally, local in results:
                stats.merge(local)
                undecoded += tally.undecoded
                schema_mismatch += tally.mismatched
                family_decoded += tally.decoded
                family_files += tally.contributing
                family_rows += tally.rows
                family_parts += tally.partitions

            reason = None
            if family_rows == 0:
                if schema_mismatch:
                    reason = (
                        f"{schema_mismatch} of {len(selected)} selected files did not match the "
                        f"family's {len(plan.fields)}-field plan; the family points at files whose "
                        "schema it does not have"
                    )
                elif undecoded:
                    reason = f"{undecoded} of {len(selected)} selected files could not be fetched or decoded"
                else:
                    reason = f"{len(selected)} files decoded and matched the plan but yielded no rows"
            record_outcome((
                run_id, family_id, family["system"], len(selected), family_decoded,
                family_files, family_rows, family_parts, reason, utcnow(),
            ))

        counts = stats.as_dict()
        counts["run_id"] = run_id
        counts["families_with_no_rows"] = sum(1 for o in outcomes if o[8] is not None)
        return StageResult("build", counts=counts)

    # ------------------------------------------------------------- population

    def population(self, *, series: Sequence[str] | None = None) -> StageResult:
        """Ingest the denominator series into ``lake/population/<series>/``."""
        wanted = list(series or ibge.KNOWN_SERIES)
        registry = ReaderRegistry()
        counts: dict[str, object] = {}
        notes: list[str] = []

        for name in wanted:
            spec = ibge.KNOWN_SERIES.get(name)
            if spec is None:
                notes.append(f"unknown series: {name}")
                continue
            if name == "CENSO":
                # the census comes from SIDRA, not from the FTP tree
                from .sidra import Sidra
                from .sidra.population import build_census

                counts[name] = build_census(Sidra(settings=self.settings), self.settings.population_dir)
                continue
            rows = self.catalog.query(
                "SELECT path FROM files WHERE path LIKE ? AND gone_at IS NULL ORDER BY path",
                (f"%/{spec.directory}/%",),
            )
            paths = [r["path"] for r in rows]
            if not paths:
                notes.append(f"{name}: no files catalogued under {spec.directory}")
                continue
            digests = self.pipeline.fetcher.ensure(paths)
            target = self.settings.population_dir / name
            written_rows = 0
            written_files = 0
            observed_years: set[int] = set()
            try:
                with staged_tree(target) as staged_target:
                    for path in paths:
                        digest = digests.get(path)
                        if not digest:
                            raise RuntimeError(f"source was not acquired: {path}")
                        outcome = decode_source(
                            self.pipeline.blobs.path_for(digest),
                            logical_path=path,
                            settings=self.settings,
                            row_limit=registry.row_limit,
                        )
                        tables = list(outcome.tables)
                        # POPTBR22.zip and POPTBR23.zip hold the national table
                        # POPTBR22.dbf AND its 27 per-state parts; reading every
                        # member counted each municipality twice (2022 total
                        # 406,161,512, 2026-10-03). The member named as the
                        # archive is the national table; the rest partition it.
                        archive = PurePosixPath(path).stem.upper()
                        national = [t for t in tables
                                    if t.member and PurePosixPath(t.member).stem.upper() == archive]
                        if national and len(tables) > len(national):
                            notes.append(
                                f"{path}: read {national[0].member} only; "
                                f"{len(tables) - len(national)} per-state members partition it"
                            )
                            tables = national
                        for table in tables:
                            arrow = ibge.canonicalize(table.to_table())
                            arrow = ibge.coerce_numeric(
                                arrow, ["year", "population", "age", "municipality"]
                            )
                            if "year" not in arrow.schema.names:
                                year = _year_from_path(self.catalog, path)
                                if year is not None:
                                    arrow = arrow.append_column(
                                        "year",
                                        pa.array([year] * arrow.num_rows, type=pa.int64()),
                                    )
                            if "year" in arrow.schema.names:
                                observed_years.update(
                                    int(v)
                                    for v in arrow.column("year").to_pylist()
                                    if v is not None
                                )
                            arrow = arrow.append_column(
                                "_source_path",
                                pa.array([path] * arrow.num_rows, type=pa.string()),
                            )
                            import pyarrow.parquet as pq

                            stem = PurePosixPath(path).stem
                            member = (
                                f"_{PurePosixPath(table.member).stem}"
                                if table.member
                                else ""
                            )
                            pq.write_table(
                                arrow,
                                staged_target
                                / f"{stem}{member}-{digest[:12]}.parquet",
                                compression=self.settings.compression,
                                use_dictionary=True,
                            )
                            written_rows += arrow.num_rows
                            written_files += 1
                    if not written_files:
                        raise RuntimeError("selected sources decoded to no population tables")
            except Exception as exc:  # keep the previous complete series intact
                notes.append(f"{name}: rebuild not published ({exc})")
                continue
            spec.file_count = len(paths)
            if observed_years:
                spec.year_min = min(observed_years)
                spec.year_max = max(observed_years)
            ibge.register_series(self.catalog, spec)
            counts[name] = {
                "files": written_files,
                "rows": written_rows,
                "years": [spec.year_min, spec.year_max],
                "age_standardizable": spec.age_standardizable,
            }

        self._close_population_questions(counts)
        return StageResult("population", counts=counts, notes=notes)

    def _close_population_questions(self, counts: dict[str, object]) -> None:
        projpop = counts.get("projpop")
        if isinstance(projpop, dict) and projpop.get("rows"):
            self.catalog.resolve_question(
                "V7.projpop",
                resolution=(
                    "IBGE/projpop holds 71 files named PROJUF00…PROJUF70 — IBGE population "
                    "*projections* keyed by projection year 2000–2070, at UF level with sex "
                    "and age. They do NOT supersede POPSVS: POPSVS is municipal and projpop "
                    "is not, so projpop complements it for projected years and for national "
                    "age structures. Note the two-digit year runs forward to 70, so the usual "
                    "1900/2000 pivot would misread the later files by a century; the epoch is "
                    "inferred per directory from contiguity."
                ),
                evidence=json.dumps(projpop),
            )
        if counts:
            self.catalog.note_question(
                "V8.ministry_denominator",
                area="denominators",
                question="Which population series backs the Ministry's own published rates?",
                verification_procedure=(
                    "Reproduce one published TabNet rate (e.g. SIH hospitalisation rate for a "
                    "given UF and year) from microdata under POPSVS and under POPTCU, and see "
                    "which reproduces the published figure exactly. This module ingests both "
                    "behind one interface precisely so the comparison is a one-line change."
                ),
                blocking="validation of any rate against a federal publication",
            )

    # ------------------------------------------------------------------ demas

    def demas(
        self,
        *,
        endpoints: Sequence[str] | None = None,
        max_pages: int = 5,
        page_size: int = 100,
    ) -> StageResult:
        counts: dict[str, object] = {}
        notes: list[str] = []
        with demas_api.DemasClient() as client:
            spec = client.swagger()
            parsed = demas_api.parse_spec(spec)
            demas_api.persist_spec(self.catalog, spec, parsed)
            counts["spec_version"] = str((spec.get("info") or {}).get("version") or "unknown")
            counts["endpoints_in_spec"] = len(parsed)

            wanted = list(endpoints or demas_api.PRIORITY_ENDPOINTS)
            landed: dict[str, object] = {}
            granularity: dict[str, list[str]] = {}
            for path in wanted:
                endpoint = demas_api.resolve_endpoint(parsed, path)
                if endpoint is None:
                    notes.append(f"endpoint not served: {path}")
                    self.catalog.note_question(
                        f"api.endpoint_missing:{path}",
                        area="api",
                        question=f"The endpoint {path} named in the architecture brief is not in the current DEMAS spec.",
                        verification_procedure="Re-read /static/swagger.json and search for a renamed equivalent.",
                        blocking=demas_api.PRIORITY_ENDPOINTS.get(path, ""),
                    )
                    continue
                granularity[endpoint.path] = [
                    str(p.get("name")) for p in endpoint.parameters if p.get("name")
                ]
                rows: list[dict[str, object]] = []
                ingest_params = json.dumps(
                    {"limit": page_size, "max_pages": max_pages}
                )
                try:
                    for page_index, page in enumerate(
                        demas_api.fetch_all(client, endpoint, page_size=page_size, max_pages=max_pages)
                    ):
                        rows.extend(page)
                        if page_index + 1 >= max_pages:
                            break
                except Exception as exc:
                    notes.append(f"{endpoint.path}: fetch failed ({exc})")
                    self.catalog.executemany(
                        "DELETE FROM api_ingests WHERE path=? AND params=?",
                        [(endpoint.path, ingest_params)],
                    )
                    continue
                if not rows:
                    notes.append(f"{endpoint.path}: returned no rows")
                    self.catalog.executemany(
                        "DELETE FROM api_ingests WHERE path=? AND params=?",
                        [(endpoint.path, ingest_params)],
                    )
                    continue
                table = demas_api.rows_to_table(rows)
                target = self.settings.demas_dir / _slug(endpoint.path)
                import pyarrow.parquet as pq

                with staged_tree(target) as staged_target:
                    pq.write_table(
                        table,
                        staged_target / "part-00000.parquet",
                        compression=self.settings.compression,
                    )
                self.catalog.executemany(
                    """
                    INSERT INTO api_ingests (path, params, rows, lake_path, fetched_at)
                    VALUES (?,?,?,?, datetime('now'))
                    ON CONFLICT(path, params) DO UPDATE SET rows=excluded.rows, fetched_at=excluded.fetched_at
                    """,
                    [
                        (
                            endpoint.path,
                            ingest_params,
                            table.num_rows,
                            str(target),
                        )
                    ],
                )
                landed[endpoint.path] = {"rows": table.num_rows, "columns": table.num_columns}
            counts["landed"] = landed
            counts["reconciliation"] = demas_api.reconciliation_targets(self.catalog)

            if granularity:
                self.catalog.resolve_question(
                    "V9.demas_granularity",
                    resolution=(
                        "Granularity read from the live OpenAPI parameters. BNAFAR/Hórus "
                        "(/daf/estoque-medicamentos-bnafar-horus) is município × establishment "
                        "× month, and it DOES carry medication identity via codigo_catmat plus "
                        "tipo_produto and sigla_programa_saude — so it can see a chronic patient's "
                        "supply before decompensation. The Previne Brasil cadastro and indicator "
                        "endpoints are both still served by spec "
                        f"{counts['spec_version']}. Full parameter lists are in api_endpoints.params_json."
                    ),
                    evidence=json.dumps(granularity),
                )
        return StageResult("demas", counts=counts, notes=notes)


def _matches_schema(field_names: Sequence[str], plan: NormalizePlan) -> bool:
    """Only normalise a table whose columns are the ones the plan was built for.

    A family is defined by its schema signature, so a file whose columns differ
    belongs to a different generation and must not be folded in silently (D2/D3).
    """
    return schema_fit(field_names, plan) is not None


def schema_fit(field_names: Sequence[str], plan: NormalizePlan) -> tuple[str, ...] | None:
    """``()`` for the family's own schema; the added columns for a republication
    that kept every catalogued column and gained some; ``None`` otherwise.

    DATASUS republished all of SIA-PA on 2026-09-17 with one more column
    (``PA_VL_CRD``). Every earlier column kept its name, so its meaning; refusing
    the files turned a year of SIA-PA into "no rows" (ADR-0078). A file that LOST
    a column is still a different generation and is refused.
    """
    from .inventory.families import schema_signature

    if schema_signature(field_names) == plan.schema_signature:
        return ()
    names = [str(n).upper() for n in field_names]
    if plan.columns and set(plan.columns) < set(names):
        known = set(plan.columns)
        return tuple(n for n in names if n not in known)
    return None


def _year_from_path(catalog: CatalogStore, path: str) -> int | None:
    rows = catalog.query("SELECT year FROM file_facts WHERE path = ?", (path,))
    return int(rows[0]["year"]) if rows and rows[0]["year"] is not None else None


def _slug(path: str) -> str:
    return path.strip("/").replace("/", "__").replace("-", "_")


def build_lake(dataset: str, years: Sequence[int], *, root: str | None = None, labels: bool = False,
               release: bool = False) -> dict[str, Any]:
    """The lake for one dataset's years (``pegasus-data build`` for a caller that is not the command line).

    A partition whose sources and normalisation plan are unchanged and whose Parquet is on disk is kept, so a second
    call over the same years writes nothing. Without labels by default: a reader of codes needs none, and they double
    the footprint. Measured on 2026-10-09 in PegaSUS's data root: a national CIHA year decodes in 30-60 min from its
    324 DBC files and reads in 12 s from the lake (18.9 M records).

    ``release`` then deletes the downloaded files of these years that verified partitions hold (`prune` for this
    build alone; ``released`` in the counts): a build otherwise keeps every file beside its Parquet, so each
    downloaded gigabyte cost disk twice, and a rebuild fetches them again."""
    from pathlib import Path

    from ._request import parse_dataset
    from .config import load_settings

    system, series = parse_dataset(dataset)
    pipeline = Pipeline(load_settings(root=Path(root) if root else None))
    try:
        result = Builder(pipeline).build(systems=[system], series=[series] if series else None, years=list(years),
                                         emit_labels=labels)
        counts = dict(result.counts)
        if release:
            from .extract import _files

            paths = [f["path"] for f in _files(pipeline.settings, dataset, years)]
            counts["released"] = pipeline.blobs.prune_verified(Path(pipeline.settings.lake_dir), paths=paths)
        return counts
    finally:
        pipeline.close()
