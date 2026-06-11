"""Transplant a valid DataDome cookie from your normal Chrome into the bot.

Use this when setup_session.py shows the hard "system thinks you are a robot"
page (no captcha offered). Your everyday browser usually still has a valid
DataDome session — copy its cookie into the bot's profile:

1. In your NORMAL Chrome window, open https://seatgeek.com and confirm the
   event page loads with prices.
2. Press F12 (DevTools) -> Application tab -> Cookies -> https://seatgeek.com
3. Find the cookie named  datadome  and copy its Value (one long string).
4. Run:  python import_cookie.py
   and paste the value when prompted (or pass it as the first argument).

The script stores the cookie in the bot's persistent profile and immediately
test-loads the event page to confirm it works.
"""
import os
import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from rebrowser_playwright.sync_api import sync_playwright
except ImportError:
    from playwright.sync_api import sync_playwright

URL = os.getenv(
    "EVENT_URL",
    "https://seatgeek.com/don-toliver-tickets/denver-colorado-ball-arena-"
    "2026-07-05-7-30-pm/concert/18050514#listing=BALImRRgX59",
)
PROFILE_DIR = os.getenv("PROFILE_DIR", ".browser_profile")

if len(sys.argv) > 1:
    cookie_value = sys.argv[1].strip()
else:
    cookie_value = input("Paste the datadome cookie value: ").strip()

if not cookie_value or " " in cookie_value:
    print("That doesn't look like a cookie value (empty or contains spaces).")
    sys.exit(1)

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        channel="chrome",
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="America/Denver",
    )
    # DataDome's cookie is scoped to .seatgeek.com; expiry ~1 year, but the
    # value rotates server-side — each successful poll refreshes it.
    ctx.add_cookies(
        [
            {
                "name": "datadome",
                "value": cookie_value,
                "domain": ".seatgeek.com",
                "path": "/",
                "secure": True,
                "sameSite": "Lax",
                "expires": int(time.time()) + 365 * 24 * 3600,
            }
        ]
    )
    print("Cookie stored. Test-loading the event page (this can take ~20s)...")

    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
    time.sleep(5)

    blocked = False
    content = page.content()
    if "captcha-delivery" in content or "thinks you are a robot" in content:
        blocked = True
    else:
        try:
            page.wait_for_selector('[data-testid="price"]', timeout=20_000)
        except Exception:
            pass

    n = page.locator('[data-testid="price"]').count()
    if blocked:
        print("\n❌ Still blocked even with the cookie. The bot's browser")
        print("   fingerprint or your IP is currently flagged. Wait a few hours")
        print("   (don't keep retrying — it extends the flag), then try again.")
    elif n > 0:
        print(f"\n✅ Success — page loaded with {n} price elements.")
        print("You can now run: python bot.py")
    else:
        print("\n⚠️ Page loaded (no block detected) but no [data-testid=\"price\"]")
        print("   elements found. Run `python debug_page.py` to inspect what the")
        print("   page looks like — the selector may need updating in scraper.py.")
        testids = page.evaluate(
            "() => [...new Set(Array.from(document.querySelectorAll('[data-testid]'))"
            ".map(e => e.getAttribute('data-testid')))].slice(0, 40)"
        )
        print(f"   data-testid values seen: {testids}")

    ctx.close()
