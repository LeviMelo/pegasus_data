"""Daily commuting between municipalities, from the Census 2010 sample microdata: a weighted origin-destination graph.

**The source** (IBGE, Censo Demográfico 2010, Resultados Gerais da Amostra, ``SOURCE``): one zip per state holding the
fixed-width person file ``Amostra_Pessoas_*.txt`` (the sample households), and ``Documentacao.zip``, whose
``Layout/Layout_microdados_Amostra.xls`` gives the columns. The person file is the intake source ``census2010_pessoas``
(every variable of the layout landed in the lake, positions checked against that layout at each landing, ``intake.py``);
this module reads six of its columns from the lake and lands the states it lacks. The variables, as documented:

* ``V0001`` (positions 1-2) UF and ``V0002`` (3-7) municipality code, joined into the 7-digit IBGE code of **residence**
  (``CODMUN``); ``V0010`` (29-44, 3 integer and 13 decimal digits, the decimal point implied) the sample weight.
* **Work.** ``V0660`` (328) "em que município ou país estrangeiro trabalha": 1 own home, 2 only this municipality but not
  at home, 3 another municipality, 4 a foreign country, 5 more than one municipality or country, blank (not employed);
  ``V6604`` (336-342) the 7-digit municipality of work, filled when ``V0660`` is 3. Its code list is
  ``Anexos Auxiliares/Migração e deslocamento _Municípios.xls`` (5,589 codes and ``8888888`` IGNORADO).
* **Study.** ``V0636`` (168) "município ou país estrangeiro que frequentava escola (ou creche)": 1 this municipality,
  2 another municipality, 3 a foreign country, blank; ``V6364`` (176-182) the 7-digit municipality of the school.

**Edges** are persons residing in ``from`` whose work (study) municipality ``to`` differs from ``from``; ``weight`` is
the sum of ``V0010`` (a sum, never a mean) and ``persons_sampled`` the unweighted count. What is not a municipality is
counted apart and never mapped: a foreign country (``V0660`` 4, ``V0636`` 3), "more than one place" (``V0660`` 5, which
has no code), a "another municipality" person with a blank code, the ignored code ``8888888``, a code neither the
documentation nor any residence names (``9999999``), and a code equal to the residence (not an edge). Persons whose question is blank are outside the universe.

Stored in ``registries/mobility/``: ``commute_work_2010.parquet`` and ``commute_study_2010.parquet``; in
``registries/census2010_microdata/`` the zips and, for `validate`, ``<kind>_answered_other.parquet`` (every "another
municipality" person by residence) and SIDRA's figures. `validate` compares each origin's total with IBGE's SIDRA tables 1615 (work) and
1611 (school), category "Outro município".
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from ..config import UF_ABBREVIATIONS, load_settings
from ..semantics.curation import declared

SOURCE = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2010/Resultados_Gerais_da_Amostra/Microdados/"
#: SP is published as two files (the metropolitan region apart).
STATES = [x for uf in UF_ABBREVIATIONS for x in (("SP1", "SP2_RM") if uf == "SP" else (uf,))]
VINTAGE = 2010
#: The IBGE "ignorado" municipality code of the code list
IGNORED = 8888888
#: layer -> (kind, question variable, code variable, answer "another municipality", "foreign country", "several places"):
#: the questionnaire's codes, declared in ``curation/published_tables.yml`` (``census_commuting:``)
LAYERS = {layer: (b["kind"], b["question"], b["code_variable"], b["other_municipality"], b["foreign_country"], b["several_places"])
          for layer, b in declared("published_tables.yml", "census_commuting", "layers").items()}
#: Census 2010 sample tables in SIDRA: persons by place of work / school: (table, variable, classification, "Outro município")
SIDRA = {layer: (b["table"], b["variable"], b["classification"], b["category"])
         for layer, b in declared("published_tables.yml", "census_commuting", "sidra").items()}
BLOCK = 100_000
#: The intake source the persons are read from (``curation/intake.yml``) and its person columns this module reads
PERSONS = "census2010_pessoas"
COLUMNS = ("CODMUN", "V0010", "V0636", "V6364", "V0660", "V6604")
KEYS = ("other_country", "multiple_places", "no_code", "ignored", "unlisted", "same_as_residence")

__all__ = ["RECORD_SHEETS", "build", "record_layouts", "validate"]


def _directory(root: str | Path | None, name: str) -> Path:
    return load_settings(root=root).registry_dir(name)


def _sheet(documentation: Path, pattern: str, **options: Any) -> Any:
    import pandas as pd

    with zipfile.ZipFile(documentation) as z:
        name = next(n for n in z.namelist() if re.search(pattern, n, re.I))
        return pd.read_excel(io.BytesIO(z.read(name)), header=None, engine="xlrd", **options)


#: The sample's record files and the layout sheet each is written by (Layout_microdados_Amostra.xls)
RECORD_SHEETS = {"Amostra_Domicilios": "DOMI", "Amostra_Pessoas": "PESS", "Amostra_Emigracao": "EMIG", "Amostra_Mortalidade": "MORT"}


def record_layouts(root: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """The documentation's own layout of each record file of the sample (``Layout/Layout_microdados_Amostra.xls`` in
    ``Documentacao.zip``, one sheet per record type): ``{file stem: {"width": the last position, "variables": {name: (first, last,
    description)}, "fields": {name: {"integer": digits before the implied decimal point, "decimals": digits after it, "type":
    the sheet's TIPO (A alphanumeric, C categorical, N numeric), "text": the NOME cell as written, line breaks and code list
    included}}}}``. A record line is ``width`` characters and a line break. Reads the held documentation only."""
    documentation = _directory(root, "census2010_microdata") / "Documentacao.zip"
    out: dict[str, dict[str, Any]] = {}
    for stem, sheet_name in RECORD_SHEETS.items():
        sheet = _sheet(documentation, r"layout_microdados_amostra\.xls$", sheet_name=sheet_name)
        rows = [r for r in sheet.itertuples(index=False) if str(r[0]).strip() and str(r[8]).strip().replace(".", "").isnumeric()]
        variables = {str(r[0]).strip(): (int(float(r[7])), int(float(r[8])), " ".join(str(r[1]).split())) for r in rows}
        fields = {str(r[0]).strip(): {"integer": int(float(r[9])), "decimals": int(float(r[10])) if str(r[10]) != "nan" else 0,
                                      "type": str(r[11]).strip(), "text": str(r[1]).strip()} for r in rows}
        out[stem] = {"width": max(v[1] for v in variables.values()), "variables": variables, "fields": fields}
    return out


def _municipality_codes(documentation: Path) -> set[int]:
    """The 7-digit municipality codes of the documentation's list (``8888888``, IGNORADO, is not one)."""
    import pandas as pd

    sheet = _sheet(documentation, r"Anexos Auxiliares/Migra.*_Munic.pios\.xls$")
    numbers = pd.to_numeric(sheet[2], errors="coerce").dropna().astype("int64")
    return {int(c) for c in numbers if c != IGNORED}


def _persons(settings: Any, state: str) -> Iterator[Any]:
    """The columns this module reads of one state's landed person records, as Arrow batches of `BLOCK` rows (never the whole state)."""
    import duckdb

    from ..intake import _safe
    from ..persist.lake import unit_parts

    parts = unit_parts(settings.lake_dir, "CENSO2010_PESSOAS_*", _safe(f"{VINTAGE}-{state}"))
    if not parts:
        raise FileNotFoundError(f"the person records of {state} are not in the lake (intake source {PERSONS})")
    con = duckdb.connect(":memory:")
    try:
        con.execute(f"SELECT {', '.join(COLUMNS)} FROM read_parquet({sorted(p.as_posix() for p in parts)!r}, hive_partitioning=false)")
        reader = con.fetch_record_batch(BLOCK)
        yield from reader
    finally:
        con.close()


def _integers(column: Any) -> tuple[Any, Any]:
    """(value, filled) of a column of digits as text (null when blank): anything else raises, never read as a number."""
    import numpy as np
    import pyarrow as pa
    import pyarrow.compute as pc

    filled = pc.is_valid(column).to_numpy(zero_copy_only=False)
    return pc.fill_null(pc.cast(column, pa.int64()), 0).to_numpy(zero_copy_only=False).astype(np.int64), filled


def _add(batches: Any, tally: dict[str, Any]) -> None:
    """Add one state's persons (Arrow batches of `_persons`) to the running aggregates."""
    import numpy as np
    import pandas as pd
    import pyarrow.compute as pc

    for block in batches:
        origin = _integers(block.column("CODMUN"))[0]
        weight = block.column("V0010").to_numpy(zero_copy_only=False)
        tally["residences"].update(np.unique(origin).tolist())
        tally["persons"] += block.num_rows
        tally["weight"] += float(weight.sum())
        for layer, (_, question, code_variable, other, foreign, several) in LAYERS.items():
            answer = block.column(question)
            code, filled = _integers(block.column(code_variable))
            state = tally[layer]
            asked = pc.is_valid(answer).to_numpy(zero_copy_only=False)

            def is_answer(value: str, answer: Any = answer) -> Any:
                return pc.fill_null(pc.equal(answer, value), False).to_numpy(zero_copy_only=False)

            is_other = is_answer(other)
            masks = {"other_country": is_answer(foreign),
                     "no_code": is_other & ~filled,
                     "ignored": is_other & filled & (code == IGNORED),
                     "same_as_residence": is_other & filled & (code == origin)}
            if several:
                masks["multiple_places"] = is_answer(several)
            for key, mask in masks.items():
                state["apart"][key][0] += int(mask.sum())
                state["apart"][key][1] += float(weight[mask].sum())
            state["asked"][0] += int(asked.sum())
            state["asked"][1] += float(weight[asked].sum())
            state["other"][0] += int(is_other.sum())
            state["other"][1] += float(weight[is_other].sum())
            state["code_without_answer"] += int((filled & ~is_other).sum())
            state["answered_other"].append(pd.DataFrame({"from": origin[is_other], "weight": weight[is_other]})
                                           .groupby("from")["weight"].agg(["sum", "size"]))
            edge = is_other & filled & (code != IGNORED) & (code != origin)
            state["edges"].append(pd.DataFrame({"from": origin[edge], "to": code[edge], "weight": weight[edge]})
                                  .groupby(["from", "to"])["weight"].agg(["sum", "size"]))


def _codes(values: Any) -> Any:
    """Municipality codes as the text the graph stores. The source declares them 7 digits (``V0001`` + ``V0002``, the
    code list's ``V6604``/``V6364``): any other width is a defect in the read, so it raises, never padded to match."""
    text = values.astype(str)
    wrong = text[text.str.len() != 7]
    if len(wrong):
        raise ValueError(f"municipality codes of the census microdata are 7 digits; found {sorted(set(wrong))[:5]}")
    return text


def build(root: str | Path | None = None, log: Any = None, states: Sequence[str] | None = None) -> dict[str, Any]:
    """Land the person records of the states the lake lacks (the intake source ``census2010_pessoas``: the 27 zips and the
    documentation are downloaded once), and write the two commuting graphs from them. ``states`` (a subset of `STATES`) is for
    a development run on a few files: the graphs then cover those states only.

    Returns the persons and weight of the whole sample and, per layer (``work``, ``study``): the edges' rows, weighted
    total and unweighted persons; the persons asked and those answering "another municipality"; and, apart, the persons
    whose place is another country, several places, without a code, ignored, unlisted or the residence itself."""
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    from ..transport import download

    micro = _directory(root, "census2010_microdata")
    out = _directory(root, "mobility")
    out.mkdir(parents=True, exist_ok=True)
    documentation = download(SOURCE + "Documentacao.zip", micro / "Documentacao.zip", timeout=3600)
    documented = _municipality_codes(documentation)
    chosen = list(states or STATES)
    from ..intake import build_source

    settings = load_settings(root=root)
    landed = build_source(settings, PERSONS, [], [VINTAGE], units=chosen)
    if log:
        log(f"person records: {landed['rows']} rows in the lake for {len(chosen)} files")
    tally: dict[str, Any] = {"persons": 0, "weight": 0.0, "residences": set()}
    for layer in LAYERS:
        tally[layer] = {"asked": [0, 0.0], "other": [0, 0.0], "code_without_answer": 0,
                        "apart": {k: [0, 0.0] for k in KEYS}, "answered_other": [], "edges": []}
    for state in chosen:
        _add(_persons(settings, state), tally)
        if log:
            log(f"{state}: {tally['persons']} persons so far")
    schema = pa.schema([("from", pa.string()), ("to", pa.string()), ("weight", pa.float64()), ("kind", pa.string()),
                        ("vintage", pa.int64()), ("persons_sampled", pa.int64())])
    report: dict[str, Any] = {"persons_sampled": tally["persons"], "weight_total": tally["weight"],
                              "documented_municipality_codes": len(documented)}
    for layer, (kind, *_) in LAYERS.items():
        state = tally[layer]
        edges = pd.concat(state["edges"]).groupby(level=["from", "to"]).sum().reset_index()
        edges.columns = ["from", "to", "weight", "persons_sampled"]
        # a destination is a municipality when the code list names it or a person of this census resides in it (the list
        # omits some, e.g. 1200013 Acrelândia); any other code, 9999999 among them, is undocumented and counted apart
        known = documented | tally["residences"]
        unlisted = ~edges["to"].isin(known)
        state["apart"]["unlisted"] = [int(edges.loc[unlisted, "persons_sampled"].sum()), float(edges.loc[unlisted, "weight"].sum())]
        state["unlisted_codes"] = sorted(edges.loc[unlisted, "to"].unique().tolist())
        edges = edges[~unlisted]
        edges["from"], edges["to"] = _codes(edges["from"]), _codes(edges["to"])
        edges["kind"], edges["vintage"] = kind, VINTAGE
        edges = edges.sort_values(["from", "to"]).reset_index(drop=True)[schema.names]
        pq.write_table(pa.Table.from_pandas(edges, schema=schema, preserve_index=False), out / f"{kind}.parquet")
        other = pd.concat(state["answered_other"]).groupby(level=0).sum()
        other.columns = ["weight", "persons_sampled"]
        other.index = _codes(other.index.to_series()).values
        other.rename_axis("from").reset_index().to_parquet(_directory(root, "census2010_microdata") / f"{kind}_answered_other.parquet", index=False)
        report[layer] = {"rows": len(edges), "weighted_total": float(edges["weight"].sum()),
                         "persons_sampled_in_edges": int(edges["persons_sampled"].sum()),
                         "asked": {"persons": state["asked"][0], "weighted": state["asked"][1]},
                         "answered_other_municipality": {"persons": state["other"][0], "weighted": state["other"][1]},
                         "undocumented_codes": state["unlisted_codes"],
                         "code_given_without_that_answer": state["code_without_answer"],
                         "apart": {k: {"persons": v[0], "weighted": v[1]} for k, v in state["apart"].items()}}
        if log:
            log(f"{layer}: {len(edges)} edges, weighted {report[layer]['weighted_total']:.0f}")
    return report


def validate(root: str | Path | None = None, layer: str = "work", tolerance: float = 1e-3) -> dict[str, Any]:
    """Compare each origin's weighted total with IBGE's SIDRA "outro município" (tables 1615 work, 1611 school).

    Two figures per municipality meet SIDRA's: every person answering "another municipality", whatever their code, and the
    graph's weighted out-commuting (edges only, so without the ignored, unlisted, no-code and own-residence persons).
    Returns, for each, how many municipalities match (within ``tolerance`` relative, and within one person), the largest
    differences and the sums."""
    import pandas as pd

    from ..transport import get_json

    table, variable, classification, category = SIDRA[layer]
    kind = LAYERS[layer][0]
    folder = _directory(root, "census2010_microdata")
    cache = folder / f"sidra_{table}_outro_municipio.parquet"
    if cache.is_file():
        published = pd.read_parquet(cache)
    else:
        url = f"https://apisidra.ibge.gov.br/values/t/{table}/n6/all/v/{variable}/p/2010/c{classification}/{category}"
        rows = get_json(url, retries=6)[1:]
        published = pd.DataFrame({"from": [r["D1C"] for r in rows], "published": [r["V"] for r in rows]})
        published["published"] = pd.to_numeric(published["published"], errors="coerce")
        published.to_parquet(cache, index=False)
    answered = pd.read_parquet(folder / f"{kind}_answered_other.parquet").set_index("from")["weight"]
    graph = pd.read_parquet(_directory(root, "mobility") / f"{kind}.parquet").groupby("from")["weight"].sum()
    frame = published.set_index("from")["published"].to_frame()
    frame["answered"], frame["graph"] = answered, graph
    known = frame[frame["published"].notna()]
    report: dict[str, Any] = {"table": table, "municipalities_published": len(known),
                              "published_without_value": int(frame["published"].isna().sum()),
                              "published_total": float(known["published"].sum())}
    for column in ("answered", "graph"):
        # a municipality our tables do not hold has no figure (null), not 0 people: it is counted apart
        # (``<column>_absent``) and is never within tolerance of what IBGE published
        report[f"{column}_absent"] = int(known[column].isna().sum())
        difference = known[column] - known["published"]
        worst = difference.abs().sort_values(ascending=False).head(5).index
        report[column] = {"total": float(known[column].sum()),
                          "within_tolerance": int((difference.abs() <= tolerance * known["published"].clip(lower=1)).sum()),
                          "within_1_person": int((difference.abs() <= 1).sum()),
                          "largest": [{"from": i, "published": float(known.at[i, "published"]), "ours": float(known.at[i, column])}
                                      for i in worst if pd.notna(known.at[i, column])],
                          "ours_not_published": sorted(set(frame.index[frame[column] > 0]) - set(published["from"]))[:10]}
    return report
