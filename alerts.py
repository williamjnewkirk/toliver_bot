"""Threshold checking and Telegram delivery."""
import asyncio
import logging
from datetime import datetime

from telegram import Bot
from telegram.error import TelegramError

import config
from scraper import FloorPriceResult
from state import State

log = logging.getLogger(__name__)


def _format_message(result: FloorPriceResult, threshold: float, escalated: bool) -> str:
    header = (
        f"🚨 PRICE DROP ALERT — under ${threshold:.0f}!"
        if escalated
        else f"⚠️ Price Alert — under ${threshold:.0f}"
    )
    return (
        f"{header}\n\n"
        f"{config.EVENT_NAME}\n"
        f"Lowest floor price: ${result.lowest_price:.2f}\n"
        f"Section: {result.section}\n"
        f"Floor listings available: {result.floor_listing_count}\n"
        f"Threshold crossed: ${threshold:.0f}\n"
        f"Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z').strip()}\n\n"
        f"{config.EVENT_URL}"
    )


async def _send_with_retry(text: str) -> bool:
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    for attempt in range(1, 4):
        try:
            await bot.send_message(
                chat_id=config.TELEGRAM_CHAT_ID,
                text=text,
                disable_web_page_preview=True,
            )
            return True
        except TelegramError as e:
            wait = 2 ** attempt  # 2s, 4s, 8s exponential backoff
            log.warning("Telegram send failed (attempt %d/3): %s", attempt, e)
            if attempt < 3:
                await asyncio.sleep(wait)
    log.error("Telegram send failed after 3 attempts — continuing polling loop")
    return False


def send_telegram(text: str) -> bool:
    """Synchronous wrapper so the polling loop stays simple."""
    try:
        return asyncio.run(_send_with_retry(text))
    except Exception:
        log.exception("Telegram send raised unexpectedly")
        return False


def check_thresholds(result: FloorPriceResult, state: State) -> None:
    """Compare the polled price against both thresholds, alert + dedupe.

    Dedup rule: each threshold alert fires once, then re-arms only after the
    price recovers to/above that threshold.
    """
    price = result.lowest_price

    for which, threshold, escalated in (
        ("high", config.THRESHOLD_HIGH, False),  # $250 — regular alert
        ("low", config.THRESHOLD_LOW, True),     # $200 — escalated alert
    ):
        if price < threshold:
            if not state.was_sent(which):
                log.info("Price $%.2f crossed below $%.0f — alerting", price, threshold)
                if send_telegram(_format_message(result, threshold, escalated)):
                    state.mark_sent(which)
        else:
            # Recovered above this threshold: re-arm so a future drop re-alerts.
            state.reset(which)

    state.record_poll(price)
    state.save()
