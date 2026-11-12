# Phase 0 status

| Piece | Status | Evidence |
|---|---|---|
| Always-on server (Oracle Always Free, Ubuntu ARM) | ✅ Live | Installer completed; owner reached it from iPhone |
| HTTPS + login (Caddy, sslip.io, basic auth) | ✅ Live | Owner signed in on iPhone Safari |
| Brain: Claude Opus 5.5, streamed | ✅ Working | Owner had a spoken conversation on laptop and iPhone |
| Voice: Jarvis H (85% Daniel / 15% George), AI 2.5, speed 0.95 | ✅ Working | "Hello, sir." + spoken answers on both devices |
| Orb UI (desktop + phone) | ✅ Working | |
| "Hey Jarvis" while open, interrupts | ✅ Built, ⏳ owner to confirm on iPhone | |
| Speed: chime + "One moment, sir." + clause streaming | ✅ Built, ⏳ owner's verdict on server speed | Stopwatch panel visible on desktop layout |
| Optional Opus fast mode (off) + monthly spend guard | ✅ Built | |
| Laptop version (start_jarvis.bat, self-updating) | ✅ Working | |

Open housekeeping: raise Anthropic monthly limit from $10 to $30; delete unused API keys.

# Phase 1a status (verified on the owner's iPhone, 2026-11-12)

| Piece | Status | Evidence |
|---|---|---|
| Voice reminders saved to the server database | ✅ Working | Owner set "remind me in two minutes"; ✓ receipt shown |
| Reminders delivered with the app closed (Web Push, Home Screen app) | ✅ Working | Notification arrived with Jarvis closed |
| Test notification on enabling | ✅ Working | Owner received it |
| Routines, water, memory, notes, activity log | ✅ Built + tested on a test database, ⏳ owner to try by voice | Tool tests passed: duplicates blocked, past times refused, due reminder fires exactly once |
| Append-only history (Opus 5.5 rule) + safe-mode fallback | ✅ Built | Simulated tool conversation passed |

Not yet built: nightly backups, proactive nudges (overdue routines, water), morning briefing, Google Calendar.
