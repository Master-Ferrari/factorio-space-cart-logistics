# -*- coding: utf-8 -*-
"""Рендер hp2 с генеративными материалами (Cycles, мало сэмплов + денойз).

Запуск:  blender -b cart_hp2.blend --python render_tex.py -- [--views single,field,...] [--samples N]
(без --factory-startup: с ним Cycles в фоне виснет).
Берёт кадры игровых видов из out/render/frames.json (их пишет render.py), пишет out/render/T_<view>.png —
ключ варианта «T»: compose.game_view и film/src/panels.py берут их как обычный вариант. Тень — shadow catcher
(в альфе), отдельного прохода _sh нет. Сохраняет cart_hp2_tex.blend (материалы + свет).
"""

import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import scl3d as K  # noqa: E402
import tex  # noqa: E402

OUT = os.path.join(HERE, "out", "render")
EAST = -math.pi / 2
GAME = ["field", "ring32", "single", "single_ns", "single_dg"]
# свет (tex_06, автор: «расположи свет строго слева под 45 градусов. плюс используй hdri карту как ту что используется
# в тайлах»): солнце летит с запада на восток, возвышение 45°. Y = 0 — растяжка WORLD по Y направление не меняет,
# на экране (u = x) свет идёт точно слева, тень на землю — строго вправо.
SUN_DIR = (1.0, 0.0, -1.0)
SUN_E = 4.4
# HDRI — как в мире Untitled.blend (тайлы автора): Environment Texture по Generated через Mapping с нулевым
# вращением, Background сила 1.0; подложка тайла рендерилась с AF_blur02, рельсы — с резкой «Autumn Forest».
HDRI_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "hdri"))     # файлы автора: только читаем
HDRI = os.path.join(HDRI_DIR, "AF_blur02.exr")
HDRI_E = 0.5


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opt = dict(views=GAME + ["hero", "close"], samples=24, painted="--painted" in a)
    a = [x for x in a if x != "--painted"]
    for i in range(0, len(a) - 1, 2):
        if a[i] == "--views":
            opt["views"] = a[i + 1].split(",")
        elif a[i] == "--samples":
            opt["samples"] = int(a[i + 1])
    return opt


def setup(samples):
    sc = K.setup_cycles(samples, gpu=True)
    cy = sc.cycles
    cy.adaptive_threshold = 0.03
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 4, 2, 2
    cy.transmission_bounces = cy.volume_bounces = 0
    cy.transparent_max_bounces = 4
    try:
        cy.denoiser = 'OPENIMAGEDENOISE'
    except Exception:
        pass
    sc.render.film_transparent = True
    # мир — HDRI автора (как у тайлов), по абсолютному пути, без копирования
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    env = nt.nodes.new('ShaderNodeTexEnvironment')
    env.image = bpy.data.images.load(HDRI, check_existing=True)
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs["Strength"].default_value = HDRI_E
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    o = nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(bg.outputs["Background"], o.inputs["Surface"])


def view_coll():
    v = bpy.data.collections.get("VIEW") or K.collection("VIEW")
    for o in list(v.objects):
        if o.type != 'LIGHT':
            bpy.data.objects.remove(o, do_unlink=True)
    return v


def catcher(v, parent):
    me = bpy.data.meshes.new("catcher")
    me.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
    o = bpy.data.objects.new("catcher", me)
    v.objects.link(o)
    o.parent = parent
    o.is_shadow_catcher = True
    return o


def instance(v, x, y, h, parent):
    o = bpy.data.objects.new("c", None)
    o.instance_type = 'COLLECTION'
    o.instance_collection = bpy.data.collections["CART_A"]
    v.objects.link(o)
    o.parent = parent
    o.location = (x, y, 0)
    o.rotation_euler = (0, 0, h)
    return o


def spring_light(sun, v):
    """Пружина в полутени корпуса и накладки не читается витками (отзыв автора). Light/shadow linking Cycles:
    основное солнце пружину не освещает; второе такое же солнце освещает только пружину, а тени для него
    отбрасывает только сама пружина (витки затеняют друг друга, корпус — нет). Тень на остальном прежняя."""
    sp = bpy.data.collections.get("SPRINGS") or bpy.data.collections.new("SPRINGS")
    for nm in ("spring_L", "spring_R", "spring_seat_L", "spring_seat_R"):
        o = bpy.data.objects[nm]
        if o.name not in sp.objects:
            sp.objects.link(o)
    sun.light_linking.receiver_collection = sp
    for c in sun.light_linking.receiver_collection.collection_objects:
        c.light_linking.link_state = 'EXCLUDE'
    s2 = K.sun("sun_spring", v, SUN_DIR, SUN_E, 2.0)
    s2.light_linking.receiver_collection = sp
    s2.light_linking.blocker_collection = sp
    return s2


def render(path):
    t = time.time()
    K.render_to(path)
    print("rendered %s %.1fs" % (os.path.basename(path), time.time() - t), flush=True)


def main():
    opt = args()
    setup(opt["samples"])
    # --painted (make.py --tex painted, на cart_hp2_paint.blend): карты автора из tex_in/ вместо генеративных
    key = "P" if opt["painted"] else "T"
    if opt["painted"]:
        import painted
        painted.apply()
    else:
        tex.apply()
    for m in bpy.data.materials:
        m.use_fake_user = m.name.startswith("hp2_")
    v = view_coll()
    for o in [o for o in v.objects if o.type == 'LIGHT']:
        bpy.data.objects.remove(o, do_unlink=True)
    spring_light(K.sun("sun", v, SUN_DIR, SUN_E, 2.0), v)
    with open(os.path.join(OUT, "frames.json"), encoding="utf-8") as f:
        frames = json.load(f)
    for view in opt["views"]:
        p = os.path.join(OUT, "%s_%s.png" % (key, view))
        v = view_coll()
        if view in GAME:
            world = K.empty("WORLD", v, scale=(1, K.STRETCH, 1))
            for x, y, h in frames[view]["poses"]:
                instance(v, x, y, h, world)
            catcher(v, world)
            K.game_camera("cam", v, K.Frame.from_dict(frames[view]["frame"]))
            render(p)
        elif view == "hero":
            tiles = [((-1, 0), ["E-W"]), ((0, 0), ["E-W", "N-S"]), ((1, 0), ["E-W", "S-W"]),
                     ((1, -1), ["N-S"]), ((0, 1), ["N-S"]), ((-2, 0), ["E-W"])]
            M = bpy.data.materials
            K.rail_ref(v, tiles, dict(base=M["hp2_ref_base"], bed=M["hp2_ref_bed"], blade=M["hp2_ref_blade"]))
            for x, y, h in [(-1, 0, EAST), (0, 0, EAST), K.tile_point((1, 0), "W", "S", 0.5), (0, 1, 0)]:
                instance(v, x, y, h, None)
            K.free_camera("cam", v, (0.15, 0.25, 0.2), (58, 0, 32), 2.7, (1000, 800))
            render(p)
        elif view == "close":
            # крупно 3/4: тот же ракурс, что persp на листе close; и игровой угол 45° без растяжки
            instance(v, 0, 0, EAST, None)
            catcher(v, None)
            K.free_camera("cam", v, (0, 0, 0.30), (62, 0, 38), 0.95, (1100, 1100))
            render(os.path.join(OUT, key + "_close_persp.png"))
            K.free_camera("cam", v, (0, 0, 0.30), (45, 0, 0), 1.0, (1100, 1100))
            render(os.path.join(OUT, key + "_close_game.png"))
    if not opt["painted"]:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "cart_hp2_tex.blend"))
        print("saved cart_hp2_tex.blend")


if __name__ == "__main__":
    main()
