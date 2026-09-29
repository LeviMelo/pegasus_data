## 2026-08-23 — The distributed artifact is a separate correctness boundary

*Split from docs/history/FINDINGS.md §3q (first) on 2026-09-28; text unchanged.*

## 3q. The artifact is a separate correctness boundary (2026-08-23)

A repository import and an installed-wheel import are different systems. The
first distribution audit found a direct `numpy` import that metadata provided
only transitively, and current PEP 639 tooling rejected the old license
classifier once the project adopted an SPDX expression. Neither issue was
visible in the runtime suite.

The release boundary is now executable. `verify_distribution.py` compares all
SQL, YAML, JSON and Parquet package data in both wheel and sdist with the source
tree, validates the resource manifest's byte counts and SHA-256 digests, checks
the license, version and CLI entry point, and rejects local databases, caches
and source archives. CI rebuilds a wheel from the sdist so the source archive is
not merely present but sufficient.

The first clean-room acceptance run installed
`pegasus_data-0.1.0a1-py3-none-any.whl` outside the repository. The import
resolved inside that environment's `site-packages`; all seven manifest
resources, 116 curated YAML files and `catalog/schema.sql` loaded; the CLI help
rendered; and an offline `plan("SIH-RD", period=2024, geography="AL")` resolved
from the shipped source map without a catalog or fact download. The sdist then
rebuilt an independently verified generic wheel.

Distribution version is authoritative in `pyproject.toml`; runtime
`__version__` reads installed metadata. Publication remains a deliberate
external action through a release-triggered, OIDC-backed PyPI workflow.
