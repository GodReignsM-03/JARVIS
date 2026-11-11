"""Server version of the key step: asks for the key (hidden), checks it with Anthropic (free), saves it.
--check : exit 0 if a working key is already saved, 1 otherwise."""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from launch import key_status, read_env, write_env  # noqa: E402


def main() -> int:
    env = read_env()
    if "--check" in sys.argv:
        return 0 if key_status(env.get("ANTHROPIC_API_KEY", "")) == "ok" else 1
    print("Jarvis needs his Anthropic API key.")
    print("In console.anthropic.com > API keys: Create Key (name it jarvis-server), click Copy next to the key.")
    while True:
        key = getpass.getpass("Paste it here (hidden - you won't see it) and press Enter: ").strip()
        status = key_status(key)
        if status == "ok":
            env["ANTHROPIC_API_KEY"] = key
            write_env(env)
            print("Key works and is saved.")
            return 0
        print("That key didn't work (or Anthropic couldn't be reached). Try again." if status == "bad"
              else "Couldn't reach Anthropic. Check the connection and try again.")


if __name__ == "__main__":
    sys.exit(main())
