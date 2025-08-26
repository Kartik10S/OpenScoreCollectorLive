import os
import json
import datetime
import logging
import requests
import traceback
from config import telegram_bot_token, telegram_chatid

# -----------------------------
# Logging & Setup
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
DATA_FOLDER = "data"
SCHEDULES_FOLDER = os.path.join(DATA_FOLDER, "schedules")
STANDINGS_FOLDER = os.path.join(DATA_FOLDER, "standings")
TOPSCORERS_FOLDER = os.path.join(STANDINGS_FOLDER, "topscorers")
SEASON_FIXTURES_FOLDER = os.path.join(DATA_FOLDER, "season_fixtures")
LEAGUE_FIXTURES_FOLDER = os.path.join(DATA_FOLDER, "league_fixtures")

os.makedirs(SCHEDULES_FOLDER, exist_ok=True)
os.makedirs(STANDINGS_FOLDER, exist_ok=True)
os.makedirs(TOPSCORERS_FOLDER, exist_ok=True)
os.makedirs(SEASON_FIXTURES_FOLDER, exist_ok=True)
os.makedirs(LEAGUE_FIXTURES_FOLDER, exist_ok=True)

# -----------------------------
# Data Source URLs
# -----------------------------
TEAM_FIXTURE_URLS = {
    "arsenal": "https://fixturedownload.com/feed/json/epl-2025/arsenal",
    "aston-villa": "https://fixturedownload.com/feed/json/epl-2025/aston-villa",
    "brighton": "https://fixturedownload.com/feed/json/epl-2025/brighton",
    "brentford": "https://fixturedownload.com/feed/json/epl-2025/brentford",
    "bournemouth": "https://fixturedownload.com/feed/json/epl-2025/bournemouth",
    "burnley": "https://fixturedownload.com/feed/json/epl-2025/burnley",
    "crystal-palace": "https://fixturedownload.com/feed/json/epl-2025/crystal-palace",
    "chelsea": "https://fixturedownload.com/feed/json/epl-2025/chelsea",
    "everton": "https://fixturedownload.com/feed/json/epl-2025/everton",
    "fulham": "https://fixturedownload.com/feed/json/epl-2025/fulham",
    "leeds": "https://fixturedownload.com/feed/json/epl-2025/leeds",
    "liverpool": "https://fixturedownload.com/feed/json/epl-2025/liverpool",
    "man-city": "https://fixturedownload.com/feed/json/epl-2025/man-city",
    "man-utd": "https://fixturedownload.com/feed/json/epl-2025/man-utd",
    "newcastle": "https://fixturedownload.com/feed/json/epl-2025/newcastle",
    "nottm-forest": "https://fixturedownload.com/feed/json/epl-2025/nott'm-forest",
    "spurs": "https://fixturedownload.com/feed/json/epl-2025/spurs",
    "sunderland": "https://fixturedownload.com/feed/json/epl-2025/sunderland",
    "west-ham": "https://fixturedownload.com/feed/json/epl-2025/west-ham",
    "wolves": "https://fixturedownload.com/feed/json/epl-2025/wolves"
}

LEAGUE_FIXTURE_URLS = {
    "premier-league": "https://fixturedownload.com/feed/json/epl-2025",
    "bundesliga": "https://fixturedownload.com/feed/json/bundesliga-2025"
}

# --- NEW: SofaScore API details for standings ---
SOFASCORE_LEAGUE_IDS = {
    "premier-league": {"id": 17, "season_id": 52186},
    "laliga": {"id": 8, "season_id": 52376},
    "serie-a": {"id": 23, "season_id": 52760},
    "bundesliga": {"id": 35, "season_id": 52162},
    "ligue-1": {"id": 34, "season_id": 52272}
}

# -----------------------------
# Helper & Alerting Functions
# -----------------------------
def send_telegram_alert(message: str):
    if not telegram_bot_token or not telegram_chatid: return
    try:
        url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
        payload = {"chat_id": telegram_chatid, "text": f"⚠️ OpenScoreCollector Error:\n{message}"}
        requests.post(url, json=payload, timeout=10)
    except Exception: pass

def save_json(content, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        logging.info(f"Saved JSON to {path}")
    except Exception: pass

def fetch_data_for_date(date_str):
    try:
        url = f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{date_str}/0"
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        return res.json()
    except requests.RequestException: return {}

# -----------------------------
# Scraper Functions
# -----------------------------
def save_team_fixture_data():
    logging.info("Fetching team season fixtures...")
    for team_name, url in TEAM_FIXTURE_URLS.items():
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            save_json(response.json(), os.path.join(SEASON_FIXTURES_FOLDER, f"{team_name}.json"))
        except Exception as e:
            logging.error(f"Could not fetch fixture data for {team_name}: {e}")

def save_league_fixture_data():
    logging.info("Fetching full league season fixtures...")
    for league_name, url in LEAGUE_FIXTURE_URLS.items():
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            save_json(response.json(), os.path.join(LEAGUE_FIXTURES_FOLDER, f"{league_name}.json"))
        except Exception as e:
            logging.error(f"Could not fetch full fixture data for {league_name}: {e}")

# --- NEW: Standings scraper using SofaScore API ---
def save_standings_from_sofascore():
    """
    Fetches standings data from the SofaScore API.
    This is more reliable than scraping a website.
    """
    logging.info("--- Starting Standings Scraper (SofaScore) ---")
    # --- FIX: Added more realistic browser headers to avoid being blocked ---
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.sofascore.com/',
        'Cache-Control': 'no-cache'
    }
    for league_name, ids in SOFASCORE_LEAGUE_IDS.items():
        try:
            url = f"https://api.sofascore.com/api/v1/unique-tournament/{ids['id']}/season/{ids['season_id']}/standings/total"
            logging.info(f"Attempting to fetch standings for {league_name} from {url}...")
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            
            data = response.json()
            standings_data = data.get("standings", [])
            
            if not standings_data:
                logging.warning(f"No standings data found in SofaScore API response for {league_name}")
                continue

            file_path = os.path.join(STANDINGS_FOLDER, f"{league_name}.json")
            save_json(standings_data, file_path)
            logging.info(f"SUCCESS: Saved standings for {league_name}.")

        except requests.RequestException as e:
            logging.error(f"CRITICAL ERROR fetching standings for {league_name}: {e}")
        except json.JSONDecodeError:
            logging.error(f"CRITICAL ERROR: Could not parse JSON for {league_name}")
    logging.info("--- Finished Standings Scraper (SofaScore) ---")


# -----------------------------
# Main Scraper Logic
# -----------------------------
def updateToday():
    logging.info("Starting updateToday process...")
    try:
        # --- Using the new, more reliable standings scraper ---
        save_standings_from_sofascore()
        
        save_team_fixture_data()
        save_league_fixture_data()
        
        today_utc = datetime.datetime.utcnow().date()
        yesterday_utc = today_utc - datetime.timedelta(days=1)
        today_str = today_utc.strftime('%Y%m%d')
        yesterday_str = yesterday_utc.strftime('%Y%m%d')

        logging.info(f"Fetching daily data for {today_str} and {yesterday_str} (UTC)...")
        today_data = fetch_data_for_date(today_str)
        yesterday_data = fetch_data_for_date(yesterday_str)

        combined_stages = yesterday_data.get("Stages", []) + today_data.get("Stages", [])
        
        merged_stages_dict = {}
        for stage in combined_stages:
            stage_id = stage.get("Sid")
            if not stage_id: continue
            
            if stage_id not in merged_stages_dict:
                merged_stages_dict[stage_id] = stage
            else:
                existing_events = {evt.get("Eid") for evt in merged_stages_dict[stage_id].get("Events", [])}
                new_events = [evt for evt in stage.get("Events", []) if evt.get("Eid") not in existing_events]
                merged_stages_dict[stage_id].get("Events", []).extend(new_events)

        final_data = {"Stages": list(merged_stages_dict.values())}
        save_json(final_data, os.path.join(SCHEDULES_FOLDER, f"{today_str}.json"))
        
        logging.info("✅ Daily update process completed successfully.")

    except Exception:
        err = traceback.format_exc()
        logging.error(f"❌ updateToday failed critically:\n{err}")
        send_telegram_alert(f"❌ updateToday crashed:\n{err}")
        raise

if __name__ == "__main__":
    updateToday()
