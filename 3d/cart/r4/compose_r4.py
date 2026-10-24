# -*- coding: utf-8 -*-
"""Раунд 4: листы и замеры (системный python, Pillow + numpy).

  python compose_r4.py

Берёт out/render/*.png и frames.json, подкладывает настоящие спрайты тайла по якорю земли,
пишет out/explore.png (схемы-альтернативы), out/sheet.png (финальный лист), out/metrics.json.
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)
import scl3d as K  # noqa: E402
from keys import KEYS, MAIN, TITLES  # noqa: E402

REN = os.path.join(HERE, "out", "render")
OUT = os.path.join(HERE, "out")
SPR = os.path.join(HERE, "..", "..", "sprites", "compose")
TILE_FULL = os.path.join(SPR, "tile_63_111111.png")
FONT = "C:/Windows/Fonts/arial.ttf"
FONTB = "C:/Windows/Fonts/arialbd.ttf"
BG = (34, 38, 40, 255)
PAPER = (22, 24, 26, 255)
OLD = os.path.join(HERE, "..", "blocking")


def font(sz, bold=False):
    try:
        return ImageFont.truetype(FONTB if bold else FONT, sz)
    except OSError:
        return ImageFont.load_default()


def downscale(im, f):
    """Bicubic Sharper (как в sprites/compose.py), по премультиплицированной альфе."""
    w, h = im.size
    small = im.convert("RGBa").resize((w // f, h // f), Image.Resampling.BICUBIC).convert("RGBA")
    return small.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))


def tile_bg(frame, tiles, sprite=TILE_FULL):
    k = frame.ppt / K.PX_GAME
    spr = Image.open(sprite).convert("RGBA")
    if k != 1:
        spr = spr.resize((round(spr.width * k), round(spr.height * k)), Image.Resampling.LANCZOS)
    gx, gy = K.SPRITE_GROUND_PX
    canvas = Image.new("RGBA", frame.res, BG)
    for tx, ty in sorted(tiles, key=lambda t: (-t[1], t[0])):
        px, py = frame.px(tx, ty, 0.0)
        canvas.alpha_composite(spr, (round(px - gx * k), round(py - gy * k)))
    return canvas


def game_view(key, view, frames, ppt, tiles=True):
    fr = K.Frame.from_dict(frames[view]["frame"]).scaled(ppt)
    ren = Image.open(os.path.join(REN, "%s_%s.png" % (key, view))).convert("RGBA")
    f = K.PX_RENDER // ppt
    if f > 1:
        ren = downscale(ren, f)
    bg = tile_bg(fr, [tuple(t) for t in frames[view]["tiles"]]) if tiles else Image.new("RGBA", fr.res, BG)
    shp = os.path.join(REN, "%s_%s_sh.png" % (key, view))
    if os.path.exists(shp):
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


def metrics(key, view, frames):
    """Силуэт на 64 px/тайл: центр рамки силуэта относительно центра спрайта тайла."""
    _, ren, fr = game_view(key, view, frames, K.PX_GAME, tiles=False)
    a = np.asarray(ren)[:, :, 3]
    lift = K.SPRITE_TILE_PX / 2 - K.SPRITE_GROUND_PX[1]
    out = []
    for (x, y), hd in zip(frames[view]["carts"], frames[view]["headings"]):
        px, py = fr.px(x, y, 0.0)
        cx, cy = px, py + lift
        # окно: в ring32 соседи стоят через 1 тайл — низ соседа сверху на ~41 px выше «земли»
        up = 39 if view == "ring32" else 90  # ring32w/ring8 — соседи через 2 тайла
        x0, x1 = int(px - 32), int(px + 32)
        y0, y1 = int(py - up), int(py + 32)
        sub = a[max(0, y0):y1, max(0, x0):x1] > 127
        ys, xs = np.nonzero(sub)
        if not len(ys):
            continue
        bx0, bx1 = xs.min() + max(0, x0), xs.max() + 1 + max(0, x0)
        by0, by1 = ys.min() + max(0, y0), ys.max() + 1 + max(0, y0)
        out.append(dict(heading=round(hd, 2), w=int(bx1 - bx0), h=int(by1 - by0),
                        dx=round((bx0 + bx1) / 2 - cx, 1), dy=round((by0 + by1) / 2 - cy, 1),
                        top=round(by0 - cy, 1), bottom=round(by1 - cy, 1)))
    return out


def stat(m):
    d = [e["dy"] for e in m]
    return sum(d) / len(d), min(d), max(d)


def label(im, text, sz=18, pos=(10, 6), fill=(235, 235, 235, 255), bold=False):
    ImageDraw.Draw(im).text(pos, text, font=font(sz, bold), fill=fill)


def nearest(im, k):
    return im.resize((im.width * k, im.height * k), Image.Resampling.NEAREST)


def silhouette(ren):
    a = np.asarray(ren)[:, :, 3]
    flat = np.full(a.shape + (4,), 232, np.uint8)
    flat[:, :, 3] = 255
    flat[a > 127, :3] = 28
    return Image.fromarray(flat, "RGBA")


def explore(frames, allm):
    """Схемы-альтернативы: 8 курсов на тайлах + плоский силуэт, dy по 8 курсам."""
    keys = [k for k in KEYS if os.path.exists(os.path.join(REN, "%s_ring8.png" % k))]
    rows = []
    for k in keys:
        img, ren, fr = game_view(k, "ring8", frames, K.PX_GAME)
        rows.append((k, nearest(img, 2), nearest(silhouette(ren), 2)))
    tw, th = rows[0][1].size
    W = 2 * tw + 30
    H = len(rows) * (th + 50) + 20
    O = Image.new("RGBA", (W, H), PAPER)
    for i, (k, a, b) in enumerate(rows):
        y = 10 + i * (th + 50)
        av, mn, mx = stat(allm[k]["ring8"])
        label(O, "%s     dy ср. %+.1f px (%+.1f…%+.1f)" % (TITLES[k], av, mn, mx), 19, (12, y + 6), bold=(k == MAIN))
        O.alpha_composite(a, (10, y + 36))
        O.alpha_composite(b, (20 + tw, y + 36))
    O.save(os.path.join(OUT, "explore.png"))


def main():
    frames = json.load(open(os.path.join(REN, "frames.json"), encoding="utf-8"))
    allm = {}
    for k in KEYS:
        allm[k] = {}
        for view in ("ring8", "ring32w"):
            if os.path.exists(os.path.join(REN, "%s_%s.png" % (k, view))):
                allm[k][view] = metrics(k, view, frames)
                print(k, view, "dy avg %.1f (%.1f…%.1f)" % stat(allm[k][view]))
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(allm, f, indent=1, ensure_ascii=False)
    explore(frames, allm)
    if os.path.exists(os.path.join(REN, "%s_field.png" % MAIN)):
        import sheet_r4
        sheet_r4.build(frames, allm)


if __name__ == "__main__":
    main()
