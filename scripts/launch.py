"""Jarvis launcher: the only thing you ever run (via start_jarvis.bat).
1. Pulls the latest fixes from GitHub.  2. Installs anything new.  3. Makes sure the voice is installed.
4. Makes sure a WORKING API key is saved (walks you through it if not).  5. Starts Jarvis and opens Chrome.
It never edits .env by hand-written commands, so nothing can get wiped."""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
PY = sys.executable
KEYS_PAGE = "https://console.anthropic.com/settings/keys"


def step(msg: str) -> None:
    print(f"\n== {msg}", flush=True)


# ---------- .env (safe read/write: only ever replaces the one setting it's changing) ----------
def read_env() -> dict:
    out = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def write_env(values: dict) -> None:
    ENV.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    try:
        os.chmod(ENV, 0o600)
    except OSError:
        pass


# ---------- key ----------
def key_status(key: str) -> str:
    """'ok', 'bad', or 'offline'. Free check: lists models, costs nothing."""
    if not key.startswith("sk-ant-") or any(c.isspace() for c in key) or len(key) < 40:
        return "bad"
    req = urllib.request.Request("https://api.anthropic.com/v1/models",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            json.load(r)
        return "ok"
    except urllib.error.HTTPError:
        return "bad"
    except urllib.error.URLError:
        return "offline"


def read_clipboard() -> str:
    if sys.platform == "win32":
        out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, text=True)
    elif sys.platform == "darwin":
        out = subprocess.run(["pbpaste"], capture_output=True, text=True)
    else:
        return ""
    return (out.stdout or "").strip()


def ensure_key() -> bool:
    env = read_env()
    status = key_status(env.get("ANTHROPIC_API_KEY", ""))
    if status == "ok":
        print("Brain key: working.")
        return True
    if status == "offline":
        print("Can't reach Anthropic to check the key (internet down?). Starting anyway.")
        return True

    print("Jarvis needs a working Anthropic API key. Opening the key page in your browser...")
    webbrowser.open(KEYS_PAGE)
    while True:
        print("\n  1. Click 'Create Key', name it jarvis-laptop, create it.")
        print("  2. Click the Copy button RIGHT NEXT TO THE KEY.")
        input("  3. Come back to this window and press Enter. ")
        key = read_clipboard()
        result = key_status(key)
        if result == "ok":
            env["ANTHROPIC_API_KEY"] = key
            write_env(env)
            print("  Key works and is saved.")
            return True
        if result == "offline":
            print("  Can't reach Anthropic right now. Check your internet, then press Enter to try again.")
        else:
            first = key.splitlines()[0][:10] if key else "(empty)"
            print(f"  That isn't a working key (clipboard starts with '{first}'). Copy the key itself and try again.")


# ---------- updates / installs ----------
def update_code() -> None:
    step("Checking for updates")
    r = subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=ROOT, capture_output=True, text=True)
    print("Up to date." if r.returncode == 0 else f"Couldn't update ({r.stderr.strip()[:200]}). Using the current version.")


def install_requirements() -> None:
    req = ROOT / "requirements.txt"
    stamp = ROOT / ".venv" / "requirements.sha"
    digest = hashlib.sha256(req.read_bytes()).hexdigest()
    if stamp.exists() and stamp.read_text() == digest:
        return
    step("Installing updates")
    r = subprocess.run([PY, "-m", "pip", "install", "-q", "-r", str(req)], cwd=ROOT)
    if r.returncode == 0:
        stamp.write_text(digest)


def ensure_voice() -> None:
    if not (ROOT / "models" / "kokoro" / "voices.npz").exists():
        step("Installing Jarvis's voice (one time, ~300 MB)")
        subprocess.run([PY, str(ROOT / "scripts" / "fetch_voice_models.py")], cwd=ROOT, check=True)


def main() -> int:
    os.chdir(ROOT)
    update_code()
    install_requirements()
    ensure_voice()
    step("Checking the brain key")
    ensure_key()
    step("Starting Jarvis (leave this window open; close it to stop him)")
    subprocess.Popen([sys.executable, "-c", "import time, webbrowser; time.sleep(6); webbrowser.open('http://localhost:4700')"])
    return subprocess.call([PY, "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", "4700"], cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
