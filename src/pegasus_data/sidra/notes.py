"""What a SIDRA table's numbers rest on: the census universe, or a sample (ADR-0206).

A cell of a sample-estimated table looks exactly like a count: table 10061 (adults by schooling × age × sex × colour)
is "Dados dos Resultados preliminares da amostra, estimados a partir de áreas de ponderação preliminares", while 9606 and
9952 are "Dados do Universo". Only IBGE's note says which, and the API of aggregates (`/agregados/<t>/metadados`) does not
carry the notes.

**Where the notes are.** IBGE publishes them in `desctabapi.aspx?c=<t>` and in the table page's own JSON
(`sidra.ibge.gov.br/Ajax/JSon/Tabela/1/<t>`, its `Notas`), both behind a Cloudflare challenge that answers 403 ("Just a
moment...") to a non-browser client: the project's transport (httpx) and `curl` with its own agent are refused (measured
2026-10-24). The library does not disguise itself to pass a bot check, so it cannot read notes on its own.

**What it knows instead, in order:**

1. ``declared``: ``curation/sidra/notes.yml`` holds, per table, the ``basis`` its note states (``universe`` or ``sample``,
   or one per census in ``by_period``) with IBGE's passage verbatim (``evidence``), the day it was read and the table's own
   "última atualização";
2. ``precision variables``: a table whose variables include a coefficient of variation or a confidence interval is
   estimated from a sample (IBGE publishes precision only for estimates): ``sample``;
3. otherwise ``unknown``, said with the reason, never assumed to be a count.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..semantics.epoch import curated

__all__ = ["BASES", "NOTES_URL", "basis", "declared_notes"]

BASES = ("universe", "sample")
#: Words of a variable name that make it a precision measure (folded: upper case, no accents)
PRECISION_WORDS = ("COEFICIENTE DE VARIACAO", "INTERVALO DE CONFIANCA")


#: Where IBGE publishes a table's notes (read in a browser; `notes.yml` cites it)
NOTES_URL = "https://apisidra.ibge.gov.br/desctabapi.aspx?c={table}"


@curated(rooted=True)
def declared_notes(root: Path | None = None) -> dict[int, dict[str, Any]]:
    """``curation/sidra/notes.yml`` by table, checked: every entry has ``read`` (the day the note was read) and either a
    ``basis`` in `BASES` with ``evidence`` (IBGE's passage that states it, verbatim), a ``by_period`` mapping (period →
    basis, for a table whose note gives each census its own basis) with its ``evidence``, or ``basis: unknown`` with
    ``why``."""
    from ..config import curation_root
    from ..semantics.curation import read_yaml

    base = root or curation_root()
    entries = (read_yaml(base / "sidra" / "notes.yml", missing_ok=True) or {}).get("tables") or {}
    out: dict[int, dict[str, Any]] = {}
    for key, entry in entries.items():
        table = int(key)
        if not entry.get("read"):
            raise ValueError(f"sidra/notes.yml {table}: no `read` date")
        by_period = {str(k): v for k, v in (entry.get("by_period") or {}).items()}
        if by_period:
            if any(v not in BASES for v in by_period.values()) or not entry.get("evidence"):
                raise ValueError(f"sidra/notes.yml {table}: by_period takes {BASES} per period and needs `evidence`")
        elif entry.get("basis") in BASES:
            if not entry.get("evidence"):
                raise ValueError(f"sidra/notes.yml {table}: basis {entry['basis']!r} needs IBGE's passage as `evidence`")
        elif entry.get("basis") == "unknown":
            if not entry.get("why"):
                raise ValueError(f"sidra/notes.yml {table}: basis unknown needs `why`")
        else:
            raise ValueError(f"sidra/notes.yml {table}: basis {entry.get('basis')!r} is not one of {BASES}, by_period or unknown")
        out[table] = {**entry, "by_period": by_period}
    return out


def basis(table: int, registry: Any = None, period: Any = None) -> dict[str, Any]:
    """What ``table``'s numbers rest on: ``basis`` (``universe``, ``sample``, ``mixed`` or ``unknown``), ``from``
    (``declared``, ``precision variables`` or ``nothing``), ``evidence`` (IBGE's passage, the variable, or why nothing is
    known), ``by_period`` (when the note gives each period its own) and ``source`` (where and when it was read).
    ``period`` picks one period of a table whose basis changes with it; ``registry`` (a `Registry`) is read for the
    precision variables."""
    from ..textenc import fold

    entry = declared_notes().get(int(table))
    source = f"{NOTES_URL.format(table=int(table))}, read {entry['read']}" if entry else None
    if entry is not None and (entry["by_period"] or entry.get("basis") in BASES):
        by_period = entry["by_period"]
        if by_period:
            value = by_period.get(str(period)) if period is not None else None
            chosen = value or (by_period[next(iter(by_period))] if len(set(by_period.values())) == 1 else "mixed")
        else:
            chosen = entry["basis"]
        return {"basis": chosen, "from": "declared", "evidence": entry["evidence"], "by_period": by_period or None,
                "source": source}
    if registry is not None:
        precision = [v["name"] for v in registry.variables(int(table)) if any(w in fold(v["name"]) for w in PRECISION_WORDS)]
        if precision:
            return {"basis": "sample", "from": "precision variables", "evidence": precision[0], "by_period": None,
                    "source": source}
    why = entry["why"] if entry else ("IBGE's notes are behind a bot check the library does not pass; declare them in "
                                      f"curation/sidra/notes.yml from {NOTES_URL.format(table=int(table))} read in a browser")
    return {"basis": "unknown", "from": "nothing", "evidence": why, "by_period": None, "source": source}
