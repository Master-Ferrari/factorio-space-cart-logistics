# -*- coding: utf-8 -*-
"""Пересборка блокинга каретки v5a одной командой.

  python v5a/make.py                     # всё: build → render → compose
  python v5a/make.py --from render       # с рендера (blend уже собран)
  python v5a/make.py --from compose      # только листы
  python v5a/make.py --only A --views solo,ortho

Стадии: build_v5a.py (Блендер, --factory-startup) → render_v5a.py (Блендер, без
--factory-startup: с ним рендер в фоне виснет) → compose_v5a.py (системный python).
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
STAGES = ["build", "render", "compose"]


def run(cmd):
    print(">", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    for line in out.splitlines():
        if any(k in line for k in ("built", "saved", "rendered", "dy avg", "Error", "Traceback", "error:")):
            print("  ", line)
    if r.returncode != 0 or "Traceback" in out:
        print(out[-4000:])
        sys.exit(1)


def main():
    a = sys.argv[1:]
    start = a[a.index("--from") + 1] if "--from" in a else "build"
    extra = []
    for k in ("--only", "--views"):
        if k in a:
            extra += [k, a[a.index(k) + 1]]
    stages = STAGES[STAGES.index(start):]
    if "build" in stages:
        only = ["--only", a[a.index("--only") + 1]] if "--only" in a else []
        run([BLENDER, "-b", "--factory-startup", "--python", "build_v5a.py", "--"] + only)
    if "render" in stages:
        run([BLENDER, "-b", "cart_v5a.blend", "--python", "render_v5a.py", "--"] + extra)
    if "compose" in stages:
        run([sys.executable, "compose_v5a.py"])


if __name__ == "__main__":
    main()
