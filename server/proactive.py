"""Jarvis speaking up on his own: morning summary, overdue routines, water. Each runs at most once a day,
never during quiet hours (9:30 PM - 5:00 AM), and each can be switched off by voice.
Messages are built straight from the database (no AI call), so they cost nothing and can't invent anything."""
from datetime import datetime, timezone

from . import db, push, tools

QUIET_START, QUIET_END = (21, 30), (5, 0)

# name: (local time it runs, setting that switches it on/off)
JOBS = {
    "morning": ((6, 30), "nudge_morning"),
    "water_noon": ((12, 0), "nudge_water"),
    "water_afternoon": ((15, 30), "nudge_water"),
    "routines": ((18, 0), "nudge_routines"),
}


def quiet(now: datetime) -> bool:
    hm = (now.hour, now.minute)
    return hm >= QUIET_START or hm < QUIET_END


def enabled(setting: str) -> bool:
    return db.get_setting(setting, "on") == "on"


def morning_text(now: datetime) -> str | None:
    if db.get_setting("last_chat_day") == now.strftime("%Y-%m-%d"):
        return None  # he already talked to Jarvis today; no need
    today = now.strftime("%Y-%m-%d")
    with db.conn() as c:
        rows = c.execute("SELECT text, due_utc FROM reminders WHERE status='pending' ORDER BY due_utc").fetchall()
    todays = [r["text"] for r in rows
              if datetime.fromisoformat(r["due_utc"]).astimezone(now.tzinfo).strftime("%Y-%m-%d") == today]
    overdue = [r["routine"] for r in tools.routines_status()["routines"] if r["overdue"]]
    from . import gcal
    events = gcal.today_events()
    parts = ["Good morning, sir."]
    if events:
        first = events[0]
        parts.append(f"{len(events)} on the calendar, starting with {first['title']} ({first['when'].split(', ')[-1]}).")
    if todays:
        parts.append(f"Today: {', '.join(todays[:4])}.")
    if overdue:
        parts.append(f"Overdue: {', '.join(overdue[:3])}.")
    if len(parts) == 1:
        parts.append("Nothing pressing today.")
    return " ".join(parts)


def water_text(now: datetime) -> str | None:
    with db.conn() as c:
        used = c.execute("SELECT COUNT(*) n FROM water WHERE logged_utc > datetime('now','-7 days')").fetchone()["n"]
    if not used:
        return None  # only nudge once he's actually tracking water
    w = tools.water_status()
    awake_fraction = min(1.0, max(0.0, (now.hour + now.minute / 60 - 5) / 16.5))  # 5 AM to 9:30 PM
    expected = w["goal_ml"] * awake_fraction
    if w["today_ml"] >= expected * 0.8:
        return None
    return f"Water check, sir: {w['today_ml']} of {w['goal_ml']} ml so far."


def routines_text(now: datetime) -> str | None:
    overdue = [r for r in tools.routines_status()["routines"] if r["overdue"]]
    if not overdue:
        return None
    bits = [f"{r['routine']} ({r['days_since']:.0f} days)" for r in overdue[:3]]
    return "Gentle reminder, sir. Overdue: " + ", ".join(bits) + "."


BUILDERS = {"morning": morning_text, "water_noon": water_text, "water_afternoon": water_text, "routines": routines_text}


def run_due(now: datetime | None = None) -> list[str]:
    """Called every scheduler tick. Returns the messages it sent (for tests and the log)."""
    now = now or datetime.now(tools.tz())
    if quiet(now):
        return []
    sent = []
    day = now.strftime("%Y-%m-%d")
    for name, ((h, m), setting) in JOBS.items():
        if (now.hour, now.minute) < (h, m) or db.get_setting(f"ran_{name}") == day:
            continue
        db.set_setting(f"ran_{name}", day)  # mark first: never twice, even if sending fails
        if (now.hour * 60 + now.minute) - (h * 60 + m) > 120:
            continue  # too late today (e.g. server was off): don't send a morning summary at 3 PM
        if not enabled(setting):
            continue
        text = BUILDERS[name](now)
        if text:
            result = push.send("Jarvis", text)
            db.log(f"nudge {name}", f"{text} -> {result['sent']} device(s)")
            sent.append(text)
    return sent


def note_chat() -> None:
    db.set_setting("last_chat_day", datetime.now(tools.tz()).strftime("%Y-%m-%d"))
