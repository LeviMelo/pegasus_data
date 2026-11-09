"""IBGE's Ligações Rodoviárias e Hidroviárias 2016: weekly coach and boat departures between municipalities.

**The product** (IBGE, *Ligações Rodoviárias e Hidroviárias 2016*, Redes e Fluxos do Território vol. 4, 2017, ``BOOK``;
``leiame.txt`` beside the workbook): a primary survey at the bus and river terminals and the informal-transport stops of every
municipality seat. The collected unit is the *seção* (a leg of a line between two seats); the workbook aggregates it per
**pair of municipalities**, 65,638 pairs (press release of 2017-06-30). Meanings, each from its source:

* Nodes are municipality seats (``Unidade espacial e de coleta``, Notas técnicas): "A unidade espacial de investigação da pesquisa
  é o município". Legs inside one *arranjo populacional* are out of scope, but the municipalities of an arrangement keep their own
  links to the outside, so no node is an arrangement. Municipalities "sem objeto" (no regular service; listed in
  ``Municipios_sem_objeto_da_pesquisa.xlsx``) are not origins, though they may appear as destinations.
* ``weight`` is **weekly departures** (``Agregação por par de municípios``): "somou-se o número de saídas semanais por par de
  municípios"; fortnightly services are multiplied by 0.5 and monthly by 0.25, and **vehicle types are weighted** (bus = 1;
  vans and cars 0.25; waterway: voadeira 0.25, lancha and catamarã 1, barco 1.5, navio 2). A weight is a capacity-weighted
  departure count, not a count of vehicles.
* **Direction**: the pair is stored once and its frequency sums both ways (``leiame.txt``: "As frequências foram agregadas, ida e
  volta, bem como seções redundantes"; the publication symmetrises "ida e/ou volta apenas por uma linha", note 5). The workbook
  is an *undirected total*; the edge list writes **both directions with the same full pair total** (never half). Summing
  ``weight`` over the table counts every pair twice.
* ``VAR05`` is the waterway frequency, ``VAR06`` the road frequency, ``VAR07`` their sum (checked on every row; dictionary sheet).
  The waterway graph is the pairs with ``VAR05 > 0``, the road graph those with ``VAR06 > 0``; pairs with both appear in both.
  Cost (``VAR03``, R$) and time (``VAR04``, minutes) are the pair's minimum over all services (``Parâmetros de coleta dos
  valores``): properties of the pair, not of the mode.
* ``VAR12``: departures by transporters declaring no CNPJ, the publication's proxy for informal transport; ``VAR13``: the pair
  holds an imputed leg (``Controle de qualidade e imputação de dados``).

**Unplaced.** The workbook also links Brazilian seats to South American cities, coded 80xxxxx-92xxxxx (the file's own ``COD_UF``:
80 ARG, 81 BOL, 82 CHI, 87 PAR, 88 PER, 91 URU, 92 VEN). They are not IBGE municipalities and go to neither graph; their pairs
and departures are counted in the report (``unplaced``) and checked against the publication's Tabela 2. A Brazilian code absent
from the shipped municipality pack is counted the same way.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

SOURCE = "https://geoftp.ibge.gov.br/organizacao_do_territorio/redes_e_fluxos_geograficos/ligacoes_rodoviarias_e_hidroviarias/base_de_dados/"
BOOK = "https://biblioteca.ibge.gov.br/visualizacao/livros/liv100602.pdf"
FILES = {
    "leiame": "leiame.txt",
    "base": "xls/Base_de_dados_ligacoes_rodoviarias_e_hidroviarias_2016.xlsx",
    "centrality": "xls/Indices_de_centralidade.xlsx",
    "no_object": "xls/Municipios_sem_objeto_da_pesquisa.xlsx",
}
VINTAGE = 2016
KINDS = {
    "road_links_2016": ("weekly_road", "road_links_2016.parquet"),
    "waterway_links_2016": ("weekly_waterway", "waterway_links_2016.parquet"),
}
#: Figures the publication prints (BOOK; Tabela 1 and 2 on PDF page 22, Tabela 3 on 23, the top pair on 20)
PUBLISHED_LINKS = 65_638
PUBLISHED_CITIES = 5_386
PUBLISHED_TOP = ("Carpina", "Paudalho", 2855.0)
PUBLISHED_BRAZIL_FREQUENCY = 3_148_078.8
PUBLISHED_WATERWAY_FREQUENCY = 11_835.8
PUBLISHED_STATE_FREQUENCY = {
    "SP": 467_532.3, "MG": 397_978.3, "BA": 342_730.0, "PR": 260_613.3, "RS": 260_613.3, "PE": 247_907.8, "CE": 173_527.5,
    "PB": 147_618.5, "SE": 143_162.0, "GO": 142_884.5, "SC": 142_115.5, "MA": 129_396.5, "PA": 122_543.0, "MT": 107_470.8,
    "RJ": 101_931.8, "PI": 101_062.8, "ES": 67_389.8, "MS": 65_262.3, "TO": 61_847.5, "AL": 58_877.0, "RN": 43_310.0,
    "RO": 34_733.3, "DF": 17_023.3, "AM": 7_541.3, "AC": 5_165.0, "RR": 3_556.0, "AP": 2_385.0,
    "PAR": 391.0, "ARG": 224.0, "VEN": 150.0, "URU": 123.0, "BOL": 76.0, "PER": 9.0, "CHI": 8.0,
}
COLUMNS = ["from", "to", "weight", "kind", "vintage", "link_id", "min_cost_brl", "min_travel_minutes", "cost_per_minute_brl",
           "weekly_road", "weekly_waterway", "weekly_total", "weekly_without_cnpj", "has_imputed_section"]

__all__ = ["KINDS", "build"]


def _registries(root: str | Path | None) -> Path:
    from ..config import load_settings

    return load_settings(root=root).registries_dir


def _fetch(folder: Path, log: Callable[[str], None]) -> dict[str, Path]:
    from ..transport import download

    out = {}
    for key, rel in FILES.items():
        log(f"ibge_links: {rel}")
        out[key] = download(SOURCE + rel, folder / rel.rsplit("/", 1)[-1])
    return out


def _pairs(path: Path) -> Any:
    """The workbook's pair table: codes as 7-character strings, the source's VARnn columns under their meaning."""
    import pandas as pd

    raw = pd.read_excel(path, sheet_name="Base de dados", dtype={"CODMUNDV_A": str, "CODMUNDV_B": str})
    if len(raw) != PUBLISHED_LINKS:
        raise ValueError(f"{path.name}: {len(raw)} pairs, the publication counts {PUBLISHED_LINKS}")
    if not (raw.CODMUNDV_A.str.len().eq(7).all() and raw.CODMUNDV_B.str.len().eq(7).all()):
        raise ValueError("a municipality code is not 7 characters wide")
    if ((raw.VAR05 + raw.VAR06 - raw.VAR07).abs() > 1e-9).any():
        raise ValueError("VAR07 is not VAR05 + VAR06: the column meanings changed")
    return pd.DataFrame({
        "a": raw.CODMUNDV_A, "b": raw.CODMUNDV_B, "uf_a": raw.UF_A, "uf_b": raw.UF_B, "name_a": raw.NOMEMUN_A, "name_b": raw.NOMEMUN_B,
        "link_id": raw.ID.astype("int64"), "min_cost_brl": raw.VAR03.astype("float64"), "min_travel_minutes": raw.VAR04.astype("float64"),
        "cost_per_minute_brl": raw.VAR14.astype("float64"), "weekly_road": raw.VAR06.astype("float64"),
        "weekly_waterway": raw.VAR05.astype("float64"), "weekly_total": raw.VAR07.astype("float64"),
        "weekly_without_cnpj": raw.VAR12.astype("float64"), "has_imputed_section": raw.VAR13.map({"Sim": True, "Não": False}),
    })


def _directed(pairs: Any, kind: str, column: str) -> Any:
    """Both directions of every pair served by this mode; the weight is the whole pair total (see the module note)."""
    import pandas as pd

    keep = pairs[pairs[column] > 0]
    side = keep.drop(columns=["a", "b", "uf_a", "uf_b", "name_a", "name_b"])
    out = pd.concat([side.assign(**{"from": keep.a, "to": keep.b}), side.assign(**{"from": keep.b, "to": keep.a})], ignore_index=True)
    out["weight"] = out[column].astype("float64")
    out["kind"], out["vintage"] = kind, VINTAGE
    return out[COLUMNS].sort_values(["from", "to"], kind="stable", ignore_index=True)


def build(root: str | Path | None = None, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Download once to ``<root>/registries/ibge_links/`` and write ``<root>/registries/mobility/{road,waterway}_links_2016.parquet``;
    return the counts, the unplaced nodes and the checks against the publication's own figures."""
    import pandas as pd

    from ..geography import municipalities

    log = log or (lambda _msg: None)
    registries = _registries(root)
    files = _fetch(registries / "ibge_links", log)
    pairs = _pairs(files["base"])
    known = {row["code7"] for row in municipalities().values()}
    if not known:
        raise RuntimeError("the municipality pack is not available: nodes cannot be placed")
    placed = pairs.a.isin(known) & pairs.b.isin(known)
    lost = pairs[~placed]
    nodes = pd.concat([lost.a[~lost.a.isin(known)], lost.b[~lost.b.isin(known)]]).drop_duplicates()
    unplaced = {
        "pairs": int(len(lost)), "nodes": int(len(nodes)), "weekly_total": float(lost.weekly_total.sum()),
        "reason": "the node is not an IBGE municipality: a South American city (codes 80xxxxx-92xxxxx; UF 80 ARG, 81 BOL, 82 CHI, "
                  "87 PAR, 88 PER, 91 URU, 92 VEN in the file) or a code outside the municipality pack",
        "codes_not_south_american": sorted(c for c in nodes if int(c) < 8_000_000),
    }
    out_dir = registries / "mobility"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"files": {k: str(v) for k, v in files.items()}, "pairs_in_source": int(len(pairs)),
                              "unplaced": unplaced, "kinds": {}}
    for kind, (column, name) in KINDS.items():
        table = _directed(pairs[placed], kind, column)
        table.to_parquet(out_dir / name, index=False)
        report["kinds"][kind] = {
            "path": str(out_dir / name), "rows": int(len(table)), "pairs": int(len(table) // 2),
            "weekly_departures_over_pairs": float(table.weight.sum() / 2), "municipalities": int(table["from"].nunique()),
        }
        log(f"ibge_links: {name}: {len(table)} rows")
    report["checks"] = _checks(pairs, files, unplaced)
    return report


def _checks(pairs: Any, files: dict[str, Path], unplaced: dict[str, Any]) -> dict[str, Any]:
    """The build against the figures the publication prints. A difference is reported, never absorbed."""
    import pandas as pd

    top = pairs.loc[pairs.weekly_total.idxmax()]
    centrality = pd.read_excel(files["centrality"], sheet_name=0)
    nodes = pd.concat([pairs.a, pairs.b]).drop_duplicates()
    # Tabela 2 counts a pair once under each state or country it touches (note 2): an inside-state pair counts once
    ends = pd.concat([pairs[["uf_a", "weekly_total"]].set_axis(["uf", "w"], axis=1),
                      pairs.loc[pairs.uf_a != pairs.uf_b, ["uf_b", "weekly_total"]].set_axis(["uf", "w"], axis=1)])
    by_uf = ends.groupby("uf").w.sum()
    return {
        "pairs": {"built": int(len(pairs)), "published": PUBLISHED_LINKS},
        "cities": {"nodes_in_pairs": int(len(nodes)), "centrality_table_rows": int(len(centrality)), "published_surveyed": PUBLISHED_CITIES},
        "top_pair": {"built": [str(top.name_a), str(top.name_b), float(top.weekly_total)], "published": list(PUBLISHED_TOP)},
        "brazil_weekly_frequency": {"built_all_pairs": float(pairs.weekly_total.sum()),
                                    "built_between_municipalities": float(pairs.weekly_total.sum() - unplaced["weekly_total"]),
                                    "published": PUBLISHED_BRAZIL_FREQUENCY},
        "waterway_weekly_frequency": {"built": float(pairs.weekly_waterway.sum()), "published": PUBLISHED_WATERWAY_FREQUENCY},
        "by_uf_or_country": {k: {"built": float(by_uf.get(k, 0.0)), "published": v, "difference": float(by_uf.get(k, 0.0) - v)}
                             for k, v in PUBLISHED_STATE_FREQUENCY.items()},
    }
