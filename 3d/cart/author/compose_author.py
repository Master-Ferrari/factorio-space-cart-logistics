# -*- coding: utf-8 -*-
"""Листы интерпретаций концепта автора: рендеры поверх настоящих спрайтов тайла + замеры силуэта.

Запуск (системный python, Pillow + numpy):  python compose_author.py
Берёт out/render/*.png и frames.json, пишет:
  out/<K>_sheet.png      — лист интерпретации (поле 64 px ×2, крупно 256 px, курсы, 3/4, сбоку, замеры);
  out/overview.png       — все интерпретации на одном поле (64 px/тайл ×2);
  out/courses32.png, out/silhouettes.png — все 32 курса (с тенью / плоская заливка);
  out/sketch_vs_model.png — рисунки автора ↔ модель в том же ракурсе;
  out/metrics.json       — силуэт по 8 и 32 курсам: dy, верх, низ, габарит.
Подложка тайла и тень — логика cart/compose_blocking.py (скопирована, не импортирована).
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)
import scl3d as K  # noqa: E402
from author_concepts import KEYS, TITLES, SHORT  # noqa: E402

REN = os.path.join(HERE, "out", "render")
OUT = os.path.join(HERE, "out")
SKETCH = os.path.join(HERE, "out", "src", "sketch_1.png")
TILE_SPRITE = os.path.join(HERE, "..", "..", "sprites", "compose", "tile_63_111111.png")
FONT = "C:/Windows/Fonts/arial.ttf"
BG = (34, 38, 40, 255)

# Кропы скетча автора (px оригинала 1600×2586) ↔ вид модели
SKETCH_CROPS = [
    ("ряд 2 слева:\nкорпус, C-щёки,\nдва овала колёс,\nмежду ними головка\nрельса\n\nмодель: спереди-сверху", (258, 672, 724, 1035), "m_front"),
    ("ряд 3 справа:\nкорпус над\nколесом-диском с «+»\n\nмодель: сбоку", (672, 1112, 996, 1422), "m_side"),
    ("ряд 3 слева:\nоктагон, колесо\nсо втулкой снизу\n\nмодель: с торца\n(или это тоже\nвид сбоку?)", (310, 1112, 569, 1409), "m_end"),
    ("низ слева:\n«одно колесо должно\nхорошо делать составы»,\nдиск с прицелом внизу\n\nмодель: почти сбоку,\nчуть спереди-сверху", (168, 1733, 582, 2133), "m_34"),
]


def font(sz):
    try:
        return ImageFont.truetype(FONT, sz)
    except OSError:
        return ImageFont.load_default()


def downscale(im, f):
    """Bicubic Sharper (как в sprites/compose.py), по премультиплицированной альфе."""
    w, h = im.size
    small = im.convert("RGBa").resize((w // f, h // f), Image.Resampling.BICUBIC).convert("RGBA")
    return small.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))


def tile_bg(frame, tiles):
    """Подложка из спрайтов тайла: центр тайла на z=0 ↔ SPRITE_GROUND_PX спрайта."""
    k = frame.ppt / K.PX_GAME
    spr = Image.open(TILE_SPRITE).convert("RGBA")
    if k != 1:
        spr = spr.resize((round(spr.width * k), round(spr.height * k)), Image.Resampling.LANCZOS)
    gx, gy = K.SPRITE_GROUND_PX
    canvas = Image.new("RGBA", frame.res, BG)
    for tx, ty in sorted(tiles, key=lambda t: (-t[1], t[0])):
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
    if os.path.exists(shp):                        # тень из прохода на белой плоскости
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


def metrics(key, frames, view="ring"):
    """Силуэт на 64 px/тайл: смещение центра bbox от центра спрайта тайла (dy < 0 — выше)."""
    _, ren, fr = game_view(key, view, frames, K.PX_GAME)
    a = np.asarray(ren)[:, :, 3]
    out = []
    lift = K.SPRITE_TILE_PX / 2 - K.SPRITE_GROUND_PX[1]
    for (x, y), hd in zip(frames[view]["carts"], frames[view]["headings"]):
        px, py = fr.px(x, y, 0.0)
        cx, cy = px, py + lift
        x0, x1 = int(px - 60), int(px + 60)
        y0, y1 = int(py - 80), int(py + 50)
        sub = a[max(0, y0):y1, max(0, x0):x1] > 127
        # соседи на сетке 32 курсов стоят в 1 тайле: берём только связные куски, чей центр
        # ближе к своей точке земли, чем к соседним (±64 px)
        lab, n = ndimage.label(sub)
        keep = np.zeros_like(sub)
        gx, gy = px - max(0, x0), py - max(0, y0)
        for i, (sy_, sx_) in enumerate(ndimage.center_of_mass(sub, lab, range(1, n + 1))):
            if abs(sx_ - gx) < 32 and -46 < sy_ - gy < 18:
                keep |= lab == i + 1
        ys, xs = np.nonzero(keep)
        if not len(ys):
            continue
        bx0, bx1 = xs.min() + max(0, x0), xs.max() + 1 + max(0, x0)
        by0, by1 = ys.min() + max(0, y0), ys.max() + 1 + max(0, y0)
        out.append(dict(heading=round(hd, 2), w=int(bx1 - bx0), h=int(by1 - by0),
                        dx=round((bx0 + bx1) / 2 - cx, 1), dy=round((by0 + by1) / 2 - cy, 1),
                        top=round(by0 - cy, 1), bottom=round(by1 - cy, 1)))
    return out


def label(im, text, sz=22, pos=(10, 6), fill=(235, 235, 235, 255)):
    ImageDraw.Draw(im).multiline_text(pos, text, font=font(sz), fill=fill, spacing=3)


def nearest(im, k):
    return im.resize((im.width * k, im.height * k), Image.Resampling.NEAREST)


def on_bg(im, col=(45, 48, 52, 255)):
    c = Image.new("RGBA", im.size, col)
    c.alpha_composite(im)
    return c


def fit_h(im, h):
    return im.resize((round(im.width * h / im.height), h), Image.Resampling.LANCZOS)


def avg(m, k):
    return sum(e[k] for e in m) / max(1, len(m))


def sheet(key, frames, m8, m32):
    field64, _, _ = game_view(key, "field", frames, K.PX_GAME)
    field256, _, fr256 = game_view(key, "field", frames, K.PX_RENDER)
    x0, y0 = fr256.px(0.4, 1.75, 0)
    x1, y1 = fr256.px(3.5, -1.65, 0)
    close = field256.crop((int(x0), int(y0), int(x1), int(y1)))
    ring64, _, _ = game_view(key, "ring", frames, K.PX_GAME)
    side = on_bg(Image.open(os.path.join(REN, "%s_side.png" % key)).convert("RGBA"))
    hero = on_bg(Image.open(os.path.join(REN, "%s_hero.png" % key)).convert("RGBA"))
    f2 = nearest(field64, 2)
    close = fit_h(close, f2.height)
    r2 = nearest(ring64, 2)
    hero = fit_h(hero, r2.height)
    W = max(f2.width + close.width, r2.width + hero.width) + 30
    H = 50 + f2.height + 10 + r2.height + 10 + side.height + 20
    S = Image.new("RGBA", (W, H), (22, 24, 26, 255))
    label(S, TITLES[key], 28, (12, 10))
    y = 50
    S.alpha_composite(f2, (10, y)); label(S, "игровой масштаб 64 px/тайл ×2 (nearest)", 16, (16, y + 4))
    S.alpha_composite(close, (20 + f2.width, y)); label(S, "рендер 256 px/тайл, спрайт тайла ×4", 16, (26 + f2.width, y + 4))
    y += f2.height + 10
    S.alpha_composite(r2, (10, y)); label(S, "курсы через 45°, 64 px/тайл ×2", 16, (16, y + 4))
    S.alpha_composite(hero, (20 + r2.width, y)); label(S, "3/4 без растяжки, болванка рельса", 16, (26 + r2.width, y + 4))
    y += r2.height + 10
    S.alpha_composite(side, (10, y)); label(S, "поезд сбоку, без растяжки", 16, (16, y + 4))
    txt = ["силуэт, px при 64/тайл (dy < 0 — выше центра спрайта тайла):"]
    for e in m8:
        txt.append("  курс %4d°:  %2d×%2d  dy %+5.1f  верх %+5.1f  низ %+5.1f" % (
            e["heading"], e["w"], e["h"], e["dy"], e["top"], e["bottom"]))
    txt.append("32 курса: dy ср. %+.1f (от %+.1f до %+.1f), габарит до %d×%d" % (
        avg(m32, "dy"), min(e["dy"] for e in m32), max(e["dy"] for e in m32),
        max(e["w"] for e in m32), max(e["h"] for e in m32)))
    ImageDraw.Draw(S).multiline_text((30 + side.width, y), "\n".join(txt), font=font(15), fill=(220, 220, 220, 255))
    S.convert("RGB").save(os.path.join(OUT, "%s_sheet.png" % key))
    return field64


def overview(keys, fields, allm, frames):
    fr = K.Frame.from_dict(frames["field"]["frame"]).scaled(K.PX_GAME)
    x0, y0 = fr.px(-2.6, 3.0, 0)
    x1, y1 = fr.px(3.4, -1.7, 0)
    box = (int(x0), int(y0), int(x1), int(y1))
    tiles = [nearest(fields[k].crop(box), 2) for k in keys]
    tw, th = tiles[0].size
    cols = 2
    rows = math.ceil(len(tiles) / cols)
    O = Image.new("RGBA", (cols * (tw + 10) + 10, rows * (th + 50) + 10), (22, 24, 26, 255))
    for i, (k, t) in enumerate(zip(keys, tiles)):
        x, y = 10 + (i % cols) * (tw + 10), 10 + (i // cols) * (th + 50)
        label(O, TITLES[k], 17, (x, y + 2))
        label(O, "dy ср. %+.1f px (32 курса)" % avg(allm[k]["c32"], "dy"), 15, (x, y + 22), (170, 170, 170, 255))
        O.alpha_composite(t, (x, y + 40))
    O.convert("RGB").save(os.path.join(OUT, "overview.png"))


def courses32(keys, frames):
    sil, shd = [], []
    for k in keys:
        img, ren, _ = game_view(k, "ring32", frames, K.PX_GAME)
        a = np.asarray(ren)[:, :, 3]
        flat = np.full(a.shape + (4,), 232, np.uint8)
        flat[:, :, 3] = 255
        flat[a > 127, :3] = 28
        sil.append(nearest(Image.fromarray(flat, "RGBA"), 2))
        shd.append(nearest(img, 2))
    for name, ims, bg in (("silhouettes.png", sil, (240, 240, 240, 255)), ("courses32.png", shd, (22, 24, 26, 255))):
        tw, th = ims[0].size
        cols = 2
        rows = math.ceil(len(ims) / cols)
        O = Image.new("RGBA", (cols * (tw + 16) + 16, rows * (th + 40) + 16), bg)
        fg = (20, 20, 20, 255) if bg[0] > 128 else (235, 235, 235, 255)
        for i, (k, im) in enumerate(zip(keys, ims)):
            x, y = 16 + (i % cols) * (tw + 16), 16 + (i // cols) * (th + 40)
            label(O, TITLES[k] + "   (32 курса, 64 px/тайл ×2)", 17, (x, y + 4), fg)
            O.alpha_composite(im, (x, y + 32))
        O.convert("RGB").save(os.path.join(OUT, name))


def sketch_vs_model(keys):
    """Строки — рисунки автора; столбцы — кроп скетча и модели K1..K4 в подобранном ракурсе."""
    sk = Image.open(SKETCH).convert("RGBA")
    th = 300
    rows = []
    for text, box, view in SKETCH_CROPS:
        crop = fit_h(sk.crop(box), th)
        ims = [crop]
        for k in keys:
            p = os.path.join(REN, "%s_%s.png" % (k, view))
            ims.append(fit_h(on_bg(Image.open(p).convert("RGBA")), th))
        rows.append((text, ims))
    cw = [max(r[1][i].width for r in rows) for i in range(len(keys) + 1)]
    W = 300 + sum(cw) + 8 * (len(cw) + 1)
    H = 44 + len(rows) * (th + 10)
    S = Image.new("RGBA", (W, H), (22, 24, 26, 255))
    x = 300 + 8
    label(S, "скетч автора", 18, (x, 12))
    x += cw[0] + 8
    for i, k in enumerate(keys):
        label(S, "%s · %s" % (k, SHORT[k]), 18, (x, 12))
        x += cw[i + 1] + 8
    for j, (text, ims) in enumerate(rows):
        y = 44 + j * (th + 10)
        label(S, text, 14, (8, y + 8), (200, 200, 200, 255))
        x = 300 + 8
        for i, im in enumerate(ims):
            S.alpha_composite(im, (x, y))
            x += cw[i] + 8
    S.convert("RGB").save(os.path.join(OUT, "sketch_vs_model.png"))


def main():
    with open(os.path.join(REN, "frames.json"), encoding="utf-8") as f:
        frames = json.load(f)
    keys = [k for k in KEYS if os.path.exists(os.path.join(REN, "%s_ring32.png" % k))]
    allm, fields = {}, {}
    for k in keys:
        m8 = metrics(k, frames, "ring")
        m32 = metrics(k, frames, "ring32m")
        allm[k] = dict(c8=m8, c32=m32, dy_avg=round(avg(m32, "dy"), 1),
                       dy_min=min(e["dy"] for e in m32), dy_max=max(e["dy"] for e in m32))
        fields[k] = sheet(k, frames, m8, m32)
        print(k, "dy avg(32) %+.1f  [%+.1f .. %+.1f]" % (allm[k]["dy_avg"], allm[k]["dy_min"], allm[k]["dy_max"]))
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(allm, f, indent=1, ensure_ascii=False)
    overview(keys, fields, allm, frames)
    courses32(keys, frames)
    if all(os.path.exists(os.path.join(REN, "%s_%s.png" % (k, v))) for k in keys for _, _, v in SKETCH_CROPS):
        sketch_vs_model(keys)


if __name__ == "__main__":
    main()
