"""IBGE's 2022 post-enumeration survey (PES, "PPE"): how complete the 2022 Census was, as published rates.

Source: IBGE, *Pesquisa de Pós-Enumeração do Censo Demográfico 2022*
(https://biblioteca.ibge.gov.br/visualizacao/livros/liv102110.pdf), Tables 1 and 8-12. The survey matches a sample
of 4,795 census tracts person by person (dual-system estimation) and reports, for the *enumerated* population
(195,101,203 people, excluding the 7,979,553 whom the Census imputed in occupied households without an interview),
the **net error rate** ``ε = (N − C) / N``: the share of the true population N that the enumerated count C missed.
It follows that ``N = C / (1 − ε)`` (the report's own equation: net error = (omission − wrongful inclusion) /
(1 − wrongful inclusion)). Imputed people are not added on top: the survey counts the households that gave no
interview as omissions, so the imputed people are part of N − C.

Published margins only (age × sex nationally, state, municipality size class): no cross-classification exists.
``corrected_census`` rakes a cell-wise correction onto all three margins, and says so; its cell values are an
**estimate** (modelled), the margins are IBGE's.
"""

from __future__ import annotations

import numpy as np

URL = "https://biblioteca.ibge.gov.br/visualizacao/livros/liv102110.pdf"
ENUMERATED = 195_101_203
IMPUTED = 7_979_553

#: Table 9: net error (%) by sex (men, women) and 5-year group 0-4 … 75-79, 80+.
NET_ERROR_AGE_SEX = {
    "men": [10.2, 9.0, 8.1, 8.2, 10.6, 10.4, 9.8, 8.7, 8.0, 7.3, 6.6, 5.6, 5.1, 4.5, 4.3, 3.5, 4.1],
    "women": [10.0, 8.8, 8.3, 9.4, 11.2, 10.2, 9.1, 8.1, 7.6, 7.0, 6.3, 5.2, 5.0, 4.2, 3.7, 3.3, 4.5],
}
#: Table 10: net error (%) by state (IBGE code).
NET_ERROR_UF = {
    12: 8.0, 27: 4.8, 16: 10.8, 13: 10.1, 29: 7.4, 23: 7.4, 53: 9.9, 32: 10.0, 52: 7.3, 21: 6.5, 51: 7.3, 50: 7.2,
    31: 6.1, 41: 5.4, 25: 3.8, 15: 9.9, 26: 8.0, 22: 4.1, 24: 6.2, 43: 5.5, 33: 15.5, 11: 11.2, 14: 10.9, 42: 7.4,
    28: 5.8, 35: 10.8, 17: 6.8,
}
#: Table 12: net error (%) by municipality size (people): class upper bounds and rates.
SIZE_BOUNDS = [14_000, 25_000, 45_000, 84_000, 150_000, 274_000, 480_000, 1_000_000]
NET_ERROR_SIZE = [3.9, 4.2, 6.0, 6.2, 7.7, 9.1, 9.5, 10.2, 13.2]
NET_ERROR_BRAZIL = 8.3
#: Table 1: people the Census imputed (households occupied, no interview), by state.
IMPUTED_BY_UF = {
    11: 53_023, 12: 15_259, 13: 94_815, 14: 9_277, 15: 235_688, 16: 18_356, 17: 41_258, 21: 186_000, 22: 61_932,
    23: 263_147, 24: 76_137, 25: 58_687, 26: 270_169, 27: 61_014, 28: 53_928, 29: 293_272, 31: 516_817, 32: 104_361,
    33: 679_330, 35: 3_439_121, 41: 399_027, 42: 228_849, 43: 241_831, 50: 107_541, 51: 147_696, 52: 223_436,
    53: 99_582,
}


def corrected_census(raw: np.ndarray, uf: np.ndarray, iters: int = 200) -> np.ndarray:
    """The PES-corrected 2022 population by (entity, sex, 5-year band) from the raw census counts.

    ``raw`` is (E, 2, 17) counts including the imputed; ``uf`` the state code of each entity. The enumerated count of
    a cell is the raw count less its state's imputed share (spread evenly over the state's cells: the imputed
    people's ages and places are not published). The factor ``1 / (1 − ε)`` of a cell is then fitted as
    ``u(age, sex) · v(state) · w(size class)`` (iterative proportional fitting) so that, summed over all cells,
    each margin equals the enumerated count of that margin divided by ``1 − ε`` of that margin, with the three
    targets brought to the age-sex margin's total."""
    state_total = {u: raw[uf == u].sum() for u in set(int(x) for x in uf)}
    imputed_share = np.array([IMPUTED_BY_UF[int(u)] / state_total[int(u)] for u in uf])
    enum = raw * (1 - imputed_share)[:, None, None]
    # targets
    eps_as = np.stack([NET_ERROR_AGE_SEX["men"], NET_ERROR_AGE_SEX["women"]]) / 100              # (2,17)
    t_as = enum.sum(0) / (1 - eps_as)
    ufs = sorted(set(int(x) for x in uf))
    uf_idx = np.searchsorted(ufs, uf)
    eps_uf = np.array([NET_ERROR_UF[u] for u in ufs]) / 100
    t_uf = np.bincount(uf_idx, enum.sum((1, 2))) / (1 - eps_uf)
    size_pop = raw.sum((1, 2))
    size_idx = np.searchsorted(SIZE_BOUNDS, size_pop)
    eps_sz = np.array(NET_ERROR_SIZE) / 100
    t_sz = np.bincount(size_idx, enum.sum((1, 2)), len(eps_sz)) / (1 - eps_sz)
    total = t_as.sum()
    t_uf *= total / t_uf.sum()
    t_sz *= total / t_sz.sum()
    f = np.ones_like(enum)
    for _ in range(iters):
        cur = (enum * f).sum(0)
        f *= (t_as / np.maximum(cur, 1e-9))[None]
        cur = np.bincount(uf_idx, (enum * f).sum((1, 2)))
        f *= (t_uf / np.maximum(cur, 1e-9))[uf_idx][:, None, None]
        cur = np.bincount(size_idx, (enum * f).sum((1, 2)), len(eps_sz))
        f *= (t_sz / np.maximum(cur, 1e-9))[size_idx][:, None, None]
    return enum * f
