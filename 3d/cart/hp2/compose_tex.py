# -*- coding: utf-8 -*-
"""Лист текстур hp2: рендеры с материалами (ключ «T», render_tex.py) поверх спрайтов тайла.

Запуск (системный python):  python compose_tex.py   ->  out/sheet_tex.png
"""

import json
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))
sys.path.insert(0, HERE)
import compose as C  # noqa: E402
import scl3d as K  # noqa: E402

REF22 = os.path.join(HERE, "..", "film", "data", "images", "22.png")
REF13 = os.path.join(HERE, "..", "film", "data", "images", "13.png")    # справа — ванильные сундуки на песке
REF13_BOX = (776, 150, 1410, 520)
REF23 = os.path.join(HERE, "..", "film", "data", "images", "23.png")    # стальной сундук крупно (~220 px на тайл)
REF24 = os.path.join(HERE, "..", "film", "data", "images", "24.png")    # накладка над пружиной: контур автора
REF24_CROP = (330, 360, 770, 580)                                        # то же место на T_close_game
KEY = "P" if "--painted" in sys.argv else "T"      # P — карты автора (make.py --tex painted)
DARK = (22, 24, 26, 255)


def row(parts, gap=12):
    W = sum(p.width for p in parts) + gap * (len(parts) - 1)
    R = Image.new("RGBA", (W, max(p.height for p in parts)), DARK)
    x = 0
    for p in parts:
        R.alpha_composite(p, (x, 0))
        x += p.width + gap
    return R


def tile_x4():
    spr = Image.open(C.TILE_SPRITE).convert("RGBA")
    return C.nearest(C.on_bg(spr), 4)


def main():
    with open(os.path.join(C.REN, "frames.json"), encoding="utf-8") as f:
        frames = json.load(f)
    field64, _, _ = C.game_view(KEY, "field", frames, K.PX_GAME)
    field256, _, fr256 = C.game_view(KEY, "field", frames, K.PX_RENDER)
    ring64, _, _ = C.game_view(KEY, "ring32", frames, K.PX_GAME)
    x0, y0 = fr256.px(-0.55, 0.55, 0)
    x1, y1 = fr256.px(3.55, -1.75, 0)
    crop = field256.crop((int(x0), int(y0), int(x1), int(y1)))
    f2 = C.nearest(field64, 2)
    r2 = C.nearest(ring64, 2)
    hero = Image.open(os.path.join(C.REN, "%s_hero.png" % KEY)).convert("RGBA")
    cp = Image.open(os.path.join(C.REN, "%s_close_persp.png" % KEY)).convert("RGBA")
    cg = Image.open(os.path.join(C.REN, "%s_close_game.png" % KEY)).convert("RGBA")

    blocks = [
        row([C.panel(f2, "Игровой масштаб с материалами: 64 px/тайл, ×2 nearest",
                     "прямые и поезд с двумя поворотами; подложка — спрайт тайла"),
             C.panel(C.fit_h(crop, f2.height), "Крупно: игровой ракурс 256 px/тайл", "поворот и прямая")]),
        row([C.panel(r2, "32 курса, 64 px/тайл ×2"), C.panel(C.fit_h(hero, r2.height), "Вид 3/4 на болванке рельса")]),
        row([C.panel(C.fit_h(cp, 700), "Крупно 3/4: краска, потёртости, пыль, AO"),
             C.panel(C.fit_h(cg, 700), "Крупно, игровой угол 45° (без растяжки)")]),
    ]
    if os.path.exists(REF24):
        r24 = Image.open(REF24).convert("RGBA")
        r24 = r24.resize((r24.width * 2, r24.height * 2), Image.Resampling.LANCZOS)
        blocks.append(row([C.panel(r24, "рисунок 24: контур накладки (автор)"),
                           C.panel(C.fit_h(cg.crop(REF24_CROP), r24.height), "накладка сейчас, игровой угол 45°")]))
    # 64 px ×4 рядом со спрайтом тайла
    small = [C.panel(tile_x4(), "спрайт тайла ×4", " ")]
    for view, nm in (("single", "E-W"), ("single_ns", "N-S"), ("single_dg", "диагональ")):
        s64, _, _ = C.game_view(KEY, view, frames, K.PX_GAME)
        small.append(C.panel(C.nearest(s64, 4), "каретка %s, 64 px ×4" % nm, " "))
    blocks.append(row(small))
    # стальной сундук 23 рядом с кареткой в том же масштабе (сундук ~3.4 × 64 px/тайл на рисунке)
    if os.path.exists(REF23):
        H = 600
        r23 = C.fit_h(Image.open(REF23).convert("RGBA"), H)
        k = r23.height / 338 * 220 / 64
        s64, _, _ = C.game_view(KEY, "single", frames, K.PX_GAME)
        sd, _, _ = C.game_view(KEY, "single_dg", frames, K.PX_GAME)
        up = lambda im: im.resize((round(im.width * k), round(im.height * k)), Image.Resampling.LANCZOS)  # noqa: E731
        blocks.append(row([C.panel(r23, "референс 23: стальной сундук (ванила)"),
                           C.panel(up(s64), "каретка 64 px, в масштабе сундука"),
                           C.panel(up(sd), "каретка 64 px, диагональ")]))
    # сравнение с референсом 22 (ванильные машины и тайл автора): наш поезд в том же увеличении, что тайл на 22
    if os.path.exists(REF22):
        ref = Image.open(REF22).convert("RGBA")
        H = 648
        k = 3.2                                       # тайл 80 px на рисунке 22 ≈ 256 px → увеличение ×3.2
        x0, y0 = fr256.px(-0.6, 0.6, 0)
        f64c = field64.crop((int(x0 / 4), int(y0 / 4), int(x0 / 4) + int(H / k), int(y0 / 4) + int(H / k)))
        ours = f64c.resize((round(f64c.width * k), round(f64c.height * k)), Image.Resampling.LANCZOS)
        parts = [C.panel(ours, "hp2 с материалами, 64 px/тайл, ×3.2")]
        if os.path.exists(REF13):
            r13 = Image.open(REF13).convert("RGBA").crop(REF13_BOX)
            parts.append(C.panel(C.fit_h(r13, H), "референс 13: стальной сундук (слева) на песке"))
        parts.append(C.panel(C.fit_h(ref, H), "референс 22: ванила Space Age и тайл автора (справа)"))
        blocks.append(row(parts))
    W = max(b.width for b in blocks) + 24
    S = Image.new("RGBA", (W, 56 + sum(b.height + 14 for b in blocks)), DARK)
    C.label(S, "Каретка hp2 — PBR-карты автора (tex_in/, без карт — заглушки out/tex_stub/)" if KEY == "P" else "Каретка hp2 — генеративные материалы (Cycles): тёмная сталь как у стального сундука, кромки затёрты до "
               "металла, ржавчина в швах, рыжая пыль, AO; колёса и бампер — голый металл", 24, (12, 12))
    y = 56
    for b in blocks:
        S.alpha_composite(b, (12, y))
        y += b.height + 14
    nm = "sheet_painted.png" if KEY == "P" else "sheet_tex.png"
    S.save(os.path.join(C.OUT, nm))
    print("sheet", nm, S.size)


if __name__ == "__main__":
    main()
