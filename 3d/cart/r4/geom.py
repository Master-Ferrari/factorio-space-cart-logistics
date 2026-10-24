# -*- coding: utf-8 -*-
"""Раунд 4: геометрия каретки «Перемётная сума» и схемы-альтернативы для сравнения силуэтов (bpy).

Локальные оси каретки: начало — на оси рельса на уровне ложа (z = 0), +Y — вперёд, Z — вверх.
Все размеры выводятся из ограничений (см. README): контакт колёс по parts.pinch_rollers,
конверт силуэта 54.7°, тоннель поворотов «)(» r 0.5, клиренс над ложементами z 0.03.
"""

import math

import bmesh
from mathutils import Vector

import scl3d as K
import lowpoly as L
import r3

RT = K.RAIL_TOP_Z
S2 = math.sqrt(0.5)
CH = 0.007                         # фаска в один сегмент

# ── ключевые размеры ────────────────────────────────────────────────
P = dict(
    r=0.125,           # радиус колеса
    w=0.036,           # толщина колеса
    z0=0.03,           # днище: клиренс над ложементами рёбер тайла
    zs=0.03,           # откуда начинается уклон бортов
    hw=0.36,           # полуширина подошвы
    hl=0.36,           # полудлина подошвы
    ch=0.14,           # 45°-фаска октагона в плане (меньше — соседи на повороте r 0.5 сходятся углами)
    face=0.04,         # внутренняя грань сумы: z = |x| + face (ниже колеса на зазор)
    top=0.225,         # конёк сумы
    a_side=60.0,       # уклон боковых граней, °
    a_end=55.0,        # уклон торцов, ° (≤ 54.7 — торец не поднимает силуэт)
    tun_z=0.15,        # потолок тоннеля «)(»
    tun_m=0.02,        # зазор тоннеля до огибающей лезвия
    yoke_y=(0.215, 0.25),    # стрельчатые стяжки над развалом
    portal_y=(0.21, 0.28),   # порталы-стяжки сразу перед и за колёсами
    hip_y=0.16,        # от этой точки конёк сходит к торцам
    hip_k=0.45,        # уклон схода конька (dz/dy)
)


def contact(s):
    return (s * 0.017, RT - 0.006)


def wheel_center(s, r):
    cx, cz = contact(s)
    return (cx + r * S2 * s, 0.0, cz + r * S2)


def env_x(y, m=0.0):
    """Огибающая лезвия под кареткой на поворотах r 0.5 (полуширина по x на расстоянии y)."""
    y = min(abs(y), 0.49)
    return 0.5 - math.sqrt(0.25 - y * y) + K.RAIL_HALF_W + m


def hourglass(m, ylim=0.47, n=9):
    ys = [-ylim + 2 * ylim * i / (n - 1) for i in range(n)]
    right = [(env_x(y, m), y) for y in ys]
    left = [(-x, y) for x, y in reversed(right)]
    return right + left


# ── примитивы ───────────────────────────────────────────────────────
def odisc(name, c, r, depth, center, axis, mat, parent, segs=16, ch=0.0, r2=None):
    """Лоуполи-цилиндр с произвольной осью axis, центр в center."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r,
                          radius2=r if r2 is None else r2, depth=depth)
    q = Vector(axis).normalized().to_track_quat('Z', 'Y')
    return L.finish(name, bm, c, mat, parent, ch, loc=center, rot=q.to_euler())


def wheel(c, root, M, s, r, w, y=0.0, name="wheel", hub=True):
    """Колесо ±45° на плече головки: плоскость колеса содержит Y и нормаль плеча."""
    cx, _, cz = wheel_center(s, r)
    ax = Vector((-s * S2, 0, S2))                      # ось колеса: внутрь-вверх (к камере сверху)
    ctr = Vector((cx, y, cz))
    odisc("%s%+d" % (name, s), c, r, w, ctr, ax, M["mid"], root, segs=16, ch=0.006)          # бандаж
    odisc("%s_disc%+d" % (name, s), c, r * 0.80, w + 0.012, ctr, ax, M["light"], root, segs=16, ch=0.006)
    if hub:
        odisc("%s_hub%+d" % (name, s), c, r * 0.28, 0.02, ctr + ax * (w / 2 + 0.012), ax,
              M["brass"], root, segs=8, ch=0.003)
        # «+» на ступице (со скетча автора)
        u = Vector((0, 1, 0))
        v = ax.cross(u).normalized()
        base = ctr + ax * (w / 2 + 0.006)
        for k, d in enumerate((u, v)):
            p0, p1 = base - d * r * 0.62, base + d * r * 0.62
            L.rod("%s_plus%d%+d" % (name, k, s), c, p0, p1, 0.008, M["mid"], root, segs=4)
    return ctr


def fender(c, root, M, s, r, w, t0=10.0, t1=170.0, gap=0.01, band=0.024, n=8, name="fender"):
    """Крыло над ободом — изогнутое лезвие в плоскости колеса со стрельчатыми кончиками,
    как дуги-лезвия тайла. Корень — в коньке сумы (верх-наружу, t = 90°)."""
    cx, _, cz = wheel_center(s, r)
    ctr = Vector((cx, 0, cz))
    e1 = Vector((0, 1, 0))
    e2 = Vector((s * S2, 0, S2))
    ax = Vector((-s * S2, 0, S2))
    hw = w / 2 + 0.012
    bm = bmesh.new()
    rings = []
    for i in range(n + 1):
        t = math.radians(t0 + (t1 - t0) * i / n)
        k = math.sin(math.pi * i / n) ** 0.6                     # к кончикам лезвие сходит на нет
        r1, r2 = r + gap, r + gap + band * max(k, 0.0)
        d = e1 * math.cos(t) + e2 * math.sin(t)
        rings.append([bm.verts.new(ctr + d * rr + ax * hh) for rr, hh in ((r1, -hw), (r2, -hw), (r2, hw), (r1, hw))])
    for i in range(n):
        for k in range(4):
            bm.faces.new((rings[i][k], rings[i][(k + 1) % 4], rings[i + 1][(k + 1) % 4], rings[i + 1][k]))
    bm.faces.new(rings[0])
    bm.faces.new(rings[-1][::-1])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    return L.finish("%s%+d" % (name, s), bm, c, M["light"], root, ch=0.003)


# ── P: «Перемётная сума» ───────────────────────────────────────────
def slope_cut(pt_xy, n_xy, z_at, ang_deg):
    """Наклонная грань: проходит через ребро плана (pt_xy, нормаль n_xy) на высоте z_at,
    уходит внутрь под углом ang к горизонту. Возвращает (co, no) для L.cut."""
    a = math.radians(ang_deg)
    nx, ny = n_xy
    return ((pt_xy[0], pt_xy[1], z_at), (nx * math.sin(a), ny * math.sin(a), math.cos(a)))


def half_oct(s, hw, hl, ch):
    half = [(0.0, -hl), (hw - ch, -hl), (hw, -hl + ch), (hw, hl - ch), (hw - ch, hl), (0.0, hl)]
    pts = [(s * x, y) for x, y in half]
    return pts[::-1] if s < 0 else pts


def pannier(c, root, M, s, p=P):
    """Сума: тёмный корпус на стальной раме-обвязке. Внутренняя грань 45° — ложе колеса,
    борта и торцы — в конверте силуэта, снизу — тоннель «)(» под повороты."""
    hw, hl, ch, z0, zs = p["hw"], p["hl"], p["ch"], p["z0"], p["zs"]
    inset = 0.0
    hw2, hl2 = hw - inset, hl - inset
    cuts = [
        ((0, 0, p["face"]), (-s, 0, 1)),                                   # 45° — ложе колеса
        ((0, 0, p["top"]), (0, 0, 1)),                                     # конёк
        slope_cut((s * hw2, 0), (s, 0), zs, p["a_side"]),                  # борт
        slope_cut((s * hw2, hl2 - ch), (s * S2, S2), zs, p["a_side"]),     # фаски октагона
        slope_cut((s * hw2, -hl2 + ch), (s * S2, -S2), zs, p["a_side"]),
        slope_cut((0, hl2), (0, 1), zs, p["a_end"]),                       # торцы
        slope_cut((0, -hl2), (0, -1), zs, p["a_end"]),
        ((0, p["hip_y"], p["top"]), (0, p["hip_k"], 1)),                   # конёк сходит к торцам
        ((0, -p["hip_y"], p["top"]), (0, -p["hip_k"], 1)),
    ]
    o = L.plan("pannier%+d" % s, c, half_oct(s, hw2, hl2, ch), z0, 0.40, M["dark"], root, cuts=cuts, ch=CH)
    tun = L.plan("tunnel_cut%+d" % s, c, hourglass(p["tun_m"]), -0.1, p["tun_z"], None, root)
    K.bool_cut(o, tun)
    return o


def ridge_frame(c, root, M, s, p=P):
    """Светлая стальная обвязка по коньку сумы."""
    hw, hl, ch, zs = p["hw"], p["hl"], p["ch"], p["zs"]
    zt = p["top"]
    run = (zt - zs) / math.tan(math.radians(p["a_side"]))
    rune = (zt - zs) / math.tan(math.radians(p["a_end"]))
    xo = hw - run
    xi = zt - p["face"]
    yo = min(hl - rune, p["hip_y"] + 0.03)
    c2 = ch * 0.75
    pts = [(xi, -yo), (xo - c2, -yo), (xo, -yo + c2), (xo, yo - c2), (xo - c2, yo), (xi, yo)]
    pts = [(s * x, y) for x, y in pts]
    if s < 0:
        pts = pts[::-1]
    return L.plan("ridge%+d" % s, c, pts, zt - 0.004, zt + 0.012, M["light"], root, ch=0.004)


def yoke(c, root, M, sy, p=P):
    """Стрельчатая стяжка над развалом: две полуарки от 45°-граней сумы сходятся в замке,
    в замке — латунная муфта (ею задают преднатяг колёс на головку). Пролёт чист над огибающей лезвия."""
    y0, y1 = p["yoke_y"]
    outer = r3.arch(0.15, 0.10, 0.235, 4)
    inner = r3.arch(0.115, 0.10, 0.195, 4)
    ring = outer + inner[::-1]
    ya, yb = (y0, y1) if sy > 0 else (-y1, -y0)
    L.section("yoke%+d" % sy, c, ring, ya, yb, M["light"], root, ch=0.004)
    yc = (ya + yb) / 2
    L.disc("yoke_bush%+d" % sy, c, 0.022, (y1 - y0) + 0.03, (0, yc, 0.212), 'Y', M["brass"], root, segs=8, ch=0.003)


def buffers(c, root, M, p=P):
    """Торцевые блоки-буферы по паре на торец — бежевые, разрезанные рельсом, как ложементы
    на рёбрах тайла. В поезде на прямой стоят против таких же блоков соседа."""
    hl, hw, ch, z0 = p["hl"], p["hw"], p["ch"], p["z0"]
    for sy in (-1, 1):
        for s in (-1, 1):
            xi = env_x(hl, p["tun_m"]) + 0.004
            xo = hw - ch + 0.03
            pts = [(xi, hl - 0.075), (xo + 0.02, hl - 0.075), (xo, hl + 0.025), (xi, hl + 0.025)]
            pts = [(s * x, sy * y) for x, y in pts]
            if s * sy < 0:
                pts = pts[::-1]
            L.plan("buffer%+d%+d" % (s, sy), c, pts, z0, z0 + 0.115, M["beige"], root,
                   cuts=[((0, sy * (hl + 0.025), z0 + 0.05), (0, sy, 0.70))], ch=0.006)


def hatch(c, root, M, s, p=P):
    """Крышка люка на борту — сума есть контейнер; люк лежит в плоскости наклонного борта."""
    zs, a = p["zs"], math.radians(p["a_side"])
    hw2 = p["hw"]
    za, zb = zs + 0.03, p["top"] - 0.03
    xa = hw2 - (za - zs) / math.tan(a)
    xb = hw2 - (zb - zs) / math.tan(a)
    U = Vector((s * (xb - xa), 0, zb - za)).normalized()          # вверх по борту
    V = Vector((0, 1, 0))
    O = Vector((s * xa, 0, za))
    hl = 0.17
    pts = [(0, -hl + 0.03), (0.03, -hl), (0.12, -hl + 0.04), (0.12, hl - 0.04), (0.03, hl), (0, hl - 0.03)]
    N = U.cross(V)
    if N.dot(Vector((s, 0, 1))) < 0:
        V = -V
    return L.plate("hatch%+d" % s, c, pts, -0.004, 0.012, M["mid"], root, origin=O, U=U, V=V, ch=0.004)


def portal(c, root, M, sy, p=P):
    """Портал — стяжка сум перед и за колёсами. Две бежевые половины (разрез по оси, как у
    ложементов тайла); в арке — рельс с запасом на вынос лезвия на повороте r 0.5; на
    внутренней грани поверх разреза — латунная муфта-стяжка: ею задают преднатяг колёс."""
    z0 = p["z0"]
    yi, yo = p["portal_y"]
    xa = env_x(yo, p["tun_m"])                        # пролёт арки — огибающая лезвия
    xo = xa + 0.10
    zt, zk = 0.21, 0.165
    for s in (-1, 1):
        half = [(0.004, zk), (xa * 0.45, zk - 0.012), (xa, 0.125), (xa, z0), (xo, z0),
                (xo, zt - 0.06), (xo - 0.06, zt), (0.004, zt)]
        pts = [(s * x, z) for x, z in half]
        if s > 0:
            pts = pts[::-1]
        ya, yb = (yi, yo) if sy > 0 else (-yo, -yi)
        L.section("portal%+d%+d" % (s, sy), c, pts, ya, yb, M["beige"], root, ch=0.006)
    yc = sy * (yi - 0.012)
    L.disc("portal_muff%+d" % sy, c, 0.026, 0.12, (0, yc, zt - 0.025), 'X', M["brass"], root, segs=8, ch=0.003)


def build_suma(c, root, M):
    p = P
    for s in (-1, 1):
        pannier(c, root, M, s)
        ridge_frame(c, root, M, s)
        wheel(c, root, M, s, p["r"], p["w"])
        fender(c, root, M, s, p["r"], p["w"])
        hatch(c, root, M, s)
    for sy in (-1, 1):
        portal(c, root, M, sy)


# ── схемы-альтернативы (только для сравнения силуэтов, без деталей) ──
def build_x1_over(c, root, M):
    """X1: корпус над колёсами — как скетч автора буквально (колёса ±45°, ящик сверху)."""
    r = P["r"]
    for s in (-1, 1):
        wheel(c, root, M, s, r, P["w"])
    zt = RT + 2 * r * S2 + 0.02
    L.plan("body", c, L.octagon(0.33, 0.36, 0.11), zt, zt + 0.20, M["dark"], root, ch=CH)
    L.plan("rim", c, L.octagon(0.31, 0.34, 0.10), zt + 0.20, zt + 0.215, M["light"], root, ch=0.004)


def build_x2_tunnel(c, root, M):
    """X2: цельный ящик-седло до ложа, колёса спрятаны в тоннеле под ним (как S1/B)."""
    r = P["r"]
    for s in (-1, 1):
        wheel(c, root, M, s, r, P["w"])
    o = L.plan("body", c, L.octagon(0.36, 0.38, 0.12), P["z0"], 0.36, M["dark"], root, ch=CH)
    cut = L.section("tunnel", c, [(-0.25, -0.1), (0.25, -0.1), (0.25, 0.33), (-0.25, 0.33)], -0.2, 0.2, None, root)
    K.bool_cut(o, cut)
    tun = L.plan("tun2", c, hourglass(0.02), -0.1, 0.15, None, root)
    K.bool_cut(o, tun)


def build_x3_nose(c, root, M):
    """X3: колесо в носу под крылом-аркой, груз сзади низко на ложе (скетч «резкий спуск вниз»)."""
    r = P["r"]
    yw = 0.20
    for s in (-1, 1):
        wheel(c, root, M, s, r, P["w"], y=yw)
    L.side("fender", c, [(yw - 0.18, 0.25), (yw + 0.16, 0.25), (yw + 0.16, 0.33), (yw - 0.18, 0.36)],
           -0.25, 0.25, M["dark"], root, ch=CH)
    o = L.plan("cargo", c, L.octagon(0.34, 0.22, 0.08), P["z0"], 0.27, M["dark"], root, ch=CH)
    o.location = (0, -0.14, 0)
    tun = L.plan("tun3", c, hourglass(0.02), -0.1, 0.15, None, root)
    tun.location = (0, 0.14, 0)
    K.bool_cut(o, tun)


def build_x4_tray(c, root, M):
    """X4: низкий поднос на ложе, колёса открыто сверху (объём весь низко, колёса — верх)."""
    r = P["r"]
    for s in (-1, 1):
        wheel(c, root, M, s, r, P["w"])
    o = L.plan("tray", c, L.octagon(0.37, 0.38, 0.13), P["z0"], 0.14, M["dark"], root, ch=CH)
    tun = L.plan("tun4", c, hourglass(0.02), -0.1, 0.20, None, root)
    K.bool_cut(o, tun)


BUILDERS = dict(P=build_suma, X1=build_x1_over, X2=build_x2_tunnel, X3=build_x3_nose, X4=build_x4_tray)
