# -*- coding: utf-8 -*-
"""Каретка hp2 — хайполи с нуля по рендерам v9c (форма снята с ортогональных видов листа v9c).

Запуск: blender -b --factory-startup --python build.py   ->  cart_hp2.blend (коллекция CART_A, исключена).
Локальные оси: Y — ход, X — поперёк (колёса на ±X), Z — вверх; 1 BU = 1 тайл, z = 0 — верх ложа.

Технология (рациональный инженер, мало станков):
  корпус   — гнутый лист: два выпуклых тела (нижний короб + шестигранник шатра), сваренные, с фаской гиба;
             хомуты-рёбра приварены; карманы пружин и выемки хвата — фрезерованы (boolean, скругление фрезы);
  крышка   — штампованная: плита + 5 выдавленных рёбер одним ремешем (галтели у рёбер);
  колесо   — токарное: обод с конической рабочей кромкой изнутри, диск, ступица, 6 болтов, латунная гайка;
  щека     — лист с отбортовкой верхней кромки, низ свёрнут в петлю (кулаки) на пальце, литой узел оси;
  проушины — приварены к торцам корпуса, палец с латунными гайками; бампер — труба на литом кронштейне.
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

import hk  # noqa: E402
import scl3d as K  # noqa: E402

S2 = math.sqrt(0.5)
VOX = 0.0022           # корпус
VOX_FINE = 0.0014      # мелкие детали

# ---------------------------------------------------------------- размеры (сняты с ортогональных видов v9c)
Z_BOT, Z_TOP = 0.341, 0.608          # низ корпуса, верх площадки
BOX_HW = 0.172                       # полуширина нижнего короба и площадки (поперёк)
HEX_HW, HEX_Z0, HEX_Z1 = 0.267, 0.486, 0.519   # самое широкое место шатра
HEX_ZL = 0.413                       # где нижний скат шатра встречает короб
END_Y, END_Z = 0.40, 0.413           # торец: скат от площадки до низа шатра (на виде с торца — шестигранник целиком)
DECK_HY = 0.16                       # полудлина площадки по ходу
PLAN_CH = 0.08                       # срез углов в плане

R_WHEEL, T_WHEEL = 0.29, 0.075
WHEEL_X, WHEEL_Z = 0.2275, 0.246     # центр колеса: коническая кромка вертикальна у y = ±лезвие
A_CHEEK = 0.075                      # плоскость щеки от плоскости колеса (палец лежит в ней)
CHEEK_T = 0.014
CHEEK_HY = 0.385
STRAP_Y, STRAP_W = 0.11, 0.025
POCKET_HY = 0.066
BEAD_R = 0.011                       # выштамповка-ребро жёсткости (полукруг в листе)
RIB_X = (-0.112, -0.056, 0.0, 0.056, 0.112)
END_S = Vector((0, END_Y - 0.16, -(0.608 - END_Z))).normalized()   # вниз по скату торца (для sy=+1)
SPRING_S = 0.142                     # гнездо пружины на щеке (вверх по скату от пальца)


def frame(sx):
    """Для стороны sx (±1): центр колеса C, n — ось колеса внутрь-вверх, u — вверх по скату наружу."""
    C = Vector((sx * WHEEL_X, 0, WHEEL_Z))
    n = Vector((-sx * S2, 0, S2))
    u = Vector((sx * S2, 0, S2))
    return C, n, u


def pin_point(sx):
    C, n, u = frame(sx)
    return C + n * A_CHEEK


# ---------------------------------------------------------------- материалы
def mats():
    return dict(
        shell=K.material("hp2_shell", (0.075, 0.08, 0.085), 0.6, 0.6),
        strap=K.material("hp2_strap", (0.12, 0.125, 0.13), 0.55, 0.6),
        lid=K.material("hp2_lid", (0.17, 0.175, 0.18), 0.5, 0.6),
        visor=K.material("hp2_visor", (0.17, 0.175, 0.18), 0.5, 0.6),
        rib=K.material("hp2_rib", (0.42, 0.43, 0.45), 0.4, 0.8),
        rim=K.material("hp2_rim", (0.50, 0.52, 0.55), 0.35, 0.9),
        web=K.material("hp2_web", (0.045, 0.045, 0.05), 0.6, 0.5),
        steel=K.material("hp2_steel", (0.30, 0.31, 0.33), 0.45, 0.8),
        brass=K.material("hp2_brass", (0.55, 0.40, 0.14), 0.35, 1.0),
        orange=K.material("hp2_orange", (0.85, 0.42, 0.06), 0.5, 0.0),
        rubber=K.material("hp2_rubber", (0.06, 0.06, 0.065), 0.8, 0.0),
        plate=K.material("hp2_plate", (0.32, 0.31, 0.27), 0.5, 0.3),
        base=K.material("hp2_ref_base", (0.05, 0.05, 0.055), 0.7, 0.3),
        bed=K.material("hp2_ref_bed", (0.56, 0.50, 0.40), 0.6, 0.0),
        blade=K.material("hp2_ref_blade", (0.62, 0.65, 0.70), 0.2, 1.0),
    )


# ---------------------------------------------------------------- корпус
def end_planes():
    s = Vector((0, -END_S.z, END_S.y))                     # нормаль ската торца
    pl = []
    for sy in (-1, 1):
        pl.append(((0, sy * END_Y, 0), (0, sy, 0)))
        pl.append(((0, sy * END_Y, END_Z), (0, sy * s.y, s.z)))
    for sx in (-1, 1):
        for sy in (-1, 1):
            pl.append(((sx * (HEX_HW - PLAN_CH), sy * END_Y, 0), (sx * S2, sy * S2, 0)))
    return pl


def shell_planes():
    """Плоскости двух выпуклых тел корпуса: шестигранник шатра и нижний короб (no — наружу)."""
    planes_hex = [((0, 0, Z_TOP), (0, 0, 1)), ((0, 0, HEX_ZL), (0, 0, -1))]
    for sx in (-1, 1):
        planes_hex.append(((sx * HEX_HW, 0, 0), (sx, 0, 0)))
        # верхний скат: (HEX_HW, HEX_Z1) -> (BOX_HW, Z_TOP)
        d = Vector((BOX_HW - HEX_HW, 0, Z_TOP - HEX_Z1))
        nrm = Vector((d.z, 0, -d.x)).normalized()
        planes_hex.append(((sx * HEX_HW, 0, HEX_Z1), (sx * nrm.x, 0, nrm.z)))
        # нижний скат: (BOX_HW, HEX_ZL) -> (HEX_HW, HEX_Z0)
        d = Vector((HEX_HW - BOX_HW, 0, HEX_Z0 - HEX_ZL))
        nrm = Vector((d.z, 0, -d.x)).normalized()
        planes_hex.append(((sx * BOX_HW, 0, HEX_ZL), (sx * nrm.x, 0, nrm.z)))
    planes_box = [((0, 0, Z_BOT), (0, 0, -1)), ((0, 0, HEX_ZL + 0.03), (0, 0, 1))]
    for sx in (-1, 1):
        planes_box.append(((sx * BOX_HW, 0, 0), (sx, 0, 0)))
    return planes_hex + end_planes(), planes_box + end_planes()


def shell_parts():
    ph, pb = shell_planes()
    return hk.polytope(ph), hk.polytope(pb)


def shell_depth(c, planes=None):
    """Глубина точки под наружной поверхностью корпуса (объединение двух выпуклых тел): > 0 — внутри."""
    ph, pb = planes or shell_planes()
    sd = min(max((c - Vector(p)).dot(Vector(n)) for p, n in pl) for pl in (ph, pb))
    return -sd


def pocket_frame(sx):
    """Ось пружины: от гнезда на щеке вдоль n; m = u — наружу от бокового ската."""
    C, n, u = frame(sx)
    Q = C + n * (A_CHEEK + CHEEK_T / 2 + 0.015) + u * SPRING_S
    return Q, n, u


def pocket_cutter(sx):
    """Карман пружины: тело короба пересекается с пружиной — вырез вдоль её оси, дно-упор у площадки."""
    Q, n, u = pocket_frame(sx)
    o = hk.hbox((-0.08, -POCKET_HY, -0.066), (0.172, POCKET_HY, 0.25))
    M = Matrix(((n.x, 0, u.x, Q.x), (n.y, 1, u.y, Q.y), (n.z, 0, u.z, Q.z), (0, 0, 0, 1)))
    hk.transform(o, M)
    hk.bevel(o, 0.012, 4, 30)
    return o


def in_pocket(c, sx):
    Q, n, u = pocket_frame(sx)
    d = c - Q
    return -0.09 < d.dot(n) < 0.205 and abs(d.y) < POCKET_HY + 0.003 and d.dot(u) < 0.02


K_UP, K_DN = 0.673, 0.82         # наклоны рёбер грани торца в её плоскости: верхние фаски (шатёр), нижние скаты
PANEL_M, PANEL_D = 0.020, 0.010  # филёнка торца: отступ от гибов шатра и глубина (гибы читаются рёбрами)
GRIP_M = 0.026                   # выемка: равный отступ от верхней и боковых кромок филёнки
GRIP_V = (PANEL_M + GRIP_M, PANEL_M + GRIP_M + 0.098)   # от верхней кромки торца вниз по скату
GRIP_HW = BOX_HW + K_UP * GRIP_V[0] - (PANEL_M + GRIP_M) * math.sqrt(1 + K_UP ** 2)
GRIP_CH = 0.024                  # длина фаски верхних углов (по скату)
GRIP_RL = 0.064                  # скругление нижней наружной кромки: длина перехода от панели до дна (по скату)
FACE = [(-BOX_HW, 0.0), (BOX_HW, 0.0), (HEX_HW, 0.141), (HEX_HW, 0.193), (BOX_HW, 0.309), (-BOX_HW, 0.309),
        (-HEX_HW, 0.193), (-HEX_HW, 0.141)]   # грань торца в своих координатах (x, v)


def offset_poly(poly, d):
    """Выпуклый многоугольник, отступленный внутрь на d (каждая сторона параллельна исходной)."""
    c = Vector((sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)))
    lines = []
    for i in range(len(poly)):
        a, b = Vector(poly[i]), Vector(poly[(i + 1) % len(poly)])
        t = (b - a).normalized()
        nrm = Vector((-t.y, t.x))
        if nrm.dot(c - a) < 0:
            nrm = -nrm
        lines.append((a + nrm * d, t))
    out = []
    for i in range(len(lines)):
        (p1, t1), (p2, t2) = lines[i - 1], lines[i]
        den = t1.x * t2.y - t1.y * t2.x
        k = ((p2.x - p1.x) * t2.y - (p2.y - p1.y) * t2.x) / den
        q = p1 + t1 * k
        out.append((q.x, q.y))
    return out


def panel_cutter(sy):
    """Филёнка торца: грань, отступленная от гибов на PANEL_M, утоплена на PANEL_D (штамп, галтель по дну)."""
    poly = offset_poly(FACE, PANEL_M)
    o = hk.hull([end_face_pt(sy, x, v, w) for x, v in poly for w in (-PANEL_D, 0.03)])
    hk.bevel(o, 0.007, 3, 20)
    return o


def grip_hw(v):
    """Контур выемки = контур грани торца, отступленный внутрь: верх || верхней кромке, фаски || фаскам грани,
    бока || нижним скатам грани (сходятся книзу), ровный низ."""
    t = v - GRIP_V[0]
    if t < GRIP_CH:
        return GRIP_HW + K_UP * t
    return GRIP_HW + K_UP * GRIP_CH - K_DN * (t - GRIP_CH)


def end_face_pt(sy, x, v, w):
    """Точка на скате торца: v — вниз по скату от верхней кромки, w — по нормали наружу."""
    top = Vector((x, sy * DECK_HY, Z_TOP))
    dn = Vector((0, sy * END_S.y, END_S.z))
    nr = Vector((0, -sy * END_S.z, END_S.y))
    return top + dn * v + nr * w


def grip_cutter(sy):
    """Выемка хвата: вырез в листе — верхняя стенка глубокая, стенки скошены как стенки короба,
    дно выходит к нижней кромке скруглением R 0.09 (гибка + фреза)."""
    v0, v1 = GRIP_V
    D, RL = 0.036, GRIP_RL                                     # глубина, скругление нижней кромки
    rows = [(v0, D), (v0 + GRIP_CH, D)]
    for k in range(17):                                        # перегиб листа: выпуклый у панели, вогнутый у дна
        u = k / 16
        rows.append((v1 - RL * (1 - u), max(D * (1 - (3 * u * u - 2 * u ** 3)), 0.0015)))
    rings = []
    for v, dd in rows:
        hw = grip_hw(v)
        sl = 0.45 * dd                                             # скос боковых стенок
        rings.append([end_face_pt(sy, -hw - 0.012, v, 0.03), end_face_pt(sy, hw + 0.012, v, 0.03),
                      end_face_pt(sy, hw - sl, v, -PANEL_D - dd), end_face_pt(sy, -hw + sl, v, -PANEL_D - dd)])
    # верхняя стенка — по нормали грани
    top = [end_face_pt(sy, -GRIP_HW - 0.012, v0 - 0.0005, 0.03), end_face_pt(sy, GRIP_HW + 0.012, v0 - 0.0005, 0.03),
           end_face_pt(sy, GRIP_HW - 0.0145, v0 - 0.0005, -PANEL_D - 0.032), end_face_pt(sy, -GRIP_HW + 0.0145, v0 - 0.0005, -PANEL_D - 0.032)]
    rings = [top] + rings
    bm = bmesh.new()
    vs = [[bm.verts.new(q) for q in r] for r in rings]
    for a, b in zip(vs, vs[1:]):
        for i in range(4):
            bm.faces.new([a[i], a[(i + 1) % 4], b[(i + 1) % 4], b[i]])
    bm.faces.new(vs[0][::-1])
    bm.faces.new(vs[-1])
    return hk.obj_from_bm(bm, 'grip')


def in_grip(c):
    sy = 1 if c.y > 0 else -1
    nr = Vector((0, -sy * END_S.z, END_S.y))
    d = c - Vector((0, sy * DECK_HY, Z_TOP))
    dn = Vector((0, sy * END_S.y, END_S.z))
    v, w = d.dot(dn), d.dot(nr)
    return GRIP_V[0] - 0.004 < v < GRIP_V[1] - 0.025 and abs(c.x) < grip_hw(min(max(v, GRIP_V[0]), GRIP_V[1])) and w < -PANEL_D - 0.005


DOOR_HX, DOOR_HY, DOOR_T = 0.128, 0.142, 0.010   # в игровом ракурсе (растяжка √2 по Y снимается) — квадрат
DOOR_GAP, DOOR_Z0 = 0.006, Z_TOP - 0.022          # проём в площадке; дверь лежит в нём ниже кромок
RIB_XS = (-0.100, -0.050, 0.0, 0.050, 0.100)
RIB_W0, RIB_W1, RIB_H, RIB_HY = 0.034, 0.022, 0.015, 0.118


def door_cutter():
    """Проём двери в площадке: гибы короба по периметру остаются выше плоскости двери."""
    hx, hy = DOOR_HX + DOOR_GAP, DOOR_HY + DOOR_GAP
    poly = hk.chamfer_poly([(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)], 0.024)
    o = hk.hull([(x, y, z) for x, y in poly for z in (DOOR_Z0 - 0.002, Z_TOP + 0.05)])
    hk.bevel(o, 0.004, 2, 30)
    return o


def build_door(M):
    """Дверь-люк на площадке: штампованная плита, рёбра жёсткости выдавлены в ней (трапеция, сбег 45° на концах).
    Рёбра — только на двери; плита и рёбра сварены одним мелким ремешем (галтели штампа)."""
    z0 = DOOR_Z0
    z1 = z0 + DOOR_T
    poly = hk.chamfer_poly([(-DOOR_HX, -DOOR_HY), (DOOR_HX, -DOOR_HY), (DOOR_HX, DOOR_HY), (-DOOR_HX, DOOR_HY)], 0.022)
    plate = hk.hull([(x, y, z) for x, y in poly for z in (z0, z1)])
    hk.bevel(plate, 0.003, 2, 30)
    parts = [plate]
    for x in RIB_XS:
        pts = []
        for z, w, hy in ((z1 - 0.002, RIB_W0 / 2, RIB_HY), (z1 + RIB_H, RIB_W1 / 2, RIB_HY - RIB_H)):
            for sx_ in (-1, 1):
                for sy_ in (-1, 1):
                    pts.append((x + sx_ * w, sy_ * hy, z))
        r = hk.hull(pts)
        hk.bevel(r, 0.0035, 2, 20)
        parts.append(r)
    d = hk.join(parts, 'door')
    hk.rs(d, 0.0012, it=2)
    return d


def visor_frame(sx):
    P = Vector((sx * BOX_HW, 0, Z_TOP))
    ds = Vector((sx * (HEX_HW - BOX_HW), 0, HEX_Z1 - Z_TOP)).normalized()     # вниз по скату наружу
    nu = Vector((sx * (Z_TOP - HEX_Z1), 0, HEX_HW - BOX_HW)).normalized()     # нормаль ската наружу
    return P, ds, nu


# накладка над пружиной (проход tex_07, рисунок 24): широкая пластина, по бокам — опущенные «лапы» с заклёпками
# (нижние наружные углы скошены), между ними — П-образный вырез вверх над пружиной, углы выреза скруглены.
# Координаты (y, s): y — по ходу, s — вниз по скату от верхней кромки площадки; (полуконтур y >= 0, третье — радиус).
VISOR_HALF = [(0.0, 0.030, 0.0), (0.060, 0.030, 0.012), (0.060, 0.080, 0.004), (0.086, 0.080, 0.006),
              (0.140, 0.058, 0.006), (0.140, -0.004, 0.003)]
VISOR_T, VISOR_W0 = 0.012, -0.002          # толщина листа, низ листа над скатом (чуть утоплен — без щели на просвет)
VISOR_RIVETS = [(-0.098, 0.022), (0.098, 0.022)]


def fillet_poly(pts, n=6):
    """Замкнутый многоугольник [(x, y, r)] -> точки со скруглёнными углами (r — радиус галтели, 0 — острый)."""
    out = []
    m = len(pts)
    for i in range(m):
        p = Vector(pts[i][:2])
        r = pts[i][2]
        if r <= 0:
            out.append(tuple(p))
            continue
        a, b = Vector(pts[i - 1][:2]), Vector(pts[(i + 1) % m][:2])
        da, db = (a - p).normalized(), (b - p).normalized()
        ang = math.acos(max(-1.0, min(1.0, da.dot(db))))
        t = r / math.tan(ang / 2)
        p0, p1 = p + da * t, p + db * t
        c = p + (da + db).normalized() * (r / math.sin(ang / 2))
        a0 = math.atan2(p0.y - c.y, p0.x - c.x)
        a1 = math.atan2(p1.y - c.y, p1.x - c.x)
        da_ = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(n + 1):
            q = a0 + da_ * k / n
            out.append((c.x + r * math.cos(q), c.y + r * math.sin(q)))
    return out


def visor_outline():
    half = VISOR_HALF[1:]
    full = [(-y, s_, r) for y, s_, r in reversed(half)] + half
    return fillet_poly(full)


def pocket_visor(sx):
    """Накладка над карманом пружины — листовая деталь (рисунок 24): лапы с заклёпками, П-вырез над пружиной.
    Контур — плита по нормали ската, мелкий ремеш + Smooth (кромки мягкие, без булевых)."""
    P, ds, nu = visor_frame(sx)
    Y = Vector((0, 1, 0))
    w0, w1 = VISOR_W0, VISOR_W0 + VISOR_T

    def pt(y, s_, w):
        return P + Y * y + ds * s_ + nu * w
    poly = visor_outline()
    bm = bmesh.new()
    lo = [bm.verts.new(pt(y, s_, w0)) for y, s_ in poly]
    hi = [bm.verts.new(pt(y, s_, w1)) for y, s_ in poly]
    bm.faces.new(lo)
    bm.faces.new(hi[::-1])
    for i in range(len(poly)):
        j = (i + 1) % len(poly)
        bm.faces.new([lo[i], lo[j], hi[j], hi[i]])
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    o = hk.obj_from_bm(bm, 'visor')
    hk.rs(o, VOX_FINE, it=3)
    return o


def build_visors(M):
    return hk.join([pocket_visor(-1), pocket_visor(1)], 'visors')


def build_visor_rivets(M):
    parts = []
    prof = hk.round_profile([(0, 0), (0.018, 0), (0.018, 0.004), (0.012, 0.010), (0, 0.011)], [0, 0.001, 0.004, 0.004, 0])
    for sx in (-1, 1):
        P, ds, nu = visor_frame(sx)
        for y, s_ in VISOR_RIVETS:
            parts.append(hk.lathe(prof, P + Vector((0, y, 0)) + ds * s_ + nu * (VISOR_W0 + VISOR_T - 0.002), nu, 48))
    return hk.join(parts, 'visor_rivets')


LUG_T, NUT_T = 0.020, 0.010
BUMP_Y, BUMP_Z = 0.402, 0.236      # труба бампера: проход 8 — на 20 мм наружу (треть сдвига прохода 6)


def lug(sx, sy):
    """Проушина пальца: лист 34 мм, приварен к торцу, обнимает палец."""
    P = pin_point(sx)
    pts = []
    for k in range(16):
        a = 2 * math.pi * k / 16
        pts.append((P.x + 0.028 * math.cos(a), P.z + 0.028 * math.sin(a)))
    pts += [(sx * 0.115, 0.40), (sx * 0.185, 0.40), (sx * 0.115, 0.36), (sx * 0.185, 0.36)]
    y0, y1 = sorted((sy * (END_Y - 0.004), sy * (END_Y + LUG_T)))
    o = hk.hull([(x, y, z) for x, z in pts for y in (y0, y1)])
    hk.bevel(o, 0.005, 2, 30)
    return o


def build_body(M):
    hexo, box = shell_parts()
    hk.bevel(hexo, 0.009, 4, 25)                 # гиб листа шатра — один радиус
    hk.bevel(box, 0.007, 3, 25)
    body = hk.boolean(hexo, box, 'UNION')
    print("body: union", len(body.data.polygons))
    for sx in (-1, 1):
        body = hk.boolean(body, pocket_cutter(sx))
        print("body: pocket", len(body.data.polygons))
    body = hk.boolean(body, door_cutter())
    for sy in (-1, 1):
        body = hk.boolean(body, panel_cutter(sy))
        body = hk.boolean(body, grip_cutter(sy))
        print("body: grip", len(body.data.polygons))
    parts = [body]
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(lug(sx, sy))
    body = hk.join(parts, 'body')
    hk.rs(body, VOX, it=2)

    def cls(c, nr):
        if in_pocket(c, -1) or in_pocket(c, 1) or in_grip(c):
            return 2
        return 0
    paint(body, [M["shell"], M["strap"], M["web"]], cls)
    recess_mask(body)
    return body


RECESS = "recess"      # атрибут точки 0..1: ручное затемнение выемок хвата и карманов пружин (tex.py)


def recess_mask(obj, it=6):
    """«Докрась руками»: точная маска затемнения выемок, без шума. Внутри выемки хвата и кармана пружины — по
    глубине под наружной поверхностью корпуса (плавно темнее к дну) плюс у верхней стенки и боковых углов выемки
    хвата; затем несколько проходов сглаживания по соседям — ровный градиент. Филёнка (10 мм) и проём двери не входят."""
    planes = shell_planes()
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()

    def sstep(a, b, x):
        t = min(max((x - a) / (b - a), 0.0), 1.0)
        return t * t * (3 - 2 * t)
    val = []
    for v in bm.verts:
        c = v.co
        m = 0.0
        sy = 1 if c.y > 0 else -1
        nr = Vector((0, -sy * END_S.z, END_S.y))
        dn = Vector((0, sy * END_S.y, END_S.z))
        d = c - Vector((0, sy * DECK_HY, Z_TOP))
        vv, ww = d.dot(dn), d.dot(nr)
        if GRIP_V[0] - 0.006 < vv < GRIP_V[1] + 0.004 and abs(c.x) < grip_hw(min(max(vv, GRIP_V[0]), GRIP_V[1])) + 0.008                 and ww < -PANEL_D + 0.002:
            depth = -ww - PANEL_D
            m = sstep(0.0, 0.034, depth)
            top = 1 - sstep(0.0, 0.05, vv - GRIP_V[0])                         # под верхней стенкой — глубже тень
            side = 1 - sstep(0.0, 0.05, grip_hw(min(max(vv, GRIP_V[0]), GRIP_V[1])) - abs(c.x))
            m *= 0.65 + 0.35 * max(top, side)
        else:
            for sx in (-1, 1):
                Q, n, u = pocket_frame(sx)
                dq = c - Q
                if -0.10 < dq.dot(n) < 0.215 and abs(dq.y) < POCKET_HY + 0.010 and dq.dot(u) < 0.03:
                    m = max(m, sstep(0.004, 0.07, shell_depth(c, planes)))
        val.append(m)
    adj = [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]
    for _ in range(it):
        val = [0.5 * val[i] + 0.5 * sum(val[j] for j in adj[i]) / max(len(adj[i]), 1) for i in range(len(val))]
    bm.free()
    at = me.attributes.new(RECESS, 'FLOAT', 'POINT')
    at.data.foreach_set("value", val)
    print("recess: %d verts > 0.1 of %d" % (sum(1 for x in val if x > 0.1), len(val)))


def build_pins(M):
    """Пого-контакты: на скате торца под выемкой, по нормали к грани — изолятор-втулка + латунный плунжер."""
    collars, plungers = [], []
    for sy in (-1, 1):
        nr = Vector((0, -sy * END_S.z, END_S.y))
        for x in (-0.075, 0.075):
            base = end_face_pt(sy, x, 0.236, -PANEL_D - 0.004)
            collars.append(hk.lathe([(0, 0), (0.031, 0), (0.031, 0.012), (0.026, 0.018), (0, 0.018)], base, nr, 48))
            prof = [(0, 0), (0.016, 0), (0.016, 0.026)] + [
                (0.016 * math.cos(math.pi / 2 * k / 6), 0.026 + 0.016 * math.sin(math.pi / 2 * k / 6)) for k in range(1, 7)]
            plungers.append(hk.lathe(prof, base, nr, 48))
    c = hk.join(collars, 'pin_collars')
    hk.rs(c, VOX_FINE * 0.7, it=2)
    q = hk.join(plungers, 'pin_plungers')
    hk.rs(q, VOX_FINE * 0.7, it=2)
    return c, q


def arc_y(x):
    """Ось дуги бампера: ровная парабола (вмятины — на текстуре)."""
    return BUMP_Y + 0.045 * (1 - (x / 0.215) ** 2)


def catmull(pts, n=8):
    """Гладкая кривая через точки (Катмулл-Ром) — гиб трубы."""
    P = [Vector(p) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2])
    return out


def ball(c, r):
    return hk.lathe([(0, -r)] + [(r * math.sin(math.pi * k / 16), -r * math.cos(math.pi * k / 16)) for k in range(1, 16)]
                    + [(0, r)], c, (0, 0, 1), 40)





def sweep_flare(path, rad, segs=40):
    """Труба по кривой в плоскости x = 0 с переменным сечением: rad(t) -> (rx, rn) — полуось вдоль X и по нормали.
    Расширение вдоль X у концов — кованый переход шеи в дугу и в лапу без видимого стыка."""
    P = [Vector(p) for p in path]
    L = [0.0]
    for a, b in zip(P, P[1:]):
        L.append(L[-1] + (b - a).length)
    X = Vector((1, 0, 0))
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(P):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        nn = t.cross(X).normalized()
        rx, rn = rad(L[i] / L[-1])
        rings.append([bm.verts.new(p + X * (rx * math.cos(2 * math.pi * k / segs)) + nn * (rn * math.sin(2 * math.pi * k / segs)))
                      for k in range(segs)])
    for a, b in zip(rings, rings[1:]):
        for k in range(segs):
            bm.faces.new([a[k], a[(k + 1) % segs], b[(k + 1) % segs], b[k]])
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    return hk.obj_from_bm(bm, 'neck')


NECK_R = 0.030                     # шея — та же труба, что дуга


def neck_rad(t):
    """Сечение шеи вдоль пути: у дуги раздаётся вдоль X (галтель ковки), в середине — круглая труба,
    у днища расплющена в лапу."""
    fa = math.exp(-(t / 0.11) ** 2)                       # переход в дугу
    fb = math.exp(-((1 - t) / 0.15) ** 2)                 # переход в лапу
    rx = NECK_R + 0.003 + 0.030 * fa + 0.024 * fb
    rn = NECK_R + 0.003 - 0.002 * fa - 0.014 * fb
    return rx, rn


def build_bumpers(M):
    """Бампер — жертвенный металл, одна кованая деталь: ровная дуга из трубы r 30 с загнутыми назад концами и одна
    шея по центру из той же трубы — раздаётся галтелью из дуги, поднимается к днищу и расплющивается в лапу;
    всё сварено одним ремешем, стыков не видно."""
    out = []
    for sy in (-1, 1):
        parts = []
        arc = [(x, arc_y(x), BUMP_Z) for x in [-0.215 + 0.43 * k / 12 for k in range(13)]]
        curl = lambda sx_: [(sx_ * 0.236, BUMP_Y - 0.022, BUMP_Z + 0.004), (sx_ * 0.244, BUMP_Y - 0.046, BUMP_Z + 0.010)]
        path = curl(-1)[::-1] + arc + curl(1)
        path = [(x, sy * y, z) for x, y, z in path]
        parts.append(hk.sweep(catmull(path, 6), 0.030, 40))
        for e in (path[0], path[-1]):
            parts.append(ball(e, 0.030))
        y0 = arc_y(0.0)
        neck = [(0, y0 - 0.004, BUMP_Z), (0, y0 - 0.034, BUMP_Z + 0.010), (0, y0 - 0.062, BUMP_Z + 0.042),
                (0, 0.372, Z_BOT - 0.030), (0, 0.346, Z_BOT - 0.014)]
        neck = [(x, sy * y, z) for x, y, z in neck]
        parts.append(sweep_flare(catmull(neck, 10), neck_rad))
        # лапа: конец шеи расплющен в плиту под днищем
        foot = [(dx, sy * y, z) for dx in (-0.050, 0.050) for y in (0.300, 0.385) for z in (Z_BOT - 0.016, Z_BOT + 0.002)]
        f = hk.hull(foot)
        hk.bevel(f, 0.008, 3, 30)
        parts.append(f)
        b = hk.join(parts, 'bumper')
        hk.rs(b, VOX_FINE, it=8)
        out.append(b)
    return hk.join(out, 'bumpers')


# ---------------------------------------------------------------- колесо
# обод: наружная грань a = -0.035 встречает рабочий конус (r + a = R) в виртуальном углу r 0.325; угол скруглён
# (касательные 45 мм) — низ обода r - a = 0.333, z 0.011 над ложем; наибольший радиус 0.306


def wheel_profile():
    """Токарный профиль (r, a): a — по оси внутрь. Обод с конусом 45° изнутри (внизу колеса он вертикален и
    обжимает лезвие), диск с проточкой, ступица. Галтели заданы явно: тело не ремешится, шейдинг аналитический."""
    R, h = R_WHEEL, T_WHEEL / 2
    h0 = 0.035                                                     # наружная грань как была; утолщение — внутрь
    pts = [(0, -0.030), (0.027, -0.030), (0.036, -0.021), (0.036, -0.011), (0.200, -0.011), (0.206, -0.016),
           (0.214, -0.016), (0.220, -0.011), (0.226, -0.011), (0.234, -h0), (R + h0, -h0),
           (R - 0.050, 0.050), (0.196, 0.050), (0.184, 0.030), (0.058, 0.030), (0.046, 0.040), (0.046, 0.056), (0, 0.056)]
    radii = [0, 0.004, 0.004, 0.004, 0.003, 0.002, 0.002, 0.003, 0.003, 0.004, 0.030, 0.004,
             0.004, 0.006, 0.005, 0.003, 0.003, 0]
    return hk.round_profile(pts, radii)


def build_wheel(sx, M):
    C, n, u = frame(sx)
    w = hk.lathe(wheel_profile(), C, n, 192, ref=(0, 1, 0))

    def cls(c, nr):
        r = ((c - C) - n * (c - C).dot(n)).length
        return 0 if r > 0.225 or r < 0.052 else 1
    paint(w, [M["rim"], M["web"]], cls)
    # колпак ступицы — тело вращения (колесо осесимметрично: любой поворот выглядит одинаково)
    nut = hk.lathe(hk.round_profile([(0, 0), (0.032, 0), (0.032, 0.014), (0.024, 0.022), (0.018, 0.022),
                                     (0.018, 0.030), (0, 0.030)], [0, 0.002, 0.003, 0.003, 0.002, 0.003, 0]),
                   C - n * 0.028, -n, 96)
    washer = hk.cyl(C + n * 0.055, n, 0.040, A_CHEEK - CHEEK_T / 2 - 0.054, segs=64)
    hk.bevel(washer, 0.002, 2, 30)
    return w, nut, washer


# ---------------------------------------------------------------- щека
CHEEK_TOP = [(-0.385, 0.140), (-0.270, 0.140), (-0.210, 0.195), (-0.140, 0.226), (0.140, 0.226), (0.210, 0.195),
             (0.270, 0.140), (0.385, 0.140)][::-1]     # ломаный низкий горб над колесом, крылья


def cheek_outline():
    p = [(-CHEEK_HY, 0.0), (CHEEK_HY, 0.0)] + CHEEK_TOP[::-1]
    return p


def plane_pt(sx, y, s, a):
    C, n, u = frame(sx)
    return C + Vector((0, y, 0)) + u * s + n * a


def build_cheek(sx, M):
    C, n, u = frame(sx)
    P = pin_point(sx)
    poly = hk.chamfer_poly(cheek_outline(), 0.012)
    plate = hk.prism(poly, P, (0, 1, 0), u, CHEEK_T)
    hk.bevel(plate, 0.004, 2, 30)
    parts = [plate]
    # отбортовка верхней кромки внутрь (к корпусу): жёсткость листа + упор для пружины
    top = CHEEK_TOP
    for (y0, s0), (y1, s1) in zip(top, top[1:]):
        q = [plane_pt(sx, y, s, A_CHEEK + CHEEK_T / 2 - 0.003 + d) for (y, s) in ((y0, s0), (y1, s1))
             for d in (0.0, 0.022)]
        q += [p - u * 0.010 for p in q]
        f = hk.hull(q)
        parts.append(f)
    # низ свёрнут в петлю на пальце — два кулака
    for s in (-1, 1):
        y0, y1 = sorted((s * 0.07, s * (CHEEK_HY - 0.006)))
        parts.append(hk.cyl(P + Vector((0, y0, 0)), (0, 1, 0), 0.023, y1 - y0, segs=48))
    # литой узел: ось колеса крест-накрест через палец
    parts.append(hk.cyl(C + n * (A_CHEEK - 0.014), n, 0.040, 0.046, segs=64))
    # гнездо пружины на отбортовке
    parts.append(hk.cyl(plane_pt(sx, 0, SPRING_S, A_CHEEK), n, 0.045, CHEEK_T / 2 + 0.015, segs=64))
    ch = hk.join(parts, 'cheek')
    hk.rs(ch, VOX_FINE, it=1)
    # таблички на крыльях щеки (обе стороны крыла): оранжевая + стальная, на заклёпках
    tabs, plates, rivets = [], [], []
    for s, face in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        yc = s * 0.335
        o = hk.prism(hk.chamfer_poly([(-0.033, 0.0), (0.033, 0.0), (0.033, 0.045), (-0.033, 0.045)], 0.006),
                     plane_pt(sx, yc, 0.085, A_CHEEK + face * (CHEEK_T / 2 + 0.002)), (0, 1, 0), u, 0.006)
        hk.bevel(o, 0.0015, 1, 30)
        tabs.append(o)
        o = hk.prism(hk.chamfer_poly([(-0.033, 0.0), (0.033, 0.0), (0.033, 0.035), (-0.033, 0.035)], 0.006),
                     plane_pt(sx, yc, 0.035, A_CHEEK + face * (CHEEK_T / 2 + 0.002)), (0, 1, 0), u, 0.006)
        hk.bevel(o, 0.0015, 1, 30)
        plates.append(o)
        for dy in (-0.024, 0.024):
            for ss in (0.052, 0.108):
                rivets.append(hk.lathe([(0, 0), (0.0045, 0), (0.0042, 0.002), (0.0025, 0.0035), (0, 0.004)],
                                       plane_pt(sx, yc + dy, ss, A_CHEEK + face * (CHEEK_T / 2 + 0.004)), n * face, 16))
    return ch, hk.join(tabs, 'tabs'), hk.join(plates, 'tab_plates'), hk.join(rivets, 'rivets')


def build_pin(sx, M):
    P = pin_point(sx)
    L = END_Y + LUG_T + NUT_T + 0.003
    rod = hk.cyl(P + Vector((0, -L, 0)), (0, 1, 0), 0.0125, 2 * L, segs=32)
    nuts = []
    for sy in (-1, 1):
        y0 = sy * (END_Y + LUG_T) if sy > 0 else -(END_Y + LUG_T) - NUT_T
        nt = hk.cyl(P + Vector((0, y0, 0)), (0, 1, 0), 0.024, NUT_T, segs=8, ref=(0, 0, 1), phase=math.pi / 8)
        hk.bevel(nt, 0.0025, 2, 30)
        nuts.append(nt)
    return rod, hk.join(nuts, 'pin_nuts')


def build_spring(sx, M):
    """Пружина как на драфте: 2 витка, квадратная проволока 0.03, наружный диаметр 0.11, высота 0.15;
    концы поджаты (по четверти витка без шага)."""
    C, n, u = frame(sx)
    Q = C + n * (A_CHEEK + CHEEK_T / 2 + 0.015) + u * SPRING_S
    a, L, turns = 0.030, 0.150, 2.0
    Rc = 0.110 / 2 - a / 2
    b1 = Vector((0, 1, 0))
    b2 = n.cross(b1)
    N = int(turns * 48)
    e = 0.25
    bm = bmesh.new()
    rings = []
    for k in range(N + 1):
        tt = turns * k / N
        if tt < e:
            h = 0.0
        elif tt > turns - e:
            h = L - a
        else:
            h = (L - a) * (tt - e) / (turns - 2 * e)
        ang = 2 * math.pi * tt
        r = b1 * math.cos(ang) + b2 * math.sin(ang)
        c = Q + n * (h + 0.004 + a / 2) + r * Rc
        rings.append([bm.verts.new(c + r * dr * a / 2 + n * dz * a / 2) for dr, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for p, q in zip(rings, rings[1:]):
        for i in range(4):
            bm.faces.new([p[i], p[(i + 1) % 4], q[(i + 1) % 4], q[i]])
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    sp = hk.obj_from_bm(bm, 'spring')
    hk.bevel(sp, 0.004, 2, 60)
    seat = hk.cyl(Q + n * (L + 0.004), n, 0.058, 0.008, segs=64)       # упорная шайба на дне кармана
    hk.bevel(seat, 0.002, 2, 30)
    return sp, seat


# ---------------------------------------------------------------- сборка
def paint(obj, mlist, fn):
    me = obj.data
    me.materials.clear()
    for m in mlist:
        me.materials.append(m)
    bm = bmesh.new()
    bm.from_mesh(me)
    for f in bm.faces:
        f.material_index = fn(f.calc_center_median(), f.normal)
    bm.to_mesh(me)
    bm.free()


def finish(obj, name, coll, parent, mat=None, origin=(0, 0, 0), smooth=True, angle=None):
    """В коллекцию ассета: начало координат на своей оси, затенение гладкое (или по углу для граней-фасок)."""
    obj.name = name
    obj.data.name = name
    if mat is not None:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    o = Vector(origin)
    obj.data.transform(Matrix.Translation(-o))
    if parent is not None:
        obj.location = o - parent.matrix_world.translation
    else:
        obj.location = o
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    obj.parent = parent
    me = obj.data
    me.shade_smooth()
    if angle is not None:
        me.set_sharp_from_angle(angle=math.radians(angle))
    bpy.context.view_layer.update()
    return obj


def report(objs):
    faces = sum(len(o.data.polygons) for o in objs)
    print("body faces total %d in %d objects" % (faces, len(objs)))


def main():
    K.reset_scene()
    bpy.context.preferences.filepaths.save_version = 0
    hk.WORK.append(K.collection("WORK"))
    M = mats()
    for k in ("base", "bed", "blade"):
        M[k].use_fake_user = True                 # подложка-болванка рельса для render.py
    coll = K.collection("CART_A")
    root = K.empty("CART_A_root", coll)
    out = []

    body = finish(build_body(M), "body", coll, root)
    out.append(body)
    c, p = build_pins(M)
    out.append(finish(c, "pogo_collars", coll, body, M["rubber"]))
    out.append(finish(p, "pogo_pins", coll, body, M["brass"]))
    out.append(finish(build_bumpers(M), "bumpers", coll, body, M["steel"]))
    out.append(finish(build_door(M), "door", coll, body, M["lid"]))
    out.append(finish(build_visors(M), "visors", coll, body, M["visor"]))
    out.append(finish(build_visor_rivets(M), "visor_rivets", coll, body, M["steel"]))

    for sx, side in ((-1, "L"), (1, "R")):
        C, n, u = frame(sx)
        P = pin_point(sx)
        rod, nuts = build_pin(sx, M)
        out.append(finish(rod, "pin_" + side, coll, body, M["steel"], origin=P))
        out.append(finish(nuts, "pin_nuts_" + side, coll, body, M["brass"], origin=P, angle=40))
        ch, tabs, plates, rivets = build_cheek(sx, M)
        cheek = finish(ch, "cheek_" + side, coll, body, M["shell"], origin=P)        # качается вокруг пальца (ось Y)
        out.append(cheek)
        out.append(finish(tabs, "tabs_" + side, coll, cheek, M["orange"], origin=P, angle=40))
        out.append(finish(plates, "tab_plates_" + side, coll, cheek, M["plate"], origin=P, angle=40))
        out.append(finish(rivets, "rivets_" + side, coll, cheek, M["steel"], origin=P))
        w, nut, washer = build_wheel(sx, M)
        wheel = finish(w, "wheel_" + side, coll, cheek, origin=C, angle=30)                     # крутится вокруг n
        out.append(wheel)
        out.append(finish(nut, "hub_nut_" + side, coll, wheel, M["brass"], origin=C))
        out.append(finish(washer, "washer_" + side, coll, cheek, M["brass"], origin=C, angle=40))
        sp, seat = build_spring(sx, M)
        out.append(finish(sp, "spring_" + side, coll, body, M["brass"], angle=50))
        out.append(finish(seat, "spring_seat_" + side, coll, body, M["brass"], angle=40))

    report(out)
    for o in list(hk.WORK[0].objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(hk.WORK[0])
    for o in out:
        assert o.data.polygons, o.name
    zs = [(o.matrix_world @ o.data.vertices[i].co).z for o in out for i in range(0, len(o.data.vertices), 50)]
    print("z range %.3f .. %.3f" % (min(zs), max(zs)))
    K.collection("CART_A", exclude=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "cart_hp2.blend"))
    print("saved cart_hp2.blend")


main()
