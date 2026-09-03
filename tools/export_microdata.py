"""Export PROCESSED MICRODATA -- one DATASUS file, decoded, as a spreadsheet.

This is the source file itself after the pipeline has run: one row per
record exactly as DATASUS published it, with the DBC decompressed, the DBF
decoded, and a `<FIELD>_label` column added beside every coded field whose
codelist is actually bound. No aggregation, no selection of "interesting"
columns, no summary.

DATASUS publishes SIH-RD as one file per UF per competence month
(RDSP2201.dbc = Sao Paulo, January 2022), so that is the natural unit here.

Excel holds 1,048,576 rows. A UF-month is comfortably inside that; a whole
national year is not, and the script refuses rather than silently truncating.

PERSONAL DATA: these are unmodified rows. Nothing is masked, hashed or
dropped -- that is a deliberate project invariant, not an oversight. SIH-RD
carries CEP, date of birth and admission dates. Treat the output as
identifiable data.

Usage::

    python tools/export_microdata.py                          # SIH-RD SP 2022-01
    python tools/export_microdata.py --uf MG --period 2022-03
    python tools/export_microdata.py --dataset SIM-DO --uf AC --period 2022
    python tools/export_microdata.py --csv                    # csv instead
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pegasus_data import query  # noqa: E402

EXCEL_MAX_ROWS = 1_048_576


def fetch(dataset: str, period: str, uf: str):
    # The fallback warnings are informative, not failures: a field whose
    # codelist has no explicit label_of relation keeps its raw code rather
    # than being given a guessed label. Dozens of them drown the output.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return query(dataset, period=period, geography=uf)


def to_csv(table, out: Path) -> None:
    names = table.column_names
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(names)
        for batch in table.to_batches(max_chunksize=20_000):
            cols = [batch.column(i).to_pylist() for i in range(batch.num_columns)]
            w.writerows(zip(*cols))


def to_xlsx(table, out: Path, sheet: str) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    # write_only streams rows instead of holding a cell object for each of
    # the ~23 million here, which is the difference between a minute and
    # running the machine out of memory.
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(sheet[:31])
    ws.freeze_panes = "A2"

    bold = Font(bold=True)
    from openpyxl.cell import WriteOnlyCell

    header = []
    for name in table.column_names:
        c = WriteOnlyCell(ws, value=name)
        c.font = bold
        header.append(c)
    ws.append(header)

    for batch in table.to_batches(max_chunksize=20_000):
        cols = [batch.column(i).to_pylist() for i in range(batch.num_columns)]
        for row in zip(*cols):
            ws.append(list(row))
    wb.save(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="SIH-RD")
    ap.add_argument("--uf", default="SP")
    ap.add_argument("--period", default="2022-01")
    ap.add_argument("--out", default=None)
    ap.add_argument("--csv", action="store_true", help="write CSV (; separated) instead")
    args = ap.parse_args()

    stem = f"{args.dataset}_{args.uf}_{args.period}".replace("-", "")
    suffix = ".csv" if args.csv else ".xlsx"
    out = Path(args.out) if args.out else Path.home() / "Desktop" / f"{stem}{suffix}"

    print(f"querying {args.dataset} {args.uf} {args.period} ...")
    t0 = time.time()
    table = fetch(args.dataset, args.period, args.uf)
    print(f"  {table.num_rows:,} rows x {len(table.column_names)} columns "
          f"in {time.time() - t0:.0f}s")

    if not args.csv and table.num_rows > EXCEL_MAX_ROWS - 1:
        print(
            f"REFUSED: {table.num_rows:,} rows exceeds Excel's "
            f"{EXCEL_MAX_ROWS:,} limit. Narrow the period or UF, or use --csv.",
            file=sys.stderr,
        )
        return 1

    print(f"writing {out.name} ...")
    t0 = time.time()
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.csv:
        to_csv(table, out)
    else:
        to_xlsx(table, out, f"{args.dataset} {args.uf} {args.period}")
    mb = out.stat().st_size / 1_048_576
    print(f"done: {out}  ({mb:.1f} MB, {time.time() - t0:.0f}s)")
    print("NOTE: unmodified microdata - contains identifiable fields.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
