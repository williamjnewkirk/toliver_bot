"""Main entry point: scheduler loop for the Don Toliver floor-price bot."""
import logging
import random
import sys
import time
from datetime import date, datetime, timedelta

import config
from alerts import check_thresholds
from scraper import fetch_floor_price
from state import State

log = logging.getLogger(__name__)


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


def poll_once(state: State) -> None:
    log.info("Polling %s", config.EVENT_URL)
    result = fetch_floor_price(config.EVENT_URL, config.FLOOR_KEYWORDS)
    if result is None:
        # Scraper already logged why; skip threshold checks this cycle.
        failures = state.record_failure()
        log.info("No price this cycle (%d consecutive failures)", failures)
        if failures >= config.FAILURES_BEFORE_NOTIFY and not state.data["block_notified"]:
            from alerts import send_telegram

            if send_telegram(
                f"🤖 Bot problem: {failures} polls in a row returned no price — "
                f"likely a DataDome block or markup change.\n\n"
                f"Run `python setup_session.py` on the machine to refresh the "
                f"session, then check bot.log.\n\n{config.EVENT_URL}"
            ):
                state.data["block_notified"] = True
        state.save()
        return
    log.info(
        "Lowest floor price: $%.2f | section: %s | floor listings: %d (of %d total)",
        result.lowest_price,
        result.section,
        result.floor_listing_count,
        result.total_listing_count,
    )
    check_thresholds(result, state)


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

    while True:
        try:
            poll_once(state)
        except Exception:
            # Belt and braces: nothing should escape poll_once, but if it
            # does, log it and keep the loop alive.
            log.exception("Poll cycle failed unexpectedly — continuing")

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
