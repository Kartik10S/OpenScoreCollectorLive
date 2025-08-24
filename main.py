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
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

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

app = Flask(__name__)

@app.route("/api/update", methods=["POST"])
def api_update():
    try:
        updateToday()  # make sure this is imported or defined above
        return jsonify({"status": "success", "message": "Fixtures updated"}), 200
    except Exception as e:
        logging.exception("Update failed")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/fixtures", methods=["GET"])
def api_fixtures():
    return jsonify(data_store.get("fixtures", []))

@app.route("/api/standings", methods=["GET"])
def api_standings():
    return jsonify(data_store.get("standings", {}))

@app.route("/api/topscorers", methods=["GET"])
def api_topscorers():
    return jsonify(data_store.get("top_scorers", {}))

# --- Scraper: Fixtures ---
def scrape_league_fixtures(league_id):
    try:
        url = f"https://www.espn.com/soccer/fixtures/_/league/{league_id}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        fixtures = []
        for match in soup.select(".Table__TR"):
            teams = match.select(".Table__Team")
            if len(teams) == 2:
                home = teams[0].get_text(strip=True)
                away = teams[1].get_text(strip=True)
                time = match.select_one(".Table__TD").get_text(strip=True)
                fixtures.append({
                    "home": home,
                    "away": away,
                    "time": time,
                    "league": league_id,
                    "date": datetime.date.today().isoformat()
                })

        return fixtures
    except Exception as e:
        logging.error(f"❌ scrape_league_fixtures failed for {league_id}: {e}")
        return []

# --- Scraper: Standings ---
def scrape_league_standings(league_id):
    try:
        url = f"https://www.espn.com/soccer/standings/_/league/{league_id}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        standings = []
        for row in soup.select(".Table__TR"):
            team = row.select_one(".hide-mobile span")
            stats = row.select("td")
            if team and len(stats) >= 3:
                standings.append({
                    "team": team.get_text(strip=True),
                    "played": stats[0].get_text(strip=True),
                    "wins": stats[1].get_text(strip=True),
                    "losses": stats[2].get_text(strip=True),
                })
        return standings
    except Exception as e:
        logging.error(f"❌ scrape_league_standings failed for {league_id}: {e}")
        return []

# --- Scraper: Top Scorers ---
def scrape_league_topscorers(league_id):
    try:
        url = f"https://www.espn.com/soccer/stats/_/league/{league_id}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        scorers = []
        for row in soup.select(".Table__TR"):
            cols = row.select("td")
            if len(cols) >= 4:
                player = cols[1].get_text(strip=True)
                team = cols[2].get_text(strip=True)
                goals = cols[3].get_text(strip=True)
                scorers.append({
                    "player": player,
                    "team": team,
                    "goals": goals
                })
        return scorers
    except Exception as e:
        logging.error(f"❌ scrape_league_topscorers failed for {league_id}: {e}")
        return []


# ----------------------
# Update today
# ----------------------
def updateToday():
    """Scrape and update all leagues for today"""
    global data_store

    today_str = datetime.date.today().strftime("%Y%m%d")
    combined_path = os.path.join(SCHEDULES_FOLDER, f"{today_str}.json")

    # Reset datastore
    data_store = {"fixtures": [], "standings": {}, "top_scorers": {}}

    try:
        for league_id, league_name in LEAGUES.items():
            try:
                # --- Scraping ---
                fixtures = scrape_league_fixtures(league_id)
                standings = scrape_league_standings(league_id)
                scorers = scrape_league_topscorers(league_id)

                # --- Save to files ---
                fixtures_path = os.path.join(SCHEDULES_FOLDER, f"{league_id}_fixtures.json")
                standings_path = os.path.join(STANDINGS_FOLDER, f"{league_id}_standings.json")
                scorers_path = os.path.join(TOPSCORERS_FOLDER, f"{league_id}_topscorers.json")

                save_json(fixtures, fixtures_path)
                save_json(standings, standings_path)
                save_json(scorers, scorers_path)

                # --- Update memory store ---
                data_store["fixtures"].extend(fixtures)
                data_store["standings"][league_id] = standings
                data_store["top_scorers"][league_id] = scorers

                logging.info(f"✅ Updated league {league_id} - {league_name}")

            except Exception:
                err = traceback.format_exc()
                logging.error(f"❌ Error updating league {league_id}:\n{err}")
                send_telegram_alert(f"❌ Error updating league {league_id}:\n{err}")

        # --- Save combined fixtures JSON (for API endpoints) ---
        combined_data = {"Stages": data_store["fixtures"]}
        save_json(combined_data, combined_path)

        total_matches = sum(1 for f in data_store["fixtures"])
        logging.info(f"✅ updateToday saved {len(LEAGUES)} leagues and {total_matches} matches to {combined_path}")

    except Exception:
        err = traceback.format_exc()
        logging.error(f"❌ updateToday failed:\n{err}")
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
