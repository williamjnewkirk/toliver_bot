"""Main entry point: scheduler loop for the Don Toliver floor-price bot."""
import logging
import random
import sys
import time
from datetime import date, datetime, timedelta

import config
from alerts import check_thresholds
from state import State

log = logging.getLogger(__name__)


def fetch_price():
    """Dispatch to the configured price source."""
    if config.SOURCE == "gametime":
        from scraper_gametime import fetch_floor_price_gametime

        return fetch_floor_price_gametime(
            config.GAMETIME_EVENT_ID,
            config.FLOOR_KEYWORDS,
            price_field=config.GAMETIME_PRICE_FIELD,
        )
    # seatgeek: Playwright scrape (requires a bootstrapped DataDome session)
    from scraper import fetch_floor_price

    return fetch_floor_price(config.EVENT_URL, config.FLOOR_KEYWORDS)


def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    root.addHandler(stdout_handler)

    file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def poll_once(state: State):
    """Run one poll cycle. Returns the FloorPriceResult (or None on failure)."""
    log.info("Polling source=%s", config.SOURCE)
    result = fetch_price()
    if result is None:
        # Source module already logged why; skip threshold checks this cycle.
        failures = state.record_failure()
        log.info("No price this cycle (%d consecutive failures)", failures)
        if failures >= config.FAILURES_BEFORE_NOTIFY and not state.data["block_notified"]:
            from alerts import send_telegram

            if config.SOURCE == "gametime":
                hint = (
                    "Run `python scraper_gametime.py` on the machine to debug — "
                    "the event may be sold out or the API may have changed."
                )
            else:
                hint = (
                    "Run `python setup_session.py` on the machine to refresh "
                    "the DataDome session, then check bot.log."
                )
            if send_telegram(
                f"🤖 Bot problem: {failures} polls in a row returned no price.\n\n"
                f"{hint}\n\n{config.ALERT_URL}"
            ):
                state.data["block_notified"] = True
        state.save()
        return None
    log.info(
        "Lowest floor price: $%.2f | section: %s | floor listings: %d (of %d total)",
        result.lowest_price,
        result.section,
        result.floor_listing_count,
        result.total_listing_count,
    )
    check_thresholds(result, state)
    return result


def send_startup_message(result) -> None:
    """One-time status message on launch so you know the bot + Telegram work."""
    from alerts import send_telegram

    if result is not None:
        text = (
            f"🤖 Bot started — monitoring {config.EVENT_NAME}\n\n"
            f"Current lowest floor price: ${result.lowest_price:.2f}\n"
            f"Section: {result.section}\n"
            f"Floor listings available: {result.floor_listing_count}\n"
            f"Alert thresholds: ${config.THRESHOLD_HIGH:.0f} / "
            f"${config.THRESHOLD_LOW:.0f}\n"
            f"Polling every ~{config.POLL_INTERVAL_MINUTES:.0f} min "
            f"(source: {config.SOURCE})\n\n"
            f"{config.ALERT_URL}"
        )
    else:
        text = (
            "🤖 Bot started, but the first poll returned no price — "
            "check bot.log on the machine. Polling will continue."
        )
    if send_telegram(text):
        log.info("Startup status message sent")


def main() -> None:
    setup_logging()

    if date.today() > config.EVENT_DATE:
        log.warning(
            "Today (%s) is past the event date (%s) — the listing likely no "
            "longer exists. The bot will run anyway, but expect no prices.",
            date.today(),
            config.EVENT_DATE,
        )

    log.info(
        "Starting bot | thresholds: $%.0f / $%.0f | interval: %.0f min ± %.0f min",
        config.THRESHOLD_HIGH,
        config.THRESHOLD_LOW,
        config.POLL_INTERVAL_MINUTES,
        config.POLL_JITTER_MINUTES,
    )

    state = State(config.STATE_FILE)

    first_cycle = True
    while True:
        try:
            result = poll_once(state)
            if first_cycle and config.SEND_STARTUP_MESSAGE:
                send_startup_message(result)
        except Exception:
            # Belt and braces: nothing should escape poll_once, but if it
            # does, log it and keep the loop alive.
            log.exception("Poll cycle failed unexpectedly — continuing")
        first_cycle = False

        jitter = random.uniform(-config.POLL_JITTER_MINUTES, config.POLL_JITTER_MINUTES)
        sleep_minutes = max(1.0, config.POLL_INTERVAL_MINUTES + jitter)
        next_poll = datetime.now() + timedelta(minutes=sleep_minutes)
        log.info("Next poll at %s (%.1f min)", next_poll.strftime("%H:%M:%S"), sleep_minutes)
        time.sleep(sleep_minutes * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Stopped by user")
