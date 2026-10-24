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
END_Y, END_Z = 0.40, 0.45            # торец: вертикаль до END_Z, дальше скат к площадке
DECK_HY = 0.16                       # полудлина площадки по ходу
PLAN_CH = 0.08                       # срез углов в плане

R_WHEEL, T_WHEEL = 0.29, 0.055
WHEEL_X, WHEEL_Z = 0.2275, 0.231     # центр колеса: коническая кромка вертикальна у y = ±лезвие
A_CHEEK = 0.059                      # плоскость щеки от плоскости колеса (палец лежит в ней)
CHEEK_T = 0.020
CHEEK_HY = 0.385
STRAP_Y, STRAP_W = 0.11, 0.025
POCKET_HY = 0.07
SPRING_S = 0.212                     # гнездо пружины на щеке (вверх по скату от пальца)


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
    s = Vector((0, 0.158, 0.24)).normalized()          # скат торца: от (y .40, z .45) к (.16, .608)
    pl = []
    for sy in (-1, 1):
        pl.append(((0, sy * END_Y, 0), (0, sy, 0)))
        pl.append(((0, sy * END_Y, END_Z), (0, sy * s.y, s.z)))
    for sx in (-1, 1):
        for sy in (-1, 1):
            pl.append(((sx * (HEX_HW - PLAN_CH), sy * END_Y, 0), (sx * S2, sy * S2, 0)))
    return pl


def shell_parts():
    up = Vector((HEX_HW - BOX_HW, 0, -(Z_TOP - HEX_Z1))).normalized()   # не используется напрямую
    del up
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
    hexo = hk.polytope(planes_hex + end_planes())
    planes_box = [((0, 0, Z_BOT), (0, 0, -1)), ((0, 0, HEX_ZL + 0.03), (0, 0, 1))]
    for sx in (-1, 1):
        planes_box.append(((sx * BOX_HW, 0, 0), (sx, 0, 0)))
    box = hk.polytope(planes_box + end_planes())
    return hexo, box


def pocket_cutter(sx):
    """Карман пружины: фрезерован вдоль оси пружины, дно-упор у кромки площадки."""
    C, n, u = frame(sx)
    Q = C + n * (A_CHEEK + CHEEK_T / 2 + 0.015) + u * SPRING_S
    o = hk.hbox((-0.06, -POCKET_HY, -0.045), (0.183, POCKET_HY, 0.20))
    # локальные оси бокса: x -> n, y -> Y, z -> u
    M = Matrix(((n.x, 0, u.x, Q.x), (n.y, 1, u.y, Q.y), (n.z, 0, u.z, Q.z), (0, 0, 0, 1)))
    hk.transform(o, M)
    hk.bevel(o, 0.014, 4, 30)
    return o


def grip_cutter(sy):
    """Выемка хвата на скате торца: горизонтальный паз с козырьком сверху."""
    lo, hi = (-0.145, 0.225, 0.512), (0.145, 0.60, 0.552)
    if sy < 0:
        lo, hi = (-0.145, -0.60, 0.512), (0.145, -0.225, 0.552)
    o = hk.hbox(lo, hi)
    hk.bevel(o, 0.012, 4, 30)
    return o


def strap(y):
    """Хомут-ребро поверх бокового ската (полоса 25 мм, лист 10 мм), концы под крышкой и у широкой кромки."""
    out = [(-HEX_HW - 0.010, 0.474), (-HEX_HW - 0.010, HEX_Z1 + 0.004), (-BOX_HW - 0.004, Z_TOP + 0.010),
           (BOX_HW + 0.004, Z_TOP + 0.010), (HEX_HW + 0.010, HEX_Z1 + 0.004), (HEX_HW + 0.010, 0.474)]
    inn = [(HEX_HW - 0.012, 0.474), (HEX_HW - 0.012, HEX_Z1 - 0.004), (BOX_HW - 0.004, Z_TOP - 0.012),
           (-BOX_HW + 0.004, Z_TOP - 0.012), (-HEX_HW + 0.012, HEX_Z1 - 0.004), (-HEX_HW + 0.012, 0.474)]
    o = hk.prism(out + inn, (0, y, 0), (1, 0, 0), (0, 0, 1), STRAP_W)
    hk.bevel(o, 0.004, 2, 30)
    return o


def lug(sx, sy):
    """Проушина пальца: лист 34 мм, приварен к торцу, обнимает палец."""
    P = pin_point(sx)
    pts = []
    for k in range(16):
        a = 2 * math.pi * k / 16
        pts.append((P.x + 0.028 * math.cos(a), P.z + 0.028 * math.sin(a)))
    pts += [(sx * 0.115, 0.40), (sx * 0.185, 0.40), (sx * 0.115, 0.36), (sx * 0.185, 0.36)]
    y0, y1 = sorted((sy * (END_Y - 0.004), sy * (END_Y + 0.034)))
    o = hk.hull([(x, y, z) for x, z in pts for y in (y0, y1)])
    hk.bevel(o, 0.005, 2, 30)
    return o


def build_body(M):
    hexo, box = shell_parts()
    hk.bevel(hexo, 0.014, 4, 25)
    hk.bevel(box, 0.010, 3, 25)
    body = hk.boolean(hexo, box, 'UNION')
    for sx in (-1, 1):
        body = hk.boolean(body, pocket_cutter(sx))
    for sy in (-1, 1):
        body = hk.boolean(body, grip_cutter(sy))
    parts = [body]
    for y in (-STRAP_Y, STRAP_Y):
        parts.append(strap(y))
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(lug(sx, sy))
    body = hk.join(parts, 'body')
    hk.rs(body, VOX, it=4)
    paint(body, [M["shell"], M["strap"]],
          lambda c, nr: 1 if (abs(abs(c.y) - STRAP_Y) < STRAP_W / 2 + 0.002 and c.z > 0.47) else 0)
    return body


def build_lid(M):
    """Штампованная крышка площадки: плита + 5 выдавленных рёбер, одним ремешем."""
    poly = hk.chamfer_poly([(-0.15, -0.14), (0.15, -0.14), (0.15, 0.14), (-0.15, 0.14)], 0.02)
    lid = hk.prism(poly, (0, 0, Z_TOP - 0.004), (1, 0, 0), (0, 1, 0), 0.018, center=False)
    hk.bevel(lid, 0.005, 3, 30)
    parts = [lid]
    for x in (-0.112, -0.056, 0.0, 0.056, 0.112):
        parts.append(hk.sweep([(x, -0.12, Z_TOP + 0.014), (x, 0.12, Z_TOP + 0.014)], 0.012, 24))
        for y in (-0.12, 0.12):
            parts.append(hk.lathe([(0, -0.012)] + [(0.012 * math.sin(math.pi * k / 12), -0.012 * math.cos(math.pi * k / 12))
                                                   for k in range(1, 12)] + [(0, 0.012)],
                                  (x, y, Z_TOP + 0.014), (0, 0, 1), 24))
    o = hk.join(parts, 'lid')
    hk.rs(o, VOX_FINE, it=3)
    paint(o, [M["lid"], M["rib"]], lambda c, nr: 1 if c.z > Z_TOP + 0.017 else 0)
    bolts = []
    for x in (-0.135, 0.135):
        for y in (-0.105, 0.105):
            b = hk.cyl((x, y, Z_TOP + 0.012), (0, 0, 1), 0.008, 0.007, segs=6)
            hk.bevel(b, 0.0015, 1, 30)
            bolts.append(b)
    bo = hk.join(bolts, 'lid_bolts')
    return o, bo


def build_pins(M):
    """Пого-контакты на торцах: изолятор-втулка + латунный плунжер со сферой."""
    collars, plungers = [], []
    for sy in (-1, 1):
        for x in (-0.07, 0.07):
            base = (x, sy * (END_Y - 0.006), 0.43)
            collars.append(hk.lathe([(0, 0), (0.021, 0), (0.021, 0.014), (0.017, 0.019), (0, 0.019)], base, (0, sy, 0), 48))
            prof = [(0, 0), (0.0105, 0), (0.0105, 0.030)] + [
                (0.0105 * math.cos(math.pi / 2 * k / 6), 0.030 + 0.0105 * math.sin(math.pi / 2 * k / 6)) for k in range(1, 7)]
            plungers.append(hk.lathe(prof, base, (0, sy, 0), 48))
    c = hk.join(collars, 'pin_collars')
    hk.rs(c, VOX_FINE * 0.7, it=2)
    p = hk.join(plungers, 'pin_plungers')
    hk.rs(p, VOX_FINE * 0.7, it=2)
    return c, p


def build_bumpers(M):
    """Бампер-труба по дуге на литом кронштейне от днища; резиновые накладки по бокам от кронштейна."""
    tubes, pads = [], []
    for sy in (-1, 1):
        pts = []
        for k in range(25):
            x = -0.205 + 0.41 * k / 24
            pts.append((x, sy * (0.432 + 0.040 * (1 - (x / 0.205) ** 2)), 0.28))
        parts = [hk.sweep(pts, 0.030, 32)]
        for e in (pts[0], pts[-1]):
            parts.append(hk.lathe([(0, -0.030)] + [(0.030 * math.sin(math.pi * k / 16), -0.030 * math.cos(math.pi * k / 16))
                                                   for k in range(1, 16)] + [(0, 0.030)], e, (0, 0, 1), 32))
        arm = [(x, sy * y, z) for x in (-0.04, 0.04) for y, z in ((0.30, 0.352), (0.40, 0.352), (0.30, 0.335))] + \
              [(x, sy * y, z) for x in (-0.03, 0.03) for y, z in ((0.44, 0.30), (0.47, 0.30), (0.44, 0.262), (0.47, 0.262))]
        a = hk.hull(arm)
        hk.bevel(a, 0.010, 3, 30)
        parts.append(a)
        tubes.append(hk.join(parts, 'bumper'))
        for s in (-1, 1):
            seg = [p for p in pts if 0.055 < s * p[0] < 0.175]
            pads.append(hk.sweep(seg, 0.035, 32))
    t = hk.join(tubes, 'bumpers')
    hk.rs(t, VOX_FINE, it=8)
    pd = hk.join(pads, 'bumper_pads')
    hk.rs(pd, VOX_FINE, it=8)
    return t, pd


# ---------------------------------------------------------------- колесо
def wheel_profile():
    """Токарный профиль (r, a): a — по оси внутрь. Обод с конусом 45° изнутри (внизу колеса он вертикален и
    обжимает лезвие), диск с проточкой, ступица. Галтели заданы явно: тело не ремешится, шейдинг аналитический."""
    R, h = R_WHEEL, T_WHEEL / 2
    pts = [(0, -0.030), (0.027, -0.030), (0.036, -0.021), (0.036, -0.011), (0.200, -0.011), (0.206, -0.016),
           (0.214, -0.016), (0.220, -0.011), (0.226, -0.011), (0.230, -h), (R, -h), (R, 0.0), (R - h, h),
           (0.234, h), (0.226, 0.012), (0.058, 0.012), (0.046, 0.024), (0.046, 0.040), (0, 0.040)]
    radii = [0, 0.004, 0.004, 0.004, 0.003, 0.002, 0.002, 0.003, 0.003, 0.003, 0.009, 0.003, 0.004,
             0.003, 0.004, 0.005, 0.003, 0.003, 0]
    return hk.round_profile(pts, radii)


def build_wheel(sx, M):
    C, n, u = frame(sx)
    w = hk.lathe(wheel_profile(), C, n, 192, ref=(0, 1, 0))

    def cls(c, nr):
        r = ((c - C) - n * (c - C).dot(n)).length
        return 0 if r > 0.225 or r < 0.052 else 1
    paint(w, [M["rim"], M["web"]], cls)
    bolts = []
    for k in range(6):
        a = 2 * math.pi * k / 6
        p = C + (Vector((0, 1, 0)) * math.cos(a) + n.cross(Vector((0, 1, 0))) * math.sin(a)) * 0.078
        b = hk.cyl(p - n * 0.009, -n, 0.009, 0.008, segs=6)
        hk.bevel(b, 0.0015, 1, 30)
        bolts.append(b)
    nut = hk.cyl(C - n * 0.028, -n, 0.030, 0.020, segs=8, ref=(0, 1, 0), phase=math.pi / 8)
    hk.bevel(nut, 0.003, 2, 30)
    cap = hk.lathe([(0, 0), (0.017, 0), (0.017, 0.006), (0.012, 0.010), (0, 0.011)], C - n * 0.047, -n, 32)
    washer = hk.cyl(C + n * 0.039, n, 0.040, 0.0095, segs=64)
    hk.bevel(washer, 0.002, 2, 30)
    return w, hk.join(bolts, 'wheel_bolts'), hk.join([nut, cap], 'hub_nut'), washer


# ---------------------------------------------------------------- щека
def cheek_outline():
    p = [(-CHEEK_HY, 0.0), (CHEEK_HY, 0.0), (CHEEK_HY, 0.17), (0.28, 0.17), (0.18, 0.262), (-0.18, 0.262),
         (-0.28, 0.17), (-CHEEK_HY, 0.17)]
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
    top = [(CHEEK_HY, 0.17), (0.28, 0.17), (0.18, 0.262), (-0.18, 0.262), (-0.28, 0.17), (-CHEEK_HY, 0.17)]
    for (y0, s0), (y1, s1) in zip(top, top[1:]):
        q = [plane_pt(sx, y, s, A_CHEEK + CHEEK_T / 2 - 0.004 + d) for (y, s) in ((y0, s0), (y1, s1))
             for d in (0.0, 0.030)]
        q += [p - u * 0.013 for p in q]
        f = hk.hull(q)
        parts.append(f)
    # низ свёрнут в петлю на пальце — два кулака
    for s in (-1, 1):
        y0, y1 = sorted((s * 0.07, s * (CHEEK_HY - 0.006)))
        parts.append(hk.cyl(P + Vector((0, y0, 0)), (0, 1, 0), 0.023, y1 - y0, segs=48))
    # литой узел: ось колеса крест-накрест через палец
    parts.append(hk.cyl(C + n * 0.046, n, 0.040, 0.050, segs=64))
    # гнездо пружины на отбортовке
    parts.append(hk.cyl(plane_pt(sx, 0, SPRING_S, A_CHEEK), n, 0.045, CHEEK_T / 2 + 0.015, segs=64))
    ch = hk.join(parts, 'cheek')
    hk.rs(ch, VOX_FINE, it=3)
    # таблички на наружной стороне у концов щеки: оранжевая + стальная, на заклёпках
    tabs, plates, rivets = [], [], []
    for s in (-1, 1):
        yc = s * 0.335
        o = hk.prism(hk.chamfer_poly([(-0.033, 0.0), (0.033, 0.0), (0.033, 0.045), (-0.033, 0.045)], 0.006),
                     plane_pt(sx, yc, 0.105, A_CHEEK - CHEEK_T / 2 - 0.002), (0, 1, 0), u, 0.006)
        hk.bevel(o, 0.0015, 1, 30)
        tabs.append(o)
        o = hk.prism(hk.chamfer_poly([(-0.033, 0.0), (0.033, 0.0), (0.033, 0.035), (-0.033, 0.035)], 0.006),
                     plane_pt(sx, yc, 0.055, A_CHEEK - CHEEK_T / 2 - 0.002), (0, 1, 0), u, 0.006)
        hk.bevel(o, 0.0015, 1, 30)
        plates.append(o)
        for dy in (-0.024, 0.024):
            for ss in (0.072, 0.128):
                rivets.append(hk.lathe([(0, 0), (0.0045, 0), (0.0042, 0.002), (0.0025, 0.0035), (0, 0.004)],
                                       plane_pt(sx, yc + dy, ss, A_CHEEK - CHEEK_T / 2 - 0.004), -n, 16))
    return ch, hk.join(tabs, 'tabs'), hk.join(plates, 'tab_plates'), hk.join(rivets, 'rivets')


def build_pin(sx, M):
    P = pin_point(sx)
    rod = hk.cyl(P + Vector((0, -0.452, 0)), (0, 1, 0), 0.0125, 0.904, segs=32)
    nuts = []
    for sy in (-1, 1):
        y0 = sy * (END_Y + 0.034) if sy > 0 else -(END_Y + 0.034) - 0.016
        nt = hk.cyl(P + Vector((0, y0, 0)), (0, 1, 0), 0.024, 0.016, segs=8, ref=(0, 0, 1), phase=math.pi / 8)
        hk.bevel(nt, 0.0025, 2, 30)
        nuts.append(nt)
    return rod, hk.join(nuts, 'pin_nuts')


def build_spring(sx, M):
    """Пружина сжатия вдоль оси колеса: от гнезда на щеке до упора кармана; крайние витки поджаты."""
    C, n, u = frame(sx)
    Q = C + n * (A_CHEEK + CHEEK_T / 2 + 0.015) + u * SPRING_S
    Rc, wire, L, turns = 0.031, 0.0075, 0.175, 5.0
    b1 = Vector((0, 1, 0))
    b2 = n.cross(b1)
    pts = []
    N = int(turns * 32)
    for k in range(N + 1):
        t = k / N
        ang = 2 * math.pi * turns * t
        # поджатые концы: первый и последний полувиток почти без шага
        tt = t * turns
        if tt < 0.6:
            h = wire * tt / 0.6
        elif tt > turns - 0.6:
            h = L - wire - wire * (turns - tt) / 0.6 + wire
        else:
            h = wire + (L - 2 * wire) * (tt - 0.6) / (turns - 1.2)
        pts.append(Q + n * (h + 0.004) + (b1 * math.cos(ang) + b2 * math.sin(ang)) * Rc)
    sp = hk.sweep(pts, wire, 16)
    hk.rs(sp, 0.0012, it=2)
    seat = hk.cyl(Q + n * (L + 0.004), n, 0.037, 0.008, segs=48)       # упорная шайба на дне кармана
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
    lid, lid_bolts = build_lid(M)
    out.append(finish(lid, "lid", coll, body))
    out.append(finish(lid_bolts, "lid_bolts", coll, body, M["steel"], angle=40))
    c, p = build_pins(M)
    out.append(finish(c, "pogo_collars", coll, body, M["rubber"]))
    out.append(finish(p, "pogo_pins", coll, body, M["brass"]))
    t, pd = build_bumpers(M)
    out.append(finish(t, "bumpers", coll, body, M["steel"]))
    out.append(finish(pd, "bumper_pads", coll, body, M["orange"]))

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
        w, bolts, nut, washer = build_wheel(sx, M)
        wheel = finish(w, "wheel_" + side, coll, cheek, origin=C, angle=30)                     # крутится вокруг n
        out.append(wheel)
        out.append(finish(bolts, "wheel_bolts_" + side, coll, wheel, M["steel"], origin=C, angle=40))
        out.append(finish(nut, "hub_nut_" + side, coll, wheel, M["brass"], origin=C, angle=40))
        out.append(finish(washer, "washer_" + side, coll, cheek, M["brass"], origin=C, angle=40))
        sp, seat = build_spring(sx, M)
        out.append(finish(sp, "spring_" + side, coll, body, M["brass"]))
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
