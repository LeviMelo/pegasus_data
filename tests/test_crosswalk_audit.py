from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.audit_crosswalk import audit


def test_audit_detects_overlaps_with_different_window_boundaries(tmp_path) -> None:
    path = tmp_path / "overlap.parquet"
    pq.write_table(
        pa.table(
            {
                "source_code": ["CNES1", "CNES1", "CNES2"],
                "target_code": ["CNPJ1", "CNPJ2", "CNPJ1"],
                "valid_from": ["202001", "202006", "202003"],
                "valid_to": ["202012", "202105", "202004"],
            }
        ),
        path,
    )
    result = audit(path)
    assert result["ambiguous_source_windows"] == 0
    assert result["ambiguous_source_pairwise_overlaps"] == 1
    assert result["reverse_multi_source_windows"] == 0
    assert result["reverse_multi_source_pairwise_overlaps"] == 1
