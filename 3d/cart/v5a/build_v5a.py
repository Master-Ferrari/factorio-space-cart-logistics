# -*- coding: utf-8 -*-
"""Блокинг каретки v5a: два больших колеса V-образно смыкаются на лезвии монорельса,
гранёный стальной ящик вложен в развал V.

Запуск: blender -b --factory-startup --python build_v5a.py   → v5a/cart_v5a.blend

Модель строится в честных пропорциях, ход — по +Y (курс 0 = север), колёса — по ±X.
Каждая вариация — коллекция CART_<K> (исключена из вью-лейера) с корнем в начале координат.
Всё режется «ножницами»: коробка → срезы плоскостями (bisect + заливка дыры),
фаски одним сегментом, вставки/выдавливания. Тела вращения — по профилю из 4–8 точек.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import scl3d as K  # noqa: E402
from params import VARIANTS  # noqa: E402

OUT = os.path.join(HERE, "cart_v5a.blend")


# ── материалы: ванильная палитра (Workbench берёт diffuse_color) ────
def mats():
    M = dict(
        steel=K.material("v5_steel", (0.20, 0.21, 0.22), 0.5, 0.8),     # корпус, тёмная сталь
        steel2=K.material("v5_steel2", (0.30, 0.31, 0.32), 0.45, 0.8),  # рамы, фаски
        dark=K.material("v5_dark", (0.07, 0.07, 0.075), 0.7, 0.2),      # ниши, диски колёс
        chrome=K.material("v5_chrome", (0.62, 0.65, 0.68), 0.2, 1.0),   # обода, звезда (как лезвия)
        beige=K.material("v5_beige", (0.74, 0.68, 0.56), 0.6, 0.0),     # буферы (как ложементы)
        brass=K.material("v5_brass", (0.78, 0.52, 0.20), 0.35, 1.0),    # втулки (как на тайле)
        orange=K.material("v5_orange", (0.95, 0.45, 0.08), 0.5, 0.0),   # акцент
        # болванка рельса для свободных видов
        base=K.material("rr_base", (0.10, 0.10, 0.11), 0.7, 0.3),
        bed=K.material("rr_bed", (0.70, 0.64, 0.52), 0.6, 0.0),
        blade=K.material("rr_blade", (0.66, 0.69, 0.72), 0.25, 1.0),
    )
    for m in M.values():
        m.use_fake_user = True
    return M


# ── «ножницы» ───────────────────────────────────────────────────────
def bm_box(x0, x1, y0, y1, z0, z1):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((x0 if v.co.x < 0 else x1, y0 if v.co.y < 0 else y1, z0 if v.co.z < 0 else z1))
    return bm


def cut(bm, co, no):
    """Срез плоскостью: всё по ту сторону нормали no удаляется, дыра закрывается гранью."""
    no = Vector(no).normalized()
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=Vector(co), plane_no=no,
                                 clear_outer=True, dist=1e-6)
    edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    if edges:
        bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def face_toward(bm, d, pick=max):
    d = Vector(d).normalized()
    return pick((f for f in bm.faces if f.normal.dot(d) > 0.98),
                key=lambda f: f.calc_center_median().dot(d))


def recess(bm, face, rim, depth):
    """Вставка + выдавливание грани по нормали: рамка шириной rim, ступень высотой -depth
    (depth > 0 — ниша, < 0 — выступ). Стенки ступени перпендикулярны грани."""
    n = face.normal.copy()
    bmesh.ops.inset_individual(bm, faces=[face], thickness=rim, depth=0.0)
    r = bmesh.ops.extrude_discrete_faces(bm, faces=[face])
    f = r["faces"][0]
    bmesh.ops.translate(bm, verts=f.verts, vec=-depth * n)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return f


def to_obj(name, bm, coll, mat, parent, matrix=None, sharp_deg=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if sharp_deg is not None:
        for p in me.polygons:
            p.use_smooth = True
        try:
            me.set_sharp_from_angle(angle=math.radians(sharp_deg))
        except Exception:
            pass
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    o.parent = parent
    if matrix is not None:
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.matrix_basis = matrix
    for mm in (mat if isinstance(mat, (list, tuple)) else [mat]):
        me.materials.append(mm)
    return o


def revolve(prof, segs, phase=0.0):
    """Тело вращения вокруг локальной X. prof — замкнутый профиль [(x, радиус), ...]."""
    bm = bmesh.new()
    ring = []
    for i in range(segs):
        a = phase + 2 * math.pi * i / segs
        ring.append([bm.verts.new((x, r * math.cos(a), r * math.sin(a))) for x, r in prof])
    n = len(prof)
    for i in range(segs):
        i2 = (i + 1) % segs
        for j in range(n):
            j2 = (j + 1) % n
            q = [ring[i][j], ring[i2][j], ring[i2][j2], ring[i][j2]]
            uniq = []
            for v in q:
                if all((v.co - u.co).length > 1e-7 for u in uniq):
                    uniq.append(v)
            if len(uniq) >= 3:
                try:
                    bm.faces.new(uniq)
                except ValueError:
                    pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def star_prism(r1, r2, x0, x1, n=4, phase=0.0):
    """Звезда (как четырёхлучевая звезда лезвий тайла) в плоскости YZ, толщина по X."""
    pts = []
    for i in range(2 * n):
        a = phase + math.pi * i / n
        r = r1 if i % 2 == 0 else r2
        pts.append((r * math.cos(a), r * math.sin(a)))
    bm = bmesh.new()
    a = [bm.verts.new((x0, y, z)) for y, z in pts]
    b = [bm.verts.new((x1, y, z)) for y, z in pts]
    bm.faces.new(a[::-1])
    bm.faces.new(b)
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def chamfer_edges(bm, width, pick):
    edges = [e for e in bm.edges if pick(e)]
    if edges:
        bmesh.ops.bevel(bm, geom=edges, offset=width, segments=1, affect='EDGES', profile=0.5)


def sharp_edges(bm, deg=30):
    return lambda e: (len(e.link_faces) == 2 and
                      e.link_faces[0].normal.angle(e.link_faces[1].normal, 0) > math.radians(deg))


# ── геометрия ───────────────────────────────────────────────────────
class Geo:
    """Поперечник каретки из параметров: всё считается от лезвия рельса и наклона колёс."""

    def __init__(self, P):
        self.P = P
        phi = math.radians(P["lean"])
        self.phi = phi
        self.u = Vector((math.sin(phi), 0, math.cos(phi)))        # «вверх» в плоскости колеса (+X)
        self.a = Vector((math.cos(phi), 0, -math.sin(phi)))       # ось колеса наружу (+X)
        # точка касания: внутренняя кромка обода на верхней кромке лезвия
        self.c0 = Vector((K.RAIL_HALF_W, 0, K.RAIL_TOP_Z))
        self.center = self.c0 + P["r"] * self.u                   # центр внутренней грани колеса (+X)

    def mirror(self, v, s):
        return Vector((v.x * s, v.y, v.z))


def wheel(coll, root, G, side, M, name):
    """Колесо: стальной обод с фасками, утопленный тёмный диск, латунная втулка, хромовая звезда.
    Локально: ось X наружу, центр внутренней грани в нуле."""
    P = G.P
    r, t = P["r"], P["t"]
    rim = P["rim"]
    # матрица: X→a, Y→Y, Z→u (для side=-1 зеркально)
    a = G.mirror(G.a, side)
    u = G.mirror(G.u, side)
    rot = Matrix((a, Vector((0, 1, 0)), u)).transposed().to_4x4()
    m = Matrix.Translation(G.mirror(G.center, side)) @ rot
    segs = P["segs"]
    ch = 0.012
    # обод: кольцо с фасками по внешним кромкам (беговая дорожка — плоская, ложится на плечо)
    tire = [(0, r - rim), (0, r - ch), (ch, r), (t - ch, r), (t, r - ch), (t, r - rim)]
    to_obj(name + "_tire", revolve(tire, segs), coll, M["chrome"], root, m, 35)
    # диск: утоплен с обеих сторон, со стороны наружу — ступенька к втулке
    web_in, web_out = 0.018, t - 0.014
    disk = [(web_in, 0.0), (web_in, r - rim + 0.002), (web_out, r - rim + 0.002), (web_out, 0.0)]
    to_obj(name + "_disk", revolve(disk, segs), coll, M["steel"], root, m, 35)
    # окна в диске: 4 выреза-«лепестка» (ритм четырёхлучевой звезды тайла)
    if P.get("windows"):
        for k in range(4):
            ang = math.pi / 4 + k * math.pi / 2
            rr = (r - rim) * 0.58
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=P["win_r"],
                                  radius2=P["win_r"], depth=0.003)
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0),
                             matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'))
            bmesh.ops.translate(bm, verts=bm.verts,
                                vec=(web_out + 0.0012, rr * math.cos(ang), rr * math.sin(ang)))
            to_obj(name + "_win%d" % k, bm, coll, M["dark"], root, m)
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=P["win_r"],
                                  radius2=P["win_r"], depth=0.003)
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0),
                             matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'))
            bmesh.ops.translate(bm, verts=bm.verts,
                                vec=(web_in - 0.0012, rr * math.cos(ang), rr * math.sin(ang)))
            to_obj(name + "_wini%d" % k, bm, coll, M["dark"], root, m)
    # втулка: латунный барабан с фаской, наружу выступает за обод; внутрь — в корпус
    hr = P["hub_r"]
    hub = [(-P["axle"], 0.0), (-P["axle"], hr * 0.75), (-0.01, hr * 0.75), (-0.01, hr),
           (t + P["hub_out"] - 0.012, hr), (t + P["hub_out"], hr - 0.012), (t + P["hub_out"], 0.0)]
    to_obj(name + "_hub", revolve(hub, 12, math.pi / 12), coll, M["brass"], root, m, 35)
    # «прицел»: хромовая четырёхлучевая звезда на торце втулки
    x0 = t + P["hub_out"]
    to_obj(name + "_star", star_prism(hr * 1.35, hr * 0.32, x0 - 0.004, x0 + 0.014, 4, 0.0),
           coll, M["chrome"], root, m)


def body(coll, root, G, M, name):
    """Гранёный ящик: коробка, срезанная плоскостями.
    Поперечник — шестигранник: клин снизу (грани ∥ колёсам, с зазором), пояс, фаски сверху.
    Торцы и углы плана срезаны (план — восьмигранник, рифма с октагонами тайла).
    Тон по граням: верх и пояс — тёмная сталь, фаски — светлая рама, клин — почти чёрный;
    сверху — утопленный грузовой колодец (тёмный) с крышкой."""
    P = G.P
    W, L = P["W"], P["L"]
    zb, zt = P["zb"], P["zt"]
    bm = bm_box(-W, W, -L / 2, L / 2, zb, zt)
    g = P["gap"]
    for s in (-1, 1):
        a = G.mirror(G.a, s)
        cut(bm, G.mirror(G.c0, s) - g * a, a)
    c = P["ch_top"]
    for s in (-1, 1):
        cut(bm, (s * W, 0, zt - c), (s, 0, 1))
    ce, cl = P["ch_end"], P["ch_end_lo"]
    for s in (-1, 1):
        cut(bm, (0, s * L / 2, zt - ce), (0, s, 1))
        cut(bm, (0, s * L / 2, zb + cl), (0, s, -1))
    cc = P["ch_plan"]
    for sx in (-1, 1):
        for sy in (-1, 1):
            cut(bm, (sx * W, sy * (L / 2 - cc), 0), (sx, sy, 0))
    top = face_toward(bm, (0, 0, 1))
    well = recess(bm, top, P["lid_rim"], P["lid_depth"])
    for f in bm.faces:
        nz = f.normal.z
        f.material_index = (3 if f is well else 0 if nz > 0.95 else 1 if nz > 0.2
                            else 0 if nz > -0.2 else 2)
    o = to_obj(name, bm, coll, [M["steel"], M["steel2"], M["dark"], M["dark"]], root)
    # крышка колодца: плита со срезанными углами и фаской, меньше колодца — по краю тёмная щель
    hx, hy = P["hatch"]
    zl = zt - P["lid_depth"]
    hb = bm_box(-hx, hx, -hy, hy, zl, zl + P["hatch_h"])
    for sx in (-1, 1):
        for sy in (-1, 1):
            cut(hb, (sx * hx, sy * (hy - 0.03), 0), (sx, sy, 0))
        cut(hb, (sx * hx, 0, zl + P["hatch_h"] - 0.01), (sx, 0, 1))
    for sy in (-1, 1):
        cut(hb, (0, sy * hy, zl + P["hatch_h"] - 0.01), (0, sy, 1))
    to_obj(name + "_lid", hb, coll, M["steel2"], root)
    # рёбра-петли крышки поперёк: две латунные планки (как латунные втулки тайла)
    for sy in (-1, 1):
        rb = bm_box(-hx - 0.012, hx + 0.012, sy * hy * 0.55 - 0.014, sy * hy * 0.55 + 0.014,
                    zl, zl + P["hatch_h"] + 0.008)
        to_obj("%s_rib%d" % (name, sy), rb, coll, M["brass"], root)
    return o


def shoes(coll, root, G, M, name):
    """Торцевые башмаки-буферы: бежевые разрезные колодки, как ложементы тайла.
    Стоят за пределами колёс по ходу (|y| > r), опускаются к ложу и седлают лезвие пазом.
    В плане поезда колодки соседей встают встык; сверху они — «уши» скетча."""
    P = G.P
    yi, yo = P["shoe_y"]
    We, z0, z1 = P["shoe_w"], P["shoe_z"][0], P["shoe_z"][1]
    slot = P["slot"]
    for s in (-1, 1):
        for k in (-1, 1):
            x0, x1 = (slot, We) if k > 0 else (-We, -slot)
            y0, y1 = (yi, yo) if s > 0 else (-yo, -yi)
            bm = bm_box(x0, x1, y0, y1, z0, z1)
            cut(bm, (k * We, 0, z0 + P["shoe_ch_lo"]), (k, 0, -1))      # низ ∥ колёсам — клин
            cut(bm, (k * We, 0, z1 - 0.04), (k, 0, 1))                  # верхняя фаска
            cut(bm, (0, s * yo, z1 - 0.05), (0, s, 1))                  # скос торца
            cut(bm, (k * We, s * (yo - 0.04), 0), (k, s, 0))            # угол плана
            chamfer_edges(bm, 0.006, sharp_edges(bm))
            to_obj("%s_shoe%d%d" % (name, s, k), bm, coll, M["beige"], root)
        # латунная сцепка над лезвием между половинками
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.026, radius2=0.026, depth=0.06)
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'X'))
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, s * (yo - 0.015), (z0 + z1) * 0.5 + 0.05))
        to_obj("%s_pin%d" % (name, s), bm, coll, M["brass"], root)


def axle_mounts(coll, root, G, M, name):
    """Опоры осей: короткие шестигранные стаканы от клина корпуса к втулке колеса."""
    P = G.P
    for s in (-1, 1):
        a = G.mirror(G.a, s)
        u = G.mirror(G.u, s)
        c = G.mirror(G.center, s)
        rot = Matrix((a, Vector((0, 1, 0)), u)).transposed().to_4x4()
        m = Matrix.Translation(c) @ rot
        L0 = P["gap"] + 0.03
        prof = [(-L0, 0.0), (-L0, P["hub_r"] * 1.25), (-0.012, P["hub_r"] * 1.25),
                (-0.004, P["hub_r"] * 1.1), (-0.004, 0.0)]
        to_obj("%s_mount%d" % (name, s), revolve(prof, 6, math.pi / 6), coll, M["steel2"], root, m)


def build_variant(key, P, M):
    coll = K.collection("CART_%s" % key, exclude=True)
    root = K.empty("CART_%s_root" % key, coll)
    G = Geo(P)
    body(coll, root, G, M, key + "_body")
    for s in (-1, 1):
        wheel(coll, root, G, s, M, "%s_wheel%d" % (key, s))
    axle_mounts(coll, root, G, M, key)
    shoes(coll, root, G, M, key)
    return coll


def main():
    K.reset_scene()
    M = mats()
    only = None
    if "--" in sys.argv:
        a = sys.argv[sys.argv.index("--") + 1:]
        if "--only" in a:
            only = a[a.index("--only") + 1].split(",")
    for key, P in VARIANTS.items():
        if only and key not in only:
            continue
        build_variant(key, P, M)
        print("built", key)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("saved", OUT)


main()
