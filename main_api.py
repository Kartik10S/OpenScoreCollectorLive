# main_api.py
import os
import json
import datetime
import logging
import asyncio
import time
from fastapi import FastAPI
import requests   # ✅ for Telegram alerts
from config import telegram_bot_token, telegram_chatid   # ✅ load creds
from fastapi.responses import JSONResponse
from main import updateToday  # OpenScoreCollector scraper
from threading import Lock
from logos import TEAM_LOGOS, LEAGUE_LOGOS  # ✅ Import logos


# -----------------------------
# Telegram Error Alert
# -----------------------------
def send_telegram_alert(message: str):
    """Send error alert to Telegram."""
    try:
        url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
        payload = {"chat_id": telegram_chatid, "text": f"⚠️ OpenScoreCollector Error:\n{message}"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Failed to send Telegram alert: {e}")

# -----------------------------
# League Config (for updateToday)
# -----------------------------
LEAGUES = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ita.1": "Serie A",
    "fra.1": "Ligue 1",
    "ger.1": "Bundesliga",
    # Add more leagues as needed
}

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

    # ESPN data structure (saved in updateToday)
    for league in data.get("Stages", []):  # we wrapped events under Stages in updateToday
        league_name = league.get("Snm", "Unknown League")
        league_logo = LEAGUE_LOGOS.get(league_name, "")

        for event in league.get("Events", []):
            competitions = event.get("competitions", [])
            if not competitions:
                continue

            comp = competitions[0]
            competitors = comp.get("competitors", [])

            home_team, away_team = {}, {}
            home_score = away_score = None

            if len(competitors) == 2:
                for c in competitors:
                    if c.get("homeAway") == "home":
                        home_team = c.get("team", {})
                        home_score = c.get("score", None)
                    else:
                        away_team = c.get("team", {})
                        away_score = c.get("score", None)

            matches.append({
                "leagueName": league_name,
                "leagueLogoUrl": league_logo,
                "stadium": comp.get("venue", {}).get("fullName", ""),
                "homeTeamName": home_team.get("displayName", "Home"),
                "homeTeamLogoUrl": TEAM_LOGOS.get(home_team.get("displayName", ""), home_team.get("logo", "")),
                "awayTeamName": away_team.get("displayName", "Away"),
                "awayTeamLogoUrl": TEAM_LOGOS.get(away_team.get("displayName", ""), away_team.get("logo", "")),
                "matchTime": event.get("status", {}).get("type", {}).get("shortDetail", ""),
                "matchStatus": event.get("status", {}).get("type", {}).get("state", "pre"),
                "homeScore": home_score,
                "awayScore": away_score,
                "matchId": event.get("id")
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
    return data.get("teams", [])

def load_top_scorers(league_id: str):
    path = os.path.join(STANDINGS_FOLDER, f"{league_id}_topscorers.json")
    if not os.path.isfile(path):
        logging.warning(f"No top scorers for league {league_id}")
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("players", [])

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

# -----------------------------
# Update Endpoint (Fixed ✅)
# -----------------------------
@app.post("/api/update")
def update():
    try:
        logging.info("Running updateToday()...")
        updateToday()
        logging.info("Fixtures updated successfully")
        return JSONResponse(content={"status": "success", "message": "Fixtures updated"}, status_code=200)
    except Exception as e:
        logging.error(f"Error in /api/update: {e}", exc_info=True)
        send_telegram_alert(str(e))   # ✅ send Telegram alert
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

# -----------------------------
# Background Updater (Optional)
# -----------------------------
async def schedule_updates(interval: int = 300):
    while True:
        try:
            updateToday()
            logging.info("Updated today's matches in background")
            with CACHE_LOCK:
                CACHE.clear()
        except Exception as e:
            logging.error(f"Background update error: {e}")
            send_telegram_alert(f"Background update failed: {e}")  # ✅ alert Telegram
        await asyncio.sleep(interval)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(schedule_updates())
    logging.info("Background updater started (5-min interval)")
