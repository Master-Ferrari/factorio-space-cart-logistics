# -*- coding: utf-8 -*-
"""Рендеры интерпретаций концепта автора (Workbench): игровой ракурс, сбоку, 3/4, виды «как на скетче».

Запуск (из этой папки, БЕЗ --factory-startup):
  blender -b author_blocking.blend --python render_author.py -- [--only K1,K2] [--views field,ring,...]

Пишет в out/render/: <K>_<view>.png (+ <K>_<view>_sh.png — проход тени на белой плоскости для
игровых видов) и frames.json. Логика полей/колец/тени скопирована из cart/render_blocking.py.
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
from build_author import mats  # noqa: E402
from author_concepts import KEYS  # noqa: E402

OUT = os.path.join(HERE, "out", "render")
D90 = math.radians(90)

# ── поле: маршруты в игровых координатах (как в раунде 3) ──────────
FIELD_FRAME = K.Frame(-3.75, 3.25, 7.5, 6.0, K.PX_RENDER)
FIELD_TILES = [(x, y) for y in range(-2, 3) for x in range(-3, 4)]
ROUTES = [
    ([((-2, y), "S", "N") for y in range(-2, 3)], 3, 48),                         # колонна на север
    ([((0, -1), "W", "E"), ((1, -1), "W", "E"), ((2, -1), "W", "N"), ((2, 0), "S", "N"),
      ((2, 1), "S", "E"), ((3, 1), "W", "E")], 5, 16),                            # змейка с поворотами
    ([((1, 2), "E", "W"), ((0, 2), "E", "W"), ((-1, 2), "E", "W")], 3, 16),       # ряд на запад (профиль)
]
RING_FRAME = K.Frame(-4.0, 2.25, 8.0, 4.5, K.PX_RENDER)
RING = [((-3 + 2 * (i % 4), 1 if i < 4 else -1), math.radians(45 * i)) for i in range(8)]
RING32_FRAME = K.Frame(-4.0, 2.25, 8.0, 4.5, K.PX_RENDER)
RING32 = [((-3.5 + (i % 8), 1.5 - (i // 8)), 2 * math.pi * i / 32) for i in range(32)]
# те же 32 курса через 2 тайла — только для замера силуэта (соседи не слипаются)
RING32M_FRAME = K.Frame(-8.0, 4.25, 16.0, 8.5, K.PX_RENDER)
RING32M = [((-7 + 2 * (i % 8), 3 - 2 * (i // 8)), 2 * math.pi * i / 32) for i in range(32)]

# Виды «как на скетче»: (rot_deg камеры, курс каретки, ширина кадра). Подобраны по рисункам:
MATCH = {
    "m_front": ((62, 0, 0), 0.0, 1.0),        # ряд 2 слева: спереди-сверху, видны оба колеса V
    "m_side": ((84, 0, 90), 0.0, 1.0),        # ряд 3 справа: почти сбоку, колесо — эллипс под корпусом
    "m_end": ((80, 0, 0), 0.0, 1.0),          # ряд 3 слева: с торца, чуть сверху
    "m_34": ((72, 0, 70), 0.0, 1.05),          # низ слева: почти сбоку, чуть спереди и сверху
}


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opt = dict(only=None, views=["field", "ring", "ring32", "ring32m", "side", "hero"] + list(MATCH))
    i = 0
    while i < len(a):
        if a[i] == "--only":
            opt["only"] = a[i + 1].split(","); i += 2
        elif a[i] == "--views":
            opt["views"] = a[i + 1].split(","); i += 2
        else:
            i += 1
    return opt


def cart_coll(key):
    return bpy.data.collections["AUTH_%s" % key]


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


# Свет Workbench: scene.display.light_direction — в осях КАМЕРЫ. (-0.5, 0.83, 0.26) при игровой
# камере = свет с северо-запада, тень вправо-вниз, как в игре (проверено в раунде 3).
LIGHT_DIR = (-0.5, 0.83, 0.26)


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


def render_game(key, frame, poses, path, shadow=True):
    v = clear_view()
    world = K.empty("WORLD", v, scale=(1, K.STRETCH, 1))
    for i, (x, y, h) in enumerate(poses):
        instance(v, cart_coll(key), "c%d" % i, x, y, h, world)
    K.game_camera("cam", v, frame)
    K.render_to(path)
    if not shadow:
        return
    pl = shadow_plane(v, world)                    # проход тени: белая плоскость на уровне ложа
    K.render_to(path.replace(".png", "_sh.png"))
    bpy.data.objects.remove(pl, do_unlink=True)


def render_free(key, ref_tiles, poses, rot_deg, target, ortho_w, res, path):
    v = clear_view()
    K.rail_ref(v, ref_tiles, mats())
    for i, (x, y, h) in enumerate(poses):
        instance(v, cart_coll(key), "c%d" % i, x, y, h, None)
    K.free_camera("cam", v, target, rot_deg, ortho_w, res)
    K.render_to(path)


def main():
    opt = args()
    os.makedirs(OUT, exist_ok=True)
    setup_workbench()
    field_poses = []
    for route, n, first in ROUTES:
        field_poses += K.train_poses(route, n, first)
    frames = dict(
        field=dict(frame=FIELD_FRAME.to_dict(), tiles=FIELD_TILES, carts=[(x, y) for x, y, _ in field_poses]),
        ring=dict(frame=RING_FRAME.to_dict(), tiles=[p for p, _ in RING], carts=[p for p, _ in RING],
                  headings=[math.degrees(h) for _, h in RING]),
        ring32=dict(frame=RING32_FRAME.to_dict(), tiles=[p for p, _ in RING32], carts=[p for p, _ in RING32],
                    headings=[math.degrees(h) for _, h in RING32]),
        ring32m=dict(frame=RING32M_FRAME.to_dict(), tiles=[p for p, _ in RING32M], carts=[p for p, _ in RING32M],
                     headings=[math.degrees(h) for _, h in RING32M]),
        match={k: dict(rot=v[0], heading=v[1], w=v[2]) for k, v in MATCH.items()},
    )
    with open(os.path.join(OUT, "frames.json"), "w", encoding="utf-8") as f:
        json.dump(frames, f, indent=1)

    for key in KEYS:
        if opt["only"] and key not in opt["only"]:
            continue
        for view in opt["views"]:
            path = os.path.join(OUT, "%s_%s.png" % (key, view))
            if view == "field":
                render_game(key, FIELD_FRAME, field_poses, path)
            elif view == "ring":
                render_game(key, RING_FRAME, [(x, y, h) for (x, y), h in RING], path)
            elif view == "ring32":
                render_game(key, RING32_FRAME, [(x, y, h) for (x, y), h in RING32], path)
            elif view == "ring32m":
                render_game(key, RING32M_FRAME, [(x, y, h) for (x, y), h in RING32M], path, shadow=False)
            elif view == "side":                    # поезд сбоку: три каретки бампер-в-бампер
                render_free(key, [((x, 0), ["E-W"]) for x in (-2, -1, 0, 1, 2)],
                            [(-1, 0, -D90), (0, 0, -D90), (1, 0, -D90)], (90, 0, 0), (0, 0, 0.2),
                            3.2, (1024, 330), path)
            elif view == "hero":
                render_free(key, [((-1, 0), ["E-W"]), ((0, 0), ["E-W", "N-S"]), ((1, 0), ["E-W", "S-W"]),
                                  ((1, -1), ["N-S"]), ((0, 1), ["N-S"])],
                            [(0, 0, -D90), K.tile_point((1, 0), "W", "S", 0.5), (0, 1, 0), (-1, 0, -D90)],
                            (58, 0, 32), (0.4, 0.0, 0.1), 3.0, (900, 720), path)
            elif view in MATCH:
                rot, hd, w = MATCH[view]
                render_free(key, [((0, 0), ["N-S"]), ((0, 1), ["N-S"]), ((0, -1), ["N-S"])],
                            [(0, 0, hd)], rot, (0, 0, 0.18), w, (640, 640), path)
            else:
                continue
            print("rendered", path)


main()
