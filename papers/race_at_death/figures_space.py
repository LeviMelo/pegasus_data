"""The figures of space, time and context (maps, panels, models), from results/spatial.json and the result tables beside it.
Run by figures.py; each figure is saved as PNG, PDF and SVG in out/.

Colour: sequential proportions in viridis, signed differences in PuOr, regions in the Okabe-Ito palette (all colour-blind safe).
Geometry: IBGE 2022 municipal mesh (pegasus_data.geography.mesh), Brazil polyconic projection (EPSG:5880).
"""
import json
import math
import warnings
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Patch

from pegasus_data.geography import mesh

warnings.simplefilter("ignore")
HERE = Path(__file__).parent
OUT, RES = HERE / "figures", HERE / "results"
R = json.loads((RES / "results.json").read_text(encoding="utf-8"))
S = json.loads((RES / "spatial.json").read_text(encoding="utf-8"))
E = pd.read_parquet(RES / "municipal_estimates.parquet")
RG = pd.read_parquet(RES / "intermediate_panel.parquet")
RT = pd.read_parquet(RES / "immediate_ratios.parquet")
BP = pd.read_parquet(RES / "border_pairs.parquet")
OKABE = {"North": "#009E73", "Northeast": "#E69F00", "Southeast": "#0072B2", "South": "#CC79A7", "Centre-West": "#D55E00"}
REGION = {1: "North", 2: "Northeast", 3: "Southeast", 4: "South", 5: "Centre-West"}
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})


def save(fig, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


G = mesh("municipality", "minima").to_crs(5880)
G["mun"] = G.code.astype(str).str[:6]
G = G.merge(E, on="mun", how="left")
STATES = mesh("state", "minima").to_crs(5880)
IMM = G.dissolve(by="immediate", as_index=False)[["immediate", "geometry"]]
INT = G.dissolve(by="intermediate", as_index=False)[["intermediate", "geometry"]]


def basemap(ax, title):
    STATES.boundary.plot(ax=ax, color="#222222", lw=0.35)
    ax.set_axis_off()
    ax.set_title(title, fontsize=8, loc="left")


def choropleth(ax, frame, col, cmap, norm, title, label, ticks=None, edge=None):
    frame.plot(column=col, ax=ax, cmap=cmap, norm=norm, lw=0 if edge is None else 0.1, edgecolor=edge or "none", missing_kwds={"color": "#DDDDDD"})
    basemap(ax, title)
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cb = plt.colorbar(sm, ax=ax, orientation="horizontal", fraction=0.045, pad=0.01, shrink=0.8, ticks=ticks)
    cb.set_label(label, fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    return cb


# ---------------------------------------------------------------- Figure 3: the municipality (infant deaths, Brown mothers)
fig, axes = plt.subplots(2, 2, figsize=(7.2, 7.6))
seq = matplotlib.colors.Normalize(0, 0.9)
choropleth(axes[0, 0], G, "PW_mean", "viridis", seq, "A. Certificate: Brown mother, infant certified White",
           "Proportion (BYM2 posterior mean)", ticks=[0, 0.3, 0.6, 0.9])
choropleth(axes[0, 1], G, "famPW_mean", "viridis", seq, "B. Family (census 2010): Brown mother, child White, ages 0-9",
           "Proportion (BYM2 posterior mean)", ticks=[0, 0.3, 0.6, 0.9])
G["diff_PW"] = G.PW_mean - G.famPW_mean
choropleth(axes[1, 0], G, "diff_PW", "PuOr_r", TwoSlopeNorm(vmin=-0.45, vcenter=0, vmax=0.45), "C. Certificate minus family (A - B)",
           "Difference in proportion", ticks=[-0.4, -0.2, 0, 0.2, 0.4])
LISA = {0: ("not significant", "#EEEEEE"), 1: ("high-high", "#B2182B"), 3: ("low-low", "#2166AC"), 2: ("low-high", "#92C5DE"), 4: ("high-low", "#F4A582")}
G["lisa_c"] = G.PW_lisa.map(lambda q: LISA.get(q, ("fewer than 5 linked deaths", "#FFFFFF"))[1] if pd.notna(q) else "#FFFFFF")
G.plot(color=G.lisa_c, ax=axes[1, 1], lw=0)
basemap(axes[1, 1], "D. Local clusters of the empirical-Bayes rate (local Moran, p < 0.05)")
axes[1, 1].legend(handles=[Patch(fc=c, ec="#999999", lw=0.3, label=f"{lab} ({S['lisa']['PW'].get(lab, 0):,})") for k, (lab, c) in LISA.items()]
                  + [Patch(fc="#FFFFFF", ec="#999999", lw=0.3, label="fewer than 5 linked deaths")], fontsize=6.5, frameon=False, loc="lower left")
fig.tight_layout(h_pad=3.0)
save(fig, "map_municipal")

# ---------------------------------------------------------------- Figure 4: composition, state and context
fig = plt.figure(figsize=(7.2, 6.0))
gs = fig.add_gridspec(2, 3, height_ratios=[1.15, 1], hspace=0.55, wspace=0.6)
ax = fig.add_subplot(gs[0, :2])
E["region"] = (E.uf // 10).map(REGION)
for rn, col in OKABE.items():
    x = E[(E.region == rn) & (E.nP > 0)]
    ax.scatter(x.white_share, x.PW_mean, s=np.clip(x.nP, 1, 400) ** 0.5 * 0.9, color=col, alpha=0.45, lw=0, label=rn)
gi = [b for b in R["gradient_infants"] if b["matrix"]["rows"].get("Parda", {}).get("n", 0) >= 100]
ax.plot([b["white_share"] for b in gi], [b["matrix"]["rows"]["Parda"]["Branca"]["est"] for b in gi], "-", color="black", lw=1.6, label="national, by class of composition")
gf = R["census"]["gradient"]["0"]
ax.plot([b["white_share"] for b in gf if "Parda" in b["matrix"]], [b["matrix"]["Parda"].get("Branca", {"est": 0})["est"] for b in gf if "Parda" in b["matrix"]], "--",
        color="black", lw=1.2, label="family (census, under 1 year)")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.set_xlabel("Share of White mothers among the municipality's live births")
ax.set_ylabel("Brown mother, infant certified White")
ax.set_title("A. Municipalities (BYM2 posterior means; area of a point: linked deaths)", fontsize=8, loc="left")
ax.legend(fontsize=6.5, frameon=False, loc="upper left", ncol=2, markerscale=1.5)
# B: what each explanation leaves: Moran's I of residuals and deviance explained
ax = fig.add_subplot(gs[0, 2])
MO = S["moran"]["PW"]
steps = [("none", "none"), ("composition", "composition"), ("state", "state"), ("context", "context"), ("composition_state", "composition\n+ state"),
         ("composition_context", "composition\n+ context"), ("composition_state_context", "all three")]
y = np.arange(len(steps))[::-1]
ax.barh(y, [MO["deviance_explained"][k] for k, _ in steps], color="#999999", height=0.4, label="deviance explained")
ax.plot([MO[k]["I"] for k, _ in steps], y, "o", color="#D55E00", ms=4, label="Moran's I of residuals")
ax.set_yticks(y, [lab for _, lab in steps], fontsize=6.5)
ax.set_xlim(0, 1)
ax.set_title("B. Brown mother, certified White:\nwhat each explanation removes", fontsize=8, loc="left")
ax.legend(fontsize=6, frameon=False, loc="upper center", bbox_to_anchor=(0.4, -0.12), ncol=1)
# C: the border test
ax = fig.add_subplot(gs[1, 0])
q = pd.qcut(BP.dA, 8, duplicates="drop")
bb = BP.groupby(q, observed=True).apply(lambda d: pd.Series({"x": np.average(d.dA, weights=d.w), "y": np.average(d.D, weights=d.w), "se": 1 / np.sqrt(d.w.sum())}))
ax.scatter(BP.dA, BP.D, s=2, color="#BBBBBB", lw=0)
ax.errorbar(bb.x, bb.y, yerr=1.96 * bb.se, fmt="o", color="black", ms=3, capsize=1.5)
xs = np.linspace(BP.dA.min(), BP.dA.max(), 10)
bt = S["border"]["PW"]
ax.plot(xs, xs, ":", color="#0072B2", lw=1, label="full state difference")
ax.plot(xs, bt["slope_state_effect"] * xs, "-", color="#D55E00", lw=1.2, label=f"fitted, slope {bt['slope_state_effect']:.2f}")
ax.set_ylim(-4, 4)
ax.set_xlabel("Difference of the states' effects,\nfrom municipalities away from borders")
ax.set_ylabel("Difference across the border")
ax.set_title(f"C. {bt['pairs']:,} pairs of neighbours\nacross state borders (log-odds)", fontsize=8, loc="left")
ax.legend(fontsize=5.8, frameon=False, loc="upper left")
# D: capital, metropolitan, interior; E: composition by GDP
ax = fig.add_subplot(gs[1, 1])
PL = ["capital", "metropolitan, not capital", "interior"]
for k, (m, c, col, lab) in enumerate((("Parda", "Branca", "#0072B2", "Brown mother, White"), ("Preta", "Preta", "#000000", "Black mother, Black"),
                                      ("Branca", "Branca", "#E69F00", "White mother, White"))):
    v = [S["by_place"][p]["rows"][m][c] for p in PL]
    ax.errorbar(np.arange(3) + (k - 1) * 0.18, [x["est"] for x in v], yerr=[1.96 * x["se"] for x in v], fmt="o", color=col, ms=3.5, capsize=1.5, label=lab)
ax.set_xticks(range(3), ["state\ncapital", "metropolitan,\nnot capital", "interior"], fontsize=6.5)
ax.set_ylim(0, 1)
ax.set_ylabel("Proportion of infant deaths")
ax.set_title("D. Place within\nthe state", fontsize=8, loc="left")
ax.legend(fontsize=5.8, frameon=False, loc="center", bbox_to_anchor=(0.5, 0.5))
ax = fig.add_subplot(gs[1, 2])
for comp, col in zip(("<30%", "30-59%", ">=60%"), ("#D55E00", "#009E73", "#0072B2"), strict=True):
    v = [S["comp_gdp"].get(f"{comp}|{q}", {}).get("rows", {}).get("Parda", {}).get("Branca") for q in ("low", "middle", "high")]
    xs_ = [i for i, x in enumerate(v) if x and x["se"] < 0.1]
    ax.plot(xs_, [v[i]["est"] for i in xs_], "-o", color=col, ms=3.5, label=f"{comp} White births")
ax.set_xticks(range(3), ["low", "middle", "high"])
ax.set_xlabel("Municipal GDP per capita (tertile)")
ax.set_ylim(0, 1)
ax.set_title("E. Brown mother, certified White:\ncomposition and wealth", fontsize=8, loc="left")
ax.legend(fontsize=6, frameon=False, loc="upper left")
save(fig, "composition_state")


# ---------------------------------------------------------------- Figure 6: time by place
def change(df, o):
    a, b = df[f"{o}_intercept"], df[f"{o}_slope"]
    return 1 / (1 + np.exp(-(a + 0.5 * b))) - 1 / (1 + np.exp(-(a - 0.5 * b))), 1 / (1 + np.exp(-(a - 0.5 * b)))


fig = plt.figure(figsize=(7.2, 7.0))
gs = fig.add_gridspec(2, 3, width_ratios=[1.05, 1.35, 0.7], height_ratios=[1, 1.35], hspace=0.38, wspace=0.42)
ax = fig.add_subplot(gs[0, :2])
yrs = sorted(int(y) for y in R["infants"]["by_year"])
for (m, c), col, lab in ((("Branca", "Branca"), "#E69F00", "White mother, certified White"), (("Parda", "Parda"), "#0072B2", "Brown mother, certified Brown"),
                         (("Preta", "Parda"), "#999999", "Black mother, certified Brown"), (("Parda", "Branca"), "#56B4E9", "Brown mother, certified White"),
                         (("Preta", "Preta"), "#000000", "Black mother, certified Black")):
    v = [R["infants"]["by_year"][str(y)]["rows"][m][c] for y in yrs]
    ax.errorbar(yrs, [x["est"] for x in v], yerr=[1.96 * x["se"] for x in v], fmt="-o", ms=2.5, lw=1, color=col, capsize=1, label=lab)
ax.set_ylim(0, 1)
ax.set_xlim(2012.5, 2029.6)
ax.set_xticks(range(2013, 2024, 2))
ax.set_xlabel("Year of death")
ax.set_ylabel("Proportion of infant deaths")
ax.set_title("A. Brazil, by mother's race (linkage)", fontsize=8, loc="left")
ax.legend(fontsize=6, frameon=False, loc="center right")
RG["KK_change"], RG["KK_2013"] = change(RG, "KK")
RG["PW_change"], RG["PW_2013"] = change(RG, "PW")
RG["intermediate"] = RG.intermediate.astype(str)
GI = INT.assign(intermediate=INT.intermediate.astype(str)).merge(RG, on="intermediate", how="left")
ax = fig.add_subplot(gs[1, 1])
choropleth(ax, GI, "KK_change", "PuOr_r", TwoSlopeNorm(vmin=-0.2, vcenter=0, vmax=0.2), "C. Black mother, infant certified\nBlack: change 2013-2023",
           "Change over the decade (model)", ticks=[-0.2, -0.1, 0, 0.1, 0.2], edge="#FFFFFF")
ax = fig.add_subplot(gs[1, 0])
RG["region"] = (RG.intermediate.str[:1].astype(int)).map(REGION)
for rn, col in OKABE.items():
    x = RG[RG.region == rn]
    ax.scatter(x.KK_2013, x.KK_change, s=10, color=col, alpha=0.8, lw=0, label=rn)
ax.axhline(0, color="#999999", lw=0.6)
ax.set_xlabel("Proportion in 2013 (model)")
ax.set_ylabel("Change 2013-2023")
ax.set_title("B. Black mother, certified Black:\n133 intermediate regions", fontsize=8, loc="left")
ax.legend(fontsize=5.8, frameon=False, loc="upper left", markerscale=1.2)
ax = fig.add_subplot(gs[:, 2])
UFN = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
       31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}
H = pd.DataFrame(S["state_year"]["agree"]).T
H = H.loc[[u for u in UFN.values() if u in H.index]]
im = ax.imshow(H.to_numpy(float), aspect="auto", cmap="viridis", vmin=0.4, vmax=0.9)
ax.set_yticks(range(len(H)), H.index, fontsize=6)
cols_ = [int(c) for c in H.columns]
ax.set_xticks([i for i, c in enumerate(cols_) if c % 2 == 1], [str(c) for c in cols_ if c % 2 == 1], fontsize=5.8, rotation=90)
cb = plt.colorbar(im, ax=ax, orientation="horizontal", fraction=0.03, pad=0.07)
cb.set_label("Certified as the\nmother's race", fontsize=6.5)
cb.ax.tick_params(labelsize=6)
ax.set_title("D. State by year,\nall mothers", fontsize=8, loc="left")
for sp_ in ax.spines.values():
    sp_.set_visible(False)
save(fig, "time_place")

# ---------------------------------------------------------------- Figure 5: competing explanations, the multilevel models of linked infants
if "multilevel" in S:
    MLs = S["multilevel"]
    fig = plt.figure(figsize=(7.2, 5.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.35], wspace=0.75)
    ax = fig.add_subplot(gs[0, 0])
    SEQ = [("composition", "composition"), ("socioeconomic", "socioeconomic\nand place"), ("services", "services and\nrecording"),
           ("socioeconomic_services", "socioeconomic\n+ services"), ("composition_socioeconomic", "composition\n+ socioeconomic"),
           ("composition_socioeconomic_services", "composition + socio-\neconomic + services"), ("full", "all, with individual,\nregion and year")]
    OUTS = [("brown_white", "Brown mother, certified White", "#0072B2"), ("black_black", "Black mother, certified Black", "#000000"),
            ("white_white", "White mother, certified White", "#E69F00")]
    y = np.arange(len(SEQ))[::-1]
    for k, (o, lab, col) in enumerate(OUTS):
        if o not in MLs:
            continue
        ax.barh(y + (1 - k) * 0.26, [100 * MLs[o]["sequence"][s_]["pcv"] for s_, _ in SEQ], height=0.25, color=col, label=lab)
    ax.set_yticks(y, [lab for _, lab in SEQ], fontsize=6.5)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Between-municipality variance explained (%)")
    ax.set_title("A. What each set of municipal\nvariables explains", fontsize=8, loc="left")
    ax.legend(fontsize=6, frameon=False, loc="upper center", bbox_to_anchor=(0.4, -0.08))
    ax = fig.add_subplot(gs[0, 1])
    TERMS = [("z_lgdp", "GDP per capita (+1 SD)"), ("z_illit", "illiteracy (+1 SD)"), ("z_urban", "urban share (+1 SD)"), ("z_lpop", "population (+1 SD)"),
             ("capital", "state capital"), ("metro", "metropolitan region"), ("z_phys", "physicians (+1 SD)"), ("z_svo", "verification service share (+1 SD)"),
             ("z_iml", "medical examiner share, external (+1 SD)"), ("z_hosp", "deaths in hospital (+1 SD)"), ("z_blank", "race left blank (+1 SD)"),
             ("certifiermedical examiner (IML)", "certifier: medical examiner"), ("certifierdeath verification service", "certifier: verification service"),
             ("certifiersubstitute physician", "certifier: substitute physician"), ("death_placehome", "died at home"), ("death_placeother health facility", "died in other facility"),
             ("age_group28-364 days", "died at 28-364 days"), ("cause_groupexternal", "external cause"), ("school0-3", "mother 0-3 years of school"),
             ("school12 or more", "mother 12+ years of school"), ("mother_age<20", "mother under 20"), ("low_weight<2500 g", "birth weight < 2500 g"),
             ("yc", "per decade (year)")]
    yy = np.arange(len(TERMS))[::-1]
    for k, (o, lab, col) in enumerate(OUTS[:2]):
        if o not in MLs:
            continue
        fx = MLs[o]["full_fit"]["fixed"]
        for j, (t, _) in enumerate(TERMS):
            if t in fx:
                e_, s_ = fx[t]["est"], fx[t]["se"]
                ax.errorbar([math.exp(e_)], [yy[j] + (0.5 - k) * 0.35], xerr=[[math.exp(e_) - math.exp(e_ - 1.96 * s_)], [math.exp(e_ + 1.96 * s_) - math.exp(e_)]],
                            fmt="o", color=col, ms=3, capsize=1.2, lw=0.9, label=lab if j == 0 else None)
    ax.axvline(1, color="#999999", lw=0.7)
    ax.set_xscale("log")
    ax.set_xticks([0.5, 1, 2], ["0.5", "1", "2"])
    ax.set_xlim(0.4, 2.6)
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_yticks(yy, [lab for _, lab in TERMS], fontsize=6.3)
    ax.set_xlabel("Odds ratio (full model)")
    ax.set_title("B. Full model: municipal and individual terms", fontsize=8, loc="left")
    ax.legend(fontsize=6, frameon=False, loc="lower center", bbox_to_anchor=(0.4, -0.16), ncol=2)
    save(fig, "multilevel")

# ---------------------------------------------------------------- Figure 8: consequences, the mortality ratio by immediate region
fig = plt.figure(figsize=(7.2, 7.4))
gs = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.18)
GR = IMM.merge(RT, on="immediate", how="left")
lr = TwoSlopeNorm(vmin=np.log(1 / 4), vcenter=0, vmax=np.log(4))
ticks = [np.log(v) for v in (1 / 4, 0.5, 1, 2, 4)]
for k, (col, title) in enumerate((("mother_log_rr", "A. By the mother's race"), ("certificate_log_rr", "B. By the race on the certificate"))):
    ax = fig.add_subplot(gs[0, k])
    cb = choropleth(ax, GR, col, "PuOr_r", lr, title, "White to Brown infant rate ratio (BYM2)", ticks=ticks, edge="#FFFFFF")
    cb.ax.set_xticklabels(["1/4", "1/2", "1", "2", "4"])
ax = fig.add_subplot(gs[1, 0])
cb = choropleth(ax, GR, "misstated", "PuOr_r", TwoSlopeNorm(vmin=-1.2, vcenter=0, vmax=1.2), "C. Misstatement: B over A",
                "Ratio of the two rate ratios", ticks=[np.log(v) for v in (0.33, 0.5, 1, 2, 3)], edge="#FFFFFF")
cb.ax.set_xticklabels(["1/3", "1/2", "1", "2", "3"])
ax = fig.add_subplot(gs[1, 1])
ax.set_position([ax.get_position().x0 + 0.08, ax.get_position().y0 + 0.06, ax.get_position().width - 0.08, ax.get_position().height - 0.08])
sc = ax.scatter(RT.white_share, np.exp(RT.misstated), c=np.log10(RT.gdp_pc), cmap="cividis", s=np.clip(RT.births, 1, None) ** 0.5 / 18, alpha=0.85, lw=0)
ax.set_yscale("log")
ax.set_yticks([0.5, 1, 2, 4, 8], ["0.5", "1", "2", "4", "8"])
ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
bins_ = pd.cut(RT.white_share, [0, 0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.75, 0.9, 1.0])
bm = RT.groupby(bins_, observed=True).apply(lambda d: pd.Series({"x": np.average(d.white_share, weights=d.births), "y": np.exp(np.average(d.misstated, weights=d.births))}))
ax.plot(bm.x, bm.y, "-", color="black", lw=1.4, label="mean by class of composition (weighted by births)")
ax.legend(fontsize=6, frameon=False, loc="lower right")
ax.axhline(1, color="#999999", lw=0.6)
ax.set_xlabel("Share of White mothers among live births")
ax.set_ylabel("Certified over mother's-race ratio")
ax.set_title("D. 510 immediate regions: composition and wealth", fontsize=8, loc="left")
cb = plt.colorbar(sc, ax=ax, fraction=0.05, pad=0.02)
cb.set_label("GDP per capita (log10 R$)", fontsize=7)
save(fig, "regional_ratios")

# ---------------------------------------------------------------- Supplementary maps: raw against smoothed, the other cells, local clusters
fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.1))
G["PW_raw"] = np.where(G.nP >= 5, G.PW / G.nP.where(G.nP > 0), np.nan)
choropleth(axes[0], G, "PW_raw", "viridis", seq, "A. Raw proportion\n(5 or more linked deaths)", "Brown mother, certified White", ticks=[0, 0.4, 0.8])
choropleth(axes[1], G, "PW_mean", "viridis", seq, "B. BYM2 posterior mean", "Brown mother, certified White", ticks=[0, 0.4, 0.8])
G["PW_width"] = G.PW_hi - G.PW_lo
choropleth(axes[2], G, "PW_width", "magma_r", matplotlib.colors.Normalize(0, 0.6), "C. Width of the 95%\ncredible interval", "Upper minus lower limit", ticks=[0, 0.2, 0.4, 0.6])
fig.tight_layout()
save(fig, "map_raw")

fig, axes = plt.subplots(2, 2, figsize=(7.2, 7.4))
for ax, (col, title) in zip(axes.flat, (("WW_mean", "A. White mother, infant certified White"), ("WP_mean", "B. White mother, infant certified Brown"),
                                        ("KK_mean", "C. Black mother, infant certified Black"), ("KP_mean", "D. Black mother, infant certified Brown")), strict=True):
    choropleth(ax, G, col, "viridis", matplotlib.colors.Normalize(0, 1), title, "Proportion (BYM2 posterior mean)", ticks=[0, 0.25, 0.5, 0.75, 1])
fig.tight_layout()
save(fig, "map_other_cells")

fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.9))
choropleth(axes[0], G, "disagree_mean", "viridis", matplotlib.colors.Normalize(0, 0.6), "A. Certified race differs from the mother's,\nall linked infant deaths",
           "Proportion (BYM2 posterior mean)", ticks=[0, 0.2, 0.4, 0.6])
G["lisa_d"] = G.disagree_lisa.map(lambda q: LISA.get(q, ("", "#FFFFFF"))[1] if pd.notna(q) else "#FFFFFF")
G.plot(color=G.lisa_d, ax=axes[1], lw=0)
basemap(axes[1], "B. Local clusters (local Moran, p < 0.05)")
axes[1].legend(handles=[Patch(fc=c, ec="#999999", lw=0.3, label=f"{lab} ({S['lisa']['disagree'].get(lab, 0):,})") for k, (lab, c) in LISA.items()],
               fontsize=6.5, frameon=False, loc="lower left")
fig.tight_layout()
save(fig, "map_disagree")
print("spatial figures written")
