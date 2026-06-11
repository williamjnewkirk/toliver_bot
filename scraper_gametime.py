"""Gametime price source: plain JSON API, no browser, no bot detection.

Gametime's mobile API serves full listing data for the event unauthenticated:

    https://mobile.gametime.co/v1/listings?event_id=<id>

Each listing carries `section` (e.g. "floor", "104"), `section_group`
(e.g. "Prime Loge"), and `price` in CENTS with both `prefee` and `total`
(all-in) amounts. Run standalone to test:

    python scraper_gametime.py
"""
import json
import logging
import urllib.request
from typing import Optional

from models import FloorPriceResult

log = logging.getLogger(__name__)

LISTINGS_URL = "https://mobile.gametime.co/v1/listings?event_id={event_id}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_floor_price_gametime(
    event_id: str,
    floor_keywords: list[str],
    price_field: str = "total",  # "total" = all-in with fees, "prefee" = sticker
) -> Optional[FloorPriceResult]:
    """Return the lowest floor/pit price from Gametime, or None on failure."""
    try:
        req = urllib.request.Request(
            LISTINGS_URL.format(event_id=event_id), headers=_HEADERS
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception:
        log.exception("[WARN] Gametime API request failed")
        return None

    listings = data.get("listings", [])
    if not listings:
        log.warning("[WARN] Gametime returned no listings — event sold out or ID changed?")
        return None

    parsed = []
    for listing in listings:
        cents = (listing.get("price") or {}).get(price_field)
        if not cents:
            continue
        section = str(listing.get("section") or "")
        group = str(listing.get("section_group") or "")
        label = f"{group} {section}".strip()
        parsed.append((cents / 100.0, label))

    floor = [
        (price, label)
        for price, label in parsed
        if any(kw in label.lower() for kw in floor_keywords)
    ]

    log.info(
        "Gametime: %d listings total, %d matched floor keywords %s",
        len(parsed),
        len(floor),
        floor_keywords,
    )
    if floor:
        log.info(
            "Floor prices (%s): %s",
            price_field,
            sorted(f"${p:.0f}" for p, _ in floor),
        )
    else:
        log.warning(
            "[WARN] No floor-section listings matched — possible temporary "
            "sellout, skipping this cycle. Sections seen: %s",
            sorted({label for _, label in parsed})[:20],
        )
        return None

    lowest_price, label = min(floor, key=lambda x: x[0])
    return FloorPriceResult(
        lowest_price=lowest_price,
        section=label,
        floor_listing_count=len(floor),
        total_listing_count=len(parsed),
    )


if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    event_id = os.getenv("GAMETIME_EVENT_ID", "69822806346f6babfa6ae7d3")
    keywords = ["floor", "pit", "ga", "general admission"]
    for field in ("total", "prefee"):
        result = fetch_floor_price_gametime(event_id, keywords, price_field=field)
        if result:
            print(
                f"\n[{field}] Lowest floor price: ${result.lowest_price:.2f}\n"
                f"  Section: {result.section}\n"
                f"  Floor listings: {result.floor_listing_count} "
                f"(of {result.total_listing_count} total)"
            )
        else:
            print(f"\n[{field}] No floor price retrieved — see warnings above.")
