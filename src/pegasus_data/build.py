"""Build stages: normalise into the lake, ingest denominators, ingest the API.

Kept apart from :mod:`pegasus_data.pipeline` because these stages *write data*
rather than metadata, and because they are the ones a user is most likely to run
repeatedly with narrow scopes (one system, one UF, a range of years).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import pyarrow as pa

from .catalog.store import Catalog, utcnow
from .config import Settings
from .decode.registry import ReaderRegistry
from .normalize.engine import NormalizePlan, build_plan, normalize_table
from .normalize.geo import MunicipalityIndex
from .persist.lake import Lake
from .pipeline import Pipeline, StageResult
from .semantics.dictionary import DictionaryCache
from .sources import demas_api, ibge


@dataclass(slots=True)
class BuildStats:
    families: int = 0
    files: int = 0
    rows: int = 0
    partitions: int = 0
    bytes_written: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "families": self.families,
            "files": self.files,
            "rows": self.rows,
            "partitions": self.partitions,
            "bytes_written": self.bytes_written,
            "skipped": self.skipped[:20],
            "errors": self.errors[:20],
        }


class Builder:
    """Turns catalogued families into Parquet partitions."""

    def __init__(self, pipeline: Pipeline) -> None:
        self.pipeline = pipeline
        self.settings: Settings = pipeline.settings
        self.catalog: Catalog = pipeline.catalog
        self.lake = Lake(
            self.settings.lake_dir,
            self.catalog,
            compression=self.settings.compression,
            row_group_size=self.settings.row_group_size,
        )

    # ------------------------------------------------------------------ build

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
        on_file: Callable[[str, str], None] | None = None,
    ) -> StageResult:
        stats = BuildStats()
        run_id = uuid.uuid4().hex[:12]
        outcomes: list[tuple[object, ...]] = []
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

        for family in families:
            family_id = family["family_id"]
            try:
                plan = build_plan(
                    self.catalog, family_id=family_id, municipalities=municipalities, cache=cache
                )
            except KeyError as exc:
                stats.errors.append((family_id, str(exc)))
                outcomes.append((run_id, family_id, family["system"], 0, 0, 0, 0,
                                 f"no normalisation plan: {exc}", utcnow()))
                continue
            plan.keep_raw = True if keep_raw is None else keep_raw
            plan.emit_labels = emit_labels

            members = self.catalog.query(
                """
                SELECT ff.path, ff.member, fa.geo_code, fa.year
                  FROM family_files ff
                  LEFT JOIN file_facts fa ON fa.path = ff.path
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
            ]
            if max_files_per_family:
                selected = selected[:max_files_per_family]
            if not selected:
                outcomes.append((
                    run_id, family_id, family["system"], 0, 0, 0, 0,
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

            digests = self.pipeline.fetcher.ensure([str(m["path"]) for m in selected])
            family_rows = 0
            family_parts = 0
            family_files = 0
            undecoded = 0
            schema_mismatch = 0

            for (uf, year), group in sorted(grouped.items()):
                batches: list[pa.RecordBatch] = []
                sources: list[str] = []
                rows_here = 0
                for m in group:
                    path = str(m["path"])
                    digest = digests.get(path)
                    if not digest:
                        stats.skipped.append(path)
                        undecoded += 1
                        continue
                    if on_file:
                        on_file(family_id, path)
                    outcome = registry.open_path(
                        self.pipeline.blobs.path_for(digest), logical_path=path
                    )
                    wanted_member = str(m["member"] or "")
                    matched_here = False
                    for table in outcome.tables:
                        if wanted_member and table.member != wanted_member:
                            continue
                        if not _matches_schema(table.field_names, plan):
                            continue
                        matched_here = True
                        for batch in normalize_table(table, plan, blob_sha256=digest):
                            batches.append(batch)
                            rows_here += batch.num_rows
                    if not matched_here:
                        # The family claims this file but its schema does not fit
                        # the plan. This is the zero-row bug's signature, and it
                        # has to be counted rather than skipped past.
                        schema_mismatch += 1
                    sources.append(path)
                    stats.files += 1
                    family_files += 1
                if not batches:
                    continue
                # No part number: this build owns the whole partition, and
                # write_batches replaces it. Numbering from the files already
                # there is what let a rebuild land beside its own stale output.
                written = self.lake.write_batches(
                    batches,
                    system=family["system"],
                    family_id=family_id,
                    schema_signature=family["schema_signature"],
                    uf=uf,
                    year=year,
                    source_paths=sources,
                )
                if written:
                    stats.partitions += 1
                    stats.rows += written.row_count
                    stats.bytes_written += written.byte_size
                    family_rows += written.row_count
                    family_parts += 1

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
            outcomes.append((
                run_id, family_id, family["system"], len(selected), family_files,
                family_rows, family_parts, reason, utcnow(),
            ))

        self.catalog.executemany(
            """
            INSERT INTO build_outcomes (run_id, family_id, system, files_selected, files_decoded,
                                        rows_written, partitions, reason, recorded_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id, family_id) DO UPDATE SET
                files_selected=excluded.files_selected, files_decoded=excluded.files_decoded,
                rows_written=excluded.rows_written, partitions=excluded.partitions,
                reason=excluded.reason, recorded_at=excluded.recorded_at
            """,
            outcomes,
        )
        counts = stats.as_dict()
        counts["run_id"] = run_id
        counts["families_with_no_rows"] = sum(1 for o in outcomes if o[7] is not None)
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
            target.mkdir(parents=True, exist_ok=True)
            written_rows = 0
            written_files = 0
            observed_years: set[int] = set()
            for path in paths:
                digest = digests.get(path)
                if not digest:
                    continue
                outcome = registry.open_path(
                    self.pipeline.blobs.path_for(digest), logical_path=path
                )
                for table in outcome.tables:
                    arrow = ibge.canonicalize(table.to_table())
                    arrow = ibge.coerce_numeric(arrow, ["year", "population", "age", "municipality"])
                    if "year" not in arrow.schema.names:
                        year = _year_from_path(self.catalog, path)
                        if year is not None:
                            arrow = arrow.append_column(
                                "year", pa.array([year] * arrow.num_rows, type=pa.int64())
                            )
                    if "year" in arrow.schema.names:
                        observed_years.update(
                            int(v) for v in arrow.column("year").to_pylist() if v is not None
                        )
                    arrow = arrow.append_column(
                        "_source_path", pa.array([path] * arrow.num_rows, type=pa.string())
                    )
                    import pyarrow.parquet as pq

                    stem = PurePosixPath(path).stem
                    member = f"_{PurePosixPath(table.member).stem}" if table.member else ""
                    pq.write_table(
                        arrow,
                        target / f"{stem}{member}.parquet",
                        compression=self.settings.compression,
                        use_dictionary=True,
                    )
                    written_rows += arrow.num_rows
                    written_files += 1
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
                try:
                    for page_index, page in enumerate(
                        demas_api.fetch_all(client, endpoint, page_size=page_size, max_pages=max_pages)
                    ):
                        rows.extend(page)
                        if page_index + 1 >= max_pages:
                            break
                except Exception as exc:
                    notes.append(f"{endpoint.path}: fetch failed ({exc})")
                    continue
                if not rows:
                    notes.append(f"{endpoint.path}: returned no rows")
                    continue
                table = demas_api.rows_to_table(rows)
                target = self.settings.demas_dir / _slug(endpoint.path)
                target.mkdir(parents=True, exist_ok=True)
                import pyarrow.parquet as pq

                pq.write_table(
                    table, target / "part-00000.parquet", compression=self.settings.compression
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
                            json.dumps({"limit": page_size, "max_pages": max_pages}),
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
    from .inventory.families import schema_signature

    return schema_signature(field_names) == plan.schema_signature


def _year_from_path(catalog: Catalog, path: str) -> int | None:
    rows = catalog.query("SELECT year FROM file_facts WHERE path = ?", (path,))
    return int(rows[0]["year"]) if rows and rows[0]["year"] is not None else None


def _slug(path: str) -> str:
    return path.strip("/").replace("/", "__").replace("-", "_")
