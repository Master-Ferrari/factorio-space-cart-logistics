# -*- coding: utf-8 -*-
"""Рендеры блокинга v5a (Workbench): игровой ракурс (поле с поездами, 32 курса, одиночная
каретка для сравнения со скетчем) и свободные виды на болванке рельса (Top/Front/Right/
Parallel как в окнах C4D автора, плюс перспектива 3/4).

Запуск (без --factory-startup — с ним рендер в фоне виснет):
  blender -b cart_v5a.blend --python render_v5a.py -- [--only A,B] [--views field,ring32,solo,ortho,hero]

Пишет v5a/out/render/<K>_<view>.png (+ _sh.png — проход тени на белой плоскости) и frames.json.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import scl3d as K  # noqa: E402
from params import VARIANTS  # noqa: E402

OUT = os.path.join(HERE, "out", "render")
D90 = math.radians(90)
EAST, NORTH = -D90, 0.0

# ── поле: E-W, N-S и поворот ───────────────────────────────────────
FIELD_FRAME = K.Frame(-3.75, 3.35, 7.5, 6.1, K.PX_RENDER)
FIELD_TILES = [(x, y) for y in range(-2, 3) for x in range(-3, 4)]
ROUTES = [
    # поезд на восток по верхнему ряду: профиль «одно колесо делает составы»
    ([((x, 2), "W", "E") for x in range(-3, 4)], 5, 48),
    # колонна на север
    ([((-3, y), "S", "N") for y in range(-2, 2)], 3, 16),
    # восток → поворот на север → поворот на восток (соседи на дугах теснее)
    ([((-1, -2), "W", "E"), ((0, -2), "W", "E"), ((1, -2), "W", "N"), ((1, -1), "S", "N"),
      ((1, 0), "S", "E"), ((2, 0), "W", "E"), ((3, 0), "W", "E")], 5, 16),
]
# все 32 курса листа (шаг 11.25°), сетка 8×4; шаг 1.25×1.5 тайла, чтобы силуэты не слипались при замере
RING32_FRAME = K.Frame(-5.0, 3.25, 10.0, 6.0, K.PX_RENDER)
RING32 = [((-4.375 + 1.25 * (i % 8), 2.25 - 1.5 * (i // 8)), 2 * math.pi * i / 32) for i in range(32)]
SOLO_FRAME = K.Frame(-0.8, 1.25, 1.6, 2.0, K.PX_RENDER)       # одна каретка на восток, как скетч

LIGHT_DIR = (-0.5, 0.83, 0.26)      # в осях камеры: свет с северо-запада, тень вправо-вниз


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opt = dict(only=None, views=["field", "ring32", "solo", "ortho", "hero"])
    if "--only" in a:
        opt["only"] = a[a.index("--only") + 1].split(",")
    if "--views" in a:
        opt["views"] = a[a.index("--views") + 1].split(",")
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


def clear_view():
    v = bpy.data.collections.get("VIEW") or K.collection("VIEW")
    for o in list(v.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(m)
    return v


def instance(v, key, name, x, y, heading, parent):
    o = bpy.data.objects.new(name, None)
    o.instance_type = 'COLLECTION'
    o.instance_collection = bpy.data.collections["CART_%s" % key]
    v.objects.link(o)
    o.parent = parent
    o.location = (x, y, 0)
    o.rotation_euler = (0, 0, heading)
    return o


def white_plane(v, parent):
    m = bpy.data.materials.get("sh_white") or bpy.data.materials.new("sh_white")
    m.diffuse_color = (1, 1, 1, 1)
    me = bpy.data.meshes.new("shplane")
    s = 20
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    pl = bpy.data.objects.new("shplane", me)
    v.objects.link(pl)
    pl.parent = parent
    me.materials.append(m)
    return pl


def render_game(key, frame, poses, path):
    v = clear_view()
    world = K.empty("WORLD", v, scale=(1, K.STRETCH, 1))
    for i, (x, y, h) in enumerate(poses):
        instance(v, key, "c%d" % i, x, y, h, world)
    K.game_camera("cam", v, frame)
    K.render_to(path)
    pl = white_plane(v, world)                          # проход тени
    K.render_to(path.replace(".png", "_sh.png"))
    bpy.data.objects.remove(pl, do_unlink=True)
    print("rendered", path)


def rail_mats():
    return dict(base=bpy.data.materials["rr_base"], bed=bpy.data.materials["rr_bed"],
                blade=bpy.data.materials["rr_blade"])


REF_TILES = [((-1, 0), ["E-W"]), ((0, 0), ["E-W", "N-S"]), ((1, 0), ["E-W"]),
             ((0, 1), ["N-S"]), ((0, -1), ["N-S"])]


def render_free(key, rot_deg, target, ortho_w, res, path, persp=None, poses=None):
    v = clear_view()
    K.rail_ref(v, REF_TILES, rail_mats())
    for i, (x, y, h) in enumerate(poses or [(0, 0, EAST)]):
        instance(v, key, "c%d" % i, x, y, h, None)
    cam = K.free_camera("cam", v, target, rot_deg, ortho_w, res, dist=12.0)
    if persp:
        cam.data.type = 'PERSP'
        cam.data.lens = persp
        cam.location = Vector(target) + (cam.location - Vector(target)).normalized() * 4.2
    K.render_to(path)
    print("rendered", path)


def main():
    opt = args()
    os.makedirs(OUT, exist_ok=True)
    setup_workbench()
    field = []
    for route, n, first in ROUTES:
        field += K.train_poses(route, n, first)
    frames = dict(
        field=dict(frame=FIELD_FRAME.to_dict(), tiles=FIELD_TILES, carts=[(x, y) for x, y, _ in field]),
        ring32=dict(frame=RING32_FRAME.to_dict(), tiles=[p for p, _ in RING32],
                    carts=[p for p, _ in RING32], headings=[math.degrees(h) for _, h in RING32]),
        solo=dict(frame=SOLO_FRAME.to_dict(), tiles=[(0, 0)], carts=[(0, 0)], headings=[-90]),
    )
    with open(os.path.join(OUT, "frames.json"), "w", encoding="utf-8") as f:
        json.dump(frames, f, indent=1)

    for key in VARIANTS:
        if opt["only"] and key not in opt["only"]:
            continue
        P = lambda view: os.path.join(OUT, "%s_%s.png" % (key, view))  # noqa: E731
        if "field" in opt["views"]:
            render_game(key, FIELD_FRAME, field, P("field"))
        if "ring32" in opt["views"]:
            render_game(key, RING32_FRAME, [(x, y, h) for (x, y), h in RING32], P("ring32"))
        if "solo" in opt["views"]:
            render_game(key, SOLO_FRAME, [(0, 0, EAST)], P("solo"))
        if "ortho" in opt["views"]:
            tgt = (0, 0, 0.3)
            # как окна C4D автора; каретка идёт на восток (ход по X, как у него)
            render_free(key, (0, 0, 0), (0, 0, 0.3), 1.5, (600, 600), P("top"))
            render_free(key, (90, 0, 0), tgt, 1.5, (600, 600), P("front"))      # смотрим на север: колесо плашмя
            render_free(key, (90, 0, 90), tgt, 1.5, (600, 600), P("right"))     # с востока: V колёс
            render_free(key, (45, 0, 0), (0, 0, 0.25), 1.5, (600, 600), P("parallel"))  # игровая камера без растяжки
        if "hero" in opt["views"]:
            render_free(key, (62, 0, 38), (0.0, 0.0, 0.25), 2.0, (900, 700), P("hero"), persp=50,
                        poses=[(0, 0, EAST), (-1.0, 0, EAST)])


main()
