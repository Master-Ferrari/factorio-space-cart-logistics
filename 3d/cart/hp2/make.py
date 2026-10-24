# -*- coding: utf-8 -*-
"""Пересборка хайполи каретки hp2 одной командой (системный python):

  python hp2/make.py                         # build → render → compose
  python hp2/make.py --from render           # без пересборки .blend
  python hp2/make.py --from compose          # только листы
  python hp2/make.py --only A --views single,ortho
  python hp2/make.py --from compose --tex 01      # материалы: Cycles-рендер + out/sheet_tex.png (+ кадр hp2_tex_01)
  python hp2/make.py --from export               # под покраску: out/cart_hp2_paint.fbx, out/bake/cart_hp2_high.fbx,
                                                 #   cart_hp2_paint.blend, out/uv_check.png (стадия не входит в --from build)
  python hp2/make.py --from export --tex painted # + рендер с картами автора из tex_in/ -> out/sheet_painted.png
  python hp2/make.py --tex painted               # только рендер с картами (export уже собран)

Результат: hp2/out/sheet.png, hp2/out/metrics.json.
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
STAGES = ["build", "render", "compose"]
EXPORT = "export"          # отдельная стадия: облегчённая сетка + UV под покраску (export.py), ~3 мин


def run(cmd):
    print(">", " ".join(cmd), flush=True)
    p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = p.stdout + p.stderr
    for line in out.splitlines():
        if any(k in line for k in ("saved", "sheet", "set cart_", "reimport", "tris high", "painted", "Warning", "wheel top", "body faces", "bumper front", "Error", "Traceback", "  File")) \
                or line[:2] in ("A ", "B "):
            print("   ", line)
    if p.returncode != 0 or "Traceback" in out:
        sys.exit("stage failed: %s" % cmd[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", choices=STAGES + [EXPORT], default="build")
    ap.add_argument("--no-high", action="store_true", help="export: без out/bake/cart_hp2_high.fbx (~100 МБ)")
    ap.add_argument("--only", default=None)
    ap.add_argument("--views", default=None)
    ap.add_argument("--film", default=None, help="NN: снять лист и панели в film/data как hp2_NN")
    ap.add_argument("--tex", default=None, help="NN: материалы — render_tex.py (Cycles) + compose_tex.py -> out/sheet_tex.png;"
                                                " NN — кадр фильма hp2_tex_NN (0 — без кадра)")
    a = ap.parse_args()
    only_painted = a.tex == "painted" and "--from" not in sys.argv     # --tex painted без --from: только рендер с картами
    todo = [] if a.start == EXPORT or only_painted else STAGES[STAGES.index(a.start):]
    if a.start == EXPORT:
        run([BLENDER, "-b", "--factory-startup", "cart_hp2.blend", "--python", "export.py", "--"]
            + (["--no-high"] if a.no_high else []))
        # проверочные рендеры Workbench (без --factory-startup) и лист out/uv_check.png
        run([BLENDER, "-b", "cart_hp2_paint.blend", "--python", "render_paint.py", "--", "--mode", "checker"])
        run([BLENDER, "-b", "cart_hp2_paint.blend", "--python", "render_paint.py", "--", "--mode", "matcap"])
        run([BLENDER, "-b", "cart_hp2.blend", "--python", "render_paint.py", "--", "--mode", "matcap"])
        run([sys.executable, "compose_uv.py"])
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
        run([BLENDER, "-b", "cart_hp2.blend", "--python", "render.py", "--"] + extra)
    if "compose" in todo:
        run([sys.executable, "compose.py"])
    if a.film:
        # кадр фильма: лист (jpg q90) + панели синхрона (film/src/panels.py, конвейер как у v9c)
        from PIL import Image
        film = os.path.join(HERE, "..", "film")
        Image.open(os.path.join(HERE, "out", "sheet.png")).convert("RGB").save(
            os.path.join(film, "data", "frames", "hp2_%s.jpg" % a.film), quality=90)
        import shutil
        shutil.copy(os.path.join(HERE, "out", "close.png"), os.path.join(film, "data", "frames", "hp2_%s_close.png" % a.film))
        run([sys.executable, os.path.join(film, "src", "panels.py"), HERE, "A",
             os.path.join(film, "data", "panels", "hp2_%s" % a.film)])
    if a.tex == "painted":
        # карты автора (tex_in/<набор>_BaseColor.png …, без них — заглушки) на облегчённой сетке; кадры — из frames.json
        run([BLENDER, "-b", "cart_hp2_paint.blend", "--python", "render_tex.py", "--", "--painted"])
        run([sys.executable, "compose_tex.py", "--painted"])
    elif a.tex is not None:
        # рендер с материалами — без --factory-startup (Cycles в фоне виснет); кадры берёт из out/render/frames.json
        run([BLENDER, "-b", "cart_hp2.blend", "--python", "render_tex.py"])
        run([sys.executable, "compose_tex.py"])
        if a.tex not in ("0", "00"):
            from PIL import Image
            film = os.path.join(HERE, "..", "film")
            Image.open(os.path.join(HERE, "out", "sheet_tex.png")).convert("RGB").save(
                os.path.join(film, "data", "frames", "hp2_tex_%s.jpg" % a.tex), quality=90)
            run([sys.executable, os.path.join(film, "src", "panels.py"), HERE, "T",
                 os.path.join(film, "data", "panels", "hp2_tex_%s" % a.tex)])


if __name__ == "__main__":
    main()
