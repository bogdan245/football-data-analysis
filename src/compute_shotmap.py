"""
Premier League 2026/2027 - Aggregate Shotmap
==============================================

Reads every match JSON in `match_details/` (produced by the fotmob scraper),
pulls out every shot taken by every player in every match, and plots them
all on a single pitch:

  - Shots (Miss, AttemptSaved, BlockedShot, Post, etc.) -> circles
  - Goals (Goal, OwnGoal)                                -> stars

Marker size is scaled by expected goals (xG) in both cases.

COORDINATE NOTES
-----------------
FotMob renders its own shotmap on an SVG pitch sized 105 x 68 (standard
real-world pitch dimensions in meters - confirmed via the <rect width="105"
height="68"> element on the FotMob match page), NOT a normalized 0-100 Opta
scale. Shot x/y values in the JSON are already in this 105 x 68 coordinate
space.

This matters a lot: values like x=100.26 or x=104.34 that looked like
"overshoot past a 0-100 boundary" were never actually invalid - they're
perfectly normal locations on a 105-long pitch (e.g. x=100 is ~5m from the
goal line, not on/past it). Clamping those down to 100 was the bug - it
was forcing valid coordinates onto a boundary that didn't match the real
pitch dimensions, which is exactly why shots that were clearly not on the
goal line in match footage were rendering as if they were.

The fix: use a 105 x 68 pitch to match FotMob's own coordinate space
directly, and only clamp to that pitch's actual boundaries (which catches
genuinely broken/garbage values, not normal shot locations).

Usage:
    python shotmap_all_matches.py
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from mplsoccer import Pitch, FontManager

fm_rubik = FontManager(
    "https://raw.githubusercontent.com/google/fonts/main/ofl/"
    "rubikmonoone/RubikMonoOne-Regular.ttf"
)

MATCH_DETAILS_DIR = Path("match_details")

# Event types that count as a goal (own goals still show up as "Goal" for
# the scoring player in most cases, but we include OwnGoal defensively in
# case FotMob tags it separately for the player who put it in their own net)
GOAL_EVENT_TYPES = {"Goal", "OwnGoal"}

# Minimum marker size, so very-low-xG shots (e.g. long range efforts) are
# still visible on the plot
MIN_MARKER_SIZE = 40
MAX_MARKER_SIZE = 300  # caps visual footprint so high-xG stars can't balloon
                       # past their true coordinate and look like they sit
                       # on/past the goal line when they don't
XG_SIZE_SCALE = 1200

# Real-world pitch dimensions matching FotMob's own SVG rendering
# (<rect width="105" height="68">). Shot x/y in the JSON are already in
# this coordinate space - no Opta 0-100 normalization involved.
PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0

# Pitch boundaries - only used to catch genuinely broken/garbage values
# (e.g. sensor glitches), not normal shot locations. A small allowance
# past the nominal edge covers legitimate close-range/on-the-line shots
# without distorting real coordinates.
X_CLAMP_MIN, X_CLAMP_MAX = -2.0, PITCH_LENGTH + 2.0
Y_CLAMP_MIN, Y_CLAMP_MAX = -2.0, PITCH_WIDTH + 2.0

# Small drawing padding so markers sitting exactly on the goal line /
# touchline aren't visually cut off by the pitch outline itself.
PITCH_PAD = 2

# Logo watermark - path to your logo file (place it next to this script,
# or update the path). Set to None to disable.
LOGO_PATH = Path("logo.png")
LOGO_POSITION = [0.84, 0.83, 0.14, 0.14]  # [left, bottom, width, height] in figure-fraction coords


def iter_player_entries(player_stats):
    """player_stats can be a dict keyed by player id, or already a list."""
    if isinstance(player_stats, dict):
        return player_stats.values()
    return player_stats


def clamp_x(value, minimum=X_CLAMP_MIN, maximum=X_CLAMP_MAX):
    return max(minimum, min(maximum, value))


def clamp_y(value, minimum=Y_CLAMP_MIN, maximum=Y_CLAMP_MAX):
    return max(minimum, min(maximum, value))


def load_all_shots():
    """
    Walk every match_details/*.json file and collect every shot from every
    player's shotmap, tagging each shot with the match id and player name
    for reference/debugging.
    """
    all_shots = []

    match_files = sorted(MATCH_DETAILS_DIR.glob("*.json"))
    if not match_files:
        raise FileNotFoundError(
            f"No JSON files found in {MATCH_DETAILS_DIR}/ - run the fotmob "
            "scraper first."
        )

    skipped_missing_coords = 0
    adjusted_coordinates = 0

    for match_file in match_files:
        with open(match_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        try:
            player_stats = data["content"]["playerStats"]
        except (KeyError, TypeError):
            print(f"  skipping {match_file.name}: no content.playerStats found")
            continue

        match_id = match_file.stem

        # Try to build a human-readable "Home vs Away" label for this match.
        general = data.get("general", {}) if isinstance(data, dict) else {}
        home_name = (general.get("homeTeam") or {}).get("name")
        away_name = (general.get("awayTeam") or {}).get("name")
        if home_name and away_name:
            match_label = f"{home_name} vs {away_name}"
        else:
            match_label = f"match {match_id}"

        for player in iter_player_entries(player_stats):
            if not isinstance(player, dict):
                continue
            player_name = player.get("name", "Unknown")
            shots = player.get("shotmap", []) or []

            for shot in shots:
                raw_x = shot.get("x")
                raw_y = shot.get("y")

                if raw_x is None or raw_y is None:
                    skipped_missing_coords += 1
                    continue

                try:
                    original_x = float(raw_x)
                    original_y = float(raw_y)
                except (TypeError, ValueError):
                    skipped_missing_coords += 1
                    continue

                x = clamp_x(original_x)
                y = clamp_y(original_y)

                if x != original_x or y != original_y:
                    adjusted_coordinates += 1

                all_shots.append(
                    {
                        "match_id": match_id,
                        "match_label": match_label,
                        "player": player_name,
                        "x": x,
                        "y": y,
                        "original_x": original_x,
                        "original_y": original_y,
                        "xg": float(shot.get("expectedGoals") or 0.0),
                        "event": shot.get("eventType", "Unknown"),
                        "is_own_goal": bool(shot.get("isOwnGoal")),
                        "min": shot.get("min"),
                        "min_added": shot.get("minAdded"),
                    }
                )

    print(f"Loaded {len(all_shots)} shots from {len(match_files)} match files.")
    if skipped_missing_coords:
        print(f"  skipped {skipped_missing_coords} shot(s) with missing/invalid coordinates")
    if adjusted_coordinates:
        print(f"  clamped {adjusted_coordinates} genuinely out-of-range coordinate(s) "
              f"(x outside [{X_CLAMP_MIN}, {X_CLAMP_MAX}] or y outside [{Y_CLAMP_MIN}, {Y_CLAMP_MAX}])")

    return all_shots


def format_minute(shot):
    minute = shot.get("min")
    added = shot.get("min_added")
    if minute is None:
        return "?'"
    if added:
        return f"{minute}+{added}'"
    return f"{minute}'"


def marker_size(xg):
    return min(MIN_MARKER_SIZE + xg * XG_SIZE_SCALE, MAX_MARKER_SIZE)


def plot_shotmap(all_shots):
    goal_shots = [s for s in all_shots if s["event"] in GOAL_EVENT_TYPES]
    non_goal_shots = [s for s in all_shots if s["event"] not in GOAL_EVENT_TYPES]

    # isOwnGoal is the authoritative flag; eventType == "OwnGoal" is a
    # fallback in case FotMob tags it that way instead for some matches.
    own_goal_shots = [s for s in goal_shots if s["is_own_goal"] or s["event"] == "OwnGoal"]
    regular_goal_shots = [s for s in goal_shots if s not in own_goal_shots]

    print(f"  goals: {len(goal_shots)} ({len(own_goal_shots)} own goals)")
    print(f"  other shots: {len(non_goal_shots)}")

    # Custom pitch matching FotMob's own 105 x 68 SVG rendering - shot x/y
    # from the JSON plug in directly, no rescaling needed. Padding lets
    # markers right on the goal line / touchline render fully.
    pitch = Pitch(
        pitch_type="custom",
        pitch_length=PITCH_LENGTH,
        pitch_width=PITCH_WIDTH,
        pitch_color="#0e1117",
        line_color="#c7d5cc",
        pad_left=PITCH_PAD,
        pad_right=PITCH_PAD,
        pad_bottom=PITCH_PAD,
        pad_top=PITCH_PAD,
    )
    fig, ax = pitch.draw(figsize=(10.5, 7))
    fig.patch.set_facecolor("#0e1117")

    # --- Non-goal shots: circles, sized by xG ---
    if non_goal_shots:
        pitch.scatter(
            [s["x"] for s in non_goal_shots],
            [s["y"] for s in non_goal_shots],
            ax=ax,
            s=[marker_size(s["xg"]) for s in non_goal_shots],
            marker="o",
            color="#4c9be8",
            edgecolors="white",
            linewidths=0.5,
            alpha=0.6,
            label="Shot",
        )

    # --- Goals: stars, sized by xG (yellow for regular goals) ---
    if regular_goal_shots:
        pitch.scatter(
            [s["x"] for s in regular_goal_shots],
            [s["y"] for s in regular_goal_shots],
            ax=ax,
            s=[marker_size(s["xg"]) for s in regular_goal_shots],
            marker="*",
            color="#f4d03f",
            edgecolors="black",
            linewidths=0.6,
            alpha=0.95,
            label="Goal",
        )

    # --- Own goals: stars, sized by xG (red, plotted separately) ---
    if own_goal_shots:
        pitch.scatter(
            [s["x"] for s in own_goal_shots],
            [s["y"] for s in own_goal_shots],
            ax=ax,
            s=[marker_size(s["xg"]) for s in own_goal_shots],
            marker="*",
            color="#e74c3c",
            edgecolors="black",
            linewidths=0.6,
            alpha=0.95,
            label="Own Goal",
        )

    if goal_shots:
        # Number each goal on the plot and print a lookup table to the
        # console, so you can cross-reference any star back to its exact
        # match/player - useful for spot-checking coordinate accuracy.
        print("\nGoal lookup (number -> match):")
        for i, s in enumerate(goal_shots, start=1):
            ax.annotate(
                str(i),
                xy=(s["x"], s["y"]),
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=6,
                color="white",
                fontweight="bold",
            )

            coordinate_note = ""
            if s["original_x"] != s["x"] or s["original_y"] != s["y"]:
                coordinate_note = (
                    f" | original x={s['original_x']:.1f} y={s['original_y']:.1f}"
                )

            own_goal_note = " [OWN GOAL]" if s in own_goal_shots else ""

            print(
                f"  {i:>3}. {s['player']:<22} {s['match_label']:<35} "
                f"{format_minute(s):>6} "
                f"x={s['x']:.1f} y={s['y']:.1f} xG={s['xg']:.2f} "
                f"event={s['event']}{own_goal_note}{coordinate_note}"
            )

    ax.set_title(
        "Premier League 2026/2027 - All Shots (After Matchday 3)",
        fontproperties=fm_rubik.prop,
        size=13,
        color="white",
        pad=12,
    )

    legend = ax.legend(loc="upper left", facecolor="#0e1117", edgecolor="white", labelcolor="white")

    # Legend handles inherit the actual (xG-scaled) marker sizes, which are
    # way too big for a legend swatch - force them down to a fixed size.
    for handle in legend.legend_handles:
        handle.set_sizes([80])

    # --- Logo watermark, top-right corner ---
    if LOGO_PATH and LOGO_PATH.exists():
        logo_ax = fig.add_axes(LOGO_POSITION)
        logo_ax.imshow(mpimg.imread(LOGO_PATH))
        logo_ax.axis("off")

    plt.savefig("Shotmaps/shotmap_round_3.png", dpi=200, facecolor=fig.get_facecolor(), bbox_inches="tight")
    print("Saved shotmap_all_matches.png")
    plt.show()


if __name__ == "__main__":
    shots = load_all_shots()
    plot_shotmap(shots)