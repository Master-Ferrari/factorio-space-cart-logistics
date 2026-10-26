# -*- coding: utf-8 -*-
"""Рендер игрового атласа каретки: 32 курса с картами автора (Cycles), два прохода на курс.

Запуск:  blender -b cart_hp2_paint.blend --python atlas.py -- [--samples N]
(без --factory-startup: с ним Cycles в фоне виснет). Свет, HDRI, материалы — как у render_tex.py --painted.
Кадр курса i (1..32) — graphics_variation = facing: 1 = север, по часовой (scripts/geometry.lua: facing_from).
Пишет out/atlas/obj_NN.png (каретка без земли) и out/atlas/all_NN.png (с shadow catcher: каретка + тень),
out/atlas/frame.json. Тень и лист собирает compose_atlas.py.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)

import scl3d as K  # noqa: E402
import painted  # noqa: E402
import render_tex as R  # noqa: E402

OUT = os.path.join(HERE, "out", "atlas")
FACINGS = 32
# 2×2 тайла вокруг точки земли (0, 0, 0): сверху 1.25 (корпус ~0.8), справа 1.0 (тень от солнца слева)
FRAME = K.Frame(-1.0, 1.25, 2.0, 2.0, K.PX_RENDER)


def heading(i):
    """facing 1..32 (по часовой от севера) → поворот вокруг Z (против часовой); 0 — модель смотрит на север."""
    return -2 * math.pi * (i - 1) / FACINGS


def main():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    samples = int(a[a.index("--samples") + 1]) if "--samples" in a else 64
    os.makedirs(OUT, exist_ok=True)
    R.setup(samples)
    painted.apply()
    v = R.view_coll()
    for o in [o for o in v.objects if o.type == 'LIGHT']:
        K._bpy().data.objects.remove(o, do_unlink=True)
    R.spring_light(K.sun("sun", v, R.SUN_DIR, R.SUN_E, 2.0), v)
    for i in range(1, FACINGS + 1):
        v = R.view_coll()
        world = K.empty("WORLD", v, scale=(1, K.STRETCH, 1))
        R.instance(v, 0, 0, heading(i), world)
        K.game_camera("cam", v, FRAME)
        R.render(os.path.join(OUT, "obj_%02d.png" % i))
        R.catcher(v, world)
        R.render(os.path.join(OUT, "all_%02d.png" % i))
    with open(os.path.join(OUT, "frame.json"), "w", encoding="utf-8") as f:
        json.dump(dict(frame=FRAME.to_dict(), ground=FRAME.px(0, 0, 0), facings=FACINGS), f, indent=1)


if __name__ == "__main__":
    main()
