"""
Premier League 2026/2027 - Attacking Zones Pitch Visualization
=================================================================

Given a match id, reads its JSON from `match_details/{match_id}.json`
(already downloaded by the fotmob scraper) and draws two separate pitch
figures - one for the home team, one for the away team - showing what
percentage of each team's attacks came down the left, center, and right
thirds of the pitch (content.attackingZones.total).

Usage:
    python attacking_zones_plot.py 5795363

Output (in the current directory):
    attacking_zones_5795363_home.png
    attacking_zones_5795363_away.png

Note on orientation: FotMob's "left/center/right" attacking zones are
fixed to the broadcast camera view, not to each team's attacking
direction (this is why an away team's split can flip almost entirely
after half time, when they switch ends). This script draws the three
thirds top-to-bottom on the pitch as left/center/right in that same
camera-fixed sense - it does not attempt to re-orient them per team.
"""

import sys
import json
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from mplsoccer import Pitch

MATCH_DETAILS_DIR = Path("match_details")
LOGO_CACHE_DIR = Path("team_logos")
LOGO_CACHE_DIR.mkdir(exist_ok=True)

# Colors per team side - tweak as desired
HOME_COLOR = "#d64541"
AWAY_COLOR = "#4c9be8"


def load_match(match_id):
    path = MATCH_DETAILS_DIR / f"{match_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Could not find {path}. Make sure the fotmob scraper has "
            f"already downloaded this match's details."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_team_names(data):
    general = data.get("general", {}) if isinstance(data, dict) else {}
    home_name = (general.get("homeTeam") or {}).get("name", "Home")
    away_name = (general.get("awayTeam") or {}).get("name", "Away")
    return home_name, away_name


def get_team_logo_urls(data):
    """
    Team logo URLs live in header.teams (one entry per team, in home/away
    order), e.g. header.teams[0].imageUrl. Match them up against
    general.homeTeam/awayTeam by team id to be safe about ordering.
    """
    general = data.get("general", {}) if isinstance(data, dict) else {}
    home_id = (general.get("homeTeam") or {}).get("id")
    away_id = (general.get("awayTeam") or {}).get("id")

    header_teams = data.get("header", {}).get("teams", [])
    home_url, away_url = None, None
    for team in header_teams:
        if team.get("id") == home_id:
            home_url = team.get("imageUrl")
        elif team.get("id") == away_id:
            away_url = team.get("imageUrl")

    return home_url, away_url


def load_team_logo(team_id, logo_url):
    """
    Downloads a team's logo (caching it locally as team_logos/{id}.png so
    repeat runs don't re-fetch it) and returns it as an RGBA numpy array
    ready for ax.imshow, or None if it couldn't be fetched.
    """
    if not logo_url:
        return None

    cache_path = LOGO_CACHE_DIR / f"{team_id}.png"

    if cache_path.exists():
        img = Image.open(cache_path).convert("RGBA")
    else:
        try:
            response = requests.get(
                logo_url,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            response.raise_for_status()
            img = Image.open(BytesIO(response.content)).convert("RGBA")
            img.save(cache_path)
        except Exception as e:
            print(f"  warning: could not download logo from {logo_url} ({e})")
            return None

    return np.array(img)


def plot_attacking_zones(match_id, side, team_name, zone_pcts, color, out_path, attack_rightward, logo_img=None):
    """
    zone_pcts: dict with 'left', 'center', 'right' percentages (0-100).
    Draws three horizontal lanes across the pitch (left/center/right
    thirds of pitch width). In each lane, an arrow shows the team's
    attacking direction; the arrow's thickness/head size scales with
    that lane's percentage, so thicker arrows = more attacks from there.

    logo_img: optional RGBA numpy array (from load_team_logo) drawn
    faintly in the center of the pitch, behind the arrows/text, as a
    watermark-style background.

    attack_rightward: True to point arrows left-to-right (used for the
    home team by convention), False for right-to-left (away team).
    Note this is a simplifying visual convention - FotMob's left/center/
    right zones are fixed to the camera view, not to which end a team
    is actually attacking (see the halftime-flip behavior discussed
    earlier), so this arrow direction does not represent a verified fact
    about the match, only a consistent way to visualize "this team's
    attacks, going this way."
    """
    pitch = Pitch(pitch_type="opta", pitch_color="#0e1117", line_color="#c7d5cc")
    fig, ax = pitch.draw(figsize=(10.5, 7))
    fig.patch.set_facecolor("#0e1117")

    # Logo watermark, centered on the pitch, drawn first so everything
    # else layers on top of it. Pitch coordinates are not square (opta's
    # 0-100 x/y represents a ~105m x 68m rectangle), so a naive equal
    # width/height box in data units renders squashed. Correct for this
    # using the axes' aspect ratio plus the logo's own pixel aspect ratio,
    # so the watermark keeps its true proportions on screen.
    if logo_img is not None:
        aspect_val = ax.get_aspect()
        try:
            aspect_val = float(aspect_val)
        except (TypeError, ValueError):
            aspect_val = 68 / 105  # fallback: standard pitch width/length ratio

        img_h, img_w = logo_img.shape[0], logo_img.shape[1]
        pixel_aspect = img_w / img_h  # >1 = wider than tall

        logo_width_units = 32  # tune this to resize the watermark
        logo_height_units = logo_width_units / (aspect_val * pixel_aspect)

        cx, cy = 50, 50
        ax.imshow(
            logo_img,
            extent=(
                cx - logo_width_units / 2,
                cx + logo_width_units / 2,
                cy - logo_height_units / 2,
                cy + logo_height_units / 2,
            ),
            alpha=0.25,
            zorder=1,
            aspect="auto",
        )

    # Lanes span the full pitch length (x: 0-100), one third of width each
    # (y: 0-100). Order top-to-bottom: left, center, right.
    band_order = [("left", 66.667, 100), ("center", 33.333, 66.667), ("right", 0, 33.333)]

    max_pct = max(zone_pcts.values()) if zone_pcts else 1
    x_start, x_end = (12, 88) if attack_rightward else (88, 12)

    for label, y_start, y_end in band_order:
        pct = zone_pcts.get(label, 0) or 0
        y_mid = (y_start + y_end) / 2
        strength = pct / max_pct if max_pct else 0

        arrow = patches.FancyArrowPatch(
            (x_start, y_mid),
            (x_end, y_mid),
            arrowstyle="-|>",
            mutation_scale=20 + strength * 40,   # head size scales with %
            linewidth=1.5 + strength * 8,         # shaft thickness scales with %
            color=color,
            alpha=0.35 + 0.6 * strength,
            zorder=3,
        )
        ax.add_patch(arrow)

        ax.text(
            50,
            y_mid + 6 if attack_rightward else y_mid - 6,
            f"{label.capitalize()}: {pct:.0f}%",
            ha="center",
            va="center",
            fontsize=13,
            color="white",
            fontweight="bold",
            zorder=4,
        )

        # faint lane divider for readability
        ax.axhline(y_start, color="white", alpha=0.08, linewidth=0.8, zorder=2)

    ax.set_title(
        f"{team_name} - Attacking Zones ({side})",
        color="white",
        fontsize=14,
        pad=12,
    )

    legend_patch = patches.Patch(color=color, label=team_name)
    legend = ax.legend(
        handles=[legend_patch],
        loc="upper left",
        facecolor="#0e1117",
        edgecolor="white",
        labelcolor="white",
    )

    plt.savefig(out_path, dpi=200, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python attacking_zones_plot.py <match_id>")
        sys.exit(1)

    match_id = sys.argv[1]
    data = load_match(match_id)

    zones = data.get("content", {}).get("attackingZones")
    if not zones:
        raise ValueError(f"No content.attackingZones found for match {match_id}")

    home_name, away_name = get_team_names(data)
    general = data.get("general", {})
    home_id = (general.get("homeTeam") or {}).get("id")
    away_id = (general.get("awayTeam") or {}).get("id")

    home_logo_url, away_logo_url = get_team_logo_urls(data)
    home_logo_img = load_team_logo(home_id, home_logo_url)
    away_logo_img = load_team_logo(away_id, away_logo_url)

    home_total = zones.get("home", {}).get("total", {})
    away_total = zones.get("away", {}).get("total", {})

    plot_attacking_zones(
        match_id, "home", home_name, home_total, HOME_COLOR,
        f"attacking_zones_{match_id}_home.png", attack_rightward=True,
        logo_img=home_logo_img,
    )
    plot_attacking_zones(
        match_id, "away", away_name, away_total, AWAY_COLOR,
        f"attacking_zones_{match_id}_away.png", attack_rightward=False,
        logo_img=away_logo_img,
    )


if __name__ == "__main__":
    main()