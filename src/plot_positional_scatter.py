"""
Plots the "Positional vs Duel-Based Defending" scatter chart: every
qualified Euro 2024 centre-back placed by their duel-based action rate
(x-axis) vs positional action rate (y-axis), with Radu Dragusin
highlighted. Directly visualizes the hypothesis that his defensive
output is anticipation/positioning-driven rather than duel-driven.

    x = (Tackles + Aerial Duels attempted) per 90
    y = (Interceptions + Blocks + Clearances) per 90

Quadrant lines are drawn at the tournament medians.

Expects output/cb_scatter_data.json (from compute_all_cbs_metrics.py).

Usage:
    python3 plot_positional_vs_duel_scatter.py
"""

import json
import numpy as np
import matplotlib.pyplot as plt

OUT_DIR = "output"
BG = "#0e1621"
FG = "white"
DRAGUSIN_COLOR = "#ffd43b"
OTHER_COLOR = "#4dabf7"
DRAGUSIN_ID = "39615"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    points = load_json(f"{OUT_DIR}/cb_scatter_data.json")

    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    median_x = np.median(xs)
    median_y = np.median(ys)

    dragusin = next(p for p in points if p["pid"] == DRAGUSIN_ID)
    others = [p for p in points if p["pid"] != DRAGUSIN_ID]

    fig, ax = plt.subplots(figsize=(11, 9.5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    ax.axvline(median_x, color="#495057", linestyle="--", linewidth=1, zorder=1)
    ax.axhline(median_y, color="#495057", linestyle="--", linewidth=1, zorder=1)

    # Quadrant labels (axes-relative coordinates, so they stay in the corners
    # regardless of the actual data range)
    ax.text(0.98, 0.98, "High positional\nHigh duels\n(all-round)", transform=ax.transAxes,
            ha="right", va="top", color="#868e96", fontsize=10, style="italic", alpha=0.8)
    ax.text(0.02, 0.98, "High positional\nLow duels\n(anticipation-based)", transform=ax.transAxes,
            ha="left", va="top", color="#51cf66", fontsize=10, style="italic", alpha=0.8)
    ax.text(0.98, 0.02, "Low positional\nHigh duels\n(duel-reliant)", transform=ax.transAxes,
            ha="right", va="bottom", color="#ff6b6b", fontsize=10, style="italic", alpha=0.8)
    ax.text(0.02, 0.02, "Low positional\nLow duels\n(low engagement)", transform=ax.transAxes,
            ha="left", va="bottom", color="#868e96", fontsize=10, style="italic", alpha=0.8)

    ax.scatter([p["x"] for p in others], [p["y"] for p in others], s=60, color=OTHER_COLOR,
               alpha=0.6, edgecolors="white", linewidth=0.5, zorder=3, label=f"Other CBs (n={len(others)})")

    ax.scatter([dragusin["x"]], [dragusin["y"]], s=350, color=DRAGUSIN_COLOR,
               edgecolors="white", linewidth=2, zorder=5, label="Drăgușin")
    ax.annotate("Drăgușin", (dragusin["x"], dragusin["y"]),
                xytext=(dragusin["x"] + 0.4, dragusin["y"] + 0.6),
                color=DRAGUSIN_COLOR, fontsize=13, weight="bold", zorder=6)

    # Label the 2 most extreme players in each quadrant (by distance from the median
    # crossing point), so the reader can see who anchors each corner of the space.
    quadrants = {"pp": [], "pn": [], "np": [], "nn": []}  # (x>=med,y>=med),(x<med,y>=med),(x>=med,y<med),(x<med,y<med)
    for p in others:
        key = ("p" if p["x"] >= median_x else "n") + ("p" if p["y"] >= median_y else "n")
        p["dist"] = ((p["x"] - median_x) ** 2 + (p["y"] - median_y) ** 2) ** 0.5
        quadrants[key].append(p)

    label_offsets = {
        "pp": (0.15, -0.45), "np": (0.15, 0.15), "pn": (0.15, -0.35), "nn": (0.15, -0.35),
    }
    for key, plist in quadrants.items():
        plist.sort(key=lambda p: -p["dist"])
        for p in plist[:2]:
            dx, dy = label_offsets[key]
            # Special-case the single most extreme top-right point, which sits right
            # next to the "High positional / High duels" quadrant text -- push it
            # further down-left so the two don't collide.
            if p["name"] == "Merih Demiral":
                dx, dy = -1.3, -0.5
            ax.annotate(p["name"], (p["x"], p["y"]), xytext=(p["x"] + dx, p["y"] + dy),
                        color="#cfd4da", fontsize=8, zorder=4)

    ax.set_xlabel("Duel-based actions per 90\n(Tackles + Aerial Duels attempted)", color=FG, fontsize=11)
    ax.set_ylabel("Positional actions per 90\n(Interceptions + Blocks + Clearances)", color=FG, fontsize=11)
    ax.tick_params(colors=FG)
    for spine in ax.spines.values():
        spine.set_color("#2c3542")
    ax.grid(color="#2c3542", linewidth=0.5, zorder=0)

    ax.set_title(
        "Positional vs Duel-Based Defending — All Euro 2024 Centre-Backs (n=59, min. 180 min)\n"
        "Drăgușin ranks among the most positionally-oriented, least duel-reliant CBs in the tournament",
        color=FG, fontsize=12.5, pad=15,
    )
    # legend and caption both anchored in axes coordinates (stacked, non-overlapping)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=2,
              facecolor=BG, labelcolor=FG, edgecolor="#2c3542", fontsize=10)
    ax.text(0.5, -0.19, "Data Source: hudl/open-data (StatsBomb) — Euro 2024. Dashed lines = tournament median.",
            transform=ax.transAxes, ha="center", color="#888888", fontsize=9)

    out_path = f"{OUT_DIR}/cb_positional_vs_duel_scatter.png"
    fig.savefig(out_path, dpi=200, facecolor=BG, bbox_inches="tight")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()