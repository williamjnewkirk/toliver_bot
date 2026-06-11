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

# --- Event ---
EVENT_URL = os.getenv(
    "EVENT_URL",
    "https://seatgeek.com/don-toliver-tickets/denver-colorado-ball-arena-"
    "2026-07-05-7-30-pm/concert/18050514#listing=BALImRRgX59",
)
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
POLL_INTERVAL_MINUTES = float(os.getenv("POLL_INTERVAL_MINUTES", "20"))
POLL_JITTER_MINUTES = float(os.getenv("POLL_JITTER_MINUTES", "3"))

# Telegram-notify after this many consecutive failed polls (likely blocked).
FAILURES_BEFORE_NOTIFY = int(os.getenv("FAILURES_BEFORE_NOTIFY", "3"))

# --- Files ---
STATE_FILE = os.getenv("STATE_FILE", "state.json")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")
