# main.py
import os
import sys
import json
import datetime
import logging
import requests
import hashlib
import traceback
from config import telegram_bot_token, telegram_chatid
from bs4 import BeautifulSoup
from main_api import LEAGUES, send_telegram_alert   # reuse LEAGUES + alert function

# ----------------------
# Setup logging
# ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ----------------------
# Global datastore
# ----------------------
data_store = {
    "fixtures": [],
    "standings": {},
    "top_scorers": {},
    "matches": []
}


# ----------------------
# Folder setup
# ----------------------
DATA_FOLDER = "data"
SCHEDULES_FOLDER = os.path.join(DATA_FOLDER, "schedules")
STANDINGS_FOLDER = os.path.join(DATA_FOLDER, "standings")
TOPSCORERS_FOLDER = STANDINGS_FOLDER

os.makedirs(SCHEDULES_FOLDER, exist_ok=True)
os.makedirs(STANDINGS_FOLDER, exist_ok=True)
os.makedirs(TOPSCORERS_FOLDER, exist_ok=True)

# ----------------------
# Telegram notifications
# ----------------------
def sendnotify(message):
    cachefilename = f"{datetime.date.today().strftime('%Y%m%d')}.cache"
    texthash = hashlib.md5(message.encode('utf-8')).hexdigest()

    if os.path.isfile(cachefilename):
        with open(cachefilename, "r+") as f:
            lstcache = [line.strip() for line in f.readlines()]
            if texthash in lstcache:
                return
            f.write(f"{texthash}\n")
    else:
        with open(cachefilename, "w") as f:
            f.write(f"{texthash}\n")

    url = f'https://api.telegram.org/bot{telegram_bot_token}/sendMessage'
    try:
        requests.post(url, data={
            "chat_id": telegram_chatid,
            "parse_mode": "Markdown",
            "text": message
        }, timeout=10)
    except Exception as e:
        logging.error(f"Telegram send error: {e}")

# -----------------------------
# Scrape all leagues
# -----------------------------
def scrape_all_leagues():
    try:
        url = "https://www.livescore.com/en/football/"
        res = requests.get(url, timeout=15)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        leagues = []
        for comp in soup.select('div.pi[data-id="sr-cmp-sc"] a'):
            name = comp.select_one(".yi").get_text(strip=True)
            link = comp["href"]
            leagues.append({"name": name, "url": link})

        save_json(leagues, os.path.join(DATA_FOLDER, "all_leagues.json"))
        logging.info(f"Found {len(leagues)} leagues")
        return leagues
    except Exception:
        err = traceback.format_exc()
        logging.error(err)
        sendnotify(f"❌ scrape_all_leagues failed:\n{err}")
        return []

# ----------------------
# Save JSON helper
# ----------------------
def save_json(content, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        logging.info(f"Saved JSON to {path}")
    except Exception:
        err = traceback.format_exc()
        logging.error(err)
        sendnotify(f"❌ save_json failed ({path}):\n{err}")

# ----------------------
# Scrape today's matches
# ----------------------
def scrape_today_matches():
    try:
        today_str = datetime.date.today().strftime('%Y%m%d')
        url = f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{today_str}/0"
        res = requests.get(url, timeout=20)
        res.encoding = 'utf-8'
        data = res.json()

        save_json(data, os.path.join(SCHEDULES_FOLDER, f"{today_str}.json"))

        for league in data.get("Stages", []):
            league_id = league.get("Id")
            if not league_id:
                continue

            standings = league.get("Standings", {})
            if standings:
                save_json(standings, os.path.join(STANDINGS_FOLDER, f"{league_id}.json"))

            top_scorers = league.get("TopScorers", {})
            if top_scorers:
                save_json(top_scorers, os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json"))
    except Exception:
        err = traceback.format_exc()
        logging.error(err)
        sendnotify(f"❌ scrape_today_matches failed:\n{err}")

# ----------------------
# League Scrapers
# ----------------------
def scrape_league_fixtures(league_id):
    try:
        url = f"https://prod-public-api.livescore.com/v1/api/app/stage/soccer/{league_id}/2/fixtures"
        res = requests.get(url, timeout=20)
        data = res.json()
        save_json(data, os.path.join(SCHEDULES_FOLDER, f"{league_id}_fixtures.json"))
    except Exception:
        err = traceback.format_exc()
        logging.error(err)
        sendnotify(f"❌ scrape_league_fixtures failed for {league_id}:\n{err}")

def scrape_league_standings(league_id):
    try:
        url = f"https://prod-public-api.livescore.com/v1/api/app/stage/soccer/{league_id}/1/table"
        res = requests.get(url, timeout=20)
        data = res.json()
        save_json(data, os.path.join(STANDINGS_FOLDER, f"{league_id}_standings.json"))
    except Exception:
        err = traceback.format_exc()
        logging.error(err)
        sendnotify(f"❌ scrape_league_standings failed for {league_id}:\n{err}")

def scrape_league_topscorers(league_id):
    try:
        url = f"https://prod-public-api.livescore.com/v1/api/app/stage/soccer/{league_id}/3/topscorers"
        res = requests.get(url, timeout=20)
        data = res.json()
        save_json(data, os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json"))
    except Exception:
        err = traceback.format_exc()
        logging.error(err)
        sendnotify(f"❌ scrape_league_topscorers failed for {league_id}:\n{err}")

# ----------------------
# Update today
# ----------------------
def updateToday():
    global data_store

    data_store["fixtures"] = []
    data_store["standings"] = {}
    data_store["top_scorers"] = {}

    def updateToday():
     """Scrape and update all leagues for today"""
    today_str = datetime.date.today().strftime("%Y%m%d")
    combined_path = os.path.join(SCHEDULES_FOLDER, f"{today_str}.json")

    data_store = {"fixtures": [], "standings": {}, "top_scorers": {}}

    try:
        for league_id, league_name in LEAGUES.items():
            try:
                # --- Scraping ---
                fixtures_path = os.path.join(SCHEDULES_FOLDER, f"{league_id}_fixtures.json")
                scrape_league_fixtures(league_id)

                standings_path = os.path.join(STANDINGS_FOLDER, f"{league_id}_standings.json")
                scrape_league_standings(league_id)

                scorers_path = os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json")
                scrape_league_topscorers(league_id)

                # --- Load scraped files ---
                if os.path.exists(fixtures_path):
                    with open(fixtures_path, "r", encoding="utf-8") as f:
                        data_store["fixtures"].append(json.load(f))

                if os.path.exists(standings_path):
                    with open(standings_path, "r", encoding="utf-8") as f:
                        data_store["standings"][league_id] = json.load(f)

                if os.path.exists(scorers_path):
                    with open(scorers_path, "r", encoding="utf-8") as f:
                        data_store["top_scorers"][league_id] = json.load(f)

                logging.info(f"✅ Updated league {league_id} - {league_name}")

            except Exception as e:
                err = traceback.format_exc()
                logging.error(f"❌ Error updating league {league_id}: {e}", exc_info=True)
            send_telegram_alert(f"❌ Error updating league {league_id}:\n{err}")

        # --- Save combined fixtures JSON (for API endpoints) ---
        # Flatten fixtures into ESPN-like structure with "Stages"
        combined_data = {"Stages": data_store["fixtures"]}

        with open(combined_path, "w", encoding="utf-8") as f:
            json.dump(combined_data, f, indent=2, ensure_ascii=False)

        total_matches = sum(len(stage.get("Events", [])) for stage in combined_data.get("Stages", []))
        logging.info(f"✅ updateToday saved {len(combined_data.get('Stages', []))} leagues and {total_matches} matches to {combined_path}")

    except Exception as e:
        err = traceback.format_exc()
        logging.error(f"❌ updateToday failed: {e}", exc_info=True)
        send_telegram_alert(f"❌ updateToday crashed:\n{err}")
        raise
            

# ----------------------
# Example league configuration
# ----------------------
LEAGUES = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ita.1": "Serie A",
    "fra.1": "Ligue 1",
    "ger.1": "Bundesliga",
}

# ----------------------
# Command line execution
# ----------------------
if __name__ == "__main__":
    import time
    try:
        if len(sys.argv) > 1 and sys.argv[1] == 'updatetoday':
            updateToday()
        else:
            while True:
                updateToday()
                time.sleep(300)  # run every 5 minutes
    except KeyboardInterrupt:
        logging.info("Worker stopped manually")
    except Exception:
        traceback_str = traceback.format_exc()
        sendnotify(f"❌ Fatal error in main.py:\n{traceback_str}")
