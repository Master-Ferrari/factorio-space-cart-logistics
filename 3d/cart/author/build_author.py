# -*- coding: utf-8 -*-
"""Блокинг каретки ПО КОНЦЕПТУ АВТОРА: интерпретации K1–K4 → author_blocking.blend.

Запуск (из этой папки):
  blender -b --factory-startup --python build_author.py

Локальные оси каретки: начало — на оси рельса на уровне ложа (z = 0), +Y — вперёд по ходу,
X — вбок, Z — вверх; 1 BU = 1 тайл. Каждая интерпретация — коллекция AUTH_<K> (исключена из
вью-лейера, живёт инстансами), корень — пустышка cart_<K>.

Механика щипка (общая для всех): два колеса под ±45° касаются плеч головки рельса.
Контакт — (±0.017, 0.111); нормаль плеча n = (±0.707, 0, 0.707); центр = контакт + r·n;
ось колеса a = (∓0.707, 0, 0.707) (⟂ n, смотрит внутрь-вверх). Плоскость диска правого
колеса: z = x + 0.094 (не зависит от r); внутренняя грань z = x + 0.094 + w·0.707,
наружная z = x + 0.094 − w·0.707. Всё, что ниже наружной грани, свободно до ложа —
туда и опускается база (клинья под колёсами).
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import scl3d as K  # noqa: E402
import lp  # noqa: E402
from author_concepts import CONCEPTS  # noqa: E402

H = math.sqrt(0.5)
D45 = math.radians(45)
D90 = math.radians(90)
CX, CZ = 0.017, K.RAIL_TOP_Z - 0.006          # точка контакта на плече головки


def mats():
    """Палитра: сталь трёх тонов (как рама тайла), бежевый ложемента, латунь втулок, оранжевый акцент."""
    return dict(
        dark=K.material("au_dark", (0.07, 0.072, 0.078), rough=0.5),
        mid=K.material("au_mid", (0.22, 0.225, 0.235), rough=0.45),
        light=K.material("au_light", (0.58, 0.61, 0.66), rough=0.3),
        beige=K.material("au_beige", (0.62, 0.54, 0.44), rough=0.6),
        brass=K.material("au_brass", (0.62, 0.45, 0.16), rough=0.35),
        accent=K.material("au_accent", (0.92, 0.42, 0.06), rough=0.4),
        tire=K.material("au_tire", (0.035, 0.035, 0.04), rough=0.7),
        # болванка рельса для видов сбоку / 3/4
        base=K.material("ref_base", (0.05, 0.05, 0.055), rough=0.7),
        bed=K.material("ref_bed", (0.58, 0.51, 0.43), rough=0.6),
        blade=K.material("ref_blade", (0.62, 0.65, 0.70), rough=0.25, metal=0.9),
    )


# ── общие узлы ──────────────────────────────────────────────────────
def wheel_center(s, r):
    return s * (CX + H * r), CZ + H * r


def vwheel(c, root, M, s, r, w, y=0.0, tag="w", face=True, hub=True):
    """Колесо щипка на плече s (±1). Диск — светлая сталь, как лезвия тайла: тёмное колесо
    тонет в чёрных карманах тайла (проверено в первом проходе). Изнутри-сверху — тёмная
    лицевая плита с латунной втулкой («прицел» с рисунка внизу слева, её видно из игровой
    камеры), снаружи-снизу — латунная втулка оси."""
    cx, cz = wheel_center(s, r)
    a = (-s * H, 0.0, H)                                   # ось: внутрь-вверх
    rot = (0, -s * D45, 0)
    nm = "%s%+d" % (tag, s)
    lp.rdisc(nm, c, r, w, (cx, y, cz), rot, M["light"], root, segs=16, ch=min(0.012, r * 0.08))
    if face:
        d = w / 2 + 0.005
        lp.rdisc(nm + "_face", c, r * 0.62, 0.014, (cx + a[0] * d, y, cz + a[2] * d), rot,
                 M["dark"], root, segs=12, ch=0.004)
        d = w / 2 + 0.016
        lp.rdisc(nm + "_cap", c, r * 0.2, 0.02, (cx + a[0] * d, y, cz + a[2] * d), rot,
                 M["brass"], root, segs=8, ch=0.004)
    if hub:
        d = w / 2 + 0.014
        lp.rdisc(nm + "_hub", c, r * 0.30, 0.03, (cx - a[0] * d, y, cz - a[2] * d), rot,
                 M["brass"], root, segs=8, ch=0.006)
    return cx, cz


def plan_chamfers(hx, hy, ch):
    """Срезы вертикальных рёбер прямоугольного плана ±hx × ±hy фаской ch (октагон в плане)."""
    return [((sx * hx, sy * (hy - ch), 0), (sx, sy, 0)) for sx in (-1, 1) for sy in (-1, 1)]


def emblem(c, root, M, y_face, sy, z, wpl=0.20, hpl=0.13, zz=(0.12, 0.085), plate=True):
    """Рамка + зигзаг-эмблема (как на всех рисунках автора) на торце y = y_face, наружу по sy."""
    org = (0, y_face, z)
    if plate:
        t0, t1 = (-0.008, 0.0) if sy > 0 else (0.0, 0.008)
        lp.plate("emb_plate%+d" % sy, c, lp.octagon(wpl / 2, hpl / 2, 0.025), t0, t1, M["light"], root,
                 origin=org, U=(1, 0, 0), V=(0, 0, 1))
    t0, t1 = (-0.02, -0.006) if sy > 0 else (0.006, 0.02)
    lp.plate("emb_zig%+d" % sy, c, lp.strip(lp.zig(zz[0], zz[1], 3), 0.024), t0, t1, M["accent"], root,
             origin=org, U=(1, 0, 0), V=(0, 0, 1))


def couplers(c, root, M, L, z=0.10, hw=0.045):
    for sy in (-1, 1):
        y0, y1 = sorted((sy * (L - 0.01), sy * (L + 0.035)))
        lp.plan("coupler%+d" % sy, c, lp.rect(-hw, hw, y0, y1), z - 0.03, z + 0.03, M["dark"], root, ch=0.008)


def wheel_well(c, obj, s, r, w, y=0.0, gap=0.025):
    """Вырезать в obj карман под колесо (цилиндр чуть больше колеса)."""
    cx, cz = wheel_center(s, r)
    cut = K.cyl("well", c, r + gap, w + 2 * gap, loc=(cx, y, cz), rot=(0, -s * D45, 0), segs=16)
    K.bool_cut(obj, cut)


# ── K1: как нарисовано (ряд 2 слева) ────────────────────────────────
def build_K1(c, root, M):
    """Буквально по рисунку: V-пара внизу целиком на виду, база-трапеция (шире книзу) лежит на
    верхушках колёс (неглубокие карманы), на базе ящик с зигзаг-панелью, по бокам C-щёки.
    Овалы колёс и головка рельса между ними — под базой, как на рисунке. Корпус целиком над
    колёсами — отсюда высота; база не длиннее колеса, иначе спереди овалов не видно и сдвиг вверх (та самая проблема «на колёсах и по центру тайла»)."""
    r, w, L = 0.20, 0.055, 0.22
    for s in (-1, 1):
        vwheel(c, root, M, s, r, w)
    sec = [(-0.32, 0.35), (0.32, 0.35), (0.28, 0.42), (-0.28, 0.42)]
    base = lp.section("base", c, sec, -L, L, M["mid"], root, cuts=plan_chamfers(0.32, L, 0.06))
    for s in (-1, 1):
        wheel_well(c, base, s, r, w, gap=0.015)
    lp.section("box", c, [(-0.22, 0.42), (0.22, 0.42), (0.22, 0.47), (0.18, 0.50), (-0.18, 0.50), (-0.22, 0.47)],
               -0.19, 0.19, M["dark"], root, cuts=plan_chamfers(0.22, 0.19, 0.04), ch=0.008)
    lp.plan("top_plate", c, lp.octagon(0.14, 0.14, 0.04), 0.50, 0.508, M["light"], root)
    lp.plan("top_zig", c, lp.strip(lp.zig(0.12, 0.17, 3), 0.03), 0.508, 0.52, M["accent"], root)
    for s in (-1, 1):
        x0, x1 = sorted((s * 0.22, s * 0.27))
        prof = [(-0.17, 0.40), (0.17, 0.40), (0.17, 0.49), (0.12, 0.53), (-0.12, 0.53), (-0.17, 0.49)]
        lp.side("cheek%+d" % s, c, prof, x0, x1, M["light"], root, ch=0.008)
        cpts = lp.sickle((-0.10, 0.42), (0.0, 0.51), (0.10, 0.42), 0.028, n=7, w1=0.028, w2=0.028)
        x0, x1 = sorted((s * 0.27, s * 0.29))
        lp.plate("cheekC%+d" % s, c, cpts, x0, x1, M["brass"], root, U=(0, 1, 0), V=(0, 0, 1))
    emblem(c, root, M, L, 1, 0.385, wpl=0.20, hpl=0.06, zz=(0.11, 0.04))
    emblem(c, root, M, -L, -1, 0.385, wpl=0.20, hpl=0.06, zz=(0.11, 0.04))
    couplers(c, root, M, L, z=0.385)


# ── K2: база обнимает (слова автора про «сложную форму базы») ───────
def build_K2(c, root, M):
    """Объём — внизу, а не сверху. База — широкий низкий поддон-октагон у самого ложа (две
    половины по бокам лезвия, торцевые бамперы-мосты над рельсом). Под каждым колесом — клин-
    люлька, её верх параллелен наружной грани колеса (z = x + 0.04). Колёса r 0.22 открыты
    сверху. Над развалом — узкий хребет-киль с бежевым разрезным горбом (как ложементы тайла),
    на торцах хребта — щёки с зигзаг-эмблемой."""
    r, w = 0.22, 0.06
    L = 0.36
    for s in (-1, 1):
        vwheel(c, root, M, s, r, w)
    # поддон: две половины-октагона по сторонам лезвия, z 0..0.10 (ниже наружных граней колёс)
    for s in (-1, 1):
        lp.plan("tray%+d" % s, c, lp.octagon(0.34, L, 0.13), 0.0, 0.10, M["mid"], root,
                cuts=[((s * 0.05, 0, 0), (-s, 0, 0))], ch=0.008)
        # клин-люлька под колесом
        sec = [(0.06, 0.10), (0.34, 0.10), (0.34, 0.22), (0.18, 0.22)]
        sec = [(s * x, z) for x, z in sec]
        if s < 0:
            sec = sec[::-1]
        lp.section("cradle%+d" % s, c, sec, -0.22, 0.22, M["mid"], root,
                   cuts=[((0, sy * 0.15, 0.22), (0, sy, 1)) for sy in (-1, 1)], ch=0.006)
    # торцевые бамперы-мосты над рельсом
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.25, sy * L))
        sec = [(-0.30, 0.0), (-0.05, 0.0), (-0.05, 0.16), (0.05, 0.16), (0.05, 0.0), (0.30, 0.0),
               (0.30, 0.12), (0.24, 0.18), (-0.24, 0.18), (-0.30, 0.12)]
        cuts = [((sx * 0.34, sy * (L - 0.13), 0), (sx, sy, 0)) for sx in (-1, 1)]
        lp.section("bumper%+d" % sy, c, sec, y0, y1, M["dark"], root, cuts=cuts, ch=0.008)
    # хребет-киль в развале: низ — V с зазором над внутренними гранями (z = |x| + 0.15)
    keel = [(0, 0.15), (0.09, 0.24), (0.09, 0.36), (0.06, 0.39), (-0.06, 0.39), (-0.09, 0.36), (-0.09, 0.24)]
    lp.section("keel", c, keel, -0.30, 0.30, M["dark"], root, ch=0.006)
    # щёки на торцах хребта (над бамперами, вне колёс по Y)
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.235, sy * 0.335))
        sec = [(-0.17, 0.18), (0.17, 0.18), (0.17, 0.27), (0.11, 0.33), (-0.11, 0.33), (-0.17, 0.27)]
        lp.section("cheek%+d" % sy, c, sec, y0, y1, M["mid"], root,
                   cuts=[((0, sy * 0.335, 0.27), (0, sy, 1))], ch=0.008)
        emblem(c, root, M, sy * 0.335, sy, 0.235, wpl=0.18, hpl=0.09, zz=(0.10, 0.06))
    # горб: разрезной бежевый ложемент на хребте
    for s in (-1, 1):
        x0, x1 = sorted((s * 0.008, s * 0.075))
        prof = [(-0.22, 0.39), (0.22, 0.39), (0.22, 0.41), (0.17, 0.435), (-0.17, 0.435), (-0.22, 0.41)]
        lp.side("hump%+d" % s, c, prof, x0, x1, M["beige"], root, ch=0.005)
    couplers(c, root, M, L, z=0.09)


# ── K3: диск снизу (ряд 3 справа + низ слева) ──────────────────────
def build_K3(c, root, M):
    """Большой плоский диск у самого ложа (тот «диск с +»), разрезан каналом под рельс; щипок
    ±45° внутри канала. Над диском — ребристая юбка-конус, корпус-«шестигранник» (октагон
    в плане, скошенные верхние рёбра), бежевый горб, C-уши по бокам, зигзаг в рамке на торцах."""
    R = 0.33
    for s in (-1, 1):                                                     # щипок внутри канала
        vwheel(c, root, M, s, 0.085, 0.035, face=False, hub=False)
    for s in (-1, 1):                                                     # две половины диска
        cuts = [((s * 0.05, 0, 0), (-s, 0, 0))]
        lp.plan("disc%+d" % s, c, lp.ngon(R, 16, rot=math.pi / 16), 0.0, 0.07, M["dark"], root, cuts=cuts, ch=0.01)
        lp.plan("rim%+d" % s, c, lp.ngon(R + 0.008, 16, rot=math.pi / 16), 0.03, 0.055, M["brass"], root, cuts=cuts)
    for sy in (-1, 1):                                                    # «прицел» на диске
        y = sy * 0.255
        lp.plan("cross_a%+d" % sy, c, lp.rect(-0.045, 0.045, y - 0.008, y + 0.008), 0.07, 0.082, M["accent"], root)
        lp.plan("cross_b%+d" % sy, c, lp.rect(-0.008, 0.008, y - 0.045, y + 0.045), 0.07, 0.082, M["accent"], root)
    # ребристая юбка: усечённый октагон, тоннель под рельс
    rings = []
    for rr, z in ((0.27, 0.07), (0.235, 0.16)):
        rings.append([(x, y, z) for x, y in lp.ngon(rr, 8, rot=math.pi / 8)])
    lp.loft("skirt", c, rings, M["mid"], root, ch=0.006)
    # корпус: октагон в плане, верхние рёбра скошены («шестигранно-скруглённый»)
    cuts = [((sx * 0.25, 0, 0.27), (sx, 0, 1)) for sx in (-1, 1)] + \
           [((0, sy * 0.27, 0.27), (0, sy, 1)) for sy in (-1, 1)]
    lp.plan("body", c, lp.octagon(0.25, 0.27, 0.09), 0.16, 0.33, M["dark"], root, cuts=cuts, ch=0.008)
    # горб-люк, разрезной бежевый
    for s in (-1, 1):
        x0, x1 = sorted((s * 0.008, s * 0.11))
        prof = [(-0.15, 0.31), (0.15, 0.31), (0.15, 0.335), (0.10, 0.37), (-0.10, 0.37), (-0.15, 0.335)]
        lp.side("hump%+d" % s, c, prof, x0, x1, M["beige"], root, cuts=[((s * 0.11, 0, 0.35), (s, 0, 1))], ch=0.005)
    # C-уши по бокам
    for s in (-1, 1):
        cpts = lp.sickle((-0.13, 0.17), (0.0, 0.31), (0.13, 0.17), 0.04, n=7, w1=0.045, w2=0.045)
        x0, x1 = sorted((s * 0.235, s * 0.275))
        lp.plate("ear%+d" % s, c, cpts, x0, x1, M["light"], root, U=(0, 1, 0), V=(0, 0, 1), ch=0.006)
    for sy in (-1, 1):
        emblem(c, root, M, sy * 0.27, sy, 0.235, wpl=0.17, hpl=0.10, zz=(0.10, 0.065))
    couplers(c, root, M, R, z=0.035, hw=0.04)


# ── K4: одно большое колесо сбоку (асимметричный щипок) ─────────────
def build_K4(c, root, M):
    """Буквально «сбоку одно большое колесо»: большое колесо r 0.245 на одном плече (+X)
    и малый прижимной ролик на другом (−X). Корпус — над роликом, ниже верха колеса, не
    закрывает колесо сверху. Под большим колесом — клин-люлька до ложа."""
    rb, wb = 0.245, 0.06
    L = 0.34
    vwheel(c, root, M, 1, rb, wb, tag="big")
    vwheel(c, root, M, -1, 0.07, 0.04, tag="pinch", face=False)
    # корпус: низ над роликом и над внутренней гранью большого колеса (z ≥ x + 0.148)
    sec = [(-0.33, 0.0), (-0.13, 0.0), (-0.13, 0.08), (-0.03, 0.20), (0.05, 0.22), (0.05, 0.30),
           (0.0, 0.35), (-0.27, 0.35), (-0.33, 0.29)]
    lp.section("body", c, sec, -L, L, M["mid"], root, cuts=plan_chamfers(0.33, L, 0.10), ch=0.01)
    for s in (-1, 1):                                    # крышка — разрезной бежевый ложемент
        x0, x1 = (-0.255, -0.142) if s < 0 else (-0.128, -0.015)
        prof = [(-0.25, 0.35), (0.25, 0.35), (0.25, 0.37), (0.20, 0.395), (-0.20, 0.395), (-0.25, 0.37)]
        lp.side("lid%+d" % s, c, prof, x0, x1, M["beige"], root, ch=0.005)
    # боковая зигзаг-эмблема на −X грани
    lp.plate("side_plate", c, lp.octagon(0.20, 0.07, 0.025), -0.338, -0.33, M["light"], root,
             origin=(0, 0, 0.17), U=(0, 1, 0), V=(0, 0, 1))
    lp.plate("side_zig", c, lp.strip(lp.zig(0.12, 0.05, 3), 0.022), -0.35, -0.338,
             M["accent"], root, origin=(0, 0, 0.17), U=(0, 1, 0), V=(0, 0, 1))
    # клин-люлька под большим колесом
    sec = [(0.06, 0.0), (0.37, 0.0), (0.37, 0.20), (0.16, 0.20), (0.06, 0.10)]
    lp.section("cradle", c, sec, -L + 0.04, L - 0.04, M["mid"], root,
               cuts=[((0.37, sy * (L - 0.14), 0), (1, sy, 0)) for sy in (-1, 1)], ch=0.008)
    for sy in (-1, 1):
        emblem(c, root, M, sy * L, sy, 0.22, wpl=0.16, hpl=0.09, zz=(0.09, 0.06))
    couplers(c, root, M, L, z=0.10)


BUILDERS = dict(K1=build_K1, K2=build_K2, K3=build_K3, K4=build_K4)


def main():
    K.reset_scene()
    M = mats()
    for key, short, _ in CONCEPTS:
        c = K.collection("AUTH_%s" % key)          # булевы резы требуют живой коллекции
        root = K.empty("cart_%s" % key, c)
        BUILDERS[key](c, root, M)
        K.collection("AUTH_%s" % key, exclude=True)
        print("built", key, len(c.objects), "objects")
    out = os.path.join(HERE, "author_blocking.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print("saved", out)


if __name__ == "__main__":
    main()
