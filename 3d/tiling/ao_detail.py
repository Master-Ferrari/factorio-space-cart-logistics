"""Мелкая часть AO из Painter: AO / размытый AO. Крупная тень запечённых путей уходит, узкие желобки
остаются. Подложка render_tile.py берёт её вместо полного AO (BASE_AO_DETAIL).

  python 3d/tiling/ao_detail.py [радиус, px текстуры 4096]   -> 3d/tiling/render/ao_detail_r<радиус>.png
"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
R = int(sys.argv[1]) if len(sys.argv) > 1 else 24
ao = Image.open(HERE.parent / "fininal tex" / "DefaultMaterial_AO.png").convert("L")
a = np.asarray(ao, dtype=np.float32)
b = np.asarray(ao.filter(ImageFilter.GaussianBlur(R)), dtype=np.float32)
d = np.clip(a / np.maximum(b, 1.0), 0.0, 1.0)
out = HERE / "render" / f"ao_detail_r{R}.png"
Image.fromarray((d * 255).astype(np.uint8)).save(out)
print(out, "mean", round(float(d.mean()), 3))
