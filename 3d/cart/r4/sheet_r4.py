# -*- coding: utf-8 -*-
"""Финальный лист раунда 4 (out/sheet.png) — вызывается из compose_r4.py."""

import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw

import compose_r4 as C
import scl3d as K
from keys import KEYS, MAIN, TITLES

INK = (232, 232, 232, 255)
DIM = (160, 165, 170, 255)
YEL = (255, 205, 60, 255)
CYAN = (90, 220, 255, 255)
ORG = (255, 120, 40, 255)

WHY = {
    "X1": "груз над колёсами: ЦМ выше центра крена — опрокидывается; силуэт уезжает вверх",
    "X2": "колёса спрятаны в тоннеле: сверху — коробка (как S1/B), «одного колеса» нет",
    "X3": "одна пара в носу не держит тангаж без второй опоры; dy скачет по курсам",
    "X4": "объём весь низко, но плоская плита: колёса торчат над подносом, груз некуда",
}


def lbl(im, text, pos, sz=17, fill=INK, bold=False):
    C.label(im, text, sz, pos, fill, bold)


def tile_crop(img, ren, fr, x, y, k=4):
    """Спрайт тайла 80×80 вокруг каретки (x, y) при 64 px/тайл, увеличенный ×k, с рамкой силуэта."""
    px, py = fr.px(x, y, 0.0)
    gx, gy = K.SPRITE_GROUND_PX
    up = 24                                            # запас сверху: высокие силуэты выходят за спрайт
    x0, y0 = round(px - gx), round(py - gy)
    box = (x0, y0 - up, x0 + 80, y0 + 80)
    t = C.nearest(img.crop(box), k)
    a = np.asarray(ren.crop(box))[:, :, 3] > 127
    ys, xs = np.nonzero(a)
    d = ImageDraw.Draw(t)
    c = 40 * k
    cyy = (40 + up) * k
    d.rectangle([0, up * k, 80 * k - 1, (80 + up) * k - 1], outline=(70, 75, 80, 255), width=1)
    d.line([(c, 0), (c, (80 + up) * k)], fill=CYAN, width=1)
    d.line([(0, cyy), (80 * k, cyy)], fill=CYAN, width=1)
    if len(ys):
        bx0, bx1, by0, by1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        d.rectangle([bx0 * k, by0 * k, bx1 * k - 1, by1 * k - 1], outline=YEL, width=2)
        cy = (by0 + by1) / 2 * k
        d.line([(c - 26, cy), (c + 26, cy)], fill=YEL, width=3)
        dy = (by0 + by1) / 2 - 40 - up
        return t, dy
    return t, 0.0


def centering(frames, allm):
    """Панель «центровка»: P и X1 (скетч буквально) на тайле, ×4, рамка силуэта и центр спрайта."""
    tiles = []
    for key in (MAIN, "X1"):
        img, ren, fr = C.game_view(key, "ring8", frames, K.PX_GAME)
        for i in (0, 2):                                     # курс N и курс W
            (x, y), hd = frames["ring8"]["carts"][i], frames["ring8"]["headings"][i]
            t, dy = tile_crop(img, ren, fr, x, y)
            tiles.append((key, hd, t, dy))
    tw = tiles[0][2].width
    P = Image.new("RGBA", (4 * tw + 5 * 12, tiles[0][2].height + 92), C.PAPER)
    for i, (key, hd, t, dy) in enumerate(tiles):
        x = 12 + i * (tw + 12)
        P.alpha_composite(t, (x, 62))
        name = "P · сума" if key == MAIN else "X1 · корпус над колёсами"
        lbl(P, "%s, курс %s" % (name, "N–S" if hd % 180 == 0 else "E–W"), (x, 8), 16, bold=(key == MAIN))
        lbl(P, "dy %+.1f px" % dy, (x, 30), 20, YEL if key == MAIN else ORG, bold=True)
    lbl(P, "голубое — центр спрайта тайла 80×80 (серая рамка); жёлтое — рамка силуэта и её центр (64 px/тайл, ×4)", (12, t.height + 66), 15, DIM)
    return P


def dy_chart(allm):
    rows = []
    for r in ("r1", "r2", "r3"):
        m = json.load(open(os.path.join(C.OLD, r, "metrics.json"), encoding="utf-8"))
        for k, v in m.items():
            d = [e["dy"] for e in v]
            rows.append((r + " " + k, sum(d) / len(d), min(d), max(d), False))
    for k in KEYS:
        v = allm[k].get("ring32w") or allm[k]["ring8"]
        d = [e["dy"] for e in v]
        rows.append(("r4 " + (k if k != MAIN else "P (32 курса)"), sum(d) / len(d), min(d), max(d), k == MAIN))
    rows.sort(key=lambda r: -r[1])
    sc = 26                                           # px на 1 px dy
    W, rh = 830, 21
    H = 60 + len(rows) * rh + 40
    O = Image.new("RGBA", (W, H), C.PAPER)
    d = ImageDraw.Draw(O)
    x0 = 150 + 23 * sc                                # ноль справа
    lbl(O, "dy — сдвиг центра силуэта от центра спрайта тайла, px при 64/тайл", (10, 6), 16, bold=True)
    lbl(O, "полоса — среднее по курсам, усы — худший и лучший курс", (10, 28), 14, DIM)
    top = 56
    for v in range(0, -24, -2):
        xx = x0 + v * sc
        d.line([(xx, top - 4), (xx, top + len(rows) * rh)], fill=(50, 54, 58, 255))
        lbl(O, "%d" % v, (xx - 8, top + len(rows) * rh + 4), 13, DIM)
    xg = x0 - 2.9 * sc
    d.line([(xg, top - 4), (xg, top + len(rows) * rh)], fill=CYAN, width=1)
    lbl(O, "−2.9: плоский предмет на ложе", (xg - 200, H - 18), 13, CYAN)
    for i, (name, av, mn, mx, hi) in enumerate(rows):
        y = top + i * rh
        col = YEL if hi else ((120, 125, 130, 255) if name.startswith("r4") else (85, 90, 96, 255))
        d.rectangle([x0 + av * sc, y + 4, x0, y + rh - 4], fill=col)
        d.line([(x0 + mn * sc, y + rh // 2), (x0 + mx * sc, y + rh // 2)], fill=INK if hi else DIM, width=2)
        lbl(O, name, (10, y + 2), 14, YEL if hi else (INK if name.startswith("r4") else DIM), bold=hi)
        lbl(O, "%+.1f" % av, (x0 + 8, y + 2), 14, YEL if hi else DIM)
    return O


def section(frames):
    s = Image.open(os.path.join(C.REN, "P_section.png")).convert("RGBA")
    info = frames["section"]
    W, (rx, ry), (tx, ty, tz) = info["ortho_w"], info["res"], info["target"]
    k = rx / W

    def P(x, z):
        return (rx / 2 + (x - tx) * k, ry / 2 - (z - tz) * k)
    bg = Image.new("RGBA", s.size, (226, 228, 230, 255))
    bg.alpha_composite(s)
    d = ImageDraw.Draw(bg)
    f = C.font(17)
    rc = P(0, 0.094)
    # линии действия реакций — через центр крена
    for sx in (-1, 1):
        c0 = P(sx * 0.017, 0.111)
        c1 = P(sx * (0.017 + 0.30), 0.111 + 0.30)
        d.line([rc, c1], fill=(40, 120, 200, 255), width=2)
        a0 = P(sx * 0.017, 0.111)
        a1 = P(sx * (0.017 + 0.09), 0.111 + 0.09)
        d.line([a0, a1], fill=(20, 80, 200, 255), width=6)
        d.polygon([a1, P(sx * (0.017 + 0.065), 0.111 + 0.09), P(sx * (0.017 + 0.09), 0.111 + 0.065)], fill=(20, 80, 200, 255))
        # вес сумы
        g = P(sx * 0.200, 0.103)
        d.ellipse([g[0] - 9, g[1] - 9, g[0] + 9, g[1] + 9], outline=(20, 20, 20, 255), width=3)
        gb = P(sx * 0.200, 0.103 - 0.10)
        d.line([g, gb], fill=(200, 30, 30, 255), width=6)
        d.polygon([(gb[0] - 10, gb[1] - 14), (gb[0] + 10, gb[1] - 14), (gb[0], gb[1] + 4)], fill=(200, 30, 30, 255))
    d.ellipse([rc[0] - 7, rc[1] - 7, rc[0] + 7, rc[1] + 7], fill=(20, 80, 200, 255))
    for z, t in ((0.117, "верх лезвия 0.117"), (0.094, "центр крена 0.094"), (0.03, "днище 0.03"), (0.0, "ложе 0")):
        y = P(0, z)[1]
        d.line([(rx - 250, y), (rx - 12, y)], fill=(90, 90, 90, 255), width=1)
        d.text((rx - 248, y - 20), t, font=f, fill=(30, 30, 30, 255))
    d.text((14, 12), "разрез по оси колёс (y = 0), вид с юга, без растяжки", font=C.font(19, True), fill=(20, 20, 20, 255))
    notes = ["синее — реакции головки по нормалям ±45°; их линии сходятся в центре крена",
             "красное — вес сумы (ЦМ по объёму x 0.20, z 0.103): масса висит по обе стороны головки,",
             "у ложа, — каретка маятник; аккумуляторы в днище опускают ЦМ ниже 0.094",
             "сечения: оранжевое — колёса, тёмное — сумы, бежевое/серое — ложе и лезвие; за срезом — портал с муфтой"]
    for i, t in enumerate(notes):
        d.text((14, 40 + i * 22), t, font=C.font(15), fill=(40, 40, 40, 255))
    return bg


def discarded(frames, allm):
    keys = [k for k in KEYS if k != MAIN]
    cells = []
    for k in keys:
        img, ren, fr = C.game_view(k, "ring8", frames, K.PX_GAME)
        pair = []
        for i in (0, 2):
            (x, y) = frames["ring8"]["carts"][i]
            t, _ = tile_crop(img, ren, fr, x, y, k=2)
            pair.append(t)
        cells.append((k, pair))
    tw = cells[0][1][0].width
    W = 1000
    H = len(cells) * (tw + 16) + 40
    O = Image.new("RGBA", (W, H), C.PAPER)
    lbl(O, "Отброшенные схемы (8 курсов; рамка — силуэт, голубое — центр спрайта)", (10, 8), 17, bold=True)
    for i, (k, pair) in enumerate(cells):
        y = 36 + i * (tw + 16)
        O.alpha_composite(pair[0], (10, y))
        O.alpha_composite(pair[1], (20 + tw, y))
        av, mn, mx = C.stat(allm[k]["ring8"])
        lbl(O, TITLES[k], (40 + 2 * tw, y + 10), 18, bold=True)
        lbl(O, "dy %+.1f px (%+.1f…%+.1f)" % (av, mn, mx), (40 + 2 * tw, y + 38), 17, ORG)
        lbl(O, WHY[k], (40 + 2 * tw, y + 66), 15, DIM)
    return O


def fit_h(im, h):
    return im.resize((round(im.width * h / im.height), h), Image.Resampling.LANCZOS)


def build(frames, allm):
    field64, _, _ = C.game_view(MAIN, "field", frames, K.PX_GAME)
    field256, _, fr256 = C.game_view(MAIN, "field", frames, K.PX_RENDER)
    x0, y0 = fr256.px(0.4, 1.75, 0)
    x1, y1 = fr256.px(3.5, -1.65, 0)
    turn = field256.crop((int(x0), int(y0), int(x1), int(y1)))
    f2 = C.nearest(field64, 2)
    turn = fit_h(turn, f2.height)

    r32, ren32, _ = C.game_view(MAIN, "ring32", frames, K.PX_GAME)
    r32 = C.nearest(r32, 2)
    s32 = C.nearest(C.silhouette(ren32), 2)

    hero = fit_h(C.on_bg(Image.open(os.path.join(C.REN, "P_hero.png")).convert("RGBA")) if hasattr(C, "on_bg")
                 else Image.open(os.path.join(C.REN, "P_hero.png")).convert("RGBA"), 640)
    close = Image.open(os.path.join(C.REN, "P_closeup.png")).convert("RGBA")
    close = fit_h(close, 640)
    side = Image.open(os.path.join(C.REN, "P_side.png")).convert("RGBA")
    sec = fit_h(section(frames), 640)
    cen = centering(frames, allm)
    chart = dy_chart(allm)
    disc = discarded(frames, allm)

    W = max(f2.width + turn.width, r32.width + s32.width, hero.width + close.width, cen.width + chart.width,
            sec.width + side.width, disc.width + sec.width) + 30
    rows_h = [70, f2.height + 34, max(cen.height, chart.height) + 20, r32.height + 34, 640 + 34,
              max(sec.height, side.height + disc.height + 40) + 34]
    S = Image.new("RGBA", (W, sum(rows_h) + 30), (16, 18, 20, 255))
    av, mn, mx = C.stat(allm[MAIN]["ring32w"])
    lbl(S, "Раунд 4 · P «Перемётная сума» — одна пара колёс ±45° на головке, груз висит по обе стороны рельса у ложа",
        (12, 10), 26, bold=True)
    lbl(S, "dy по 32 курсам: %+.1f px (%+.1f…%+.1f)  ·  скетч «корпус над колёсами» (X1): %+.1f px  ·  лучшие прошлых раундов: T3 −6.0 (−12…−1), E −6.8"
        % (av, mn, mx, C.stat(allm["X1"]["ring8"])[0]), (12, 44), 18, YEL)
    y = 70
    S.alpha_composite(f2, (10, y + 24)); lbl(S, "игровой масштаб 64 px/тайл ×2 (nearest), настоящие спрайты тайла: прямая, поворот, ряд E–W", (14, y))
    S.alpha_composite(turn, (20 + f2.width, y + 24)); lbl(S, "поворот r 0.5 крупно (256 px/тайл)", (24 + f2.width, y))
    y += rows_h[1]
    S.alpha_composite(cen, (10, y)); S.alpha_composite(chart, (20 + cen.width, y))
    y += rows_h[2]
    S.alpha_composite(r32, (10, y + 24)); lbl(S, "все 32 курса листа (шаг 11.25°), 64 px/тайл ×2", (14, y))
    S.alpha_composite(s32, (20 + r32.width, y + 24)); lbl(S, "те же курсы плоской заливкой", (24 + r32.width, y))
    y += rows_h[3]
    S.alpha_composite(hero, (10, y + 24)); lbl(S, "3/4 без растяжки: прямая, поворот, стрелка", (14, y))
    S.alpha_composite(close, (20 + hero.width, y + 24)); lbl(S, "крупно, курс N–S", (24 + hero.width, y))
    y += rows_h[4]
    S.alpha_composite(sec, (10, y + 24)); lbl(S, "разрез поперёк рельса: колёса на головке, путь нагрузки", (14, y))
    S.alpha_composite(side, (20 + sec.width, y + 24)); lbl(S, "сбоку (горизонтально, без растяжки): ближняя сума закрывает колесо — «одно колесо» видно в игровом ракурсе", (24 + sec.width, y))
    S.alpha_composite(disc, (20 + sec.width, y + 34 + side.height + 24))
    S.save(os.path.join(C.OUT, "sheet.png"))
    # отдельные крупные куски — смотреть без лупы
    cen.save(os.path.join(C.OUT, "centering.png"))
    chart.save(os.path.join(C.OUT, "dy_chart.png"))
    section(frames).save(os.path.join(C.OUT, "section.png"))
    print("sheet", S.size)
