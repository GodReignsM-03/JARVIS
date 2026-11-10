"""Safely save your Anthropic API key into .env (hidden while you paste, checked before saving).
Run:  .venv\\Scripts\\python scripts\\set_key.py"""
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"


def main() -> int:
    print("Paste your Anthropic API key and press Enter.")
    print("(It stays hidden - you won't see anything as you paste. That's normal.)")
    key = getpass.getpass("Key: ").strip()

    if not re.fullmatch(r"sk-ant-[A-Za-z0-9_\-]{20,}", key):
        print("\nThat doesn't look like an API key (it should start with sk-ant- and contain no spaces).")
        print("Nothing was saved. Copy ONLY the key from console.anthropic.com and run this again.")
        return 1

    print("Checking the key with Anthropic (free check, no charge)...")
    req = urllib.request.Request("https://api.anthropic.com/v1/models",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            json.load(r)
    except urllib.error.HTTPError as e:
        print(f"\nAnthropic rejected that key (HTTP {e.code}). Nothing was saved.")
        print("Make sure it's a NEW key that hasn't been deleted, and run this again.")
        return 1
    except urllib.error.URLError as e:
        print(f"\nCouldn't reach Anthropic ({e.reason}). Check your internet and try again. Nothing was saved.")
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
