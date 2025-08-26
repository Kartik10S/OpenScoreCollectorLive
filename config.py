import os

# First, try to get values from environment (Heroku)
telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_chatid = os.getenv("TELEGRAM_CHATID")
api_football_key = os.getenv("API_FOOTBALL_KEY") # New key for standings

# Fallback for local testing (only used if env vars are not set)
if not telegram_bot_token:
    telegram_bot_token = "YOUR_BOT_TOKEN_HERE"

if not telegram_chatid:
    telegram_chatid = "YOUR_CHAT_ID_HERE"

if not api_football_key:
    api_football_key = "ee281508f95bc44b1901a25fd669baba"