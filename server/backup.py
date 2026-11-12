"""Nightly backups.
1. A snapshot on the server itself (keeps 14 days) - protects against mistakes and corruption.
2. If JARVIS_BACKUP_URL is set (an Oracle Object Storage pre-authenticated URL), the same snapshot is
   copied off the server - protects against losing the server itself.
Secrets (.env) are never included."""
import gzip
import io
import json
import os
import sqlite3
import tarfile
import time
import urllib.request
from datetime import datetime

from . import config, db, tools

LOCAL_DIR = config.ROOT / "data" / "backups"
KEEP_LOCAL = 14
STATE = config.ROOT / "data" / "backup_state.json"


def _state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _snapshot_bytes() -> bytes:
    """A consistent copy of the database (+ notification keys + spend), as a .tar.gz in memory."""
    tmp = config.ROOT / "data" / "_snapshot.db"
    src = sqlite3.connect(db.DB_FILE)
    dst = sqlite3.connect(tmp)
    with dst:
        src.backup(dst)  # SQLite's own safe online copy
    src.close()
    dst.close()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(tmp, arcname="jarvis.db")
        for extra in ["vapid_private.pem", "spend.json"]:
            p = config.ROOT / "data" / extra
            if p.exists():
                tar.add(p, arcname=extra)
    tmp.unlink(missing_ok=True)
    return buf.getvalue()


def run_backup() -> dict:
    stamp = datetime.now(tools.tz()).strftime("%Y-%m-%d_%H%M")
    name = f"jarvis-{stamp}.tar.gz"
    data = _snapshot_bytes()
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    (LOCAL_DIR / name).write_bytes(data)
    for old in sorted(LOCAL_DIR.glob("jarvis-*.tar.gz"))[:-KEEP_LOCAL]:
        old.unlink()
    result = {"file": name, "size_kb": round(len(data) / 1024, 1), "local": True, "offsite": None}

    url = os.environ.get("JARVIS_BACKUP_URL", "")
    if url:
        try:
            req = urllib.request.Request(url.rstrip("/") + "/" + name, data=data, method="PUT",
                                         headers={"Content-Type": "application/gzip"})
            with urllib.request.urlopen(req, timeout=60) as r:
                result["offsite"] = 200 <= r.status < 300
        except Exception as e:
            result["offsite"] = False
            result["offsite_error"] = f"{type(e).__name__}: {e}"[:200]
    st = {"last_utc": db.now_utc(), "last_local_day": datetime.now(tools.tz()).strftime("%Y-%m-%d"), **result}
    STATE.write_text(json.dumps(st))
    db.log("backup", f"{name} ({result['size_kb']} KB) offsite={result['offsite']}")
    return result


def due() -> bool:
    """Once a day, after 3:30 AM local time (or right away if there has never been one)."""
    st = _state()
    now = datetime.now(tools.tz())
    if not st:
        return True
    return st.get("last_local_day") != now.strftime("%Y-%m-%d") and (now.hour, now.minute) >= (3, 30)


def status() -> dict:
    st = _state()
    return {"last": st.get("last_utc"), "file": st.get("file"), "offsite": st.get("offsite"),
            "offsite_configured": bool(os.environ.get("JARVIS_BACKUP_URL")), "local_copies": len(list(LOCAL_DIR.glob("jarvis-*.tar.gz"))) if LOCAL_DIR.exists() else 0}
