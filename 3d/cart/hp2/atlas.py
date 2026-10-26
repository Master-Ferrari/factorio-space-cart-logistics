# -*- coding: utf-8 -*-
"""Рендер игрового атласа каретки: 32 курса с картами автора (Cycles), два прохода на курс.

Запуск:  blender -b cart_hp2_fix.blend --python atlas.py -- [--samples N] [--facings 1,9,17 --out out/leds_test]
         [--wheels 15,0.006 --out out/atlas_b]   # второй лист: колёса повёрнуты и сдвинуты (wheels.py)
         [--lamps-off]  # днём лампы выключены (тёмное стекло), горят только в слое света
         [--close 13]   # + крупно в полном разрешении: игровой ракурс курса 13 (256 px/тайл) и перспектива 3/4
(без --factory-startup: с ним Cycles в фоне виснет). Свет, HDRI, материалы — как у render_tex.py --painted.
Кадр курса i (1..100) — graphics_variation = facing: 1 = север, по часовой (scripts/geometry.lua: facing_from).
Пишет out/atlas/obj_NN.png (каретка без земли), out/atlas/sh_NN.png (только тень: shadow catcher, каретка невидима камере, но тень отбрасывает),
light_NN.png (светят только ходовые огни, leds.light_only — для карты освещения), frame.json.
Тень, свет и лист собирает compose_atlas.py.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)

import scl3d as K  # noqa: E402
import fix  # noqa: E402
import wheels  # noqa: E402
import leds  # noqa: E402
import painted  # noqa: E402
import render_tex as R  # noqa: E402

OUT = os.path.join(HERE, "out", "atlas")
FACINGS = 100                       # шаг 3.6°: по кадру на каждую клетку поворота (25 на четверть круга)
# 2×2 тайла вокруг точки земли (0, 0, 0): сверху 1.25 (корпус ~0.8), справа 1.0 (тень от солнца слева)
FRAME = K.Frame(-1.0, 1.25, 2.0, 2.0, K.PX_RENDER)


def heading(i):
    """facing 1..32 (по часовой от севера) → поворот вокруг Z (против часовой); 0 — модель смотрит на север."""
    return -2 * math.pi * (i - 1) / FACINGS


def main():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    samples = int(a[a.index("--samples") + 1]) if "--samples" in a else 64
    facings = [int(x) for x in a[a.index("--facings") + 1].split(",")] if "--facings" in a else range(1, FACINGS + 1)
    out = os.path.join(HERE, a[a.index("--out") + 1]) if "--out" in a else OUT
    os.makedirs(out, exist_ok=True)
    R.setup(samples)
    painted.apply()
    fix.apply("--lamps-off" in a)   # панель и лампы автора (cart_hp2_fix.blend), перёд — +Y, как в его модели
    if "--wheels" in a:
        wheels.apply(*(float(x) for x in a[a.index("--wheels") + 1].split(",")))
    # тень отдельным проходом — целая, без выреза под корпусом (вычитание альф давало дыру и светлые швы по контуру)
    cart = list(K._bpy().data.collections["CART_A"].all_objects)
    v = R.view_coll()
    for o in [o for o in v.objects if o.type == 'LIGHT']:
        K._bpy().data.objects.remove(o, do_unlink=True)
    R.spring_light(K.sun("sun", v, R.SUN_DIR, R.SUN_E, 2.0), v)
    for i in facings:
        v = R.view_coll()
        world = K.empty("WORLD", v, scale=(1, K.STRETCH, 1))
        R.instance(v, 0, 0, heading(i), world)
        K.game_camera("cam", v, FRAME)
        R.render(os.path.join(out, "obj_%03d.png" % i))
        R.catcher(v, world)
        for o in cart:
            o.visible_camera = False
        R.render(os.path.join(out, "sh_%03d.png" % i))
        for o in cart:
            o.visible_camera = True
    if "--close" in a:
        h = heading(int(a[a.index("--close") + 1]))
        v = R.view_coll()
        world = K.empty("WORLD", v, scale=(1, K.STRETCH, 1))
        R.instance(v, 0, 0, h, world)
        R.catcher(v, world)
        K.game_camera("cam", v, K.Frame(-0.6, 0.95, 1.2, 1.2, K.PX_RENDER * 3))
        R.render(os.path.join(out, "close_game.png"))
        v = R.view_coll()
        R.instance(v, 0, 0, h, None)
        R.catcher(v, None)
        K.free_camera("cam", v, (0, 0, 0.32), (62, 0, 38), 0.95, (1100, 1100))
        R.render(os.path.join(out, "close_persp.png"))
    fix.lamps_on()
    leds.light_only()
    K._bpy().context.scene.view_settings.view_transform = 'Standard'       # линейно, без выжигания цвета AgX
    for i in facings:
        v = R.view_coll()
        world = K.empty("WORLD", v, scale=(1, K.STRETCH, 1))
        R.instance(v, 0, 0, heading(i), world)
        K.game_camera("cam", v, FRAME)
        R.render(os.path.join(out, "light_%03d.png" % i))
    with open(os.path.join(out, "frame.json"), "w", encoding="utf-8") as f:
        json.dump(dict(frame=FRAME.to_dict(), ground=FRAME.px(0, 0, 0), facings=FACINGS), f, indent=1)


if __name__ == "__main__":
    main()
