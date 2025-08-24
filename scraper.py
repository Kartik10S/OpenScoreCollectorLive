import os
import json
import datetime
import logging
import requests
import traceback
from bs4 import BeautifulSoup
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
TOPSCORERS_FOLDER = os.path.join(STANDINGS_FOLDER, "topscorers") # Corrected path

os.makedirs(SCHEDULES_FOLDER, exist_ok=True)
os.makedirs(STANDINGS_FOLDER, exist_ok=True)
os.makedirs(TOPSCORERS_FOLDER, exist_ok=True)

# -----------------------------
# Telegram Alerting
# -----------------------------
def send_telegram_alert(message: str):
    """Send an alert message to a Telegram chat."""
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
    """Saves content to a JSON file."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        logging.info(f"Saved JSON to {path}")
    except Exception:
        err = traceback.format_exc()
        logging.error(err)
        send_telegram_alert(f"❌ save_json failed ({os.path.basename(path)}):\n{err}")

def fetch_data_for_date(date_str):
    """Fetches soccer data for a specific date string (YYYYMMDD)."""
    try:
        url = f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{date_str}/0"
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        logging.error(f"Failed to fetch data for date {date_str}: {e}")
        return {} # Return empty dict on failure

# -----------------------------
# Main Scraper Logic
# -----------------------------
def updateToday():
    """
    Scrapes data for the current and previous UTC day to ensure a full
    24-hour window of matches, handling timezone differences.
    """
    logging.info("Starting updateToday process...")
    try:
        today_utc = datetime.datetime.utcnow().date()
        yesterday_utc = today_utc - datetime.timedelta(days=1)

        today_str = today_utc.strftime('%Y%m%d')
        yesterday_str = yesterday_utc.strftime('%Y%m%d')

        logging.info(f"Fetching data for {today_str} and {yesterday_str} (UTC)...")

        today_data = fetch_data_for_date(today_str)
        yesterday_data = fetch_data_for_date(yesterday_str)

        # Combine stages (leagues and their matches) from both days
        combined_stages = yesterday_data.get("Stages", []) + today_data.get("Stages", [])
        
        # Use a dictionary to merge leagues by ID, preventing duplicates
        merged_stages_dict = {}
        for stage in combined_stages:
            stage_id = stage.get("Sid")
            if not stage_id:
                continue
            
            if stage_id not in merged_stages_dict:
                merged_stages_dict[stage_id] = stage
            else:
                # If league exists, merge the events (matches)
                existing_events = {evt.get("Eid") for evt in merged_stages_dict[stage_id].get("Events", [])}
                new_events = [evt for evt in stage.get("Events", []) if evt.get("Eid") not in existing_events]
                merged_stages_dict[stage_id].get("Events", []).extend(new_events)

        final_data = {"Stages": list(merged_stages_dict.values())}

        # Save the combined data to today's file path
        save_json(final_data, os.path.join(SCHEDULES_FOLDER, f"{today_str}.json"))

        # Extract and save standings and top scorers from the combined data
        for league in final_data.get("Stages", []):
            league_id = league.get("Cid") # Use Competition ID
            if not league_id:
                continue

            # Find the standings table (usually named "All")
            standings = next((tbl for tbl in league.get("Tables", []) if tbl.get("Lnm") == "All"), None)
            if standings:
                save_json(standings, os.path.join(STANDINGS_FOLDER, f"{league_id}.json"))

            top_scorers = league.get("TopScorers")
            if top_scorers:
                save_json(top_scorers, os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json"))
        
        logging.info("✅ updateToday process completed successfully with merged data.")

    except Exception:
        err = traceback.format_exc()
        logging.error(f"❌ updateToday failed critically:\n{err}")
        send_telegram_alert(f"❌ updateToday crashed:\n{err}")
        raise
