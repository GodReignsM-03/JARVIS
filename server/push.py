"""Web Push: lets the server put a notification on the owner's iPhone even when Jarvis is closed.
(iPhone requirement: Jarvis must be added to the Home Screen and notifications allowed once.)"""
import base64
import json

from . import config, db

KEY_FILE = config.ROOT / "data" / "vapid_private.pem"
SUB_CLAIM = "mailto:jarvis-server@example.com"


def _ensure_keys():
    from py_vapid import Vapid01
    if not KEY_FILE.exists():
        KEY_FILE.parent.mkdir(exist_ok=True)
        v = Vapid01()
        v.generate_keys()
        v.save_key(str(KEY_FILE))
    return Vapid01.from_file(str(KEY_FILE))


def public_key() -> str:
    from cryptography.hazmat.primitives import serialization
    v = _ensure_keys()
    raw = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def subscribe(sub: dict) -> None:
    with db.conn() as c:
        c.execute("INSERT INTO push_subs (endpoint, sub_json, created_utc) VALUES (?,?,?) "
                  "ON CONFLICT(endpoint) DO UPDATE SET sub_json=excluded.sub_json",
                  (sub["endpoint"], json.dumps(sub), db.now_utc()))
    db.log("notifications enabled", sub["endpoint"][:40] + "...")


def count() -> int:
    with db.conn() as c:
        return c.execute("SELECT COUNT(*) n FROM push_subs").fetchone()["n"]


def send(title: str, body: str) -> dict:
    """Send to every subscribed device. Returns how many succeeded/failed; drops dead subscriptions."""
    from pywebpush import WebPushException, webpush
    _ensure_keys()
    with db.conn() as c:
        subs = [json.loads(r["sub_json"]) for r in c.execute("SELECT sub_json FROM push_subs")]
    ok, failed = 0, 0
    for s in subs:
        try:
            webpush(s, json.dumps({"title": title, "body": body}), vapid_private_key=str(KEY_FILE),
                    vapid_claims={"sub": SUB_CLAIM}, ttl=3600)
            ok += 1
        except WebPushException as e:
            failed += 1
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):  # device unsubscribed: forget it
                with db.conn() as c:
                    c.execute("DELETE FROM push_subs WHERE endpoint=?", (s["endpoint"],))
    return {"sent": ok, "failed": failed, "devices": len(subs)}
