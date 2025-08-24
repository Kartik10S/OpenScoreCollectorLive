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
from logos import TEAM_LOGOS, LEAGUE_LOGOS

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
        for match in league.get("Events", []):
            matches.append({
                "leagueName": league.get("Snm", "Unknown League"),
                "leagueLogoUrl": league.get("img", ""),
                "stadium": match.get("Stadium", ""),
                "homeTeamName": match.get("T1", [{}])[0].get("Nm", "Home"),
                "homeTeamLogoUrl": match.get("T1img", ""),
                "awayTeamName": match.get("T2", [{}])[0].get("Nm", "Away"),
                "awayTeamLogoUrl": match.get("T2img", ""),
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
        standings.append({
            "rank": team.get("rank"),
            "teamId": team.get("teamId"),
            "teamName": team.get("teamName"),
            "teamAbbreviation": team.get("teamAbbreviation"),
            "teamLogoUrl": team.get("teamLogoUrl"),
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
            "playerTeamLogoUrl": player.get("playerTeamLogoUrl"),
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
    fixtures = []
    for file in os.listdir(FIXTURES_FOLDER):
        if file.endswith(".json"):
            path = os.path.join(FIXTURES_FOLDER, file)
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)

                for match in data:
                    league_name = match.get("leagueName", "")
                    match["leagueLogoUrl"] = LEAGUE_LOGOS.get(league_name, "")

                    # Replace team logos
                    home = match.get("homeTeamName", "")
                    away = match.get("awayTeamName", "")
                    match["homeTeamLogoUrl"] = TEAM_LOGOS.get(home, "")
                    match["awayTeamLogoUrl"] = TEAM_LOGOS.get(away, "")

                    fixtures.append(match)
            except Exception as e:
                logging.error(f"Error reading fixtures {file}: {e}")
    return fixtures

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

@app.get("/api/standings")
def get_all_standings():
    """Return standings for all leagues"""
    all_standings = {}
    for file in os.listdir(STANDINGS_FOLDER):
        if file.endswith(".json") and not file.endswith("_topscorers.json"):
            league_id = file.replace(".json", "")
            all_standings[league_id] = load_standings(league_id)
    return all_standings

@app.get("/api/topscorers/{league_id}")
def get_top_scorers_endpoint(league_id: str):
    key = f"topscorers_{league_id}"
    cached = get_cached(key)
    if cached:
        return cached
    data = load_top_scorers(league_id)
    set_cache(key, data)
    return data

@app.get("/api/topscorers")
def get_all_top_scorers():
    """Return top scorers for all leagues"""
    all_scorers = {}
    for file in os.listdir(STANDINGS_FOLDER):
        if file.endswith("_topscorers.json"):
            league_id = file.replace("_topscorers.json", "")
            all_scorers[league_id] = load_top_scorers(league_id)
    return all_scorers


@app.get("/api/leagues")
def get_available_leagues():
    """Return all available leagues with ID, name, and logo if available."""
    leagues = {}

    for file in os.listdir(STANDINGS_FOLDER):
        if file.endswith(".json") and not file.endswith("_topscorers.json"):
            league_id = file.replace(".json", "")
            path = os.path.join(STANDINGS_FOLDER, file)

            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)

                leagues[league_id] = {
                    "leagueId": league_id,
                    "leagueName": data.get("leagueName", f"League {league_id}"),
                    "leagueLogoUrl": data.get("leagueLogoUrl", "")
                }
            except Exception as e:
                logging.error(f"Error reading league file {file}: {e}")
                leagues[league_id] = {
                    "leagueId": league_id,
                    "leagueName": f"League {league_id}",
                    "leagueLogoUrl": ""
                }

    return {"leagues": list(leagues.values())}

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
