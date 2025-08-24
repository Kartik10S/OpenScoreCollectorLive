import requests
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import telegram_bot_token # Import token from config

# Use your Heroku app URL here
API_BASE = "https://opencollector-live-5e8aab08da77.herokuapp.com" 
API_URL = f"{API_BASE}/api/scores" # Use the unified endpoint

# Cache to store latest API data
latest_data = {}

# -----------------------------
# Helper
# -----------------------------
def fmt_row(home, away, hs, as_, status):
    score = f"{hs}-{as_}" if hs is not None and as_ is not None else "–"
    return f"{home} {score} {away}  ({status})"

# -----------------------------
# Telegram Handlers
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to Goal2Gol ⚽\n"
        "Use /live for live scores, /matches for fixtures, /help for help."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start – Start the bot\n"
        "/live – Live football scores\n"
        "/matches – Today’s fixtures\n"
        "/help – This help"
    )

async def live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    live_matches = latest_data.get("live", [])
    if not live_matches:
        await update.message.reply_text("No live matches right now.")
        return
    lines = [fmt_row(m["homeTeamName"], m["awayTeamName"], m["homeScore"], m["awayScore"], m["matchStatus"])
             for m in live_matches[:10]]
    await update.message.reply_text("Live Scores:\n" + "\n".join(lines))

async def matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fixtures = latest_data.get("fixtures", [])
    if not fixtures:
        await update.message.reply_text("No fixtures available right now.")
        return
    lines = [fmt_row(m["homeTeamName"], m["awayTeamName"], m["homeScore"], m["awayScore"], m["matchStatus"])
             for m in fixtures[:10]]
    await update.message.reply_text("Today’s Fixtures:\n" + "\n".join(lines))

# -----------------------------
# Background updater for the bot
# -----------------------------
async def update_loop():
    global latest_data
    while True:
        try:
            r = requests.get(API_URL, timeout=15)
            r.raise_for_status()
            latest_data = r.json()
            print(f"Bot updated data at {asyncio.get_event_loop().time()}")
        except Exception as e:
            print(f"Bot error fetching updates: {e}")
        await asyncio.sleep(60)  # Update bot data every minute

# -----------------------------
# Main
# -----------------------------
async def main():
    if not telegram_bot_token or telegram_bot_token == "YOUR_BOT_TOKEN_HERE":
        print("Telegram bot token not configured. Exiting.")
        return

    app = ApplicationBuilder().token(telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("live", live))
    app.add_handler(CommandHandler("matches", matches))

    # Start background updater
    asyncio.create_task(update_loop())

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
