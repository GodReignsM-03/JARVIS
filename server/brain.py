"""Jarvis's brain: Claude Opus 5.5, streamed sentence by sentence so the voice can start early."""
import re
import time
from collections import defaultdict
from typing import AsyncIterator

import anthropic

from . import config

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


async def chat(session: str, text: str) -> AsyncIterator[dict]:
    """Yield events: {"type":"sentence","text":...}, then {"type":"done", ...} or {"type":"error", ...}."""
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
    try:
        async with client().messages.stream(
            model=config.MODEL,
            max_tokens=4000,  # covers thinking + the short spoken answer
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": config.EFFORT_CHAT},
            messages=messages,
        ) as stream:
            async for chunk in stream.text_stream:
                buf += chunk
                ready, buf = _split_ready(buf)
                for s in ready:
                    if first_sentence_at is None:
                        first_sentence_at = time.monotonic() - started
                    spoken.append(s)
                    yield {"type": "sentence", "text": s}
            final = await stream.get_final_message()
        if buf.strip():
            if first_sentence_at is None:
                first_sentence_at = time.monotonic() - started
            spoken.append(buf.strip())
            yield {"type": "sentence", "text": buf.strip()}

        if final.stop_reason == "refusal":
            yield {"type": "error", "message": "I'm afraid I can't help with that one, sir."}
            return

        # Append the full assistant content (not just text) so history stays valid.
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in final.content]})
        del history[: max(0, len(history) - MAX_TURNS * 2)]

        u = final.usage
        yield {
            "type": "done",
            "first_sentence_s": round(first_sentence_at or 0, 2),
            "total_s": round(time.monotonic() - started, 2),
            "usage": {
                "input": u.input_tokens,
                "output": u.output_tokens,
                "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
            },
        }
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
