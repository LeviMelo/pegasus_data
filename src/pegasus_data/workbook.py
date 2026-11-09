"""A built aggregate artifact as a presentable Excel workbook.

A spreadsheet handed to a team is read without the interface's guardrails,
so the workbook carries them itself. Two rules shape it:

- **Every cut is its own aggregation.** A sheet by sex asks the aggregate
  layer for the sex breakdown, never pivots or re-sums another sheet: `los`
  (length of stay) is a mean, and summing or averaging means gives a
  plausible wrong number. Totals are separate calls at the coarser level.
- **Absence is not zero.** A municipality with no cell was not observed; the
  cell stays blank and the Leia-me sheet says so.

Formerly ``tools/export_workbook.py``, which reached the package through the
HTTP API and reduced stocks over time itself; both now come from the package.
Needs the ``excel`` extra (openpyxl).
"""

from __future__ import annotations

import datetime as dt
import functools
from pathlib import Path
from typing import Any

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook import Workbook

from ._aggregate import aggregate
from .capabilities import capabilities
from .geography import municipalities

# ---------------------------------------------------------------- palette
INK = "1F2933"
ACCENT = "2F3E9E"
HEAD_FILL = PatternFill("solid", fgColor="EEF1FA")
TOTAL_FILL = PatternFill("solid", fgColor="F5F5F5")
HAIR = Side(style="thin", color="D8DEE9")


def number_format(measure: dict) -> str:
    """Excel format from the measure's declared unit and decimals."""
    if measure["unit"] == "brl":
        return 'R$ #,##0.00'
    decimals = int(measure.get("decimals") or 0)
    return "#,##0" if decimals == 0 else "#,##0." + "0" * decimals


def _cut(artifact: str, by: list[str], measures: list[dict], *, settings: Any = None) -> list[dict]:
    """One cut: its own aggregation, never a pivot of another sheet.

    A stock's time is reduced by the aggregate layer itself, by the rule its
    measure declares (OQ-14), so a sheet without time carries a stock's
    mean, last or maximum, never its bed-months.
    """
    table = aggregate(artifact, by=by or None, measures=[m["id"] for m in measures], settings=settings)
    return table.to_pylist()  # type: ignore[union-attr]


def headers_for(measures: list[dict], time_on_axis: bool) -> list[str]:
    """Measure labels, qualified when a stock has had its time collapsed.

    On a sheet with time as an axis a stock's cell IS that period's value and
    needs no qualifier. On a sheet without one, the cell is a reduction over
    the whole window, and a bare "Leitos" over 78.594 reads as a total when
    it is a monthly mean.
    """
    words = {"mean": "média", "last": "último", "max": "máximo"}
    out = []
    for m in measures:
        rule = m.get("time_reducer")
        if rule and not time_on_axis:
            out.append(f"{m['label']} ({words.get(rule, rule)} por período)")
        else:
            out.append(m["label"])
    return out


def sheet_title(name: str) -> str:
    """Excel forbids : \\ / ? * [ ] in sheet names, and caps them at 31 chars.

    "Raça/cor" is a real dimension label, so this is a certainty rather than
    a defensive flourish.
    """
    for bad in ':\\/?*[]':
        name = name.replace(bad, "-")
    return name[:31].strip() or "Planilha"


def write_sheet(
    wb: Workbook,
    title: str,
    headers: list[str],
    rows: list[list],
    formats: dict[int, str],
    note: str = "",
    total_row: list | None = None,
) -> None:
    """One sheet: a note, a header band, the data, an optional total."""
    ws = wb.create_sheet(sheet_title(title))
    r = 1
    if note:
        ws.cell(row=1, column=1, value=note).font = Font(size=9, italic=True, color="6B7280")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(headers), 1))
        r = 3

    header_row = r
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.font = Font(bold=True, color=INK, size=10)
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=HAIR)
    r += 1

    for row in rows:
        for c, v in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            if c in formats:
                cell.number_format = formats[c]
        r += 1

    if total_row is not None:
        for c, v in enumerate(total_row, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(bold=True)
            cell.fill = TOTAL_FILL
            cell.border = Border(top=HAIR)
            if c in formats:
                cell.number_format = formats[c]

    # Widths from content, capped so a long municipality name cannot push the
    # measures off screen.
    for c, h in enumerate(headers, start=1):
        longest = len(str(h))
        for row in rows[:400]:
            if c - 1 < len(row) and row[c - 1] is not None:
                longest = max(longest, len(str(row[c - 1])))
        ws.column_dimensions[get_column_letter(c)].width = min(max(longest + 3, 11), 42)

    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    if rows:
        ws.auto_filter.ref = (
            f"A{header_row}:{get_column_letter(len(headers))}{header_row + len(rows)}"
        )


def build(artifact: str, out: Path, *, settings: Any = None) -> Path:
    """Write ``artifact``'s workbook to ``out`` and return the path."""
    capability = capabilities(artifact, settings=settings)
    caps = capability.as_dict()
    measures = caps["measures"]
    mids = [m["id"] for m in measures]

    # Territory names, indexed by the 6-digit code the artifact stores.
    by6: dict[str, dict] = {}
    uf_name: dict[Any, str] = {}
    for code6, muni in municipalities().items():
        by6[code6] = {"name": muni["name"], "uf": muni["uf_sigla"], "macroregion": muni["macroregion"]}
        uf_name[muni["uf_sigla"]] = muni["uf_name"]

    # Dimension labels, from the artifact's own codelists.
    codelists = {d.id: {lv.code: lv.label for lv in d.levels} for d in capability.dimensions}
    cut = functools.partial(_cut, settings=settings)

    wb = Workbook()
    wb.remove(wb.active)

    # ------------------------------------------------------------ Leia-me
    ws = wb.create_sheet("Leia-me")
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 96
    row = 1

    def kv(k: str, v: str, bold: bool = False) -> None:
        nonlocal row
        a = ws.cell(row=row, column=1, value=k)
        a.font = Font(bold=True, size=10, color=INK)
        b = ws.cell(row=row, column=2, value=v)
        b.alignment = Alignment(wrap_text=True, vertical="top")
        if bold:
            b.font = Font(bold=True)
        row += 1

    def gap(n: int = 1) -> None:
        nonlocal row
        row += n

    def head(text: str) -> None:
        nonlocal row
        c = ws.cell(row=row, column=1, value=text)
        c.font = Font(bold=True, size=12, color=ACCENT)
        row += 1

    title = ws.cell(row=row, column=1, value=caps["label"])
    title.font = Font(bold=True, size=16, color=INK)
    row += 1
    ws.cell(row=row, column=1, value=caps.get("description") or "").font = Font(
        size=10, color="6B7280"
    )
    row += 2

    head("Procedência")
    kv("Fonte", f"DATASUS {caps['dataset']} ({caps['system']} · {caps['series']})")
    kv("Artefato", caps["id"])
    kv("Impressão digital", caps["fingerprint"])
    kv("Vintage (build)", caps["vintage"])
    period = caps["period"]
    kv("Período", f"{period['from']} a {period['to']} (grão: {period['grain']})")
    kv("Unidade observada", caps["observation_unit"])
    kv("Exportado em", dt.datetime.now().astimezone().isoformat(timespec="seconds"))
    gap()

    head("Medidas")
    for m in measures:
        kind = {
            "count": "contagem",
            "sum": "soma",
            "mean": "média",
            "ratio": "razão",
        }.get(m["kind"], m["kind"])
        extra = ""
        if m["kind"] == "mean":
            extra = (
                "  ⚠ É uma MÉDIA: não some nem tire média desta coluna. "
                "Cada total foi recalculado a partir dos dados de origem."
            )
        if m.get("time_reducer"):
            words = {"mean": "média", "last": "último valor", "max": "máximo"}
            extra += (
                f"  ⚠ É um ESTOQUE: existe em cada instante, não se acumula. "
                f"Somar ao longo dos meses produziria '{m['unit']}-mês'. "
                f"Onde o tempo foi colapsado, a coluna traz o "
                f"{words.get(m['time_reducer'], m['time_reducer'])} dos valores mensais."
            )
        kv(m["label"], f"{kind} · unidade: {m['unit']} · fórmula: {m['formula']}{extra}")
    gap()

    head("Como ler")
    kv(
        "Cada aba é um recorte próprio",
        "Nenhuma aba foi derivada de outra. Cada uma foi recalculada a partir "
        "do agregado, porque somar ou tirar média de uma coluna que já é média "
        "(permanência) produz um número plausível e errado.",
    )
    kv(
        "Célula vazia ≠ zero",
        "Um município sem célula não foi observado naquele recorte — ele não "
        "reportou zero. Vazio foi mantido vazio de propósito; preencher com 0 "
        "faria qualquer média subsequente mentir.",
    )
    kv(
        "Totais",
        "As linhas de Total vêm de uma agregação separada no nível mais amplo, "
        "não da soma da coluna acima.",
    )
    cov = caps["spatial"]["coverage"]
    kv(
        "Cobertura",
        f"{cov['kind']} · {cov.get('municipalities', '?')} municípios no escopo do build."
        + (f" Observação: {cov['note']}" if cov.get("note") else ""),
    )
    gap()
    kv(
        "Gerado por",
        "PegaSUS — pegasus_data (agregação; pegasus-data workbook). "
        "Os valores aqui são os mesmos servidos por pegasus_data.serve.",
    )

    # ------------------------------------------------- Resumo (Brasil/ano)
    national = cut(artifact, [], measures)
    if national:
        n = national[0]
        write_sheet(
            wb,
            "Resumo Brasil",
            ["Medida", "Valor", "Unidade"],
            [
                [h, n.get(m["id"]), m["unit"]]
                for h, m in zip(headers_for(measures, False), measures, strict=True)
            ],
            {2: "#,##0.00"},
            note=f"Brasil · {period['from']} a {period['to']}. Uma agregação nacional única.",
        )
        # Per-measure formats differ, so set them cell by cell.
        sheet = wb["Resumo Brasil"]
        for i, m in enumerate(measures):
            sheet.cell(row=4 + i, column=2).number_format = number_format(m)

    # ------------------------------------------------------ tempo (mês)
    monthly = cut(artifact, ["month"], measures)
    monthly.sort(key=lambda r: r.get("month") or "")
    write_sheet(
        wb,
        "Por mês",
        ["Mês"] + headers_for(measures, True),
        [[r.get("month")] + [r.get(i) for i in mids] for r in monthly],
        {i + 2: number_format(m) for i, m in enumerate(measures)},
        note="Brasil, por mês de competência.",
        total_row=["Total"] + [national[0].get(i) for i in mids] if national else None,
    )

    # ------------------------------------------------------------- por UF
    per_uf = cut(artifact, ["uf"], measures)
    per_uf.sort(key=lambda r: -(r.get(mids[0]) or 0))
    write_sheet(
        wb,
        "Por UF",
        ["UF", "Estado"] + headers_for(measures, False),
        [
            [r.get("uf"), uf_name.get(r.get("uf"), r.get("uf"))] + [r.get(i) for i in mids]
            for r in per_uf
        ],
        {i + 3: number_format(m) for i, m in enumerate(measures)},
        note="Ordenado pela primeira medida. Cada linha é uma agregação da UF inteira.",
        total_row=["", "Total"] + [national[0].get(i) for i in mids] if national else None,
    )

    # -------------------------------------------------------- UF x mês
    uf_month = cut(artifact, ["uf", "month"], measures)
    uf_month.sort(key=lambda r: (r.get("uf") or "", r.get("month") or ""))
    write_sheet(
        wb,
        "Por UF e mês",
        ["UF", "Estado", "Mês"] + headers_for(measures, True),
        [
            [r.get("uf"), uf_name.get(r.get("uf"), r.get("uf")), r.get("month")]
            + [r.get(i) for i in mids]
            for r in uf_month
        ],
        {i + 4: number_format(m) for i, m in enumerate(measures)},
        note="Série mensal por estado.",
    )

    # ------------------------------------------------------ municípios
    per_mun = cut(artifact, ["municipality"], measures)
    per_mun.sort(key=lambda r: -(r.get(mids[0]) or 0))
    mun_rows = []
    for r in per_mun:
        code = r.get("municipality") or ""
        e = by6.get(code, {})
        mun_rows.append(
            [code, e.get("name", ""), e.get("uf", ""), e.get("macroregion", "")]
            + [r.get(i) for i in mids]
        )
    write_sheet(
        wb,
        "Por município",
        ["Código", "Município", "UF", "Região"] + headers_for(measures, False),
        mun_rows,
        {i + 5: number_format(m) for i, m in enumerate(measures)},
        note=(
            f"{len(mun_rows):,} municípios com pelo menos uma célula no período. "
            "Um município ausente desta lista não foi observado — não é zero."
        ).replace(",", "."),
        total_row=["", "", "", "Total"] + [national[0].get(i) for i in mids] if national else None,
    )

    # ------------------------------------------------- uma aba por dimensão
    for dim in caps["dimensions"]:
        did, dlabel = dim["id"], dim["label"]
        table = cut(artifact, [did], measures)
        labels: dict[Any, Any] = codelists.get(did, {})
        table.sort(key=lambda r: -(r.get(mids[0]) or 0))
        rows = [
            [r.get(did), labels.get(r.get(did), r.get(did))] + [r.get(i) for i in mids]
            for r in table
        ]
        note = f"Brasil, por {dlabel.lower()}."
        if dim.get("derived"):
            note += " Dimensão derivada — construída pelo pipeline, não é uma coluna bruta."
        if dim.get("note"):
            note += f" {dim['note']}"
        write_sheet(
            wb,
            f"Por {dlabel}",
            ["Código", dlabel] + headers_for(measures, False),
            rows,
            {i + 3: number_format(m) for i, m in enumerate(measures)},
            note=note,
            total_row=["", "Total"] + [national[0].get(i) for i in mids] if national else None,
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out


__all__ = ["build"]
