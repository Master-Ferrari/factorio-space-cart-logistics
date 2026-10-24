# -*- coding: utf-8 -*-
"""Раунд 2 блокинга: «технически продвинутый стальной ящик» на разных ходовых.

Общий язык — ванильный стальной сундук: тёмная сталь, светлые угловые стойки и
обвязка по верху, светлая плита крышки, тёмный пояс по бокам. «Продвинутость» —
пять огоньков слотов на крышке (число слотов = качество каретки, 1..5) и фонарь
спереди. Ходовая и форма базы — то, чем отличаются концепты.
"""

import math

import scl3d as K
from parts import couplers, pinch_rollers

RT = K.RAIL_TOP_Z
D45 = math.radians(45)
D90 = math.radians(90)
TUNNEL = (0.055, 0.17)            # полуширина и высота тоннеля под рельс в днище


def tunnel_profile(hw, z0, z1, tunnel=TUNNEL):
    tw, th = tunnel
    return [(-hw, z0), (-tw, z0), (-tw, th), (tw, th), (tw, z0), (hw, z0), (hw, z1), (-hw, z1)]


def clip_x(pts, c, side):
    """Отсечение многоугольника полуплоскостью side·x >= c (Сазерленд — Ходжмен)."""
    out = []
    n = len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        ip, iq = side * p[0] >= c, side * q[0] >= c
        if ip:
            out.append(p)
        if ip != iq:
            t = (c * side - p[0]) / (q[0] - p[0])
            out.append((c * side, p[1] + (q[1] - p[1]) * t))
    return out


def lid(c, root, M, p, w, l, z1, y=0.0):
    """Обвязка по верху, плита крышки, огоньки слотов, фонарь."""
    hw, hl = w / 2, l / 2
    for s in (-1, 1):
        K.box(p + "rim_y%+d" % s, c, (w, 0.05, 0.03), loc=(0, y + s * (hl - 0.025), z1),
              mat=M["chest_lt"], parent=root, bevel=0.008)
        K.box(p + "rim_x%+d" % s, c, (0.05, l, 0.03), loc=(s * (hw - 0.025), y, z1),
              mat=M["chest_lt"], parent=root, bevel=0.008)
    K.box(p + "plate", c, (w - 0.15, l - 0.15, 0.02), loc=(0, y, z1 + 0.005), mat=M["chest_lt"],
          parent=root, bevel=0.006)
    K.box(p + "seal", c, (w - 0.26, l - 0.26, 0.02), loc=(0, y, z1 + 0.015), mat=M["chest"],
          parent=root, bevel=0.004)
    for i in range(5):
        K.box(p + "slot%d" % i, c, (0.032, 0.022, 0.012), loc=(-0.09 + 0.045 * i, y + hl - 0.06, z1 + 0.018),
              mat=M["glow"] if i < 3 else M["frame"], parent=root)


def chest(c, root, M, p, w, l, z0, z1, y=0.0, tunnel=None, posts=True, band=True, top=True):
    hw, hl = w / 2, l / 2
    if tunnel:
        K.profile_sweep_y(p + "core", c, tunnel_profile(hw, z0, z1, tunnel), y - hl, y + hl,
                          mat=M["chest"], parent=root, bevel=0.01)
    else:
        K.box(p + "core", c, (w, l, z1 - z0), loc=(0, y, (z0 + z1) / 2), mat=M["chest"], parent=root, bevel=0.01)
    h = z1 - z0
    if posts:
        for sx in (-1, 1):
            for sy in (-1, 1):
                K.box(p + "post%+d%+d" % (sx, sy), c, (0.06, 0.06, h + 0.01),
                      loc=(sx * (hw - 0.022), y + sy * (hl - 0.022), (z0 + z1) / 2),
                      mat=M["chest_lt"], parent=root, bevel=0.01)
    if band:
        zb = z0 + h * 0.42
        for s in (-1, 1):
            K.box(p + "band_x%+d" % s, c, (0.014, l - 0.10, 0.04), loc=(s * (hw + 0.004), y, zb),
                  mat=M["frame"], parent=root)
            K.box(p + "band_y%+d" % s, c, (w - 0.10, 0.014, 0.04), loc=(0, y + s * (hl + 0.004), zb),
                  mat=M["frame"], parent=root)
    if top:
        lid(c, root, M, p, w, l, z1, y)
    K.box(p + "lamp", c, (0.09, 0.02, 0.03), loc=(0, y + hl + 0.006, z1 - 0.05), mat=M["lamp"], parent=root)


def hidden_rollers(c, root, M, ys=(-0.2, 0.2)):
    pinch_rollers(c, root, M, 0.035, 0.02, ys=ys, name="pinch", hub=False)


# ── S1: ящик-седло ─────────────────────────────────────────────────
def build_s1(c, root, M):
    chest(c, root, M, "", 0.58, 0.62, 0.02, 0.30, tunnel=TUNNEL)
    for s in (-1, 1):                                  # полозья по низу — «стоит на ложе»
        K.box("skid%+d" % s, c, (0.05, 0.64, 0.035), loc=(s * 0.27, 0, 0.035), mat=M["frame"],
              parent=root, bevel=0.008)
    hidden_rollers(c, root, M)
    couplers(c, root, M, 0.22, y=0.31)


# ── S2: ящик на тележках (колёса по ложу, рельс — направляющий) ───
def bogie(c, root, M, p, y, wheels=True):
    for s in (-1, 1):                                  # щёки рамы по сторонам лезвия
        K.box(p + "cheek%+d" % s, c, (0.05, 0.16, 0.11), loc=(s * 0.065, y, 0.085), mat=M["frame"],
              parent=root, bevel=0.008)
    K.box(p + "bolster", c, (0.40, 0.06, 0.03), loc=(0, y, 0.145), mat=M["frame"], parent=root, bevel=0.006)
    if wheels:
        for s in (-1, 1):
            K.cyl(p + "wheel%+d" % s, c, 0.065, 0.04, loc=(s * 0.125, y, 0.065), rot=(0, D90, 0),
                  mat=M["wheel"], parent=root, bevel=0.006)
            K.cyl(p + "axlebox%+d" % s, c, 0.03, 0.04, loc=(s * 0.165, y, 0.065), rot=(0, D90, 0),
                  mat=M["brass"], parent=root)
    hidden_rollers(c, root, M, ys=(y,))


def build_s2(c, root, M):
    chest(c, root, M, "", 0.56, 0.60, 0.16, 0.36)
    for s in (-1, 1):
        bogie(c, root, M, "bogie%+d_" % s, s * 0.19)
    couplers(c, root, M, 0.22, y=0.30)


# ── S3: ящик-щипок (колёса ±45° в арке между половинами) ───────────
def build_s3(c, root, M):
    pinch_rollers(c, root, M, 0.13, 0.04)
    hw, hl, z0, z1 = 0.29, 0.31, 0.02, 0.30
    for s in (-1, 1):
        y0, y1 = sorted((s * 0.15, s * hl))
        K.profile_sweep_y("half%+d" % s, c, tunnel_profile(hw, z0, z1), y0, y1, mat=M["chest"],
                          parent=root, bevel=0.01)
        for sx in (-1, 1):
            K.box("archpost%+d%+d" % (sx, s), c, (0.05, 0.04, z1 - z0), loc=(sx * (hw - 0.02), s * 0.17, (z0 + z1) / 2),
                  mat=M["chest_lt"], parent=root, bevel=0.008)
            K.box("post%+d%+d" % (sx, s), c, (0.06, 0.06, z1 - z0 + 0.01),
                  loc=(sx * (hw - 0.022), s * (hl - 0.022), (z0 + z1) / 2), mat=M["chest_lt"], parent=root, bevel=0.01)
    K.box("deck", c, (2 * hw, 2 * hl, 0.05), loc=(0, 0, z1 + 0.025), mat=M["chest"], parent=root, bevel=0.01)
    keel = [(-0.05, 0.19), (0.0, 0.145), (0.05, 0.19), (0.05, z1), (-0.05, z1)]
    K.profile_sweep_y("keel", c, keel, -0.15, 0.15, mat=M["frame"], parent=root)
    lid(c, root, M, "", 2 * hw, 2 * hl, z1 + 0.05)
    K.box("lamp", c, (0.09, 0.02, 0.03), loc=(0, hl + 0.006, z1 - 0.03), mat=M["lamp"], parent=root)
    couplers(c, root, M, 0.22, y=0.31)


# ── S4: ящик на поворотном круге ────────────────────────────────────
def build_s4(c, root, M):
    R, ch = 0.27, 0.04
    circle = [(R * math.cos(2 * math.pi * i / 48), R * math.sin(2 * math.pi * i / 48)) for i in range(48)]
    for s in (-1, 1):
        K.prism("ring_low%+d" % s, c, clip_x(circle, ch, s), 0.015, 0.13, mat=M["frame"], parent=root, bevel=0.006)
    K.cyl("ring_top", c, R, 0.03, loc=(0, 0, 0.145), mat=M["frame"], parent=root, bevel=0.006)
    K.cyl("ring_band", c, R + 0.006, 0.018, loc=(0, 0, 0.155), mat=M["brass"], parent=root)
    for i in range(24):
        a = 2 * math.pi * (i + 0.5) / 24
        K.box("tooth%02d" % i, c, (0.028, 0.04, 0.08), loc=((R + 0.012) * math.cos(a), (R + 0.012) * math.sin(a), 0.075),
              rot=(0, 0, a - D90), mat=M["frame"], parent=root)
    chest(c, root, M, "", 0.42, 0.42, 0.16, 0.36)
    hidden_rollers(c, root, M, ys=(-0.17, 0.17))
    couplers(c, root, M, 0.10, y=0.28)


# ── S5: ящик в захватах (две П-арки держат рельс) ───────────────────
def build_s5(c, root, M):
    for s in (-1, 1):
        y = s * 0.25
        for sx in (-1, 1):
            K.box("leg%+d%+d" % (sx, s), c, (0.07, 0.07, 0.34), loc=(sx * 0.255, y, 0.19), mat=M["frame"],
                  parent=root, bevel=0.01)
            K.box("jaw%+d%+d" % (sx, s), c, (0.19, 0.07, 0.06), loc=(sx * 0.155, y, 0.05), mat=M["frame"],
                  parent=root, bevel=0.01)
        K.box("beam%+d" % s, c, (0.58, 0.07, 0.06), loc=(0, y, 0.34), mat=M["frame"], parent=root, bevel=0.01)
        K.cyl("hoist%+d" % s, c, 0.035, 0.30, loc=(0, y, 0.39), rot=(0, D90, 0), mat=M["brass"], parent=root)
        hidden_rollers(c, root, M, ys=(y,))
    chest(c, root, M, "", 0.44, 0.38, 0.06, 0.30, tunnel=(0.05, 0.15))
    K.box("lamp_beam", c, (0.12, 0.02, 0.03), loc=(0, 0.29, 0.34), mat=M["lamp"], parent=root)
    couplers(c, root, M, 0.20, y=0.30)


# ── S6: ящик с тягачом ─────────────────────────────────────────────
def build_s6(c, root, M):
    chest(c, root, M, "", 0.52, 0.44, 0.02, 0.30, y=-0.08, tunnel=TUNNEL)
    K.profile_sweep_y("nose", c, tunnel_profile(0.20, 0.02, 0.20), 0.14, 0.29, mat=M["chest_lt"],
                      parent=root, bevel=0.012)
    for i in range(4):
        K.box("grill%d" % i, c, (0.30, 0.018, 0.02), loc=(0, 0.17 + 0.035 * i, 0.21), mat=M["frame"], parent=root)
    for s in (-1, 1):
        K.box("headlamp%+d" % s, c, (0.07, 0.02, 0.04), loc=(s * 0.12, 0.295, 0.14), mat=M["lamp"], parent=root)
        K.cyl("motor%+d" % s, c, 0.065, 0.03, loc=(s * 0.205, 0.215, 0.11), rot=(0, D90, 0), mat=M["brass"], parent=root)
    K.cyl("stack", c, 0.018, 0.14, loc=(0.15, 0.17, 0.27), mat=M["frame"], parent=root)
    pinch_rollers(c, root, M, 0.035, 0.02, ys=(0.21, -0.2), name="pinch", hub=False)
    couplers(c, root, M, 0.22, y=0.30)


# ── S7: ящик на гусеницах ───────────────────────────────────────────
def build_s7(c, root, M):
    r, hl = 0.05, 0.30
    prof = []
    for i in range(9):                                  # передняя полуокружность
        a = -D90 + math.pi * i / 8
        prof.append((hl - r + r * math.cos(a), r + r * math.sin(a)))
    for i in range(9):                                  # задняя
        a = D90 + math.pi * i / 8
        prof.append((-hl + r + r * math.cos(a), r + r * math.sin(a)))
    for s in (-1, 1):
        x0, x1 = sorted((s * 0.055, s * 0.15))
        K.profile_sweep_x("track%+d" % s, c, prof, x0, x1, mat=M["wheel"], parent=root)
        for i in range(9):
            K.box("cleat%+d_%d" % (s, i), c, (0.095, 0.018, 0.012), loc=(s * 0.1025, -0.24 + 0.06 * i, 0.104),
                  mat=M["frame"], parent=root)
        for sy in (-1, 1):
            K.cyl("sprocket%+d%+d" % (s, sy), c, 0.035, 0.015, loc=(s * 0.155, sy * (hl - r), r), rot=(0, D90, 0),
                  mat=M["brass"], parent=root)
    chest(c, root, M, "", 0.50, 0.50, 0.11, 0.33, tunnel=(0.05, 0.14))
    hidden_rollers(c, root, M)
    couplers(c, root, M, 0.22, y=0.31)


# ── S8: ящик-октагон (фаски рамы тайла, X-эмблема) ─────────────────
def build_s8(c, root, M):
    h, ch = 0.30, 0.12
    octa = [(-h + ch, -h), (h - ch, -h), (h, -h + ch), (h, h - ch), (h - ch, h), (-h + ch, h), (-h, h - ch), (-h, -h + ch)]
    for s in (-1, 1):
        K.prism("low%+d" % s, c, clip_x(octa, 0.055, s), 0.02, 0.17, mat=M["chest"], parent=root, bevel=0.008)
    K.prism("upper", c, octa, 0.17, 0.30, mat=M["chest"], parent=root, bevel=0.008)
    K.prism("rim", c, [(x * 1.01, y * 1.01) for x, y in octa], 0.30, 0.32, mat=M["chest_lt"], parent=root, bevel=0.006)
    K.prism("lid", c, [(x * 0.78, y * 0.78) for x, y in octa], 0.32, 0.335, mat=M["chest"], parent=root, bevel=0.004)
    for a in (D45, -D45):
        K.box("x%+d" % round(math.degrees(a)), c, (0.40, 0.035, 0.02), loc=(0, 0, 0.343), rot=(0, 0, a),
              mat=M["brass"], parent=root, bevel=0.006)
    K.cyl("boss", c, 0.045, 0.03, loc=(0, 0, 0.35), mat=M["chest_lt"], parent=root)
    for i in range(4):                                  # стойки на фасках
        a = D45 + D90 * i
        d = h - ch / 2 + 0.008
        K.box("cpost%d" % i, c, (0.11, 0.035, 0.29), loc=(d * math.cos(a) * 1.0, d * math.sin(a), 0.165),
              rot=(0, 0, a + D90), mat=M["chest_lt"], parent=root, bevel=0.008)
    for s in (-1, 1):
        K.box("band%+d" % s, c, (0.014, 0.30, 0.04), loc=(s * (h + 0.004), 0, 0.14), mat=M["frame"], parent=root)
    for i in range(5):
        K.box("slot%d" % i, c, (0.032, 0.022, 0.012), loc=(-0.09 + 0.045 * i, 0.20, 0.343 - 0.004),
              mat=M["glow"] if i < 3 else M["frame"], parent=root)
    K.box("lamp", c, (0.09, 0.02, 0.03), loc=(0, h + 0.006, 0.25), mat=M["lamp"], parent=root)
    hidden_rollers(c, root, M)
    couplers(c, root, M, 0.22, y=0.30)


BUILDERS = dict(chest_saddle=build_s1, chest_bogies=build_s2, chest_pinch=build_s3, chest_turntable=build_s4,
                chest_gantry=build_s5, chest_tractor=build_s6, chest_crawler=build_s7, chest_octagon=build_s8)
