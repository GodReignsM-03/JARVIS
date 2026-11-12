// Jarvis <-> Google Calendar bridge. Runs inside YOUR Google account (script.google.com).
// Only requests carrying this secret are answered; everything else is refused.
const SECRET = "__JARVIS_SECRET__";

function doPost(e) {
  let req = {};
  try { req = JSON.parse(e.postData.contents); } catch (err) { return out({ ok: false, error: "bad request" }); }
  if (req.secret !== SECRET) return out({ ok: false, error: "unauthorized" });
  try {
    if (req.action === "ping") return out({ ok: true, calendars: CalendarApp.getAllOwnedCalendars().map(c => c.getName()) });
    if (req.action === "list") return out(listEvents(req.start, req.end));
    if (req.action === "create") return out(createEvent(req));
    if (req.action === "move") return out(moveEvent(req));
    if (req.action === "delete") return out(deleteEvent(req));
    return out({ ok: false, error: "unknown action" });
  } catch (err) {
    return out({ ok: false, error: String(err) });
  }
}

function listEvents(start, end) {
  const s = new Date(start), e = new Date(end), events = [];
  CalendarApp.getAllCalendars().forEach(cal => {
    if (cal.isHidden()) return;
    cal.getEvents(s, e).forEach(ev => events.push({
      id: ev.getId(), calendar: cal.getName(), title: ev.getTitle(), allDay: ev.isAllDayEvent(),
      start: ev.getStartTime().toISOString(), end: ev.getEndTime().toISOString(), location: ev.getLocation() || ""
    }));
  });
  events.sort((a, b) => a.start < b.start ? -1 : 1);
  return { ok: true, events: events.slice(0, 50) };
}

function createEvent(r) {
  const ev = CalendarApp.getDefaultCalendar().createEvent(r.title, new Date(r.start), new Date(r.end),
    { location: r.location || "", description: "Added by Jarvis" });
  return { ok: true, id: ev.getId(), title: ev.getTitle(), start: ev.getStartTime().toISOString(), end: ev.getEndTime().toISOString() };
}

function findEvent(id) {
  const ev = CalendarApp.getEventById(id);
  if (!ev) throw new Error("event not found");
  return ev;
}

function moveEvent(r) {
  const ev = findEvent(r.id);
  ev.setTime(new Date(r.start), new Date(r.end));
  return { ok: true, id: ev.getId(), title: ev.getTitle(), start: ev.getStartTime().toISOString(), end: ev.getEndTime().toISOString() };
}

function deleteEvent(r) {
  const ev = findEvent(r.id), title = ev.getTitle();
  ev.deleteEvent();
  return { ok: true, id: r.id, title: title, deleted: true };
}

function out(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
