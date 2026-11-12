"""The things Jarvis can actually do. Every tool returns a dict that states exactly what happened,
so Jarvis only confirms what the database confirms."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(db.get_setting("timezone", "America/Chicago"))
    except Exception:
        return ZoneInfo("America/Chicago")


def _local(utc_iso: str | None) -> str:
    if not utc_iso:
        return "never"
    return datetime.fromisoformat(utc_iso).astimezone(tz()).strftime("%a %d %b %Y, %I:%M %p").replace(" 0", " ")


def _parse_local(s: str) -> datetime:
    """'2026-11-14T09:00' (owner's local time) -> aware UTC datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz())
    return dt.astimezone(timezone.utc)


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


TOOLS = [
    {"name": "create_reminder", "strict": True,
     "description": "Create a reminder that will be pushed to the owner's phone at the given local time. "
                    "If the owner gives only a day, use 09:00. Returns the saved reminder.",
     "input_schema": _obj({"text": {"type": "string", "description": "What to remind about, short."},
                           "due_local": {"type": "string", "description": "Local date-time, format YYYY-MM-DDTHH:MM"}},
                          ["text", "due_local"])},
    {"name": "list_reminders", "strict": True,
     "description": "List upcoming (pending) reminders, soonest first.",
     "input_schema": _obj({}, [])},
    {"name": "update_reminder", "strict": True,
     "description": "Change a pending reminder's time and/or text. Use empty string for a field that stays the same.",
     "input_schema": _obj({"id": {"type": "integer"}, "due_local": {"type": "string"}, "text": {"type": "string"}},
                          ["id", "due_local", "text"])},
    {"name": "cancel_reminder", "strict": True,
     "description": "Cancel (delete) a pending reminder. Ask the owner first unless they just asked to undo it.",
     "input_schema": _obj({"id": {"type": "integer"}}, ["id"])},
    {"name": "log_routine", "strict": True,
     "description": "Record that the owner just did a routine (e.g. 'laundry', 'shave', 'clean room', 'gave Max heartworm pill'). "
                    "Creates the routine if new. Use short lowercase names and reuse existing names.",
     "input_schema": _obj({"name": {"type": "string"}}, ["name"])},
    {"name": "set_routine_interval", "strict": True,
     "description": "Set how often (in days) a routine should happen, e.g. laundry every 7 days.",
     "input_schema": _obj({"name": {"type": "string"}, "every_days": {"type": "number"}}, ["name", "every_days"])},
    {"name": "routines_status", "strict": True,
     "description": "Every routine with days since last done, its interval, and whether it's overdue.",
     "input_schema": _obj({}, [])},
    {"name": "log_water", "strict": True,
     "description": "Log water the owner drank, in millilitres (a standard bottle is 500 ml, a glass 250 ml).",
     "input_schema": _obj({"ml": {"type": "integer"}}, ["ml"])},
    {"name": "water_status", "strict": True,
     "description": "Today's water total and the daily goal.",
     "input_schema": _obj({}, [])},
    {"name": "set_water_goal", "strict": True,
     "description": "Set the daily water goal in millilitres.",
     "input_schema": _obj({"ml": {"type": "integer"}}, ["ml"])},
    {"name": "remember", "strict": True,
     "description": "Save a durable fact about the owner's life (people, pets, preferences, goals, sizes, places). "
                    "Use when the owner states something worth remembering or says 'remember that'.",
     "input_schema": _obj({"fact": {"type": "string"},
                           "category": {"type": "string", "enum": ["person", "pet", "preference", "goal", "health",
                                                                   "business", "church", "money", "other"]}},
                          ["fact", "category"])},
    {"name": "forget", "strict": True,
     "description": "Remove a remembered fact by its id (when the owner says it's wrong or to forget it).",
     "input_schema": _obj({"id": {"type": "integer"}}, ["id"])},
    {"name": "save_note", "strict": True,
     "description": "Save an idea or note ('save this idea for Cross Spur', 'note to self').",
     "input_schema": _obj({"text": {"type": "string"},
                           "tag": {"type": "string", "description": "e.g. cross-spur, church, personal, fitness"}},
                          ["text", "tag"])},
    {"name": "search_notes", "strict": True,
     "description": "Find saved notes/ideas by words or tag. Empty query lists the most recent.",
     "input_schema": _obj({"query": {"type": "string"}}, ["query"])},
    {"name": "set_nudges", "strict": True,
     "description": "Turn Jarvis's own nudges on or off: morning summary (6:30 AM if not opened yet), water checks, "
                    "overdue-routine reminder (6 PM). Use when the owner says e.g. 'stop the water reminders'.",
     "input_schema": _obj({"kind": {"type": "string", "enum": ["morning", "water", "routines"]},
                           "on": {"type": "boolean"}}, ["kind", "on"])},
    {"name": "briefing", "strict": True,
     "description": "Everything for 'what does my day look like' / 'morning, Jarvis': today's and upcoming reminders, "
                    "overdue routines, water so far. Calendar is not connected yet.",
     "input_schema": _obj({}, [])},
    {"name": "recent_activity", "strict": True,
     "description": "What Jarvis has done recently (the activity log), for 'what did you do today?'.",
     "input_schema": _obj({"hours": {"type": "integer"}}, ["hours"])},
]


# ---------- implementations ----------
def create_reminder(text: str, due_local: str) -> dict:
    due = _parse_local(due_local)
    if due < datetime.now(timezone.utc) - timedelta(minutes=1):
        return {"ok": False, "error": f"That time ({_local(due.isoformat())}) is in the past."}
    with db.conn() as c:
        # Duplicate guard: the same reminder at the same time within the last 2 minutes is a retry, not a new one.
        dup = c.execute("SELECT id FROM reminders WHERE text=? AND due_utc=? AND status='pending' AND created_utc>?",
                        (text, due.isoformat(timespec="seconds"),
                         (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(timespec="seconds"))).fetchone()
        if dup:
            return {"ok": True, "id": dup["id"], "note": "already saved", "text": text, "due": _local(due.isoformat())}
        cur = c.execute("INSERT INTO reminders (text, due_utc, created_utc) VALUES (?,?,?)",
                        (text, due.isoformat(timespec="seconds"), db.now_utc()))
        rid = cur.lastrowid
    db.log("reminder created", f"#{rid} {text} @ {_local(due.isoformat())}")
    return {"ok": True, "id": rid, "text": text, "due": _local(due.isoformat())}


def list_reminders() -> dict:
    with db.conn() as c:
        rows = c.execute("SELECT id, text, due_utc FROM reminders WHERE status='pending' ORDER BY due_utc LIMIT 30").fetchall()
    return {"ok": True, "reminders": [{"id": r["id"], "text": r["text"], "due": _local(r["due_utc"])} for r in rows]}


def update_reminder(id: int, due_local: str, text: str) -> dict:
    with db.conn() as c:
        r = c.execute("SELECT * FROM reminders WHERE id=? AND status='pending'", (id,)).fetchone()
        if not r:
            return {"ok": False, "error": f"No pending reminder #{id}."}
        new_due = _parse_local(due_local).isoformat(timespec="seconds") if due_local else r["due_utc"]
        new_text = text or r["text"]
        c.execute("UPDATE reminders SET due_utc=?, text=? WHERE id=?", (new_due, new_text, id))
    db.log("reminder changed", f"#{id} {new_text} @ {_local(new_due)}")
    return {"ok": True, "id": id, "text": new_text, "due": _local(new_due)}


def cancel_reminder(id: int) -> dict:
    with db.conn() as c:
        n = c.execute("UPDATE reminders SET status='cancelled' WHERE id=? AND status='pending'", (id,)).rowcount
    if not n:
        return {"ok": False, "error": f"No pending reminder #{id}."}
    db.log("reminder cancelled", f"#{id}")
    return {"ok": True, "id": id, "cancelled": True}


def log_routine(name: str) -> dict:
    name = name.strip().lower()
    now = db.now_utc()
    with db.conn() as c:
        prev = c.execute("SELECT last_done_utc, every_days FROM routines WHERE name=?", (name,)).fetchone()
        c.execute("INSERT INTO routines (name, last_done_utc, created_utc) VALUES (?,?,?) "
                  "ON CONFLICT(name) DO UPDATE SET last_done_utc=excluded.last_done_utc", (name, now, now))
        c.execute("INSERT INTO routine_log (name, done_utc) VALUES (?,?)", (name, now))
    db.log("routine done", name)
    out = {"ok": True, "routine": name, "logged": _local(now), "new_routine": prev is None}
    if prev and prev["last_done_utc"]:
        out["previous"] = _local(prev["last_done_utc"])
    return out


def set_routine_interval(name: str, every_days: float) -> dict:
    name = name.strip().lower()
    with db.conn() as c:
        c.execute("INSERT INTO routines (name, every_days, created_utc) VALUES (?,?,?) "
                  "ON CONFLICT(name) DO UPDATE SET every_days=excluded.every_days", (name, every_days, db.now_utc()))
    db.log("routine interval", f"{name}: every {every_days:g} days")
    return {"ok": True, "routine": name, "every_days": every_days}


def routines_status() -> dict:
    now = datetime.now(timezone.utc)
    with db.conn() as c:
        rows = c.execute("SELECT * FROM routines ORDER BY name").fetchall()
    out = []
    for r in rows:
        days = (now - datetime.fromisoformat(r["last_done_utc"])).total_seconds() / 86400 if r["last_done_utc"] else None
        out.append({"routine": r["name"], "last_done": _local(r["last_done_utc"]),
                    "days_since": round(days, 1) if days is not None else None, "every_days": r["every_days"],
                    "overdue": bool(r["every_days"] and days is not None and days >= r["every_days"])})
    return {"ok": True, "routines": out}


def _today() -> str:
    return datetime.now(tz()).strftime("%Y-%m-%d")


def log_water(ml: int) -> dict:
    if not 0 < ml <= 3000:
        return {"ok": False, "error": "That amount looks wrong."}
    with db.conn() as c:
        c.execute("INSERT INTO water (ml, local_day, logged_utc) VALUES (?,?,?)", (ml, _today(), db.now_utc()))
    db.log("water", f"+{ml} ml")
    return water_status()


def water_status() -> dict:
    with db.conn() as c:
        total = c.execute("SELECT COALESCE(SUM(ml),0) t FROM water WHERE local_day=?", (_today(),)).fetchone()["t"]
    goal = int(db.get_setting("water_goal_ml", "3000"))
    return {"ok": True, "today_ml": total, "goal_ml": goal, "remaining_ml": max(0, goal - total)}


def set_water_goal(ml: int) -> dict:
    db.set_setting("water_goal_ml", str(ml))
    db.log("water goal", f"{ml} ml")
    return {"ok": True, "goal_ml": ml}


def remember(fact: str, category: str) -> dict:
    with db.conn() as c:
        rid = c.execute("INSERT INTO memories (fact, category, created_utc) VALUES (?,?,?)",
                        (fact, category, db.now_utc())).lastrowid
    db.log("remembered", fact)
    return {"ok": True, "id": rid, "fact": fact}


def forget(id: int) -> dict:
    with db.conn() as c:
        n = c.execute("UPDATE memories SET active=0 WHERE id=? AND active=1", (id,)).rowcount
    if not n:
        return {"ok": False, "error": f"No memory #{id}."}
    db.log("forgot", f"#{id}")
    return {"ok": True, "id": id, "forgotten": True}


def save_note(text: str, tag: str) -> dict:
    with db.conn() as c:
        rid = c.execute("INSERT INTO notes (text, tag, created_utc) VALUES (?,?,?)",
                        (text, tag.strip().lower(), db.now_utc())).lastrowid
    db.log("note saved", f"[{tag}] {text}")
    return {"ok": True, "id": rid, "tag": tag}


def search_notes(query: str) -> dict:
    with db.conn() as c:
        if query.strip():
            like = f"%{query.strip()}%"
            rows = c.execute("SELECT * FROM notes WHERE text LIKE ? OR tag LIKE ? ORDER BY id DESC LIMIT 15",
                             (like, like)).fetchall()
        else:
            rows = c.execute("SELECT * FROM notes ORDER BY id DESC LIMIT 10").fetchall()
    return {"ok": True, "notes": [{"id": r["id"], "tag": r["tag"], "text": r["text"], "saved": _local(r["created_utc"])}
                                  for r in rows]}


def recent_activity(hours: int) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(hours=max(1, min(hours, 720)))).isoformat(timespec="seconds")
    with db.conn() as c:
        rows = c.execute("SELECT * FROM activity WHERE ts_utc>? ORDER BY id DESC LIMIT 40", (since,)).fetchall()
    return {"ok": True, "activity": [{"when": _local(r["ts_utc"]), "action": r["action"], "detail": r["detail"]} for r in rows]}


def set_nudges(kind: str, on: bool) -> dict:
    db.set_setting(f"nudge_{kind}", "on" if on else "off")
    db.log("nudges", f"{kind} {'on' if on else 'off'}")
    return {"ok": True, "kind": kind, "on": on}


def briefing() -> dict:
    return {"ok": True, "now": datetime.now(tz()).strftime("%A %d %B, %I:%M %p"),
            "reminders": list_reminders()["reminders"][:8],
            "overdue_routines": [r for r in routines_status()["routines"] if r["overdue"]],
            "water": water_status(), "calendar": "not connected yet"}


HANDLERS = {t["name"]: globals()[t["name"]] for t in TOOLS}


def run(name: str, args: dict) -> dict:
    fn = HANDLERS.get(name)
    if not fn:
        return {"ok": False, "error": f"Unknown tool {name}"}
    try:
        return fn(**args)
    except Exception as e:  # report honestly, never pretend
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def context_block() -> str:
    """Fresh facts for this turn: the time, what Jarvis remembers, what's pending. Appended to the user's message."""
    now = datetime.now(tz())
    with db.conn() as c:
        mem = c.execute("SELECT id, fact FROM memories WHERE active=1 ORDER BY id LIMIT 150").fetchall()
        pending = c.execute("SELECT COUNT(*) n FROM reminders WHERE status='pending'").fetchone()["n"]
    lines = [f"[Context, not from the owner] Now: {now.strftime('%A %d %B %Y, %I:%M %p')} ({now.tzinfo})."]
    lines.append(f"Pending reminders: {pending}.")
    if mem:
        lines.append("Things you remember about the owner (id: fact): " + "; ".join(f"{m['id']}: {m['fact']}" for m in mem))
    return "\n".join(lines)
