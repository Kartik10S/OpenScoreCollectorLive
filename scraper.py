import os
import json
import datetime
import logging
import requests
import traceback
from bs4 import BeautifulSoup
from config import telegram_bot_token, telegram_chatid

# -----------------------------
# Logging & Setup
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
DATA_FOLDER = "data"
# ... (folder definitions are the same)
SCHEDULES_FOLDER = os.path.join(DATA_FOLDER, "schedules")
STANDINGS_FOLDER = os.path.join(DATA_FOLDER, "standings")
TOPSCORERS_FOLDER = os.path.join(STANDINGS_FOLDER, "topscorers")
SEASON_FIXTURES_FOLDER = os.path.join(DATA_FOLDER, "season_fixtures")

os.makedirs(SCHEDULES_FOLDER, exist_ok=True)
os.makedirs(STANDINGS_FOLDER, exist_ok=True)
os.makedirs(TOPSCORERS_FOLDER, exist_ok=True)
os.makedirs(SEASON_FIXTURES_FOLDER, exist_ok=True)

# -----------------------------
# Data Source URLs
# -----------------------------
TEAM_FIXTURE_URLS = {
    "arsenal": "https://fixturedownload.com/feed/json/epl-2025/arsenal",
    # ... (all other teams are the same)
    "wolves": "https://fixturedownload.com/feed/json/epl-2025/wolves"
}

# --- NEW: Central place for league standings URLs ---
LEAGUE_STANDINGS_URLS = {
    "premier-league": "https://www.livescore.com/en/football/england/premier-league/standings/",
    "laliga": "https://www.livescore.com/en/football/spain/laliga/standings/",
    "serie-a": "https://www.livescore.com/en/football/italy/serie-a/standings/",
    "bundesliga": "https://www.livescore.com/en/football/germany/bundesliga/standings/",
    "ligue-1": "https://www.livescore.com/en/football/france/ligue-1/standings/"
}

# -----------------------------
# Helper & Alerting Functions (no changes here)
# -----------------------------
def send_telegram_alert(message: str):
    # ... (function is the same)
    pass

def save_json(content, path):
    # ... (function is the same)
    pass

def fetch_data_for_date(date_str):
    # ... (function is the same)
    pass

# -----------------------------
# Scraper Functions
# -----------------------------
def save_team_fixture_data():
    # ... (this function is the same)
    pass

# --- NEW: Function to scrape and save standings from LiveScore pages ---
def save_standings_from_livescore():
    """
    Scrapes standings data from LiveScore HTML pages by parsing embedded JSON.
    Runs only once per day.
    """
    marker_file_path = os.path.join(STANDINGS_FOLDER, "last_standings_update.txt")
    today_utc_str = datetime.datetime.utcnow().date().isoformat()

    if os.path.exists(marker_file_path):
        with open(marker_file_path, 'r') as f:
            if f.read().strip() == today_utc_str:
                logging.info("Standings have already been updated today. Skipping.")
                return

    logging.info("Starting daily standings update from LiveScore pages...")
    for league_name, url in LEAGUE_STANDINGS_URLS.items():
        try:
            logging.info(f"Fetching standings for {league_name} from {url}...")
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
            
            if not script_tag:
                logging.warning(f"Could not find __NEXT_DATA__ script tag for {league_name}")
                continue

            data = json.loads(script_tag.string)
            # Navigate through the complex JSON to find the standings table
            standings_data = data.get('props', {}).get('pageProps', {}).get('standings', [{}])[0].get('tables', [])
            
            if not standings_data:
                logging.warning(f"Could not extract standings table for {league_name}")
                continue

            file_path = os.path.join(STANDINGS_FOLDER, f"{league_name}.json")
            save_json(standings_data, file_path)

        except requests.RequestException as e:
            logging.error(f"Could not fetch standings page for {league_name}: {e}")
        except (json.JSONDecodeError, AttributeError, IndexError) as e:
            logging.error(f"Could not parse standings JSON for {league_name}: {e}")

    with open(marker_file_path, 'w') as f:
        f.write(today_utc_str)
    logging.info(f"Finished fetching standings. Marker file updated for {today_utc_str}.")


# -----------------------------
# Main Scraper Logic
# -----------------------------
def updateToday():
    logging.info("Starting updateToday process...")
    try:
        # --- NEW: Call the new standings scraper ---
        save_standings_from_livescore()
        
        save_team_fixture_data()

        # ... (rest of the daily scraper logic is the same)
        
        logging.info("✅ Daily update process completed successfully.")

    except Exception:
        err = traceback.format_exc()
        logging.error(f"❌ updateToday failed critically:\n{err}")
        send_telegram_alert(f"❌ updateToday crashed:\n{err}")
        raise

if __name__ == "__main__":
    updateToday()
