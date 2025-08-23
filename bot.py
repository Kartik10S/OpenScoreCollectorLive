import requests
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8321486230:AAExOi_IummpRegMHkCpN5Fdz2ojgRY7YQs"  # your bot token
API_BASE = "https://your-cloud-run-url"  # or http://127.0.0.1:8000 for local testing
SCORES_URL = f"{API_BASE}/api/scores"
FIXTURES_URL = f"{API_BASE}/api/fixtures"

# Cache to store latest API data
latest_scores = []
latest_fixtures = []

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
    if not latest_scores:
        await update.message.reply_text("No live matches right now.")
        return
    lines = [fmt_row(m["homeTeamName"], m["awayTeamName"], m["homeScore"], m["awayScore"], m["matchStatus"])
             for m in latest_scores[:10]]
    await update.message.reply_text("Live Scores:\n" + "\n".join(lines))

async def matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not latest_fixtures:
        await update.message.reply_text("No fixtures available right now.")
        return
    lines = [fmt_row(m["homeTeamName"], m["awayTeamName"], m["homeScore"], m["awayScore"], m["matchStatus"])
             for m in latest_fixtures[:10]]
    await update.message.reply_text("Today’s Fixtures:\n" + "\n".join(lines))

# -----------------------------
# Background updater
# -----------------------------
async def update_loop():
    global latest_scores, latest_fixtures
    while True:
        try:
            r1 = requests.get(SCORES_URL, timeout=10)
            r1.raise_for_status()
            latest_scores = r1.json()

            r2 = requests.get(FIXTURES_URL, timeout=10)
            r2.raise_for_status()
            latest_fixtures = r2.json()

            print(f"Updated scores and fixtures at {asyncio.get_event_loop().time()}")
        except Exception as e:
            print(f"Error fetching updates: {e}")
        await asyncio.sleep(300)  # every 5 minutes, matches API cache

# -----------------------------
# Main
# -----------------------------
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("live", live))
    app.add_handler(CommandHandler("matches", matches))

    # Start background updater
    asyncio.create_task(update_loop())

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
