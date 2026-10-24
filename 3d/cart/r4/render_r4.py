# -*- coding: utf-8 -*-
"""Раунд 4: рендеры Workbench в out/render/.

  blender -b r4.blend --python render_r4.py -- [--only P,X1] [--views ring8,ring32,field,side,hero,section]

Игровые виды (ring8, ring32, field) — с растяжкой WORLD √2, без тайла; тайлы подкладывает
compose_r4.py по якорю земли. Для каждого игрового вида есть второй проход *_sh.png
(те же каретки на белой плоскости z = 0) — из него compose берёт тень.
Свободные виды (side, hero, section) — без растяжки, на болванке рельса.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import bmesh  # noqa: E402
import bpy  # noqa: E402
import scl3d as K  # noqa: E402
from build_r4 import mats  # noqa: E402
from keys import KEYS, MAIN  # noqa: E402

OUT = os.path.join(HERE, "out", "render")
D90 = math.radians(90)
LIGHT_DIR = (-0.5, 0.83, 0.26)          # в осях камеры: свет с северо-запада, тень вправо-вниз

RING8_FRAME = K.Frame(-4.0, 2.25, 8.0, 4.5, K.PX_RENDER)
RING8 = [((-3 + 2 * (i % 4), 1 if i < 4 else -1), math.radians(45 * i)) for i in range(8)]
RING32_FRAME = K.Frame(-4.0, 2.25, 8.0, 4.5, K.PX_RENDER)
RING32 = [((-3.5 + (i % 8), 1.5 - (i // 8)), 2 * math.pi * i / 32) for i in range(32)]
# те же 32 курса через 2 тайла — только для замеров (соседи не попадают в окно силуэта)
RING32W_FRAME = K.Frame(-8.0, 4.5, 16.0, 9.0, K.PX_RENDER)
RING32W = [((-7 + 2 * (i % 8), 3 - 2 * (i // 8)), 2 * math.pi * i / 32) for i in range(32)]

FIELD_FRAME = K.Frame(-3.75, 3.25, 7.5, 6.0, K.PX_RENDER)
FIELD_TILES = [(x, y) for y in range(-2, 3) for x in range(-3, 4)]
ROUTES = [
    ([((-2, y), "S", "N") for y in range(-2, 3)], 3, 48),                       # колонна на север
    ([((0, -1), "W", "E"), ((1, -1), "W", "E"), ((2, -1), "W", "N"), ((2, 0), "S", "N"),
      ((2, 1), "S", "E"), ((3, 1), "W", "E")], 5, 16),                            # восток → север → восток
    ([((1, 2), "E", "W"), ((0, 2), "E", "W"), ((-1, 2), "E", "W")], 3, 16),     # ряд на запад
]


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opt = dict(only=None, views=["ring8", "ring32", "ring32w", "field", "side", "hero", "closeup", "section"])
    i = 0
    while i < len(a):
        if a[i] == "--only":
            opt["only"] = a[i + 1].split(","); i += 2
        elif a[i] == "--views":
            opt["views"] = a[i + 1].split(","); i += 2
        else:
            i += 1
    return opt


def coll(key):
    return bpy.data.collections["CART_%s" % key]


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


def instance(v, c, name, x, y, heading, parent):
    o = bpy.data.objects.new(name, None)
    o.instance_type = 'COLLECTION'
    o.instance_collection = c
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
    sc.display.shadow_shift = 0.25
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


def white_plane(v, parent):
    m = bpy.data.materials.get("sh_white") or bpy.data.materials.new("sh_white")
    m.diffuse_color = (1, 1, 1, 1)
    me = bpy.data.meshes.new("shplane")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=12)
    bm.to_mesh(me)
    bm.free()
    pl = bpy.data.objects.new("shplane", me)
    v.objects.link(pl)
    pl.parent = parent
    me.materials.append(m)
    return pl


def render_game(key, frame, poses, path):
    v = clear_view()
    world = K.empty("WORLD", v, scale=(1, K.STRETCH, 1))
    for i, (x, y, h) in enumerate(poses):
        instance(v, coll(key), "c%d" % i, x, y, h, world)
    K.game_camera("cam", v, frame)
    K.render_to(path)
    pl = white_plane(v, world)
    K.render_to(path.replace(".png", "_sh.png"))
    bpy.data.objects.remove(pl, do_unlink=True)
    print("rendered", path)


def view_free(key, ref_tiles, poses, rot_deg, target, ortho_w, res, path):
    v = clear_view()
    M = mats()
    K.rail_ref(v, ref_tiles, M)
    for i, (x, y, h) in enumerate(poses):
        instance(v, coll(key), "c%d" % i, x, y, h, None)
    K.free_camera("cam", v, target, rot_deg, ortho_w, res)
    K.render_to(path)
    print("rendered", path)


CUT = {"r4_dark": (0.16, 0.17, 0.19), "r4_light": (0.95, 0.42, 0.10), "r4_mid": (0.95, 0.42, 0.10),
       "r4_beige": (0.72, 0.60, 0.45), "r4_brass": (0.55, 0.40, 0.16), "ref_bed": (0.62, 0.55, 0.46),
       "ref_blade": (0.45, 0.55, 0.68), "ref_base": (0.10, 0.10, 0.11)}


def cut_mat_for(o):
    m0 = o.data.materials[0] if o.data.materials and o.data.materials[0] else None
    col = CUT.get(m0.name if m0 else "", (0.85, 0.30, 0.08))
    return K.material("cut_%s" % (m0.name if m0 else "x"), col, rough=0.8)


def realize_cut(v, src_objs, cut_mat, name):
    """Реальные копии объектов (с модификаторами), срезанные плоскостью y = 0: остаётся y ≥ 0.
    Грани среза получают материал cut_mat."""
    dg = bpy.context.evaluated_depsgraph_get()
    for o in src_objs:
        if o.type != 'MESH':
            continue
        cut_mat = cut_mat_for(o)
        ev = o.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev)
        me.transform(o.matrix_world)
        bm = bmesh.new()
        bm.from_mesh(me)
        geom_all = bm.verts[:] + bm.edges[:] + bm.faces[:]
        res = bmesh.ops.bisect_plane(bm, geom=geom_all, plane_co=(0, 0, 0), plane_no=(0, -1, 0),
                                     clear_outer=True, dist=1e-6)
        edges = [e for e in bm.edges if e.is_boundary]
        new = []
        if edges:
            r = bmesh.ops.holes_fill(bm, edges=edges, sides=0)
            new = r["faces"]
        if not bm.faces:
            bm.free()
            continue
        names = [m.name if m else "" for m in me.materials]
        if cut_mat.name not in names:
            me.materials.append(cut_mat)
            names.append(cut_mat.name)
        ci = names.index(cut_mat.name)
        for f in new:
            f.material_index = ci
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name + o.name, me)
        v.objects.link(ob)


def view_section(key, path):
    """Разрез поперёк рельса по оси колёс (y = 0), вид с юга."""
    v = clear_view()
    M = mats()
    tmp = K.collection("TMP_SECTION")
    K.rail_ref(tmp, [((0, 0), ["N-S"])], M)
    cutm = K.material("r4_cut", (0.85, 0.30, 0.08), rough=0.6)
    realize_cut(v, list(tmp.objects), cutm, "sec_rail_")
    # каретка: реальные объекты коллекции (инстанс не режется); коллекцию временно включаем
    lc = next(l for l in bpy.context.view_layer.layer_collection.children if l.collection == coll(key))
    lc.exclude = False
    bpy.context.view_layer.update()
    realize_cut(v, [o for o in coll(key).all_objects], cutm, "sec_cart_")
    lc.exclude = True
    for o in list(tmp.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(tmp)
    res = (1200, 640)
    W = 1.0
    tgt = (0.0, 0.0, 0.17)
    K.free_camera("cam", v, tgt, (90, 0, 0), W, res)
    K.render_to(path)
    print("rendered", path)
    return dict(target=tgt, ortho_w=W, res=res)


def main():
    opt = args()
    os.makedirs(OUT, exist_ok=True)
    setup_workbench()
    K.setup_world(0.55)
    field_poses = []
    for route, n, first in ROUTES:
        field_poses += K.train_poses(route, n, first)
    fpath = os.path.join(OUT, "frames.json")
    frames = json.load(open(fpath, encoding="utf-8")) if os.path.exists(fpath) else {}
    frames.update(
        field=dict(frame=FIELD_FRAME.to_dict(), tiles=FIELD_TILES, carts=[(x, y) for x, y, _ in field_poses],
                   headings=[math.degrees(h) for _, _, h in field_poses]),
        ring8=dict(frame=RING8_FRAME.to_dict(), tiles=[p for p, _ in RING8],
                   carts=[p for p, _ in RING8], headings=[math.degrees(h) for _, h in RING8]),
        ring32w=dict(frame=RING32W_FRAME.to_dict(), tiles=[p for p, _ in RING32W],
                     carts=[p for p, _ in RING32W], headings=[math.degrees(h) for _, h in RING32W]),
        ring32=dict(frame=RING32_FRAME.to_dict(), tiles=[p for p, _ in RING32],
                    carts=[p for p, _ in RING32], headings=[math.degrees(h) for _, h in RING32]),
    )
    for key in KEYS:
        if opt["only"] and key not in opt["only"]:
            continue
        for view in opt["views"]:
            path = os.path.join(OUT, "%s_%s.png" % (key, view))
            if view == "ring8":
                render_game(key, RING8_FRAME, [(x, y, h) for (x, y), h in RING8], path)
            elif view == "ring32w":
                render_game(key, RING32W_FRAME, [(x, y, h) for (x, y), h in RING32W], path)
            elif view == "ring32":
                render_game(key, RING32_FRAME, [(x, y, h) for (x, y), h in RING32], path)
            elif key != MAIN and view not in ("hero",):
                continue
            elif view == "field":
                render_game(key, FIELD_FRAME, field_poses, path)
            elif view == "side":
                view_free(key, [((x, 0), ["E-W"]) for x in (-1, 0, 1, 2)],
                          [(0, 0, -D90), (1, 0, -D90)], (90, 0, 0), (0.5, 0, 0.16), 2.4, (1228, 420), path)
            elif view == "hero":
                view_free(key, [((-1, 0), ["E-W"]), ((0, 0), ["E-W", "N-S"]), ((1, 0), ["E-W", "S-W"]),
                                ((1, -1), ["N-S"]), ((0, 1), ["N-S"])],
                          [(0, 0, -D90), K.tile_point((1, 0), "W", "S", 0.5), (0, 1, 0)],
                          (58, 0, 32), (0.4, 0.0, 0.1), 3.0, (1200, 960), path)
            elif view == "closeup":
                view_free(key, [((0, 0), ["N-S"])], [(0, 0, 0)], (52, 0, 35), (0.0, 0.0, 0.12), 1.15,
                          (1000, 800), path)
            elif view == "section":
                frames["section"] = view_section(key, path)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(frames, f, indent=1)


main()
