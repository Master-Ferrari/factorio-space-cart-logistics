# -*- coding: utf-8 -*-
"""Ходовые огни: на скосе носа и кормы по две продолговатые LED-полосы — спереди белые, сзади красные.

Автор: «можешь дополнить мою модель двумя продолговато-вертикальными led огнями ? сзади красные, спереди белые»;
«размести огни под углом - как у границы панели в которой они находятся / размести их также чуть выше на небольшом
равном отступе от границ / цвет сделай умереннее»; «добавь небольшую тёмную окантовку фонарей на модели».
Перёд — +Y модели (heading 0 = facing 1 = север). Скос торца — плоскость с нормалью N0, в ней утоплена панель.
Координаты в плоскости скоса: s — поперёк (= X мира), t — вверх по скосу от точки C0. Нижняя скошенная кромка
панели (замер лучами по сетке 1 см) идёт от EDGE_A к EDGE_B, ~43° от вертикали. Полоса — параллельно ей, отступ GAP
от кромки, точка и нормаль — лучом в body. Добавляются в CART_A при рендере (apply), .blend не перезаписывается.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

N0 = Vector((0, 0.6306, 0.7761))   # нормаль скоса носа (корма — зеркально по Y)
C0 = (0.355, 0.445)                 # (|y|, z) начала координат s, t на скосе
EDGE_A = (0.145, -0.03)             # (|s|, t) нижний конец скошенной кромки панели
EDGE_B = (0.225, 0.055)             # верхний конец
GAP = 0.012         # отступ полосы от кромки (и снизу — от низа панели, по месту)
ALONG = 0.022       # сдвиг низа полосы вдоль кромки от EDGE_A («чуть выше»)
LEN = 0.075         # вдоль кромки
WID = 0.024         # поперёк
THK = 0.010         # толщина, наполовину в панели
RIM = 0.008         # тёмная окантовка: шире полосы на столько с каждой стороны, чуть ниже её
RIM_COL = (0.025, 0.025, 0.027)
FRONT = ((1.0, 0.93, 0.82), 2.5)                # цвет излучения, сила: тёплый белый
REAR = ((1.0, 0.06, 0.03), 2.0)                 # приглушённый красный (сильнее — AgX выжигает в оранжевый)


def material(name, col, strength):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = 0.25
    b.inputs["Emission Color"].default_value = (*col, 1)
    b.inputs["Emission Strength"].default_value = strength
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def rim_material():
    m = bpy.data.materials.get("led_rim") or bpy.data.materials.new("led_rim")
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*RIM_COL, 1)
    b.inputs["Metallic"].default_value = 0.0
    b.inputs["Roughness"].default_value = 0.55
    return m


def strip(name, coll, at, normal, axis, mat, wid=WID, ln=LEN, thk=THK, dz=0.0):
    """Плоская плашка со скруглёнными углами (профиль выдавлен по нормали): локальная Y — вдоль axis, Z — по нормали."""
    r, seg = wid * 0.4, 6
    pts = []
    for cx, cy, a0 in ((wid / 2 - r, ln / 2 - r, 0), (-wid / 2 + r, ln / 2 - r, 90),
                       (-wid / 2 + r, -ln / 2 + r, 180), (wid / 2 - r, -ln / 2 + r, 270)):
        for k in range(seg + 1):
            t = math.radians(a0 + 90 * k / seg)
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    bm = bmesh.new()
    bot = [bm.verts.new((x, y, dz - thk / 2)) for x, y in pts]
    top = [bm.verts.new((x, y, dz + thk / 2)) for x, y in pts]
    bm.faces.new(top)
    bm.faces.new(bot[::-1])
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    n = normal.normalized()
    ax = (axis - n * axis.dot(n)).normalized()
    side = ax.cross(n)
    o = bpy.data.objects.new(name, me)
    o.matrix_world = Matrix.Translation(at) @ Matrix((side, ax, n)).transposed().to_4x4()
    coll.objects.link(o)
    return o


def apply():
    coll = bpy.data.collections["CART_A"]
    body = bpy.data.objects["body"]
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.transform(body.matrix_world)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    mats = {1: material("led_front", *FRONT), -1: material("led_rear", *REAR)}
    rim = rim_material()
    ds, dt = EDGE_B[0] - EDGE_A[0], EDGE_B[1] - EDGE_A[1]
    k = (ds * ds + dt * dt) ** 0.5
    ds, dt = ds / k, dt / k                                     # вдоль кромки, вверх-наружу
    ins, int_ = -dt, ds                                         # перпендикуляр внутрь панели (к оси, вверх)
    ins, int_ = (ins, int_) if ins < 0 else (-ins, -int_)
    a = ALONG + LEN / 2
    off = GAP + WID / 2
    cs = EDGE_A[0] + ds * a + ins * off                         # |s| центра полосы
    ct = EDGE_A[1] + dt * a + int_ * off
    for sgn in (1, -1):
        n0 = Vector((0, sgn * N0.y, N0.z))
        up = Vector((0, -sgn * N0.z, N0.y))                     # вверх по скосу
        c0 = Vector((0, sgn * C0[0], C0[1]))
        for sx in (1, -1):
            p = c0 + Vector((sx * cs, 0, 0)) + up * ct
            hit, nrm, _, _ = tree.ray_cast(p + n0 * 0.3, -n0)
            axis = Vector((sx * ds, 0, 0)) + up * dt
            nm = "led_%s_%s" % ("front" if sgn > 0 else "rear", "R" if sx > 0 else "L")
            strip(nm, coll, hit, nrm, axis, mats[sgn])
            strip(nm + "_rim", coll, hit, nrm, axis, rim, WID + 2 * RIM, LEN + 2 * RIM, THK, -THK * 0.25)
    print("leds: 4 strips at |s|=%.3f t=%.3f" % (cs, ct), flush=True)


def light_only():
    """Проход карты освещения: в сцене светят только полосы (солнца, HDRI и пружинный свет гасятся)."""
    sc = bpy.context.scene
    for o in sc.objects:
        if o.type == 'LIGHT':
            o.hide_render = True
    bg = sc.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Strength"].default_value = 0.0
