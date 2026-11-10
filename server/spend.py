"""Monthly spend guard. Tracks what Jarvis's brain costs this month and switches fast mode
off automatically before the monthly cap is reached (standard Opus keeps working)."""
import json
import os
import threading
from datetime import date

from . import config

# Claude Opus 5.5 list prices, USD per million tokens. Fast mode is 2x.
PRICE = {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00}
FAST_MULTIPLIER = 2.0
CAP = float(os.environ.get("JARVIS_MONTHLY_CAP", "30"))
FAST_UNTIL = 0.80  # stop using fast mode at 80% of the cap

_FILE = config.ROOT / "data" / "spend.json"
_lock = threading.Lock()


def _load() -> dict:
    month = date.today().strftime("%Y-%m")
    try:
        d = json.loads(_FILE.read_text())
        if d.get("month") == month:
            return d
    except (OSError, ValueError):
        pass
    return {"month": month, "usd": 0.0, "requests": 0}


def record(usage, fast: bool) -> float:
    """Add one request's cost; returns the month-to-date total."""
    cost = (usage.get("input", 0) * PRICE["input"] + usage.get("output", 0) * PRICE["output"]
            + usage.get("cache_read", 0) * PRICE["cache_read"] + usage.get("cache_write", 0) * PRICE["cache_write"]) / 1e6
    if fast:
        cost *= FAST_MULTIPLIER
    with _lock:
        d = _load()
        d["usd"] = round(d["usd"] + cost, 6)
        d["requests"] += 1
        _FILE.parent.mkdir(exist_ok=True)
        _FILE.write_text(json.dumps(d))
        return d["usd"]


def month_to_date() -> float:
    return _load()["usd"]


def fast_allowed() -> bool:
    return month_to_date() < CAP * FAST_UNTIL
