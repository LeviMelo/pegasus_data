"""ICD column quality: measure the token rule, then report what fails (§6.5).

Rendering multi-valued ICD columns is settled in §5.7 and does not wait on this.
What this produces is a *configuration input* — the token rule each column needs
— and a *quality report*. Neither blocks anything, and the report is the point:
a consumer should be able to filter on data quality rather than discover it three
analyses later.

The classification below is deliberately five-way rather than valid/invalid.
``0000`` is not malformed — it is the sentinel SIH writes into ``DIAG_SECUN``
from the 113-column generation onward, and calling it "invalid" would hide that
the column is dead rather than dirty. A code that is syntactically perfect but
absent from the CID table for its vintage is a different finding again: usually
a real code from a later revision, which says the vintage window is wrong, not
the data.

Nothing here drops or nulls a value. Malformed entries are preserved and flagged
(§13), because a value that fails to parse is evidence about the source and
deleting it destroys the only record that it happened.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..catalog.store import Catalog

#: A dotless ICD-10 code: a letter, two digits, then an optional fourth
#: character. ``J189``, ``A419``, ``I10X`` — the trailing X is DATASUS padding a
#: three-character code to the field width, not a real subdivision.
ICD_CODE = re.compile(r"^[A-Z]\d{2}[0-9X]?$")

#: The dotted form, which appears in some transcriptions and in TabNet exports.
ICD_DOTTED = re.compile(r"^[A-Z]\d{2}\.\d$")

#: ICD-**9**: three or four digits, or an E/V-prefixed code. SIM ran on CID-9
#: until 1996 and the FTP tree still carries those years under SIM/CID9, so a
#: numeric CAUSABAS is a valid code from the previous revision — not a
#: structurally broken one. Calling it malformed hides a revision boundary and
#: invites someone to "clean" real data away.
ICD9_CODE = re.compile(r"^[EV]?\d{3,4}$")

#: Values that mean "nothing here" rather than a code.
SENTINELS = frozenset({"0000", "000", "00", "0", "", "----", "....", "9999"})

#: Candidate separators for a multi-valued cell. Which one a column uses is
#: *measured*, not ranked: SIM's LINHAA fields use ``*`` and its ATESTADO field
#: uses ``/``, and a fixed try-order picks the wrong one for whichever column it
#: meets second.
DELIMITERS = ("*", "/", ";", "|", ",")


@dataclass(slots=True)
class ColumnQuality:
    """What one ICD-classified column actually contains."""

    system: str
    field_name: str
    values_examined: int = 0
    single_valid: int = 0
    several_codes: int = 0
    malformed: int = 0
    sentinel: int = 0
    valid_but_absent: int = 0
    #: Valid under a *different* ICD revision — numeric CID-9 in a column bound
    #: to CID-10. Counted apart from malformed because the fix is a second
    #: reference table, not a data repair.
    other_revision: int = 0
    inferred_rule: dict[str, object] = field(default_factory=dict)
    examples_malformed: list[str] = field(default_factory=list)
    examples_absent: list[str] = field(default_factory=list)

    @property
    def multi_valued(self) -> bool:
        return self.several_codes > 0

    def as_dict(self) -> dict[str, object]:
        total = self.values_examined or 1
        return {
            "system": self.system,
            "field_name": self.field_name,
            "values_examined": self.values_examined,
            "single_valid": self.single_valid,
            "several_codes": self.several_codes,
            "malformed": self.malformed,
            "sentinel": self.sentinel,
            "valid_but_absent": self.valid_but_absent,
            "other_revision": self.other_revision,
            "pct_single_valid": round(self.single_valid / total, 4),
            "pct_malformed": round(self.malformed / total, 4),
            "pct_sentinel": round(self.sentinel / total, 4),
            "multi_valued": self.multi_valued,
            "inferred_rule": self.inferred_rule,
            "examples_malformed": self.examples_malformed[:5],
            "examples_absent": self.examples_absent[:5],
        }


def _normalise(value: str) -> str:
    return value.strip().upper()


def infer_token_rule(values: Sequence[str]) -> dict[str, object]:
    """Work out how a column packs several codes into one cell.

    A delimiter, when one is present in a meaningful share of values, beats fixed
    width — and it has to, because SIM's causal-chain fields are ``*``-separated
    four-character codes and splitting those on width alone shifts every token
    after the first by one character.

    Returns an empty rule for a column that holds one code per cell. That is not
    a failure to infer; it is the answer.
    """
    populated = [v for v in (_normalise(x) for x in values) if v and v not in SENTINELS]
    if not populated:
        return {}
    # Pick the delimiter that actually appears most, rather than the first one
    # in a fixed list. ATESTADO contains a stray '*' often enough to pass a
    # threshold while '/' is its real separator, and try-order alone got it wrong.
    coverage = {d: sum(1 for v in populated if d in v) for d in DELIMITERS}
    # Every separator that carries weight, not just the heaviest. ATESTADO uses
    # '/' and '*' in the same cell, and choosing one of them leaves the other
    # inside a token, which then fails every shape check.
    carried = [d for d, n in coverage.items() if n / len(populated) >= 0.02]
    delimiter = "".join(sorted(carried, key=lambda d: -coverage[d]))
    carrying = max(coverage.values(), default=0)
    if delimiter and carrying / len(populated) >= 0.05:
        pattern = f"[{re.escape(delimiter)}]"
        segments = [part for v in populated for part in re.split(pattern, v) if part.strip()]
        if segments:
            widths: dict[int, int] = {}
            for seg in segments:
                widths[len(seg)] = widths.get(len(seg), 0) + 1
            best_width, hits = max(widths.items(), key=lambda kv: kv[1])
            if hits / len(segments) >= 0.8:
                return {"delimiter": delimiter, "width": best_width}
            return {"delimiter": delimiter}

    # No delimiter: is any value longer than one code?
    lengths = {len(v) for v in populated}
    if lengths <= {3, 4}:
        return {}
    multiples = [v for v in populated if len(v) >= 8 and len(v) % 4 == 0]
    if len(multiples) / len(populated) >= 0.05:
        return {"width": 4}
    return {}


def measure_column(
    values: Sequence[str],
    *,
    system: str,
    field_name: str,
    known_codes: Mapping[str, str] | None = None,
    rule: Mapping[str, object] | None = None,
    other_revision_bound: bool = False,
) -> ColumnQuality:
    """Classify every observed value of one ICD column.

    ``other_revision_bound`` says a table for the *other* ICD revision is bound
    to this column. When it is, a numeric CID-9 code is not a curiosity to be
    counted apart — it is a valid, labellable value, and reporting it as
    anything else overstates how much of the column is unusable.
    """
    out = ColumnQuality(system=system, field_name=field_name)
    token_rule = dict(rule) if rule else infer_token_rule(values)
    out.inferred_rule = token_rule
    delimiter = token_rule.get("delimiter")
    width = int(token_rule.get("width") or 0)

    for raw in values:
        if raw is None:
            continue
        value = _normalise(str(raw))
        out.values_examined += 1
        if value in SENTINELS:
            out.sentinel += 1
            continue

        if delimiter:
            tokens = [
                t.strip()
                for t in re.split(f"[{re.escape(str(delimiter))}]", value)
                if t.strip()
            ]
        elif width and len(value) > width and len(value) % width == 0:
            tokens = [value[i : i + width].strip() for i in range(0, len(value), width)]
            tokens = [t for t in tokens if t]
        else:
            tokens = [value]

        # Presence in a bound table outranks shape. Shape is a heuristic and a
        # narrow one: SIM writes CID-9 as three or four digits, SIH writes it as
        # six (065099 is "650 - Parto normal"), and no regex should have to know
        # that. If a codelist bound to this column decodes the token, the token
        # is valid — that is proof, not inference.
        decoded = (
            known_codes is not None
            and bool(tokens)
            and all(t in known_codes for t in tokens)
        )
        shapes_ok = [bool(ICD_CODE.match(t) or ICD_DOTTED.match(t)) for t in tokens]
        looks_icd9 = bool(tokens) and all(ICD9_CODE.match(t) for t in tokens)

        if not decoded and not all(shapes_ok) and looks_icd9:
            # ICD-9 shaped, and either no table is bound for that revision or it
            # does not carry this code. Counted apart from malformed because the
            # fix is a reference table, not a data repair.
            out.other_revision += 1
            if not other_revision_bound:
                continue
        elif not decoded and not all(shapes_ok):
            out.malformed += 1
            if len(out.examples_malformed) < 20:
                out.examples_malformed.append(value)
            continue

        if len(tokens) > 1:
            out.several_codes += 1
        else:
            out.single_valid += 1
        if known_codes is not None and not decoded:
            out.valid_but_absent += 1
            if len(out.examples_absent) < 20:
                out.examples_absent.append(value)
    return out


def measure_icd_columns(
    catalog: Catalog,
    lake_root: str | Path | None = None,
    *,
    codelist: str = "CID10",
    systems: Sequence[str] | None = None,
) -> list[ColumnQuality]:
    """Measure every column the catalog has bound to an ICD codelist.

    Reads observed values from ``value_frequencies``, which is a sample of the
    top values per field rather than the full column. That is the right trade:
    it is enough to settle the token rule and to surface the shapes present, and
    the alternative is decoding the whole lake to answer a configuration question.
    The sample bias is stated in the report rather than hidden — rare malformed
    values are exactly what a top-N sample under-counts.
    """
    def _known_for(system: str, groups: Sequence[str]) -> Mapping[str, str] | None:
        """Every table bound to the field, merged.

        A column whose *classification* changed needs all of its vintages here or
        the measurement reports real codes as broken. SIM's CAUSABAS is bound to
        CID10 and CID9WHO because the tree carries both — SIM/CID9 runs
        1979-1998 and SIM/CID10 runs 1996-2024 — and the merge is safe because
        the two code spaces are disjoint: numeric versus letter-prefixed, sharing
        exactly zero codes.
        """
        if lake_root is None:
            return None
        from ..persist.reference import read_reference_table

        merged: dict[str, str] = {}
        for group in groups:
            try:
                table = read_reference_table(lake_root, group, system=system)
            except FileNotFoundError:
                continue
            for code, lbl in zip(
                table.column("code").to_pylist(), table.column("label").to_pylist(), strict=True
            ):
                if code is not None:
                    merged.setdefault(str(code), str(lbl))
        return merged or None

    clause, params = "", []
    if systems:
        clause = f" AND fa.system IN ({','.join('?' * len(systems))})"
        params = list(systems)

    rows = catalog.query(
        f"""
        SELECT fa.system AS system, fc.field_name AS field_name
          FROM field_codelists fc
          JOIN families fa ON fa.system = fc.system
         WHERE fc.codelist = ?{clause}
         GROUP BY fa.system, fc.field_name
        """,
        [codelist, *params],
    )
    out: list[ColumnQuality] = []
    for r in rows:
        values = [
            str(v["value"])
            for v in catalog.query(
                "SELECT value FROM value_frequencies WHERE field_name = ? "
                "AND value IS NOT NULL ORDER BY count DESC LIMIT 5000",
                (r["field_name"],),
            )
        ]
        if not values:
            continue
        system = str(r["system"])
        field_name = str(r["field_name"])
        bound = [
            str(b["codelist"])
            for b in catalog.query(
                "SELECT DISTINCT codelist FROM field_codelists WHERE system = ? AND field_name = ?",
                (system, field_name),
            )
        ] or [codelist]
        out.append(
            measure_column(
                values,
                system=system,
                field_name=field_name,
                known_codes=_known_for(system, bound),
                other_revision_bound=any("CID9" in b.upper() for b in bound),
            )
        )
    return sorted(out, key=lambda q: (-q.values_examined, q.field_name))


def persist_token_rules(catalog: Catalog, measured: Sequence[ColumnQuality]) -> int:
    """Write inferred token rules into the variable dictionary, as ``inferred``.

    Never overwrites a curated entry: a rule someone asserted in ``curation/``
    outranks one measured here, which is the whole point of the authority order.
    A measured rule fills a gap; it does not win an argument.
    """
    import json

    written = 0
    for q in measured:
        if not q.inferred_rule:
            continue
        existing = catalog.query(
            "SELECT source, token_rule FROM variable_docs WHERE system = ? AND field_name = ?",
            (q.system, q.field_name),
        )
        if existing and existing[0]["source"] != "inferred" and existing[0]["token_rule"]:
            continue
        reasoning = (
            f"measured over {q.values_examined} observed values of {q.field_name}: "
            f"{q.several_codes} carried several codes, {q.single_valid} a single code, "
            f"{q.malformed} were malformed and {q.sentinel} were sentinels"
        )
        catalog.execute(
            """
            INSERT INTO variable_docs (system, field_name, code_system, codelist,
                multi_valued, token_rule, source, source_ref, asserted_by, asserted_at, reasoning)
            VALUES (?,?,'external','CID10',?,?,'inferred','pegasus-data icd-quality',
                    'pegasus_data', datetime('now'), ?)
            ON CONFLICT(system, field_name) DO UPDATE SET
                multi_valued=excluded.multi_valued, token_rule=excluded.token_rule,
                reasoning=excluded.reasoning, asserted_at=excluded.asserted_at
            """,
            (q.system, q.field_name, int(q.multi_valued), json.dumps(q.inferred_rule), reasoning),
        )
        written += 1
    return written


#: Below this share of structurally valid codes, a binding is not weak evidence
#: — it is the wrong table. A real ICD column is overwhelmingly ICD-shaped.
SUSPECT_BINDING_THRESHOLD = 0.10


def flag_suspect_bindings(catalog: Catalog, measured: Sequence[ColumnQuality]) -> int:
    """Record columns whose bound codelist does not fit what they contain.

    The distributional detectors bind on shape, and shape is not identity: IBGE's
    ``IDADE`` column holds age-band codes like ``2559`` and ``1524``, which look
    numeric-and-short exactly the way an ICD-9 code does, so it was bound to
    CID10 at 0.35 confidence and matched essentially nothing.

    A near-zero match rate is a *finding*, not a coverage problem, and the two
    need different responses — one wants a better table, the other wants the
    binding removed. Saying so is the point; the binding is left in place for a
    person to adjudicate, exactly as a prefix contradiction is.
    """
    flagged = 0
    for q in measured:
        if not q.values_examined:
            continue
        valid = (q.single_valid + q.several_codes) / q.values_examined
        if valid >= SUSPECT_BINDING_THRESHOLD:
            continue
        flagged += 1
        catalog.note_question(
            f"semantics.suspect_icd_binding:{q.system}.{q.field_name}",
            area="semantics",
            question=(
                f"{q.system}.{q.field_name} is bound to an ICD codelist but only "
                f"{valid:.1%} of its {q.values_examined} sampled values are ICD-shaped "
                f"({q.malformed} malformed, {q.other_revision} matching the ICD-9 shape). "
                f"Examples: {q.examples_malformed[:3]}"
            ),
            verification_procedure=(
                "Read the field's record layout. If it is not a diagnosis column, delete "
                "the binding (it came from a distributional detector, which matches on "
                "shape rather than meaning). If it is, find the classification it really "
                "uses — a numeric column may be ICD-9 rather than ICD-10."
            ),
            blocking=f"labelling {q.field_name} correctly",
        )
    return flagged
