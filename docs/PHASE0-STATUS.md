# Phase 0 status

| Piece | Status | Evidence |
|---|---|---|
| Voice (Jarvis H, AI 2.5) on the server | ✅ Working | preflight: text → processed MP3 |
| Orb interface (desktop + phone layouts) | ✅ Working | headless browser test, no page errors |
| Tap-to-talk, "end of thought" pause (FINISH_MS = 900) | ✅ Built, ⏳ needs your real mic test | Browser speech recognition can't be exercised headlessly |
| "Hey Jarvis" while the app is open | ✅ Built, ⏳ needs iPhone test | |
| Interrupt ("stop", "wait", tap the orb) | ✅ Built, ⏳ needs real mic test | |
| Brain (Claude Opus 5.5, streamed by sentence) | ✅ Built, ⏳ needs API key on the server | SDK accepted the request shape; server rejected the dummy key as expected |
| Honest errors (no key, bad key, offline) | ✅ Working | spoken + shown: "My brain isn't connected yet, sir." |
| Security basics (allowlisted files only, headers, size limits) | ✅ Working | preflight |
| Mute flag `?mute=1` | ✅ Built | |

Preflight (local, no key): **7 pass, 0 fail, 1 warn** (brain: no key on this machine).
