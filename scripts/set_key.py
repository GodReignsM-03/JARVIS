"""Save your Anthropic API key into .env.
Copy the key (Copy button in console.anthropic.com), then run this. It reads the key straight from
your clipboard - no pasting - checks it with Anthropic (free), and only then saves it.
Run:  .venv\\Scripts\\python scripts\\set_key.py"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"


def read_clipboard() -> str:
    if sys.platform == "win32":
        out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                             capture_output=True, text=True)
    elif sys.platform == "darwin":
        out = subprocess.run(["pbpaste"], capture_output=True, text=True)
    else:
        out = subprocess.run(["xclip", "-o", "-selection", "clipboard"], capture_output=True, text=True)
    return (out.stdout or "").strip()


def describe(text: str) -> str:
    """Safe description of what's on the clipboard: never prints the secret part."""
    if not text:
        return "the clipboard is empty"
    first_line = text.splitlines()[0]
    return f"{len(text)} characters, starts with '{first_line[:10]}'"


def main() -> int:
    key = read_clipboard()
    print(f"Clipboard: {describe(key)}")

    if not key.startswith("sk-ant-") or any(c.isspace() for c in key) or len(key) < 40:
        print("\nThat isn't an API key. Your clipboard holds something else.")
        print("In console.anthropic.com, click the Copy button right next to the new key,")
        print("then come straight back here and run this again (type it, don't paste it).")
        return 1

    print("Checking the key with Anthropic (free, no charge)...")
    req = urllib.request.Request("https://api.anthropic.com/v1/models",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            json.load(r)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        print(f"\nAnthropic said no: HTTP {e.code}. {detail}")
        print("Nothing was saved.")
        return 1
    except urllib.error.URLError as e:
        print(f"\nCouldn't reach Anthropic ({e.reason}). Nothing was saved.")
        return 1

    ENV.write_text(f"ANTHROPIC_API_KEY={key}\n")
    try:
        os.chmod(ENV, 0o600)
    except OSError:
        pass
    print("\nKey works and is saved. Start Jarvis with:  .\\start_jarvis.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
