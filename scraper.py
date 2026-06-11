"""Playwright scraping logic: load the SeatGeek event page, extract floor prices.

Run standalone for a one-shot test that doesn't need Telegram credentials:

    python scraper.py
"""
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Optional

from models import FloorPriceResult

# rebrowser-playwright is a drop-in Playwright fork that patches the CDP
# Runtime.enable leak DataDome fingerprints. Prefer it; fall back to vanilla.
try:
    from rebrowser_playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from rebrowser_playwright.sync_api import sync_playwright
except ImportError:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)

# playwright-stealth masks the headless fingerprint (navigator.webdriver etc.).
# v2.x exposes a Stealth class; v1.x exposed stealth_sync(). Support both, and
# fall back to a manual init script if neither import works.
_HAVE_STEALTH = False
try:
    from playwright_stealth import Stealth  # type: ignore  # v2.x API

    _stealth = Stealth()

    def _apply_stealth(page) -> None:
        _stealth.apply_stealth_sync(page)

    _HAVE_STEALTH = True
except Exception:
    try:
        from playwright_stealth import stealth_sync  # type: ignore  # v1.x API

        def _apply_stealth(page) -> None:
            stealth_sync(page)

        _HAVE_STEALTH = True
    except Exception:
        pass

# Manual fallback: hide the most common headless tells. Not as thorough as the
# stealth plugin, but covers navigator.webdriver, which DataDome checks first.
_MANUAL_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = window.chrome || { runtime: {} };
"""

# Recent Chrome on Windows — keep this current-ish; a stale UA is itself a tell.
# Only used when running bundled Chromium; real Chrome sends its own real UA.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)

# Browser settings (overridable via .env). DataDome blocks Playwright's
# bundled headless Chromium outright, so the defaults use the real installed
# Chrome plus a persistent profile dir — once one session passes the DataDome
# check, its cookie is reused on every later poll.
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "chrome")  # "" = bundled Chromium
HEADLESS = os.getenv("HEADLESS", "true").strip().lower() not in ("0", "false", "no")
PROFILE_DIR = os.getenv("PROFILE_DIR", ".browser_profile")

# Matches "$298", "$1,234.56", "$ 250"
_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")


def _parse_price(text: str) -> Optional[float]:
    m = _PRICE_RE.search(text)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def fetch_floor_price(event_url: str, floor_keywords: list[str]) -> Optional[FloorPriceResult]:
    """Load the event page and return the lowest floor/pit price.

    Returns None on any failure (timeout, bot block, no prices found) —
    never raises, so a bad cycle can't kill the polling loop.
    """
    try:
        return _fetch(event_url, floor_keywords)
    except Exception:
        log.exception("[WARN] Unexpected scraper error")
        return None


def _fetch(event_url: str, floor_keywords: list[str]) -> Optional[FloorPriceResult]:
    profile_dir = str(Path(PROFILE_DIR).absolute())
    with sync_playwright() as p:
        # Persistent context: keeps cookies (including DataDome's) between
        # polls so we don't face a fresh bot-check every cycle.
        # --disable-blink-features=AutomationControlled removes the
        # "Chrome is being controlled by automated software" signal.
        launch_kwargs = dict(
            user_data_dir=profile_dir,
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/Denver",
        )
        if BROWSER_CHANNEL:
            # Real installed Chrome — its own UA/fingerprint is the most
            # convincing; don't override the user agent in this mode.
            launch_kwargs["channel"] = BROWSER_CHANNEL
        else:
            launch_kwargs["user_agent"] = USER_AGENT

        context = p.chromium.launch_persistent_context(**launch_kwargs)
        try:
            page = context.pages[0] if context.pages else context.new_page()

            if _HAVE_STEALTH:
                try:
                    _apply_stealth(page)
                except Exception:
                    log.warning(
                        "playwright-stealth failed against this Playwright "
                        "version; using manual stealth script instead"
                    )
                    page.add_init_script(_MANUAL_STEALTH_JS)
            else:
                page.add_init_script(_MANUAL_STEALTH_JS)

            page.goto(event_url, wait_until="domcontentloaded", timeout=30_000)

            # Small human-ish pause before the page settles; also gives the
            # listing XHRs time to fire.
            time.sleep(random.uniform(1.5, 3.5))

            # data-testid="price" is the stable hook on SeatGeek listing rows.
            # Do NOT switch to the atm_* class names — they are auto-generated
            # and rotate. If this wait starts timing out, open the page in a
            # real browser, inspect a listing price, and update the selector.
            try:
                page.wait_for_selector('[data-testid="price"]', timeout=15_000)
            except PlaywrightTimeoutError:
                content = page.content()
                if "captcha-delivery" in content or "datadome" in content.lower():
                    log.warning(
                        "[WARN] DataDome challenge detected — bot was blocked "
                        "this cycle. Consider longer intervals or headed mode."
                    )
                else:
                    log.warning(
                        "[WARN] Price selector not found — possible bot block "
                        "or page change"
                    )
                return None

            # Pull every price element plus the text of its enclosing listing
            # row. We climb ancestors in JS until the surrounding text contains
            # more than just the price itself — that text holds the section
            # name ("Floor", "GA Pit", "Section 120", ...). Done in one
            # evaluate() call so we read a consistent DOM snapshot.
            listings = page.evaluate(
                """
                () => Array.from(document.querySelectorAll('[data-testid="price"]'))
                    .map(el => {
                        const priceText = (el.innerText || '').trim();
                        let node = el;
                        let context = '';
                        for (let i = 0; i < 6 && node.parentElement; i++) {
                            node = node.parentElement;
                            const t = (node.innerText || '').trim();
                            if (t.replace(priceText, '').trim().length > 3) {
                                context = t;
                                break;
                            }
                        }
                        return { price: priceText, context };
                    })
                """
            )
        finally:
            context.close()  # close after every run; profile dir persists cookies

    parsed = []
    for item in listings:
        price = _parse_price(item["price"]) or _parse_price(item["context"])
        if price is None:
            continue
        # Collapse the listing-row text to one line for matching/logging.
        label = " | ".join(
            line.strip() for line in item["context"].splitlines() if line.strip()
        )
        parsed.append((price, label))

    if not parsed:
        log.warning("[WARN] Price elements present but none parsed — markup change?")
        return None

    log.info("Raw prices found: %s", [f"${p:.0f} ({lbl[:60]})" for p, lbl in parsed])

    floor = [
        (price, label)
        for price, label in parsed
        if any(kw in label.lower() for kw in floor_keywords)
    ]
    log.info(
        "Filtered as floor/pit: %s",
        [f"${p:.0f}" for p, _ in floor] or "none",
    )

    if not floor:
        log.warning(
            "[WARN] No floor-section listings matched keywords %s — "
            "possible temporary sellout, skipping this cycle",
            floor_keywords,
        )
        return None

    lowest_price, label = min(floor, key=lambda x: x[0])
    return FloorPriceResult(
        lowest_price=lowest_price,
        section=label[:120],
        floor_listing_count=len(floor),
        total_listing_count=len(parsed),
    )


if __name__ == "__main__":
    # One-shot test mode: no Telegram credentials needed.
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    url = os.getenv(
        "EVENT_URL",
        "https://seatgeek.com/don-toliver-tickets/denver-colorado-ball-arena-"
        "2026-07-05-7-30-pm/concert/18050514#listing=BALImRRgX59",
    )
    keywords = ["floor", "pit", "ga", "general admission"]
    print(f"Stealth plugin available: {_HAVE_STEALTH}")
    result = fetch_floor_price(url, keywords)
    if result:
        print(
            f"\nLowest floor price: ${result.lowest_price:.2f}\n"
            f"Section: {result.section}\n"
            f"Floor listings: {result.floor_listing_count} "
            f"(of {result.total_listing_count} total)"
        )
    else:
        print("\nNo floor price retrieved — see warnings above.")
