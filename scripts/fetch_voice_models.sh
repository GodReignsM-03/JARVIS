#!/usr/bin/env bash
# Downloads the free Kokoro voice model + the two voices Jarvis blends (Apache 2.0).
set -euo pipefail
cd "$(dirname "$0")/.."
D=models/kokoro; mkdir -p "$D/voices"
B=https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main
[ -f "$D/model.onnx" ] || curl -fL -o "$D/model.onnx" "$B/onnx/model.onnx"
for v in bm_daniel bm_george; do [ -f "$D/voices/$v.bin" ] || curl -fL -o "$D/voices/$v.bin" "$B/voices/$v.bin"; done
python3 -I - "$D" <<'PY'
import sys, numpy as np
d = sys.argv[1]
np.savez(f"{d}/voices.npz", **{n: np.fromfile(f"{d}/voices/{n}.bin", dtype=np.float32).reshape(-1, 1, 256)
                               for n in ["bm_daniel", "bm_george"]})
print("voices.npz written")
PY
