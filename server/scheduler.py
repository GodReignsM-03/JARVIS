"""The clock that runs on the server 24/7. Fires due reminders as phone notifications, app open or not.
Reminders live in the database, so a restart never loses one; one that came due while the server was down
fires once as soon as it's back, never twice."""
import asyncio
from datetime import datetime, timezone

from . import db, push

INTERVAL_S = 20


def fire_due() -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.conn() as c:
        due = c.execute("SELECT id, text FROM reminders WHERE status='pending' AND due_utc<=? ORDER BY due_utc",
                        (now,)).fetchall()
        # Mark first, then send: a crash mid-send can't cause a second notification later.
        for r in due:
            c.execute("UPDATE reminders SET status='fired', fired_utc=? WHERE id=?", (now, r["id"]))
    for r in due:
        result = push.send("Jarvis", f"Reminder, sir: {r['text']}")
        db.log("reminder fired", f"#{r['id']} {r['text']} -> sent to {result['sent']} of {result['devices']} device(s)")
    return len(due)


async def run_forever() -> None:
    while True:
        try:
            await asyncio.to_thread(fire_due)
        except Exception as e:
            print(f"[scheduler] {type(e).__name__}: {e}", flush=True)
        await asyncio.sleep(INTERVAL_S)
