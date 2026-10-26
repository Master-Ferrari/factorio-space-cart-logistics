# -*- coding: utf-8 -*-
"""Материалы деталей из FBX автора (cart_hp2_fix.blend, сборка — fix_build.py): его верхняя панель и его лампы.

Панель new_door — «битмапа окклюзии + характерный шум» (автор), палитра снята со скриншота альбедо старой панели
(медианы полос яркости, sRGB): пурпурное дно 50,21,39 (~30 % площади), грязь-переход 90,81,76 (~20 %),
краска рёбер и рамки 132,128,122 (~43 %), блик 149,144,140. AO панели (UVAO, ~0.90–1.00 на поле) растягивается
на 0–1 и смещается шумом; дно — где AO ниже, грязь — по краю перехода. Шероховатость и металличность — по старым
картам автора на прежней двери: дно 0.98 / 0.03, рёбра 0.58 / 0.41.
Лампы: группа front_lamps — тёплый белый, back_lamps — красный (leds.py), окантовки rim* — тёмные.
"""

import os

import bpy
import numpy as np

import leds

HERE = os.path.dirname(os.path.abspath(__file__))
AO = os.path.join(HERE, "out", "bake", "new_door_ao.png")


def srgb(r, g, b):
    return tuple(((c / 255 + 0.055) / 1.055) ** 2.4 if c / 255 > 0.04045 else c / 255 / 12.92 for c in (r, g, b)) + (1,)


# контраст (автор: «ещё немного контрастнее»): дно и грязь темнее на ~15 %, краска и блик светлее на ~8 %
PURPLE, DIRT, PAINT, HIGH = srgb(42, 17, 33), srgb(76, 68, 64), srgb(142, 138, 132), srgb(161, 156, 151)
AO_LO = 0.90                    # AO поля панели: 1 % — 0.90, медиана — 1.0
# Граница — резкий порог (не плавный переход): у автора пятна рваные, с зубчатым краем, а не ровная дымка.
# Шум — три октавы: зоны чисто/грязно (крупно), форма пятен (фрактал), зубцы края (мелко); Fac шума Блендера
# держится около 0.5 ± 0.1, поэтому усиление ×1.6…2.6, иначе порог на верхах рёбер не достигается.
PURPLE_T = 0.62                 # пурпур: шумная AO ниже порога — дно и пятна, затёкшие на рёбра
DIRT_T = 0.70                   # серо-бурая кайма вокруг пурпурных пятен
EDGE = 0.012                    # полуширина порога
FILM = (0.55, 0.97, 0.7)        # полупрозрачная пурпурная плёнка в низинах: по чистой AO (от, до, непрозрачность)


def door_material():
    m = bpy.data.materials.new("new_door")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    L = nt.links.new
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L(b.outputs["BSDF"], out.inputs["Surface"])
    uv = nt.nodes.new('ShaderNodeUVMap')
    uv.uv_map = "UVAO"
    img = nt.nodes.new('ShaderNodeTexImage')
    img.image = bpy.data.images.load(AO, check_existing=True)
    img.image.colorspace_settings.name = 'Non-Color'
    img.extension = 'EXTEND'
    L(uv.outputs["UV"], img.inputs["Vector"])

    def node(kind, **inp):
        n = nt.nodes.new(kind)
        for k, v in inp.items():
            n.inputs[k].default_value = v
        return n

    def noise(scale, detail, rough):
        n = node('ShaderNodeTexNoise', Scale=scale, Detail=detail, Roughness=rough)
        L(uv.outputs["UV"], n.inputs["Vector"])
        return n.outputs["Fac"]

    ao = node('ShaderNodeMapRange', **{"From Min": AO_LO, "From Max": 1.0})
    L(img.outputs["Color"], ao.inputs["Value"])
    def madd(src, mul, add):
        n = nt.nodes.new('ShaderNodeMath')
        n.operation = 'MULTIPLY_ADD'
        L(src, n.inputs[0])
        n.inputs[1].default_value, n.inputs[2].default_value = mul, add
        return n.outputs[0]

    def add(a, bb):
        n = nt.nodes.new('ShaderNodeMath')
        L(a, n.inputs[0])
        L(bb, n.inputs[1])
        return n.outputs[0]

    zone, shape, jag = noise(4.0, 2.0, 0.5), noise(14.0, 12.0, 0.8), noise(90.0, 8.0, 0.8)
    m_ = add(add(add(ao.outputs["Result"], madd(zone, 1.6, -0.8)), madd(shape, 2.6, -1.3)), madd(jag, 0.8, -0.4))

    def below(t):
        """1 — ниже порога t, 0 — выше; переход узкий (±EDGE) — рваный край пятна."""
        r = node('ShaderNodeMapRange', **{"From Min": t - EDGE, "From Max": t + EDGE, "To Min": 1.0, "To Max": 0.0})
        L(m_, r.inputs["Value"])
        return r.outputs["Result"]

    purple, dirt = below(PURPLE_T), below(DIRT_T)
    n2 = shape

    def mix(kind, a, bb, fac):
        n = nt.nodes.new('ShaderNodeMix')
        n.data_type = kind
        ia, ib, o = (6, 7, 2) if kind == 'RGBA' else (2, 3, 0)
        for i, v in ((ia, a), (ib, bb)):
            if isinstance(v, bpy.types.NodeSocket):
                L(v, n.inputs[i])
            else:
                n.inputs[i].default_value = v
        L(fac, n.inputs["Factor"])
        return n.outputs[o]

    col = mix('RGBA', PAINT, HIGH, n2)
    col = mix('RGBA', col, DIRT, dirt)
    # автор: «чуть больше полупрозрачного покрытия в низинах» — плавно по AO, без шума, под рваными пятнами
    film = node('ShaderNodeMapRange', **{"From Min": FILM[0], "From Max": FILM[1], "To Min": FILM[2], "To Max": 0.0})
    film.interpolation_type = 'SMOOTHSTEP'
    L(ao.outputs["Result"], film.inputs["Value"])
    col = mix('RGBA', col, PURPLE, film.outputs["Result"])
    col = mix('RGBA', col, PURPLE, purple)
    L(col, b.inputs["Base Color"])
    rough = mix('FLOAT', mix('FLOAT', 0.58, 0.85, dirt), 0.98, purple)
    metal = mix('FLOAT', mix('FLOAT', 0.41, 0.12, dirt), 0.03, purple)
    L(rough, b.inputs["Roughness"])
    L(metal, b.inputs["Metallic"])
    return m


# Выключенные лампы. Автор: «у них должен быть виден фринель эффект. у передних синий отблеск, у задних бордовый»;
# «сделай текстурой чтобы по краям был насыщенный свет»; затем: «синий только на фасках. плавный переход».
# Градиент — по форме лампы, а не по UV (маска по UV давала цвет только на фасках): в плоскости лицевой грани лампа —
# капсула (полудлина A, полуширина B); расстояние до её контура d ∈ [−B, 0] даёт t = 1 + d/B — 0 на осевой линии
# (тёмная середина), 1 на контуре и дальше, на фасках и боковинах (насыщенный край). Переход плавный по всей ширине.
OFF_CORE = {"front_lamps": srgb(16, 18, 30), "back_lamps": srgb(42, 11, 17)}        # середина
OFF_EDGE = {"front_lamps": srgb(62, 82, 150), "back_lamps": srgb(160, 22, 48)}  # край
EDGE_POW = 3.0                  # кривая t: смесь идёт в линейном цвете — 30 % яркого синего уже светлое на глаз, поэтому круто


def lamp_frame(o):
    """Центр, оси (длинная, короткая) и полуразмеры лампы целиком (с фасками) в плоскости её лицевой грани,
    в локальных координатах: по одной лицевой грани (узкая плоская середина) тёмной выходила только черта."""
    me = o.data
    big = max(me.polygons, key=lambda p: p.area)
    pts = np.array([v.co[:] for v in me.vertices])
    n = np.array(big.normal[:])
    q = pts - pts.mean(0)
    q -= np.outer(q @ n, n)
    _, vec = np.linalg.eigh(q.T @ q)
    u = vec[:, 2]                                  # длинная ось
    v = np.cross(n, u)
    pu, pv = q @ u, q @ v
    c = pts.mean(0) + u * (pu.max() + pu.min()) / 2 + v * (pv.max() + pv.min()) / 2
    return c, u, v, (pu.max() - pu.min()) / 2, (pv.max() - pv.min()) / 2


def lamp_off_material(o, core, edge):
    """Выключенная лампа (днём, без карты света): без свечения, цвет середина ↔ край по расстоянию до контура."""
    c, u, v, A, B = lamp_frame(o)
    m = bpy.data.materials.new("lamp_off_" + o.name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    L = nt.links.new
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L(b.outputs["BSDF"], out.inputs["Surface"])
    b.inputs["Roughness"].default_value = 0.3
    b.inputs["Metallic"].default_value = 0.0

    def vm(op, a_, b_=None):
        n_ = nt.nodes.new('ShaderNodeVectorMath')
        n_.operation = op
        for i, x in enumerate((a_, b_)):
            if x is None:
                continue
            if isinstance(x, bpy.types.NodeSocket):
                L(x, n_.inputs[i])
            else:
                n_.inputs[i].default_value = x
        return n_.outputs["Value" if op in ('DOT_PRODUCT', 'LENGTH') else "Vector"]

    def mt(op, a_, b_=0.0):
        n_ = nt.nodes.new('ShaderNodeMath')
        n_.operation = op
        for i, x in enumerate((a_, b_)):
            if isinstance(x, bpy.types.NodeSocket):
                L(x, n_.inputs[i])
            else:
                n_.inputs[i].default_value = x
        return n_.outputs[0]

    tc = nt.nodes.new('ShaderNodeTexCoord')
    p = vm('SUBTRACT', tc.outputs["Object"], tuple(c))
    px = mt('ABSOLUTE', vm('DOT_PRODUCT', p, tuple(u)))
    py = vm('DOT_PRODUCT', p, tuple(v))
    qx = mt('MAXIMUM', mt('SUBTRACT', px, A - B), 0.0)          # капсула: отрезок ±(A−B) по длинной оси, радиус B
    cx = nt.nodes.new('ShaderNodeCombineXYZ')
    L(qx, cx.inputs["X"])
    L(py, cx.inputs["Y"])
    d = mt('SUBTRACT', vm('LENGTH', cx.outputs["Vector"]), B)
    t = mt('POWER', mt('MAXIMUM', mt('MINIMUM', mt('ADD', mt('DIVIDE', d, B), 1.0), 1.0), 0.0), EDGE_POW)
    mx = nt.nodes.new('ShaderNodeMix')
    mx.data_type = 'RGBA'
    L(t, mx.inputs["Factor"])
    mx.inputs[6].default_value = core
    mx.inputs[7].default_value = edge
    L(mx.outputs[2], b.inputs["Base Color"])
    return m


LAMPS = {}                      # объект лампы -> горящий материал (для прохода света, lamps_on)


def apply(lamps_off=False):
    door = bpy.data.objects["new_door"]
    door.data.materials.clear()
    door.data.materials.append(door_material())
    white, red, rim = leds.material("led_front", *leds.FRONT), leds.material("led_rear", *leds.REAR), leds.rim_material()
    for o in bpy.data.collections["CART_A"].all_objects:
        if o.parent and o.parent.name in ("front_lamps", "back_lamps"):
            on = rim if o.name.startswith("rim") else white if o.parent.name == "front_lamps" else red
            g = o.parent.name
            mat = lamp_off_material(o, OFF_CORE[g], OFF_EDGE[g]) if lamps_off and on is not rim else on
            LAMPS[o] = on
            o.data.materials.clear()
            o.data.materials.append(mat)
    print("fix: new_door AO+noise, lamps %s" % ("off (day)" if lamps_off else "on"), flush=True)


def lamps_on():
    """Проход карты света: лампы горят, что бы ни стояло днём."""
    for o, mat in LAMPS.items():
        o.data.materials[0] = mat
