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
from urllib.parse import unquote

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
# Centralized Data Loading and Processing
# -----------------------------
def load_and_process_daily_data():
    """
    Loads the main daily JSON file, processes it into structured data
    (matches, leagues), and caches the result. This is the single source
    of truth for all API endpoints.
    """
    cached_data = get_cached("processed_daily_data")
    if cached_data:
        return cached_data

    path = get_today_json_path()
    if not os.path.isfile(path):
        logging.warning(f"No JSON file found at {path}. Attempting to generate it.")
        try:
            updateToday()
        except Exception as e:
            logging.error(f"Failed to create initial data file: {e}")
            raise HTTPException(status_code=503, detail="Data source is currently unavailable. Please try again later.")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    matches = []
    league_info_list = []
    league_name_to_id_map = {}
    seen_league_ids = set()

    for league in data.get("Stages", []):
        league_name = league.get("Snm", "Unknown League")
        league_id = league.get("Cid")
        league_logo = LEAGUE_LOGOS.get(league_name, "")

        if league_id and league_id not in seen_league_ids:
            league_info = {"leagueName": league_name, "leagueId": league_id}
            league_info_list.append(league_info)
            league_name_to_id_map[league_name] = league_id
            seen_league_ids.add(league_id)

        for event in league.get("Events", []):
            home_team_data = event.get("T1", [{}])[0]
            away_team_data = event.get("T2", [{}])[0]
            scores = event.get("Tr1"), event.get("Tr2")
            status_info = event.get("Eps")

            matches.append({
                "leagueName": league_name, "leagueId": league_id, "leagueLogoUrl": league_logo,
                "homeTeamName": home_team_data.get("Nm", "Home"),
                "homeTeamLogoUrl": TEAM_LOGOS.get(home_team_data.get("Nm", ""), ""),
                "awayTeamName": away_team_data.get("Nm", "Away"),
                "awayTeamLogoUrl": TEAM_LOGOS.get(away_team_data.get("Nm", ""), ""),
                "matchTime": event.get("Esd"), "matchStatus": status_info,
                "homeScore": scores[0], "awayScore": scores[1], "matchId": event.get("Eid")
            })
    
    processed_data = {
        "matches": matches,
        "leagues": league_info_list,
        "league_map": league_name_to_id_map
    }
    set_cache("processed_daily_data", processed_data)
    return processed_data

def load_secondary_data(file_path: str):
    """Generic function to load standings or topscorers JSON files."""
    if not os.path.isfile(file_path):
        return None
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)

# -----------------------------
# Background Task
# -----------------------------
async def scheduled_update_task(interval: int):
    while True:
        await asyncio.sleep(interval)
        try:
            logging.info("Running background update...")
            updateToday()
            clear_cache()
            logging.info("Background update finished successfully.")
        except Exception as e:
            logging.error(f"Background update failed: {e}")
            send_telegram_alert(f"Background update failed: {e}")

@app.on_event("startup")
async def startup_event():
    logging.info("Application startup...")
    # Run initial update in the background to not block startup
    background_tasks = BackgroundTasks()
    background_tasks.add_task(updateToday)
    # Start the recurring background task
    asyncio.create_task(scheduled_update_task(interval=600))
    logging.info("Initial data load and background updater started.")

# -----------------------------
# API Endpoints (Ordered from most specific to most general)
# -----------------------------
@app.get("/")
def get_root():
    """Root endpoint to confirm the API is running."""
    return {"message": "Welcome to the OpenScoreCollector API!"}

@app.get("/api/leagues")
def get_leagues():
    """Returns a list of all available leagues for the day."""
    try:
        data = load_and_process_daily_data()
        return data["leagues"]
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})


@app.get("/api/scores")
@app.get("/api/fixtures")
def get_scores_and_fixtures():
    try:
        data = load_and_process_daily_data()
        all_matches = data["matches"]
        
        live_scores = [m for m in all_matches if m["matchStatus"] not in ["NS", "FT", "Sched", "Cancelled", "Postponed", "Awarded"]]
        fixtures = [m for m in all_matches if m["matchStatus"] in ["NS", "Sched"]]

        return {"live": live_scores, "fixtures": fixtures, "all": all_matches}
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

@app.get("/api/standings/{league_name}")
def get_standings(league_name: str):
    try:
        decoded_league_name = unquote(league_name)
        processed_data = load_and_process_daily_data()
        
        league_id = processed_data["league_map"].get(decoded_league_name)
        if not league_id:
            raise HTTPException(status_code=404, detail=f"League '{decoded_league_name}' not found for today.")

        path = os.path.join(STANDINGS_FOLDER, f"{league_id}.json")
        data = load_secondary_data(path)
        
        if data is None:
            raise HTTPException(status_code=404, detail="Standings data file not found for this league.")
        
        return data.get("Tables", [])
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

@app.get("/api/topscorers/{league_name}")
def get_top_scorers(league_name: str):
    try:
        decoded_league_name = unquote(league_name)
        processed_data = load_and_process_daily_data()

        league_id = processed_data["league_map"].get(decoded_league_name)
        if not league_id:
            raise HTTPException(status_code=404, detail=f"League '{decoded_league_name}' not found for today.")

        path = os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json")
        data = load_secondary_data(path)

        if data is None:
            raise HTTPException(status_code=404, detail="Top scorers data file not found for this league.")

        return data.get("Players", [])
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

@app.post("/api/update")
def trigger_update(background_tasks: BackgroundTasks):
    """Manually triggers a background update of the data."""
    logging.info("Manual update triggered via API.")
    background_tasks.add_task(updateToday)
    background_tasks.add_task(clear_cache)
    return JSONResponse(content={"status": "success", "message": "Update process started in the background."}, status_code=202)
