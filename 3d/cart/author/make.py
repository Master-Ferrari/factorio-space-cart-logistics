# -*- coding: utf-8 -*-
"""Пересборка блокинга «концепт автора» одной командой.

  python make.py [--from build|render|compose] [--only K1,K2] [--views ring,side]

build   — build_author.py   → author_blocking.blend
render  — render_author.py  → out/render/*.png (Workbench, без --factory-startup)
compose — compose_author.py → out/*_sheet.png, overview.png, courses32.png, silhouettes.png,
                              sketch_vs_model.png, metrics.json
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
    ap.add_argument("--views", default=None)
    a = ap.parse_args()
    todo = STAGES[STAGES.index(a.start):]
    if "build" in todo:
        run([BLENDER, "-b", "--factory-startup", "--python", "build_author.py"])
    if "render" in todo:
        extra = (["--only", a.only] if a.only else []) + (["--views", a.views] if a.views else [])
        run([BLENDER, "-b", "author_blocking.blend", "--python", "render_author.py", "--"] + extra)
    if "compose" in todo:
        run([sys.executable, "compose_author.py"])


if __name__ == "__main__":
    main()
