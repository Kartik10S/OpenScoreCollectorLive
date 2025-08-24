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
# League Configuration
# -----------------------------
LEAGUES = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ita.1": "Serie A",
    "fra.1": "Ligue 1",
    "ger.1": "Bundesliga",
}

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

# -----------------------------
# Scrapers
# -----------------------------
def scrape_today_matches():
    """Fetches today's match data from the livescore API and saves it."""
    try:
        today_str = datetime.date.today().strftime('%Y%m%d')
        # This is a more direct API endpoint for daily soccer data
        url = f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{today_str}/0"
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        data = res.json()

        # Save the main schedule file for the day
        save_json(data, os.path.join(SCHEDULES_FOLDER, f"{today_str}.json"))

        # Extract and save standings and top scorers for each league found in the data
        for league in data.get("Stages", []):
            league_id = league.get("Cid") # Use Competition ID
            if not league_id:
                continue

            standings = next((tbl for tbl in league.get("Tables", []) if tbl.get("Lnm") == "All"), None)
            if standings:
                save_json(standings, os.path.join(STANDINGS_FOLDER, f"{league_id}.json"))

            top_scorers = league.get("TopScorers")
            if top_scorers:
                save_json(top_scorers, os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json"))
        logging.info("Successfully scraped and saved today's matches, standings, and top scorers.")
    except Exception:
        err = traceback.format_exc()
        logging.error(err)
        send_telegram_alert(f"❌ scrape_today_matches failed:\n{err}")

def updateToday():
    """Main function to trigger the scraping for today."""
    logging.info("Starting updateToday process...")
    try:
        # The single API call now handles fixtures, standings, and top scorers
        scrape_today_matches()
        logging.info("✅ updateToday process completed successfully.")
    except Exception:
        err = traceback.format_exc()
        logging.error(f"❌ updateToday failed critically:\n{err}")
        send_telegram_alert(f"❌ updateToday crashed:\n{err}")
        raise
