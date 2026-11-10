"""Downloads the free Kokoro voice model + the two voices Jarvis blends (Apache 2.0).
Works on Windows, Mac and Linux:  python scripts/fetch_voice_models.py"""
import sys
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "models" / "kokoro"
BASE = "https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main"
VOICES = ["bm_daniel", "bm_george"]


def get(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  already have {dest.name}")
        return
    print(f"  downloading {dest.name} ...", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)


def main() -> int:
    (D / "voices").mkdir(parents=True, exist_ok=True)
    get(f"{BASE}/onnx/model.onnx", D / "model.onnx")
    for v in VOICES:
        get(f"{BASE}/voices/{v}.bin", D / "voices" / f"{v}.bin")
    np.savez(D / "voices.npz", **{v: np.fromfile(D / "voices" / f"{v}.bin", dtype=np.float32).reshape(-1, 1, 256)
                                  for v in VOICES})
    print("Voice model ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
