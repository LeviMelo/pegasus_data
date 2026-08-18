"""Distributional semantic detectors (D5).

The prior implementation classified a field by matching each value against a
regex. The regex was correct; the failure was categorical. SINAN's ``NU_IDADE``
stores ``A020`` — DATASUS unit-prefixed age, where the letter is the unit
(**A**nos / **M**eses / **D**ias / **H**oras) and the digits are the value, so
``A020`` = 20 years. And ``A02.0`` is a valid ICD-10 code (salmonellosis). The
collision is **real and unresolvable per value**; validating against the genuine
14,197-row CID table would not fix it, because ``A020`` is a legitimate code.

So classification consumes the whole value distribution. For this collision the
separating statistics are:

* **first-character entropy** — an age field draws from ~4 symbols (≈2 bits at
  most, usually far less); a diagnosis field draws from ~20 chapters (≈4 bits);
* **numeric-tail density and contiguity** — age tails are a dense run 0–120;
  diagnosis tails are sparse;
* **distinct count** — age ≈ 100–130; a real ``DIAG_PRINC`` was measured at 443
  and 693 distinct values by schema generation.

Every verdict carries a confidence **and the statistics that produced it**, so a
consumer can re-audit the classification without re-reading the raw file.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..config import UF_CODES, UF_NUMERIC
from .accumulators import FieldStats

ICD10_RE = re.compile(r"^[A-TV-Z][0-9][0-9AB](?:\.?[0-9A-TV-Z]{0,4})?$", re.I)
DATASUS_AGE_RE = re.compile(r"^[AMDH]\d{2,3}$", re.I)
DATE8_RE = re.compile(r"^\d{8}$")
DATE6_RE = re.compile(r"^\d{6}$")
CPF_RE = re.compile(r"^\d{11}$")
CNPJ_RE = re.compile(r"^\d{14}$")
CNS_RE = re.compile(r"^\d{15}$")

#: Sentinels DATASUS writes for "no date". Recognised so a date field is not
#: penalised for containing them — but never nulled here (§13: sentinel handling
#: is per-field and ledger-driven).
DATE_SENTINELS = frozenset({"00000000", "99999999", "0", "00/00/0000", "        "})

MONEY_NAME_HINT = re.compile(r"VAL|VLR|VALOR|CUSTO|US_|_TOT|FINANC", re.I)
AGE_NAME_HINT = re.compile(r"IDADE|IDAD|NU_IDADE|ANOS|COD_IDADE", re.I)
DIAG_NAME_HINT = re.compile(r"DIAG|CID|CAUSA|CAUS|MORTE|OBITO", re.I)
GEO_NAME_HINT = re.compile(r"MUNIC|MUN_|CODMUN|CO_MUN|IBGE|RESID|MOV", re.I)
PROC_NAME_HINT = re.compile(r"PROC|PRIPAL|SECUND|SIGTAP|ATO_PROF", re.I)
DATE_NAME_HINT = re.compile(r"^DT|_DT|DATA|DATE|NASC|INTER|SAIDA|EMISS|COMPET|ANOMES", re.I)


@dataclass(slots=True)
class ReferenceSets:
    """Authoritative code universes, sourced from the tree rather than assumed.

    Populated from ``catalog.code_tables`` after the TAB kits are ingested, each
    entry carrying its own provenance. When a set is missing the detectors fall
    back to structural evidence only and say so in the recorded confidence, which
    is the difference between "checked and matched" and "looked plausible".
    """

    icd10: frozenset[str] = frozenset()
    municipalities: frozenset[str] = frozenset()
    procedures: frozenset[str] = frozenset()
    cnes: frozenset[str] = frozenset()
    provenance: dict[str, str] = field(default_factory=dict)

    @property
    def has_icd10(self) -> bool:
        return len(self.icd10) > 1000

    @property
    def has_municipalities(self) -> bool:
        return len(self.municipalities) > 1000

    @property
    def has_procedures(self) -> bool:
        return len(self.procedures) > 500


@dataclass(slots=True)
class SemanticVerdict:
    semantic_type: str
    confidence: float
    evidence: dict[str, Any]

    def evidence_json(self) -> str:
        return json.dumps(self.evidence, ensure_ascii=False, sort_keys=True, default=str)


def _rate(stats: FieldStats, predicate: Callable[[str], bool]) -> float:
    """Share of *observed mass* (not of distinct values) matching a predicate."""
    total = sum(count for _, count in stats.top_values)
    if not total:
        return 0.0
    hit = sum(count for value, count in stats.top_values if predicate(value))
    return hit / total


def _membership(stats: FieldStats, universe: frozenset[str], *, normalise: Callable[[str], str] | None = None) -> float:
    total = sum(count for _, count in stats.top_values)
    if not total or not universe:
        return 0.0
    hit = 0
    for value, count in stats.top_values:
        key = normalise(value) if normalise else value
        if key in universe:
            hit += count
    return hit / total


# --------------------------------------------------------------- the detectors


def _numeric_tail_shape(stats: FieldStats, prefix_len: int = 1) -> tuple[float | None, int | None, int | None]:
    """Density and range of the numeric tail after a fixed-length prefix.

    Mirrors ``FieldStats.tail_*`` but for the all-digit encoding, where the unit
    is a leading digit rather than a leading letter.
    """
    from collections import Counter

    from .accumulators import robust_tail_span

    tails: Counter[int] = Counter()
    for value, count in stats.top_values:
        tail = value[prefix_len:]
        if len(value) < prefix_len + 1 or not tail.isdigit():
            continue
        tails[int(tail)] += count
    if len(tails) < 5:
        return None, None, None
    lo, hi, inside = robust_tail_span(tails)
    if lo is None or hi is None:
        return None, None, None
    span = hi - lo + 1
    return (inside / span if span else None), lo, hi


def detect_datasus_age(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    """Unit-prefixed age, in both encodings DATASUS actually uses.

    * **Letter-prefixed** ``A020`` — unit ∈ {A(nos), M(eses), D(ias), H(oras)}.
      This is the encoding that collides with ICD-10, and the collision is why
      per-value regexes cannot settle it (D5).
    * **Digit-prefixed** ``4020`` — unit ∈ {1 hora, 2 dia, 3 mês, 4 ano}, used by
      SINAN's ``NU_IDADE_N``. Measured in ``DENGBR16``: 195 distinct values, top
      values ``4020``/``4019``/``4021``. No ICD collision here, but it is equally
      not a "numeric measure": summing it or taking its mean is meaningless.
    """
    letter_rate = _rate(stats, lambda v: bool(DATASUS_AGE_RE.match(v)))
    total_first = max(1, sum(stats.first_char_hist.values()))

    if letter_rate >= 0.5:
        unit_chars = {c.upper() for c in stats.first_char_hist}
        unit_share = sum(
            c for ch, c in stats.first_char_hist.items() if ch.upper() in {"A", "M", "D", "H"}
        ) / total_first
        evidence = {
            "rule": "datasus_age_letter_prefixed",
            "pattern_match_rate": round(letter_rate, 4),
            "first_char_entropy": round(stats.first_char_entropy, 4),
            "unit_symbols": sorted(unit_chars)[:8],
            "unit_char_share": round(unit_share, 4),
            "distinct_count": stats.distinct_count,
            "tail_density": stats.tail_density,
            "tail_range": [stats.tail_min, stats.tail_max],
            "name_hint": bool(AGE_NAME_HINT.search(name)),
            "separates_from_icd10_because": (
                "an age field draws its leading symbol from ~4 units while a diagnosis field "
                "draws from ~20 ICD chapters, and an age tail is a dense contiguous run"
            ),
        }
        confidence = 0.4
        if unit_share > 0.95:
            confidence += 0.15
        if stats.first_char_entropy < 2.2:
            confidence += 0.15
        if stats.tail_density is not None and stats.tail_density > 0.5:
            confidence += 0.15
        if stats.tail_max is not None and stats.tail_max <= 130:
            confidence += 0.05
        if 40 <= stats.distinct_count <= 400:
            confidence += 0.05
        if AGE_NAME_HINT.search(name):
            confidence += 0.05
        return SemanticVerdict("datasus_age", min(confidence, 0.97), evidence)

    # Digit-prefixed variant.
    digit_rate = _rate(stats, lambda v: len(v) == 4 and v.isdigit() and v[0] in "1234")
    if digit_rate < 0.8 or not AGE_NAME_HINT.search(name):
        return None
    density, lo, hi = _numeric_tail_shape(stats, 1)
    if density is None or density < 0.4:
        return None
    unit_digits = sorted({v[0] for v, _ in stats.top_values if len(v) == 4 and v.isdigit()})
    evidence = {
        "rule": "datasus_age_digit_prefixed",
        "pattern_match_rate": round(digit_rate, 4),
        "unit_digits": unit_digits,
        "unit_legend": {"1": "hora", "2": "dia", "3": "mes", "4": "ano"},
        "tail_density": round(density, 4),
        "tail_range": [lo, hi],
        "distinct_count": stats.distinct_count,
        "name_hint": True,
        "note": "coded age; not additive and not a mean-able quantity without decoding the unit",
    }
    confidence = 0.55 + (0.2 if density > 0.7 else 0.1) + (0.1 if len(unit_digits) <= 4 else 0.0)
    return SemanticVerdict("datasus_age", min(confidence, 0.95), evidence)


def detect_icd10(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    """ICD-10 code: regex match **plus** chapter spread, sparse tail, membership."""
    match_rate = _rate(stats, lambda v: bool(ICD10_RE.match(v)))
    if match_rate < 0.5:
        return None
    membership = _membership(stats, refs.icd10, normalise=lambda v: v.replace(".", "").upper())
    evidence = {
        "rule": "icd10",
        "pattern_match_rate": round(match_rate, 4),
        "first_char_entropy": round(stats.first_char_entropy, 4),
        "distinct_letters": len(stats.first_char_hist),
        "distinct_count": stats.distinct_count,
        "tail_density": stats.tail_density,
        "cid_table_membership": round(membership, 4) if refs.has_icd10 else None,
        "cid_table_provenance": refs.provenance.get("icd10"),
        "name_hint": bool(DIAG_NAME_HINT.search(name)),
    }
    # A dense contiguous tail over few leading letters is an age field wearing an
    # ICD-shaped costume. Refuse the verdict outright rather than out-score it.
    if (
        stats.tail_density is not None
        and stats.tail_density > 0.5
        and stats.first_char_entropy < 2.2
        and len(stats.first_char_hist) <= 6
    ):
        evidence["rejected_because"] = "dense_contiguous_tail_over_few_leading_symbols"
        return None
    confidence = 0.35
    if stats.first_char_entropy >= 2.5:
        confidence += 0.15
    if len(stats.first_char_hist) >= 10:
        confidence += 0.1
    if stats.distinct_count > 120:
        confidence += 0.1
    if refs.has_icd10:
        confidence += 0.25 * membership
    if DIAG_NAME_HINT.search(name):
        confidence += 0.05
    return SemanticVerdict("icd10", min(confidence, 0.99), evidence)


def detect_municipality(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    """IBGE municipality code: 6 or 7 digits, valid UF prefix, table membership."""
    six = _rate(stats, lambda v: len(v) == 6 and v.isdigit())
    seven = _rate(stats, lambda v: len(v) == 7 and v.isdigit())
    if max(six, seven) < 0.7:
        return None
    width = 6 if six >= seven else 7
    uf_ok = _rate(stats, lambda v: v[:2] in UF_NUMERIC if len(v) >= 2 else False)
    membership = _membership(stats, refs.municipalities, normalise=lambda v: v[:6])
    evidence = {
        "rule": "municipality",
        "code_width": width,
        "width_match_rate": round(max(six, seven), 4),
        "uf_prefix_rate": round(uf_ok, 4),
        "distinct_count": stats.distinct_count,
        "ibge_table_membership": round(membership, 4) if refs.has_municipalities else None,
        "ibge_table_provenance": refs.provenance.get("municipalities"),
        "name_hint": bool(GEO_NAME_HINT.search(name)),
    }
    if uf_ok < 0.7:
        return None
    confidence = 0.4 + 0.2 * uf_ok
    if refs.has_municipalities:
        confidence += 0.3 * membership
    elif GEO_NAME_HINT.search(name):
        confidence += 0.08
    if stats.distinct_count > 50:
        confidence += 0.05
    return SemanticVerdict(f"municipality_code_{width}", min(confidence, 0.98), evidence)


def detect_uf(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    alpha = _rate(stats, lambda v: v.upper() in UF_CODES)
    numeric = _rate(stats, lambda v: v.zfill(2) in UF_NUMERIC)
    if max(alpha, numeric) < 0.9 or stats.distinct_count > 30:
        return None
    kind = "uf_alpha" if alpha >= numeric else "uf_numeric"
    return SemanticVerdict(
        kind,
        0.9,
        {
            "rule": "uf",
            "alpha_rate": round(alpha, 4),
            "numeric_rate": round(numeric, 4),
            "distinct_count": stats.distinct_count,
        },
    )


def detect_date(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    """Dates, with sentinel handling — and competência told apart from a date."""
    d8 = _rate(stats, lambda v: bool(DATE8_RE.match(v)))
    d6 = _rate(stats, lambda v: bool(DATE6_RE.match(v)))
    sentinel = _rate(stats, lambda v: v in DATE_SENTINELS)
    if d8 >= 0.6:
        plausible = _rate(stats, lambda v: bool(DATE8_RE.match(v)) and 1900 <= int(v[:4]) <= 2100)
        if plausible < 0.5:
            # Could be DDMMYYYY rather than YYYYMMDD.
            plausible = _rate(stats, lambda v: bool(DATE8_RE.match(v)) and 1900 <= int(v[4:]) <= 2100)
            order = "DDMMYYYY"
        else:
            order = "YYYYMMDD"
        if plausible < 0.5:
            return None
        return SemanticVerdict(
            "date",
            min(0.55 + 0.4 * plausible, 0.97),
            {
                "rule": "date8",
                "order": order,
                "match_rate": round(d8, 4),
                "plausible_year_rate": round(plausible, 4),
                "sentinel_rate": round(sentinel, 4),
                "sentinels_observed": sorted(
                    {v for v, _ in stats.top_values if v in DATE_SENTINELS}
                ),
                "name_hint": bool(DATE_NAME_HINT.search(name)),
            },
        )
    if d6 >= 0.8:
        month_ok = _rate(stats, lambda v: bool(DATE6_RE.match(v)) and 1 <= int(v[4:6]) <= 12)
        year_ok = _rate(stats, lambda v: bool(DATE6_RE.match(v)) and 1900 <= int(v[:4]) <= 2100)
        if month_ok > 0.9 and year_ok > 0.9:
            return SemanticVerdict(
                "competencia",
                0.9,
                {
                    "rule": "yyyymm",
                    "match_rate": round(d6, 4),
                    "month_valid_rate": round(month_ok, 4),
                    "distinct_count": stats.distinct_count,
                },
            )
    return None


def detect_money(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    """Money: name hint + continuous positive distribution + declared decimals."""
    if stats.numeric_rate < 0.9 or stats.numeric_max is None:
        return None
    name_hit = bool(MONEY_NAME_HINT.search(name))
    declared_decimals = (stats.decimals or 0) >= 1
    if not name_hit and not declared_decimals:
        return None
    if stats.numeric_min is not None and stats.numeric_min < 0 and not name_hit:
        return None
    continuous = stats.distinct_count > 50
    evidence = {
        "rule": "money",
        "name_hint": name_hit,
        "declared_decimals": stats.decimals,
        "numeric_rate": round(stats.numeric_rate, 4),
        "range": [stats.numeric_min, stats.numeric_max],
        "distinct_count": stats.distinct_count,
        "continuous": continuous,
    }
    confidence = 0.35 + (0.3 if name_hit else 0.0) + (0.2 if declared_decimals else 0.0) + (0.1 if continuous else 0.0)
    return SemanticVerdict("money", min(confidence, 0.95), evidence)


def detect_procedure(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    """Procedure code: fixed-width numeric, high cardinality, table membership."""
    widths = [w for w, c in stats.lengths.items() if c > 0]
    if not widths:
        return None
    dominant_width = max(stats.lengths, key=lambda w: stats.lengths[w])
    if dominant_width not in (8, 10):
        return None
    fixed = stats.lengths[dominant_width] / max(1, sum(stats.lengths.values()))
    digits = stats.digit_rate
    if fixed < 0.9 or digits < 0.9:
        return None
    membership = _membership(stats, refs.procedures)
    evidence = {
        "rule": "procedure",
        "dominant_width": dominant_width,
        "fixed_width_rate": round(fixed, 4),
        "digit_rate": round(digits, 4),
        "distinct_count": stats.distinct_count,
        "procedure_table_membership": round(membership, 4) if refs.has_procedures else None,
        "procedure_table_provenance": refs.provenance.get("procedures"),
        "name_hint": bool(PROC_NAME_HINT.search(name)),
    }
    confidence = 0.35
    if stats.distinct_count > 100:
        confidence += 0.1
    if PROC_NAME_HINT.search(name):
        confidence += 0.1
    if refs.has_procedures:
        confidence += 0.4 * membership
    else:
        evidence["note"] = "no procedure table loaded; verdict rests on structure alone"
    return SemanticVerdict("procedure_code", min(confidence, 0.97), evidence)


def detect_personal_identifier(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    """CPF / CNS / CNPJ shaped fields.

    Worth a first-class verdict for a reason the brief does not anticipate: the
    2001–2007 APAC files recovered from the ``.exe`` archives carry
    ``APA_CPFPCN`` — an eleven-digit patient CPF — in a public download. A
    consumer preparing a federal deliverable needs that surfaced, not silently
    normalised into a column called "identifier".
    """
    upper = name.upper()
    cpf = _rate(stats, lambda v: bool(CPF_RE.match(v)))
    cns = _rate(stats, lambda v: bool(CNS_RE.match(v)))
    cnpj = _rate(stats, lambda v: bool(CNPJ_RE.match(v)))
    if max(cpf, cns, cnpj) < 0.8:
        return None
    if stats.distinct_count < 20 or (stats.non_null and stats.distinct_count / stats.non_null < 0.05):
        return None  # a low-cardinality 11-digit field is a code, not an identity
    if cpf >= max(cns, cnpj) and ("CPF" in upper or cpf > 0.95):
        kind, rate = "cpf", cpf
    elif cns >= cnpj and ("CNS" in upper or "CARTAO" in upper or cns > 0.95):
        kind, rate = "cns", cns
    elif "CGC" in upper or "CNPJ" in upper or cnpj > 0.95:
        kind, rate = "cnpj", cnpj
    else:
        return None
    return SemanticVerdict(
        f"personal_identifier_{kind}",
        min(0.5 + 0.4 * rate, 0.95),
        {
            "rule": "personal_identifier",
            "kind": kind,
            "match_rate": round(rate, 4),
            "distinct_count": stats.distinct_count,
            "distinct_ratio": round(stats.distinct_count / stats.non_null, 4) if stats.non_null else None,
            "name_hint": kind.upper() in upper,
            "privacy_note": (
                "direct personal identifier present in a public DATASUS download; "
                "handle under the applicable data-protection rules"
            ),
        },
    )


def detect_categorical(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    """Low-cardinality field.

    Deliberately *not* a decoded verdict. Whether this is ``sex`` or ``race`` or
    ``bill type`` is a question for the dictionary, and a low-cardinality field
    with no dictionary entry is reported as ``categorical_undecoded`` — an
    actionable gap with a coverage penalty, never a guess (§13).
    """
    if stats.distinct_count == 0 or stats.distinct_count > 60:
        return None
    return SemanticVerdict(
        "categorical_undecoded",
        0.5,
        {
            "rule": "categorical",
            "distinct_count": stats.distinct_count,
            "top_values": stats.top_values[:20],
            "note": "awaiting a .CNV/.DEF mapping; not decoded",
        },
    )


def detect_constant(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    """A column that is present, non-null, and carries exactly one value.

    Worth its own verdict because of a trap measured in SIH-RD 2020: the brief
    predicts ``DIAG_SECUN`` is *absent* from the 113-column generation, so a query
    for it would return empty. Measured, it is **present with 3,784 non-null rows
    all equal to ``'0000'``** — the column was retained and retired, and secondary
    diagnoses moved to ``DIAGSEC1..9``. That is strictly worse than absence: an
    empty result at least looks odd, whereas thousands of ``0000`` look like data
    and will be counted.
    """
    if stats.distinct_count != 1 or stats.non_null == 0:
        return None
    value = stats.top_values[0][0] if stats.top_values else ""
    looks_retired = bool(re.fullmatch(r"[09]+", value)) or value in {"", "0"}
    return SemanticVerdict(
        "constant_column",
        0.9,
        {
            "rule": "constant",
            "value": value,
            "non_null": stats.non_null,
            "looks_like_retired_placeholder": looks_retired,
            "warning": (
                "single-valued column: treat as carrying no information for this "
                "schema generation, and check whether it was superseded by another field"
            ),
        },
    )


def detect_establishment(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    """CNES establishment code: 7 digits, zero-padded, with a name or table hint."""
    seven = _rate(stats, lambda v: len(v) == 7 and v.isdigit())
    if seven < 0.9:
        return None
    upper = name.upper()
    name_hit = "CNES" in upper or "CODUNI" in upper or "UNIDADE" in upper
    membership = _membership(stats, refs.cnes)
    if not name_hit and not refs.cnes:
        return None
    return SemanticVerdict(
        "cnes_establishment",
        min(0.55 + (0.15 if name_hit else 0.0) + 0.3 * membership, 0.97),
        {
            "rule": "cnes",
            "width_match_rate": round(seven, 4),
            "name_hint": name_hit,
            "cnes_table_membership": round(membership, 4) if refs.cnes else None,
            "cnes_table_provenance": refs.provenance.get("cnes"),
            "distinct_count": stats.distinct_count,
        },
    )


def detect_numeric_measure(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    """A quantity, as opposed to a numeric-looking code.

    Zero padding is the discriminator: ``0303140151`` is a procedure code and
    ``4820`` is a value. A measure that is silently treated as a code (or the
    reverse) is the sort of error that survives all the way into a published rate.
    """
    if stats.numeric_rate < 0.95 or stats.distinct_count <= 60:
        return None
    if stats.leading_zero_rate > 0.05:
        return None
    # A quantity varies in width — 7, 56, 1234. A column where hundreds of
    # distinct values all occupy exactly the same five-plus digits is an
    # identifier: a municipality code, a CNES, a procedure. Letting a measure
    # verdict win there is how a code ends up summed.
    if len(stats.lengths) == 1 and next(iter(stats.lengths)) >= 5:
        return None
    return SemanticVerdict(
        "numeric_measure",
        0.6,
        {
            "rule": "numeric_measure",
            "numeric_rate": round(stats.numeric_rate, 4),
            "leading_zero_rate": round(stats.leading_zero_rate, 4),
            "range": [stats.numeric_min, stats.numeric_max],
            "mean": stats.numeric_mean,
            "distinct_count": stats.distinct_count,
        },
    )


def detect_free_text(stats: FieldStats, refs: ReferenceSets, name: str) -> SemanticVerdict | None:
    if stats.non_null == 0:
        return None
    ratio = stats.distinct_count / stats.non_null
    mean_len = (
        sum(w * c for w, c in stats.lengths.items()) / max(1, sum(stats.lengths.values()))
    )
    if ratio > 0.5 and mean_len > 8 and stats.alpha_rate > 0.3:
        return SemanticVerdict(
            "free_text",
            0.6,
            {
                "rule": "free_text",
                "distinct_ratio": round(ratio, 4),
                "mean_length": round(mean_len, 2),
                "alpha_rate": round(stats.alpha_rate, 4),
            },
        )
    return None


#: Order matters: the specific detectors run before the generic ones, and the
#: age/ICD pair runs before anything that would swallow either.
DETECTORS: tuple[Callable[[FieldStats, ReferenceSets, str], SemanticVerdict | None], ...] = (
    detect_constant,
    detect_datasus_age,
    detect_uf,
    detect_personal_identifier,
    detect_icd10,
    detect_municipality,
    detect_establishment,
    detect_date,
    detect_procedure,
    detect_money,
    detect_categorical,
    detect_numeric_measure,
    detect_free_text,
)


def classify(
    stats: FieldStats,
    *,
    refs: ReferenceSets | None = None,
    name: str | None = None,
    detectors: Sequence[Callable[[FieldStats, ReferenceSets, str], SemanticVerdict | None]] = DETECTORS,
) -> SemanticVerdict:
    """Run every detector and return the best-supported verdict.

    All candidate verdicts are kept in the evidence, so the record shows not only
    what was decided but what else was considered and why it lost.
    """
    refs = refs or ReferenceSets()
    field_name = name or stats.name
    candidates: list[SemanticVerdict] = []
    for detector in detectors:
        try:
            verdict = detector(stats, refs, field_name)
        except Exception as exc:  # a detector must never take down a profile run
            candidates.append(
                SemanticVerdict("detector_error", 0.0, {"rule": detector.__name__, "error": str(exc)})
            )
            continue
        if verdict is not None:
            candidates.append(verdict)
    real = [c for c in candidates if c.semantic_type != "detector_error"]
    if not real:
        return SemanticVerdict(
            "unknown",
            0.0,
            {
                "rule": "none_matched",
                "distinct_count": stats.distinct_count,
                "numeric_rate": round(stats.numeric_rate, 4),
                "considered": [c.evidence.get("rule") for c in candidates],
            },
        )
    best = max(real, key=lambda c: c.confidence)
    best.evidence["alternatives"] = [
        {"semantic_type": c.semantic_type, "confidence": round(c.confidence, 3)}
        for c in real
        if c is not best
    ]
    return best
