import os
import json
import datetime
import logging
import asyncio
import time
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from threading import Lock
from scraper import updateToday, send_telegram_alert # Import from scraper
from logos import TEAM_LOGOS, LEAGUE_LOGOS

# -----------------------------
# Setup
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
app = FastAPI(title="OpenScoreCollector API")

# -----------------------------
# Paths
# -----------------------------
DATA_FOLDER = "data"
SCHEDULES_FOLDER = os.path.join(DATA_FOLDER, "schedules")
STANDINGS_FOLDER = os.path.join(DATA_FOLDER, "standings")
TOPSCORERS_FOLDER = os.path.join(STANDINGS_FOLDER, "topscorers")

# -----------------------------
# Cache
# -----------------------------
CACHE = {}
CACHE_LOCK = Lock()
CACHE_TTL = 300  # 5 minutes

def get_cached(key):
    with CACHE_LOCK:
        entry = CACHE.get(key)
        if entry and (time.time() - entry["time"]) < CACHE_TTL:
            return entry["data"]
    return None

def set_cache(key, data):
    with CACHE_LOCK:
        CACHE[key] = {"data": data, "time": time.time()}

def clear_cache():
    with CACHE_LOCK:
        CACHE.clear()
    logging.info("Cache cleared.")

# -----------------------------
# Data Loading Helpers
# -----------------------------
def get_today_json_path():
    today_str = datetime.date.today().strftime("%Y%m%d")
    return os.path.join(SCHEDULES_FOLDER, f"{today_str}.json")

def load_matches_from_json():
    path = get_today_json_path()
    if not os.path.isfile(path):
        logging.warning(f"No JSON file found at {path}. Triggering update.")
        try:
            updateToday()
        except Exception as e:
            logging.error(f"Failed to create initial data file: {e}")
            return []

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    matches = []
    for league in data.get("Stages", []):
        league_name = league.get("Snm", "Unknown League")
        league_logo = LEAGUE_LOGOS.get(league_name, "")

        for event in league.get("Events", []):
            home_team_data = event.get("T1", [{}])[0]
            away_team_data = event.get("T2", [{}])[0]
            scores = event.get("Tr1"), event.get("Tr2")
            status_info = event.get("Eps")

            matches.append({
                "leagueName": league_name,
                "leagueId": league.get("Cid"), # Include league ID
                "leagueLogoUrl": league_logo,
                "homeTeamName": home_team_data.get("Nm", "Home"),
                "homeTeamLogoUrl": TEAM_LOGOS.get(home_team_data.get("Nm", ""), ""),
                "awayTeamName": away_team_data.get("Nm", "Away"),
                "awayTeamLogoUrl": TEAM_LOGOS.get(away_team_data.get("Nm", ""), ""),
                "matchTime": event.get("Esd"),
                "matchStatus": status_info,
                "homeScore": scores[0],
                "awayScore": scores[1],
                "matchId": event.get("Eid")
            })
    return matches

def load_data_from_json(file_path: str):
    """Generic function to load data from a JSON file."""
    if not os.path.isfile(file_path):
        return None
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)

# -----------------------------
# Background Task
# -----------------------------
async def scheduled_update_task(interval: int):
    """Runs the update process periodically."""
    while True:
        try:
            logging.info("Running background update...")
            updateToday()
            clear_cache()
            logging.info("Background update finished.")
        except Exception as e:
            logging.error(f"Background update failed: {e}")
            send_telegram_alert(f"Background update failed: {e}")
        await asyncio.sleep(interval)

@app.on_event("startup")
async def startup_event():
    """On startup, create the first data file and start the background task."""
    logging.info("Application startup...")
    initial_update_task = asyncio.create_task(asyncio.to_thread(updateToday))
    asyncio.create_task(scheduled_update_task(interval=300))
    await initial_update_task
    logging.info("Initial data loaded and background updater started.")

# -----------------------------
# API Endpoints
# -----------------------------
@app.get("/api/scores")
@app.get("/api/fixtures")
def get_scores_and_fixtures():
    key = "matches"
    cached = get_cached(key)
    if cached:
        return cached
    
    all_matches = load_matches_from_json()
    
    live_scores = [m for m in all_matches if m["matchStatus"] not in ["NS", "FT", "Sched", "Cancelled", "Postponed", "Awarded"]]
    fixtures = [m for m in all_matches if m["matchStatus"] in ["NS", "Sched"]]

    response_data = {"live": live_scores, "fixtures": fixtures, "all": all_matches}
    set_cache(key, response_data)
    return response_data

@app.get("/api/standings/{league_id}")
def get_standings(league_id: str):
    key = f"standings_{league_id}"
    cached = get_cached(key)
    if cached:
        return cached

    path = os.path.join(STANDINGS_FOLDER, f"{league_id}.json")
    data = load_data_from_json(path)
    
    if data is None:
        raise HTTPException(status_code=404, detail="Standings not found for this league.")
    
    # The structure might be {"Lnm": "All", "Tables": [{"team": ...}]}
    standings_table = data.get("Tables", [])
    set_cache(key, standings_table)
    return standings_table


@app.get("/api/topscorers/{league_id}")
def get_top_scorers(league_id: str):
    key = f"topscorers_{league_id}"
    cached = get_cached(key)
    if cached:
        return cached

    path = os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json")
    data = load_data_from_json(path)

    if data is None:
        raise HTTPException(status_code=404, detail="Top scorers not found for this league.")

    # The structure might be {"Players": [...]}
    players = data.get("Players", [])
    set_cache(key, players)
    return players


@app.post("/api/update")
def trigger_update(background_tasks: BackgroundTasks):
    """Manually triggers a background update of the data."""
    logging.info("Manual update triggered via API.")
    background_tasks.add_task(updateToday)
    background_tasks.add_task(clear_cache)
    return JSONResponse(content={"status": "success", "message": "Update process started in the background."}, status_code=202)
