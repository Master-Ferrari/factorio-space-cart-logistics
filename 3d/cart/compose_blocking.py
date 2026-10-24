# -*- coding: utf-8 -*-
"""Листы блокинга: рендеры кареток поверх настоящих спрайтов тайла + замеры силуэта.

Запуск (системный python, Pillow + numpy):  python compose_blocking.py
Берёт blocking/render/*.png и frames.json, пишет blocking/<K>_sheet.png,
blocking/overview.png и blocking/metrics.json.
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
import scl3d as K  # noqa: E402
sys.path.insert(0, HERE)
from concepts import CURRENT, TITLES  # noqa: E402

REN = os.path.join(HERE, "blocking", "render")
OUT = os.path.join(HERE, "blocking")
TILE_SPRITE = os.path.join(HERE, "..", "sprites", "compose", "tile_63_111111.png")
FONT = "C:/Windows/Fonts/arial.ttf"

BG = (34, 38, 40, 255)


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
    for tx, ty in sorted(tiles, key=lambda t: (-t[1], t[0])):       # север раньше юга
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
    if os.path.exists(shp):                        # Workbench: тень из прохода на белой плоскости
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
    """Силуэт по кольцу курсов на 64 px/тайл: смещение центра от центра спрайта тайла."""
    _, ren, fr = game_view(key, "ring", frames, K.PX_GAME)
    a = np.asarray(ren)[:, :, 3]
    out = []
    lift = K.SPRITE_TILE_PX / 2 - K.SPRITE_GROUND_PX[1]           # центр спрайта ниже «земли»
    for (x, y), hd in zip(frames["ring"]["carts"], frames["ring"]["headings"]):
        px, py = fr.px(x, y, 0.0)
        cx, cy = px, py + lift
        x0, x1 = int(px - 64), int(px + 64)
        y0, y1 = int(py - 80), int(py + 64)
        sub = a[max(0, y0):y1, max(0, x0):x1] > 127
        ys, xs = np.nonzero(sub)
        if not len(ys):
            continue
        bx0, bx1 = xs.min() + max(0, x0), xs.max() + 1 + max(0, x0)
        by0, by1 = ys.min() + max(0, y0), ys.max() + 1 + max(0, y0)
        out.append(dict(heading=round(hd), w=int(bx1 - bx0), h=int(by1 - by0),
                        dx=round((bx0 + bx1) / 2 - cx, 1), dy=round((by0 + by1) / 2 - cy, 1),
                        top=round(by0 - cy, 1), bottom=round(by1 - cy, 1)))
    return out


def label(im, text, sz=22, pos=(10, 6), fill=(235, 235, 235, 255)):
    d = ImageDraw.Draw(im)
    d.text(pos, text, font=font(sz), fill=fill)


def nearest(im, k):
    return im.resize((im.width * k, im.height * k), Image.Resampling.NEAREST)


def on_bg(im, pad=0):
    c = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), BG)
    c.alpha_composite(im, (pad, pad))
    return c


def sheet(key, frames, m):
    field64, _, _ = game_view(key, "field", frames, K.PX_GAME)
    field256, _, fr256 = game_view(key, "field", frames, K.PX_RENDER)
    # крупно: участок с поворотами (тайлы x 0.5..3.5, y -1.6..1.6)
    x0, y0 = fr256.px(0.4, 1.75, 0)
    x1, y1 = fr256.px(3.5, -1.65, 0)
    close = field256.crop((int(x0), int(y0), int(x1), int(y1)))
    ring64, _, _ = game_view(key, "ring", frames, K.PX_GAME)
    side = on_bg(Image.open(os.path.join(REN, "%s_side.png" % key)).convert("RGBA"))
    hero = on_bg(Image.open(os.path.join(REN, "%s_hero.png" % key)).convert("RGBA"))

    f2 = nearest(field64, 2)                                       # 960×768
    close = close.resize((round(close.width * f2.height / close.height), f2.height), Image.Resampling.LANCZOS)
    r2 = nearest(ring64, 2)                                        # 1024×576
    hero = hero.resize((round(hero.width * r2.height / hero.height), r2.height), Image.Resampling.LANCZOS)
    W = max(f2.width + close.width, r2.width + hero.width) + 30
    H = 50 + f2.height + 10 + r2.height + 10 + side.height + 60
    S = Image.new("RGBA", (W, H), (22, 24, 26, 255))
    label(S, TITLES[key], 28, (12, 10))
    y = 50
    S.alpha_composite(f2, (10, y)); label(S, "игровой масштаб 64 px/тайл ×2 (nearest)", 16, (16, y + 4))
    S.alpha_composite(close, (20 + f2.width, y)); label(S, "рендер 256 px/тайл, спрайт тайла ×4", 16, (26 + f2.width, y + 4))
    y += f2.height + 10
    S.alpha_composite(r2, (10, y)); label(S, "курсы через 45°, 64 px/тайл ×2", 16, (16, y + 4))
    S.alpha_composite(hero, (20 + r2.width, y)); label(S, "3/4 без растяжки, болванка рельса", 16, (26 + r2.width, y + 4))
    y += r2.height + 10
    S.alpha_composite(side, (10, y)); label(S, "сбоку, без растяжки", 16, (16, y + 4))
    txt = ["силуэт (px при 64/тайл; dy < 0 — выше центра спрайта тайла):"]
    for e in m:
        txt.append("  курс %4d°:  %2d×%2d  dy %+5.1f  верх %+5.1f  низ %+5.1f" % (
            e["heading"], e["w"], e["h"], e["dy"], e["top"], e["bottom"]))
    d = ImageDraw.Draw(S)
    d.multiline_text((30 + side.width, y), "\n".join(txt), font=font(15), fill=(220, 220, 220, 255))
    S.save(os.path.join(OUT, "%s_sheet.png" % key))
    return field64


def main():
    with open(os.path.join(REN, "frames.json"), encoding="utf-8") as f:
        frames = json.load(f)
    keys = [k for k, _, _ in CURRENT if os.path.exists(os.path.join(REN, "%s_field.png" % k))]
    allm, fields = {}, {}
    for k in keys:
        allm[k] = metrics(k, frames)
        fields[k] = sheet(k, frames, allm[k])
        print(k, "dy avg %.1f" % (sum(e["dy"] for e in allm[k]) / max(1, len(allm[k]))))
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(allm, f, indent=1, ensure_ascii=False)
    # обзор: участок поля с поездами (x -2.6..3.4, y -1.7..2.6), 64 px/тайл ×2
    fr = K.Frame.from_dict(frames["field"]["frame"]).scaled(K.PX_GAME)
    x0, y0 = fr.px(-2.6, 3.0, 0)
    x1, y1 = fr.px(3.4, -1.7, 0)
    box = (int(x0), int(y0), int(x1), int(y1))
    cols = 2
    tiles = [nearest(fields[k].crop(box), 2) for k in keys]
    tw, th = tiles[0].size
    rows = math.ceil(len(tiles) / cols)
    O = Image.new("RGBA", (cols * (tw + 10) + 10, rows * (th + 50) + 10), (22, 24, 26, 255))
    for i, (k, t) in enumerate(zip(keys, tiles)):
        x, y = 10 + (i % cols) * (tw + 10), 10 + (i // cols) * (th + 50)
        label(O, TITLES[k], 17, (x, y + 2))
        label(O, "dy ср. %+.1f px" % (sum(e["dy"] for e in allm[k]) / len(allm[k])), 15, (x, y + 22), (170, 170, 170, 255))
        O.alpha_composite(t, (x, y + 40))
    O.save(os.path.join(OUT, "overview.png"))
    # 3/4 всех концептов на болванке рельса — чтобы видеть формы, которые сверху не читаются
    heroes = [on_bg(Image.open(os.path.join(REN, "%s_hero.png" % k)).convert("RGBA")) for k in keys]
    hw_, hh_ = heroes[0].width // 2, heroes[0].height // 2
    cols = 4
    rows = math.ceil(len(heroes) / cols)
    Hs = Image.new("RGBA", (cols * (hw_ + 8) + 8, rows * (hh_ + 30) + 8), (22, 24, 26, 255))
    for i, (k, h) in enumerate(zip(keys, heroes)):
        x, y = 8 + (i % cols) * (hw_ + 8), 8 + (i // cols) * (hh_ + 30)
        label(Hs, TITLES[k].split(" — ")[0], 17, (x, y + 2))
        Hs.alpha_composite(h.resize((hw_, hh_), Image.Resampling.LANCZOS), (x, y + 28))
    Hs.save(os.path.join(OUT, "heroes.png"))
    courses32(keys, frames)


def courses32(keys, frames):
    """Все 32 курса листа при 64 px/тайл ×2: плоские силуэты (silhouettes.png) и с тенью
    на тайлах (courses32.png). Силуэт должен читаться на любом курсе."""
    keys = [k for k in keys if os.path.exists(os.path.join(REN, "%s_ring32.png" % k))]
    if not keys or "ring32" not in frames:
        return
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
            label(O, TITLES[k] + "   (32 курса, шаг 11.25°, 64 px/тайл ×2)", 17, (x, y + 4), fg)
            O.alpha_composite(im, (x, y + 32))
        O.save(os.path.join(OUT, name))


if __name__ == "__main__":
    main()
