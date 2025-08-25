import os
import json
import datetime
import logging
import requests
import traceback
from config import telegram_bot_token, telegram_chatid

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -----------------------------
# Folder Setup
# -----------------------------
DATA_FOLDER = "data"
SCHEDULES_FOLDER = os.path.join(DATA_FOLDER, "schedules")
STANDINGS_FOLDER = os.path.join(DATA_FOLDER, "standings")
TOPSCORERS_FOLDER = os.path.join(STANDINGS_FOLDER, "topscorers")
SEASON_FIXTURES_FOLDER = os.path.join(DATA_FOLDER, "season_fixtures")

os.makedirs(SCHEDULES_FOLDER, exist_ok=True)
os.makedirs(STANDINGS_FOLDER, exist_ok=True)
os.makedirs(TOPSCORERS_FOLDER, exist_ok=True)
os.makedirs(SEASON_FIXTURES_FOLDER, exist_ok=True)

# -----------------------------
# Central place for team fixture URLs
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


# -----------------------------
# Telegram Alerting
# -----------------------------
def send_telegram_alert(message: str):
    if not telegram_bot_token or not telegram_chatid:
        logging.warning("Telegram token or chat ID is not configured. Skipping alert.")
        return
    try:
        url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
        payload = {"chat_id": telegram_chatid, "text": f"⚠️ OpenScoreCollector Error:\n{message}"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Failed to send Telegram alert: {e}")

# -----------------------------
# Helper Functions
# -----------------------------
def save_json(content, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        logging.info(f"Saved JSON to {path}")
    except Exception:
        err = traceback.format_exc()
        logging.error(err)
        send_telegram_alert(f"❌ save_json failed ({os.path.basename(path)}):\n{err}")

def fetch_data_for_date(date_str):
    try:
        url = f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{date_str}/0"
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        logging.error(f"Failed to fetch data for date {date_str}: {e}")
        return {}

# -----------------------------
# Simplified function to fetch and save season fixtures
# -----------------------------
def save_team_fixture_data():
    """
    Fetches and saves season fixture JSON for all teams.
    This runs every time the main update is triggered.
    """
    logging.info("Fetching team season fixtures...")
    for team_name, url in TEAM_FIXTURE_URLS.items():
        try:
            logging.info(f"Fetching fixtures for {team_name} from {url}...")
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            fixtures_data = response.json()
            
            file_path = os.path.join(SEASON_FIXTURES_FOLDER, f"{team_name}.json")
            save_json(fixtures_data, file_path)
            
        except requests.RequestException as e:
            logging.error(f"Could not fetch fixture data for {team_name}: {e}")
        except json.JSONDecodeError:
            logging.error(f"Could not parse JSON for {team_name} from {url}")
            
    logging.info("Finished fetching team season fixtures.")


# -----------------------------
# Main Scraper Logic
# -----------------------------
def updateToday():
    logging.info("Starting updateToday process...")
    try:
        # This will now run every time, ensuring files are always created.
        save_team_fixture_data()

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

        for league in final_data.get("Stages", []):
            league_id = league.get("Cid") or league.get("Sid")
            if not league_id: continue

            standings = next((tbl for tbl in league.get("Tables", []) if tbl.get("Lnm") == "All"), None)
            if standings:
                save_json(standings, os.path.join(STANDINGS_FOLDER, f"{league_id}.json"))

            top_scorers = league.get("TopScorers")
            if top_scorers:
                save_json(top_scorers, os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json"))
        
        logging.info("✅ Daily live score update process completed successfully.")

    except Exception:
        err = traceback.format_exc()
        logging.error(f"❌ updateToday failed critically:\n{err}")
        send_telegram_alert(f"❌ updateToday crashed:\n{err}")
        raise

if __name__ == "__main__":
    updateToday()
