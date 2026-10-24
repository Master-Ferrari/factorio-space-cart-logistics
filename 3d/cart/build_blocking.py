# -*- coding: utf-8 -*-
"""Блокинг каретки: все концепты (раунды — concepts.py) в одном cart_blocking.blend.

Запуск (из этой папки):
  blender -b --factory-startup --python build_blocking.py

Локальные оси каретки: начало — на оси рельса на уровне ложа (z = 0), +Y — вперёд
по ходу, Z — вверх. 1 BU = 1 тайл. Каждый концепт — коллекция CART_<ключ> (исключена
из вью-лейера, живёт инстансами), корень — пустышка cart_<ключ> в начале координат.
Сцена PREVIEW в файле — те же концепты на болванке рельса, без растяжки, для глаз.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import scl3d as K  # noqa: E402
from concepts import ROUND1, ROUND2, ROUND3, CURRENT  # noqa: E402
from parts import couplers, pinch_rollers  # noqa: E402
import chest_r2  # noqa: E402
import r3  # noqa: E402

RT = K.RAIL_TOP_Z
D45 = math.radians(45)
D90 = math.radians(90)

CONCEPTS = ROUND1 + ROUND2 + ROUND3


def mats():
    return dict(
        body=K.material("body", (0.62, 0.60, 0.56), rough=0.5),
        body2=K.material("body_dark", (0.20, 0.22, 0.24), rough=0.45),
        wheel=K.material("wheel", (0.07, 0.07, 0.075), rough=0.6),
        steel=K.material("steel", (0.55, 0.57, 0.60), rough=0.3, metal=0.8),
        accent=K.material("accent", (0.90, 0.36, 0.05), rough=0.4),
        cargo=K.material("cargo", (0.10, 0.32, 0.33), rough=0.35),
        lamp=K.material("lamp", (1.0, 0.7, 0.3), emit=(1.0, 0.6, 0.2)),
        glow=K.material("glow", (0.3, 0.9, 1.0), emit=(0.3, 0.9, 1.0)),
        # раунд 2 — ванильная палитра стального сундука
        chest=K.material("chest_steel", (0.20, 0.21, 0.22), rough=0.45, metal=0.55),
        chest_lt=K.material("chest_frame", (0.42, 0.42, 0.41), rough=0.35, metal=0.65),
        frame=K.material("frame_dark", (0.06, 0.06, 0.065), rough=0.55, metal=0.3),
        brass=K.material("brass", (0.55, 0.40, 0.16), rough=0.35, metal=0.8),
        rust=K.material("rust", (0.30, 0.15, 0.08), rough=0.7),
        base=K.material("ref_base", (0.05, 0.05, 0.055), rough=0.7),
        bed=K.material("ref_bed", (0.58, 0.51, 0.43), rough=0.6),
        blade=K.material("ref_blade", (0.62, 0.65, 0.70), rough=0.25, metal=0.9),
        # раунд 3 — сталь трёх тонов + бежевый ложемента (как на тайле), латунь, оранжевый акцент
        dark=K.material("r3_dark", (0.045, 0.047, 0.05), rough=0.5),
        mid=K.material("r3_mid", (0.15, 0.155, 0.16), rough=0.4),
        light=K.material("r3_light", (0.62, 0.65, 0.70), rough=0.3),
        beige=K.material("r3_beige", (0.60, 0.52, 0.42), rough=0.6),
    )


# ── A: щипок (идея автора) ──────────────────────────────────────────
def build_pinch(c, root, M):
    r, w = 0.17, 0.045
    pinch_rollers(c, root, M, r, w)
    # хребет в развале колёс: низ — вдоль плоскостей колёс с зазором (z = |x| + 0.141)
    prof = [(-0.07, 0.211), (0.0, 0.141), (0.07, 0.211), (0.07, 0.34), (-0.07, 0.34)]
    K.profile_sweep_y("spine", c, prof, -0.30, 0.30, mat=M["body"], parent=root, bevel=0.012)
    K.box("cargo", c, (0.16, 0.44, 0.07), loc=(0, -0.02, 0.37), mat=M["cargo"], parent=root, bevel=0.015)
    K.box("lamp", c, (0.08, 0.03, 0.03), loc=(0, 0.30, 0.30), mat=M["lamp"], parent=root)
    # пружинная стяжка колёс (преднатяг щипка) — поперёк над хребтом
    K.cyl("preload", c, 0.018, 0.40, loc=(0, 0.0, 0.30), rot=(0, D90, 0), mat=M["steel"], parent=root)
    couplers(c, root, M, 0.25, y=0.30)


# ── B: седло (корпус обнимает рельс) ───────────────────────────────
def build_saddle(c, root, M):
    prof = [(-0.27, 0.015), (-0.06, 0.015), (-0.06, 0.17), (0.06, 0.17), (0.06, 0.015),
            (0.27, 0.015), (0.27, 0.22), (0.22, 0.30), (-0.22, 0.30), (-0.27, 0.22)]
    K.profile_sweep_y("shell", c, prof, -0.34, 0.34, mat=M["body"], parent=root, bevel=0.02)
    for s in (-1, 1):
        K.cyl("drum%+d" % s, c, 0.145, 0.05, loc=(s * 0.29, 0, 0.155), rot=(0, D90, 0),
              mat=M["wheel"], parent=root, bevel=0.008)
        K.cyl("drumhub%+d" % s, c, 0.05, 0.07, loc=(s * 0.30, 0, 0.155), rot=(0, D90, 0),
              mat=M["accent"], parent=root)
    pinch_rollers(c, root, M, 0.035, 0.02, ys=(-0.2, 0.2), name="pinch", hub=False)  # внутри, снаружи не видно
    K.box("hatch", c, (0.30, 0.36, 0.03), loc=(0, -0.03, 0.31), mat=M["cargo"], parent=root, bevel=0.01)
    K.box("lamp", c, (0.12, 0.03, 0.04), loc=(0, 0.34, 0.24), mat=M["lamp"], parent=root)
    couplers(c, root, M, 0.22)


# ── C: моноколесо ──────────────────────────────────────────────────
def build_monowheel(c, root, M):
    r = 0.19
    zc = RT + r - 0.012                       # V-ручей садится на головку на 1.2 см
    K.cyl("tire", c, r, 0.07, loc=(0, 0, zc), rot=(0, D90, 0), mat=M["wheel"], parent=root, bevel=0.01)
    K.cyl("rim", c, 0.13, 0.08, loc=(0, 0, zc), rot=(0, D90, 0), mat=M["steel"], parent=root)
    K.cyl("hub", c, 0.045, 0.12, loc=(0, 0, zc), rot=(0, D90, 0), mat=M["accent"], parent=root)
    K.arc_slab("fender", c, 0.205, 0.235, math.radians(25), math.radians(155), 0.05,
               loc=(0, 0, zc), mat=M["body"], parent=root)
    K.cyl("axle", c, 0.028, 0.44, loc=(0, 0, zc), rot=(0, D90, 0), mat=M["steel"], parent=root)
    for s in (-1, 1):
        K.box("pod%+d" % s, c, (0.13, 0.50, 0.24), loc=(s * 0.19, 0, 0.16), mat=M["body"],
              parent=root, bevel=0.03)
        K.box("podlid%+d" % s, c, (0.10, 0.36, 0.03), loc=(s * 0.19, 0, 0.29), mat=M["cargo"],
              parent=root, bevel=0.008)
        K.box("podstripe%+d" % s, c, (0.135, 0.04, 0.19), loc=(s * 0.19, 0.23, 0.16), mat=M["accent"],
              parent=root)
    for s in (-1, 1):
        K.box("crossbar%+d" % s, c, (0.26, 0.04, 0.04), loc=(0, s * 0.255, 0.16), mat=M["body2"], parent=root)
    K.box("lamp", c, (0.08, 0.04, 0.03), loc=(0, 0.20, zc + 0.11), mat=M["lamp"], parent=root)
    couplers(c, root, M, 0.16, y=0.27)


# ── D: шайба (диск-тележка + шестигранный корпус) ─────────────────
def build_puck(c, root, M):
    R, ch = 0.30, 0.035                       # радиус диска, полуширина канала под рельс
    # нижняя часть диска — две «D»-половины по сторонам канала
    for s in (-1, 1):
        pts = []
        for i in range(41):
            a = -D90 + math.pi * i / 40
            x, y = R * math.cos(a), R * math.sin(a)
            if x >= ch:
                pts.append((x, y))
        hy = math.sqrt(R * R - ch * ch)
        pts = [(ch, -hy)] + pts + [(ch, hy)]
        pts = [(s * x, y) for x, y in pts]
        if s < 0:
            pts = pts[::-1]
        K.prism("disc_low%+d" % s, c, pts, 0.015, 0.14, mat=M["body2"], parent=root, bevel=0.01)
    K.cyl("disc_top", c, R, 0.03, loc=(0, 0, 0.155), mat=M["body2"], parent=root, bevel=0.008)
    K.cyl("bumper", c, R + 0.015, 0.045, loc=(0, 0, 0.09), mat=M["wheel"], parent=root)
    K.cyl("bearing", c, 0.20, 0.03, loc=(0, 0, 0.185), mat=M["steel"], parent=root)
    hexr = 0.26
    hexp = [(hexr * math.cos(math.radians(60 * i)), hexr * math.sin(math.radians(60 * i))) for i in range(6)]
    K.prism("body", c, hexp, 0.20, 0.32, mat=M["body"], parent=root, bevel=0.015)
    hexs = [(0.15 * math.cos(math.radians(60 * i)), 0.15 * math.sin(math.radians(60 * i))) for i in range(6)]
    K.prism("hatch", c, hexs, 0.32, 0.34, mat=M["cargo"], parent=root, bevel=0.006)
    pinch_rollers(c, root, M, 0.03, 0.02, ys=(-0.18, 0.18), name="pinch", hub=False)  # в канале диска
    K.cyl("target", c, 0.045, 0.02, loc=(0, R + 0.012, 0.09), rot=(D90, 0, 0), mat=M["accent"], parent=root)
    K.box("lamp", c, (0.10, 0.03, 0.04), loc=(0, hexr * math.sqrt(3) / 2 + 0.005, 0.27), mat=M["lamp"], parent=root)
    couplers(c, root, M, 0.12, y=0.31)


# ── E: магнитный скат (maglev, без колёс) ──────────────────────────
def build_manta(c, root, M):
    hull = K.ellipsoid("hull", c, (0.33, 0.37, 0.15), loc=(0, 0, 0.07), mat=M["body"], parent=root)
    cut = K.box("cut_bottom", c, (1, 1, 0.2), loc=(0, 0, -0.085), parent=root)
    K.bool_cut(hull, cut)                                 # низ корпуса — по ложу, z = 0.015
    cut = K.box("cut_channel", c, (0.10, 1, 0.33), loc=(0, 0, 0.0), parent=root)
    K.bool_cut(hull, cut)                                 # канал под рельс до z = 0.165
    for s in (-1, 1):
        K.box("glow%+d" % s, c, (0.012, 0.56, 0.03), loc=(s * 0.056, 0, 0.05), mat=M["glow"], parent=root)
    K.ellipsoid("hump", c, (0.15, 0.21, 0.07), loc=(0, -0.03, 0.20), mat=M["cargo"], parent=root)
    K.box("lamp", c, (0.10, 0.03, 0.025), loc=(0, 0.34, 0.11), mat=M["lamp"], parent=root)
    for s in (-1, 1):
        K.box("fin%+d" % s, c, (0.05, 0.16, 0.06), loc=(s * 0.31, -0.18, 0.06), mat=M["accent"], parent=root, bevel=0.01)
    couplers(c, root, M, 0.19, y=0.33)


BUILDERS = dict(pinch=build_pinch, saddle=build_saddle, monowheel=build_monowheel, puck=build_puck,
                manta=build_manta)
BUILDERS.update(chest_r2.BUILDERS)
BUILDERS.update(r3.BUILDERS)


def build_all():
    K.reset_scene()
    M = mats()
    carts = {}
    for key, name, _ in CONCEPTS:
        c = K.collection("CART_%s_%s" % (key, name))
        root = K.empty("cart_%s" % key, c)
        BUILDERS[name](c, root, M)
        carts[key] = c
    # превью без растяжки: каждый концепт — поезд из трёх на прямой E-W + болванка рельса
    prev = K.collection("PREVIEW")
    for i, (key, name, title) in enumerate(CURRENT):
        y = -i * 2.0
        K.rail_ref(prev, [((x, y), ["E-W"]) for x in (-1, 0, 1, 2)], M)
        for j, x in enumerate((-1, 0, 1)):
            inst = bpy.data.objects.new("prev_%s_%d" % (key, j), None)
            inst.instance_type = 'COLLECTION'
            inst.instance_collection = carts[key]
            inst.location = (x, y, 0)
            inst.rotation_euler = (0, 0, -D90)              # курс на восток
            prev.objects.link(inst)
        cu = bpy.data.curves.new("label_%s" % key, 'FONT')
        cu.body = "%s  %s" % (key, name)
        cu.size = 0.3
        t = bpy.data.objects.new("label_%s" % key, cu)
        t.location = (-1.6, y + 0.6, 0)
        prev.objects.link(t)
    for c in carts.values():
        K.collection(c.name, exclude=True)
    return carts


if __name__ == "__main__":
    build_all()
    out = os.path.join(HERE, "cart_blocking.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("saved", out)
