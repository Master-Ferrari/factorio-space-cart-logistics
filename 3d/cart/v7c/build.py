# -*- coding: utf-8 -*-
"""Блокинг каретки v7c «Прищепка»: корпус v5b разрезан вдоль конька на две створки на шарнире,
каждая несёт своё колесо ±45°; пружина в V-щели конька разжимает верх → колёса снизу жмут боковины лезвия.
Док-рука, сжимая створки за выемки на крыше, раскрывает прищепку.

Запуск:  blender -b --factory-startup --python build.py
Пишет cart_v7c.blend: коллекции CART_<K> (исключены из вью-лейера, корень — пустышка в 0).

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

BLEND = os.path.join(HERE, "cart_v7c.blend")
NSEG = 24


# ── материалы (Workbench берёт diffuse_color) ──────────────────────
def mats():
    return dict(
        steel=K.material("v7c_steel", (0.105, 0.108, 0.115), 0.5, 0.6),       # тёмная сталь ящика
        steel2=K.material("v7c_steel2", (0.24, 0.245, 0.255), 0.45, 0.7),     # светлее: утопленные панели
        rim=K.material("v7c_rim", (0.55, 0.58, 0.62), 0.25, 1.0),             # хром обода (как лезвия)
        web=K.material("v7c_web", (0.05, 0.05, 0.055), 0.6, 0.4),             # тёмный диск колеса
        brass=K.material("v7c_brass", (0.50, 0.32, 0.08), 0.35, 1.0),         # втулки
        beige=K.material("v7c_beige", (0.56, 0.50, 0.40), 0.6, 0.0),          # как ложементы рельса
        orange=K.material("v7c_orange", (0.85, 0.32, 0.02), 0.5, 0.0),        # акцент
        # болванка рельса
        base=K.material("v7c_ref_base", (0.05, 0.05, 0.055), 0.7, 0.3),
        bed=K.material("v7c_ref_bed", (0.56, 0.50, 0.40), 0.6, 0.0),
        blade=K.material("v7c_ref_blade", (0.62, 0.65, 0.70), 0.2, 1.0),
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
    cx, cz = K.RAIL_HALF_W, K.RAIL_TOP_Z - P.get("drop", 0.0)   # касание — на боковине, ниже верха лезвия
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
    # две створки: разрез по x = 0 и V-щель в коньке выше шарнира
    tb = P["cleft"]
    for s in (1, -1):
        h = bm.copy()
        cut(h, (s * 0.004, 0, 0), (-s, 0, 0))
        cut(h, (s * 0.004, 0, P["zh"]), (-s, 0, tb))
        obj_from_bm("shell%+d" % s, h, coll, root, [M["steel"], M["steel2"], M["beige"]], bevel=0.008)
    bm.free()
    body = None
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
        bm = bmesh.new()
        bm_box(bm, -0.03, 0.03, -0.016, 0.016, -0.014, 0.01)
        obj_from_bm("lock%+d" % s, bm, coll, root, [M["brass"]], bevel=0.003, matrix=rot)
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


# ── колесо ──────────────────────────────────────────────────────────
def wheel_matrix(P, side):
    """Мировая (в каретке) матрица колеса: локальные x — ход, y — вверх по колесу, z — наружу."""
    cx, cz, m, nin = frame(P)
    s = side
    e1 = Vector((0, s, 0))
    mm = Vector((s * m[0], 0, m[1]))
    nz = e1.cross(mm)                            # наружу-вниз
    contact = Vector((s * cx, 0, cz))
    c = contact + mm * P["r"]
    M3 = Matrix((e1, mm, nz)).transposed()
    M4 = M3.to_4x4()
    M4.translation = c
    return M4


def build_wheel(P, coll, root, M, side):
    r, t = P["r"], P["t"]
    ri = r * 0.72
    mt = wheel_matrix(P, side)
    # обод: внутренняя грань (z = 0) проходит через угол лезвия; фаска по внешней кромке
    bm = bmesh.new()
    c = 0.022
    lathe(bm, [(ri, 0.0), (r, 0.0), (r, t - c), (r - c, t), (ri, t)])
    obj_from_bm("rim%+d" % side, bm, coll, root, [M["rim"]], bevel=0.005, matrix=mt)
    # диск утоплен к наружной стороне
    bm = bmesh.new()
    disc(bm, ri + 0.004, t * 0.45, t * 0.8)
    obj_from_bm("web%+d" % side, bm, coll, root, [M["steel"]], bevel=0.0, matrix=mt)
    # спиц нет: колесо — сплошной диск
    # ступица — латунный октагон почти заподлицо с внутренней гранью; тонкая ось уходит в киль
    bm = bmesh.new()
    disc(bm, 0.058, -0.012, t + 0.012, 8, math.pi / 8)      # насквозь: видна и снаружи
    obj_from_bm("hub%+d" % side, bm, coll, root, [M["brass"]], bevel=0.006, matrix=mt)
    bm = bmesh.new()
    disc(bm, 0.026, -P["gap"] - 0.02, 0.0, 8, math.pi / 8)
    obj_from_bm("axle%+d" % side, bm, coll, root, [M["steel"]], bevel=0.0, matrix=mt)
    bm = bmesh.new()
    disc(bm, 0.03, -0.02, -0.008, 8, math.pi / 8)
    obj_from_bm("hubcap%+d" % side, bm, coll, root, [M["orange"]], bevel=0.0, matrix=mt)


def build_clothespin(P, coll, root, M, w):
    """Шарнир створок, пружины в щели конька и выемки под пальцы док-руки."""
    L2 = P["L"] / 2
    zh, tb = P["zh"], P["cleft"]
    # шарнир: толстый латунный палец вдоль хода, торчит из торцов (видно на курсе N-S)
    bm = bmesh.new()
    disc(bm, 0.034, -L2 - 0.03, L2 + 0.03, 8, math.pi / 8)
    obj_from_bm("hinge", bm, coll, root, [M["brass"]], bevel=0.005,
                matrix=Matrix.Translation((0, 0, zh)) @ Matrix.Rotation(-math.pi / 2, 4, 'X'))
    # пружины-стаканы поперёк щели (оранжевые: «вот что разжимает»)
    zs = P["z3"] - 0.06
    half = 0.004 + (zs - zh) * tb
    for sy in (1, -1):
        bm = bmesh.new()
        disc(bm, 0.04, -half - 0.03, half + 0.03, 8, math.pi / 8)
        mt = Matrix.Translation((0, sy * 0.19, zs)) @ Matrix.Rotation(math.pi / 2, 4, 'Y')
        obj_from_bm("spring%+d" % sy, bm, coll, root, [M["orange"]], bevel=0.006, matrix=mt)
        for k in (-1, 1):                                    # латунные тарелки пружины
            bm = bmesh.new()
            disc(bm, 0.05, k * half - 0.008, k * half + 0.008, 8, math.pi / 8)
            obj_from_bm("spcup%+d%+d" % (sy, k), bm, coll, root, [M["brass"]], bevel=0.003, matrix=mt)
    # выемки под пальцы: тёмные карманы вдоль конька на каждой створке
    zt = P["z3"]
    for s in (1, -1):
        bm = bmesh.new()
        x0 = 0.004 + (zt - zh) * tb + 0.008
        bm_box(bm, x0, x0 + 0.042, -0.12, 0.12, zt - 0.045, zt + 0.002)
        if s < 0:
            bmesh.ops.scale(bm, vec=(-1, 1, 1), verts=bm.verts)
        bmesh.ops.reverse_faces(bm, faces=bm.faces) if s < 0 else None
        obj_from_bm("grip%+d" % s, bm, coll, root, [M["web"]], bevel=0.0)


def build_variant(key, title, P, M):
    coll = K.collection("CART_%s" % key, exclude=True)
    root = K.empty("root_%s" % key, coll)
    _, w = build_body(P, coll, root, M)
    build_clothespin(P, coll, root, M, w)
    if P.get("bump"):
        build_bumpers(P, coll, root, M)
    for side in (1, -1):
        build_wheel(P, coll, root, M, side)
    return coll


def report(P):
    cx, cz, m, nin = frame(P)
    r, t = P["r"], P["t"]
    top = (cx + 2 * r * m[0], cz + 2 * r * m[1])
    print("  wheel top (x, z) = (%.3f, %.3f); outer reach x = %.3f; band half-width = %.3f; keel bottom half-width = %.3f"
          % (top[0], top[1], top[0] + t * m[1], keel_halfwidth(P, P["z1"]), keel_halfwidth(P, P["zb"])))


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
