import os
import json
import datetime
import logging
import asyncio
import time
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from threading import Lock
from scraper import updateToday, send_telegram_alert
from urllib.parse import unquote

# -----------------------------
# Setup & Paths
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
app = FastAPI(title="OpenScoreCollector API")
DATA_FOLDER = "data"
SCHEDULES_FOLDER = os.path.join(DATA_FOLDER, "schedules")
STANDINGS_FOLDER = os.path.join(DATA_FOLDER, "standings")
TOPSCORERS_FOLDER = os.path.join(DATA_FOLDER, "topscorers")
SEASON_FIXTURES_FOLDER = os.path.join(DATA_FOLDER, "season_fixtures")
LEAGUE_FIXTURES_FOLDER = os.path.join(DATA_FOLDER, "league_fixtures") # New folder

# -----------------------------
# Cache & Data Loading
# -----------------------------
CACHE = {}
CACHE_LOCK = Lock()
CACHE_TTL = 60

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

def get_data_file_paths():
    today_utc = datetime.datetime.utcnow().date()
    yesterday_utc = today_utc - datetime.timedelta(days=1)
    today_str = today_utc.strftime("%Y%m%d")
    yesterday_str = yesterday_utc.strftime("%Y%m%d")
    return [
        os.path.join(SCHEDULES_FOLDER, f"{today_str}.json"),
        os.path.join(SCHEDULES_FOLDER, f"{yesterday_str}.json")
    ]

def load_and_process_daily_data():
    cached_data = get_cached("processed_daily_data")
    if cached_data:
        return cached_data

    data = None
    for path in get_data_file_paths():
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                logging.info(f"Successfully loaded data from {path}")
                break
            except (json.JSONDecodeError, FileNotFoundError):
                logging.warning(f"Could not read or parse {path}, trying next file.")
                continue
    
    if not data:
        raise HTTPException(status_code=503, detail="Daily match data is currently being prepared. Please try again in a minute.")

    matches, league_info_list, league_name_to_id_map = [], [], {}
    seen_league_ids = set()
    for league in data.get("Stages", []):
        league_name = league.get("Snm", "Unknown League")
        league_id = league.get("Cid") or league.get("Sid")
        if league_id and league_name and league_id not in seen_league_ids:
            league_info_list.append({"leagueName": league_name, "leagueId": league_id})
            league_name_to_id_map[league_name] = league_id
            seen_league_ids.add(league_id)
        
        for event in league.get("Events", []):
            try:
                home_team_data = event.get("T1", [{}])[0] if event.get("T1") else {}
                away_team_data = event.get("T2", [{}])[0] if event.get("T2") else {}
                matches.append({
                    "leagueName": league_name, "leagueId": league_id,
                    "homeTeamName": home_team_data.get("Nm", "N/A"),
                    "awayTeamName": away_team_data.get("Nm", "N/A"),
                    "matchTime": event.get("Esd"), "matchStatus": event.get("Eps"),
                    "homeScore": event.get("Tr1"), "awayScore": event.get("Tr2"), 
                    "matchId": event.get("Eid")
                })
            except (IndexError, TypeError) as e:
                logging.error(f"Could not process a match in league {league_name}. Data: {event}. Error: {e}")
                continue
    
    processed_data = {
        "matches": matches, "leagues": league_info_list, "league_map": league_name_to_id_map
    }
    set_cache("processed_daily_data", processed_data)
    return processed_data

def load_secondary_data(file_path: str):
    if not os.path.isfile(file_path):
        return None
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return None

# -----------------------------
# Background Task
# -----------------------------
async def run_update_task():
    try:
        logging.info("Running data update task...")
        await asyncio.to_thread(updateToday)
        clear_cache()
        logging.info("Data update task finished successfully.")
    except Exception as e:
        logging.error(f"Data update task failed: {e}", exc_info=True)
        send_telegram_alert(f"Background update failed: {e}")

async def scheduled_update_task(interval: int):
    await asyncio.sleep(interval) 
    while True:
        await run_update_task()
        logging.info(f"Next background update in {interval} seconds.")
        await asyncio.sleep(interval)

@app.on_event("startup")
async def startup_event():
    logging.info("Application startup...")
    logging.info("Running initial data load... This may take a moment.")
    await run_update_task()
    logging.info("Initial data load complete. Server is now ready.")
    asyncio.create_task(scheduled_update_task(interval=600))
    logging.info("Background updater has been scheduled.")

# -----------------------------
# API Endpoints (Reordered and updated for new structure)
# -----------------------------
@app.get("/")
def get_root():
    return {"message": "Welcome to the OpenScoreCollector API!"}

@app.get("/api/leagues")
def get_leagues():
    try:
        data = load_and_process_daily_data()
        return data["leagues"]
    except HTTPException as e:
        raise e

@app.get("/api/scores")
def get_daily_fixtures_and_scores():
    try:
        data = load_and_process_daily_data()
        all_matches = data["matches"]
        live_scores = [m for m in all_matches if m["matchStatus"] not in ["NS", "FT", "Sched", "Cancelled", "Postponed", "Awarded"]]
        fixtures = [m for m in all_matches if m["matchStatus"] in ["NS", "Sched"]]
        return {"live": live_scores, "fixtures": fixtures, "all": all_matches}
    except HTTPException as e:
        raise e

@app.get("/api/fixtures/{league_name}/{team_name}")
def get_team_fixtures_in_league(league_name: str, team_name: str):
    try:
        filename = f"{unquote(team_name).lower()}.json"
        path = os.path.join(SEASON_FIXTURES_FOLDER, filename)
        data = load_secondary_data(path)
        if data is None:
            raise HTTPException(status_code=404, detail=f"Season fixtures not found for team '{team_name}'.")
        return data
    except HTTPException as e:
        raise e

@app.get("/api/fixtures/{league_name}")
def get_league_fixtures(league_name: str):
    try:
        filename = f"{unquote(league_name).lower().replace(' ', '-')}.json"
        path = os.path.join(LEAGUE_FIXTURES_FOLDER, filename)
        data = load_secondary_data(path)
        if data is None:
            raise HTTPException(status_code=404, detail=f"Full season fixtures not found for league '{league_name}'.")
        return data
    except HTTPException as e:
        raise e

@app.get("/api/standings/{league_name}")
def get_standings(league_name: str):
    try:
        filename = f"{unquote(league_name).lower().replace(' ', '-')}.json"
        path = os.path.join(STANDINGS_FOLDER, filename)
        data = load_secondary_data(path)
        if data is None:
            raise HTTPException(status_code=404, detail=f"Standings not found for league '{league_name}'.")
        return data
    except HTTPException as e:
        raise e

@app.get("/api/topscorers/{league_name}")
def get_top_scorers(league_name: str):
    try:
        decoded_league_name = unquote(league_name)
        processed_data = load_and_process_daily_data()
        league_id = processed_data["league_map"].get(decoded_league_name)
        if not league_id:
            raise HTTPException(status_code=404, detail=f"League '{decoded_league_name}' not found in today's data.")
        path = os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json")
        data = load_secondary_data(path)
        if data is None:
            raise HTTPException(status_code=404, detail="Top scorers data file not found for this league.")
        return data.get("Players", [])
    except HTTPException as e:
        raise e

@app.post("/api/update")
def trigger_update(background_tasks: BackgroundTasks):
    logging.info("Manual update triggered via API.")
    background_tasks.add_task(run_update_task)
    return JSONResponse(content={"status": "success", "message": "Update process started in the background."}, status_code=202)
