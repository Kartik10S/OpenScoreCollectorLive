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

# Global datastore
data_store = {
    "fixtures": [],
    "standings": {},
    "topscorers": {},
    "matches": []
}

# Folder setup
DATA_FOLDER = "data"
SCHEDULES_FOLDER = os.path.join(DATA_FOLDER, "schedules")
STANDINGS_FOLDER = os.path.join(DATA_FOLDER, "standings")
TOPSCORERS_FOLDER = os.path.join(STANDINGS_FOLDER, "topscorers")


# Example league configuration
LEAGUES = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ita.1": "Serie A",
    "fra.1": "Ligue 1",
    "ger.1": "Bundesliga",
    # Add more league IDs as needed
}


os.makedirs(SCHEDULES_FOLDER, exist_ok=True)
os.makedirs(STANDINGS_FOLDER, exist_ok=True)
os.makedirs(TOPSCORERS_FOLDER, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

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

    url = f'https://api.telegram.org/bot{telegram_bot_token}/sendMessage?chat_id={telegram_chatid}&parse_mode=Markdown&text={message}'
    requests.get(url)

# -----------------------------
# NEW FUNCTION for leagues list
# -----------------------------
def scrape_all_leagues():
    url = "https://www.livescore.com/en/football/"
    res = requests.get(url)
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


# ----------------------
# Save JSON helper
# ----------------------
def save_json(content, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        logging.info(f"Saved JSON to {path}")
    except Exception as e:
        logging.error(f"Error saving JSON to {path}: {e}")

# ----------------------
# Scrape today's matches
# ----------------------
def scrape_today_matches():
    today_str = datetime.date.today().strftime('%Y%m%d')
    url = f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{today_str}/0"
    res = requests.get(url)
    res.encoding = 'utf-8'
    data = res.json()

    # Save schedules JSON
    save_json(data, os.path.join(SCHEDULES_FOLDER, f"{today_str}.json"))

    # Process standings and top scorers
    for league in data.get("Stages", []):
        league_id = league.get("Id", None)
        if not league_id:
            continue

        # Save standings (if available)
        standings = league.get("Standings", {})
        if standings:
            save_json(standings, os.path.join(STANDINGS_FOLDER, f"{league_id}.json"))

        # Save top scorers (if available)
        top_scorers = league.get("TopScorers", {})
        if top_scorers:
            save_json(top_scorers, os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json"))

# ----------------------
# Update today
# ----------------------
def updateToday():
    global data_store

    data_store["fixtures"] = []
    data_store["standings"] = {}
    data_store["top_scorers"] = {}

    # Loop through all leagues
    for league_id, league_info in LEAGUES.items():
        try:
            # --- Fixtures ---
            fixtures = scrape_fixtures(league_id)
            if fixtures:
                data_store["fixtures"].extend(fixtures)

            # --- Standings ---
            standings = scrape_standings(league_id)
            if standings:
                data_store["standings"][league_id] = standings

            # --- Top Scorers ---
            scorers = scrape_top_scorers(league_id)
            if scorers:
                data_store["top_scorers"][league_id] = scorers

        except Exception as e:
            print(f"Error updating league {league_id}: {e}")


# ----------------------
# League Id
# ----------------------

def scrape_league_fixtures(league_id):
    url = f"https://prod-public-api.livescore.com/v1/api/app/stage/soccer/{league_id}/2/fixtures"
    res = requests.get(url)
    data = res.json()
    save_json(data, os.path.join(SCHEDULES_FOLDER, f"{league_id}_fixtures.json"))

def scrape_league_standings(league_id):
    url = f"https://prod-public-api.livescore.com/v1/api/app/stage/soccer/{league_id}/1/table"
    res = requests.get(url)
    data = res.json()
    save_json(data, os.path.join(STANDINGS_FOLDER, f"{league_id}_standings.json"))

def scrape_league_topscorers(league_id):
    url = f"https://prod-public-api.livescore.com/v1/api/app/stage/soccer/{league_id}/3/topscorers"
    res = requests.get(url)
    data = res.json()
    save_json(data, os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json"))        

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
    except Exception as e:
        traceback_str = traceback.format_exc()
        sendnotify(f"Error in main.py execution:\n{traceback_str}")

