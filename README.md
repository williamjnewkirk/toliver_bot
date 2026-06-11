# Don Toliver Floor-Price Alert Bot

Monitors GA floor/pit ticket prices for **Don Toliver: Octane Tour** at Ball
Arena, Denver (July 5, 2026, 7:30 PM) on SeatGeek and sends Telegram alerts
when the lowest floor price drops below **$250** (regular alert) and **$200**
(escalated alert).

## ⚠️ Read this first: how the DataDome workaround works

SeatGeek uses DataDome bot protection, and testing confirmed it blocks fresh
automated sessions **before the page even loads** — stealth plugins alone do
not get past it. What does work: a browser profile that already holds a valid
DataDome cookie. So the flow is:

1. Run `python setup_session.py` once. A real Chrome window opens on the event
   page — solve the captcha if one appears. The session cookie is saved into
   `.browser_profile/`.
2. If you instead get the **hard block page** ("It looks like our system
   thinks you are a robot" — no captcha offered), run
   `python import_cookie.py` and follow its prompts: it copies the valid
   `datadome` cookie out of your normal Chrome (DevTools → Application →
   Cookies → seatgeek.com) into the bot's profile and test-loads the page.
   If your *normal* Chrome is also blocked, your IP is flagged — stop
   retrying and wait a few hours before trying again.
3. Run `python bot.py`. Headless polls reuse (and refresh) the cookie.
4. If DataDome ever re-blocks the session, the bot sends you a Telegram
   message telling you to redo step 1 or 2. Expect this occasionally — it
   takes about 30 seconds.

## Setup

### 1. Create a Telegram bot

1. Open Telegram and message **@BotFather**.
2. Send `/newbot`, pick a name and a username (must end in `bot`).
3. BotFather replies with your **bot token**. Save it.

### 2. Get your chat ID

1. Message **@userinfobot** on Telegram — it replies with your numeric ID.
2. **Important:** also send your new bot any message (e.g. "hi") so it is
   allowed to message you back.

### 3. Install

```powershell
python -m pip install -r requirements.txt
playwright install chromium   # fallback browser; real Chrome is used if installed
```

### 4. Configure

```powershell
Copy-Item .env.example .env
```

Edit `.env` and fill in `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
Never commit `.env` (it's in `.gitignore`).

### 5. Bootstrap the session

```powershell
python setup_session.py
```

Wait for the "✅ Session established" message.

## Run

Quick scraper-only test (no Telegram credentials needed):

```powershell
python scraper.py
```

Full bot:

```powershell
python bot.py
```

It polls immediately on startup, then every ~20 minutes (with random jitter).
Logs go to stdout and `bot.log`. Alert state persists in `state.json`, so
restarting won't re-send alerts you've already received.

### Running in the background

**Windows (this machine):**

```powershell
Start-Process -WindowStyle Hidden pythonw bot.py
```

or create a Task Scheduler task that runs `python bot.py` at logon.

**Mac/Linux:**

```bash
nohup python bot.py &
```

## Maintenance notes

- **`data-testid="price"` is the intended stable selector.** If prices stop
  being detected, open the SeatGeek event page in a normal browser, inspect a
  listing's price element, and confirm this attribute still exists
  (`setup_session.py` prints all `data-testid` values it sees to help with
  this). Do not use the auto-generated `atm_*` class names — they rotate.
- **Diagnostics:** `python debug_page.py` loads the page once and dumps the
  title, selector counts, dollar amounts found, and a `debug_page.png`
  screenshot. Use it when the bot logs warnings you don't understand.
- **Anti-bot stack:** the scraper prefers `rebrowser-playwright` (patches the
  CDP fingerprint DataDome detects), launches your real installed Chrome
  (`BROWSER_CHANNEL=chrome`), applies `playwright-stealth` v2 (with a manual
  fallback init script), and keeps cookies in a persistent profile. If blocks
  become frequent, increase `POLL_INTERVAL_MINUTES`.
- The bot warns on startup if today's date is past the event date
  (`EVENT_DATE` in `.env`), since the listing will no longer exist.
