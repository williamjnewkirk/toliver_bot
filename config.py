"""Configuration loaded from .env via python-dotenv.

All tunable values live here so no other module touches os.environ directly.
"""
import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


# --- Telegram credentials (required) ---
TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _require("TELEGRAM_CHAT_ID")

# --- Price source: "gametime" (JSON API, reliable) or "seatgeek" (Playwright
# scrape, blocked by DataDome unless a valid session cookie is established) ---
SOURCE = os.getenv("SOURCE", "gametime").strip().lower()

# --- Event ---
EVENT_URL = os.getenv(
    "EVENT_URL",
    "https://seatgeek.com/don-toliver-tickets/denver-colorado-ball-arena-"
    "2026-07-05-7-30-pm/concert/18050514#listing=BALImRRgX59",
)
GAMETIME_EVENT_ID = os.getenv("GAMETIME_EVENT_ID", "69822806346f6babfa6ae7d3")
GAMETIME_URL = f"https://gametime.co/events/{GAMETIME_EVENT_ID}"
# "total" = all-in price including fees; "prefee" = sticker price before fees.
GAMETIME_PRICE_FIELD = os.getenv("GAMETIME_PRICE_FIELD", "total").strip().lower()

# Link to include in Telegram alerts — wherever the price actually came from.
ALERT_URL = GAMETIME_URL if SOURCE == "gametime" else EVENT_URL

EVENT_DATE = date.fromisoformat(os.getenv("EVENT_DATE", "2026-07-05"))
EVENT_NAME = os.getenv("EVENT_NAME", "Don Toliver — Octane Tour @ Ball Arena, Denver")

# --- Floor/pit section matching (case-insensitive substring match) ---
FLOOR_KEYWORDS = [
    kw.strip().lower()
    for kw in os.getenv("FLOOR_KEYWORDS", "floor,pit,ga,general admission").split(",")
    if kw.strip()
]

# --- Price thresholds ---
THRESHOLD_HIGH = float(os.getenv("THRESHOLD_HIGH", "250"))
THRESHOLD_LOW = float(os.getenv("THRESHOLD_LOW", "200"))

# --- Polling cadence ---
# The Gametime JSON API has no bot detection, so 5 min is fine. If you switch
# SOURCE to seatgeek, raise this back to 20+ to stay under DataDome's radar.
POLL_INTERVAL_MINUTES = float(os.getenv("POLL_INTERVAL_MINUTES", "5"))
POLL_JITTER_MINUTES = float(os.getenv("POLL_JITTER_MINUTES", "1"))

# Send a Telegram status message (current price) when the bot starts.
SEND_STARTUP_MESSAGE = os.getenv("SEND_STARTUP_MESSAGE", "true").strip().lower() not in (
    "0",
    "false",
    "no",
)

# Telegram-notify after this many consecutive failed polls (likely blocked).
FAILURES_BEFORE_NOTIFY = int(os.getenv("FAILURES_BEFORE_NOTIFY", "3"))

# --- Files ---
STATE_FILE = os.getenv("STATE_FILE", "state.json")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")
