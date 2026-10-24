# -*- coding: utf-8 -*-
"""Листы v5a: рендеры поверх настоящего спрайта тайла (по якорю земли) + замер dy.

Запуск (системный python, Pillow + numpy):  python compose_v5a.py [--main A]
Пишет out/sheet_<K>.png для каждой вариации, out/sheet.png (основная) и out/metrics.json.
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
from params import MAIN, VARIANTS  # noqa: E402

REN = os.path.join(HERE, "out", "render")
OUT = os.path.join(HERE, "out")
TILE_SPRITE = os.path.join(HERE, "..", "..", "sprites", "compose", "tile_63_111111.png")
SKETCH = os.path.join(HERE, "ref", "8.png")
FONT = "C:/Windows/Fonts/arial.ttf"
BG = (34, 38, 40, 255)
PAGE = (22, 24, 26, 255)
LIFT = K.SPRITE_TILE_PX / 2 - K.SPRITE_GROUND_PX[1]       # центр спрайта тайла ниже «земли» на 2.9 px


def font(sz):
    try:
        return ImageFont.truetype(FONT, sz)
    except OSError:
        return ImageFont.load_default()


def label(im, text, pos, sz=17, fill=(235, 235, 235, 255)):
    ImageDraw.Draw(im).multiline_text(pos, text, font=font(sz), fill=fill, spacing=4)


def downscale(im, f):
    """Bicubic Sharper (как sprites/compose.py), по премультиплицированной альфе."""
    w, h = im.size
    small = im.convert("RGBa").resize((w // f, h // f), Image.Resampling.BICUBIC).convert("RGBA")
    return small.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))


def nearest(im, k):
    return im.resize((round(im.width * k), round(im.height * k)), Image.Resampling.NEAREST)


def fit_h(im, h):
    return im.resize((round(im.width * h / im.height), h), Image.Resampling.LANCZOS)


def tile_bg(frame, tiles):
    """Подложка: центр тайла на z=0 ↔ SPRITE_GROUND_PX спрайта. Спрайт масштабируется nearest
    (на ×4 видно настоящие пиксели игры)."""
    k = frame.ppt / K.PX_GAME
    spr = Image.open(TILE_SPRITE).convert("RGBA")
    if k != 1:
        spr = nearest(spr, k)
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
    if os.path.exists(shp):               # тень: проход на белой плоскости z = 0
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
    """Силуэт на 64 px/тайл по 32 курсам: габарит и смещение центра от центра спрайта тайла.
    dy < 0 — силуэт выше центра тайла."""
    _, ren, fr = game_view(key, "ring32", frames, K.PX_GAME)
    a = np.asarray(ren)[:, :, 3]
    out = []
    for (x, y), hd in zip(frames["ring32"]["carts"], frames["ring32"]["headings"]):
        px, py = fr.px(x, y, 0.0)
        cx, cy = px, py + LIFT
        x0, x1, y0, y1 = int(px - 39), int(px + 39), int(py - 76), int(py + 30)
        sub = a[max(0, y0):y1, max(0, x0):x1] > 127
        ys, xs = np.nonzero(sub)
        bx0, bx1 = xs.min() + max(0, x0), xs.max() + 1 + max(0, x0)
        by0, by1 = ys.min() + max(0, y0), ys.max() + 1 + max(0, y0)
        out.append(dict(heading=round(hd, 2), w=int(bx1 - bx0), h=int(by1 - by0),
                        dx=round((bx0 + bx1) / 2 - cx, 1), dy=round((by0 + by1) / 2 - cy, 1),
                        top=round(by0 - cy, 1), bottom=round(by1 - cy, 1)))
    return out


def flat(ren, fg=(28, 28, 28), bg=(232, 232, 232)):
    a = np.asarray(ren)[:, :, 3]
    im = np.zeros(a.shape + (4,), np.uint8)
    im[:, :, :3] = bg
    im[:, :, 3] = 255
    im[a > 127, :3] = fg
    return Image.fromarray(im, "RGBA")


def on(im, bg=BG, pad=0):
    c = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), bg)
    c.alpha_composite(im, (pad, pad))
    return c


def panel(im, title, sub=None):
    """Картинка с подписью сверху."""
    h = 30 if not sub else 52
    c = Image.new("RGBA", (im.width, im.height + h), PAGE)
    c.alpha_composite(im, (0, h))
    label(c, title, (4, 4), 17)
    if sub:
        label(c, sub, (4, 27), 14, (170, 170, 170, 255))
    return c


def row(ims, gap=12):
    W = sum(i.width for i in ims) + gap * (len(ims) - 1)
    H = max(i.height for i in ims)
    c = Image.new("RGBA", (W, H), PAGE)
    x = 0
    for i in ims:
        c.alpha_composite(i, (x, 0))
        x += i.width + gap
    return c


def col(ims, gap=16):
    W = max(i.width for i in ims)
    H = sum(i.height for i in ims) + gap * (len(ims) - 1)
    c = Image.new("RGBA", (W, H), PAGE)
    y = 0
    for i in ims:
        c.alpha_composite(i, (0, y))
        y += i.height + gap
    return c


def sheet(key, frames, m):
    P = VARIANTS[key]
    # 1. игровой масштаб: поле 64 px/тайл ×2
    field64, _, fr64 = game_view(key, "field", frames, K.PX_GAME)
    f2 = nearest(field64, 2)
    # 2. крупно ×4: участок поля на 256 px/тайл (поворот + E-W)
    field256, _, fr = game_view(key, "field", frames, K.PX_RENDER)
    x0, y0 = fr.px(-1.6, 0.85, 0)
    x1, y1 = fr.px(2.6, -2.55, 0)
    close = field256.crop((int(x0), int(y0), int(x1), int(y1)))
    x0, y0 = fr.px(-3.6, 3.3, 0)
    x1, y1 = fr.px(1.0, 1.45, 0)
    close_ew = field256.crop((int(x0), int(y0), int(x1), int(y1)))
    # 3. 32 курса
    r64, ren32, _ = game_view(key, "ring32", frames, K.PX_GAME)
    r2 = nearest(r64, 2)
    s2 = nearest(flat(ren32), 2)
    # 4. скетч и игровой ракурс того же курса (на восток)
    solo256, solo_ren, sfr = game_view(key, "solo", frames, K.PX_RENDER)
    solo64, solo_ren64, _ = game_view(key, "solo", frames, K.PX_GAME)
    hh = 384
    sk = Image.open(SKETCH).convert("RGBA")
    sk_panel = panel(fit_h(on(sk, (52, 74, 70, 255)), hh), "8.png — силуэт скетча")
    cart_only = solo_ren.crop(solo_ren.getbbox())
    flat_sil = flat(cart_only, (240, 170, 80), (52, 74, 70))
    sil_panel = panel(fit_h(on(flat_sil, (52, 74, 70, 255), 12), hh), "моя модель: плоский силуэт, курс E")
    solo_panel = panel(fit_h(solo256, hh), "тот же курс на тайле, 256 px/тайл (×4)")
    solo64_panel = panel(nearest(solo64, 4).resize((hh, hh), Image.Resampling.NEAREST),
                         "в игре: 64 px/тайл, nearest ×4")
    # 5. ортовиды и 3/4
    ortho = []
    for v, t in (("top", "Top — сверху"), ("right", "Right — с торца: V колёс на лезвии"),
                 ("front", "Front — сбоку: колесо плашмя"), ("parallel", "Parallel — 45°, без растяжки")):
        ortho.append(panel(on(Image.open(os.path.join(REN, "%s_%s.png" % (key, v))).convert("RGBA")), t))
    orth = col([row(ortho[:2], 8), row(ortho[2:], 8)], 8)
    hero = panel(on(Image.open(os.path.join(REN, "%s_hero.png" % key)).convert("RGBA")),
                 "3/4, перспектива, болванка рельса (без растяжки)")
    hero = hero.resize((round(hero.width * orth.height / hero.height), orth.height), Image.Resampling.LANCZOS)
    # 6. замер
    dys = [e["dy"] for e in m]
    ew = [e for e in m if round(e["heading"]) % 180 == 90]
    ns = [e for e in m if round(e["heading"]) % 180 == 0]
    txt = ["Замер силуэта при 64 px/тайл (dy < 0 — центр силуэта выше центра спрайта тайла)",
           "dy средний по 32 курсам: %+.1f px   (мин %+.1f, макс %+.1f)" % (np.mean(dys), min(dys), max(dys)),
           "E-W: %d×%d px, dy %+.1f, верх %+.1f, низ %+.1f" % (ew[0]["w"], ew[0]["h"], ew[0]["dy"], ew[0]["top"], ew[0]["bottom"]),
           "N-S: %d×%d px, dy %+.1f, верх %+.1f, низ %+.1f" % (ns[0]["w"], ns[0]["h"], ns[0]["dy"], ns[0]["top"], ns[0]["bottom"]),
           "", "курс   w×h    dy     курс   w×h    dy     курс   w×h    dy     курс   w×h    dy"]
    for i in range(8):
        cells = []
        for j in range(4):
            e = m[i + 8 * j]
            cells.append("%5.1f° %2d×%2d %+5.1f" % (e["heading"], e["w"], e["h"], e["dy"]))
        txt.append("   ".join(cells))
    tb = Image.new("RGBA", (r2.width, 250), PAGE)
    ImageDraw.Draw(tb).multiline_text((8, 6), "\n".join(txt), font=ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 15),
                                      fill=(225, 225, 225, 255), spacing=5)

    blocks = [
        panel(row([f2, fit_h(close, f2.height)]),
              "Игровой масштаб: поезда E-W (верх), N-S (слева), поворот (низ) — слева 64 px/тайл ×2 nearest, справа рендер 256 px/тайл (×4) поверх спрайта ×4",
              "тень — второй проход Workbench на белой плоскости z = 0; спрайт тайла подложен по якорю земли (40, 37.1)"),
        panel(fit_h(close_ew, 380), "Крупно ×4: поезд на восток — «одно колесо делает составы»"),
        panel(row([sk_panel, sil_panel, solo_panel, solo64_panel]), "Скетч автора и моя модель в том же курсе"),
        panel(row([r2, s2]), "Все 32 курса (шаг 11.25°), 64 px/тайл ×2: с тенью на тайле и плоским силуэтом"),
        tb,
        panel(row([orth, hero]), "Ортовиды как в окнах C4D автора (каретка идёт на восток) и 3/4"),
    ]
    S = col(blocks, 22)
    page = Image.new("RGBA", (S.width + 24, S.height + 70), PAGE)
    label(page, "v5a · %s" % P["title"], (12, 12), 26)
    page.alpha_composite(S, (12, 58))
    page.convert("RGB").save(os.path.join(OUT, "sheet_%s.png" % key), optimize=True)
    return page


def main():
    with open(os.path.join(REN, "frames.json"), encoding="utf-8") as f:
        frames = json.load(f)
    allm = {}
    for key in VARIANTS:
        if not os.path.exists(os.path.join(REN, "%s_field.png" % key)):
            continue
        allm[key] = m = metrics(key, frames)
        page = sheet(key, frames, m)
        if key == MAIN:
            page.convert("RGB").save(os.path.join(OUT, "sheet.png"), optimize=True)
        print(key, "dy avg %+.1f  E-W %+.1f  N-S %+.1f" % (
            np.mean([e["dy"] for e in m]), m[8]["dy"], m[0]["dy"]))
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(allm, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
