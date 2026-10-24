# -*- coding: utf-8 -*-
"""Пересборка каретки v9c одной командой (системный python):

  python v9c/make.py                         # build → render → compose
  python v9c/make.py --from render           # без пересборки .blend
  python v9c/make.py --from compose          # только листы
  python v9c/make.py --only A --views single,ortho

Результат: v9c/out/sheet.png, v9c/out/metrics.json.
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
STAGES = ["build", "render", "compose"]


def run(cmd):
    print(">", " ".join(cmd), flush=True)
    p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = p.stdout + p.stderr
    for line in out.splitlines():
        if any(k in line for k in ("saved", "sheet", "wheel top", "Error", "Traceback", "  File")) \
                or line[:2] in ("A ", "B "):
            print("   ", line)
    if p.returncode != 0 or "Traceback" in out:
        sys.exit("stage failed: %s" % cmd[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", choices=STAGES, default="build")
    ap.add_argument("--only", default=None)
    ap.add_argument("--views", default=None)
    a = ap.parse_args()
    todo = STAGES[STAGES.index(a.start):]
    if "build" in todo:
        # сборка геометрии рендер не трогает — можно с --factory-startup
        run([BLENDER, "-b", "--factory-startup", "--python", "build.py"])
    if "render" in todo:
        extra = []
        if a.only:
            extra += ["--only", a.only]
        if a.views:
            extra += ["--views", a.views]
        # рендер — без --factory-startup (с ним рендер в фоне виснет)
        run([BLENDER, "-b", "cart_v9c.blend", "--python", "render.py", "--"] + extra)
    if "compose" in todo:
        run([sys.executable, "compose.py"])


if __name__ == "__main__":
    main()
