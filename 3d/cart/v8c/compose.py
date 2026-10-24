# -*- coding: utf-8 -*-
"""Листы блокинга v8c: рендеры поверх настоящих спрайтов тайла, замер dy, сравнение со скетчем.

Запуск (системный python, Pillow + numpy):  python compose.py
Берёт out/render/*.png и frames.json, пишет out/sheet.png (главный лист, вариант A),
out/metrics.json.
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)
import scl3d as K  # noqa: E402
from params import VARIANTS, TITLES  # noqa: E402

REN = os.path.join(HERE, "out", "render")
OUT = os.path.join(HERE, "out")
TILE_SPRITE = os.path.join(HERE, "..", "..", "sprites", "compose", "tile_63_111111.png")
SKETCH = os.path.join(HERE, "ref_sketch.png")      # копия 8.png автора (кладёт make.py, если есть)
FONT = "C:/Windows/Fonts/arial.ttf"
BG = (34, 38, 40, 255)
INK = (232, 232, 232, 255)
DIM = (165, 170, 172, 255)


def font(sz):
    try:
        return ImageFont.truetype(FONT, sz)
    except OSError:
        return ImageFont.load_default()


def label(im, text, sz=18, pos=(10, 6), fill=INK):
    ImageDraw.Draw(im).text(pos, text, font=font(sz), fill=fill)


def downscale(im, f):
    """Bicubic Sharper по премультиплицированной альфе (как в sprites/compose.py)."""
    w, h = im.size
    small = im.convert("RGBa").resize((w // f, h // f), Image.Resampling.BICUBIC).convert("RGBA")
    return small.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))


def nearest(im, k):
    return im.resize((round(im.width * k), round(im.height * k)), Image.Resampling.NEAREST)


def tile_bg(frame, tiles):
    """Подложка из спрайтов тайла: центр тайла на z = 0 ↔ SPRITE_GROUND_PX спрайта."""
    k = frame.ppt / K.PX_GAME
    spr = Image.open(TILE_SPRITE).convert("RGBA")
    if k != 1:
        spr = spr.resize((round(spr.width * k), round(spr.height * k)), Image.Resampling.LANCZOS)
    gx, gy = K.SPRITE_GROUND_PX
    canvas = Image.new("RGBA", frame.res, BG)
    for tx, ty in sorted(tiles, key=lambda t: (-t[1], t[0])):        # север раньше юга
        px, py = frame.px(tx, ty, 0.0)
        canvas.alpha_composite(spr, (round(px - gx * k), round(py - gy * k)))
    return canvas


def game_view(key, view, frames, ppt):
    fr = K.Frame.from_dict(frames[view]["frame"]).scaled(ppt)
    ren = Image.open(os.path.join(REN, "%s_%s.png" % (key, view))).convert("RGBA")
    f = K.PX_RENDER // ppt
    if f > 1:
        ren = downscale(ren, f)
    bg = tile_bg(fr, [tuple(t) for t in frames[view]["tiles"]])
    shp = os.path.join(REN, "%s_%s_sh.png" % (key, view))
    if os.path.exists(shp):                         # тень из прохода на белой плоскости
        sh = Image.open(shp).convert("RGBA")
        if f > 1:
            sh = sh.resize(ren.size, Image.Resampling.BOX)
        lum = np.asarray(sh.convert("L"), dtype=np.float32)
        a = np.asarray(ren, dtype=np.float32)[:, :, 3] / 255.0
        ref = np.percentile(lum[a < 0.02], 99) if (a < 0.02).any() else 255.0
        shade = np.clip(1.0 - lum / max(ref, 1.0), 0, 1) * (1.0 - a)
        b = np.asarray(bg, dtype=np.float32)
        b[:, :, :3] *= (1.0 - 0.7 * np.clip(shade * 2.5, 0, 1))[:, :, None]
        bg = Image.fromarray(b.clip(0, 255).astype(np.uint8), "RGBA")
    bg.alpha_composite(ren)
    return bg, ren, fr


def metrics(key, frames):
    """32 курса при 64 px/тайл: рамка силуэта относительно центра спрайта тайла (dy < 0 — выше)."""
    _, ren, fr = game_view(key, "ringm", frames, K.PX_GAME)
    a = np.asarray(ren)[:, :, 3]
    lift = K.SPRITE_TILE_PX / 2 - K.SPRITE_GROUND_PX[1]
    out = []
    for x, y, h in frames["ringm"]["poses"]:
        px, py = fr.px(x, y, 0.0)
        cx, cy = px, py + lift
        x0, x1 = int(px - 64), int(px + 64)
        y0, y1 = int(py - 80), int(py + 48)
        sub = a[max(0, y0):y1, max(0, x0):x1] > 127
        ys, xs = np.nonzero(sub)
        if not len(ys):
            continue
        bx0, bx1 = xs.min() + max(0, x0), xs.max() + 1 + max(0, x0)
        by0, by1 = ys.min() + max(0, y0), ys.max() + 1 + max(0, y0)
        out.append(dict(heading=round(np.degrees(h), 2), w=int(bx1 - bx0), h=int(by1 - by0),
                        dx=round((bx0 + bx1) / 2 - cx, 1), dy=round((by0 + by1) / 2 - cy, 1),
                        top=round(by0 - cy, 1), bottom=round(by1 - cy, 1)))
    return out


def on_bg(im, color=BG):
    c = Image.new("RGBA", im.size, color)
    c.alpha_composite(im)
    return c


def fit_h(im, h):
    return im.resize((round(im.width * h / im.height), h), Image.Resampling.LANCZOS)


def panel(im, title, sub=None):
    """Картинка с подписью сверху."""
    pad = 46 if sub else 28
    P = Image.new("RGBA", (im.width, im.height + pad), (22, 24, 26, 255))
    label(P, title, 17, (4, 3))
    if sub:
        label(P, sub, 14, (4, 24), DIM)
    P.alpha_composite(on_bg(im), (0, pad))
    return P


def compare(key, frames):
    """Скетч 8.png рядом с игровым ракурсом модели на том же курсе (E-W), обе — одной высоты."""
    single, _, fr = game_view(key, "single", frames, K.PX_RENDER)
    s64, _, f64 = game_view(key, "single", frames, K.PX_GAME)
    # отметка центра спрайта тайла (куда игрок смотрит как на «центр клетки»)
    for im, f in ((single, fr), (s64, f64)):
        gx, gy = f.px(0, 0, 0)
        cy = gy + (K.SPRITE_TILE_PX / 2 - K.SPRITE_GROUND_PX[1]) * f.ppt / K.PX_GAME
        k = f.ppt / K.PX_GAME
        d = ImageDraw.Draw(im)
        col = (255, 60, 200, 255)
        d.line((gx - 30 * k, cy, gx - 22 * k, cy), fill=col, width=max(1, round(k / 2)))
        d.line((gx + 22 * k, cy, gx + 30 * k, cy), fill=col, width=max(1, round(k / 2)))
    H = 384
    parts = []
    if os.path.exists(SKETCH):
        parts.append(panel(fit_h(Image.open(SKETCH).convert("RGBA"), H), "скетч автора (8.png)", " "))
    parts.append(panel(fit_h(single, H), "модель, курс E-W, 256 px/тайл", "розовые засечки — центр спрайта тайла"))
    parts.append(panel(nearest(s64, H / s64.height), "она же в игре: 64 px/тайл, ×4 nearest", " "))
    # плоский силуэт — как читается заливкой
    a = np.asarray(downscale(Image.open(os.path.join(REN, "%s_single.png" % key)).convert("RGBA"), 4))[:, :, 3]
    flat = np.zeros(a.shape + (4,), np.uint8)
    flat[:, :, :3] = (52, 78, 72)
    flat[:, :, 3] = 255
    flat[a > 127, :3] = (226, 165, 80)
    parts.append(panel(nearest(Image.fromarray(flat, "RGBA"), H / a.shape[0]), "силуэт заливкой, 64 px/тайл", " "))
    W = sum(p.width for p in parts) + 12 * (len(parts) + 1)
    C = Image.new("RGBA", (W, parts[0].height + 12), (22, 24, 26, 255))
    x = 12
    for p in parts:
        C.alpha_composite(p, (x, 6))
        x += p.width + 12
    return C


def scheme(key, P):
    """Разрез с торца в манере скетчей автора: поверх рендера с торца — штрихи сил."""
    import math
    im = Image.open(os.path.join(REN, "%s_section.png" % key)).convert("RGBA")
    B = Image.new("RGBA", im.size, (40, 44, 46, 255))
    B.alpha_composite(im)
    im = B
    d = ImageDraw.Draw(im)
    S = 900
    X = lambda x, z: (450 + x * S, 450 - (z - 0.28) * S)
    WH, RED, GRN = (245, 245, 245, 255), (235, 40, 40, 255), (40, 200, 70, 255)

    def arrow(p0, p1, col, wdt=6):
        a, b = X(*p0), X(*p1)
        d.line((a, b), fill=col, width=wdt)
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        for da in (2.5, -2.5):
            d.line((b, (b[0] + 20 * math.cos(ang + da), b[1] + 20 * math.sin(ang + da))), fill=col, width=wdt)
    rw = K.RAIL_HALF_W
    zc = K.RAIL_TOP_Z - P["drop"]
    ps = math.radians(P["psi"])
    zm = (P["ck0"] + P["ck1"]) / 2
    for s in (1, -1):
        m = (s * math.sin(ps), math.cos(ps))
        nz = (s * math.cos(ps), -math.sin(ps))
        hub = (s * rw + m[0] * P["r"], zc + m[1] * P["r"])
        L = lambda y, z: (hub[0] + m[0] * (y - P["r"]) + nz[0] * z, hub[1] + m[1] * (y - P["r"]) + nz[1] * z)
        hp = L(P["hinge_y"], zm)
        sp = L(P["spring_y"], P["ck0"])
        # щека (белая линия вдоль колеса) от низа к верху
        d.line([X(*L(0.1, zm)), X(*L(P["r"] + 0.33, zm))], fill=WH, width=5)
        hx, hy = X(*hp)
        d.ellipse((hx - 15, hy - 15, hx + 15, hy + 15), outline=WH, width=5)
        # пружина: зигзаг от ящика к верху щеки, стрелка наружу
        x0, x1 = 0.12, abs(sp[0])
        pts = [X(s * (x0 + (x1 - x0) * i / 6), sp[1] + (0.012 if i % 2 else -0.012)) for i in range(7)]
        d.line(pts, fill=RED, width=5)
        arrow((s * x1, sp[1]), (s * (x1 + 0.08), sp[1]), RED)
        # поворот щеки вокруг шарнира: верх наружу, низ внутрь (зелёная дуга внизу)
        arrow((s * (rw + 0.10), zc), (s * (rw + 0.012), zc), GRN, 7)
        arc = [X(hp[0] + s * 0.13 * math.cos(a), hp[1] - 0.13 * math.sin(a)) for a in
               [math.radians(t) for t in range(10, 75, 8)]]
        d.line(arc, fill=GRN, width=5)
    d.rectangle((X(-rw, K.RAIL_TOP_Z), X(rw, 0)), outline=WH, width=4)
    arrow((0, 0.6), (0, 0.72), RED, 5)
    f = font(22)
    d.text(X(0.02, 0.73), "F отрыва", font=f, fill=RED)
    d.text(X(-0.48, 0.74), "пружины распирают верх щёк от ящика", font=f, fill=RED)
    d.text(X(-0.48, 0.71), "→ шарнир → колёса снизу сжимают лезвие", font=f, fill=GRN)
    W = im.width + 640
    C = Image.new("RGBA", (W, im.height), (28, 31, 33, 255))
    C.alpha_composite(im, (0, 0))
    a_sp = P["spring_y"] - P["hinge_y"]
    a_c = P["hinge_y"]
    txt = [
        "«Щёки-прищепки» — путь сил:",
        "",
        "Ящик целый, по центру. Щека — тонкая изломанная",
        "панель в плоскости колеса; колесо сидит на щеке.",
        "Щека качается на латунном пальце вдоль хода",
        "(белый кружок) — ниже ступицы, выше касания.",
        "",
        "Пружины ящик ↔ верх щеки распирают её наружу:",
        "щека поворачивается, низ с колесом идёт внутрь,",
        "кромка обода жмёт боковину лезвия (зелёные).",
        "Рычаг: пружина на %.2f от шарнира, касание на %.2f" % (a_sp, a_c),
        "→ прижим N ≈ %.1f × силы пружины." % (a_sp / a_c),
        "",
        "Отрыв держит трение: F < 2·μ·N, μ ≈ %.1f." % P["mu"],
        "Пружине всё равно, где «верх», — держит",
        "и в невесомости, и вверх ногами.",
        "Удар «в рельс» — V из колёс садится на углы лезвия.",
        "",
        "Док-рука берёт ящик за прорези на крыше,",
        "пальцами поджимает верх щёк к ящику:",
        "пружины сжаты, колёса расходятся — снято.",
    ]
    ImageDraw.Draw(C).multiline_text((im.width + 20, 20), "\n".join(txt), font=font(21), fill=INK, spacing=6)
    return C


def ortho_block(key):
    names = [("persp", "3/4 (как Perspective в C4D)"), ("top", "Top"), ("front", "Front: сбоку, колесо"),
             ("right", "Right: с торца, развал V")]
    ims = [panel(Image.open(os.path.join(REN, "%s_%s.png" % (key, n))).convert("RGBA"), t) for n, t in names]
    W = sum(i.width for i in ims) + 12 * (len(ims) + 1)
    C = Image.new("RGBA", (W, ims[0].height + 12), (22, 24, 26, 255))
    x = 12
    for i in ims:
        C.alpha_composite(i, (x, 6))
        x += i.width + 12
    return C


def metrics_text(m, P):
    dys = [e["dy"] for e in m]
    ew = [e for e in m if abs(abs(e["heading"]) - 90) < 1 or abs(e["heading"] - 270) < 1]
    ns = [e for e in m if e["heading"] % 180 < 1]
    lines = ["Замер силуэта по 32 курсам, 64 px/тайл (dy < 0 — центр рамки выше центра спрайта тайла):",
             "  dy среднее %+.1f px, от %+.1f до %+.1f;  высота рамки %d…%d px, ширина %d…%d px" % (
                 np.mean(dys), min(dys), max(dys), min(e["h"] for e in m), max(e["h"] for e in m),
                 min(e["w"] for e in m), max(e["w"] for e in m))]
    for nm, grp in (("E-W", ew), ("N-S", ns)):
        if grp:
            e = grp[0]
            lines.append("  %s: %d×%d px, dy %+.1f, верх %+.1f, низ %+.1f (от центра спрайта тайла)" % (
                nm, e["w"], e["h"], e["dy"], e["top"], e["bottom"]))
    lines.append("  Справка: тело на рельсе от z=0 до z_top даёт dy ≈ −22.6·z_top − 2.9;"
                 " для z_top = %.3f это %+.1f px;" % (P["z3"], -22.6 * P["z3"] - 2.9))
    lines.append("  на E-W рамку тянут вверх горб северного колеса, вниз — обод южного; ступица южного колеса"
                 " — в ~4 px над центром спрайта тайла.")
    return lines


def sheet(key, title, frames, m, P):
    field64, _, _ = game_view(key, "field", frames, K.PX_GAME)
    field256, _, fr256 = game_view(key, "field", frames, K.PX_RENDER)
    ring64, _, _ = game_view(key, "ring32", frames, K.PX_GAME)
    # крупно ×4: участок с поворотом и прямой E-W
    x0, y0 = fr256.px(-0.55, 0.55, 0)
    x1, y1 = fr256.px(3.55, -1.75, 0)
    close = field256.crop((int(x0), int(y0), int(x1), int(y1)))
    hero = Image.open(os.path.join(REN, "%s_hero.png" % key)).convert("RGBA")

    f2 = nearest(field64, 2)                                         # 960×768
    r2 = nearest(ring64, 2)                                          # 1024×576
    blocks = [
        [panel(f2, "Игровой масштаб: 64 px/тайл, ×2 nearest", "колонна N-S, ряд E-W, поезд с двумя поворотами; подложка — спрайт тайла"),
         panel(fit_h(close, f2.height), "Крупно: игровой ракурс 256 px/тайл (×4)", "та же сцена, поворот и прямая")],
        [panel(r2, "Все 32 курса листа (шаг 11.25°), 64 px/тайл ×2"),
         panel(fit_h(hero, r2.height), "Вид 3/4, без растяжки, болванка рельса")],
        [ortho_block(key)],
        [compare(key, frames)],
        [panel(scheme(key, P), 'Разрез с торца: как держат щёки-прищепки', 'рендер с торца 900 px/тайл + штрихи сил')],
    ]
    rows = []
    for row in blocks:
        W = sum(p.width for p in row) + 12 * (len(row) - 1)
        H = max(p.height for p in row)
        R = Image.new("RGBA", (W, H), (22, 24, 26, 255))
        x = 0
        for p in row:
            R.alpha_composite(p, (x, 0))
            x += p.width + 12
        rows.append(R)
    txt = metrics_text(m, P)
    W = max(r.width for r in rows) + 24
    H = 56 + sum(r.height + 14 for r in rows) + 22 * len(txt) + 20
    S = Image.new("RGBA", (W, H), (22, 24, 26, 255))
    label(S, "Каретка v8c — блокинг. " + title, 26, (12, 12))
    y = 56
    for r in rows:
        S.alpha_composite(r, (12, y))
        y += r.height + 14
    ImageDraw.Draw(S).multiline_text((16, y), "\n".join(txt), font=font(17), fill=INK, spacing=6)
    return S


def main():
    with open(os.path.join(REN, "frames.json"), encoding="utf-8") as f:
        frames = json.load(f)
    allm = {}
    for key, title, P in VARIANTS:
        if not os.path.exists(os.path.join(REN, "%s_field.png" % key)):
            continue
        m = metrics(key, frames)
        allm[key] = m
        S = sheet(key, title, frames, m, P)
        name = "sheet.png" if key == VARIANTS[0][0] else "sheet_%s.png" % key
        S.save(os.path.join(OUT, name))
        print("sheet", name, S.size, "dy avg %.1f" % np.mean([e["dy"] for e in m]))
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(allm, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
