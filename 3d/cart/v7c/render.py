# -*- coding: utf-8 -*-
"""Рендеры блокинга v7c (Workbench).

Запуск:  blender -b cart_v7c.blend --python render.py -- [--only A,B] [--views field,ring32,single,ortho,hero]
Пишет out/render/<K>_<view>.png (+ _sh.png — проход тени на белой плоскости) и frames.json.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import scl3d as K  # noqa: E402
from params import VARIANTS  # noqa: E402

OUT = os.path.join(HERE, "out", "render")
D90 = math.radians(90)
EAST = -D90                      # курс «на восток» (ход вдоль +X)

# поле 7.5×6 тайлов: колонна N-S, ряд E-W, маршрут с двумя поворотами
FIELD_FRAME = K.Frame(-3.75, 3.25, 7.5, 6.0, K.PX_RENDER)
FIELD_TILES = [(x, y) for y in range(-2, 3) for x in range(-3, 4)]
ROUTES = [
    ([((-2, y), "S", "N") for y in range(-2, 3)], 3, 48),
    ([((0, -1), "W", "E"), ((1, -1), "W", "E"), ((2, -1), "W", "N"), ((2, 0), "S", "N"),
      ((2, 1), "S", "E"), ((3, 1), "W", "E")], 5, 16),
    ([((1, 2), "E", "W"), ((0, 2), "E", "W"), ((-1, 2), "E", "W")], 3, 16),
]
# все 32 курса (шаг 11.25°), сетка 8×4 с шагом 1 тайл
RING32_FRAME = K.Frame(-4.0, 2.25, 8.0, 4.5, K.PX_RENDER)
RING32 = [((-3.5 + (i % 8), 1.5 - (i // 8)), 2 * math.pi * i / 32) for i in range(32)]
# для замера: те же 32 курса с шагом 2 тайла, чтобы соседи не попадали в рамку
RINGM_FRAME = K.Frame(-8.0, 4.0, 16.0, 8.0, K.PX_RENDER)
RINGM = [((-7 + 2 * (i % 8), 3 - 2 * (i // 8)), 2 * math.pi * i / 32) for i in range(32)]
# одна каретка на тайле, курс E-W — для сравнения со скетчем и крупного плана
SINGLE_FRAME = K.Frame(-0.75, 1.0, 1.5, 1.5, K.PX_RENDER)

LIGHT_DIR = (-0.5, 0.83, 0.26)   # в осях камеры: свет с северо-запада, тень вправо-вниз


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opt = dict(only=None, views=["field", "ring32", "ringm", "single", "ortho", "hero"])
    for i in range(0, len(a) - 1, 2):
        if a[i] == "--only":
            opt["only"] = a[i + 1].split(",")
        elif a[i] == "--views":
            opt["views"] = a[i + 1].split(",")
    return opt


def setup_workbench():
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sh = sc.display.shading
    sh.light = 'STUDIO'
    sh.studio_light = 'Default'
    sh.color_type = 'MATERIAL'
    sh.show_shadows = True
    sh.shadow_intensity = 0.55
    sh.show_cavity = True
    sh.cavity_type = 'BOTH'
    sh.cavity_ridge_factor = 1.0
    sh.cavity_valley_factor = 1.0
    sh.curvature_ridge_factor = 1.0
    sh.curvature_valley_factor = 1.0
    sh.show_specular_highlight = True
    sc.display.light_direction = LIGHT_DIR
    sc.display.shadow_shift = 0.05
    sc.display.shadow_focus = 0.2
    sc.display.render_aa = '16'
    r = sc.render
    r.film_transparent = True
    r.resolution_percentage = 100
    r.image_settings.file_format = 'PNG'
    r.image_settings.color_mode = 'RGBA'
    r.image_settings.color_depth = '8'
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'


def cart_coll(key):
    return bpy.data.collections["CART_%s" % key]


def clear_view():
    v = bpy.data.collections.get("VIEW") or K.collection("VIEW")
    for o in list(v.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for me in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(me)
    return v


def instance(v, coll, name, x, y, heading, parent):
    o = bpy.data.objects.new(name, None)
    o.instance_type = 'COLLECTION'
    o.instance_collection = coll
    v.objects.link(o)
    o.parent = parent
    o.location = (x, y, 0)
    o.rotation_euler = (0, 0, heading)
    return o


def white_plane(v, parent):
    m = bpy.data.materials.get("sh_white") or bpy.data.materials.new("sh_white")
    m.diffuse_color = (1, 1, 1, 1)
    me = bpy.data.meshes.new("sh_plane")
    me.from_pydata([(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)], [], [(0, 1, 2, 3)])
    me.materials.append(m)
    pl = bpy.data.objects.new("sh_plane", me)
    v.objects.link(pl)
    pl.parent = parent
    return pl


def render_game(key, frame, poses, path):
    v = clear_view()
    world = K.empty("WORLD", v, scale=(1, K.STRETCH, 1))
    for i, (x, y, h) in enumerate(poses):
        instance(v, cart_coll(key), "c%d" % i, x, y, h, world)
    K.game_camera("cam", v, frame)
    K.render_to(path)
    pl = white_plane(v, world)                    # проход тени: белая плоскость на уровне ложа
    K.render_to(path.replace(".png", "_sh.png"))
    bpy.data.objects.remove(pl, do_unlink=True)
    print("rendered", path)


def ref_mats():
    return dict(base=bpy.data.materials["v7c_ref_base"], bed=bpy.data.materials["v7c_ref_bed"],
                blade=bpy.data.materials["v7c_ref_blade"])


def render_free(key, ref_tiles, poses, rot_deg, target, ortho_w, res, path):
    v = clear_view()
    if ref_tiles:
        K.rail_ref(v, ref_tiles, ref_mats())
    for i, (x, y, h) in enumerate(poses):
        instance(v, cart_coll(key), "c%d" % i, x, y, h, None)
    K.free_camera("cam", v, target, rot_deg, ortho_w, res)
    K.render_to(path)
    print("rendered", path)


def main():
    opt = args()
    os.makedirs(OUT, exist_ok=True)
    setup_workbench()
    field_poses = []
    for route, n, first in ROUTES:
        field_poses += K.train_poses(route, n, first)
    frames = dict(
        field=dict(frame=FIELD_FRAME.to_dict(), tiles=FIELD_TILES, poses=field_poses),
        ring32=dict(frame=RING32_FRAME.to_dict(), tiles=[p for p, _ in RING32],
                    poses=[(x, y, h) for (x, y), h in RING32]),
        ringm=dict(frame=RINGM_FRAME.to_dict(), tiles=[p for p, _ in RINGM],
                   poses=[(x, y, h) for (x, y), h in RINGM]),
        single=dict(frame=SINGLE_FRAME.to_dict(), tiles=[(0, 0)], poses=[(0, 0, EAST)]),
    )
    with open(os.path.join(OUT, "frames.json"), "w", encoding="utf-8") as f:
        json.dump(frames, f, indent=1)

    row = [((x, 0), ["E-W"]) for x in (-1, 0, 1)]
    for key, title, P in VARIANTS:
        if opt["only"] and key not in opt["only"]:
            continue
        for view in opt["views"]:
            p = lambda n: os.path.join(OUT, "%s_%s.png" % (key, n))  # noqa: E731
            if view in frames:
                render_game(key, K.Frame.from_dict(frames[view]["frame"]), frames[view]["poses"], p(view))
            elif view == "ortho":
                # как у автора в C4D: ход вдоль X; Top, Front (сбоку, колесо кругом), Right (с торца, развал V)
                one = [(0, 0, EAST)]
                render_free(key, [((0, 0), ["E-W", "N-S"])], one, (0, 0, 0), (0, 0, 0.3), 1.25, (500, 500), p("top"))
                render_free(key, row, one, (90, 0, 0), (0, 0, 0.25), 1.25, (500, 500), p("front"))
                render_free(key, [((0, 0), ["N-S"])], one, (90, 0, 90), (0, 0, 0.25), 1.25, (500, 500), p("right"))
                render_free(key, [((0, 0), ["N-S"])], one, (90, 0, 90), (0, 0, 0.28), 1.0, (900, 900), p("section"))
                render_free(key, row, one, (62, 0, 38), (0, 0, 0.22), 1.45, (500, 500), p("persp"))
            elif view == "hero":
                tiles = [((-1, 0), ["E-W"]), ((0, 0), ["E-W", "N-S"]), ((1, 0), ["E-W", "S-W"]),
                         ((1, -1), ["N-S"]), ((0, 1), ["N-S"]), ((-2, 0), ["E-W"])]
                poses = [(-1, 0, EAST), (0, 0, EAST), K.tile_point((1, 0), "W", "S", 0.5), (0, 1, 0)]
                render_free(key, tiles, poses, (58, 0, 32), (0.15, 0.25, 0.2), 2.7, (1000, 800), p("hero"))


main()
