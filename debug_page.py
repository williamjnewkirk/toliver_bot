"""Diagnostic: load the event page, dump title, screenshot, and DOM clues."""
import os
import re
import time

from rebrowser_playwright.sync_api import sync_playwright

URL = (
    "https://seatgeek.com/don-toliver-tickets/denver-colorado-ball-arena-"
    "2026-07-05-7-30-pm/concert/18050514#listing=BALImRRgX59"
)
HEADLESS = os.getenv("HEADLESS", "true").strip().lower() not in ("0", "false", "no")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=".browser_profile",
        channel="chrome",
        headless=HEADLESS,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="America/Denver",
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=45_000)
    time.sleep(12)  # let everything render / any interstitial resolve

    print("TITLE:", page.title())
    print("URL NOW:", page.url)
    content = page.content()
    print("CONTENT LENGTH:", len(content))
    print("has captcha-delivery iframe:", 'src="https://geo.captcha-delivery.com' in content)
    print("mentions DataDome:", "datadome" in content.lower())
    print("interstitial text:", bool(re.search(r"(verify you are|are you a robot|blocked|Press & Hold)", content, re.I)))

    for sel in [
        '[data-testid="price"]',
        '[data-testid*="price" i]',
        '[data-testid*="listing" i]',
        '[class*="price" i]',
    ]:
        try:
            n = page.locator(sel).count()
        except Exception as e:
            n = f"error: {e}"
        print(f"count {sel}: {n}")

    # Sample data-testid values present on the page
    testids = page.evaluate(
        "() => [...new Set(Array.from(document.querySelectorAll('[data-testid]'))"
        ".map(e => e.getAttribute('data-testid')))].slice(0, 60)"
    )
    print("data-testid values:", testids)

    dollars = page.evaluate(
        "() => (document.body.innerText.match(/\\$\\d[\\d,]*/g) || []).slice(0, 30)"
    )
    print("dollar amounts in body text:", dollars)

    page.screenshot(path="debug_page.png", full_page=False)
    print("screenshot saved to debug_page.png")
    ctx.close()
