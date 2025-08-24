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
# Update Endpoint (FastAPI style)
# -----------------------------
from fastapi import Request
from fastapi.responses import JSONResponse

@app.post("/api/update")
def update(request: Request):
    try:
        print("Running updateToday()...")  # Debug log
        updateToday()
        print("Fixtures updated successfully")
        return {"status": "success", "message": "Fixtures updated"}
    except Exception as e:
        import traceback
        print("Error in /api/update:", e)
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


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
