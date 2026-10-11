"""BNAFAR / Hórus medicine stock (DEMAS ``daf/estoque-medicamentos-bnafar-horus``), read by filter, never in bulk.

The endpoint holds each lot's CURRENT stock position (one row per establishment x product x lot, dated by its last report;
measured 2026-10-10: no lot appears at two dates, and a past month holds only lots not reported since), not a history:
it answers "what stock is where now", never a series (0.1 to 10 million rows, no total
count, offsets slow when deep: docs/evaluation/2026-10-10-demas-source-assessment.md), so nothing here pages the table:
a reader names a CATMAT code and a month (and optionally a state) and gets that slice, kept in
``<root>/registries/bnafar`` (a past month does not change).

A BNAFAR product is a CATMAT *item with its unit of supply*: ``BR0268123U0042`` is item 268123 (levotiroxina 50 mcg) in
supply unit U0042 (comprimido), and the filter takes that string whole (no prefix match). The catalogue (Compras.gov.br
``modulo-material``, the open CATMAT) publishes the items of a PDM (the drug) but not the national unit codes, so
:func:`products` forms the candidate codes from the catalogue's items and the unit suffixes read from BNAFAR's own rows
(`SOLID_ORAL`), and asks BNAFAR for one row of each (cached, negative answers too): the item codes are the catalogue's,
the pairs that exist are BNAFAR's.

A stock row is a lot's quantity at its last report. :func:`monthly` groups rows by the month of that last report, which
is NOT the stock in that month: a past month holds only the lots not reported since (a gap, never a series).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from ..config import DEMAS_BASE_URL

ENDPOINT = "/daf/estoque-medicamentos-bnafar-horus"
CATMAT_BASE = "https://dadosabertos.compras.gov.br/modulo-material"
#: Drugs and medicines (CATMAT group 65, class 6505).
CATMAT_CLASS = 6505
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
PAGE = 1000
#: Seconds between two requests to either host.
INTERVAL = 1.1

#: The columns kept (the rest of a row is the establishment's address, telephone and e-mail).
COLUMNS = ("codigo_uf", "uf", "codigo_municipio", "municipio", "codigo_cnes", "data_posicao_estoque", "codigo_catmat",
           "descricao_produto", "quantidade_estoque", "numero_lote", "data_validade", "tipo_produto",
           "sigla_programa_saude", "sigla_sistema_origem")

_last = [0.0]
_client: list[httpx.Client] = []


def _cache(root: str | Path | None) -> Path:
    from ..config import load_settings

    path = Path(root or load_settings().root) / "registries" / "bnafar"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get(url: str, params: dict[str, Any], retries: int = 4) -> Any:
    """GET json, at most one request per INTERVAL, a browser User-Agent, backoff on 429/5xx and timeouts."""
    if not _client:
        _client.append(httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=120,
                                    follow_redirects=True))
    for attempt in range(retries + 1):
        wait = INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            r = _client[0].get(url, params=params)
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            return r.json()
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == retries:
                raise
            time.sleep(5 * 2 ** attempt)
    raise AssertionError("unreachable")


def _fold(text: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c)).upper()


# --- CATMAT (the open catalogue) -------------------------------------------------------------------------------------

def _pages(path: str, params: dict[str, Any]) -> list[dict]:
    out, page = [], 1
    while True:
        d = _get(f"{CATMAT_BASE}/{path}", {**params, "pagina": page, "tamanhoPagina": 500})
        out += d.get("resultado") or []
        if page >= int(d.get("totalPaginas") or 0):
            return out
        page += 1


def catmat_pdms(root: str | Path | None = None, refresh: bool = False) -> list[dict]:
    """The PDMs (drugs) of the CATMAT medicines class: [{codigoPdm, nomePdm, statusPdm}] (1,901 on 2026-10-10)."""
    target = _cache(root) / "catmat_pdm.json"
    if target.is_file() and not refresh:
        return json.loads(target.read_text(encoding="utf8"))
    rows = [{k: r[k] for k in ("codigoPdm", "nomePdm", "statusPdm")}
            for r in _pages("3_consultarPdmMaterial", {"codigoClasse": CATMAT_CLASS})]
    target.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf8")
    return rows


def catmat_items(pdm: int, root: str | Path | None = None) -> dict[str, list[dict]]:
    """{"items": [{codigoItem, descricaoItem, statusItem}], "units": [{seq, sigla, nome, capacidade}]} of one PDM."""
    target = _cache(root) / "catmat_items" / f"{pdm}.json"
    if target.is_file():
        return json.loads(target.read_text(encoding="utf8"))
    items = [{"codigoItem": r["codigoItem"], "descricaoItem": r["descricaoItem"], "statusItem": r["statusItem"]}
             for r in _pages("4_consultarItemMaterial", {"codigoPdm": pdm})]
    units = [{"seq": r["numeroSequencialUnidadeFornecimento"], "sigla": r["siglaUnidadeFornecimento"],
              "nome": r["nomeUnidadeFornecimento"], "capacidade": r["capacidadeUnidadeFornecimento"]}
             for r in _pages("6_consultarMaterialUnidadeFornecimento", {"codigoPdm": pdm})]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"items": items, "units": units}, ensure_ascii=False), encoding="utf8")
    return {"items": items, "units": units}


#: Supply-unit suffixes of solid oral forms, read from BNAFAR's own rows (SP and RS, 2025-06, 3,107 rows): U0042 is on 106
#: distinct product descriptions, 97 naming COMPRIMIDO and the rest "COMP"; U0041 on 16, 14 naming CÁPSULA and 2 "CAP INAL". The
#: suffix is a national unit-of-supply code that also encodes volume (U0062 is a 100 mL bottle, U0086 20 mL), not the PDM's own
#: unit number (levotiroxina's comprimido is the PDM's unit 2, BNAFAR's U0042), so other presentations pass their suffix.
SOLID_ORAL = {"U0042": "COMPRIMIDO", "U0041": "CÁPSULA"}


def products(term: str, root: str | Path | None = None, units: dict[str, str] | None = None,
             only_with_stock: bool = True) -> list[dict]:
    """The BNAFAR products of the drugs whose CATMAT PDM name holds ``term`` (accents and case ignored): each item of
    the catalogue with each supply-unit suffix of ``units`` (default `SOLID_ORAL`) that BNAFAR holds a row of, with
    BNAFAR's own description: [{"pdm", "pdm_name", "code", "item", "item_description", "unit", "description"}]. Each
    candidate code is asked once (one row; the answer, negative too, is kept)."""
    units = units or SOLID_ORAL
    cache = _cache(root) / "product_probe.json"
    probe: dict[str, Any] = json.loads(cache.read_text(encoding="utf8")) if cache.is_file() else {}
    wanted = _fold(term)
    out = []
    for pdm in catmat_pdms(root):
        if wanted not in _fold(pdm["nomePdm"]):
            continue
        for item in catmat_items(pdm["codigoPdm"], root)["items"]:
            for suffix, unit in units.items():
                code = f"BR{int(item['codigoItem']):07d}{suffix}"
                if code not in probe:
                    rows = _get(DEMAS_BASE_URL + ENDPOINT, {"codigo_catmat": code, "limit": 1}).get("parametros") or []
                    probe[code] = rows[0]["descricao_produto"].strip() if rows else None
                    cache.write_text(json.dumps(probe, ensure_ascii=False), encoding="utf8")
                if probe[code] or not only_with_stock:
                    out.append({"pdm": pdm["codigoPdm"], "pdm_name": pdm["nomePdm"], "code": code,
                                "item": item["codigoItem"], "item_description": item["descricaoItem"],
                                "unit": unit, "description": probe[code]})
    return out


# --- the stock -------------------------------------------------------------------------------------------------------

def _all_pages(params: dict[str, Any]) -> pa.Table:
    """Every row of a filter, paged by ``limit=1000`` until a page is empty (the API applies its limit before
    de-duplication, so a short page is not an end)."""
    rows, offset = [], 0
    while True:
        page = _get(DEMAS_BASE_URL + ENDPOINT, {**params, "limit": PAGE, "offset": offset}).get("parametros") or []
        rows += [{c: (r.get(c) if c == "quantidade_estoque" or r.get(c) is None else str(r[c])) for c in COLUMNS} for r in page]
        if not page:
            break
        offset += PAGE
    schema = pa.schema([(c, pa.float64() if c == "quantidade_estoque" else pa.string()) for c in COLUMNS])
    return pa.Table.from_pylist(rows, schema=schema)


def _cached(name: str, params: dict[str, Any], root: str | Path | None, refresh: bool) -> pa.Table:
    target = _cache(root) / "stock" / name
    if target.is_file() and not refresh:
        return pq.read_table(target)
    table = _all_pages(params)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, target)
    return table


def stock(catmat: str, anomes: int, uf: int | str | None = None, root: str | Path | None = None,
          refresh: bool = False) -> pa.Table:
    """Every stock row of one CATMAT code (with its supply unit) in one month (``anomes`` 202506), optionally of one
    state (its IBGE code, 43). Cached per (code, month, state): a past month does not change, the current one does
    (``refresh``)."""
    params: dict[str, Any] = {"codigo_catmat": catmat, "anomes_posicao_estoque": anomes}
    if uf:
        params["codigo_uf"] = uf
    return _cached(f"{catmat}_{anomes}_{uf or 'BR'}.parquet", params, root, refresh)


def program(sigla: str, root: str | Path | None = None, refresh: bool = False) -> pa.Table:
    """Every stock row tagged with a health programme (``sigla_programa_saude``: TOXO is "TOXOPLASMOSE"; NI, "não
    informado", is most rows), all dates. A programme is a few thousand rows at most; read at its date, cached."""
    return _cached(f"program_{sigla}.parquet", {"sigla_programa_saude": sigla}, root, refresh)


def monthly(catmats: list[str], year: int, months: range | list[int] = range(1, 13),
            root: str | Path | None = None) -> pa.Table:
    """(catmat, description, anomes, uf, rows, establishments, lots, quantity): the stock by state and month, the
    month's last position of each lot in each establishment, summed (see the module note). A (code, month) holds
    nothing when the API returns no row for it; that month is absent from the table."""
    out = []
    for code in catmats:
        for m in months:
            t = stock(code, year * 100 + m, root=root)
            if not t.num_rows:
                continue
            rows = t.to_pylist()
            last: dict[tuple, dict] = {}
            for r in rows:
                key = (r["codigo_cnes"], r["numero_lote"], r["data_validade"])
                if key not in last or r["data_posicao_estoque"] > last[key]["data_posicao_estoque"]:
                    last[key] = r
            by_uf: dict[str, dict] = {}
            for r in last.values():
                d = by_uf.setdefault(r["uf"], {"catmat": code, "description": (r["descricao_produto"] or "").strip(),
                                               "anomes": year * 100 + m, "uf": r["uf"], "rows": 0,
                                               "cnes": set(), "lots": 0, "quantity": 0.0})
                d["cnes"].add(r["codigo_cnes"])
                d["lots"] += 1
                d["quantity"] += r["quantidade_estoque"] or 0.0
            for uf, d in by_uf.items():
                d["rows"] = sum(1 for r in rows if r["uf"] == uf)
                d["establishments"] = len(d.pop("cnes"))
                out.append(d)
    schema = pa.schema([("catmat", pa.string()), ("description", pa.string()), ("anomes", pa.int32()), ("uf", pa.string()),
                        ("rows", pa.int64()), ("establishments", pa.int64()), ("lots", pa.int64()), ("quantity", pa.float64())])
    return pa.Table.from_pylist(out, schema=schema)
