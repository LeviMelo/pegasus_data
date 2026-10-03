"""TabNet's own tables, read over HTTP from ``tabnet.datasus.gov.br``.

TabNet is the Ministry's web tabulator. Its current territorial tables
(``cgi/territorio/*.cnv``) are what its population and health tabulations
classify municipalities by today, one table per classification. The TabWin
kits on the FTP tree carry older copies, one per publishing system, and they
contradict each other: ``BR_MACSAUD`` names a different health macroregion for
66% of municipalities depending on the system (ADR-0049). TabNet's
``br_macsaud.cnv`` is the single current answer.

TabNet is also an independent reference: a published tabulation can be
requested and compared with what this project computes from microdata
(``tabulate``). The population study the Ministry's tables divide by was
identified that way (OQ-12, 2026-10-03).
"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://tabnet.datasus.gov.br/cgi"

__all__ = ["BASE", "fetch_territorial", "tabulate"]


def fetch_territorial(name: str, cache_dir: str | Path, *, refresh: bool = False, timeout: float = 120.0) -> Path:
    """TabNet's current territorial table ``name`` (``br_macsaud``), cached.

    The file is the ``.CNV`` TabNet itself reads, kept byte for byte so it is
    parsed by the project's one CNV parser.
    """
    target = Path(cache_dir) / f"{name.lower()}.cnv"
    if target.is_file() and not refresh:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"{BASE}/territorio/{name.lower()}.cnv"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = response.read()
    if not data or data.lstrip()[:1] == b"<":
        raise FileNotFoundError(f"TabNet has no territorial table at {url}")
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    return target


def tabulate(definition: str, *, row: str, files: list[str], column: str = "--Não-Ativa--",
             measure: str = "População_residente", timeout: float = 180.0) -> list[tuple[str, str]]:
    """One TabNet tabulation as (row label, value) pairs, total row included.

    ``definition`` is the form's ``.def`` path (``ibge/cnv/popsvs2024br.def``);
    ``row``, ``column``, ``measure`` and ``files`` are the form's own option
    values. TabNet reads the form in Latin-1.
    """
    fields = [("Linha", row), ("Coluna", column), ("Incremento", measure)]
    fields += [("Arquivos", f) for f in files]
    fields += [("formato", "prn"), ("mostre", "Mostra")]
    body = urllib.parse.urlencode(fields, encoding="latin-1").encode()
    request = urllib.request.Request(f"{BASE}/tabcgi.exe?{definition}", data=body, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        page = response.read().decode("latin-1")
    pre = re.search(r"<PRE>(.*?)</PRE>", page, re.S | re.I)
    if pre is None:
        raise RuntimeError(f"TabNet returned no table for {definition}")
    out: list[tuple[str, str]] = []
    for line in html.unescape(pre.group(1)).splitlines()[1:]:
        parts = [p.strip().strip('"') for p in line.split(";")]
        if len(parts) >= 2 and parts[0]:
            out.append((parts[0], parts[-1]))
    return out
