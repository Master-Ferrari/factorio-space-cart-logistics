# -*- coding: utf-8 -*-
"""Игровой атлас каретки из рендеров atlas.py (системный python, Pillow + numpy).

Запуск:  python compose_atlas.py
Берёт out/atlas/obj_NN.png, all_NN.png, frame.json. Тень = доля альфы all сверх obj (shadow catcher).
Пишет ../../../graphics/cart.png и cart-shadow.png (32 кадра в строку, общая ячейка W×H при 64 px/тайл),
out/atlas/atlas.json (ячейка и shift для data.lua), out/atlas/preview.png (кадры на тайле, ×2).
Якорь: точка земли (0, 0, 0) встаёт на 2.9 px выше позиции сущности — как центр тайла в спрайте тайла
(SPRITE_GROUND_PX), иначе каретка не сядет на рельс.
"""

import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)
import scl3d as K  # noqa: E402
from compose import downscale, nearest, TILE_SPRITE, BG  # noqa: E402

SRC = os.path.join(HERE, "out", "atlas")
GFX = os.path.normpath(os.path.join(HERE, "..", "..", "..", "graphics"))
PAD = 1                                         # поле вокруг общей рамки силуэтов, px
HAZE = 0.06                                     # дымка AO от HDRI на catcher (альфа до ~0.05 на пол-кадра) — срезаем


def load(name, f):
    return downscale(Image.open(os.path.join(SRC, name)).convert("RGBA"), f)


def main():
    meta = json.load(open(os.path.join(SRC, "frame.json"), encoding="utf-8"))
    f = K.PX_RENDER // K.PX_GAME
    n = meta["facings"]
    gx, gy = meta["ground"][0] / f, meta["ground"][1] / f        # точка земли в кадре 64 px/тайл
    objs, shads = [], []
    for i in range(1, n + 1):
        o = load("obj_%02d.png" % i, f)
        a_all = np.asarray(load("all_%02d.png" % i, f), np.float32)[:, :, 3] / 255
        a_obj = np.asarray(o, np.float32)[:, :, 3] / 255
        sh = np.clip((a_all - a_obj) / np.maximum(1 - a_obj, 1e-3), 0, 1)
        sh = np.clip((sh - HAZE) / (1 - HAZE), 0, 1)
        sh[a_obj > 0.98] = 0                    # под корпусом тень не видна — не тащим мусор
        s = np.zeros(sh.shape + (4,), np.uint8)
        s[:, :, 3] = (sh * 255).round().astype(np.uint8)
        objs.append(o)
        shads.append(Image.fromarray(s, "RGBA"))
    # общая рамка всех кадров (каретка + тень), симметрия не нужна — её снимает shift
    box = None
    for im in objs + shads:
        b = im.getchannel("A").point(lambda v: 255 if v > 2 else 0).getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    W, H = objs[0].size
    if box[0] == 0 or box[1] == 0 or box[2] == W or box[3] == H:
        sys.exit("силуэт упёрся в край кадра atlas.FRAME: %s в %dx%d" % (box, W, H))
    x0, y0 = box[0] - PAD, box[1] - PAD
    w, h = box[2] - box[0] + 2 * PAD, box[3] - box[1] + 2 * PAD
    w, h = w + w % 2, h + h % 2
    # пиксель (gx, gy) ячейки должен лечь на позицию − 2.9 px: центр ячейки + shift + (g − c) = −2.9
    lift = K.SPRITE_TILE_PX / 2 - K.SPRITE_GROUND_PX[1]
    shift = ((w / 2 - (gx - x0)) / K.PX_GAME, (h / 2 - (gy - y0) - lift) / K.PX_GAME)
    sheet_o = Image.new("RGBA", (w * n, h))
    sheet_s = Image.new("RGBA", (w * n, h))
    for i in range(n):
        sheet_o.paste(objs[i].crop((x0, y0, x0 + w, y0 + h)), (i * w, 0))
        sheet_s.paste(shads[i].crop((x0, y0, x0 + w, y0 + h)), (i * w, 0))
    sheet_o.save(os.path.join(GFX, "cart.png"), optimize=True)
    sheet_s.save(os.path.join(GFX, "cart-shadow.png"), optimize=True)
    info = dict(width=w, height=h, line_length=n, variation_count=n, shift=[round(shift[0], 4), round(shift[1], 4)])
    json.dump(info, open(os.path.join(SRC, "atlas.json"), "w", encoding="utf-8"), indent=1)
    print("atlas %dx%d cell %dx%d shift %s" % (w * n, h, w, h, info["shift"]))
    preview(sheet_o, sheet_s, w, h, n, shift)


def preview(sheet_o, sheet_s, w, h, n, shift):
    """Кадры как в игре: тайл по якорю, тень (≈ ванильная плотность 0.5), каретка; 8×4, ×2."""
    tile = Image.open(TILE_SPRITE).convert("RGBA")
    cell = 128
    P = Image.new("RGBA", (cell * 8, cell * 4), BG)
    for i in range(n):
        cx, cy = (i % 8) * cell + cell // 2, (i // 8) * cell + cell // 2        # позиция сущности
        P.alpha_composite(tile, (round(cx - tile.width / 2), round(cy - tile.height / 2)))
        ox = round(cx - w / 2 + shift[0] * K.PX_GAME)
        oy = round(cy - h / 2 + shift[1] * K.PX_GAME)
        s = sheet_s.crop((i * w, 0, (i + 1) * w, h))
        s.putalpha(s.getchannel("A").point(lambda v: v // 2))
        P.alpha_composite(s, (ox, oy))
        P.alpha_composite(sheet_o.crop((i * w, 0, (i + 1) * w, h)), (ox, oy))
    nearest(P, 2).save(os.path.join(SRC, "preview.png"))


if __name__ == "__main__":
    main()
