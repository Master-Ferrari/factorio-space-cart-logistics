# -*- coding: utf-8 -*-
"""Сравнение вариантов в игровом масштабе (64 px/тайл ×2, nearest) — поле с поездами на спрайтах тайла.

  python compare/compare_game.py v8a v8b v8c
Берёт compose.py каждого варианта (его game_view), кладёт поля рядом.
"""
import importlib.util, json, os, sys
from PIL import Image, ImageDraw, ImageFont

CART = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
names = sys.argv[1:] or ["v8a", "v8b", "v8c"]
font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 26)
panels = []
for n in names:
    d = os.path.join(CART, n)
    sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("compose_" + n, os.path.join(d, "compose.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    sys.path.remove(d)
    with open(os.path.join(d, "out", "render", "frames.json"), encoding="utf-8") as f:
        frames = json.load(f)
    img, _, _ = m.game_view("A", "field", frames, m.K.PX_GAME)
    panels.append((n, img.resize((img.width * 2, img.height * 2), Image.Resampling.NEAREST)))
W = sum(p.width for _, p in panels) + 10 * (len(panels) + 1)
H = max(p.height for _, p in panels) + 60
out = Image.new("RGBA", (W, H), (22, 24, 26, 255))
dr = ImageDraw.Draw(out)
x = 10
for n, p in panels:
    dr.text((x + 4, 14), n, font=font, fill=(235, 235, 235, 255))
    out.alpha_composite(p, (x, 50)); x += p.width + 10
path = os.path.join(CART, "compare", "game_%s.png" % "_".join(names))
out.save(path); print(path)
