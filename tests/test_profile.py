"""Accumulators, drift, and the distributional detectors that fix D5."""

from __future__ import annotations

import pyarrow as pa
import pytest

from pegasus_data.decode.base import FieldMeta
from pegasus_data.profile.accumulators import FieldAccumulator, robust_tail_span
from pegasus_data.profile.detectors import ReferenceSets, classify


def _stats(name: str, values: list[str], *, physical="C", width=None, decimals=None):
    acc = FieldAccumulator(FieldMeta(name=name, physical_type=physical, width=width, decimals=decimals))
    acc.add_array(pa.array(values, type=pa.string()))
    return acc.stats()


class TestAccumulator:
    def test_counts_nulls_and_blanks_but_not_sentinels(self):
        stats = _stats("F", ["A", "", "   ", None, "9"])
        assert stats.non_null == 2  # 'A' and '9'
        assert stats.nulls == 3
        assert dict(stats.top_values)["9"] == 1

    def test_first_character_entropy(self):
        one_symbol = _stats("F", ["A01", "A02", "A03", "A04"])
        many_symbols = _stats("F", [f"{c}01" for c in "ABCDEFGHIJKLMNOP"])
        assert one_symbol.first_char_entropy == 0.0
        assert many_symbols.first_char_entropy > 3.5

    def test_leading_zero_rate_separates_codes_from_measures(self):
        code = _stats("P", ["0303140151", "0407020015"])
        measure = _stats("V", ["1234", "5678"])
        assert code.leading_zero_rate == 1.0
        assert measure.leading_zero_rate == 0.0

    def test_numeric_summary_ignores_non_numeric_tokens(self):
        """A diagnosis column full of 'O48' must not abort the whole profile."""
        stats = _stats("D", ["O48", "123", "456"])
        assert stats.numeric_min == 123 and stats.numeric_max == 456

    def test_robust_tail_span_trims_sentinels(self):
        from collections import Counter

        tails = Counter(dict.fromkeys(range(0, 90), 100))
        tails[999] = 1  # a lone 'unknown' sentinel
        lo, hi, inside = robust_tail_span(tails)
        assert hi < 999 and lo == 0 and inside == 90


class TestDetectors:
    def test_letter_prefixed_age_is_not_icd(self):
        """SINAN's A020 collides with ICD-10 A02.0; only the distribution separates them."""
        values = [f"A{i:03d}" for i in range(0, 100)] * 3
        verdict = classify(_stats("NU_IDADE", values))
        assert verdict.semantic_type == "datasus_age"
        assert verdict.evidence["first_char_entropy"] == 0.0
        assert verdict.evidence["tail_density"] > 0.9

    def test_digit_prefixed_age_is_not_a_measure(self):
        """SINAN's NU_IDADE_N stores 4020 = 20 years; summing it is meaningless."""
        values = [f"4{i:03d}" for i in range(1, 90)] * 5
        verdict = classify(_stats("NU_IDADE_N", values))
        assert verdict.semantic_type == "datasus_age"
        assert verdict.evidence["unit_legend"]["4"] == "ano"

    def test_diagnosis_is_icd(self):
        values = [f"{c}{i:02d}" for c in "ABCDEFGHIJKLMNOPQRST" for i in range(0, 40, 3)]
        verdict = classify(_stats("DIAG_PRINC", values))
        assert verdict.semantic_type == "icd10"
        assert verdict.evidence["distinct_letters"] >= 10

    def test_icd_verdict_is_refused_on_a_dense_tail_over_few_letters(self):
        values = [f"A{i:03d}" for i in range(0, 110)]
        verdict = classify(_stats("SOMEFIELD", values))
        assert verdict.semantic_type != "icd10"

    def test_membership_in_the_real_cid_table_raises_confidence(self):
        values = ["A00", "A001", "B99"] * 40
        bare = classify(_stats("DIAG_PRINC", values))
        with_table = classify(
            _stats("DIAG_PRINC", values),
            refs=ReferenceSets(
                icd10=frozenset({"A00", "A001", "B99"} | {f"Z{i:03d}" for i in range(1200)}),
                provenance={"icd10": "TAB_SIH.zip!CID10"},
            ),
        )
        assert with_table.confidence > bare.confidence
        assert with_table.evidence["cid_table_provenance"] == "TAB_SIH.zip!CID10"

    def test_constant_column_is_flagged(self):
        """SIH-RD 2020 keeps DIAG_SECUN, filled entirely with '0000'."""
        verdict = classify(_stats("DIAG_SECUN", ["0000"] * 500))
        assert verdict.semantic_type == "constant_column"
        assert verdict.evidence["looks_like_retired_placeholder"] is True

    def test_procedure_code_beats_numeric_measure(self):
        values = [f"03{i:08d}" for i in range(300)]
        verdict = classify(_stats("PROC_REA", values))
        assert verdict.semantic_type == "procedure_code"

    def test_money_uses_declared_decimals(self):
        values = [str(1000 + i) for i in range(200)]
        verdict = classify(_stats("VAL_TOT", values, physical="N", width=10, decimals=2))
        assert verdict.semantic_type == "money"
        assert verdict.evidence["declared_decimals"] == 2

    def test_municipality_requires_a_valid_uf_prefix(self):
        # 31 is Minas Gerais; 30 and 99 are not IBGE UF codes at all.
        good = classify(_stats("MUNIC_RES", [f"31{i:04d}" for i in range(100)]))
        bad = classify(_stats("MUNIC_RES", [f"99{i:04d}" for i in range(100)]))
        assert good.semantic_type == "municipality_code_6"
        assert bad.semantic_type != "municipality_code_6"

    def test_a_fixed_width_numeric_code_is_never_a_measure(self):
        """Summing a municipality code produces a number, and the number is nonsense."""
        verdict = classify(_stats("SOME_CODE", [f"35{i:04d}" for i in range(200)]))
        assert verdict.semantic_type != "numeric_measure"

    def test_low_cardinality_without_a_dictionary_is_a_gap_not_a_verdict(self):
        verdict = classify(_stats("SEXO", ["1", "2", "9"] * 50))
        assert verdict.semantic_type == "categorical_undecoded"
        assert "awaiting" in verdict.evidence["note"]

    def test_personal_identifier_is_surfaced(self):
        """APAC's public 2002 files carry an 11-digit patient CPF."""
        verdict = classify(_stats("APA_CPFPCN", [f"{i:011d}" for i in range(500)]))
        assert verdict.semantic_type == "personal_identifier_cpf"
        assert "data-protection" in verdict.evidence["privacy_note"]

    def test_date_records_its_sentinels_without_nulling_them(self):
        values = [f"2020{m:02d}15" for m in range(1, 13)] * 5 + ["00000000"] * 3
        verdict = classify(_stats("DT_INTER", values))
        assert verdict.semantic_type == "date"
        assert "00000000" in verdict.evidence["sentinels_observed"]

    def test_every_verdict_carries_its_evidence(self):
        for values, name in [
            (["A020"] * 50, "NU_IDADE"),
            (["0000"] * 50, "X"),
            ([str(i) for i in range(500)], "N"),
        ]:
            verdict = classify(_stats(name, values))
            assert verdict.evidence and "rule" in verdict.evidence

    def test_unknown_is_an_honest_answer(self):
        verdict = classify(_stats("WEIRD", ["!!", "@@", "##", "$$"] * 20))
        assert verdict.semantic_type in {"unknown", "categorical_undecoded"}


class TestDrift:
    def test_never_reports_stable_at_n_equals_one(self, catalog):
        from pegasus_data.profile.drift import analyse_drift

        catalog.executemany(
            """INSERT INTO strata (stratum_id, system, series, year, file_count, schema_signature, sample_status)
               VALUES (?,?,?,?,?,?,'ok')""",
            [("s1", "SIHSUS", "RD", 1992, 1, "sigA")],
        )
        catalog.executemany(
            "INSERT INTO schemas (schema_signature, field_count, fields_json) VALUES (?,?,?)",
            [("sigA", 2, '["A","B"]')],
        )
        report = analyse_drift(catalog)[0]
        assert report.drift_status == "insufficient_evidence"

    def test_reports_drifting_when_signatures_differ(self, catalog):
        from pegasus_data.profile.drift import analyse_drift

        catalog.executemany(
            """INSERT INTO strata (stratum_id, system, series, year, file_count, schema_signature, sample_status)
               VALUES (?,?,?,?,?,?,'ok')""",
            [("s1", "SIHSUS", "RD", 1992, 1, "sigA"), ("s2", "SIHSUS", "RD", 2020, 1, "sigB")],
        )
        catalog.executemany(
            "INSERT INTO schemas (schema_signature, field_count, fields_json) VALUES (?,?,?)",
            [("sigA", 2, '["A","B"]'), ("sigB", 3, '["A","B","C"]')],
        )
        report = analyse_drift(catalog)[0]
        assert report.drift_status == "drifting"
        assert report.always_present == ["A", "B"]
        assert report.sometimes_present == ["C"]


@pytest.mark.parametrize("n", [0, 1, 5])
def test_classify_never_raises(n):
    assert classify(_stats("F", ["x"] * n)).semantic_type is not None
