"""One-time (and as-needed) session bootstrap for DataDome.

SeatGeek's DataDome protection blocks fresh automated sessions outright, but
once a browser profile holds a valid DataDome cookie, headless polls reuse
and refresh it. This script opens a visible Chrome window on the event page —
solve the captcha / wait for the page to load normally, and the cookie is
saved into the bot's persistent profile (.browser_profile).

Run it:        python setup_session.py
Re-run it whenever the bot tells you it's blocked.
"""
import os
import sys
import time

# Windows consoles often default to cp1252, which can't print ✅/⚠️.
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
WAIT_MINUTES = 5

print("Opening Chrome. If a captcha / 'verify you are human' page appears,")
print("solve it. Once ticket listings are visible, this script will confirm")
print(f"and close automatically (waiting up to {WAIT_MINUTES} minutes).\n")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        channel="chrome",
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="America/Denver",
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

    deadline = time.time() + WAIT_MINUTES * 60
    ok = False
    warned_hard_block = False
    while time.time() < deadline:
        try:
            content = page.content()
            # DataDome's HARD block page offers no captcha at all — solving is
            # impossible from this window. Tell the user the way out.
            if "thinks you are a robot" in content and not warned_hard_block:
                warned_hard_block = True
                print("⛔ DataDome HARD BLOCK page detected (no captcha offered).")
                print("   Options, in order:")
                print("   1. In this window, go to seatgeek.com (homepage), browse")
                print("      around a bit, then navigate back to the event page.")
                print("   2. If still blocked: close this, and run")
                print("      python import_cookie.py")
                print("      to copy the datadome cookie from your normal Chrome")
                print("      (instructions are printed by that script).")
                print("   3. If your normal Chrome is ALSO blocked, your IP is")
                print("      flagged — stop retrying and wait a few hours.")
                print("   Waiting in case you browse your way out of it...\n")
            # Same stable selector the scraper uses.
            if page.locator('[data-testid="price"]').count() > 0:
                ok = True
                break
            # Fallback: any dollar amounts rendered means listings loaded
            # even if the data-testid changed — flag that loudly below.
            body = page.evaluate("() => document.body.innerText")
            if body.count("$") >= 3 and "captcha" not in content.lower():
                ok = True
                break
        except Exception:
            pass  # page may be mid-navigation after the captcha
        time.sleep(2)

    if ok:
        n = page.locator('[data-testid="price"]').count()
        print(f"\n✅ Session established — listings are visible.")
        if n:
            print(f"   Found {n} [data-testid=\"price\"] elements (selector OK).")
        else:
            print("   ⚠️ Listings loaded but [data-testid=\"price\"] matched nothing —")
            print("   SeatGeek may have changed markup. Inspect the page and update")
            print("   the selector in scraper.py.")
        # Print the data-testid values to help debug selector changes.
        testids = page.evaluate(
            "() => [...new Set(Array.from(document.querySelectorAll('[data-testid]'))"
            ".map(e => e.getAttribute('data-testid')))].slice(0, 40)"
        )
        print(f"   data-testid values on page: {testids}")
        print("\nYou can now run: python bot.py")
    else:
        print("\n❌ Timed out without seeing listings. Re-run and solve the captcha,")
        print("   or try browsing a few SeatGeek pages in the opened window first.")

    ctx.close()
