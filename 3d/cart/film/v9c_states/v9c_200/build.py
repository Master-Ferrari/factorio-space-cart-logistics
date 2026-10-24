# -*- coding: utf-8 -*-
"""Блокинг каретки v9c «Тележка-прищепка» (от v8c): целый гранёный ящик-шатёр с квадратной верхней площадкой;
по бокам прямоугольные щёки-боковины, как у ж/д тележек, с накладками на выступах; колесо на щеке;
щека качается на крупном кулачном шарнире, ось которого лежит в плоскости щеки и проходит через ступицу колеса; винтовые пружины (геометрия из v8a)
вдоль оси колеса (по одной на щёку) распирают верх щеки, утопленные в карманы в скатах ящика и упёртые в их дно → колёса конической кромкой жмут боковины лезвия."""

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

BLEND = os.path.join(HERE, "cart_v9c.blend")
NSEG = 24


# ── материалы (Workbench берёт diffuse_color) ──────────────────────
def mats():
    return dict(
        steel=K.material("v9c_steel", (0.105, 0.108, 0.115), 0.5, 0.6),       # тёмная сталь ящика
        steel2=K.material("v9c_steel2", (0.24, 0.245, 0.255), 0.45, 0.7),     # светлее: утопленные панели
        rim=K.material("v9c_rim", (0.55, 0.58, 0.62), 0.25, 1.0),             # хром обода (как лезвия)
        web=K.material("v9c_web", (0.05, 0.05, 0.055), 0.6, 0.4),             # тёмный диск колеса
        brass=K.material("v9c_brass", (0.50, 0.32, 0.08), 0.35, 1.0),         # втулки
        beige=K.material("v9c_beige", (0.56, 0.50, 0.40), 0.6, 0.0),          # как ложементы рельса
        orange=K.material("v9c_orange", (0.85, 0.32, 0.02), 0.5, 0.0),        # акцент
        # болванка рельса
        base=K.material("v9c_ref_base", (0.05, 0.05, 0.055), 0.7, 0.3),
        bed=K.material("v9c_ref_bed", (0.56, 0.50, 0.40), 0.6, 0.0),
        blade=K.material("v9c_ref_blade", (0.62, 0.65, 0.70), 0.2, 1.0),
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
    # опорная точка колеса = угол обода без фаски; рабочая (вертикальная) грань фаски — ровно на боковине лезвия
    cx = K.RAIL_HALF_W - 0.7071 * P.get("rim_cc", 0.0)
    cz = K.RAIL_TOP_Z - P.get("drop", 0.0)
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
    w = P["ws"]
    L2 = P["L"] / 2
    bm = bmesh.new()
    bm_box(bm, -w, w, -L2, L2, P["zb"], P["z3"])
    # сечение «гробиком»: нижние грани (xb, zb) → (ws, z2s), скаты (ws, z2s) → (wt, z3); пружины их
    # пересекают — там выемки (build_mechanism)
    for s in (1, -1):
        cut(bm, (s * P["xb"], 0, P["zb"]), (s * (P["z2s"] - P["zb"]), 0, -(P["ws"] - P["xb"])))
        cut(bm, (s * P["ws"], 0, P["z2s"]), (s * (P["z3"] - P["z2s"]), 0, P["ws"] - P["wt"]))
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
    # квадратная площадка — утопленная панель; скаты поперёк — утопленные «фасады»
    top = max(faces_by_normal(bm, (0, 0, 1)), key=lambda f: f.calc_center_median().z)
    recess(bm, top, 0.016, 0.012, 3)                  # тёмное дно под рёбрами крыши (как стальной ящик)
    bm.normal_update()
    for s in (1, -1):
        nx = Vector((s * (P["z3"] - P["z2s"]), 0, P["ws"] - P["wt"])).normalized()
        fs = faces_by_normal(bm, nx, 0.05)
        if fs:
            recess(bm, max(fs, key=lambda f: f.calc_area()), 0.02, 0.01, 1)
            bm.normal_update()
    body = obj_from_bm("body", bm, coll, root, [M["steel"], M["steel2"], M["beige"], M["web"]], bevel=0.008)
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
    cc = P["rim_cc"]
    lathe(bm, [(ri, 0.0), (r - cc, 0.0), (r, cc), (r, t - c), (r - c, t), (ri, t)])   # внутр. кромка — конус 45°
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
    disc(bm, 0.03, P["ck0"] - 0.006, 0.0, 8, math.pi / 8)   # ось — в щеку, не в ящик
    obj_from_bm("axle%+d" % side, bm, coll, root, [M["steel"]], bevel=0.0, matrix=mt)
    bm = bmesh.new()
    disc(bm, 0.03, -0.02, -0.008, 8, math.pi / 8)
    obj_from_bm("hubcap%+d" % side, bm, coll, root, [M["orange"]], bevel=0.0, matrix=mt)


def helix(bm, R, wire, turns, h, n_per=8):
    """Крупная винтовая пружина (как в v8a): квадратное сечение wire по винту радиуса R, высота h (ось Z)."""
    N = int(turns * n_per)
    pitch = (h - wire) / turns
    secs = []
    for i in range(N + 1):
        a = 2 * math.pi * i / n_per
        c, s_ = math.cos(a), math.sin(a)
        z = wire / 2 + pitch * i / n_per
        sec = []
        for dr, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            rr = R + dr * wire / 2
            sec.append(bm.verts.new((rr * c, rr * s_, z + dz * wire / 2)))
        secs.append(sec)
    for i in range(N):
        a_, b_ = secs[i], secs[i + 1]
        for k in range(4):
            j = (k + 1) % 4
            bm.faces.new((a_[k], a_[j], b_[j], b_[k]))
    bm.faces.new(secs[0][::-1])
    bm.faces.new(secs[-1])


def build_cheek(P, coll, root, M, side):
    """Щека-боковина с внутренней стороны колеса: низ срезан по оси ступицы, над колесом — горб по дуге обода,
    по сторонам — крылья до торцов со скошенными углами; накладки на крыльях."""
    mt = wheel_matrix(P, side)
    X, yb, yw = P["ck_x"], P["ck_yb"], P["ck_yw"]
    c1, c2, Rh = P["ck_c1"], P["ck_c2"], P["ck_yt"]
    z0, z1 = P["ck0"], P["ck1"]
    # горб над колесом — ломаный, «ножницами»: плечо от крыла (xs, yw) к плоскому верху (xt, Rh)
    xs, xt = P["ck_xs"], P["ck_xt"]
    prof = [(-X + c1, yb), (X - c1, yb), (X, yb + c1), (X, yw - c2), (X - c2, yw),
            (xs, yw), (xt, Rh), (-xt, Rh), (-xs, yw)]
    prof += [(-X + c2, yw), (-X, yw - c2), (-X, yb + c1)]
    bm = bmesh.new()
    A = [bm.verts.new((x, y, z0)) for x, y in prof]
    B = [bm.verts.new((x, y, z1)) for x, y in prof]
    bm.faces.new(A[::-1])
    bm.faces.new(B)
    k = len(prof)
    for i in range(k):
        j = (i + 1) % k
        bm.faces.new((A[i], A[j], B[j], B[i]))
    obj_from_bm("cheek%+d" % side, bm, coll, root, [M["steel2"]], bevel=0.005, matrix=mt)
    # накладки на крыльях за контуром колеса: бежевая табличка + оранжевая полоса, на обеих сторонах щеки
    for sx in (1, -1):
        xa_, xb_ = (0.30, 0.37) if sx > 0 else (-0.37, -0.30)
        for za, zb in ((z0 - 0.008, z0 + 0.002), (z1 - 0.002, z1 + 0.008)):
            bm = bmesh.new()
            bm_box(bm, xa_, xb_, yb + 0.035, 0.045, za, zb)
            obj_from_bm("plate%+d%+d" % (side, sx), bm, coll, root, [M["beige"]], bevel=0.003, matrix=mt)
            bm = bmesh.new()
            bm_box(bm, xa_, xb_, 0.058, 0.08, za, zb)
            obj_from_bm("stripe%+d%+d" % (side, sx), bm, coll, root, [M["orange"]], bevel=0.0, matrix=mt)


def grip_cutter(P, sy):
    """Резак выемки под захват: профиль (y, z) — потолок, задняя стенка, скругление в дно; выдавлен поперёк
    и обрезан с боков плоскостями стенок базы, сдвинутыми внутрь на grip_m (боковины выемки им параллельны)."""
    m, gy, z0, rf = P["grip_m"], P["grip_y"], P["grip_z0"], P["grip_rf"]
    # потолок: отступ m от верхнего ребра, отмеренный по скату торца
    a = math.atan2(P["z3"] - P["z2"], P["L"] / 2 - P["lt"])
    z1 = P["z3"] - m * math.sin(a)
    # наружная нижняя кромка (дно ∩ торцевой скат) скруглена радиусом rf: дуга от дна к скату
    L2 = P["L"] / 2
    d = Vector((L2 - P["lt"], -(P["z3"] - P["z2"]))).normalized()      # вдоль ската вниз-наружу
    no = Vector((-d.y, d.x))                                             # наружная нормаль ската
    if no.y < 0:
        no = -no
    ys = lambda z: L2 + (P["z2"] - z) * (L2 - P["lt"]) / (P["z3"] - P["z2"])  # скат: y(z)
    # центр дуги: на rf ниже дна и на rf внутрь от ската
    cz = z0 - rf
    # точка на прямой z = cz, отстоящая от ската на rf внутрь: сдвиг по y на rf / cos(угла нормали к y)
    cy = ys(cz) - rf / no.x
    t1 = (cy, z0)                                                        # касание дна
    t2 = (cy + rf * no.x, cz + rf * no.y)                                # касание ската
    a1, a2 = math.pi / 2, math.atan2(no.y, no.x)
    n = P["grip_seg"]
    prof = [(gy, z1), (0.8, z1), (0.8, t2[1])]
    arc = [(cy + rf * math.cos(a1 + (a2 - a1) * i / n), cz + rf * math.sin(a1 + (a2 - a1) * i / n)) for i in range(n + 1)]
    prof += arc[::-1]
    prof.append((gy, z0))
    bm = bmesh.new()
    X = 0.6
    A = [bm.verts.new((-X, sy * y, z)) for y, z in prof]
    B = [bm.verts.new((X, sy * y, z)) for y, z in prof]
    k = len(prof)
    bm.faces.new(A)
    bm.faces.new(B[::-1])
    for i in range(k):
        j = (i + 1) % k
        bm.faces.new((A[i], A[j], B[j], B[i]))
    # контур выреза на грани — многоугольник: ровный низ, боковины сходятся книзу, верхние углы срезаны фасками
    pts = P["grip_poly"]
    for s in (1, -1):
        for (x0, za), (x1, zc) in zip(pts[:-1], pts[1:]):
            nv = Vector((s * (zc - za), 0, -(x1 - x0))).normalized()
            cut(bm, (s * x0, 0, za), nv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def build_mechanism(P, coll, root, M):
    """Кулачный шарнир щеки (главный акцент), винтовые пружины вдоль оси колеса, выемки под захват в плите."""
    r = P["r"]
    zm = (P["ck0"] + P["ck1"]) / 2                                   # ось шарнира — в средней плоскости щеки
    for s in (1, -1):
        wm = wheel_matrix(P, s)
        hy = P["hinge_y"] - r                                         # hinge_y = r → через ось колеса (ступицу)
        rot = Matrix.Rotation(math.pi / 2, 4, 'Y')                   # локальная z диска → ход
        # шарнир одним соосным узлом: сквозной палец + на каждом конце «латунь | оранжевый кулак | латунь»
        bm = bmesh.new()
        disc(bm, 0.03, -P["pin_x"] - 0.07, P["pin_x"] + 0.07, 8, math.pi / 8)
        obj_from_bm("hpin%+d" % s, bm, coll, root, [M["brass"]], bevel=0.004,
                    matrix=wm @ Matrix.Translation((0, hy, zm)) @ rot)
        R = P["knuckle_r"]
        for sx in (1, -1):
            c0 = sx * P["knuckle_x"]
            # узел короче: внутренняя проушина за ободом колеса (|x| > r), палец не длиннее буферов
            for nm, a, b_, mat in (("lugA", -0.07, -0.034, M["brass"]), ("knuckle", -0.03, 0.03, M["orange"]),
                                   ("lugB", 0.034, 0.07, M["brass"])):
                bm = bmesh.new()
                disc(bm, R, c0 + a, c0 + b_, 8, math.pi / 8)
                obj_from_bm("%s%+d%+d" % (nm, s, sx), bm, coll, root, [mat], bevel=0.006,
                            matrix=wm @ Matrix.Translation((0, hy, zm)) @ rot)
        # одна пружина на щёку, по центру хода: ось вдоль оси колеса, верхняя чашка — на дне кармана в скате ящика
        base = wm @ Matrix.Translation((0, P["spring_y"] - r, P["ck0"])) @ Matrix.Rotation(math.pi, 4, 'X')
        bm = bmesh.new()
        helix(bm, P["spring_R"], P["wire"], P["turns"], P["spring_h"])
        obj_from_bm("spring%+d" % s, bm, coll, root, [M["brass"]], bevel=0.0, matrix=base)
        for z0 in (0.0, P["spring_h"] - 0.012):
            bm = bmesh.new()
            disc(bm, P["spring_R"] + 0.01, z0, z0 + 0.016, 8, math.pi / 8)
            obj_from_bm("cup%+d_%d" % (s, int(z0 > 0)), bm, coll, root, [M["steel"]], bevel=0.003, matrix=base)
        top = base @ Vector((0, 0, P["spring_h"]))
        # карман: соосный пружине цилиндр с зазором, только там, где пружина входит в скат/киль ящика;
        # дно кармана — у верхнего торца пружины, в него упирается верхняя чашка (boolean, запекается в меш)
        body = next(o for o in coll.objects if o.name.startswith("body"))
        bm = bmesh.new()
        h = P["spring_h"]
        disc(bm, P["spring_R"] + P["pocket_gap"], -0.3, h + 0.006, 12, math.pi / 12)
        me = bpy.data.meshes.new("pocket%+d" % s)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(M["web"])                                  # стенки ниши — чёрные: тень кармана
        cutter = bpy.data.objects.new("pocket%+d" % s, me)
        coll.objects.link(cutter)
        cutter.matrix_world = base
        md = body.modifiers.new("pocket%+d" % s, 'BOOLEAN')
        md.operation = 'DIFFERENCE'
        md.object = cutter
        md.solver = 'EXACT'
        md.material_mode = 'TRANSFER'
        while body.modifiers[0].name != md.name:
            body.modifiers.move(body.modifiers.find(md.name), 0)
        print("  spring %+d top (%.3f, %.3f)" % (s, top.x, top.z))
        hp = wm @ Vector((0, hy, zm))
        print("  hinge %+d at (x %.3f, z %.3f)" % (s, hp.x, hp.z))
    # выемки под захват на торцевых скатах: горизонтальная щель под нависающей кромкой крыши
    body = next(o for o in coll.objects if o.name.startswith("body"))
    for sy in (1, -1):
        bm = grip_cutter(P, sy)
        me = bpy.data.meshes.new("pocket_grip%+d" % sy)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(M["web"])
        cutter = bpy.data.objects.new("pocket_grip%+d" % sy, me)
        coll.objects.link(cutter)
        md = body.modifiers.new("grip%+d" % sy, 'BOOLEAN')
        md.operation, md.object, md.solver, md.material_mode = 'DIFFERENCE', cutter, 'EXACT', 'TRANSFER'
    # запечь карманы в меш ящика и убрать резаки. Коллекция варианта исключена из слоя — депсграф её
    # не вычисляет, поэтому на время запекания включаем её; фаску снимаем и ставим заново поверх выемок
    body = next(o for o in coll.objects if o.name.startswith("body"))
    lc = next(c for c in bpy.context.view_layer.layer_collection.children if c.collection == coll)
    lc.exclude = False
    bev = [(m.width, m.angle_limit) for m in body.modifiers if m.type == 'BEVEL']
    for m in [m for m in body.modifiers if m.type == 'BEVEL']:
        body.modifiers.remove(m)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    newme = bpy.data.meshes.new_from_object(body.evaluated_get(dg))
    body.modifiers.clear()
    old = body.data
    body.data = newme
    bpy.data.meshes.remove(old)
    for o in [o for o in coll.objects if o.name.startswith("pocket")]:
        bpy.data.objects.remove(o, do_unlink=True)
    for w_, a_ in bev:
        md = body.modifiers.new("bevel", 'BEVEL')
        md.width, md.segments, md.limit_method, md.angle_limit = w_, 1, 'ANGLE', a_
    lc.exclude = True
    print("  body faces after pockets:", len(body.data.polygons))
    build_ribs(P, coll, root, M)
    build_decals(P, coll, root, M)


def build_decals(P, coll, root, M):
    """Торец: пара контактов-разъёмов сцепки на скате под выемкой (гильза + тёмное гнездо + латунный пин-полусфера)
    и полукруглый оранжевый бампер поперёк вертикального торца — им каретки касаются в поезде."""
    L2 = P["L"] / 2
    dy, dz = L2 - P["lt"], P["z3"] - P["z2"]
    ln = math.hypot(dy, dz)
    zc = P["pogo_z"]
    rr, rs, rp = P["pogo_r"], P["pogo_r"] * 0.66, P["pogo_r"] * 0.5
    for sy in (1, -1):
        v = Vector((0, -sy * dy / ln, dz / ln))                 # вверх по скату
        n = Vector((0, sy * dz / ln, dy / ln))                  # наружу
        for sx in (1, -1):
            o = Vector((sx * P["pogo_x"], sy * (L2 - (zc - P["z2"]) * dy / dz), zc))
            mt = Matrix((Vector((1, 0, 0)), v, n)).transposed().to_4x4()
            mt.translation = o
            bm = bmesh.new()
            disc(bm, rr, -0.004, 0.012, 12, 0)                 # гильза
            obj_from_bm("pogo%+d%+d" % (sy, sx), bm, coll, root, [M["beige"]], bevel=0.003, matrix=mt)
            bm = bmesh.new()
            disc(bm, rs, 0.010, 0.0135, 12, 0)                # тёмное гнездо
            obj_from_bm("pogos%+d%+d" % (sy, sx), bm, coll, root, [M["web"]], bevel=0.0, matrix=mt)
            bm = bmesh.new()                                   # пин-полусфера
            prof = [(1e-4, 0.010)] + [(rp * math.cos(a), 0.012 + rp * math.sin(a))
                                       for a in (0.0, math.pi / 6, math.pi / 3)] + [(1e-4, 0.012 + rp)]
            lathe(bm, prof, 12)
            obj_from_bm("pogop%+d%+d" % (sy, sx), bm, coll, root, [M["brass"]], bevel=0.0, matrix=mt)
        # бампер: самостоятельная труба-дуга в плане (центр на оси каретки), вынесена вперёд на центральной опоре
        # из такой же трубы; концы свободные, скруглены полусферами. Висит низко (bmp_z), где низ торца уходит назад.
        R, Rp, zb_ = P["bmp_r"], P["bmp_rp"], P["bmp_z"]
        yc = P["bmp_front"] - Rp
        Rc = Rp - R
        a1 = math.asin(P["bmp_xe"] / Rc)
        N, NS = 16, 12
        bm = bmesh.new()
        rings = []
        for k in range(N + 1):
            a = -a1 + 2 * a1 * k / N
            dx, dy_ = math.sin(a), math.cos(a)
            c = Vector((Rc * dx, sy * (yc + Rc * dy_), zb_))
            rdir = Vector((dx, sy * dy_, 0))
            rings.append([bm.verts.new(c + rdir * (R * math.cos(2 * math.pi * q / NS)) + Vector((0, 0, R * math.sin(2 * math.pi * q / NS))))
                          for q in range(NS)])
        for k in range(N):
            for q in range(NS):
                q2 = (q + 1) % NS
                bm.faces.new((rings[k][q], rings[k][q2], rings[k + 1][q2], rings[k + 1][q]))
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
        obj_from_bm("bumper%+d" % sy, bm, coll, root, [M["orange"]], bevel=0.0)
        for e in (-1, 1):                                    # полусферы-заглушки на концах дуги
            a = e * a1
            c = Vector((Rc * math.sin(a), sy * (yc + Rc * math.cos(a)), zb_))
            tng = Vector((e * math.cos(a), -sy * e * math.sin(a), 0)).normalized()   # наружу вдоль дуги
            up = Vector((0, 0, 1))
            side = tng.cross(up)
            mt = Matrix((side, tng.cross(side), tng)).transposed().to_4x4()
            mt.translation = c
            bm = bmesh.new()
            prof = [(1e-4, -0.002), (R, -0.002)] + [(R * math.cos(t), R * math.sin(t)) for t in (0.4, 0.8, 1.2)] + [(1e-4, R)]
            lathe(bm, prof, NS)
            obj_from_bm("bumpcap%+d%+d" % (sy, e), bm, coll, root, [M["orange"]], bevel=0.0, matrix=mt)
        # центральная опора — та же труба по оси каретки, от торца (внутри корпуса) до середины дуги
        ym = yc + Rc
        bm = bmesh.new()
        disc(bm, R, P["bmp_post0"], ym, NS, 0)
        mt = Matrix.Translation((0, 0, zb_)) @ Matrix.Rotation(-sy * math.pi / 2, 4, 'X')
        obj_from_bm("bumppost%+d" % sy, bm, coll, root, [M["steel2"]], bevel=0.003, matrix=mt)
    print("  bumper front |y| = %.3f, gap at 1-tile pitch = %.3f" % (P["bmp_front"], 1 - 2 * P["bmp_front"]))


def build_ribs(P, coll, root, M):
    """Рёбра: рейки вдоль хода на крыше (отсылка к стальному ящику) и рёбра жёсткости по бокам кармана пружины."""
    # рейки на крыше — в тёмной утопленной панели, светлые
    n, a = P["rib_n"], P["lt"] - 0.016 - 0.006
    pitch = 2 * (P["wt"] - 0.016 - 0.012) / n
    zf = P["z3"] - 0.012
    for k in range(n):
        xc = -P["wt"] + 0.016 + 0.012 + pitch * (k + 0.5)
        bm = bmesh.new()
        bm_box(bm, xc - P["rib_w"] / 2, xc + P["rib_w"] / 2, -a, a, zf - 0.002, P["z3"] + 0.006)
        obj_from_bm("toprib%d" % k, bm, coll, root, [M["steel2"]], bevel=0.004)
    # рёбра жёсткости: пластины поперёк хода, повторяют сечение базы с вылетом e, обрамляют карман с двух сторон
    e, t = P["fin_e"], P["fin_t"]
    L2 = P["L"] / 2
    for s in (1, -1):
        for y0 in P["fin_y"]:
            for sy in (1, -1):
                yc = sy * y0
                bm = bmesh.new()
                bm_box(bm, -0.6, 0.6, yc - t / 2, yc + t / 2, P["zb"], P["z3"] - 0.004)

                def cut_off(co, no):
                    nv = Vector(no).normalized()
                    cut(bm, Vector(co) + nv * e, nv)
                cut_off((s * P["xb"], 0, P["zb"]), (s * (P["z2s"] - P["zb"]), 0, -(P["ws"] - P["xb"])))
                cut_off((s * P["ws"], 0, P["z2s"]), (s * (P["z3"] - P["z2s"]), 0, P["ws"] - P["wt"]))
                cut_off((0, sy * L2, P["z2"]), (0, sy * (P["z3"] - P["z2"]), L2 - P["lt"]))
                cut_off((0, sy * L2, P["z1e"]), (0, sy * (P["z1e"] - P["zb"]), -(L2 - P["lb"])))
                cut(bm, (s * P["fin_x0"], 0, 0), (-s, 0, 0))            # только у наружной стороны
                cut(bm, (0, 0, P["fin_z0"]), (0, 0, -1))
                obj_from_bm("fin%+d%+d_%d" % (s, sy, int(y0 * 1000)), bm, coll, root, [M["steel2"]], bevel=0.004)


def build_variant(key, title, P, M):
    coll = K.collection("CART_%s" % key, exclude=True)
    root = K.empty("root_%s" % key, coll)
    build_body(P, coll, root, M)
    build_mechanism(P, coll, root, M)
    if P.get("bump"):
        build_bumpers(P, coll, root, M)
    for side in (1, -1):
        build_wheel(P, coll, root, M, side)
        build_cheek(P, coll, root, M, side)
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
