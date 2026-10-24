# -*- coding: utf-8 -*-
"""Рендеры блокинга каретки: игровой ракурс (поле, кольцо курсов), вид сбоку, 3/4.

Запуск (из этой папки):
  blender -b cart_blocking.blend --python render_blocking.py -- [--only A,C] [--views field,ring,side,hero]
        [--engine wb|cycles] [--samples 16]

Пишет в blocking/render/: <K>_<view>.png и frames.json (кадры игровых видов для
compose_blocking.py — он подкладывает спрайты тайлов и собирает листы).

Движок по умолчанию — Workbench (раунд 3): плоские цвета материалов, студийный свет,
cavity, тени. Секунда на кадр даже при занятом GPU. Shadow catcher у Workbench нет,
поэтому для игровых видов есть второй проход <K>_<view>_sh.png — те же каретки на белой
плоскости z = 0; compose вычитает из него тень и кладёт её на подложку тайлов.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import scl3d as K  # noqa: E402
from build_blocking import mats  # noqa: E402
from concepts import CURRENT  # noqa: E402

OUT = os.path.join(HERE, "blocking", "render")
D90 = math.radians(90)

# ── поле: маршруты в игровых координатах (тайлы, +Y — север) ───────
FIELD_FRAME = K.Frame(-3.75, 3.25, 7.5, 6.0, K.PX_RENDER)
FIELD_TILES = [(x, y) for y in range(-2, 3) for x in range(-3, 4)]
ROUTES = [
    # колонна на север
    ([((-2, y), "S", "N") for y in range(-2, 3)], 3, 48),
    # восток → поворот на север → поворот на восток
    ([((0, -1), "W", "E"), ((1, -1), "W", "E"), ((2, -1), "W", "N"), ((2, 0), "S", "N"),
      ((2, 1), "S", "E"), ((3, 1), "W", "E")], 5, 16),
    # ряд на запад (профиль сбоку)
    ([((1, 2), "E", "W"), ((0, 2), "E", "W"), ((-1, 2), "E", "W")], 3, 16),
]

RING_FRAME = K.Frame(-4.0, 2.25, 8.0, 4.5, K.PX_RENDER)
RING = [((-3 + 2 * (i % 4), 1 if i < 4 else -1), math.radians(45 * i)) for i in range(8)]
# все 32 курса листа спрайта (шаг 11.25°), сетка 8×4 с шагом 1 тайл
RING32_FRAME = K.Frame(-4.0, 2.25, 8.0, 4.5, K.PX_RENDER)
RING32 = [((-3.5 + (i % 8), 1.5 - (i // 8)), 2 * math.pi * i / 32) for i in range(32)]


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opt = dict(only=None, views=["field", "ring", "ring32", "side", "hero"], samples=48, engine="wb")
    i = 0
    while i < len(a):
        if a[i] == "--only":
            opt["only"] = a[i + 1].split(","); i += 2
        elif a[i] == "--views":
            opt["views"] = a[i + 1].split(","); i += 2
        elif a[i] == "--samples":
            opt["samples"] = int(a[i + 1]); i += 2
        elif a[i] == "--engine":
            opt["engine"] = a[i + 1]; i += 2
        else:
            i += 1
    return opt


def cart_coll(key):
    return next(c for c in bpy.data.collections if c.name.startswith("CART_%s_" % key))


def clear_view():
    v = bpy.data.collections.get("VIEW")
    if v:
        for o in list(v.objects):
            bpy.data.objects.remove(o, do_unlink=True)
    else:
        v = K.collection("VIEW")
    for n in [m.name for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(bpy.data.meshes[n])
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


# Свет для теней Workbench. ВНИМАНИЕ: scene.display.light_direction задан в осях КАМЕРЫ
# (x вправо, y вверх по экрану, z на зрителя), а не мира. (-0.5, 0.83, 0.26) при игровой
# камере = мировой свет с северо-запада под ~50°: тень ложится вправо-вниз, как в игре.
LIGHT_DIR = (-0.5, 0.83, 0.26)
WB = {"on": True}


def shadow_plane(v, parent):
    m = bpy.data.materials.get("sh_white") or bpy.data.materials.new("sh_white")
    m.diffuse_color = (1, 1, 1, 1)
    bpy.ops.mesh.primitive_plane_add(size=20)
    pl = bpy.context.active_object
    for c in pl.users_collection:
        c.objects.unlink(pl)
    v.objects.link(pl)
    pl.parent = parent
    pl.data.materials.append(m)
    return pl


def lights(v):
    K.setup_world(0.55)
    K.sun("sun", v)


def view_game(key, frame, poses, catcher):
    v = clear_view()
    world = K.empty("WORLD", v, scale=(1, K.STRETCH, 1))
    for i, (x, y, h) in enumerate(poses):
        instance(v, cart_coll(key), "c%d" % i, x, y, h, world)
    if catcher and not WB["on"]:
        bpy.ops.mesh.primitive_plane_add(size=20)
        pl = bpy.context.active_object
        for c in pl.users_collection:
            c.objects.unlink(pl)
        v.objects.link(pl)
        pl.parent = world
        pl.is_shadow_catcher = True
    lights(v)
    K.game_camera("cam", v, frame)
    return v, world


def render_game(key, frame, poses, catcher, path):
    v, world = view_game(key, frame, poses, catcher)
    K.render_to(path)
    if WB["on"]:                                   # проход тени: белая плоскость на уровне ложа
        pl = shadow_plane(v, world)
        K.render_to(path.replace(".png", "_sh.png"))
        bpy.data.objects.remove(pl, do_unlink=True)


def view_free(key, ref_tiles, poses, rot_deg, target, ortho_w, res):
    v = clear_view()
    M = mats()
    K.rail_ref(v, ref_tiles, M)
    for i, (x, y, h) in enumerate(poses):
        instance(v, cart_coll(key), "c%d" % i, x, y, h, None)
    lights(v)
    K.free_camera("cam", v, target, rot_deg, ortho_w, res)


def main():
    opt = args()
    os.makedirs(OUT, exist_ok=True)
    WB["on"] = opt["engine"] == "wb"
    if WB["on"]:
        setup_workbench()
    else:
        K.setup_cycles(samples=opt["samples"])
    for c in list(bpy.data.collections):
        if c.name == "PREVIEW":
            for lc in bpy.context.view_layer.layer_collection.children:
                if lc.collection == c:
                    lc.exclude = True
    field_poses = []
    for route, n, first in ROUTES:
        field_poses += K.train_poses(route, n, first)
    frames = dict(
        field=dict(frame=FIELD_FRAME.to_dict(), tiles=FIELD_TILES,
                   carts=[(x, y) for x, y, _ in field_poses]),
        ring=dict(frame=RING_FRAME.to_dict(), tiles=[p for p, _ in RING],
                  carts=[p for p, _ in RING], headings=[math.degrees(h) for _, h in RING]),
        ring32=dict(frame=RING32_FRAME.to_dict(), tiles=[p for p, _ in RING32],
                    carts=[p for p, _ in RING32], headings=[math.degrees(h) for _, h in RING32]),
    )
    with open(os.path.join(OUT, "frames.json"), "w", encoding="utf-8") as f:
        json.dump(frames, f, indent=1)

    for key, name, _ in CURRENT:
        if opt["only"] and key not in opt["only"]:
            continue
        for view in opt["views"]:
            path = os.path.join(OUT, "%s_%s.png" % (key, view))
            if view == "field":
                render_game(key, FIELD_FRAME, field_poses, True, path)
                print("rendered", path)
                continue
            elif view == "ring":
                render_game(key, RING_FRAME, [(x, y, h) for (x, y), h in RING], False, path)
                print("rendered", path)
                continue
            elif view == "ring32":
                render_game(key, RING32_FRAME, [(x, y, h) for (x, y), h in RING32], False, path)
                print("rendered", path)
                continue
            elif view == "side":
                view_free(key, [((x, 0), ["E-W"]) for x in (-1, 0, 1, 2)],
                          [(0, 0, -D90), (1, 0, -D90)], (90, 0, 0), (0.5, 0, 0.15),
                          2.4, (614, 282))
            elif view == "hero":
                view_free(key, [((-1, 0), ["E-W"]), ((0, 0), ["E-W", "N-S"]), ((1, 0), ["E-W", "S-W"]),
                                ((1, -1), ["N-S"]), ((0, 1), ["N-S"])],
                          [(0, 0, -D90), K.tile_point((1, 0), "W", "S", 0.5), (0, 1, 0)],
                          (58, 0, 32), (0.4, 0.0, 0.1), 3.0, (900, 720))
            else:
                continue
            K.render_to(path)
            print("rendered", path)


main()
