"""Does CIHA's MUNIC_RES record where the patient lives?

Usage: python scripts/ciha_residence_check.py UF [UF ...]

Births linked deterministically to CIHA delivery admissions (keys: the
mother's birth date, the hospital, the day; residence is not a key) carry two
residences for the same woman: SINASC's, from the birth declaration, and
CIHA's. If private-hospital mothers simply live where their hospitals are,
SINASC shows it too; if CIHA's field holds the hospital's municipality, the two
diverge exactly where SINASC places the mother elsewhere.
EVALUATION 2026-09-30, "CIHA's residence field tested against SINASC".
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc

from pegasus_data import link, role_table

OUT = Path(__file__).resolve().parents[1] / "data" / "probes" / "linkage"
UNFILLED = {None, "", "000000", "999999"}


def _ids(t: pa.Table) -> list[str]:
    return pc.binary_join_element_wise(t.column("_blob_sha256"),
                                       pc.cast(t.column("_row"), pa.string()), ":").to_pylist()


def check(uf: str) -> dict[str, object]:
    r = link("sinasc_births_to_ciha_delivery", period="2022", geography=uf, method="deterministic",
             allow_not_viable=True, allow_partial=True)
    pairs = list(zip(r.pairs.column("l").to_pylist(), r.pairs.column("r").to_pylist(), strict=True))
    sn = role_table("SINASC-DN", period="2022", geography=uf, allow_partial=True)
    sinasc = dict(zip(_ids(sn), sn.column("mother.residence").to_pylist(), strict=True))
    ci = role_table("CIHA", period="2022", geography=uf, allow_partial=True)
    ciha = dict(zip(_ids(ci), zip(ci.column("patient.residence").to_pylist(),
                                  ci.column("admission.facility_municipality").to_pylist(), strict=True),
                    strict=True))
    c: dict[str, object] = dict.fromkeys(
        ["pairs", "sinasc_res_eq_hosp", "ciha_filled", "ciha_res_eq_hosp", "ciha_res_eq_sinasc",
         "sinasc_elsewhere", "elsewhere_ciha_filled", "elsewhere_ciha_eq_hosp", "elsewhere_ciha_eq_sinasc"], 0)
    c["pairs"] = len(pairs)
    for left, right in pairs:
        s = sinasc.get(left)
        cres, hosp = ciha.get(right, (None, None))
        if s is None or hosp is None:
            continue
        s6, h6 = str(s)[:6], str(hosp)[:6]
        filled = cres not in UNFILLED
        c6 = str(cres)[:6] if filled else None
        c["sinasc_res_eq_hosp"] += s6 == h6
        if filled:
            c["ciha_filled"] += 1
            c["ciha_res_eq_hosp"] += c6 == h6
            c["ciha_res_eq_sinasc"] += c6 == s6
        if s6 != h6:
            c["sinasc_elsewhere"] += 1
            if filled:
                c["elsewhere_ciha_filled"] += 1
                c["elsewhere_ciha_eq_hosp"] += c6 == h6
                c["elsewhere_ciha_eq_sinasc"] += c6 == s6
    c["verdict"] = r.verdict
    return c


def main(ufs: list[str]) -> None:
    warnings.simplefilter("ignore")
    out = {}
    for uf in ufs:
        out[uf] = check(uf)
        print(uf, json.dumps(out[uf]), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"ciha_residence_test_{'_'.join(ufs)}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
