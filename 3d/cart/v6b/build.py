# -*- coding: utf-8 -*-
"""Блокинг каретки v6b: два больших колеса развалом V на лезвии + гранёный ящик в развале.

Запуск:  blender -b --factory-startup --python build.py
Пишет cart_v6b.blend: коллекции CART_<K> (исключены из вью-лейера, корень — пустышка в 0).

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
from params import VARIANTS, TONG  # noqa: E402

BLEND = os.path.join(HERE, "cart_v6b.blend")
NSEG = 24


# ── материалы (Workbench берёт diffuse_color) ──────────────────────
def mats():
    return dict(
        steel=K.material("v6b_steel", (0.105, 0.108, 0.115), 0.5, 0.6),       # тёмная сталь ящика
        steel2=K.material("v6b_steel2", (0.24, 0.245, 0.255), 0.45, 0.7),     # светлее: утопленные панели
        rim=K.material("v6b_rim", (0.55, 0.58, 0.62), 0.25, 1.0),             # хром обода (как лезвия)
        web=K.material("v6b_web", (0.05, 0.05, 0.055), 0.6, 0.4),             # тёмный диск колеса
        brass=K.material("v6b_brass", (0.50, 0.32, 0.08), 0.35, 1.0),         # втулки
        beige=K.material("v6b_beige", (0.56, 0.50, 0.40), 0.6, 0.0),          # как ложементы рельса
        orange=K.material("v6b_orange", (0.85, 0.32, 0.02), 0.5, 0.0),        # акцент
        # болванка рельса
        base=K.material("v6b_ref_base", (0.05, 0.05, 0.055), 0.7, 0.3),
        bed=K.material("v6b_ref_bed", (0.56, 0.50, 0.40), 0.6, 0.0),
        blade=K.material("v6b_ref_blade", (0.62, 0.65, 0.70), 0.2, 1.0),
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


def bar(name, p0, p1, hw, ht, coll, root, mat, bevel=0.004, ext=0.0):
    """Брус из p0 в p1 (мировые точки в каретке): сечение hw по Y × ht в плоскости XZ."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    ln = d.length
    d.normalize()
    yv = Vector((0, 1, 0))
    if abs(d.dot(yv)) > 0.99:
        yv = Vector((1, 0, 0))
    zv = d.cross(yv).normalized()
    yv = zv.cross(d)
    m = Matrix((d, yv, zv)).transposed().to_4x4()
    m.translation = p0
    bm = bmesh.new()
    bm_box(bm, -ext, ln + ext, -hw, hw, -ht, ht)
    return obj_from_bm(name, bm, coll, root, [mat], bevel=bevel, matrix=m)


def build_wheel(P, coll, root, M, side):
    """Колесо-диск: обод, сплошной диск, крупная латунная ступица, ось насквозь с гайкой."""
    r, t = P["r"], P["t"]
    ri = r * 0.74
    mt = wheel_matrix(P, side)
    bm = bmesh.new()
    c = 0.022
    lathe(bm, [(ri, 0.0), (r, 0.0), (r, t - c), (r - c, t), (ri, t)])
    obj_from_bm("rim%+d" % side, bm, coll, root, [M["rim"]], bevel=0.005, matrix=mt)
    # сплошной диск, утоплен к наружной стороне
    bm = bmesh.new()
    disc(bm, ri + 0.004, t * 0.3, t * 0.72)
    obj_from_bm("web%+d" % side, bm, coll, root, [M["steel2"]], bevel=0.0, matrix=mt)
    # ступица: крупный латунный октагон с фаской наружу
    bm = bmesh.new()
    lathe(bm, [(0.0, -0.01), (0.075, -0.01), (0.075, t * 0.75), (0.05, t + 0.012), (0.0, t + 0.012)], 8, math.pi / 8)
    obj_from_bm("hub%+d" % side, bm, coll, root, [M["brass"]], bevel=0.004, matrix=mt)
    # ось: изнутри уходит во втулку киля, снаружи — сквозь щеку вилки, с гайкой
    bm = bmesh.new()
    disc(bm, 0.024, -P["gap"] - 0.03, t + 0.075, 8, math.pi / 8)
    obj_from_bm("axle%+d" % side, bm, coll, root, [M["rim"]], bevel=0.0, matrix=mt)
    bm = bmesh.new()
    disc(bm, 0.044, t + 0.045, t + 0.066, 6, 0)
    obj_from_bm("nut%+d" % side, bm, coll, root, [M["orange"]], bevel=0.003, matrix=mt)


def build_tongs(P, coll, root, M):
    """Клещи удержания на обоих торцах: ножницы, губы-ролики с вертикальной осью жмут бока лезвия.
    Рукояти тянутся тягами к серьге на торце: любая сила «оторвать каретку» тянет серьгу от рельса
    и сильнее сводит губы (самозатягивание, как у ледовых щипцов). Пружина даёт преднатяг."""
    T = TONG
    rx = Matrix.Rotation(math.pi / 2, 4, 'Y')
    ry = Matrix.Rotation(math.pi / 2, 4, 'X')
    for sy in (1, -1):
        y = sy * T["ty"]
        for s in (1, -1):                       # s — сторона губы
            yl = y + s * 0.017                 # два плеча в разных слоях ножниц
            jaw = Vector((s * (K.RAIL_HALF_W + T["rr"]), yl, sum(T["rz"]) / 2))
            knee = Vector((s * T["knee"][0], yl, T["knee"][1]))
            piv = Vector((T["pivot"][0], yl, T["pivot"][1]))
            hnd = Vector((-s * T["handle"][0], yl, T["handle"][1]))
            ring = Vector((T["ring"][0], y, T["ring"][1]))
            tag = "%+d%+d" % (sy, s)
            jt = Vector((jaw.x + s * 0.01, yl, T["rz"][1] + 0.012))
            for i, (a, b) in enumerate(((jt, knee), (knee, piv), (piv, hnd))):
                bar("tong%d%s" % (i, tag), a, b, 0.02, 0.022, coll, root, M["brass"], ext=0.012)
            # губа-ролик: ось вертикальная, катится по боку лезвия
            bm = bmesh.new()
            disc(bm, T["rr"], T["rz"][0], T["rz"][1], 8, math.pi / 8)
            obj_from_bm("jaw" + tag, bm, coll, root, [M["rim"]], bevel=0.004,
                        matrix=Matrix.Translation((jaw.x, yl, 0)))
            bm = bmesh.new()
            disc(bm, 0.012, T["rz"][1], T["rz"][1] + 0.024, 6, 0)
            obj_from_bm("jawpin" + tag, bm, coll, root, [M["steel"]], bevel=0.0,
                        matrix=Matrix.Translation((jaw.x, yl, 0)))
            # тяга рукоять → серьга
            bar("link" + tag, hnd, ring, 0.01, 0.01, coll, root, M["steel2"], ext=0.01)
        # шарнир ножниц
        bm = bmesh.new()
        disc(bm, 0.026, -0.04, 0.04, 8, math.pi / 8)
        obj_from_bm("pivot%+d" % sy, bm, coll, root, [M["orange"]], bevel=0.004,
                    matrix=Matrix.Translation((T["pivot"][0], y, T["pivot"][1])) @ ry)
        # серьга на кронштейне торца
        bm = bmesh.new()
        disc(bm, 0.028, -0.025, 0.025, 8, math.pi / 8)
        obj_from_bm("ring%+d" % sy, bm, coll, root, [M["orange"]], bevel=0.004,
                    matrix=Matrix.Translation((0, y, T["ring"][1])) @ ry)
        bar("lug%+d" % sy, (0, y, T["ring"][1]), (0, sy * (P["L"] / 2 - 0.04), T["ring"][1] + 0.01),
            0.03, 0.022, coll, root, M["steel2"], ext=0.0)
        # пружина преднатяга между рукоятями
        zh = T["handle"][1] - 0.02
        xh = T["handle"][0] - 0.02
        bm = bmesh.new()
        disc(bm, 0.008, -xh, xh, 6, 0)
        obj_from_bm("sprod%+d" % sy, bm, coll, root, [M["rim"]], bevel=0.0,
                    matrix=Matrix.Translation((0, y + sy * 0.03, zh)) @ rx)
        for i in range(5):
            bm = bmesh.new()
            disc(bm, 0.018, -0.005, 0.005, 8, math.pi / 8)
            obj_from_bm("coil%+d_%d" % (sy, i), bm, coll, root, [M["rim"]], bevel=0.0,
                        matrix=Matrix.Translation((-0.06 + 0.03 * i, y + sy * 0.03, zh)) @ rx)


def cut_grips(P, body, coll, root, M):
    """Две поперечные выемки на крыше под пальцы док-руки, в каждой — хромовая скоба-ручка."""
    # коллекция исключена из вью-лейера — на время булевой операции включаем, иначе depsgraph её не считает
    lc = next(c for c in bpy.context.view_layer.layer_collection.children if c.collection == coll)
    lc.exclude = False
    for sy in (1, -1):
        yc = sy * P["grip_y"]
        bm = bmesh.new()
        bm_box(bm, -0.5, 0.5, yc - P["grip_w"] / 2, yc + P["grip_w"] / 2, P["grip_z"], 1.0)
        cutter = obj_from_bm("gripcut%+d" % sy, bm, coll, root, [M["steel"]], bevel=0.0)
        K.bool_cut(body, cutter)
        bm = bmesh.new()
        disc(bm, 0.017, -0.16, 0.16, 8, math.pi / 8)
        obj_from_bm("grip%+d" % sy, bm, coll, root, [M["brass"]], bevel=0.0,
                    matrix=Matrix.Translation((0, yc, P["grip_z"] + 0.04)) @ Matrix.Rotation(math.pi / 2, 4, 'Y'))
    lc.exclude = True


def build_hoops(P, coll, root, M):
    """Две рамы-обруча вокруг ящика: несут втулки осей, ящик висит в них."""
    cx, cz, m, nin = frame(P)
    w = keel_halfwidth(P, P["z1"])
    d = 0.016
    for sy in (1, -1):
        y0, y1 = (0.25, 0.30) if sy > 0 else (-0.30, -0.25)
        bm = bmesh.new()
        bm_box(bm, -w - d, w + d, y0, y1, P["zb"] - d, P["z3"] + d)
        for s in (1, -1):
            co = (s * (cx + (P["gap"] - d * 0.6) * nin[0]), 0, cz + (P["gap"] - d * 0.6) * nin[1])
            cut(bm, co, (s * -nin[0], 0, -nin[1]))
        for s in (1, -1):
            n = Vector((s * (P["z3"] - P["z2"]), 0, w - P["wt"])).normalized()
            cut(bm, Vector((s * w, 0, P["z2"])) + n * d, n)
        obj_from_bm("hoop%+d" % sy, bm, coll, root, [M["steel2"]], bevel=0.005)


def build_variant(key, title, P, M):
    coll = K.collection("CART_%s" % key, exclude=True)
    root = K.empty("root_%s" % key, coll)
    body, _ = build_body(P, coll, root, M)
    cut_grips(P, body, coll, root, M)
    if P.get("bump"):
        build_bumpers(P, coll, root, M)
    build_hoops(P, coll, root, M)
    for side in (1, -1):
        build_wheel(P, coll, root, M, side)
    build_tongs(P, coll, root, M)
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
