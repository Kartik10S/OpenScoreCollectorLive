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
LEAGUE_FIXTURES_FOLDER = os.path.join(DATA_FOLDER, "league_fixtures") # New folder

os.makedirs(SCHEDULES_FOLDER, exist_ok=True)
os.makedirs(STANDINGS_FOLDER, exist_ok=True)
os.makedirs(TOPSCORERS_FOLDER, exist_ok=True)
os.makedirs(SEASON_FIXTURES_FOLDER, exist_ok=True)
os.makedirs(LEAGUE_FIXTURES_FOLDER, exist_ok=True) # New folder

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

LEAGUE_STANDINGS_URLS = {
    "premier-league": "https://www.livescore.com/en/football/england/premier-league/standings/",
    "laliga": "https://www.livescore.com/en/football/spain/laliga/standings/",
    "serie-a": "https://www.livescore.com/en/football/italy/serie-a/standings/",
    "bundesliga": "https://www.livescore.com/en/football/germany/bundesliga/standings/",
    "ligue-1": "https://www.livescore.com/en/football/france/ligue-1/standings/"
}

# --- NEW: Central place for full league fixture URLs ---
LEAGUE_FIXTURE_URLS = {
    "premier-league": "https://fixturedownload.com/feed/json/epl-2025",
    "bundesliga": "https://fixturedownload.com/feed/json/bundesliga-2025"
}

# -----------------------------
# Helper & Alerting Functions
# -----------------------------
def send_telegram_alert(message: str):
    pass
def save_json(content, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        logging.info(f"Saved JSON to {path}")
    except Exception:
        pass
def fetch_data_for_date(date_str):
    try:
        url = f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{date_str}/0"
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        return res.json()
    except requests.RequestException:
        return {}

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

# --- NEW: Function to scrape and save full league fixtures ---
def save_league_fixture_data():
    logging.info("Fetching full league season fixtures...")
    for league_name, url in LEAGUE_FIXTURE_URLS.items():
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            save_json(response.json(), os.path.join(LEAGUE_FIXTURES_FOLDER, f"{league_name}.json"))
        except Exception as e:
            logging.error(f"Could not fetch full fixture data for {league_name}: {e}")

def save_standings_from_livescore():
    marker_file_path = os.path.join(STANDINGS_FOLDER, "last_standings_update.txt")
    today_utc_str = datetime.datetime.utcnow().date().isoformat()
    if os.path.exists(marker_file_path):
        with open(marker_file_path, 'r') as f:
            if f.read().strip() == today_utc_str:
                logging.info("Standings already updated today. Skipping.")
                return
    logging.info("Starting daily standings update from LiveScore pages...")
    for league_name, url in LEAGUE_STANDINGS_URLS.items():
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
            if script_tag:
                data = json.loads(script_tag.string)
                standings_data = data.get('props', {}).get('pageProps', {}).get('standings', [{}])[0].get('tables', [])
                if standings_data:
                    save_json(standings_data, os.path.join(STANDINGS_FOLDER, f"{league_name}.json"))
        except Exception as e:
            logging.error(f"Could not parse standings for {league_name}: {e}")
    with open(marker_file_path, 'w') as f:
        f.write(today_utc_str)
    logging.info(f"Finished fetching standings. Marker file updated.")

# -----------------------------
# Main Scraper Logic
# -----------------------------
def updateToday():
    logging.info("Starting updateToday process...")
    try:
        save_standings_from_livescore()
        save_team_fixture_data()
        save_league_fixture_data() # New function call
        # ... (rest of daily scraper logic is the same)
        logging.info("✅ Daily update process completed successfully.")
    except Exception:
        err = traceback.format_exc()
        logging.error(f"❌ updateToday failed critically:\n{err}")
        send_telegram_alert(f"❌ updateToday crashed:\n{err}")
        raise

if __name__ == "__main__":
    updateToday()
