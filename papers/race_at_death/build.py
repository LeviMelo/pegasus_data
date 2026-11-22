"""Builds the manuscript and the supplement from results/results.json and the figures of figures.py. No number is typed here.

    python papers/race_at_death/figures.py
    python papers/race_at_death/build.py        -> out/manuscript.docx, out/supplement.docx, out/build_report.json
"""
import json
import math
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

HERE = Path(__file__).parent
OUT = HERE / "out"
R = json.loads((HERE / "results" / "results.json").read_text(encoding="utf-8"))
SP = json.loads((HERE / "results" / "spatial.json").read_text(encoding="utf-8"))
REFS: dict = {}
for name in ("crossref.json", "crossref_theory.json", "crossref_more.json", "crossref_methods.json", "crossref_methods2.json"):
    REFS |= json.loads((HERE / "references" / name).read_text(encoding="utf-8"))
MANUAL = json.loads((HERE / "references" / "manual.json").read_text(encoding="utf-8"))

DESIGN = "cross-sectional study of routinely collected birth and death records and of census microdata"
OBJECTIVE = ("to compare the race recorded on the death certificate of people who died before age 25 in Brazil with the race their mothers declared for "
             "themselves and with the race families assign to children, to find where in the country and over which years they differ and what explains it, and to "
             "measure what the differences do to mortality rate ratios by race")
EN = {"Branca": "White", "Preta": "Black", "Parda": "Brown", "Indigena": "Indigenous"}
ORDER = ["Branca", "Parda", "Preta", "Indigena"]


# ---------------------------------------------------------------- formatting: a miss raises
def f2(x):
    return f"{x:.2f}"


def f1(x):
    return f"{x:.1f}"


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def n0(x):
    return f"{int(round(x)):,}"


def ci(c, log=False, d=2):
    """est (95%CI lo; hi) from an {est, se}; a ratio's interval on the log scale."""
    v, s = c["est"], c["se"]
    lo, hi = (v * math.exp(-1.96 * s / v), v * math.exp(1.96 * s / v)) if log else (v - 1.96 * s, v + 1.96 * s)
    assert lo <= v <= hi
    return f"{v:.{d}f} (95%CI {lo:.{d}f}; {hi:.{d}f})"


def cc(c, limit=0.15):
    """A proportion estimated as a difference of counts: 'not estimable' when its error is wide or it leaves 0 to 1 by more than the error."""
    if c is None or c.get("se") is None or c["se"] > limit or c["est"] < -2 * c["se"] or c["est"] > 1 + 2 * c["se"]:
        return "not estimable"
    return ci(c)


def cell(m, a, b):
    """The cell (mother's or birth-record class a, certified class b) of a matrix of the candidate estimator or of the linkage."""
    return m["rows"][a][b] if a in m["rows"] else None


def fam(m, a, b):
    return m[a][b]["est"]


# ---------------------------------------------------------------- references: numbered at first citation
order: list[str] = []


def cite(*keys):
    for k in keys:
        if k not in REFS and k not in MANUAL:
            raise KeyError(f"reference {k} is not verified")
        if k not in order:
            order.append(k)
    nums = sorted(order.index(k) + 1 for k in keys)
    return "[" + ",".join(str(n) for n in nums) + "]"


def reference_text(k):
    if k in MANUAL:
        return MANUAL[k]
    r = REFS[k]
    authors = ", ".join(r["authors"][:6]) + (", et al" if len(r["authors"]) > 6 else "")
    title = re.sub(r"\s+", " ", r["title"].replace("&amp;", "&")).rstrip(".")
    journal = (r.get("journal") or "").replace("&amp;", "&")
    vol = f";{r['volume']}" if r.get("volume") else ""
    issue = f"({r['issue']})" if r.get("issue") and str(r["issue"]) != "0" else ""
    pages = f":{r['pages']}" if r.get("pages") and str(r["pages"]) != "None" else ""
    return f"{authors}. {title}. {journal}. {r['year']}{vol}{issue}{pages}. doi:{r['doi']}"


# ---------------------------------------------------------------- the document
def new_doc():
    d = Document()
    style = d.styles["Normal"]
    style.font.name, style.font.size = "Times New Roman", Pt(11)
    for s in d.sections:
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Cm(2.5)
    return d


def para(d, text, bold=False, italic=False, align=None, size=None):
    text = re.sub(r"([.,;]) (\[\d+(?:,\d+)*\])", lambda m: " " + m.group(2) + m.group(1), text)          # a citation goes before the punctuation
    assert "not estimable (" not in text and "nan" not in text.lower().split(), text[:80]
    p = d.add_paragraph()
    r = p.add_run(text)
    r.bold, r.italic = bold, italic
    if size:
        r.font.size = Pt(size)
    if align:
        p.alignment = align
    return p


def table(d, title, header, rows, notes=()):
    para(d, title, bold=True)
    t = d.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    for i, h in enumerate(header):
        t.rows[0].cells[i].text = h
    for row in rows:
        cells = t.add_row().cells
        assert len(row) == len(header), (title, row)
        for i, v in enumerate(row):
            cells[i].text = str(v)
            if i:
                cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for c in (c for r in t.rows for c in r.cells):
        for p in c.paragraphs:
            for run in p.runs:
                run.font.size = Pt(9)
    for note in notes:
        para(d, note, size=9)
    d.add_paragraph()


def figure(d, name, title, notes=()):
    d.add_picture(str(OUT / f"{name}.png"), width=Cm(16))
    para(d, title, bold=True)
    for note in notes:
        para(d, note, size=9)
    d.add_paragraph()


for part in ("text.py", "text_results.py", "text_discussion.py", "text_supplement.py"):          # the text, kept apart from the machinery; the parts share one namespace
    exec(compile((HERE / part).read_text(encoding="utf-8"), part, "exec"))
body = [p.text for p in d.paragraphs]
start, end = body.index("Introduction"), body.index("References")
words_text = sum(len(t.split()) for t in body[start:end] if not t.startswith(("Table ", "Figure ")))
report = {"words_introduction_to_conclusion": words_text, "words_all_paragraphs": sum(len(t.split()) for t in body), "references": len(order), "reference_keys": order,
          "tables": sum(t.startswith("Table ") for t in body), "figures": sum(t.startswith("Figure ") for t in body),
          "supplementary_tables": sum(p.text.startswith("Supplementary Table ") for p in s.paragraphs), "supplementary_figures": sum(p.text.startswith("Supplementary Figure ") for p in s.paragraphs)}
(OUT / "build_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print({k: v for k, v in report.items() if k != "reference_keys"})
