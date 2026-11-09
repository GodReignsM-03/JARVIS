"""Jarvis configuration. Secrets come from the environment or a .env file (chmod 600),
which lives in the project root and is never served to the browser."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
PERSONA_FILE = ROOT / "persona" / "persona.md"


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# Exact model ids Jarvis is allowed to use. A name that isn't here is refused, never guessed.
KNOWN_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"}
MODEL = os.environ.get("JARVIS_MODEL", "claude-opus-5-5")
EFFORT_CHAT = os.environ.get("JARVIS_EFFORT", "low")  # casual voice chat: low effort = faster, cheaper

HOST = os.environ.get("JARVIS_HOST", "127.0.0.1")
PORT = int(os.environ.get("JARVIS_PORT", "4700"))

VOICE_MODEL_DIR = Path(os.environ.get("JARVIS_VOICE_DIR", ROOT / "models" / "kokoro"))

# Max characters accepted per request (abuse / runaway guard).
MAX_TEXT = 2000


def brain_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
