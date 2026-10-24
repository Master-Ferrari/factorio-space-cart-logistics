# -*- coding: utf-8 -*-
"""Пересборка блокинга каретки одной командой.

  python make.py [--from build|render|compose] [--only A,C] [--engine wb|cycles] [--samples 16]

build   — build_blocking.py  → cart_blocking.blend
render  — render_blocking.py → blocking/render/*.png
compose — compose_blocking.py → blocking/*_sheet.png, overview.png, metrics.json
Рендер по умолчанию — Workbench (быстро, без GPU-нагрузки); --engine cycles — как в раундах 1–2.
Рендер — без --factory-startup: с ним Cycles в фоне виснет (замечено на 5.1 + OptiX).
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
STAGES = ["build", "render", "compose"]


def run(cmd):
    print(">", " ".join(cmd))
    subprocess.run(cmd, cwd=HERE, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", choices=STAGES, default="build")
    ap.add_argument("--only", default=None)
    ap.add_argument("--samples", default="16")
    ap.add_argument("--engine", default="wb", choices=["wb", "cycles"])
    a = ap.parse_args()
    todo = STAGES[STAGES.index(a.start):]
    if "build" in todo:
        run([BLENDER, "-b", "--factory-startup", "--python", "build_blocking.py"])
    if "render" in todo:
        extra = ["--samples", a.samples, "--engine", a.engine] + (["--only", a.only] if a.only else [])
        run([BLENDER, "-b", "cart_blocking.blend", "--python", "render_blocking.py", "--"] + extra)
    if "compose" in todo:
        run([sys.executable, "compose_blocking.py"])


if __name__ == "__main__":
    main()
