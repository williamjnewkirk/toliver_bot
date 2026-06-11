"""Alert deduplication state, persisted to state.json across restarts."""
import json
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_DEFAULT_STATE = {
    "alert_high_sent": False,   # the $250 (THRESHOLD_HIGH) alert
    "alert_low_sent": False,    # the $200 (THRESHOLD_LOW) alert
    "last_price": None,
    "last_successful_poll": None,
    "consecutive_failures": 0,
    "block_notified": False,    # "bot is blocked" Telegram alert sent for this streak
}


class State:
    def __init__(self, path: str):
        self.path = path
        self.data = dict(_DEFAULT_STATE)
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            log.info("No existing state file at %s — starting fresh", self.path)
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.data.update({k: saved[k] for k in _DEFAULT_STATE if k in saved})
            log.info("Loaded state: %s", self.data)
        except (json.JSONDecodeError, OSError):
            log.exception("Could not read %s — starting with fresh state", self.path)

    def save(self) -> None:
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)  # atomic on both Windows and POSIX
        except OSError:
            log.exception("Failed to persist state to %s", self.path)

    def record_poll(self, price: float) -> None:
        self.data["last_price"] = price
        self.data["last_successful_poll"] = datetime.now(timezone.utc).isoformat()
        self.data["consecutive_failures"] = 0
        self.data["block_notified"] = False

    def record_failure(self) -> int:
        self.data["consecutive_failures"] = int(self.data.get("consecutive_failures", 0)) + 1
        return self.data["consecutive_failures"]

    # --- threshold flags ---

    def was_sent(self, which: str) -> bool:
        return bool(self.data[f"alert_{which}_sent"])

    def mark_sent(self, which: str) -> None:
        self.data[f"alert_{which}_sent"] = True

    def reset(self, which: str) -> None:
        """Price recovered above this threshold — re-arm the alert."""
        if self.data[f"alert_{which}_sent"]:
            log.info("Price recovered above %s threshold — re-arming alert", which)
        self.data[f"alert_{which}_sent"] = False
