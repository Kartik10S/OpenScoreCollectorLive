# main_api.py
import os
import json
import datetime
import logging
import asyncio
from fastapi import FastAPI
from main import updateToday  # OpenScoreCollector scraper
from threading import Lock
import time
from logos import TEAM_LOGOS, LEAGUE_LOGOS  # ✅ Import logos

# -----------------------------
# Paths
# -----------------------------
DATA_FOLDER = "data"
SCHEDULES_FOLDER = os.path.join(DATA_FOLDER, "schedules")
STANDINGS_FOLDER = os.path.join(DATA_FOLDER, "standings")

os.makedirs(SCHEDULES_FOLDER, exist_ok=True)
os.makedirs(STANDINGS_FOLDER, exist_ok=True)

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(title="OpenScoreCollector API")

# -----------------------------
# Cache Setup
# -----------------------------
CACHE = {}
CACHE_LOCK = Lock()
CACHE_TTL = 300  # 5 minutes in seconds

def get_cached(key):
    """Return cached data if not expired."""
    with CACHE_LOCK:
        entry = CACHE.get(key)
        if entry and (time.time() - entry["time"]) < CACHE_TTL:
            return entry["data"]
    return None

def set_cache(key, data):
    """Set cache entry."""
    with CACHE_LOCK:
        CACHE[key] = {"data": data, "time": time.time()}

# -----------------------------
# Helper Functions
# -----------------------------
def get_today_json_path():
    today_str = datetime.date.today().strftime("%Y%m%d")
    return os.path.join(SCHEDULES_FOLDER, f"{today_str}.json")

def load_matches_from_json(path: str):
    if not os.path.isfile(path):
        logging.warning(f"No JSON file found at {path}")
        return []

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    matches = []
    for league in data.get("Stages", []):
        league_name = league.get("Snm", "Unknown League")
        league_logo = LEAGUE_LOGOS.get(league_name, league.get("img", ""))  # ✅ Attach logo

        for match in league.get("Events", []):
            home_name = match.get("T1", [{}])[0].get("Nm", "Home")
            away_name = match.get("T2", [{}])[0].get("Nm", "Away")

            matches.append({
                "leagueName": league_name,
                "leagueLogoUrl": league_logo,
                "stadium": match.get("Stadium", ""),
                "homeTeamName": home_name,
                "homeTeamLogoUrl": TEAM_LOGOS.get(home_name, match.get("T1img", "")),  # ✅ Attach team logo
                "awayTeamName": away_name,
                "awayTeamLogoUrl": TEAM_LOGOS.get(away_name, match.get("T2img", "")),  # ✅ Attach team logo
                "matchTime": match.get("Eps", "Not Started"),
                "matchStatus": match.get("Eps", "Not Started"),
                "homeScore": match.get("Tr1", None),
                "awayScore": match.get("Tr2", None),
                "homeScorers": match.get("homeScorers", []),
                "awayScorers": match.get("awayScorers", []),
                "homePossession": match.get("homePossession", None),
                "awayPossession": match.get("awayPossession", None),
                "homeTotalShots": match.get("homeTotalShots", None),
                "awayTotalShots": match.get("awayTotalShots", None),
                "homeShotsOnTarget": match.get("homeShotsOnTarget", None),
                "awayShotsOnTarget": match.get("awayShotsOnTarget", None),
                "homePasses": match.get("homePasses", None),
                "awayPasses": match.get("awayPasses", None),
                "homePassAccuracy": match.get("homePassAccuracy", None),
                "awayPassAccuracy": match.get("awayPassAccuracy", None),
                "homeFouls": match.get("homeFouls", None),
                "awayFouls": match.get("awayFouls", None),
                "homeYellowCards": match.get("homeYellowCards", None),
                "awayYellowCards": match.get("awayYellowCards", None),
                "homeRedCards": match.get("homeRedCards", None),
                "awayRedCards": match.get("awayRedCards", None),
                "homeOffsides": match.get("homeOffsides", None),
                "awayOffsides": match.get("awayOffsides", None),
                "homeCorners": match.get("homeCorners", None),
                "awayCorners": match.get("awayCorners", None),
                "homeLineup": match.get("homeLineup", None),
                "awayLineup": match.get("awayLineup", None),
                "headToHead": match.get("headToHead", None),
                "homeManager": match.get("homeManager", None),
                "awayManager": match.get("awayManager", None),
                "homeSquad": match.get("homeSquad", None),
                "awaySquad": match.get("awaySquad", None),
                "topScorers": match.get("topScorers", None),
                "mostAssists": match.get("mostAssists", None),
                "matchId": match.get("Id", None)
            })
    return matches

def load_match_by_id(match_id: str):
    matches = load_matches_from_json(get_today_json_path())
    for match in matches:
        if str(match.get("matchId")) == str(match_id):
            return match
    return None

def load_standings(league_id: str):
    path = os.path.join(STANDINGS_FOLDER, f"{league_id}.json")
    if not os.path.isfile(path):
        logging.warning(f"No standings for league {league_id}")
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    standings = []
    for team in data.get("teams", []):
        team_name = team.get("teamName")
        standings.append({
            "rank": team.get("rank"),
            "teamId": team.get("teamId"),
            "teamName": team_name,
            "teamAbbreviation": team.get("teamAbbreviation"),
            "teamLogoUrl": TEAM_LOGOS.get(team_name, team.get("teamLogoUrl")),  # ✅ Attach logo
            "gamesPlayed": team.get("gamesPlayed"),
            "wins": team.get("wins"),
            "draws": team.get("draws"),
            "losses": team.get("losses"),
            "goalDifference": team.get("goalDifference"),
            "points": team.get("points")
        })
    return standings

def load_top_scorers(league_id: str):
    path = os.path.join(STANDINGS_FOLDER, f"{league_id}_topscorers.json")
    if not os.path.isfile(path):
        logging.warning(f"No top scorers for league {league_id}")
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    top_scorers = []
    for player in data.get("players", []):
        top_scorers.append({
            "rank": player.get("rank"),
            "playerName": player.get("playerName"),
            "playerTeamLogoUrl": TEAM_LOGOS.get(player.get("playerTeam"), player.get("playerTeamLogoUrl")),  # ✅ Attach logo
            "statValue": player.get("statValue")
        })
    return top_scorers

# -----------------------------
# API Endpoints with Cache
# -----------------------------
@app.get("/api/scores")
def get_scores():
    cached = get_cached("scores")
    if cached:
        return cached
    matches = load_matches_from_json(get_today_json_path())
    set_cache("scores", matches)
    return matches

@app.get("/api/fixtures")
def get_fixtures():
    cached = get_cached("fixtures")
    if cached:
        return cached
    matches = load_matches_from_json(get_today_json_path())
    set_cache("fixtures", matches)
    return matches

@app.get("/api/match/{match_id}")
def get_match_detail(match_id: str):
    key = f"match_{match_id}"
    cached = get_cached(key)
    if cached:
        return cached
    match = load_match_by_id(match_id)
    if match:
        set_cache(key, match)
        return match
    return {"error": "Match not found"}

@app.get("/api/standings/{league_id}")
def get_standings_endpoint(league_id: str):
    key = f"standings_{league_id}"
    cached = get_cached(key)
    if cached:
        return cached
    data = load_standings(league_id)
    set_cache(key, data)
    return data

@app.get("/api/topscorers/{league_id}")
def get_top_scorers_endpoint(league_id: str):
    key = f"topscorers_{league_id}"
    cached = get_cached(key)
    if cached:
        return cached
    data = load_top_scorers(league_id)
    set_cache(key, data)
    return data


@app.route('/api/update', methods=['POST'])
def update():
    try:
        print("Running updateToday()...")  # Debug log
        updateToday()
        print("Fixtures updated successfully")
        return jsonify({"status": "success", "message": "Fixtures updated"}), 200
    except Exception as e:
        import traceback
        print("Error in /api/update:", e)
        traceback.print_exc()  # full error trace in logs
        return jsonify({"status": "error", "message": str(e)}), 500




# -----------------------------
# Background Updater (Optional)
# -----------------------------
async def schedule_updates(interval: int = 300):  # 5 minutes
    while True:
        try:
            updateToday()
            logging.info("Updated today's matches in background")
            # Clear cache after update
            with CACHE_LOCK:
                CACHE.clear()
        except Exception as e:
            logging.error(f"Background update error: {e}")
        await asyncio.sleep(interval)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(schedule_updates())
    logging.info("Background updater started (5-min interval)")
