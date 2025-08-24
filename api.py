import os
import json
import datetime
import logging
import asyncio
import time
from fastapi import FastAPI, BackgroundTasks
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
        # If file doesn't exist, run a scrape to create it.
        # This is a blocking call, but should only happen once if the file is missing.
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
            status_info = event.get("Eps") # e.g., "FT", "HT", "45'"

            matches.append({
                "leagueName": league_name,
                "leagueLogoUrl": league_logo,
                "homeTeamName": home_team_data.get("Nm", "Home"),
                "homeTeamLogoUrl": TEAM_LOGOS.get(home_team_data.get("Nm", ""), ""),
                "awayTeamName": away_team_data.get("Nm", "Away"),
                "awayTeamLogoUrl": TEAM_LOGOS.get(away_team_data.get("Nm", ""), ""),
                "matchTime": event.get("Esd"), # Start time timestamp
                "matchStatus": status_info,
                "homeScore": scores[0],
                "awayScore": scores[1],
                "matchId": event.get("Eid")
            })
    return matches

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
    # Run initial update in the background to not block startup
    # This ensures the app starts fast, and data becomes available shortly after.
    initial_update_task = asyncio.create_task(asyncio.to_thread(updateToday))
    # Start the recurring background task
    asyncio.create_task(scheduled_update_task(interval=300))
    await initial_update_task # Wait for the first update to complete
    logging.info("Initial data loaded and background updater started.")


# -----------------------------
# API Endpoints
# -----------------------------
@app.get("/api/scores")
@app.get("/api/fixtures")
def get_scores_and_fixtures():
    cached = get_cached("matches")
    if cached:
        return cached
    
    matches = load_matches_from_json()
    
    # Simple filtering for live scores vs fixtures
    live_scores = [m for m in matches if m["matchStatus"] not in ["NS", "FT", "Sched", "Cancelled"]]
    fixtures = [m for m in matches if m["matchStatus"] in ["NS", "Sched"]]

    # For simplicity, this example returns all matches.
    # You can create separate endpoints or add query params to filter.
    response_data = {"live": live_scores, "fixtures": fixtures, "all": matches}
    set_cache("matches", response_data)
    return response_data

@app.post("/api/update")
def trigger_update(background_tasks: BackgroundTasks):
    """Manually triggers a background update of the data."""
    logging.info("Manual update triggered via API.")
    background_tasks.add_task(updateToday)
    background_tasks.add_task(clear_cache)
    return JSONResponse(content={"status": "success", "message": "Update process started in the background."}, status_code=202)
