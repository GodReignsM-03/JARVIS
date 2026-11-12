"""Safely set ONE setting in .env (never wipes the others).  Usage: python scripts/set_setting.py NAME VALUE"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from launch import read_env, write_env  # noqa: E402

if len(sys.argv) != 3 or not sys.argv[1].isidentifier():
    sys.exit("usage: set_setting.py NAME VALUE")
env = read_env()
env[sys.argv[1]] = sys.argv[2]
write_env(env)
print(f"{sys.argv[1]} saved.")
