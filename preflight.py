#!/usr/bin/env python3
"""Preflight: runs every LIVE chain end to end against the running server and prints a verdict.
Not unit tests, not mocks. "Done" means preflight passed.

Usage: python preflight.py [base_url]   (default http://127.0.0.1:4700)
Exit code is non-zero on any failure."""
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:4700").rstrip("/")
results = []


def check(name, fn):
    try:
        status, detail = fn()
    except Exception as e:  # a crash is a failure, with the reason shown
        status, detail = "fail", f"{type(e).__name__}: {e}"
    results.append(status)
    mark = {"pass": "✔", "fail": "✘", "warn": "!"}[status]
    print(f" {mark} {name}" + (f"  ({detail})" if detail else ""))


def req(path, data=None, timeout=60):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(BASE + path, data=body, method="POST" if body else "GET",
                               headers={"Content-Type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def server_up():
    code, _, body = req("/api/health")
    h = json.loads(body)
    return ("pass", None) if code == 200 and h["ok"] else ("fail", f"HTTP {code}")


def model_known():
    h = json.loads(req("/api/health")[2])
    return ("pass", h["model"]) if h["model_known"] else ("fail", f"'{h['model']}' is not in the known model list")


def served_match_disk():
    stale = []
    for path, name in [("/", "index.html"), ("/app.js", "app.js"), ("/orb.js", "orb.js"), ("/style.css", "style.css"),
                       ("/sw.js", "sw.js"), ("/manifest.json", "manifest.json"), ("/icon-192.png", "icon-192.png")]:
        code, _, body = req(path)
        disk = (ROOT / "web" / name).read_bytes()
        if code != 200 or hashlib.sha256(body).digest() != hashlib.sha256(disk).digest():
            stale.append(name)
    return ("pass", None) if not stale else ("fail", "stale or missing: " + ", ".join(stale))


def secrets_not_served():
    leaks = [p for p in ["/.env", "/server/config.py", "/../.env", "/%2e%2e/.env", "/preflight.py", "/models/kokoro/model.onnx", "/data/jarvis.db", "/data/vapid_private.pem"]
             if req(p)[0] == 200]
    return ("pass", None) if not leaks else ("fail", "served: " + ", ".join(leaks))


def security_headers():
    _, headers, _ = req("/")
    missing = [h for h in ["X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"] if h not in headers]
    return ("pass", None) if not missing else ("fail", "missing " + ", ".join(missing))


def oversized_refused():
    code, _, _ = req("/api/tts", {"text": "x" * 9000})
    return ("pass", None) if code in (400, 413) else ("fail", f"HTTP {code}")


def voice_works():
    h = json.loads(req("/api/health")[2])
    if not h["voice_loaded"]:
        return "fail", "voice model not loaded (run scripts/fetch_voice_models.sh)"
    code, headers, body = req("/api/tts", {"text": "Preflight check, sir."})
    ok = code == 200 and headers.get("Content-Type", "").startswith("audio/mpeg") and len(body) > 2000
    return ("pass", f"{len(body)//1024} KB mp3") if ok else ("fail", f"HTTP {code}, {len(body)} bytes")


def push_ready():
    code, _, body = req("/api/push/key")
    key = json.loads(body).get("key", "") if code == 200 else ""
    h = json.loads(req("/api/health")[2])
    if len(key) < 80:
        return "fail", f"HTTP {code}"
    n = h.get("notification_devices", 0)
    return ("pass", f"{n} phone(s) signed up") if n else ("warn", "server ready; no phone has turned on reminders yet")


def backups_ok():
    b = json.loads(req("/api/health")[2]).get("backup", {})
    if not b.get("last"):
        return "fail", "no backup has run yet"
    if not b.get("offsite_configured"):
        return "warn", f"server copy only ({b['local_copies']} kept); off-server copy not set up yet"
    return ("pass", f"last {b['last']}, off-server copy ok") if b.get("offsite") else ("fail", "off-server copy failed")


def brain_answers():
    h = json.loads(req("/api/health")[2])
    code, _, body = req("/api/chat", {"text": "Preflight: reply with one short sentence.", "session": "preflight"}, timeout=120)
    events = [json.loads(l[6:]) for l in body.decode().split("\n\n") if l.startswith("data: ")]
    kinds = [e["type"] for e in events]
    if not h["brain_configured"]:
        clean = code == 200 and kinds == ["error"]
        return ("warn", "no API key on this server; clean error returned") if clean else ("fail", f"unclean: {kinds}")
    if "sentence" in kinds and kinds[-1] == "done":
        done = events[-1]
        return "pass", f"first words {done['first_sentence_s']}s, total {done['total_s']}s"
    return "fail", f"events: {events[-1] if events else 'none'}"


print(f"Preflight against {BASE}")
check("Server is up", server_up)
check("Model id is a known, exact id", model_known)
check("Browser receives the files on disk (no stale files)", served_match_disk)
check("Secrets and source are never served", secrets_not_served)
check("Security headers present", security_headers)
check("Oversized requests refused", oversized_refused)
check("Voice: text becomes processed audio", voice_works)
check("Notifications: server keys ready, phones signed up", push_ready)
check("Backups: nightly snapshot exists (and off-server copy)", backups_ok)
check("Brain: real question gets a real streamed answer", brain_answers)

p, f, w = results.count("pass"), results.count("fail"), results.count("warn")
print(f"\n{p} pass, {f} fail, {w} warn")
sys.exit(1 if f else 0)
