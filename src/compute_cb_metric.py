"""
Computes defensive and aerial duel metrics for every centre-back at Euro
2024 (min. 180 minutes played), then ranks Radu Dragusin's values as
percentiles against that population.

Metrics computed:
    - Defensive Duels per 90        (Duel-type events tagged "Tackle")
    - Defensive Duels Won %         (Won / Success outcomes as % of tackles)
    - PAdj Interceptions            (Interceptions/90, adjusted for time
                                      out of possession: PAdj = raw * (50 / OpponentPossession%))
    - Successful Defensive Actions/90  (Interceptions + Blocks + Clearances + Won Tackles)
    - Aerial Duels per 90           (Aerial Lost events + events with an
                                      'aerial_won' flag = True)
    - Aerial Duels Won %            (aerial wins / total aerial duels)

Requires the FULL tournament data downloaded via download_euro2024_data.py
(all 51 matches, not just Romania's):
    data/matches/55/282.json
    data/events/{match_id}.json
    data/lineups/{match_id}.json

Outputs (all in ./output/):
    all_cbs_raw.json                 - every CB found, minutes played, match ids
    all_matches_possession.json      - time-based possession % for all 51 matches
    all_cbs_defensive_metrics.json   - the 6 metrics for every qualified CB
    dragusin_defensive_percentiles.json - Dragusin's raw values + percentile ranks
    cb_scatter_data.json             - positional vs duel-based action rates, all CBs

Usage:
    python3 compute_all_cbs_metrics.py
"""

import json
import os
from collections import defaultdict
from scipy.stats import percentileofscore

DATA_DIR = "data"
OUT_DIR = "output"
DRAGUSIN_ID = 39615
MIN_MINUTES = 180  # qualification threshold (2 full matches)

WIN_OUTCOMES = {"Won", "Success In Play", "Success Out"}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def parse_mmss(s):
    m, sec = s.split(":")
    return int(m) + int(sec) / 60


def match_end_minutes(events):
    half_ends = [e for e in events if e.get("type", {}).get("name") == "Half End"]
    max_period = max(h["period"] for h in half_ends)
    last = next(h for h in half_ends if h["period"] == max_period)
    return last["minute"] + last["second"] / 60


def minutes_played(positions, match_end):
    total = 0.0
    for seg in positions:
        start = parse_mmss(seg["from"])
        end = parse_mmss(seg["to"]) if seg["to"] else match_end
        total += end - start
    return total


def time_based_possession(events):
    """Standard gap-between-events possession calculation (see romania_possession_stats.py)."""
    by_period = defaultdict(list)
    for e in events:
        if e.get("possession_team") is None:
            continue
        by_period[e["period"]].append(e)
    team_seconds = defaultdict(float)
    for period, pevents in by_period.items():
        pevents.sort(key=lambda e: e["index"])
        for i in range(len(pevents) - 1):
            e1, e2 = pevents[i], pevents[i + 1]
            t1 = e1["minute"] * 60 + e1["second"]
            t2 = e2["minute"] * 60 + e2["second"]
            dt = t2 - t1
            if dt <= 0:
                continue
            team_seconds[e1["possession_team"]["name"]] += dt
    return team_seconds


def get_aerial_won_flag(event):
    """Check every nested type-specific dict (pass/clearance/shot/etc.) for 'aerial_won'."""
    for key, val in event.items():
        if isinstance(val, dict) and "aerial_won" in val:
            return val["aerial_won"]
    return None


def find_all_centre_backs(matches):
    """Step 1: find every player whose PRIMARY starting position is a Centre Back,
    across all matches, with total minutes played and the list of match ids."""
    cb_players = defaultdict(lambda: {"name": None, "team": None, "minutes": 0.0, "match_ids": []})

    for m in matches:
        mid = m["match_id"]
        try:
            events = load_json(f"{DATA_DIR}/events/{mid}.json")
            lineups = load_json(f"{DATA_DIR}/lineups/{mid}.json")
        except FileNotFoundError:
            continue
        match_end = match_end_minutes(events)

        for team_lineup in lineups:
            team_name = team_lineup["team_name"]
            for p in team_lineup["lineup"]:
                if not p["positions"]:
                    continue
                if "Center Back" not in p["positions"][0]["position"]:
                    continue
                mins = minutes_played(p["positions"], match_end)
                pid = p["player_id"]
                cb_players[pid]["name"] = p["player_name"]
                cb_players[pid]["team"] = team_name
                cb_players[pid]["minutes"] += mins
                cb_players[pid]["match_ids"].append(mid)

    return cb_players


def compute_all_match_possession(matches):
    """Step 2: time-based possession % for every match (needed for PAdj Interceptions)."""
    match_possession = {}
    for m in matches:
        mid = m["match_id"]
        try:
            events = load_json(f"{DATA_DIR}/events/{mid}.json")
        except FileNotFoundError:
            continue
        poss = time_based_possession(events)
        total = sum(poss.values())
        if total == 0:
            continue
        match_possession[mid] = {team: 100 * secs / total for team, secs in poss.items()}
    return match_possession


def compute_player_metrics(pid, d, match_possession):
    """Step 3: compute all 6 metrics for one qualified CB."""
    team = d["team"]
    minutes = d["minutes"]
    match_ids = d["match_ids"]

    tackles = tackle_wins = interceptions = blocks = clearances = 0
    aerial_wins = aerial_losses = 0
    opp_poss_weighted_sum = 0.0
    total_mins_for_poss = 0.0

    for mid in match_ids:
        events = load_json(f"{DATA_DIR}/events/{mid}.json")
        poss_dict = match_possession.get(str(mid), match_possession.get(mid, {}))
        own_poss = poss_dict.get(team, 50.0)
        opp_poss = 100 - own_poss

        lineups = load_json(f"{DATA_DIR}/lineups/{mid}.json")
        team_lineup = next(t for t in lineups if t["team_name"] == team)
        p_entry = next(pl for pl in team_lineup["lineup"] if pl["player_id"] == pid)
        match_end = match_end_minutes(events)
        match_mins = minutes_played(p_entry["positions"], match_end)

        opp_poss_weighted_sum += opp_poss * match_mins
        total_mins_for_poss += match_mins

        for e in events:
            if e.get("player", {}).get("id") != pid:
                continue
            t = e.get("type", {}).get("name")
            if t == "Duel" and e.get("duel", {}).get("type", {}).get("name") == "Tackle":
                tackles += 1
                if e.get("duel", {}).get("outcome", {}).get("name") in WIN_OUTCOMES:
                    tackle_wins += 1
            elif t == "Duel" and e.get("duel", {}).get("type", {}).get("name") == "Aerial Lost":
                aerial_losses += 1
            elif t == "Interception":
                interceptions += 1
            elif t == "Block":
                blocks += 1
            elif t == "Clearance":
                clearances += 1

            if get_aerial_won_flag(e) is True:
                aerial_wins += 1

    avg_opp_poss = opp_poss_weighted_sum / total_mins_for_poss if total_mins_for_poss else 50.0
    duels_per90 = tackles / minutes * 90
    duels_won_pct = (tackle_wins / tackles * 100) if tackles > 0 else None
    raw_int_per90 = interceptions / minutes * 90
    padj_interceptions = raw_int_per90 * (50 / avg_opp_poss)
    successful_actions_per90 = (interceptions + blocks + clearances + tackle_wins) / minutes * 90
    total_aerial = aerial_wins + aerial_losses
    aerial_duels_per90 = total_aerial / minutes * 90
    aerial_won_pct = (aerial_wins / total_aerial * 100) if total_aerial > 0 else None

    return {
        "name": d["name"], "team": team, "minutes": minutes,
        "tackles": tackles, "tackle_wins": tackle_wins,
        "interceptions": interceptions, "blocks": blocks, "clearances": clearances,
        "aerial_wins": aerial_wins, "aerial_losses": aerial_losses,
        "avg_opponent_possession": avg_opp_poss,
        "duels_per90": duels_per90,
        "duels_won_pct": duels_won_pct,
        "padj_interceptions": padj_interceptions,
        "successful_actions_per90": successful_actions_per90,
        "aerial_duels_per90": aerial_duels_per90,
        "aerial_won_pct": aerial_won_pct,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    matches = load_json(f"{DATA_DIR}/matches/55/282.json")

    print("Step 1: finding all centre-backs...")
    cb_players_raw = find_all_centre_backs(matches)
    save_json({str(k): v for k, v in cb_players_raw.items()}, f"{OUT_DIR}/all_cbs_raw.json")
    qualified = {pid: d for pid, d in cb_players_raw.items() if d["minutes"] >= MIN_MINUTES}
    print(f"  Found {len(cb_players_raw)} total, {len(qualified)} qualified (>= {MIN_MINUTES} min)")

    print("Step 2: computing possession for all matches...")
    match_possession = compute_all_match_possession(matches)
    save_json(match_possession, f"{OUT_DIR}/all_matches_possession.json")
    print(f"  Computed possession for {len(match_possession)} matches")

    print("Step 3: computing metrics for all qualified CBs...")
    all_metrics = {}
    for pid, d in qualified.items():
        all_metrics[str(pid)] = compute_player_metrics(pid, d, match_possession)
    save_json(all_metrics, f"{OUT_DIR}/all_cbs_defensive_metrics.json")
    print(f"  Done -> {OUT_DIR}/all_cbs_defensive_metrics.json")

    print("Step 4: computing Dragusin's percentiles...")
    dragusin = all_metrics[str(DRAGUSIN_ID)]
    METRICS = ["duels_per90", "duels_won_pct", "padj_interceptions",
               "successful_actions_per90", "aerial_duels_per90", "aerial_won_pct"]
    percentiles = {}
    for m in METRICS:
        values = [d[m] for d in all_metrics.values() if d.get(m) is not None]
        if dragusin[m] is None:
            percentiles[m] = None
            continue
        percentiles[m] = percentileofscore(values, dragusin[m], kind="mean")
        print(f"  {m}: Dragusin={dragusin[m]:.2f}, percentile={percentiles[m]:.1f} (n={len(values)})")

    save_json({"dragusin_raw": dragusin, "percentiles": percentiles},
               f"{OUT_DIR}/dragusin_defensive_percentiles.json")

    print("Step 5: building positional vs duel-based scatter data...")
    points = []
    for pid, d in all_metrics.items():
        mins = d["minutes"]
        duel_actions = d["tackles"] + d.get("aerial_wins", 0) + d.get("aerial_losses", 0)
        positional_actions = d["interceptions"] + d["blocks"] + d["clearances"]
        points.append({
            "pid": pid, "name": d["name"], "team": d["team"],
            "x": duel_actions / mins * 90, "y": positional_actions / mins * 90,
            "minutes": mins,
        })
    save_json(points, f"{OUT_DIR}/cb_scatter_data.json")
    print(f"  Saved -> {OUT_DIR}/cb_scatter_data.json")


if __name__ == "__main__":
    main()