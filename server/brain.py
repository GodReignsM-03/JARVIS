"""Jarvis's brain: Claude Opus 5.5, streamed sentence by sentence so the voice can start early."""
import re
import time
from collections import defaultdict
from typing import AsyncIterator

import anthropic

from . import config, spend

VOICE_RULES = """
## Speaking rules (you are heard, not read)
- Your words are converted to speech. Never use markdown, bullet points, emoji, or symbols.
- Write numbers and times the way a person says them ("half seven", "nine fifteen", "twenty dollars").
- Lead with the answer. One or two short sentences unless asked for more.
- Use punctuation for natural pauses: commas, full stops, the occasional ellipsis before something important.
- This is phase 0: you have no access yet to calendars, tasks, email or memory. If asked to do something
  that needs them, say plainly and briefly that it isn't connected yet. Never pretend to have done it.
"""


def _system_prompt() -> str:
    persona = config.PERSONA_FILE.read_text() if config.PERSONA_FILE.exists() else ""
    return persona + "\n" + VOICE_RULES


SYSTEM = _system_prompt()

# Conversation history per session (in memory for phase 0). Kept short for speed and cost.
_history: dict[str, list[dict]] = defaultdict(list)
MAX_TURNS = 12

_client: anthropic.AsyncAnthropic | None = None
_fast_ok = True  # flips off if the account doesn't have fast mode


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


_SENTENCE_END = re.compile(r"(.+?[.!?…])(\s+|$)", re.S)


def _split_ready(buf: str) -> tuple[list[str], str]:
    """Return complete sentences from the buffer, and the leftover partial text."""
    out = []
    while True:
        m = _SENTENCE_END.match(buf)
        if not m or not m.group(2):  # need trailing whitespace to be sure the sentence ended
            break
        out.append(m.group(1).strip())
        buf = buf[m.end():]
    return out, buf


_CLAUSE = re.compile(r"^(.{25,}?[,;:—])\s+(.*)$", re.S)


_TAIL_WORDS = re.compile(r"^(sir|ma'am|then|too|as well|though|of course|indeed)\b", re.I)


def _first_clause(buf: str) -> tuple[str, str]:
    """A first clause long enough to sound natural on its own (e.g. 'I'd suggest the salmon tonight,').
    Only split once we've seen what comes next, and never strand a short tail like ', sir.'"""
    m = _CLAUSE.match(buf)
    if not m:
        return "", buf
    rest = m.group(2)
    if len(rest) < 20 or _TAIL_WORDS.match(rest.lstrip()):
        return "", buf  # wait: the sentence is about to end, or the next words belong with this clause
    return m.group(1).strip(), rest


async def warm_up() -> None:
    """Open the connection to the AI service ahead of time so the first question doesn't pay for it."""
    if config.brain_configured():
        try:
            await client().models.list(limit=1)
        except Exception:
            pass


async def chat(session: str, text: str) -> AsyncIterator[dict]:
    """Yield events: {"type":"sentence","text":...}, then {"type":"done", ...} or {"type":"error", ...}."""
    global _fast_ok
    if config.MODEL not in config.KNOWN_MODELS:
        yield {"type": "error", "message": f"Unknown model '{config.MODEL}'. I have: {sorted(config.KNOWN_MODELS)}"}
        return
    if not config.brain_configured():
        yield {"type": "error", "message": "My brain isn't connected yet, sir. No API key is configured on this server."}
        return

    history = _history[session]
    messages = history + [{"role": "user", "content": text}]
    started = time.monotonic()
    first_sentence_at = None
    spoken: list[str] = []
    buf = ""
    use_fast = config.FAST and _fast_ok and spend.fast_allowed()
    try:
        kwargs = dict(
            model=config.MODEL,
            max_tokens=4000,  # covers thinking + the short spoken answer
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": config.EFFORT_CHAT},  # Opus 5.5 always thinks; "low" = least thinking
            messages=messages,
        )
        if use_fast:
            # Fast mode: the same Opus 5.5, generating up to ~2.5x faster (thinking included), at 2x price.
            streamer = client().beta.messages.stream(speed="fast", betas=["fast-mode-2026-02-01"], **kwargs)
        else:
            streamer = client().messages.stream(**kwargs)
        async with streamer as stream:
            # First sentence goes out alone (fast start); later sentences are grouped into
            # ~150-character chunks so the voice flows in natural phrases instead of stop-start.
            pending = ""
            async for chunk in stream.text_stream:
                buf += chunk
                ready, buf = _split_ready(buf)
                # Speed: don't wait for the whole first sentence if a natural clause is ready.
                if first_sentence_at is None and not ready:
                    clause, rest = _first_clause(buf)
                    if clause:
                        ready, buf = [clause], rest
                for s in ready:
                    if first_sentence_at is None:
                        first_sentence_at = time.monotonic() - started
                        spoken.append(s)
                        yield {"type": "sentence", "text": s}
                        continue
                    pending = f"{pending} {s}".strip()
                    # Send each finished sentence promptly (very short ones ride along with the next),
                    # so the next piece of audio is ready before the current one finishes playing.
                    if len(pending) >= 40:
                        spoken.append(pending)
                        yield {"type": "sentence", "text": pending}
                        pending = ""
            final = await stream.get_final_message()
        tail = f"{pending} {buf}".strip()
        if tail:
            if first_sentence_at is None:
                first_sentence_at = time.monotonic() - started
            spoken.append(tail)
            yield {"type": "sentence", "text": tail}

        if final.stop_reason == "refusal":
            yield {"type": "error", "message": "I'm afraid I can't help with that one, sir."}
            return

        # Append the full assistant content (not just text) so history stays valid.
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in final.content]})
        del history[: max(0, len(history) - MAX_TURNS * 2)]

        u = final.usage
        usage = {
            "input": u.input_tokens,
            "output": u.output_tokens,
            "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
        }
        month_usd = spend.record(usage, use_fast)
        yield {
            "type": "done",
            "fast": use_fast,
            "month_usd": round(month_usd, 2),
            "first_sentence_s": round(first_sentence_at or 0, 2),
            "total_s": round(time.monotonic() - started, 2),
            "usage": {
                "input": u.input_tokens,
                "output": u.output_tokens,
                "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
            },
        }
    except (anthropic.BadRequestError, anthropic.PermissionDeniedError, anthropic.NotFoundError) as e:
        if use_fast and not spoken:
            _fast_ok = False
            print(f"[brain] fast mode unavailable ({e.status_code}: {e.message}); using standard Opus", flush=True)
            async for ev in chat(session, text):
                yield ev
            return
        print(f"[brain] API error {e.status_code}: {e.message}", flush=True)
        yield {"type": "error", "message": f"The AI service returned an error ({e.status_code}), sir. Details are in the server window."}
    except anthropic.AuthenticationError:
        yield {"type": "error", "message": "My API key was refused, sir. It may be wrong or revoked."}
    except anthropic.RateLimitError:
        yield {"type": "error", "message": "I'm being rate limited, sir. Give me a moment."}
    except anthropic.APIStatusError as e:
        print(f"[brain] API error {e.status_code}: {e.message}", flush=True)  # visible in the server window
        yield {"type": "error", "message": f"The AI service returned an error ({e.status_code}), sir. Details are in the server window."}
    except anthropic.APIConnectionError:
        yield {"type": "error", "message": "I can't reach the AI service, sir. The connection seems to be down."}


def reset(session: str) -> None:
    _history.pop(session, None)
