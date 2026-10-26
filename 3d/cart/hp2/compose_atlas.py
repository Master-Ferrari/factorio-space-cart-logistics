# -*- coding: utf-8 -*-
"""Игровой атлас каретки из рендеров atlas.py (системный python, Pillow + numpy).

Запуск:  python compose_atlas.py            # атлас в graphics/
         python compose_atlas.py --test out/leds_test   # пробные курсы оттуда: test.png (64 px/тайл ×4), graphics не трогает
Берёт out/atlas/obj_NN.png, sh_NN.png, light_NN.png, frame.json. Тень = альфа sh (shadow catcher, каретка невидима
камере) — целая, и под корпусом: прежнее вычитание альф «с кареткой − без» вырезало дыру со светлыми швами по контуру.
Свет (draw_as_light) = проход, где светят только ходовые огни: полосы и подсвеченный ими металл, плюс глоу от полос,
обрезанный кругом GLOW_R px (автор: «итоговый глоу должен быть не больше пяти пикселей в радиусе», затем
«рдиус свечения увеличь в полтора раза» — 7.5).
Пишет ../../../graphics/cart.png, cart-shadow.png, cart-light.png (32 кадра в строку, общая ячейка W×H при 64 px/тайл),
out/atlas/atlas.json (ячейка и shift для data.lua), out/atlas/preview.png (кадры на тайле, ×2).
Якорь: точка земли (0, 0, 0) встаёт на 2.9 px выше позиции сущности — как центр тайла в спрайте тайла
(SPRITE_GROUND_PX), иначе каретка не сядет на рельс.
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)
import scl3d as K  # noqa: E402
from compose import downscale, nearest, TILE_SPRITE, BG  # noqa: E402

SRC = os.path.join(HERE, "out", "atlas")
SRC_B = os.path.join(HERE, "out", "atlas_b")           # колёса повёрнуты (atlas.py --wheels)
GFX = os.path.normpath(os.path.join(HERE, "..", "..", "..", "graphics"))
PAD = 1                                         # поле вокруг общей рамки силуэтов, px
HAZE = 0.06                                     # дымка AO от HDRI на catcher (альфа до ~0.05 на пол-кадра) — срезаем
GLOW_R = 7.5                                    # радиус глоу от полос, px при 64 px/тайл — жёсткая граница
GLOW_SIGMA = 2.4                                # мягкость глоу внутри этого круга
GLOW_K = 0.9                                    # сила глоу относительно полосы
CORE = 0.75                                     # порог яркости «сама полоса» в проходе света
LIT_GAIN = 2.5                                  # подъём подсветки металла (она слабая: полосы маленькие)
NIGHT = 0.12                                    # пробник: тьма ночи в карте освещения


def load(name, f, src=SRC):
    return downscale(Image.open(os.path.join(src, name)).convert("RGBA"), f)


def frame(i, f, src=SRC):
    """Курс i при 64 px/тайл: каретка и тень (доля альфы all сверх obj, без дымки AO)."""
    o = load("obj_%02d.png" % i, f, src)
    sh = np.asarray(load("sh_%02d.png" % i, f, src), np.float32)[:, :, 3] / 255
    sh = np.clip((sh - HAZE) / (1 - HAZE), 0, 1)
    s = np.zeros(sh.shape + (4,), np.uint8)
    s[:, :, 3] = (sh * 255).round().astype(np.uint8)
    return o, Image.fromarray(s, "RGBA")


def dilate(mask, r):
    """Маска, расширенная кругом радиуса r px."""
    out = mask.copy()
    k = int(r)
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            if 0 < dx * dx + dy * dy <= r * r:
                out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def light(i, f, src=SRC):
    """Карта освещения курса i: RGBA, rgb — цвет света, a — его яркость (max канала)."""
    im = load("light_%02d.png" % i, f, src)
    a = np.asarray(im, np.float32) / 255
    rgb = a[:, :, :3] * a[:, :, 3:4]                            # премультиплицированный свет
    peak = rgb.max(axis=2)
    core = peak > CORE
    if core.any():
        lit = np.where(core[:, :, None], rgb, np.clip(rgb * LIT_GAIN, 0, 1))
        # глоу: размытые полосы, жёстко обрезанные кругом GLOW_R вокруг полос
        src_core = Image.fromarray((rgb * core[:, :, None] * 255).astype(np.uint8), "RGB")
        glow = np.asarray(src_core.filter(ImageFilter.GaussianBlur(GLOW_SIGMA)), np.float32) / 255
        glow = np.clip(glow * GLOW_K * 2 * np.pi * GLOW_SIGMA ** 2 / 3, 0, 1)
        glow *= dilate(core, GLOW_R)[:, :, None]
        lit = np.maximum(lit, glow)
    else:
        lit = rgb
    al = lit.max(axis=2)
    out = np.zeros(lit.shape[:2] + (4,), np.uint8)
    out[:, :, :3] = (np.clip(lit / np.maximum(al, 1e-4)[:, :, None], 0, 1) * 255).round()
    out[:, :, 3] = (al * 255).round()
    return Image.fromarray(out, "RGBA")


def main():
    """Атлас A (out/atlas) и, если отрендерен, B (out/atlas_b, колёса повёрнуты — кадр вращения): общая ячейка и
    общий shift, иначе подмена листа на ходу дёргала бы каретку на пиксель."""
    meta = json.load(open(os.path.join(SRC, "frame.json"), encoding="utf-8"))
    f = K.PX_RENDER // K.PX_GAME
    n = meta["facings"]
    gx, gy = meta["ground"][0] / f, meta["ground"][1] / f        # точка земли в кадре 64 px/тайл
    sets = [(suf, src) for suf, src in (("", SRC), ("-b", SRC_B)) if os.path.exists(os.path.join(src, "obj_01.png"))]
    layers = {}
    for suf, src in sets:
        objs, shads, lights = [], [], []
        for i in range(1, n + 1):
            o, sh = frame(i, f, src)
            objs.append(o)
            shads.append(sh)
            lights.append(light(i, f, src))
        layers[suf] = (objs, shads, lights)
    # общая рамка всех кадров всех листов (каретка + тень + свет), симметрия не нужна — её снимает shift
    box = None
    for objs, shads, lights in layers.values():
        for im in objs + shads + lights:
            bb = im.getchannel("A").point(lambda v: 255 if v > 2 else 0).getbbox()
            if bb:
                box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]), max(box[2], bb[2]), max(box[3], bb[3]))
    W, H = layers[""][0][0].size
    if box[0] == 0 or box[1] == 0 or box[2] == W or box[3] == H:
        sys.exit("силуэт упёрся в край кадра atlas.FRAME: %s в %dx%d" % (box, W, H))
    x0, y0 = box[0] - PAD, box[1] - PAD
    w, h = box[2] - box[0] + 2 * PAD, box[3] - box[1] + 2 * PAD
    w, h = w + w % 2, h + h % 2
    # пиксель (gx, gy) ячейки должен лечь на позицию − 2.9 px: центр ячейки + shift + (g − c) = −2.9
    lift = K.SPRITE_TILE_PX / 2 - K.SPRITE_GROUND_PX[1]
    shift = ((w / 2 - (gx - x0)) / K.PX_GAME, (h / 2 - (gy - y0) - lift) / K.PX_GAME)
    sheets = {}
    for suf, (objs, shads, lights) in layers.items():
        out = []
        for nm, ims in (("", objs), ("-shadow", shads), ("-light", lights)):
            sh_ = Image.new("RGBA", (w * n, h))
            for i in range(n):
                sh_.paste(ims[i].crop((x0, y0, x0 + w, y0 + h)), (i * w, 0))
            sh_.save(os.path.join(GFX, "cart%s%s.png" % (suf, nm)), optimize=True)
            out.append(sh_)
        sheets[suf] = out
    info = dict(width=w, height=h, line_length=n, variation_count=n, shift=[round(shift[0], 4), round(shift[1], 4)],
                sheets=["cart%s" % suf for suf in sheets])
    json.dump(info, open(os.path.join(SRC, "atlas.json"), "w", encoding="utf-8"), indent=1)
    print("atlas %s: %dx%d cell %dx%d shift %s" % (", ".join(info["sheets"]), w * n, h, w, h, info["shift"]))
    preview(sheets[""][0], sheets[""][1], w, h, n, shift)
    if "-b" in sheets:
        wheels_compare(sheets[""][0], sheets["-b"][0], w, h)


def wheels_compare(a, b, w, h, ids=(1, 5, 9, 13, 17)):
    """Кадры A и B друг под другом (×4) — видно ли вращение колёс."""
    P = Image.new("RGBA", (w * len(ids), h * 2), BG)
    for k, i in enumerate(ids):
        for r, sh_ in enumerate((a, b)):
            P.alpha_composite(sh_.crop(((i - 1) * w, 0, i * w, h)), (k * w, r * h))
    nearest(P, 4).save(os.path.join(SRC_B, "compare.png"))


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


def night(scene, lm):
    """Ночь как в игре: сцена × карта освещения (тьма NIGHT, поверх — спрайт света обычным смешиванием)."""
    sc = np.asarray(scene, np.float32)
    l = np.asarray(lm, np.float32) / 255
    a = l[:, :, 3:4]
    m = NIGHT * (1 - a) + l[:, :, :3] * a
    sc[:, :, :3] *= m
    return Image.fromarray(sc.clip(0, 255).astype(np.uint8), "RGBA")


def test(src):
    """Пробные курсы на тайле, 64 px/тайл ×4 (nearest): сверху день, снизу ночь с картой освещения."""
    meta = json.load(open(os.path.join(src, "frame.json"), encoding="utf-8"))
    f = K.PX_RENDER // K.PX_GAME
    gx, gy = meta["ground"][0] / f, meta["ground"][1] / f
    lift = K.SPRITE_TILE_PX / 2 - K.SPRITE_GROUND_PX[1]
    tile = Image.open(TILE_SPRITE).convert("RGBA")
    ids = sorted(int(n[4:6]) for n in os.listdir(src) if n.startswith("obj_"))
    cell = 112
    P = Image.new("RGBA", (cell * len(ids), cell), BG)
    L = Image.new("RGBA", P.size, (0, 0, 0, 0))
    for k, i in enumerate(ids):
        o, sh = frame(i, f, src)
        cx, cy = k * cell + cell // 2, cell // 2 + 8                                  # позиция сущности
        P.alpha_composite(tile, (round(cx - tile.width / 2), round(cy - tile.height / 2)))
        ox, oy = round(cx - gx), round(cy - lift - gy)
        sh.putalpha(sh.getchannel("A").point(lambda v: v // 2))
        P.alpha_composite(sh, (ox, oy))
        P.alpha_composite(o, (ox, oy))
        if os.path.exists(os.path.join(src, "light_%02d.png" % i)):
            L.alpha_composite(light(i, f, src), (ox, oy))
    T = Image.new("RGBA", (P.width, P.height * 2), BG)
    T.paste(P, (0, 0))
    T.paste(night(P, L), (0, P.height))
    nearest(T, 4).save(os.path.join(src, "test.png"))
    print("test %s: facings %s" % (os.path.relpath(src, HERE), ids))


if __name__ == "__main__":
    if "--test" in sys.argv:
        test(os.path.join(HERE, sys.argv[sys.argv.index("--test") + 1]))
    else:
        main()
