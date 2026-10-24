# -*- coding: utf-8 -*-
"""Блокинг каретки v7b (идея автора «b»): корпус v5b, вокруг лезвия три колеса в сечении —
два больших боковых с вертикальной осью и малое сверху (их два: спереди и сзади).

Запуск:  blender -b --factory-startup --python build.py
Пишет cart_v7b.blend: коллекции CART_<K> (исключены из вью-лейера, корень — пустышка в 0).

Лоуполи: корпус — куб, обрезанный плоскостями (bisect_plane + заливка дыр),
колёса — 24-гранные «токарные» профили, фаски одним сегментом.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import scl3d as K  # noqa: E402
from params import VARIANTS  # noqa: E402

BLEND = os.path.join(HERE, "cart_v7b.blend")
NSEG = 24


# ── материалы (Workbench берёт diffuse_color) ──────────────────────
def mats():
    return dict(
        steel=K.material("v7b_steel", (0.105, 0.108, 0.115), 0.5, 0.6),       # тёмная сталь ящика
        steel2=K.material("v7b_steel2", (0.24, 0.245, 0.255), 0.45, 0.7),     # светлее: утопленные панели
        rim=K.material("v7b_rim", (0.55, 0.58, 0.62), 0.25, 1.0),             # хром обода (как лезвия)
        web=K.material("v7b_web", (0.05, 0.05, 0.055), 0.6, 0.4),             # тёмный диск колеса
        brass=K.material("v7b_brass", (0.50, 0.32, 0.08), 0.35, 1.0),         # втулки
        beige=K.material("v7b_beige", (0.56, 0.50, 0.40), 0.6, 0.0),          # как ложементы рельса
        orange=K.material("v7b_orange", (0.85, 0.32, 0.02), 0.5, 0.0),        # акцент
        # болванка рельса
        base=K.material("v7b_ref_base", (0.05, 0.05, 0.055), 0.7, 0.3),
        bed=K.material("v7b_ref_bed", (0.56, 0.50, 0.40), 0.6, 0.0),
        blade=K.material("v7b_ref_blade", (0.62, 0.65, 0.70), 0.2, 1.0),
    )


# ── bmesh-инструменты ──────────────────────────────────────────────
def bm_box(bm, x0, x1, y0, y1, z0, z1):
    g = bmesh.ops.create_cube(bm, size=1.0)
    vs = g["verts"]
    bmesh.ops.scale(bm, vec=(x1 - x0, y1 - y0, z1 - z0), verts=vs)
    bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), verts=vs)
    return vs


def cut(bm, co, no):
    """Ножницы: отрезать всё по ту сторону плоскости, куда смотрит нормаль no, и заделать срез."""
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    res = bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=co, plane_no=no, clear_outer=True)
    edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    if edges:
        bmesh.ops.holes_fill(bm, edges=edges, sides=0)


def lathe(bm, prof, n=NSEG, a0=None):
    """Тело вращения вокруг локальной Z: замкнутый профиль [(радиус, z), ...]."""
    a0 = math.pi / n if a0 is None else a0
    rings = []
    for i in range(n):
        a = a0 + 2 * math.pi * i / n
        c, s = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((r * c, r * s, z)) for r, z in prof])
    k = len(prof)
    for i in range(n):
        j = (i + 1) % n
        for p in range(k):
            q = (p + 1) % k
            bm.faces.new((rings[i][p], rings[j][p], rings[j][q], rings[i][q]))


def disc(bm, r, z0, z1, n=NSEG, a0=None):
    a0 = math.pi / n if a0 is None else a0
    bot = [bm.verts.new((r * math.cos(a0 + 2 * math.pi * i / n), r * math.sin(a0 + 2 * math.pi * i / n), z0)) for i in range(n)]
    top = [bm.verts.new((v.co.x, v.co.y, z1)) for v in bot]
    bm.faces.new(bot[::-1])
    bm.faces.new(top)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))


def obj_from_bm(name, bm, coll, parent, mat_list, bevel=0.006, matrix=None, angle=35):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mat_list:
        me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    o.parent = parent
    if matrix is not None:
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.matrix_basis = matrix
    if bevel:
        md = o.modifiers.new("bevel", 'BEVEL')
        md.width = bevel
        md.segments = 1
        md.limit_method = 'ANGLE'
        md.angle_limit = math.radians(angle)
    return o


def faces_by_normal(bm, n, tol=0.02):
    n = Vector(n).normalized()
    return [f for f in bm.faces if (f.normal - n).length < tol]


def recess(bm, face, inset, depth, mat_index=None):
    """Утопленная панель: инсет грани + вдавливание внутрь (лоуполи-«люк»)."""
    r = bmesh.ops.inset_region(bm, faces=[face], thickness=inset, depth=0.0, use_even_offset=True)
    nrm = face.normal.copy()
    bmesh.ops.translate(bm, vec=-nrm * depth, verts=list(face.verts))
    if mat_index is not None:
        face.material_index = mat_index
    return r


# ── геометрия развала ───────────────────────────────────────────────
def frame(P):
    """Контакт, направление вверх по колесу m и внутренняя нормаль для восточного колеса (x > 0)."""
    psi = math.radians(P["psi"])
    cx, cz = K.RAIL_HALF_W, K.RAIL_TOP_Z
    m = (math.sin(psi), math.cos(psi))           # вдоль колеса от контакта вверх-наружу (x, z)
    nin = (-math.cos(psi), math.sin(psi))        # внутренняя нормаль колеса (к оси, вверх)
    return cx, cz, m, nin


def keel_halfwidth(P, z):
    """Полуширина корпуса на высоте z, если его киль параллелен колесу с зазором gap."""
    cx, cz, m, nin = frame(P)
    # (x - cx)·nin_x + (z - cz)·nin_z = gap  →  x
    return cx + ((z - cz) * nin[1] - P["gap"]) / (-nin[0])


# ── корпус: куб, обрезанный ножницами ──────────────────────────────
def build_body(P, coll, root, M):
    cx, cz, m, nin = frame(P)
    w = keel_halfwidth(P, P["z1"])
    L2 = P["L"] / 2
    bm = bmesh.new()
    bm_box(bm, -w, w, -L2, L2, P["zb"], P["z3"])
    # киль: две грани параллельно колёсам, с зазором gap
    for s in (1, -1):
        co = (s * (cx + P["gap"] * nin[0]), 0, cz + P["gap"] * nin[1])
        cut(bm, co, (s * -nin[0], 0, -nin[1]))
    # крыша-шатёр поперёк: от верха пояса (w, z2) к (wt, z3)
    for s in (1, -1):
        cut(bm, (s * w, 0, P["z2"]), (s * (P["z3"] - P["z2"]), 0, w - P["wt"]))
    # крыша по ходу: от (L2, z2) к (lt, z3)
    for s in (1, -1):
        cut(bm, (0, s * L2, P["z2"]), (0, s * (P["z3"] - P["z2"]), L2 - P["lt"]))
    # торцы снизу: от (L2, z1e) к (lb, zb)
    for s in (1, -1):
        cut(bm, (0, s * L2, P["z1e"]), (0, s * (P["z1e"] - P["zb"]), -(L2 - P["lb"])))
    # углы в плане
    c = P["cc"]
    for sx in (1, -1):
        for sy in (1, -1):
            cut(bm, (sx * w, sy * (L2 - c), 0), (sx, sy, 0))
    bm.normal_update()
    # люк на узком верхе и «фасады» на скатах поперёк: скат под 45° смотрит прямо в игровую камеру,
    # поэтому это главная грань силуэта (окно скетча). Внутри — бежевая вставка, как ложементы рельса.
    top = max(faces_by_normal(bm, (0, 0, 1)), key=lambda f: f.calc_center_median().z)
    recess(bm, top, 0.018, 0.012, 1)
    bm.normal_update()
    for s in (1, -1):
        nx = Vector((s * (P["z3"] - P["z2"]), 0, w - P["wt"])).normalized()
        fs = faces_by_normal(bm, nx, 0.05)
        if fs:
            f = max(fs, key=lambda f: f.calc_area())
            recess(bm, f, 0.02, 0.014, 1)
            bm.normal_update()
    # торцевые скаты — утопленные панели (боковые щиты скетча)
    for s in (1, -1):
        ny = Vector((0, s * (P["z3"] - P["z2"]), P["L"] / 2 - P["lt"])).normalized()
        fs = faces_by_normal(bm, ny, 0.05)
        if fs:
            f = max(fs, key=lambda f: f.calc_area())
            recess(bm, f, 0.03, 0.012, 1)
            bm.normal_update()
    body = obj_from_bm("body", bm, coll, root, [M["steel"], M["steel2"], M["beige"]], bevel=0.008)
    # бежевое окно-вставка на фасаде (две половины с разрезом поперёк хода — как ложементы рельса)
    # и латунный замок в разрезе
    dx, dz = -(w - P["wt"]), P["z3"] - P["z2"]
    ln = math.hypot(dx, dz)
    for s in (1, -1):
        mid = Vector((s * (w + P["wt"]) / 2, 0, (P["z2"] + P["z3"]) / 2))
        nrm = Vector((s * dz, 0, -dx)).normalized()
        th = math.atan2(-dz, s * dx)
        rot = Matrix.Translation(mid) @ Matrix.Rotation(th, 4, 'Y')
        hw, hl = (ln - 0.075) / 2, P["win"] / 2
        for sy in (1, -1):
            bm = bmesh.new()
            y0, y1 = (0.008, hl) if sy > 0 else (-hl, -0.008)
            bm_box(bm, -hw, hw, y0, y1, -0.014, 0.004)
            obj_from_bm("win%+d%+d" % (s, sy), bm, coll, root, [M["beige"]], bevel=0.004, matrix=rot)
    return body, w


def build_bumpers(P, coll, root, M):
    """Бежевые разрезные буферы на торцах: в поезде упираются друг в друга, как ложементы на стыке тайлов."""
    L2 = P["L"] / 2
    zl, zh = P["zb"] + 0.035, P["z1e"] - 0.005
    for sy in (1, -1):
        for sx in (1, -1):
            bm = bmesh.new()
            x0, x1 = (0.007, 0.13) if sx > 0 else (-0.13, -0.007)
            y0, y1 = (L2 - 0.12, L2 + P["bump"]) if sy > 0 else (-L2 - P["bump"], -L2 + 0.12)
            bm_box(bm, x0, x1, y0, y1, zl, zh)
            yo = sy * (L2 + P["bump"])
            cut(bm, (0, yo - sy * 0.03, zh), (0, sy, 1))          # фаска сверху
            cut(bm, (0, yo - sy * 0.03, zl), (0, sy, -1))         # фаска снизу
            cut(bm, (sx * 0.13, yo - sy * 0.035, 0), (sx, sy, 0))  # угол в плане
            obj_from_bm("bump_%+d%+d" % (sy, sx), bm, coll, root, [M["beige"]], bevel=0.006)
        # латунная втулка-сцепка между половинами
        bm = bmesh.new()
        disc(bm, 0.03, 0, 0.05, 8, 0)
        ym = sy * (L2 + P["bump"] - 0.045)
        mt = Matrix.Translation((0, ym, (zl + zh) / 2)) @ Matrix.Rotation(-sy * math.pi / 2, 4, 'X')
        obj_from_bm("coupler%+d" % sy, bm, coll, root, [M["brass"]], bevel=0.004, matrix=mt)


# ── колёса схемы «b» ───────────────────────────────────────────────
def bar(name, p0, p1, hw, ht, coll, root, mat, bevel=0.004):
    """Брус из p0 в p1: сечение 2hw × 2ht."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    ln = d.length
    d.normalize()
    up = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    yv = up.cross(d).normalized()
    zv = d.cross(yv)
    m = Matrix((d, yv, zv)).transposed().to_4x4()
    m.translation = p0
    bm = bmesh.new()
    bm_box(bm, 0, ln, -hw, hw, -ht, ht)
    return obj_from_bm(name, bm, coll, root, [mat], bevel=bevel, matrix=m)


def build_side_wheel(P, coll, root, M, side):
    """Большое боковое колесо: лежит плашмя (ось вертикальная), ободом жмёт боковину лезвия."""
    r = P["rs"]
    z0, z1 = P["zs"]
    cx = side * (K.RAIL_HALF_W + r)
    mt = Matrix.Translation((cx, 0, 0))
    c = 0.018
    bm = bmesh.new()
    ri = r * 0.7
    lathe(bm, [(ri, z0), (r - c, z0), (r, z0 + c), (r, z1 - c), (r - c, z1), (ri, z1)])
    obj_from_bm("srim%+d" % side, bm, coll, root, [M["rim"]], bevel=0.004, matrix=mt)
    bm = bmesh.new()
    disc(bm, ri + 0.004, z0 + 0.012, z1 - 0.012)                  # сплошной диск, верх чуть утоплен
    obj_from_bm("sweb%+d" % side, bm, coll, root, [M["web"]], bevel=0.0, matrix=mt)
    bm = bmesh.new()
    lathe(bm, [(0.0, z0 + 0.006), (0.06, z0 + 0.006), (0.06, z1 + 0.012), (0.04, z1 + 0.03), (0.0, z1 + 0.03)],
          8, math.pi / 8)
    obj_from_bm("shub%+d" % side, bm, coll, root, [M["brass"]], bevel=0.004, matrix=mt)
    # вертикальная ось и вилка-кронштейн: от оси вверх-внутрь в киль корпуса
    zk = P["zb"] + 0.03
    xk = keel_halfwidth(P, zk) - 0.02
    top = Vector((cx, 0, z1 + 0.06))
    bm = bmesh.new()
    disc(bm, 0.026, z1, z1 + 0.075, 8, math.pi / 8)
    obj_from_bm("saxle%+d" % side, bm, coll, root, [M["steel2"]], bevel=0.0, matrix=mt)
    for sy in (1, -1):                                             # две щеки вилки по ходу
        bar("sfork%+d%+d" % (side, sy), (cx, sy * 0.05, z1 + 0.06), (side * xk, sy * 0.09, zk),
            0.022, 0.022, coll, root, M["steel2"])
    bm = bmesh.new()
    bm_box(bm, -0.05, 0.05, -0.075, 0.075, -0.018, 0.018)
    obj_from_bm("scap%+d" % side, bm, coll, root, [M["steel2"]], bevel=0.006, matrix=Matrix.Translation(top))
    bm = bmesh.new()
    disc(bm, 0.03, 0.0, 0.016, 6, 0)
    obj_from_bm("snut%+d" % side, bm, coll, root, [M["orange"]], bevel=0.003,
                matrix=Matrix.Translation(top + Vector((0, 0, 0.016))))


def build_top_wheel(P, coll, root, M, sy):
    """Малое верхнее колесо-барабан: ось поперёк, катится по верху лезвия и прижимает его вниз.
    Сидит под корпусом и проглядывает из-под скошенного борта."""
    r, h = P["rt"], P["ht"]
    zc = K.RAIL_TOP_Z + r
    y = sy * P["yt"]
    ry = Matrix.Translation((0, y, zc)) @ Matrix.Rotation(math.pi / 2, 4, 'Y')
    bm = bmesh.new()
    lathe(bm, [(0.0, -h), (r - 0.012, -h), (r, -h + 0.012), (r, h - 0.012), (r - 0.012, h), (0.0, h)], 12)
    obj_from_bm("twheel%+d" % sy, bm, coll, root, [M["rim"]], bevel=0.003, matrix=ry)
    for s in (1, -1):
        bm = bmesh.new()
        disc(bm, 0.036, 0.0, 0.016, 8, math.pi / 8)
        obj_from_bm("thub%+d%+d" % (sy, s), bm, coll, root, [M["brass"]], bevel=0.003,
                    matrix=Matrix.Translation((s * h, y, zc)) @ Matrix.Rotation(s * math.pi / 2, 4, 'Y'))
        # щека вилки вверх в корпус
        bar("tfork%+d%+d" % (sy, s), (s * (h + 0.026), y, zc), (s * (h + 0.026), y, zc + 0.1),
            0.03, 0.012, coll, root, M["steel2"])


def cut_grips(P, body, coll, root, M):
    """Две поперечные выемки на крыше под пальцы док-руки, в каждой — латунная скоба-ручка."""
    # коллекция исключена из вью-лейера — на время булевой операции включаем, иначе depsgraph её не считает
    lc = next(c for c in bpy.context.view_layer.layer_collection.children if c.collection == coll)
    lc.exclude = False
    for sy in (1, -1):
        yc = sy * P["grip_y"]
        bm = bmesh.new()
        bm_box(bm, -0.5, 0.5, yc - P["grip_w"] / 2, yc + P["grip_w"] / 2, P["grip_z"], 1.0)
        K.bool_cut(body, obj_from_bm("gripcut%+d" % sy, bm, coll, root, [M["steel"]], bevel=0.0))
        bm = bmesh.new()
        disc(bm, 0.018, -0.16, 0.16, 8, math.pi / 8)
        obj_from_bm("grip%+d" % sy, bm, coll, root, [M["brass"]], bevel=0.0,
                    matrix=Matrix.Translation((0, yc, P["grip_z"] + 0.04)) @ Matrix.Rotation(math.pi / 2, 4, 'Y'))
    lc.exclude = True


def build_variant(key, title, P, M):
    coll = K.collection("CART_%s" % key, exclude=True)
    root = K.empty("root_%s" % key, coll)
    body, _ = build_body(P, coll, root, M)
    cut_grips(P, body, coll, root, M)
    if P.get("bump"):
        build_bumpers(P, coll, root, M)
    for side in (1, -1):
        build_side_wheel(P, coll, root, M, side)
        build_top_wheel(P, coll, root, M, side)
    return coll


def report(P):
    print("  side wheels D %.2f, outer x = %.3f; top wheels D %.2f at y = ±%.3f, top z = %.3f; keel bottom z = %.3f"
          % (2 * P["rs"], K.RAIL_HALF_W + 2 * P["rs"], 2 * P["rt"], P["yt"], K.RAIL_TOP_Z + 2 * P["rt"], P["zb"]))


def main():
    K.reset_scene()
    M = mats()
    for m in M.values():
        m.use_fake_user = True                   # материалы болванки рельса нужны рендеру
    for key, title, P in VARIANTS:
        print(key, title)
        report(P)
        build_variant(key, title, P, M)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    print("saved", BLEND)


main()
