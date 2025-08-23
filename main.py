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

# Folder setup
DATA_FOLDER = "data"
SCHEDULES_FOLDER = os.path.join(DATA_FOLDER, "schedules")
STANDINGS_FOLDER = os.path.join(DATA_FOLDER, "standings")
TOPSCORERS_FOLDER = os.path.join(STANDINGS_FOLDER, "topscorers")

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
    try:
        scrape_today_matches()
        logging.info("Today's matches, standings, and top scorers updated.")
    except Exception as e:
        traceback_str = traceback.format_exc()
        logging.error(f"Error in updateToday: {traceback_str}")
        sendnotify(f"Error in main.py updateToday:\n{traceback_str}")

# ----------------------
# Command line execution
# ----------------------
if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == 'updatetoday':
            updateToday()
        else:
            print("Usage: python main.py updatetoday")
    except Exception as e:
        traceback_str = traceback.format_exc()
        sendnotify(f"Error in main.py execution:\n{traceback_str}")

# Add at the end of main.py
if __name__ == "__main__":
    import time
    try:
        while True:
            updateToday()
            time.sleep(300)  # run every 5 minutes
    except KeyboardInterrupt:
        logging.info("Worker stopped manually")
    except Exception as e:
        traceback_str = traceback.format_exc()
        sendnotify(f"Error in long-running worker:\n{traceback_str}")
