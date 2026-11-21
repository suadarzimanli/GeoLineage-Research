"""
Figures for the paper from the collected item lists and study/results.json.

    python -m study.make_figures              -> ../Paper/figures/fig_*.pdf
    python -m study.make_figures --dark DIR   -> dark-background PNGs (for a website)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from study.analyze import WEEKS, by_city, latest_n, load, sensing_key, ts  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--dark", type=Path, metavar="DIR")
ARGS = ap.parse_args()
DARK = ARGS.dark is not None
OUT = ARGS.dark if DARK else ROOT.parent / "Paper" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
EXT = ".png" if DARK else ".pdf"
if DARK:
    C = ["#3987e5", "#d95926", "#199e70", "#c98500"]
    INK, INK2, GRID, BG = "#f0efec", "#c3c2b7", "#2a2f38", "#14171c"
else:
    C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
    INK, INK2, GRID, BG = "#0b0b0b", "#52514e", "#e6e5e0", "#ffffff"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": INK, "legend.labelcolor": INK,
    "font.family": "DejaVu Sans", "font.size": 8.5, "axes.edgecolor": INK2, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "savefig.bbox": "tight", "savefig.dpi": 300,
})

res = json.loads((ROOT / "study" / "results.json").read_text(encoding="utf-8"))
es_rows, pc_rows = load("earthsearch"), load("planetary")
es = by_city(es_rows)

# ---------- 1. weekly "latest 10" pipeline: how many items each diff reports as added / removed ----------
added, removed = Counter(), Counter()
for items in es.values():
    prev = None
    for d in WEEKS:
        cur = latest_n(items, d)
        if prev is not None:
            added[len(set(cur) - set(prev))] += 1
            removed[len(set(prev) - set(cur))] += 1
        prev = cur
xs = range(0, 11)
fig, ax = plt.subplots(figsize=(6.4, 2.8))
w = 0.38
ax.bar([x - w / 2 for x in xs], [added[x] for x in xs], width=w, color=C[0], label="added")
ax.bar([x + w / 2 for x in xs], [removed[x] for x in xs], width=w, color=C[1], label="removed")
ax.set_xticks(list(xs))
ax.set_xlabel("Items reported per weekly diff (query: newest 10 scenes)")
ax.set_ylabel("Weekly diffs")
e2 = res["e2_window"]
ax.text(0.98, 0.95, f"{e2['weekly_diffs']} weekly diffs, 20 cities, 2025\n"
        f"{e2['removed_sample_still_in_catalog']} of {e2['removed_sample']} sampled 'removed' scenes\nare still in the catalog",
        transform=ax.transAxes, ha="right", va="top", fontsize=7.6, color=INK)
ax.legend(frameon=False, loc="upper left", ncol=2, fontsize=7.6)
ax.set_ylim(0, max(max(added.values()), max(removed.values())) * 1.3)
ax.grid(axis="x", visible=False)
fig.savefig(OUT / ("fig_churn" + EXT))
plt.close(fig)

# ---------- 2. the same scene in two catalogs: recorded acquisition time differs ----------
es_k = {r["scene_key"]: r for r in es_rows}
pc_k = {r["scene_key"]: r for r in pc_rows}
diff_min = [(ts(es_k[k]["datetime"]) - ts(pc_k[k]["datetime"])).total_seconds() / 60 for k in set(es_k) & set(pc_k)]
fig, ax = plt.subplots(figsize=(6.4, 2.6))
ax.hist(diff_min, bins=40, color=C[2])
ax.set_xlabel("Earth Search minus Planetary Computer acquisition time (minutes)")
ax.set_ylabel("Scenes")
e4 = res["e4_identity"]
ax.text(0.98, 0.95, f"{e4['matched_by_product_uri']} scenes matched by product URI\n"
        f"identical item ids: {e4['matched_with_equal_ids']}", transform=ax.transAxes, ha="right", va="top", fontsize=7.6, color=INK)
fig.savefig(OUT / ("fig_crosscatalog" + EXT))
plt.close(fig)

# ---------- 3. reuse by query design ----------
e5 = res["e5_reuse"]
labels = {"latest_10": "Newest 10 scenes", "rolling_30_days": "Last 30 days", "fixed_period_march": "Fixed past period\n(March 2025)"}
fig, ax = plt.subplots(figsize=(6.4, 2.4))
keys = list(labels)
vals = [e5[k]["reuse_share_by_ids"] for k in keys]
bars = ax.barh(range(len(keys)), vals, color=[C[1], C[3], C[2]], height=0.55)
for i, v in enumerate(vals):
    ax.text(v + 1.5, i, f"{v:.1f}%", va="center", fontsize=8, color=INK)
ax.set_yticks(range(len(keys)), [labels[k] for k in keys])
ax.set_xlim(0, 112)
ax.set_xlabel(f"Weekly re-runs that can reuse their output (20 cities, {e5['latest_10']['reruns']} re-runs per design)")
ax.grid(axis="y", visible=False)
ax.invert_yaxis()
fig.savefig(OUT / ("fig_reuse" + EXT))
plt.close(fig)
print("figures written to", OUT)
