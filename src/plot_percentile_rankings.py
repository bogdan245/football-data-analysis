"""
Plots the two-panel percentile ranking visualization for Radu Dragusin's
defensive + aerial metrics vs all qualified Euro 2024 centre-backs:
    Left:  Nightingale rose (polar) chart
    Right: Horizontal bar chart
Both panels encode the SAME percentile values -- they are two visual
styles of one result, not two independent findings.

Expects output/dragusin_defensive_percentiles.json
(from compute_all_cbs_metrics.py).

Usage:
    python3 plot_percentile_rankings.py
"""

import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

OUT_DIR = "output"
BG = "#0e1621"
FG = "white"
DEFENCE_COLOR = "#4dabf7"
AERIAL_COLOR = "#ff922b"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    data = load_json(f"{OUT_DIR}/dragusin_defensive_percentiles.json")
    raw = data["dragusin_raw"]
    pct = data["percentiles"]

    METRICS = [
        ("successful_actions_per90", "Successful Defensive\nActions per 90",
         f"{raw['successful_actions_per90']:.2f}", DEFENCE_COLOR),
        ("duels_per90", "Defensive Duels\nper 90",
         f"{raw['duels_per90']:.2f}", DEFENCE_COLOR),
        ("duels_won_pct", "Defensive Duels\nWon %",
         f"{raw['duels_won_pct']:.1f}%", DEFENCE_COLOR),
        ("padj_interceptions", "PAdj\nInterceptions",
         f"{raw['padj_interceptions']:.2f}", DEFENCE_COLOR),
        ("aerial_duels_per90", "Aerial Duels\nper 90",
         f"{raw['aerial_duels_per90']:.2f}", AERIAL_COLOR),
        ("aerial_won_pct", "Aerial Duels\nWon %",
         f"{raw['aerial_won_pct']:.1f}%", AERIAL_COLOR),
    ]

    fig = plt.figure(figsize=(17, 8.5))
    fig.patch.set_facecolor(BG)

    fig.suptitle(
        "Radu Drăgușin — Defensive & Aerial Percentile Rankings and raw values\nvs all Euro 2024 Centre-Backs (min. 180 minutes, n=59)",
        color=FG, fontsize=15, y=0.98, va="top",
    )
    # ---- LEFT: Nightingale rose chart ----
    ax1 = fig.add_subplot(1, 2, 1, projection="polar")
    ax1.set_facecolor(BG)
    ax1.set_theta_offset(np.pi / 2 + np.pi / 6)  # rotate so no wedge sits under the title

    n = len(METRICS)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    width = 2 * np.pi / n * 0.85

    for i, (key, label, val_str, color) in enumerate(METRICS):
        p = pct[key] if pct[key] is not None else 0
        ax1.bar(angles[i], p, width=width, color=color, edgecolor=BG, linewidth=2, alpha=0.9, zorder=2)
        label_r = max(p / 2, 10)
        ax1.text(angles[i], label_r, f"{p:.0f}", ha="center", va="center",
                  color="white", fontsize=12, weight="bold", zorder=3,
                  bbox=dict(boxstyle="round,pad=0.3", facecolor=color, edgecolor="white", linewidth=1))

    ax1.set_xticks(angles)
    ax1.set_xticklabels([m[1] for m in METRICS], color=FG, fontsize=9.5)
    ax1.set_ylim(0, 100)
    ax1.set_yticks([25, 50, 75, 100])
    ax1.set_yticklabels([])
    ax1.grid(color="#2c3542", linewidth=0.7)
    ax1.spines["polar"].set_color("#2c3542")

    # ax1.set_title(
    #     "Drăgușin — Defensive & Aerial Percentile Rankings\n"
    #     "vs all Euro 2024 Centre-Backs (min. 180 minutes, n=59)",
    #     color=FG, fontsize=13, pad=40,
    # )

    legend_elements = [Patch(facecolor=DEFENCE_COLOR, label="Ground Defence"),
                        Patch(facecolor=AERIAL_COLOR, label="Aerial")]
    ax1.legend(handles=legend_elements, loc="upper right", bbox_to_anchor=(1.35, 1.15),
               facecolor=BG, labelcolor=FG, edgecolor="#2c3542", fontsize=9)

    # ---- RIGHT: Horizontal bar chart ----
    ax2 = fig.add_subplot(1, 2, 2)
    ax2.set_facecolor(BG)

    labels = [m[1].replace("\n", " ") for m in METRICS][::-1]
    values = [pct[m[0]] if pct[m[0]] is not None else 0 for m in METRICS][::-1]
    raw_labels = [m[2] for m in METRICS][::-1]
    colors = [m[3] for m in METRICS][::-1]

    y = np.arange(len(labels))
    bars = ax2.barh(y, values, color=colors, height=0.6, zorder=2)

    for yi, v, r in zip(y, values, raw_labels):
        ax2.text(v + 2, yi, r, va="center", ha="left", color="white", fontsize=11, weight="bold")

    ax2.set_yticks(y)
    ax2.set_yticklabels(labels, color=FG, fontsize=11)
    ax2.set_xlim(0, 110)
    ax2.set_xticks([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    ax2.tick_params(colors=FG)
    for spine in ax2.spines.values():
        spine.set_color("#2c3542")
    ax2.grid(axis="x", color="#2c3542", linewidth=0.5, zorder=0)
    ax2.set_xlabel("Percentile Ranking Score", color=FG, fontsize=11)

    # ax2.set_title(
    #     "Drăgușin — Defensive & Aerial Percentile Rankings\n"
    #     "vs all Euro 2024 Centre-Backs (min. 180 minutes, n=59)",
    #     color=FG, fontsize=13, pad=15,
    # )

    fig.text(0.5, 0.02, "Data Source: hudl/open-data (StatsBomb) — Euro 2024. All metrics per 90 unless stated.",
              ha="center", color="#888888", fontsize=9)

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    out_path = f"{OUT_DIR}/dragusin_defensive_percentile_rankings_v2.png"
    fig.savefig(out_path, dpi=200, facecolor=BG, bbox_inches="tight")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()