"""Jarvis web server (phase 0). Serves ONLY the web/ folder plus the /api routes."""
import asyncio
import json
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from . import brain, config, voice

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

STATIC = {  # explicit allowlist: nothing else is ever served
    "/": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/orb.js": ("orb.js", "text/javascript"),
    "/style.css": ("style.css", "text/css"),
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "model": config.MODEL,
        "model_known": config.MODEL in config.KNOWN_MODELS,
        "brain_configured": config.brain_configured(),
        "voice_loaded": voice.loaded(),
        "fast": config.FAST,
    }


async def _json_body(request: Request) -> dict:
    raw = await request.body()
    if len(raw) > 8192:
        raise HTTPException(413, "request too large")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    text = str(body.get("text", "")).strip()
    if not text or len(text) > config.MAX_TEXT:
        raise HTTPException(400, "text missing or too long")
    body["text"] = text
    return body


@app.post("/api/tts")
async def tts(request: Request):
    body = await _json_body(request)
    tone = str(body.get("tone", voice.DEFAULT_TONE))
    t0 = time.monotonic()
    try:
        audio = await asyncio.to_thread(voice.speak, body["text"], tone)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    ms = int((time.monotonic() - t0) * 1000)
    return Response(audio, media_type="audio/mpeg", headers={"X-TTS-ms": str(ms)})


@app.post("/api/chat")
async def chat(request: Request):
    body = await _json_body(request)
    session = str(body.get("session", "default"))[:64]

    async def events():
        async for ev in brain.chat(session, body["text"]):
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/api/reset")
async def reset(request: Request):
    raw = await request.body()
    session = str(json.loads(raw or b"{}").get("session", "default"))[:64]
    brain.reset(session)
    return {"ok": True}


@app.get("/{path:path}")
async def static(path: str):
    entry = STATIC.get("/" + path)
    if not entry:
        raise HTTPException(404)
    name, media = entry
    return FileResponse(config.WEB_DIR / name, media_type=media)


@app.on_event("startup")
async def warm_up():
    await brain.warm_up()
    # Load the voice and pre-render the greeting so the first words are instant.
    if await asyncio.to_thread(voice.load):
        for line in ["Hello, sir."]:
            await asyncio.to_thread(voice.speak, line)
