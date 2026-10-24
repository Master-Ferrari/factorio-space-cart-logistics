# -*- coding: utf-8 -*-
"""Раунд 4 одной командой:  python make.py [--from build|render|compose] [--only P] [--views ...]"""

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
        run([BLENDER, "-b", "--factory-startup", "--python", "build_r4.py"])
    if "render" in todo:                     # без --factory-startup (см. 3d/CLAUDE.md)
        extra = (["--only", a.only] if a.only else []) + (["--views", a.views] if a.views else [])
        run([BLENDER, "-b", "r4.blend", "--python", "render_r4.py", "--"] + extra)
    if "compose" in todo:
        run([sys.executable, "compose_r4.py"])


if __name__ == "__main__":
    main()
