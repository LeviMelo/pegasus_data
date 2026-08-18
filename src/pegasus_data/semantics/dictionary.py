"""Dictionary assembly: merge sources by authority, record conflicts, never guess.

Supply chain, highest authority first (§6.3):

1. ``.CNV`` — TabNet's code→category maps.
2. ``.DEF`` — the only artifact that states what a column is officially called,
   and which codelist decodes it.
3. ``.DBF`` lookup tables inside kits — CID-10, procedures, establishments.
4. Dictionary PDFs — lower confidence, never overriding ``.CNV``/``.DEF``.
5. DEMAS API metadata — machine-readable, above PDF harvesting.
6. Inference — lowest authority, always flagged ``source='inferred'``.

**Codelists are not columns.** ``SEXO.CNV`` says ``1 → Masculino`` without saying
which column uses it, and one codelist legitimately serves several columns
(``MUNICBR`` decodes both ``MUNIC_RES`` and ``MUNIC_MOV``). So codes are stored
once per *codelist* and attached to fields through ``field_codelists``, which the
``.DEF`` files populate. Flattening codelists into columns instead would
duplicate 5,600 municipality rows per column and — worse — would report a
"conflict" every time two unrelated codelists both define the code ``1``, burying
the real disagreements under a million false ones.

**Conflicts between sources are recorded, never silently resolved.** A genuine
disagreement — two sources claiming different labels for the same code *in the
same codelist* — produces a ``dictionary_conflicts`` row carrying both claims and
both provenances, because a conflict is a finding.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..catalog.store import Catalog, utcnow
from .cnv_parser import CnvFile
from .tabkit import ParsedKit

#: Authority ranking. A lower number wins a disagreement; the loser is still
#: written to ``dictionary_conflicts`` so nothing is lost.
SOURCE_AUTHORITY: dict[str, int] = {
    "manual": 0,
    "cnv": 1,
    "def": 2,
    "dbf_lookup": 3,
    "demas_api": 4,
    "pdf": 5,
    "inferred": 6,
}

DEFAULT_CONFIDENCE: dict[str, float] = {
    "manual": 1.0,
    "cnv": 0.95,
    "def": 0.9,
    "dbf_lookup": 0.9,
    "demas_api": 0.7,
    "pdf": 0.5,
    "inferred": 0.3,
}


@dataclass(slots=True)
class DictionaryEntry:
    """One ``value → label`` claim, scoped to a codelist and carrying its source."""

    system: str | None
    value_raw: str
    value_label: str
    source: str
    source_ref: str
    confidence: float
    value_group: str | None = None       # the codelist this claim belongs to
    field_name: str | None = None        # set only when a source names the column
    family_id: str | None = None
    schema_signature_scope: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None

    @property
    def authority(self) -> int:
        return SOURCE_AUTHORITY.get(self.source, 99)

    def key(self) -> tuple[str | None, str | None, str | None, str, str | None]:
        # Validity is part of the identity: the same codelist name carries
        # different mappings in different eras, and both are correct.
        return (self.system, self.value_group, self.field_name, self.value_raw, self.valid_from)


@dataclass(slots=True)
class CodelistBinding:
    """A statement that a column is decoded by a codelist, and who said so."""

    system: str | None
    field_name: str
    codelist: str
    source: str
    source_ref: str
    confidence: float
    family_id: str | None = None


def _norm_member(ref: str) -> str:
    return PurePosixPath(ref.replace("\\", "/")).name.upper()


def _codelist_name(member: str) -> str:
    return PurePosixPath(member.replace("\\", "/")).stem.upper()


def entries_from_kit(
    kit: ParsedKit,
) -> tuple[list[DictionaryEntry], list[CodelistBinding], list[tuple[str, str, str, str]]]:
    """Turn a parsed kit into codelist entries, field bindings, and rules."""
    entries: list[DictionaryEntry] = []
    bindings: list[CodelistBinding] = []
    rules: list[tuple[str, str, str, str]] = []

    for parsed_def in kit.defs.values():
        for v in parsed_def.variables:
            if not v.lookup_ref:
                continue
            bindings.append(
                CodelistBinding(
                    system=kit.system,
                    field_name=v.field_name,
                    codelist=_codelist_name(v.lookup_ref),
                    source="def",
                    source_ref=f"{parsed_def.source_ref}:{v.line_no}",
                    confidence=DEFAULT_CONFIDENCE["def"],
                )
            )

    for member, cnv in kit.cnvs.items():
        codelist = _codelist_name(member)
        for code, (label, category) in cnv.mapping().items():
            entries.append(
                DictionaryEntry(
                    system=kit.system,
                    value_raw=code,
                    value_label=label,
                    source="cnv",
                    source_ref=f"{kit.kit_path}!{member}:{category.line_no}",
                    confidence=DEFAULT_CONFIDENCE["cnv"],
                    value_group=codelist,
                    valid_from=kit.valid_from,
                    valid_to=kit.valid_to,
                )
            )
        for expression, category in cnv.rules():
            rules.append(
                (codelist, expression, category.label, f"{kit.kit_path}!{member}:{category.line_no}")
            )

    for table_id, rows in kit.code_tables.items():
        for code, label, _extra in rows:
            if not code:
                continue
            entries.append(
                DictionaryEntry(
                    system=kit.system,
                    value_raw=code,
                    value_label=label,
                    source="dbf_lookup",
                    source_ref=f"{kit.kit_path}!{table_id}",
                    confidence=DEFAULT_CONFIDENCE["dbf_lookup"],
                    value_group=table_id,
                    valid_from=kit.valid_from,
                    valid_to=kit.valid_to,
                )
            )
    return entries, bindings, rules


def entries_from_loose_cnv(cnv: CnvFile, *, system: str | None) -> list[DictionaryEntry]:
    codelist = _codelist_name(cnv.name)
    return [
        DictionaryEntry(
            system=system,
            value_raw=code,
            value_label=label,
            source="cnv",
            source_ref=f"{cnv.source_ref}:{category.line_no}",
            confidence=DEFAULT_CONFIDENCE["cnv"],
            value_group=codelist,
        )
        for code, (label, category) in cnv.mapping().items()
    ]


# --------------------------------------------------------------------- merging


def persist_entries(catalog: Catalog, entries: Sequence[DictionaryEntry]) -> dict[str, int]:
    """Insert entries, recording genuine conflicts instead of resolving silently.

    The incoming batch goes into a temp table and everything else is a join.
    Reading the whole ``dictionary`` into Python per kit was quadratic: the SIH
    and SINAN kits alone put roughly a million rows in, so by the third kit each
    call was scanning millions of rows to check a few thousand keys.
    """
    if not entries:
        return {"inserted": 0, "conflicts": 0}

    # Deduplicate within the batch first, highest authority winning, and note any
    # disagreement between two claims about the same code in the same codelist.
    conflicts: list[tuple[object, ...]] = []
    winners: dict[tuple[str | None, str | None, str | None, str, str | None], DictionaryEntry] = {}
    now = utcnow()
    for entry in entries:
        key = entry.key()
        prior = winners.get(key)
        if prior is None:
            winners[key] = entry
            continue
        if prior.value_label != entry.value_label:
            conflicts.append(
                (
                    entry.system, entry.value_group or entry.field_name, entry.value_raw,
                    prior.value_label, prior.source_ref,
                    entry.value_label, entry.source_ref, now,
                )
            )
        if entry.authority < prior.authority:
            winners[key] = entry

    payload = [
        (
            e.system, e.value_group, e.field_name, e.value_raw, e.value_label,
            e.family_id, e.schema_signature_scope, e.source, e.source_ref,
            e.confidence, e.valid_from, e.valid_to, e.authority,
        )
        for e in winners.values()
    ]

    with catalog.write() as conn:
        conn.execute("DROP TABLE IF EXISTS temp._incoming_dict")
        conn.execute(
            """
            CREATE TEMP TABLE _incoming_dict (
              system TEXT, value_group TEXT, field_name TEXT, value_raw TEXT,
              value_label TEXT, family_id TEXT, schema_signature_scope TEXT,
              source TEXT, source_ref TEXT, confidence REAL,
              valid_from TEXT, valid_to TEXT, authority INTEGER
            )
            """
        )
        conn.executemany(
            "INSERT INTO temp._incoming_dict VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", payload
        )
        conn.execute(
            "CREATE INDEX temp.ix_incoming ON _incoming_dict (system, value_group, field_name, value_raw)"
        )

        join = (
            "d.system IS i.system AND d.value_group IS i.value_group "
            "AND d.field_name IS i.field_name AND d.value_raw = i.value_raw "
            "AND d.valid_from IS i.valid_from"
        )
        # A stored claim that disagrees with an incoming one is a finding, kept
        # with both provenances whichever way the authority ranking falls.
        rows = conn.execute(
            f"""
            SELECT i.system, COALESCE(i.value_group, i.field_name), i.value_raw,
                   d.value_label, d.source_ref, i.value_label, i.source_ref
              FROM temp._incoming_dict i
              JOIN dictionary d ON {join}
             WHERE d.value_label IS NOT i.value_label
            """
        ).fetchall()
        conflicts.extend(tuple(r) + (now,) for r in rows)

        # An incoming claim only replaces a stored one of strictly worse authority.
        conn.execute(
            f"""
            DELETE FROM dictionary WHERE rowid IN (
                SELECT d.rowid FROM dictionary d JOIN temp._incoming_dict i ON {join}
                 WHERE i.authority <= CASE d.source
                        WHEN 'manual' THEN 0 WHEN 'cnv' THEN 1 WHEN 'def' THEN 2
                        WHEN 'dbf_lookup' THEN 3 WHEN 'demas_api' THEN 4
                        WHEN 'pdf' THEN 5 WHEN 'inferred' THEN 6 ELSE 99 END
            )
            """
        )
        inserted = conn.execute(
            f"""
            INSERT INTO dictionary (system, family_id, field_name, schema_signature_scope,
                value_raw, value_label, value_group, source, source_ref, confidence, valid_from, valid_to)
            SELECT i.system, i.family_id, i.field_name, i.schema_signature_scope,
                   i.value_raw, i.value_label, i.value_group, i.source, i.source_ref,
                   i.confidence, i.valid_from, i.valid_to
              FROM temp._incoming_dict i
             WHERE NOT EXISTS (SELECT 1 FROM dictionary d WHERE {join})
            """
        ).rowcount
        conn.executemany(
            """
            INSERT INTO dictionary_conflicts (system, field_name, value_raw, claim_a, source_a, claim_b, source_b, noted_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            conflicts,
        )
        conn.execute("DROP TABLE temp._incoming_dict")
    return {"inserted": max(0, inserted), "conflicts": len(conflicts)}


def persist_bindings(catalog: Catalog, bindings: Sequence[CodelistBinding]) -> int:
    return catalog.executemany(
        """
        INSERT INTO field_codelists (system, family_id, field_name, codelist, source, source_ref, confidence)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(system, family_id, field_name, codelist) DO UPDATE SET
            source=excluded.source, source_ref=excluded.source_ref, confidence=excluded.confidence
        """,
        [
            (b.system, b.family_id or "", b.field_name, b.codelist, b.source, b.source_ref, b.confidence)
            for b in bindings
        ],
    )


def persist_rules(
    catalog: Catalog, rules: Iterable[tuple[str, str, str, str]], *, system: str | None
) -> int:
    rows = [
        (
            system, codelist, expression, label, "cnv", source_ref,
            DEFAULT_CONFIDENCE["cnv"],
            "alphanumeric range with no known code universe to expand against",
        )
        for codelist, expression, label, source_ref in rules
    ]
    return catalog.executemany(
        """
        INSERT INTO dictionary_rules (system, field_name, expression, value_label, source, source_ref, confidence, reason)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def bind_codelists_to_fields(catalog: Catalog) -> int:
    """Populate ``field_codelists`` from every ``.DEF`` declaration seen so far."""
    rows = catalog.query(
        """
        SELECT DISTINCT system, field_name, lookup_ref, def_path
          FROM def_variables
         WHERE lookup_ref IS NOT NULL
        """
    )
    return catalog.executemany(
        """
        INSERT INTO field_codelists (system, family_id, field_name, codelist, source, source_ref, confidence)
        VALUES (?, '', ?, ?, 'def', ?, ?)
        ON CONFLICT(system, family_id, field_name, codelist) DO NOTHING
        """,
        [
            (
                r["system"], r["field_name"],
                PurePosixPath(str(r["lookup_ref"]).replace("\\", "/")).stem.upper(),
                str(r["def_path"]), DEFAULT_CONFIDENCE["def"],
            )
            for r in rows
        ],
    )


# --------------------------------------------------------------------- lookup


def codelists_for(catalog: Catalog, *, system: str | None, field_name: str) -> list[str]:
    """Codelists a ``.DEF`` binds to this field. Empty means genuinely unbound."""
    rows = catalog.query(
        """
        SELECT DISTINCT codelist FROM field_codelists
         WHERE field_name = ? AND (system IS ? OR system IS NULL OR ? IS NULL)
         ORDER BY confidence DESC, codelist
        """,
        (field_name, system, system),
    )
    return [str(r["codelist"]) for r in rows]


def lookup(
    catalog: Catalog,
    *,
    system: str | None,
    field_name: str,
    values: Sequence[str] | None = None,
    observed: dict[str, int] | None = None,
) -> dict[str, str]:
    """Resolve ``value → label`` for one field via its bound codelists.

    Where several codelists bind to the same field, they are usually **not in
    conflict**: TabNet offers a variable at several aggregation levels at once.
    ``DIAG_PRINC`` binds to the full CID-10 table *and* to ``CID10CAP``
    (21 chapters), ``CID10GRUPO`` (blocks) and the per-chapter lists; ``MUNIC_MOV``
    binds to ``MUNICBR`` and also to ``REGIAO``, ``UF``, ``CAPITAL`` and the health-
    region roll-ups.

    The one used for labelling is the **most granular**, chosen by distinct-label
    ratio: a 1:1 code→label table (CID-10 proper, ratio ≈ 1.0) beats a grouping
    that maps 14,000 codes onto 275 labels (ratio ≈ 0.02). Picking by row count
    instead would happily relabel a diagnosis as its chapter, or a municipality as
    its region. The coarser codelists stay reachable through
    :func:`codelist_values` and are reported by ``describe()`` as roll-ups, which
    is what §6.3's ``value_group`` is for.
    """
    codelists = codelists_for(catalog, system=system, field_name=field_name)
    direct = catalog.query(
        """
        SELECT value_raw, value_label, source FROM dictionary
         WHERE field_name = ? AND (system IS ? OR system IS NULL)
        """,
        (field_name, system),
    )
    best: dict[str, tuple[str, int]] = {}
    for row in direct:
        authority = SOURCE_AUTHORITY.get(row["source"], 99)
        current = best.get(row["value_raw"])
        if current is None or authority < current[1]:
            best[row["value_raw"]] = (row["value_label"], authority)

    granular = most_granular_codelist(catalog, codelists, system=system, observed=observed)
    if granular:
        for row in catalog.query(
            """
            SELECT value_raw, value_label, source FROM dictionary
             WHERE value_group = ? AND (system IS ? OR system IS NULL)
            """,
            (granular, system),
        ):
            if row["value_raw"] not in best:
                best[row["value_raw"]] = (row["value_label"], SOURCE_AUTHORITY.get(row["source"], 99))

    out = {k: v[0] for k, v in best.items()}
    if values is None:
        return out
    wanted = set(values)
    return {k: v for k, v in out.items() if k in wanted}


def codelist_stats(
    catalog: Catalog, codelists: Sequence[str], *, system: str | None = None
) -> list[dict[str, object]]:
    if not codelists:
        return []
    rows = catalog.query(
        f"""
        SELECT value_group,
               COUNT(*) AS codes,
               COUNT(DISTINCT value_label) AS labels
          FROM dictionary
         WHERE value_group IN ({','.join('?' * len(codelists))})
           AND (system IS ? OR system IS NULL)
         GROUP BY value_group
        """,
        [*codelists, system],
    )
    return [
        {
            "codelist": str(r["value_group"]),
            "codes": int(r["codes"]),
            "distinct_labels": int(r["labels"]),
            "granularity": int(r["labels"]) / max(1, int(r["codes"])),
        }
        for r in rows
    ]


def most_granular_codelist(
    catalog: Catalog,
    codelists: Sequence[str],
    *,
    system: str | None = None,
    observed: dict[str, int] | None = None,
) -> str | None:
    """Pick the codelist that best labels this field's *actual* values.

    Granularity alone is not enough. ``PROC_REA`` binds to ``TPROC`` (7,717
    procedures, ratio 0.61) and to ``GCARDIO`` (221 cardiac procedures, ratio
    1.00); ranking on ratio picks the cardiac subset and leaves 97% of procedures
    unlabelled. ``MUNIC_RES`` binds to ``MUNICBR`` (5,653 municipalities) and to
    ``DISTRFEDERAL`` (21 Brasília administrative regions), and the same mistake
    would label the whole country as Brasília.

    So when the observed value distribution is available it decides: the codelist
    covering the most observed mass wins, and granularity only breaks ties. That
    is a measurement, not a preference. Without observations the fallback ranks by
    absolute distinct-label count, which favours the comprehensive table over a
    specialised subset.
    """
    stats = codelist_stats(catalog, codelists, system=system)
    if not stats:
        return None
    if observed:
        total = sum(observed.values()) or 1
        for entry in stats:
            values = codelist_values(catalog, str(entry["codelist"]), system=system)
            entry["observed_coverage"] = (
                sum(count for value, count in observed.items() if value in values) / total
            )
        ranked = sorted(
            stats,
            key=lambda e: (
                -round(float(e.get("observed_coverage", 0.0)), 4),
                -float(e["granularity"]),
                -int(e["distinct_labels"]),
            ),
        )
        return str(ranked[0]["codelist"])
    ranked = sorted(stats, key=lambda e: (-int(e["distinct_labels"]), -float(e["granularity"])))
    return str(ranked[0]["codelist"])


def observed_values(
    catalog: Catalog, *, family_id: str, field_name: str, schema_signature: str
) -> dict[str, int]:
    rows = catalog.query(
        """
        SELECT value, count FROM value_frequencies
         WHERE family_id = ? AND field_name = ? AND schema_signature = ?
        """,
        (family_id, field_name, schema_signature),
    )
    return {str(r["value"]): int(r["count"]) for r in rows}


#: Semantic verdicts that justify binding a field to a reference code table even
#: where no ``.DEF`` names it. The binding rests on the detector's *measured*
#: membership rate in that table, and is recorded with ``source='semantic_match'``
#: so the weaker basis stays visible next to the ``.DEF``-sourced bindings.
SEMANTIC_CODELISTS: dict[str, tuple[str, ...]] = {
    "icd10": ("CID10",),
    "procedure_code": ("TPROC10", "TPROC"),
    "cnes_establishment": ("TCNESBR",),
    "municipality_code_6": ("MUNICBR",),
    "municipality_code_7": ("MUNICBR",),
}


def bind_by_semantic_type(catalog: Catalog) -> int:
    """Attach reference tables to fields the detectors identified.

    ``DIAG_PRINC`` is the motivating case: TabNet's ``.DEF`` binds it to the
    per-chapter CID lists but never to the complete 14,197-row ``CID10`` table,
    which is the only member that gives each code its own description. The
    detector measured that the column's values *are* in that table, so the
    binding is evidence-backed rather than assumed.
    """
    known = {
        str(r["value_group"])
        for r in catalog.query("SELECT DISTINCT value_group FROM dictionary WHERE value_group IS NOT NULL")
    }
    rows = catalog.query(
        """
        SELECT DISTINCT f.system, vp.field_name, vp.semantic_type, vp.semantic_confidence
          FROM variable_profiles vp
          JOIN families f ON f.family_id = vp.family_id
         WHERE vp.semantic_type IN ({})
        """.format(",".join("?" * len(SEMANTIC_CODELISTS))),
        list(SEMANTIC_CODELISTS),
    )
    payload: list[tuple[object, ...]] = []
    for row in rows:
        for candidate in SEMANTIC_CODELISTS.get(str(row["semantic_type"]), ()):
            if candidate not in known:
                continue
            payload.append(
                (
                    row["system"], "", row["field_name"], candidate, "semantic_match",
                    f"detector:{row['semantic_type']}",
                    float(row["semantic_confidence"] or 0.0),
                )
            )
            break
    return catalog.executemany(
        """
        INSERT INTO field_codelists (system, family_id, field_name, codelist, source, source_ref, confidence)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(system, family_id, field_name, codelist) DO NOTHING
        """,
        payload,
    )


def rollups_for(
    catalog: Catalog,
    *,
    system: str | None,
    field_name: str,
    observed: dict[str, int] | None = None,
) -> list[dict[str, object]]:
    """Every codelist bound to a field, with how coarse each one is.

    This is the answer to "what else can this column be grouped by" — the
    chapter/block/list hierarchies TabNet publishes alongside the raw codes, and
    which of them was chosen for labelling.
    """
    codelists = codelists_for(catalog, system=system, field_name=field_name)
    stats = codelist_stats(catalog, codelists, system=system)
    if not stats:
        return []
    granular = most_granular_codelist(catalog, codelists, system=system, observed=observed)
    total = sum(observed.values()) if observed else 0
    out: list[dict[str, object]] = []
    for entry in stats:
        row = {
            "codelist": entry["codelist"],
            "codes": entry["codes"],
            "distinct_labels": entry["distinct_labels"],
            "granularity": round(float(entry["granularity"]), 4),
            "used_for_labels": entry["codelist"] == granular,
        }
        if total:
            values = codelist_values(catalog, str(entry["codelist"]), system=system)
            row["observed_coverage"] = round(
                sum(c for v, c in (observed or {}).items() if v in values) / total, 4
            )
        out.append(row)
    return sorted(out, key=lambda r: (-float(r.get("observed_coverage", 0.0)), -int(r["distinct_labels"])))


def codelist_values(catalog: Catalog, codelist: str, *, system: str | None = None) -> dict[str, str]:
    rows = catalog.query(
        "SELECT value_raw, value_label FROM dictionary WHERE value_group = ? AND (system IS ? OR ? IS NULL)",
        (codelist, system, system),
    )
    return {str(r["value_raw"]): str(r["value_label"]) for r in rows}


def apply_rules(
    catalog: Catalog, *, system: str | None, field_name: str, values: Sequence[str]
) -> dict[str, str]:
    """Resolve values that only an unexpanded range covers, e.g. ``A00-B99``."""
    codelists = codelists_for(catalog, system=system, field_name=field_name) or [field_name]
    placeholders = ",".join("?" * len(codelists))
    rows = catalog.query(
        f"SELECT expression, value_label FROM dictionary_rules WHERE field_name IN ({placeholders})",
        codelists,
    )
    out: dict[str, str] = {}
    for row in rows:
        for part in str(row["expression"]).split(","):
            part = part.strip()
            if "-" not in part:
                continue
            lo, _, hi = part.partition("-")
            n = max(len(lo), len(hi))
            for value in values:
                if value in out:
                    continue
                if lo <= value[:n].ljust(n) <= hi:
                    out[value] = str(row["value_label"])
    return out


def coverage_for_field(
    catalog: Catalog,
    *,
    family_id: str,
    field_name: str,
    schema_signature: str,
    labels: dict[str, str] | None = None,
) -> tuple[float, int, int]:
    """Fraction of *observed* values in a field that have a dictionary entry.

    Weighted by observed mass, not by distinct value: a field whose top three
    codes cover 99.8% of rows and whose long tail is undecoded is not 40% covered,
    it is 99.8% covered, and reporting the former would misdirect the work.
    """
    rows = catalog.query(
        """
        SELECT value, count FROM value_frequencies
         WHERE family_id = ? AND field_name = ? AND schema_signature = ?
        """,
        (family_id, field_name, schema_signature),
    )
    if not rows:
        return 0.0, 0, 0
    if labels is None:
        system_row = catalog.query("SELECT system FROM families WHERE family_id = ?", (family_id,))
        system = system_row[0]["system"] if system_row else None
        observed = {str(r["value"]): int(r["count"]) for r in rows}
        labels = lookup(catalog, system=system, field_name=field_name, observed=observed)
        unresolved = [r["value"] for r in rows if r["value"] not in labels]
        if unresolved:
            labels = {
                **labels,
                **apply_rules(catalog, system=system, field_name=field_name, values=unresolved),
            }
    total = sum(int(r["count"]) for r in rows)
    covered = sum(int(r["count"]) for r in rows if r["value"] in labels)
    decoded_distinct = sum(1 for r in rows if r["value"] in labels)
    return (covered / total if total else 0.0), len(rows), decoded_distinct


def match_codelist_by_name(catalog: Catalog, field_name: str) -> list[str]:
    """Codelists whose name matches a field name — a *candidate*, not a binding.

    ``SEXO`` → ``SEXO.CNV`` is obvious and correct; the point of returning
    candidates rather than applying them is that "obvious" is how a wrong mapping
    gets in without provenance. Promote one with :func:`persist_bindings` using
    ``source='name_match'`` so the weaker basis stays visible.
    """
    rows = catalog.query("SELECT DISTINCT value_group FROM dictionary WHERE value_group IS NOT NULL")
    upper = field_name.upper()
    out = []
    for row in rows:
        group = str(row["value_group"])
        if group == upper or fnmatch.fnmatch(group, f"{upper}*") or fnmatch.fnmatch(upper, f"{group}*"):
            out.append(group)
    return sorted(out)


def conflicts_report(catalog: Catalog, limit: int = 50) -> list[dict[str, object]]:
    rows = catalog.query(
        """
        SELECT system, field_name AS scope, value_raw, claim_a, source_a, claim_b, source_b
          FROM dictionary_conflicts ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    )
    return [dict(r) for r in rows]
