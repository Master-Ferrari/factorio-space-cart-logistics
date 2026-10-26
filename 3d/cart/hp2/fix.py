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


def apply():
    door = bpy.data.objects["new_door"]
    door.data.materials.clear()
    door.data.materials.append(door_material())
    white, red, rim = leds.material("led_front", *leds.FRONT), leds.material("led_rear", *leds.REAR), leds.rim_material()
    for o in bpy.data.collections["CART_A"].all_objects:
        if o.parent and o.parent.name in ("front_lamps", "back_lamps"):
            mat = rim if o.name.startswith("rim") else white if o.parent.name == "front_lamps" else red
            o.data.materials.clear()
            o.data.materials.append(mat)
    print("fix: new_door AO+noise, lamps front/back", flush=True)
